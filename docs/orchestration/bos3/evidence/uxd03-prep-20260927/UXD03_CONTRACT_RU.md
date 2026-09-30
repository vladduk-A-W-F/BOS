# B30-UXD03-PREP — контракт карточки очереди отдела

Статус: **PREPARED_FOR_INDEPENDENT_REVIEW**, reviewer `bos3_candidate_review`. Это подготовка по исходникам, не реализация и не приёмка UXD-03, прав, runtime или full readiness.

Проверенный checkout: `C:/Users/user/.codex/worktrees/bos3-product-design/repo`, detached HEAD `e710eb568717dfe3ede945feb899f030bd5ad1ab`; перед чтением дерево чистое. Вход: `D:/3/BOSDev/evidence/bos3-readiness-20260927/UXD_SOURCE_DELTA_E710.json`. Полные Git blob IDs и SHA-256 исходников, входного delta и этого документа находятся в `HANDOFF.json`. Сообщённые координатором product/runtime/docs pins не заменяют проверку установленного сервера; HTTP и runtime здесь не исследовались.

## 1. Подтверждённая основа и точная граница пробела

**Настоящая очередь уже существует.** `Tasks` в `frontend/boss_app_source.html:2443–2463` получает `/api/tasks/?archived=false&department_id=<ID>`, дерево отделов, справочник сотрудников и серверную дату. `TaskViewSet.get_queryset` (`tasks/views.py:18–37`) сначала применяет `Policy.tasks()`, затем фильтрует `assignee_employee__branch_id` и `assignee_employee__branch__type='department'`. ID отдела — положительное ASCII-число; повторные параметры отклоняются. Это параметр фильтра, не поле `Task.department_id`.

Текущий исполнитель уже показан на карточке: `assignee_name`/`assignee`, `assignee_id`, deadline, status, is_overdue, priority, category и первоначальная branch_name. Пробел — не отсутствие очереди или исполнителя вообще: карточка не выводит связь `order_id/order_code` и компактные сведения `handoff` о передаче. История и подробности есть в существующем диалоге.

`Task.branch` — исходный бизнес-контекст. Отдел очереди — **текущая** `Employee.branch` исполнителя. Передача меняет assignee, deadline и status, но не Task.branch (`tasks/handoffs.py:65–85`). Исторический `handoff.recipient.department` — снимок отдела при передаче; он не обязан совпадать с нынешним отделом сотрудника. Нельзя смешивать эти три значения.

Действующие фильтры: рабочие/архивные, входные, в работе, выполненные, просроченные. `c01TaskSegment` (`frontend/boss_app_source.html:3740`) выбирает archive → done → is_overdue → process → active. Серверный `is_overdue` вычисляется из server as_of, deadline, незавершённости и отсутствия архивирования (`tasks/queries.py:6–19`). Исторический raw status `overdue` допускается моделью, но новые команды принимают только active/process/done. «Вхідні» означает открытые назначения; это не подтверждение личного принятия. Фильтр сроков — диапазон дедлайнов, не исторический отчётный период.

## 2. Часть A — сведения существующего списка для компактной карточки

Общий источник: `TaskSerializer.to_representation → tasks.queries.project` (`tasks/serializers.py:10`, `tasks/queries.py:55–65`). Это одна проекция для list и retrieve; отдельного API `current_handoff` нет, настоящее имя — `task.handoff` с `handoff.current`.

| Факт | Точное поле / источник | Разрешённое представление и граница |
|---|---|---|
| Идентичность | `id`, `title`, `category` | Заголовок и «Доручення №ID». Текст через обычный React text, без HTML. Ничего не брать из скрытых строк или глобального audit. |
| Исполнитель сейчас | `assignee_id`, `assignee_name`, fallback `assignee` | «Виконавець: … · №ID». При null — исторически не назначен, не выдуманный пользователь. Это уже есть на карточке. |
| Срок и рабочее состояние | `deadline`, `status`, `is_overdue`, `archived`, `archived_at` | Срок или «Не задано»; текущие украинские подписи `C01_STATUS`. Просрочку брать из server `is_overdue`, а не локальных часов. Архив отделён от выполнения. |
| Приоритет | `priority` | high/medium/low/null; null не повышать до medium и не трактовать как отсутствие задачи. |
| Исходная бизнес-филия | `branch`, `branch_name` | Явная подпись «Початкова бізнес-філія». Не использовать для вычисления принадлежности очереди отдела. |
| Текущий отдел очереди | query `department_id`, дерево `/api/branches/`; для текущего сотрудника каталог `/api/employees/` и `Employee.branch` | Только узлы `type=department`, выбранные по ID. Отдел — фильтр внутри разрешённых задач, не самостоятельное право. Не использовать свободную строку `Employee.department` или должность `Employee.role` для прав. |
| Связь с текущим заказом | `order_id`, `order_code` | При ненулевом ID строка «Замовлення <code или №ID>». При null — «Поточне замовлення не прив’язано»; это не доказывает отсутствие исторических или закупочных источников. Клик ведёт в существующий проверяемый диалог Task. Не показывать цены, строки заказа или документы из одного наличия ID. |
| Последняя передача | `handoff.schema`, `handoff.state`, `handoff.current`, `handoff.recipient.employee_id` | Только валидная `bos.task-handoff.v1`. Для current=true дополнительно сопоставить recipient.employee_id с assignee_id. Подпись «Остання передача: призначення чинне» или «Попереднє призначення». Не писать «прийнято», «очікує» или «в роботі» из факта sent. |
| Получатель при передаче | `handoff.recipient.employee_id`, `.department.id/.name` | Разрешённый краткий факт из уже полученной проекции: «Отримувач передачі: №…; відділ на момент передачі …». Имя текущего получателя брать из assignee_name только при совпадении ID и current=true. Иначе сохранять исторический ID, не угадывать имя. |

`tasks/handoffs.latest` (`94–103`) ищет последнюю сохранённую handoff-подию, возвращает null либо `sent/superseded` и `current`. `current` оценивает применимость назначения по исполнителю и последующим изменениям assignee, **не** незавершённость задачи, ожидание или принятие. Он может сохраняться у выполненной задачи. `handoff.as_of` — бизнес-дата; в этой проекции нет точного timestamp/ID handoff-события. Для времени реальной передачи нужна история с `created_at`, а не подмена значением as_of.

У `handoff` также существуют `sender.{user_id,employee_id,role,department}`, `previous_assignee.employee_id`, `recipient.{user_id,employee_id,role,department}`, `expected_result`, `deadline`, `source_refs`, `as_of`. Для минимальной карточки не разворачивать весь объект. `handoff.deadline` — срок при передаче, способный отличаться от текущего `task.deadline`. `handoff=null` обозначать «Відомостей про передачу немає», а не «передач никогда не было».

Важное ограничение: list-проекция уже возвращает `result`, `result_recorded` и подробный handoff, включая expected_result и идентификаторы участников. Предлагаемая краткая карточка — whitelist отображения, **не новая серверная граница секретности**. Нельзя утверждать, что эти данные отсутствуют в сетевом ответе. Если требуется их скрытие от роли на уровне API, это отдельная проверяемая задача policy/projection вне настоящего контракта.

## 3. Часть B — подробности, история и источники через существующие проверки

| Переход | Существующий маршрут / функция | Что проверяется и что можно показать |
|---|---|---|
| Открыть Task | `GET /api/tasks/<id>/`; `ControlledTask`, `C01TaskLegacy`, `C01Handoff` | Retrieve через `Policy.tasks()` и ту же Task-проекцию. Сначала повторное чтение, совпадение ID и access revision; затем текущие факты, `result` отдельно от expected_result, источники и передача. |
| Прочитать историю | `GET /api/tasks/<id>/history/?limit=20[&cursor=…]`; `tasks/views.py:42`, `tasks/history.py:21–46` | Повторно `policy.tasks().get`. `items`: id/action/created_at/transition/actor/reason/before/after/changes/handoff/legacy. Whitelist `STATE_FIELDS` и `CHANGE_FIELDS`, не сырой AuditEvent. Cursor связан с task_id, actor_id, access_revision, cutoff/last; limit 1–50. Нет основания считать одну страницу полной историей. |
| Открыть источник Task | `C01TaskSource`, `c01GatherSources` (`frontend/boss_app_source.html:3770,3778–3783`) | Повторно Task + history(limit=50), проверка принадлежности выбранного ref, затем защищённый источник. Это UI-композиция существующих GET, **не** отдельный `/task-source/` endpoint. Источник за пределами прочитанной страницы нельзя выдумать; неполная история — не отсутствие источника. |
| Заказ | `GET /api/erp/snapshot/` → `erp.queries.snapshot(policy)` → `operations.projections.snapshot` | Найти конкретный order_id только среди полученных orders; показывать проверенные code/status/due_date в текущем просмотре. Список Task не даёт права обходить ERP policy или брать суммы из другого кэша. |
| Закупочная заявка | `GET /api/operations/compare/?code=<request_code>` | `Policy.requests().get`, затем `projections.comparison`; разрешённые request/quote факты. У observer удаляются totals части сравнения и recommendation; partial allocation явно restricted, не ноль. Не переносить весь ответ в очередь. |
| Документ | `GET /api/operations/documents/<id>/` | `Policy.document`: отдельная проверка документов, текст/sections/версии только после успешного ответа. Download — другой маршрут `/download/` и отдельное `download_document`, в том числе для CEO. |
| Историческая квитанция / неизвестный исход подтверждения | `GET /api/operations/task-proposals/<uuid>/`; `tasks/history.py:51–65` | Только собственное proposal.user_id, совпадающая роль, нынешний policy.action, для handoff — повторная проверка сторон/источников; успех связывается с доступной Task и audit_id, затем receipt projection. Это не общий список передач и не состояние ожидания участника. |

На компактной карточке не выводить `result`, `expected_result`, history.reason, before/after, полные source_refs, user_id/роль отправителя, содержимое документов, финансовые поля, персональные контакты, KPI или зарплаты. Их наличие в других ответах не оправдывает объединение кэшей. Сохраняется существующий явный путь «Task → джерело / історія → повернутися», с проверкой данных при каждом открытии. Минимальная реализация может лишь подписать существующую кнопку «Відкрити доручення — джерела й історія»; она не обещает уже отсутствующий прямой переход/автооткрытие нужной записи (отдельная UXD-02).

Причина исторической передачи хранится как `AuditEvent.payload.reason` и доступна через task history; она **не является** `waiting_reason`. `result` — фактический/предыдущий результат Task; `handoff.expected_result` — ожидаемый результат конкретного назначения. Эти тексты и сроки нельзя объединять.

## 4. Роли, policy и проекции

Идентичность выводится сервером из активного пользователя, одной группы ceo/manager/observer и связанного неархивного Employee (`boss_project/identity.py:25–50`). Job title не задаёт роль. `LocalRoleGuard` (`operations/middleware.py`) повторно проверяет identity, ставит `X-BoS-Access`, возвращает `X-BoS-Identity: denied` при отказе, блокирует unsafe для observer и проверяет CSRF. Это прочитанная реализация, не доказательство динамической безопасности установленного сервера.

| Область | CEO | Manager | Observer |
|---|---|---|---|
| Доступные Task | `visible_tasks` возвращает все Task; затем выбранные list-фильтры | Все Task, для которых **каждый накопленный** order/request ref доступен по текущей policy | Тот же алгоритм проверки всех refs, но document policy уже: operational вместо operational+management |
| Отдел | Тот же department_id по текущему Employee.branch | Фильтр не ограничен автоматически «своим» отделом | Аналогично; отдел не расширяет разрешённый набор |
| Отсутствующие/повреждённые refs | CEO bypass в visible_tasks | refs=None скрывает Task; пустой валидный список refs удовлетворяет all([]), поэтому несвязанные Task не автоматически скрыты | То же; нельзя заявлять, что observer видит только лично назначенные или связанные задачи |
| Список/деталь/история Task | Одна project; history после повторного task scope | Такая же Task-проекция после object scope; нет отдельного role-based исключения result/handoff в TaskSerializer | То же чтение; отсутствие write не запрещает уже разрешённую историю |
| Справочник Employee | Сериализатор может вернуть личные поля; краткая очередь их не использует | Только DIRECTORY: id/full_name/role/department/branch/branch_name/archived_at | Тот же DIRECTORY; phone/email/birthday/kpi не добавлять через обход |
| Документы/ERP | CEO-policy | `view_document`, operational/management, исключения private statement docs; ERP IDs зависят от доступности документов и связанных объектов | `view_document`, только operational и те же private исключения; ERP/compare дополнительно ограничены проекцией |
| Передать Task | Незавершённая неархивная доступная Task, валидный иной получатель и все источники у обеих сторон | Дополнительно actor.employee_id обязан совпасть с текущим task.assignee_employee_id | Действие запрещено; кнопки нет |
| Создать/изменить/архивировать | Текущий preview/confirm command путь | Текущий policy.action + task/source validations; нельзя приписывать update_task ограничение «только своё» из отдельного handoff-правила | Изменения запрещены |

Накопленные refs берутся из текущего sales_order и всего AuditEvent Task, включая исторически отвязанные order/request (`tasks/queries.py:23–52`). Потеря доступа к любому из них скрывает Task у non-CEO; это не фильтр по отправителю или department membership. Исторические опасения private membership / cross-role acceptance здесь не объявляются закрытыми.

Получатель handoff должен иметь неархивного Employee, активного связанного пользователя, явную ветку type=department, роль CEO/manager и доступ ко всем refs. Все условия подтверждает сервер (`tasks/handoffs.py:37–62`). Справочник сотрудников не раскрывает надёжную готовую allowlist получателей: должность, имя и branch сами по себе недостаточны. UI `c01CanHandoff` — affordance, не замена этой проверки.

Изменения остаются только через `POST /api/operations/preview/` → явное подтверждение → `POST /api/operations/confirm/`. Raw POST/PUT/PATCH/DELETE Task возвращают approval_required (`tasks/views.py:39–40`). Для handoff exact payload: action/task_id/assignee_id/expected_result/deadline/reason, action=`handoff_task`. Нет автоматического вызова при открытии карточки. Подтверждение передаёт назначение и ставит active; оно не создаёт отдельного «принял».

## 5. Часть C — действительно отсутствующая семантика ожидания

В проверенных Task model, project, command FIELDS/ACTIONS и handoff protocol нет `waiting`, `waiting_reason`, `waiting_for_employee_id`, dependency state, accepted_at/accepted_by или команд start_wait/resume/accept_handoff. Модель хранит active/process/done/исторический overdue; command.clean принимает новые active/process/done. `pending/expired/unknown/succeeded` proposal recovery — состояние подтверждения команды, не работы другого участника.

Нельзя выводить ожидание из sent, current=true, просрочки, пустого result, отсутствия следующей операции, наличия заявки или локального флага. Нельзя заводить фронтенд-only статус, счётчик ожидающих, фиктивную причину, заглушку с нулём или «Прийняти», которая лишь меняет цвет.

**Открытое решение UXD03-WAIT-01 для владельца/единственного интегратора:** является ли ожидание самостоятельным сохраняемым состоянием Task или ортогональным блокером зависимости? Нужно определить: кто вправе установить/снять его; фактический участник или тип зависимости; обязательная причина и её видимость; влияние на deadline/overdue; кто подтверждает возобновление; поведение при передаче/архивировании/завершении; аудит и повтор подтверждения.

Без решения — реализуем только краткое представление существующих фактов, без waiting-фильтра. Если ожидание входит в следующий scope, нужен отдельный согласованный command/data/projection/policy контракт; вероятна схема/миграция для устойчивого состояния либо явно согласованная серверная проекция событий. Выбор event-backed варианта нельзя считать разрешённым обходом модели. Это не часть UI allowlist ниже и не объявленная готовая реализация.

## 6. Минимальная карточка и сохранение дизайна

Ниже структура предложения; фигурные поля — ссылки на контракт, не демонстрационные бизнес-факты:

```text
{title}                                      {status; is_overdue}
Доручення №{id} · {category}
Виконавець: {assignee_name / assignee} · №{assignee_id}
Строк: {deadline / Не задано}    Пріоритет: {priority}
Замовлення: {order_code / №order_id / не прив’язано}
Остання передача: {чинне / попереднє / відомостей немає}
Отримувач передачі: №{recipient.employee_id}
Відділ на момент передачі: {recipient.department.name}
Початкова бізнес-філія: {branch_name / Не визначено}
[Відкрити доручення — джерела й історія] [Передати, якщо дозволено]
```

Для null handoff две строки получателя не рисовать; для устаревшего назначения явно «попереднє». Не дублировать имя текущего исполнителя как историческое. На узком экране строки идут вертикально, ID и длинные коды переносятся; кнопки с читаемой подписью, целевой высотой не менее 44 px. На широком экране сохранить auto-fit/minmax(min(100%,300px),1fr) существующей очереди, без фиксированных высот/обрезания текста.

Использовать текущие `article.c01-current`, `.erp-actions`, `.op-muted` и токены `--bos-surface`, `--bos-ink`, `--bos-muted`, `--bos-line`, `--bos-primary`, `--bos-warning`, `--bos-danger` (`frontend/bos_design.css:3–10,22,139,551–556`). Белая поверхность, тонкая граница, radius 14 px, текущая изумрудная основная кнопка; предупредительный цвет сопровождается текстом. Сохранить светлую desktop/mobile оболочку, фокус и reduced motion. Не добавлять новую сетку приложения, framework, внешние изображения или «ожидание» как украшение.

Состояния берутся из текущего Tasks owner/view lifecycle: loading очищает старые facts; fresh разрешает отображение и open; stale/error/denied показывают сообщение и явное обновление; пустой **успешный** набор говорит только об отсутствии доступных записей по выбранным фильтрам. При смене scope/department/archive — cancel, очищение данных и диалога. Утрата identity глобально возвращает вход. Не сохранять row bodies/историю/HR в localStorage. Сохранить существующий возврат фокуса и перечитывание списка после подтверждения; не заменять их optimistic обновлением приёмки.

## 7. Предлагаемая будущая allowlist и проверяемый выход

Этот документ **не выдаёт разрешение на исполнение**. Для последующей минимальной UI-карточки после отдельного допуска:

| Категория | Пути / граница |
|---|---|
| Редактируемые исходники | `frontend/boss_app_source.html`: только Tasks compact-card display и необходимые локальные presentation helpers; `frontend/bos_design.css`: только стили этих карточек. |
| Генерируемые результаты будущей штатной сборки | `frontend/boss_app_html.html`, `assets/app.js`. `scripts/build_frontend.cjs` остаётся существующим механизмом, не предметом изменения. Здесь сборка не запускалась. |
| Уточнение контракта/доказательства | Отдельный согласованный путь docs/evidence, назначаемый интегратором. Текущий output — только UXD03_CONTRACT_RU.md и HANDOFF.json в указанном scratch. |
| За пределами UI-карточки | tasks/models.py, commands.py, handoffs.py, history.py, queries.py, serializers.py, views.py, migrations; boss_project/policy.py/identity.py; operations policy/projections/service; новые маршруты; DB/seed/reset/runtime. Waiting требует нового решения, не скрытого расширения этой allowlist. |

Критерии будущего review: значения карточки совпадают с доступной list-проекцией; роли/отделы не расширяют видимость; null/legacy и сменённый исполнитель не создают ложной передачи; отсутствие документов/денег не заменяется нулями; history/source открываются с повторной проверкой, cursor не переиспользуется между пользователями; card не меняет Task и не выдаёт sent за acceptance/waiting; мобильный перенос/клавиатура сохраняют доступность. Нужные будущие динамические проверки назначаются отдельно с учётом NEW/SAME-PROBLEM и прежних лимитов — здесь они не запускались и не считаются PASS.

Текущий DoD: точный source-bound контракт, три разделённые группы фактов, матрица трёх ролей, список настоящих маршрутов/проекций, минимальный layout, ограниченная будущая allowlist и открытое waiting-решение. Приёмка этого документа принадлежит `bos3_candidate_review`, интеграция — единственному root. TECHNICAL_READY/PILOT_ALLOWED/MVP не изменяются.
