# Контракт навчальної сесії · авторський результат

## R2 · фактичне прийняття адресної корекції GCR01

До предметної корекції звірено повний writer-допуск `GUIDED-LEARNING-CONTRACT-CORRECTION-R2-20261001`: SHA-256 `2ee8eeb77792656650c38b8db1d7f9fe39d99953bf9d6407c8ef2ec0146f4fc3`. Review snapshot і original збігаються: `23b3a1e1b1bf0d8184a0852073f971ef6ff71e8b3f12235aa2b971a54509b672`. Поточна таблиця збігається з frozen writer-r1: `4902e0bf6d508848dbe62c5a3c907f68a2ca4293ad3717b69e0de029a4ee5e02`; базовий report: `c8c4493415c8d1b608b88bede769a42d1ca9a3ba423c813f8b22dc1db1633752`. HEAD source повторно прочитано: `aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975`. Workspace і allowlist ті самі два файли; requested Astra/high, observed UNCONFIRMED. Context actual accepted; R2 author in progress. Прийняті field/ID mappings не відкрито повторно; scope лише CLEAR_RESET/GCR01.

## R2 · результат GCR01

Статус адресної корекції: **AUTHOR_COMPLETE_UNREVIEWED**. GCR01 має авторське disposition у `lifecycle[id=CLEAR_RESET]`: `implementation_gap`, `UNSUPPORTED_BY_EXISTING_TRAINING_API`, посилання на чинні GC-F05/GC-F06. Блокера авторської корекції немає; незалежне закриття finding ще не виконано.

- `start` повторно використовує запис тієї самої identity та не очищає progress/current_step; `pause` змінює status зі збереженням прогресу. [training/service.py:234](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/service.py:234).
- Чинні дії — start/pause/tour/navigate/check; невідома дія відхиляється. Clear/reset/delete не мають підтриманої операції в перевіреному training API. [training/service.py:260](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/service.py:260), [training/urls.py:4](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/urls.py:4).
- Виняток для observer дозволяє лише наявні операції навчального прогресу. Нових reset-прав немає. [operations/middleware.py:53](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/operations/middleware.py:53).
- `setSession(null)` при виборі кейсу — локальний UI стан. Очищення UI/URL/браузерного сховища не є server reset і не видаляє progress/current_step або проведені ERP/CRM факти. Попередження UI прямо відокремлює повторне проходження від стирання даних браузера. [frontend/boss_app_source.html:5480](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/frontend/boss_app_source.html:5480), [локальний choose:5485](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/frontend/boss_app_source.html:5485).

Для майбутнього reset власник — training/domain owner лише за окремим рішенням sole integrator про scope, права, збереження доказів і семантику нового проходження. Ця корекція не додає API, видалення сесії чи дозволу повторно провести операції. Main передає exact corrected snapshot enablement; автор не контактує з іншими чатами.

R2-SC03 порівняв поточний JSON із frozen R1 після вилучення тільки нового correction_r2 і CLEAR_RESET: решта об’єкта повністю збіглася. Нові шість source refs та чотири hashes перевірені. Exit 0. Повний фактичний script і raw output збережено в `correction_r2.static_checks`; попередні R1 static_checks лишилися історичними.

```json
{"scope":"GCR01_ONLY","frozen_base_sha256":"4902e0bf6d508848dbe62c5a3c907f68a2ca4293ad3717b69e0de029a4ee5e02","prior_mapping_unchanged":true,"clear_reset_entries":1,"new_evidence_refs":6,"gap_ids":["GC-F05","GC-F06"],"executions":0,"QA":"NOT_RUN"}
```

R1 містив 9 lifecycle-подій і 293 evidence refs; R2 додає тільки CLEAR_RESET і 6 refs (разом 10 та 299). Кількість lesson/step/session fields, 8 gap groups і source pin залишилися попередніми.

Поточний SHA-256 [SESSION_CAPABILITIES.json](D:/3/BOSDev/qa-scratch/bos3-guided-contract-20260930/writer/SESSION_CAPABILITIES.json): `a5d0baa5797a795931dedc9fa6c8d54a6c288acfcee403e6671bef49c7ffa4c8`. SHA цього report передається зовні. Product executions=0; runtime/live/visual/behavior/progress NOT_RUN; readiness та contract acceptance=false.

## Збережений авторський результат R1

Статус R1: **AUTHOR_COMPLETE_UNREVIEWED** на момент авторської передачі. Задача GUIDED-LEARNING-CONTRACT-FIELDS, writer `01a0be9f-b413-7822-9f93-16ba69f4f00f`. Подальший незалежний review повернув CHANGES_REQUIRED; GCR01 адресовано у R2 вище, без самоприймання.

Після переривання продовжено ту саму задачу і папку. До предметного читання source фактичне прийняття контексту записано в обох дозволених outputs. SHA-256 admission та п’яти references збіглися; `git rev-parse HEAD` повернув `aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975`. Папка writer була порожня. Requested `gpt-6-astra/high`; observed `UNCONFIRMED`. Canonical/remote commits не підміняють цей source.

Allowlist: лише `D:/3/BOSDev/qa-scratch/bos3-guided-contract-20260930/writer/SESSION_CAPABILITIES.json` і `AUTHOR_REPORT_UA.md`. Прийняті IDENTITY_MAP та Q01–Q03 використано як залежності; їх bytes, авторство та статуси не змінено й повторного review не проводилося.

## Що фактично підтримується

Сесія зберігає public UUID, user, role, installation_id, fixture_id/hash, case_id, status, current_step, progress і tour_state: [training/models.py](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/models.py:7). Ключ не залежить від Django session_key, тому повторний вхід тим самим користувачем/роллю/fixture/кейсом знаходить той самий навчальний запис. API має GET content/state та POST start/pause/navigate/check/tour; окремого resume API немає: [training/service.py](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/service.py:234).

Progress зберігає тільки `{step_id:{stamp}}`; stamp обчислюється з observed, expected answer, access_revision і fixture hash. Факти/evidence щоразу читаються із джерел. GET може вивести needs_recheck без запису цього стану в DB; check записує новий stamp лише після перевірки: [training/service.py](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/service.py:179) і [training/service.py](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/service.py:266).

Права походять із server identity і чинної policy: активний user, одна групова роль, неархівний employee, власник ізольованої synthetic установки. Case03 — CEO; observer може записувати лише навчальний прогрес, а operation/crm кроки для нього перетворюються на числові answer. Business commands проходять окремі preview/confirm, CSRF, role/source gates і прив’язку proposal до user/role/auth session: [training/access.py](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/access.py:18), [operations/middleware.py](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/operations/middleware.py:53), [operations/service.py](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/operations/service.py:130).

## Покриття полів

У JSON кожен рядок має фактичний symbol/file/line/fileSHA, поточну операцію, посилання на точні rights/owner gates і gap ID. `exists` означає наявну source-семантику (alias названо явно), а не literal назву поля чи dynamic PASS.

| Група | Поле | Статус | Gap |
| --- | --- | --- | --- |
| lesson | `lesson_id` | implementation_gap | GC-F01 |
| lesson | `lesson_version` | implementation_gap | GC-F01 |
| lesson | `product_source` | partial | GC-F01 |
| lesson | `case_id` | exists | — |
| lesson | `goal_uk` | exists | — |
| lesson | `prerequisites` | partial | GC-F05 |
| lesson | `role_requirements` | partial | GC-F05 |
| lesson | `data_mode` | partial | GC-F05 |
| lesson | `steps` | exists | — |
| lesson | `source_references` | partial | GC-F01, GC-F02 |
| lesson | `faq` | implementation_gap | GC-F07 |
| lesson | `acceptance_status` | implementation_gap | GC-F07 |
| step | `step_id` | exists | — |
| step | `kind` | partial | GC-F04 |
| step | `title_uk` | exists | — |
| step | `explanation_uk` | partial | GC-F01, GC-F05 |
| step | `source_refs` | partial | GC-F02, GC-F03 |
| step | `expected_context` | partial | GC-F01, GC-F02 |
| step | `allowed_action` | partial | GC-F05, GC-F08 |
| step | `completion_rule` | partial | GC-F04, GC-F05 |
| step | `success_evidence` | partial | GC-F03 |
| step | `next_step` | partial | GC-F06 |
| step | `error_states` | partial | GC-F05, GC-F02 |
| step | `pause_resume_rule` | partial | GC-F05, GC-F06 |

Усього: 24 поля — 5 exists, 15 partial, 4 implementation_gap. Усі 5 session requirements зіставлені окремо і мають partial; часткову підтримку не підвищено до виконання повного нового контракту.

## Конкретні прогалини

- **GC-F01 — Ідентичність і версія уроку та точний product source.** Немає lesson_id/lesson_version/content revision/product commit у session identity або progress stamp. Fixture hash — seed, не lesson revision. Очікуване уточнення: Майбутній контракт має визначити approved lesson/version/source binding і правило перевірки старого прогресу після зміни; не прирівнювати case/schema/fixture до версії уроку.
- **GC-F02 — Повний контекст джерел і звірка з тим, що бачив користувач.** Немає expected_context input або системного stamp всіх source PK/lesson revision. Observed values можуть збігатися у змінених джерел; check читає current facts без client expected context. Очікуване уточнення: Контракт має визначити які source identities/revisions прив'язують доказ, і поведінку context_changed без перенесення успіху на інший context.
- **GC-F03 — Зв'язок навчального результату з квитанцією команди.** progress зберігає лише stamp. Немає link step -> proposal/receipt/event/task/deal або перевіреного result snapshot; crm step evidence — boolean. Task proposal-status recovery існує, але training не зберігає потрібний proposal UUID. Очікуване уточнення: Семантика має відрізняти already-existing domain fact від команди цього навчального проходження; для вимоги receipt визначити чинний спосіб зв'язку/відновлення або явний implementation gap.
- **GC-F04 — П'ять видів кроку проти трьох чинних видів.** Source має answer/operation/crm; information і source_check не окремі типи; operator/observer semantics різні. Очікуване уточнення: Кожен proposed kind повинен мати явне зіставлення або окремий implementation gap. Tour completed не дорівнює information step/ERP result.
- **GC-F05 — Декларативні передумови, дозволена дія, стани помилки й правила паузи.** Права й predicates існують у коді, але немає structured prerequisites/role_requirements/allowed_action/expected_context/error_states/per-kind pause_resume_rule; route не є command permission. Очікуване уточнення: Контракт описує чинні gates, operations та status/error mapping; не додає мовчазного права, нового API чи generic executor. Наявний код не називається повною підтримкою proposed полів.
- **GC-F06 — Збережений поточний крок і наступний доступний крок.** Немає server next_step. New session.current_step може бути blank; GET не нормалізує current_step після stale попереднього кроку; frontend сам знаходить available і викликає navigate. Очікуване уточнення: Контракт визначає valid current/next on start/reentry/invalidation/pause та чіткий статус; ці правила не оголошуються реалізованими сервером.
- **GC-F07 — FAQ і статус приймання навчального змісту.** Немає lesson FAQ/acceptance_status у registry/model/API. Навчальне completed не є прийняттям contract або product readiness. Очікуване уточнення: Enablement має визначити approved content/FAQ/acceptance як матеріал контракту або окрему реалізацію. Наявні review артефакти не стають runtime fields автоматично.
- **GC-F08 — Навчальні передумови до CRM handoff.** Порядок followup -> crm є у training steps; check/navigate не приймає locked step. Однак CRM draft/prepare приймають in_progress/paused/needs_recheck session і перевіряють ownership/sources без перевірки session.progress попередніх кроків. UI CRM CTA залежить від hasSession, а не завершеного followup. Очікуване уточнення: Зберегти Q02 як прийняту вимогу порядку; не заявляти backend-enforced prerequisite. Якщо потрібен обов'язковий допуск лише після підтвердженого доручення, це конкретний майбутній implementation gap.

## Повернення, пауза та вже виконані дії

Вибраний slug зберігається в URL перед входом; це не серверний last_case для іншого пристрою. Pause зберігає current_step/progress; start відновлює paused. Navigate/check також переводять status у in_progress. Після зміни джерела збережений current_step може вказувати на тепер locked крок: на GET сервер його не нормалізує. Вихід у робочий простір не потребує завершення, але сам по собі не записує pause: [frontend/boss_app_source.html](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/frontend/boss_app_source.html:5752), [training/service.py](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/service.py:202), [training/service.py](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/training/service.py:242).

Зміна role/fixture/installation змінює identity або закриває доступ. Зміна актуальних permissions/observed/expected знімає валідність stamp. Окрема lesson version і повний source PK context у stamp відсутні; зміна лише тексту/правила чи заміна сутностей зі збіжними observed значеннями не має гарантованого окремого invalidation. Повернення до попередньої ролі з тим самим актуальним access_revision може відновити валідність старого stamp; історію epochs відкликання код не зберігає.

Training check не виконує господарську команду. У case02 вже правильна shipment може задовольнити allocation. CRM draft/preview повертає existing handoff. Повтор того самого proposal може повернути квитанцію, а новий proposal не є replay попереднього. Квитанції є в ActionProposal; task proposal-status GET може прочитати власний дозволений результат після повторного входу та повідомляє same_session. Навчальний прогрес не зберігає proposal UUID/receipt link: [tasks/history.py](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/tasks/history.py:49), [operations/models.py](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/operations/models.py:50), [crm/commands.py](D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo/crm/commands.py:370).

Q01 збережено як CTA → серверна чернетка → preview → явне підтвердження → receipt/існуюча передача. Q02 зберігає доручення з відповідальним і строком до CRM у case03; не створено вигаданого кроку після CRM. Source-код відображає цей порядок навчальних кроків, але CRM admission не перевіряє попередній progress (GC-F08). Q03 зберігає відмінність public session UUID, case_id, source PK і synthetic B3/slug; live identity лишається NOT_RUN.

## Точні входи

| Файл | SHA-256 |
| --- | --- |
| [GUIDED_CONTRACT_ADMISSION.json](D:/3/BOSDev/evidence/plan-acceleration-20260930/GUIDED_CONTRACT_ADMISSION.json) | `d6fdc105b4201dda43f773518e14fcb71e2f352431b9bea70c037fe3485d9ceb` |
| [GUIDED_LEARNING_CONTRACT_UA.json](D:/3/BOSDev/evidence/product-enablement-20260930/GUIDED_LEARNING_CONTRACT_UA.json) | `631074d8894c8fd40650947350167b99724d435aa1f0e00ab4a4ea95e07976cc` |
| [CONTRACT_DEPENDENCY_R4_UA.json](D:/3/BOSDev/departments/product-enablement/CONTRACT_DEPENDENCY_R4_UA.json) | `87a834a7a4bb7b29525a32fc56cb2084215f8f54d8a82557717a1a5f338eaa93` |
| [ENABLEMENT_CONTRACT_DELTA_REVIEW.json](D:/3/BOSDev/evidence/change-intake-20260930/ENABLEMENT_CONTRACT_DELTA_REVIEW.json) | `6180fe7cd27a9b6aac6a913e3f8dfe8eea7dbaa64daa676fce8bd53d8b65c208` |
| [IDENTITY_MAP.json](D:/3/BOSDev/evidence/resume-solutions-20260930/main/writer/IDENTITY_MAP.json) | `91237e09cce96aa8927470455b0f50995caa5a72f4a0c77fcc44199adbf49a00` |
| [ACCELERATION_UA.md](D:/3/BOSDev/evidence/plan-acceleration-20260930/ACCELERATION_UA.md) | `30a86d4be9d191db89b1afa86c2f972452fc16987ac45507821cac451709f3b1` |
| [JOURNEY_SOURCE_ADMISSION.json](D:/3/BOSDev/evidence/resume-solutions-20260930/integrator/JOURNEY_SOURCE_ADMISSION.json) | `7106925d62789fa15063890f73c17294ddb332e175808a616ad5b90712d54a4e` |
| [JOURNEY_SOURCE_CONTEXT_RECEIPT.json](D:/3/BOSDev/evidence/resume-solutions-20260930/main/JOURNEY_SOURCE_CONTEXT_RECEIPT.json) | `513e3261e1fac391f0ace12d761fd035960505904a8ce35c11a8acff3db539a4` |

24 точні source hashes записані в `SESSION_CAPABILITIES.json.source_files`; кожне з 293 evidence references також має свій file SHA. Це усуває підміну source версією canonical або новішим UI patch.

## Статична перевірка і передача

Фактичні команди та exit codes наведені в `static_checks`. Admission/reference hashing, HEAD read, source reads і hash checks завершилися exit 0. Один початковий пошук неіснуючого `operations/auth.py` повернув exit 1; використано фактичні `boss_project/identity.py` і `boss_project/auth_views.py`. Вузький literal-пошук відсутніх proposed полів повернув exit 1 (немає збігів); це не repository-wide доказ відсутності, висновки спираються також на прочитані model/service/registry.

Точний PowerShell script у SC10 розібрав JSON, зіставив arrays з pinned proposal, перевірив statuses, source SHA, межі line refs, allowlist та false readiness. Exit 0; raw result:

```json
{"lesson_fields":12,"step_fields":12,"session_requirements":5,"source_hashes":24,"evidence_refs":293,"gaps":8,"status":"AUTHOR_COMPLETE_UNREVIEWED","executions":0,"QA":"NOT_RUN"}
```

Історичний SHA-256 frozen writer-r1 SESSION_CAPABILITIES.json: `4902e0bf6d508848dbe62c5a3c907f68a2ca4293ad3717b69e0de029a4ee5e02`. Поточний R2 hash наведено у секції корекції вище; self-reference не створюється.

Наступний отримувач — main: передати точну таблицю enablement одним змістовним handoff; quality лише після root admission і exact manifest. Автор не запускає review, не координує інші чати і не призначає собі нових задач.

Продуктові executions=0, QA/app/runtime/browser/DB/CI NOT_RUN. Contract accepted=false; guided implementation=false; guided integration implemented=false; TECHNICAL_READY=false; PILOT_ALLOWED=false; MVP=false. Всі історичні caps збережені. Цей документ не є дозволом змінити schema/API/права або виконати новий запуск.
