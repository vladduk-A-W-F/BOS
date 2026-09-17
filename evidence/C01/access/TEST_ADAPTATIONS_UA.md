# C01: обґрунтування адаптації перевірок доступу

Підготовлено незалежним агентом c03_statement_plan. Змінено лише три access scripts у власній копії `tmp/c01_access_candidate/source`. Автор backend надав стабільний checkpoint; його файли скопійовано без редагування. Canonical HEAD на момент передачі: `b375d4f316e44d694e376f5ad0bb0fff9b4e7eba`. Canonical, робоча БД, приватні завантаження та вихідні історичні записи цим підетапом не змінювалися.

## Які старі очікування змінено й чому

| Поверхня | Попереднє очікування | C01 та позитивна альтернатива |
|---|---|---|
| Task list POST, detail PUT/PATCH/DELETE для CEO/manager; усі `.json` варіанти | Прямий CRUD змінює запис | 403 із `code=approval_required`, повний business digest незмінний. Справжні preview→confirm create/update/done/archive/restore виконуються й перевіряються окремо. |
| Нативний Task admin add/change/delete/bulk POST | Модельний admin міг записувати Task | Погоджений shared writer вимагає перегляду/погодження; admin читає рядок, але повні валідні форми не змінюють Task або історію. Видалення не замасковано невалідною формою. Архівування та відновлення функціонують через proposal. |
| Непідтримувані list PUT/PATCH/DELETE і detail POST | 403/405, без змін | Старий 403/405 збережено. Початковий новий body oracle помилково вимагав approval_required також для неоголошених методів; обмежено саме чотирма оголошеними CRUD writer-комбінаціями. Усі24 фактичні405 адресно перевірено повторно. |
| Task DTO | Старі поля | Старі поля збережені, додаються9 явних C01 полів; legacy FK/result залишаються NULL. Новий факт не вигадується. |

Усі **177** старих route records і **57** обов’язкових field test IDs побайтно за структурою збережені в manifest. Додано рівно3 визначення: task history, його DRF format route, task proposal status UUID. Recovery `.json` не додано — такого маршруту контракт не передбачає. Повний actual resolver має рівно180 визначень, їх множини/кратності зіставлено з явним manifest. Жоден маршрут не видаляється через dynamic discovery.

## Реальні синтетичні дані та canaries

Нові5 Task створені через actual preview/confirm; завершення містить реальний FK відповідального й явний результат, архів і relink теж виконані через погодження. Окремий synthetic legacy AuditEvent має нерозмічений payload, який не повинен віддаватися як структурований diff. Після relink додано101 явно синтетичний сторонній audit record: попереднє закрите джерело має залишатися захищеним незалежно від глобального ліміту100.

12 явних груп перевіряють:

1. Structured history для CEO/manager/observer та всіх трьох адрес; справжній actor/result; legacy payload не витікає.
2. Поточне закрите джерело і раніше закрите джерело після relink: detail/history404, active/archive/summary/home не розкривають canaries; CEO отримує власний дозволений історичний факт.
3. Архів зберігає поля/результат/FK/історію; default list/home виключають його; restore повертає його та додає рівно1 до total/done KPI, без зміни active/process/overdue. No-op не додає Proposal/Audit/Task.
4. Функціональна альтернатива raw CRUD: create→done→archive; raw hard delete403 зберігає рядок; пізній replay початкового proposal віддає первинний receipt.
5. Owner outcome200, чужий користувач включно з іншим manager —404.
6. Змінена роль власника —403, receipt не витікає.
7. Нова сесія того самого manager читає receipt з same_session=false; не може повторно execute старий proposal.
8. Pending/expired outcome GET не виконує дію; expired confirm409, receipt залишається NULL.
9. B02 import proposal не читається через Task recovery.
10. Пагінація Task history не повторює events; cursor прив’язаний до користувача/Task; неправильний cursor або limit400.
11. Втрата document capability приховує Task history, списки з джерелами та outcome.
12. Технічний admin реально читає Task, але валідні add/change/delete/bulk POST не змінюють business digest.

## Докази й виправлений дефект

| Запуск | Фактичний результат |
|---|---|
| `RED_FOCUSED.json`, старий B03 backend | 0/7; очікувані7 відмов, включно з raw201, відсутніми полями/маршрутами та невідомим order_id |
| `GREEN_FOCUSED.json`, перший C01 checkpoint | 6/7; history.json500 |
| `SURFACES_FIRST.json` | Фіксовані13 Task-related definitions,16 URL,5 ролей,9 методів плюс no_documents history;730/774 surface cases;9/12 control groups |
| `SURFACES_PATCH1.json` | Повторено рівно44 попередні невдалі case keys;44/44.12/12 control groups,100 HTTP |
| `GREEN_FOCUSED_FIXED.json` | Ті самі7 focused груп:7/7 |
| `CONTROLS_FINAL.json` | 12/12 groups,104 HTTP; додано фактичні home/KPI assertions до archive/restore |

Backend blocker відтворено реально: `TaskViewSet.history(self,request,pk=None)` не приймав DRF `format`; `.json` GET/HEAD500. Автор a08 виправив `format=None`; його SHA записано у `BACKEND_CHECKPOINT_PATCH1.json`. 20 помилок формату й24 уточнення unsupported-method oracle повністю закриті адресним повтором. `RESULT_LEDGER.json` машинно підтверджує, що повторені ключі дорівнюють усім44 первинно невдалим ключам. Це комбінований результат початкового прогону та адресного повтору; новий повний774 run не заявляється.

Сфера доказу — реальні in-process Django HTTP requests, авторизовані Django Client сесії, ізольована нова owned SQLite та media у scratch; транзакційний rollback між cases. Жодних моків writer/permission/history. Зазначені HTTP counts охоплюють самі перевірки, не підготовчі login/fixture requests. 57 field tests збережено, але тут вони не запускались. Повний gate, full verify, PostgreSQL, browser, A09 та gate6 не запускались і не прийняті цим звітом.

## Файли для інтеграції

- `scripts/access_fixtures.py` — SHA256 `6d787e06862fba2149b946a7950b95f02b0877b82cb30ad6c73cd16b6e62b323`
- `scripts/access_routes.json` — SHA256 `182639ea19916ca2c8f4a7c51b1b936e6bcf19d7148f5328b1166d5ca73d8597`
- `scripts/check_access.py` — SHA256 `0e0f4b6ebd2b2af77d750d466eeb5bc83bce682c5ff0cb3a2688862159ee5694`

Після інтеграції root виконує власний загальний gate. Нові `run_c01_controls` включено в main як додаткові явні перевірки; вони не підміняють попередні маршрути або57 field IDs.
