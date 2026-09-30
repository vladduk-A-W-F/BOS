# UXD03-WAIT-01 — исправленный контракт ожидания участника

**Статус:** `REVISED_PROPOSAL_NOT_ACCEPTED`.

Это независимая read-only доработка proposal после verdict `UXD03_WAIT_REVIEW_V1.json`. Она не является карточкой реализации, миграцией, изменением UI, QA-приёмкой или ростом готовности. Единственный прочитанный кандидат — clean commit `e710eb568717dfe3ede945feb899f030bd5ad1ab` в `C:/Users/user/.codex/worktrees/bos3-learning-proof/repo`. Выполнений, импортов, тестов, сборок, HTTP, runtime, БД и browser: **0**.

## 1. Рекомендованная модель и её граница

Рекомендуется один **устойчивый ортогональный blocker** `waiting for internal participant`, а не `Task.status='waiting'`.

`Task.status` уже имеет `active/process/done` и историческое `overdue` (`tasks/models.py:11-27`); `is_overdue` вычисляется отдельно из server `as_of`, deadline, отсутствия архива и незавершённости (`tasks/queries.py:6-19`). Ожидание не отменяет ход работы, дедлайн или исключение. Поэтому оно не меняет `status` и не выводится из `handoff.current`, просрочки, пустого результата или отсутствия следующей операции.

Минимальная будущая migration-backed модель:

```text
Task.waiting_for_employee  ForeignKey(Employee, NULL, PROTECT)
Task.waiting_reason        Text, NULL, max 240
CheckConstraint: waiting_for_employee IS NULL <=> waiting_reason IS NULL
```

Отдельное время начала не требуется: неизменяемое `AuditEvent.created_at` фиксирует начало и окончание. `PROTECT` предотвращает удаление строки, но не заменяет server validation при start или replay. Один blocker означает ровно одного внутреннего участника; внешние контрагенты, документы, сервисы и несколько зависимостей не входят в этот контракт.

## 2. Participant — внутренняя source-authorized сторона

При `start_task_wait` participant не является свободной ссылкой или будущим владельцем Task. Это внутренний business actor, который на момент start **активен и авторизован для всех накопленных source refs той же Task**.

Для participant обязательны все условия:

1. `Employee` существует, не архивирован и отличается от текущего `task.assignee_employee`.
2. У Employee есть активный linked User, ровно одна BoS role `ceo` или `manager`, и branch типа `department`.
3. `Policy.for_user(participant_user)` проходит тот же `check_sources()` для всех `tasks.queries.source_refs(task)`, что и инициатор. Это повторяет существенную часть handoff contract: sender и recipient проверяют sources отдельно (`tasks/handoffs.py:46-63`).
4. Ожидающая Task сама доступна actor через `Policy.tasks()`; текущие accumulated refs остаются единственным основанием list/detail/history visibility (`tasks/queries.py:44-52`).

Проверка participant делается при **preview**, перед **confirm**, при replay/status успешного `start_task_wait`, и после любой смены access revision на клиенте. Identity нельзя брать из текста формы: `actor_for_user()` заново читает active User, единственную role и неархивного Employee (`boss_project/identity.py:25-44`); middleware выдаёт `X-BoS-Access` либо `X-BoS-Identity: denied` (`operations/middleware.py:40-57`). Новый UI обязан отбрасывать list/detail/proposal response, если этот revision не равен текущему runtime revision, как существующий C01 reader.

### Disclosure matrix

Причина — только короткое operational explanation, 3–240 символов после trim. В ней запрещены персональные/медицинские/дисциплинарные сведения, телефоны/e-mail, credentials/secrets, содержимое документов, цены, суммы и реквизиты. Это не поле для произвольной заметки. Непустая, ограниченная и несекретная причина нужна именно потому, что обычная Task projection shared between all readers of the same permitted Task (`tasks/queries.py:55-65`), а history уже раскрывает audit reason permitted readers (`tasks/history.py:21-27`).

| Читатель, уже имеющий `Policy.tasks()` доступ | List | Detail | History |
|---|---|---|---|
| CEO | `waiting` boolean, participant full name + **текущий** department name, reason | то же; без user id, role, contacts, source payload | immutable start/end snapshot: participant id/name/department и reason на момент действия |
| Manager | то же, только после current Task source policy | то же | то же, только после current Task source policy |
| Observer | то же read-only после current Task source policy | то же read-only | то же read-only |
| Любой без current Task access | ничего: ни факт ожидания, ни имя/отдел, ни причина | 404/denied как текущая Task | 404/denied как текущая history |

Имя и department в list/detail — current permitted directory facts из server projection, не из client cache; после archive/deactivation они не должны объявляться текущими правами participant. В history хранится самостоятельный неизменяемый snapshot start: `{employee_id, full_name, department:{id,name}, waiting_reason}`. End event копирует этот snapshot как `ended_wait_snapshot`; он не пересчитывается по позднему rename, archive, department move или access loss. Это различает текущий display и исторический факт.

## 3. Две command actions и единый lifecycle guard

Новые action names, только через имеющиеся `POST /api/operations/preview/` и explicit `POST /api/operations/confirm/`:

```json
{"action":"start_task_wait","task_id":123,"waiting_for_employee_id":456,
 "waiting_reason":"Очікуємо контроль якості партії"}

{"action":"end_task_wait","task_id":123,
 "reason":"Контроль якості отримано та перевірено"}
```

`waiting_reason` является также audit reason start. End reason обязателен (3–240) и объясняет проверенное возобновление. Никакого auto-acceptance, notification, auto-end или изменения assignee/status/deadline нет.

Один server helper `waiting_guard(task, action, actor, payload, phase)` обязан вызываться из `clean/prepare`, `locked_references`, `apply`, handoff validation, generic update, proposal status/replay и confirm validation. Он даёт следующую исчерпывающую матрицу:

| Состояние Task | Разрешено | Заблокировано |
|---|---|---|
| Нет active wait; Task не archived и не done | `start_task_wait`; текущие allowed `update_task`, handoff, archive, completion по их существующим правилам | `end_task_wait` |
| Есть active wait | Только `end_task_wait` | Любой `update_task`, включая title/category/priority/deadline/order/assignee/status/result/archived; handoff; archive; completion; reopen; второй start |
| Archived или done | Нет wait action | start/end, пока отдельная существующая restore/reopen не вернёт Task к нормальному состоянию |

Во время wait CEO может выполнить start/end для видимой Task. Manager — только когда `actor.employee_id == task.assignee_employee_id`; observer никогда. End не требует, чтобы participant оставался active, linked, source-authorized или в прежнем department: действующий CEO/current assignee должен суметь снять реальный blocker после его deactivation/access loss. При этом end всегда повторно проверяет actor identity, current `Policy.tasks()` source access и current assignee rule. Таким образом deactivation не создаёт вечную блокировку и не запускает auto-clear.

## 4. Atomic, lock, proposal и replay contract

Новая модель не создаёт другой writer. Она расширяет действующий task command path: preview уже использует `transaction.atomic()` и ERP mutex (`tasks/commands.py:140-149`), confirm берёт mutex перед повторной task validation и CAS claim (`operations/service.py:139-192`). Порядок должен быть единым для start, end, update, handoff и proposal status validation:

```text
transaction.atomic
  -> erp.service.write_lock()
  -> Task.select_for_update()
  -> Employee.select_for_update() по sorted set:
       current assignee + waiting participant (если есть) + proposed participant
  -> fresh Policy/identity/source checks
  -> fingerprint/stale check
  -> ActionProposal receipt compare-and-set
  -> Task + AuditEvent + receipt в той же transaction
```

`operations/service.py` сейчас перечисляет только `create_task/update_task/handoff_task` при fingerprint, preview, lock и confirm (`operations/service.py:84-104`, `139-157`, `181-217`). Будущий product card обязан заменить эти повторяющиеся tuples единственным `tasks.commands.ACTIONS`, включающим start/end; иначе new action может обойти lock, task fingerprint или dispatch.

Fingerprint start включает full Task row с wait fields, full accumulated history/source refs, current assignee и proposed participant: Employee archive/branch, linked User active flag, group role/permissions и dataset/source facts. Confirm повторяет participant source authorization **после** locks. Fingerprint end включает Task wait fields, owner, source refs и actor access state; participant access намеренно не является end precondition.

Pending semantics:

* Pending **start** становится `proposal_stale`/denied при любом изменении Task, wait fields, assignee, participant active/user/role/department/source access, actor identity/access revision или accumulated sources.
* Pending **end** становится stale при изменении Task/wait fields/assignee/actor/source access. Participant archive/deactivation/source loss сам по себе не делает end stale.
* Existing pre-wait update/handoff/archive/complete proposal становится stale после successful start и дополнительно отклоняется `waiting_guard`; старый proposal не может обойти blocker.
* Stored start receipt/status повторно validates actor and participant source authorization, как handoff replay (`tasks/history.py:51-64` и `tasks/handoffs.py:73-80`). Stored end receipt/status validates actor and Task source access, но не participant availability.

Audit uses current `bos.task-change.v1`: action `start_task_wait`/`end_task_wait`, transition `wait_started`/`wait_ended`, current actor, `before`, `after`, impact, source refs и immutable waiting snapshot. `tasks.commands.state()` and `tasks.history.STATE_FIELDS` must include the whitelist wait state; history item must return immutable event snapshot rather than reconstruct it from a changed Employee. Neither result nor handoff expected_result is reused as waiting reason.

## 5. Projection and minimal future allowlist

Task list/detail receive only:

```json
"waiting": null | {
  "state":"waiting",
  "participant":{"employee_id":456,"full_name":"…","department":{"id":7,"name":"…"}},
  "reason":"…"
}
```

No user id, role, contact, source refs, document body, financial data or raw audit payload enters list/detail. Existing `TaskSerializer` delegates to `tasks.queries.project` (`tasks/serializers.py:5-10`), and current project/list use one projection (`tasks/queries.py:55-65`); this is the place for a single role-neutral whitelist after `Policy.tasks()`, not a frontend-only computed state.

Future migration-backed product card, only after an explicit root decision, may touch:

- `tasks/models.py`, new migration, `tasks/commands.py`, `tasks/queries.py`, `tasks/handoffs.py`, `tasks/history.py`, `tasks/views.py` only if needed for projection/query validation;
- `operations/service.py` for all action-dispatch/lock/fingerprint sites;
- focused isolated tests for start/end, policy drift, replay, stale old proposals, deactivation and immutable history;
- the separately owned UXD03 card only after server contract review.

No migration, DB apply, UI, route, reset, runtime operation or dynamic test is authorized by this source-only proposal. Current raw Task REST remains approval-required (`tasks/views.py:39-40`). The compact card must segment only after receiving the server field: `archive -> done -> overdue -> waiting -> process -> active`; an overdue waiting Task remains an exception and still shows its blocker.

## 6. Remaining owner decisions

This proposal deliberately chooses a single internal source-authorized participant and no auto-acceptance. It does **not** decide or authorize:

1. external/system/document dependencies or multiple concurrent participants;
2. pausing contractual deadline or suppressing overdue while waiting;
3. broader disclosure than the explicit non-sensitive matrix above;
4. any migration-backed implementation or DB apply.

The root/integrator must explicitly accept this persistent schema, disclosure and lifecycle matrix as a new product card before implementation. Until then the accepted UI contract displays only existing facts; no `waiting` field, counter, cause or action may be invented.

## 7. Revision disposition

This revision addresses all three independent P1 findings: (1) participant source authorization, access revision and exact disclosure/sensitivity rules; (2) one guard, exhaustive transition matrix and shared lock/fingerprint/CAS/dispatch path; (3) separate start/end drift rules, end-after-deactivation, no auto-clear and immutable audit snapshots.

It remains a proposal. `TECHNICAL_READY`, `PILOT_ALLOWED`, `MVP`, UXD-03 and full readiness are unchanged.
