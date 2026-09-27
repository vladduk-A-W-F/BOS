# B30-ARCH-CONTRACT-20260927 · архітектурна звірка BoS 3.0

Дата зрізу: 27.09.2026, 14:42 UTC. Автор: bos_architect. Режим: читання джерел та зовнішня специфікація. Це не незалежне приймання всього UI або виконання QA.

Висновок: новий монітор зберігає наявний захищений контракт читання. Нового доведеного блокера продуктового коду в перевіреному стику не знайдено. Є один конкретний блокер майбутнього навчального QA-плану та одне уточнення фінансового терміна в документації дизайну. Змінювати архітектуру або реалізовувати сценарії заново не потрібно.

## Точні джерела

- Canonical: C:/Users/user/.codex/worktrees/bos-consolidation-plan/repo; branch codex/bos3-prerelease-20260927; HEAD 4a83f17679339a983f00e76c74e48a80ddcbda7f; git status --short порожній.
- Product: f55a15de4006d10c0d7c65f8a2ca8499fbb99819, dev.3. Delivered runtime той самий за чинними control/accepted delivery records; процес і HTTP цим оглядом не перевірялися.
- Design: C:/Users/user/.codex/worktrees/bos3-product-design/repo; HEAD 32acfb6ad3a0aeabe2f7501a28ba878dfeaeec87; незакомічений WIP. Висновки прив'язані до SHA-256 файлів, а не до заяви, що весь WIP входить у HEAD.
- QA: D:/3/BOSDev/qa-scratch/bos3-readiness-scope-20260927/; поточний текст revision 3. Canonical REVIEW_RU.md з п'ятьма findings описує першу підготовку. Під час огляду root додав незакомічений REVISION3_REVIEW_RU.md: ACCEPT_SCOPED_PREPARATION_ONLY, повний DoD PARTIAL; нове доручення тому самому QA — тільки фактичні три learning cases. S2 mapping прийнятий статично; executable plan не прийнято.
- SHA-256 та Git blobs перевірених джерел наведено в HANDOFF.json. Десять прочитаних продуктових backend-файлів байтами Git blob збігаються з exact f55.

## Контракт процесу й даних

| Межа | Наявний контракт | Джерело і сенс для UI / QA |
| --- | --- | --- |
| Компанія / користувач / роль | Django; окрема установка на компанію. Policy відбирає доступні записи. Навчальна установка окремо прив'язана до користувача, fixture та шляху БД. | AGENTS.md, розділ «Продукт»; erp/queries.py:83–95; training/access.py:18–48. Новий монітор не є shared-DB SaaS і не змінює права. |
| Публічний вхід → робочий монітор | Брошюра описує синтетичні історії; робочі цифри читає BoSHome через GET /api/erp/snapshot/. | Design contract:7–13; design frontend/boss_app_source.html:5141–5189,5644. Презентаційні числа не є поточними ERP-фактами. |
| Джерело → показник | Сервер формує role-filtered snapshot; для CEO додає фінансовий home, для інших — тільки доступні tasks. Монітор рахує замовлення/роботи/партії/доручення з цього read. | erp/views.py:16–19; design frontend:5203–5218. Показники стосуються доступних записів, а не доведено всіх філій/періодів іншого dashboard. |
| Час → придатність показника | Scope включає user/mode/role/access_revision/capabilities; stale/error не стають нулями; mismatch/denied очищає контекст. Час read — локальний годинник; as_of — бізнес-дата. | Design frontend:5067–5069,5147–5189,5130–5135. Монітор та огляд мають незалежні reads; атомарної єдиної миті між компонентами не обіцяти. |
| Факт → погоджена дія | Policy → preview → proposal → explicit confirm → перевірка user/role/session/expiry/source → mutex/CAS → transaction → receipt. | operations/service.py:99–126,129–160,173–192; erp/views.py:22–43; erp/service.py:188–193. Монітор сам не створює команд і не приймає receipt за доказ свіжості read. |
| Сума → обліковий зміст | Receivable — сума відкритих рахунків за валютою; collectible — receivable мінус retained; це різні значення. | erp/experience.py:62–74; erp/balances.py:62–65. Не змішувати валюти, борг, касовий залишок і дозволену суму платежу. |
| ERP результат → навчальний крок | answer підтверджує відповідь; operation підтверджує поточний факт джерела; CRM — існування пов'язаної картки з next_action. Перехід navigate не завершує крок. | training/service.py:98–112,129–144,158–176,260–287. Supply/quality/payment — не автоматично operational S1/S2/S3. |
| Крок → збережений прогрес | Identity=(user,role,installation,fixture ID/hash,case). Stamp включає observed/expected/access_revision/fixture; змінений факт повертає needs_recheck. | training/models.py:24–34; training/service.py:35–40,179–209. Reload/relogin oracle порівнює цю identity та stamp-семантику, а не лише зелений UI статус. |
| Навчання → CRM | Потрібний session-bound запис і next_action; файл/чернетка не є створеною CRM карткою. | training/service.py:70–77,167–176; crm/commands.py:90–106,270–294. Для observer operation замінюється навчальною answer і learning_mode=read_only. |
| S2 document → registration | Revision 3 коректно відокремлює S2 CEO document-match/preview/confirm, ActionProposal, SupplierInvoiceRegistration, Event та receipt. Реєстрація не означає оплату, AP/ledger або рух складу. | QA revision3:84–107,132–137; operations/service.py:116–122,158–160. Детальний S2 trace залишається відповідальністю призначеного незалежного reviewer; тут він не прийнятий повторно. |

Причинний ланцюг: бізнес-факт і документ → доступна роль та джерело → preview/explicit confirm → service/mutex/transaction → receipt і зміна джерела → нове захищене читання → перевірка відповідного навчального predicate → stamp прогресу. Показник, receipt та completed мають різні предмети доказу.

## Нові предметні findings

### ARCH-01 · P1 для майбутнього training QA, не для runtime

**Факт.** Revision 3 пропонує SQLite з ім'ям b30_12_<run-id>.sqlite3 або PostgreSQL (B30_12_QA_SCOPE_RU.md:114–115), а серед evidence очікує completed-step reload/relogin (126–128). У exact f55 training/access.py:21–29 відхиляє будь-який vendor, крім sqlite, та назву БД без bos3-fasteners. Рядки 31–48 додатково вимагають чинні fixture/manifest hash, installation ID, owner і database_identity_sha256.

**Найсвіжіше уточнення root.** Новий docs/orchestration/bos3/evidence/readiness-scope-20260927/REVISION3_REVIEW_RU.md:11 пропонує learning-only SQLite root b30-12-learning-f55-r1/ з db.sqlite3. Це усуває невизначеність engine, але db.sqlite3 прямо заборонена training/access.py:29 і не містить bos3-fasteners. ARCH-01 тому залишається чинним для нового exact handoff. Потрібно виправити тільки запропоноване ім'я та узгодити marker/identity контракт, не послаблювати guard.

**Наслідок.** З описаного загального середовища не можна отримати штатну навчальну session/progress evidence. Operational S2 може мати окремий environment; він не доводить придатність для training. Це точна несумісність поточної пропозиції з guard, а не твердження, що вже запущений runtime несправний. JSON future_environment також лишається OWNER_DECISION_REQUIRED, тому виконання ще не дозволене.

**Власник / мінімальний крок.** Наявний QA, thread 01a0c05d-6eeb-79f1-a135-be66985b442f: у тих самих draft артефактах розділити operational environment та навчальний progress environment. Для training вказати сумісну isolated SQLite назву з bos3-fasteners та всі marker/identity умови точного training/access.py; для PG позначити, що training evidence на f55 не підтримується. Це специфікація без створення БД, fixture/setup або зміни guard.

**Незалежна перевірка.** start_overview_review звіряє MD/JSON з training/access.py:18–48 і training/service.py:35–40; встановлює, який саме run доводить learning progress; кожен planned run має NEW/SAME-PROBLEM і ліміт. Поки не визначено точний сумісний source/fixture/environment та допустимість виконання, progress oracle лишається BLOCKED. Не потрібен новий запуск, щоб перевірити цю правку документа.

### ARCH-02 · P2, термін у design contract

**Факт.** BROCHURE_MONITOR_20260927_RU.md:11 називає фінансову картку «доступный финансовый остаток». Реальний WIP frontend:5217 правильно підписує financial.receivable як «Очікуємо від клієнтів». Сервер erp/experience.py:71 сумує invoice.open; erp/balances.py:62–65 відокремлює receivable від collectible=receivable-retained.

**Наслідок.** Документ може породити неправильний QA oracle: receivable не є готівкою/банківським залишком і не є сумою, яку зараз можна провести як оплату з урахуванням утримань. Помилки actual UI числового поля цим оглядом не встановлено.

**Власник / мінімальний крок.** Чинний design owner у своєму immutable handoff уточнює лише контракт: «дебіторська заборгованість / очікуємо від клієнтів, окремо за валютою, з доступних рахунків». Не міняти формулу чи продуктове поле для відповідності нечіткому тексту.

**Незалежна перевірка.** Вже призначений reviewer порівнює одну фразу з frontend:5217 і erp/experience.py:71. Нові build/browser/QA спроби для цієї документальної правки не потрібні.

## Межі існуючого і недоведеного

- Наявне й прочитане: захищені snapshot та command/service шляхи, serialized write_lock, role/installation-bound training identity, recheck при зміні факту. Це статичний висновок з exact source, не нова динамічна гарантія.
- Підтверджений contract: незалежність monitor read від робочого огляду, явний read timestamp/as_of, synthetic-only та відсутність нового writer у моніторі.
- Proposal: QA revision3, його environment/exception та ширший S1/S2/S3 trace. Частина mapping уже конкретизована; не повторювати всі п'ять старих findings як поточний стан.
- NOT_PROVEN: навчальний completed-step reload/relogin/resume на кінцевому candidate; повні operational S1/S2/S3; accepted immutable design commit/QA handoff; повна готовність продукту. Власні заяви design contract про run3/8 screenshots тут не перевірялися повторно.
- Observer completed означає навчальну відповідь в read_only. Payment followup з відповідальним/строком не погашає борг. Посилання на екран, ACK, diagram, proposal або експорт не підтверджує виконану бізнес-дію.

## Передача та перевірка цієї роботи

Передати цей packet тільки єдиному інтегратору 01a0dd56-ca2d-79c0-b159-bde80074a026 через root. До вже призначених QA/design повернути два адресні уточнення без створення дубльованих задач. Після виправлення reviewer перевіряє нові exact hashes; root інтегрує лише прийнятий immutable handoff. Цей packet не є самоприйманням виправлень.

Фінальний git status показав зміни root у ACTIVE_WORK_PLAN_RU.md, CONTROL_STATE.json, TEAM_CURRENT_RU.md і нові revision3 evidence; HEAD лишився 4a83f17. Початкова чистота вище стосується першого читання. Ці паралельні зміни не належать архітектору й не скасовувалися.

Прочитано чинні AGENTS.md, PROJECT_CONTROL_RU.md, CONTROL_STATE.json, ACTIVE_WORK_PLAN_RU.md, review першого QA draft, поточний revision3 та вузькі source стики. Git metadata/hash команди завершилися exit 0. Два пошуки за непідтвердженими можливими шляхами (app/src та crm/service.py) дали missing-path exit 1/2; далі використані фактичні frontend/boss_app_source.html і crm/commands.py. Це навігаційні промахи, не продуктові тести й не спроби з QA ledger.

Застосунок, тести, browser/HTTP, CI/build, DB/media, setup/reset/seed/migrate не запускалися. Змінені тільки ARCHITECTURE_REVIEW_RU.md та HANDOFF.json у наданому зовнішньому allowlist. Product/canonical/design/runtime не змінено; коміту немає, бо це зовнішній review packet. P05/A09/A10/A11 та вичерпані ліміти збережено. TECHNICAL_READY=false, PILOT_ALLOWED=false, MVP=false.
