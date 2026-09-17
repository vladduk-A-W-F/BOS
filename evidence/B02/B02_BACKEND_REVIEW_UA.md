# B02 — незалежний завершений review замороженого backend кандидата

12.09.2026. Висновок: **блокувальних зауважень у перевірених межах frozen B02 backend не залишилося; кандидат погоджено для інтеграції та обов’язкового canonical full verify.** Це не приймання всього B02, інтерфейсу або готовності BoS MVP.

Переглядач читав контракт, код та фактичні журнали, звірив SHA; не змінював checkout, не відкривав оригінальні DB/media, не повторював full suite, сервери чи A09 boundary. Окремий ранній Decimal probe виконував лише точний AST чистої функції без Django/SQL/HTTP. Наведені нижче HTTP/SQLite докази виконані автором або root у власних синтетичних середовищах і прочитані незалежно.

## Заморожена ідентичність

- `tmp/b02_candidate/B02_BACKEND_FROZEN_MANIFEST.json`: SHA256 `22858caab2c387f6923f55764febe928d4c18f2c0901b447b5068935d9114499`.
- Незалежно звірено **28/28 source файлів та 28/28 evidence файлів**; розбіжностей немає. Усі 28 base SHA звірені з git HEAD перед інтеграцією, включно з відсутністю нових файлів. Patch і execution report відповідають manifest.
- Source aggregate, самостійно обчислений як SHA256 sorted compact JSON словника source_files: `e72abaf0eece045716a9df0d0edab0cf47bf093a877d128a9328b082d3dcc730`.
- Центральний `erp/importing.py`: `59989c9d873c8d9346dfe51dae991c3fb0cab8515f9c859e70dc670f6e9fe426`.
- Міграція `0004_initial_import_ledger.py`: `b90620e5499f28e53ec7e26f3b55cf037fb99353a6147c7da3dbd3e5175bbbc1`.
- Остаточний `final-frozen.log`: `9aa0251501297b6ab5a0ff4b63fb7a76db222946a73f24f83cc96a36a9004e87`; **45/45, 15.342 s**, включно зі старими 18 B01 і новими 27 B02 тестами. B01_SOURCE_ROLLBACK має `refused=true`, `changed=[]`.

## Прийняті межі поведінки

Спеціальний CEO-only імпорт має JSON або manifest+CSV → попередній розрахунок → чинний proposal/confirm → один атомарний batch/event/receipt. Профіль охоплює контрагентів, каталог buy, склади, початкові pending партії, повні невідвантажені SO та залишки історичних PO. Для PO первинні quantity/received/cutover/dates збережено в snapshot, нова quantity дорівнює залишку, received дорівнює нулю. Минулі складські рухи, рахунки або платежі не створюються.

Generic operations preview прямо відхиляє erp_import_batch. Звичайний purchase API не може створити історичний PO JSON-параметром: authority перевіряє точний виданий об’єкт, row hash, phase, connection та lifetime atomic block. Preview відкочується, confirm отримує новий apply context. Це захист API admission; довільний довірений Python усередині процесу не називається ізольованим середовищем.

ERP mutex береться перед бізнес-читаннями; Counterparty/Employee locks справді materialized у стабільному порядку до fingerprint, actor перевіряється повторно. Importer не викликає finance Transaction/Salary writers. Реальні SQLite contention tests підтверджують відсутність подвійного ефекту в перевірених сценаріях; висновок про PostgreSQL блокування не робиться.

Namespace/external ID і точний первинний source hash відділено від поточних бізнес-значень. Повторне підтвердження повертає первинний receipt. Новий UUID з тими самими identities не перепризначає first_batch і не створює повторних цілей. Законне подальше приймання не змінює історичні вихідні суми; current totals показуються окремо. Тотали обмежено цілями пакета та opening groups, це не баланс усієї компанії.

Документи для нових rows перевіряються за доступом, code/revision/checksum, approved/newest та фактичними verified_document_bytes. Imported PO успадковує B01 перевірку current і historical source visibility. Observer projection не повертає ціну, extras або комерційний source snapshot. Нові чотири import routes CEO-only; звичайного CRUD для ledger немає. PROTECT, identity uniqueness і one-target shape обмежують допустимий стан БД; незмінність історії означає командну/API межу, а не заборону довільного SQL адміністратора.

## Конкретні review findings і закриття

| Ризик | Фактичний доказ і мінімальна правка |
|---|---|
| Неправильні типи UUID/text та bool/float control counts | types-red: 5 failures; явні type guards і strict controls; review-green пройшов. |
| current_targets для нового UUID reuse/mixed | targets-red: 0 замість 9; цілі резолвляться з canonical source keys, first_batch не переписується; green перевіряє 9/11 targets. |
| Explicit bindings відсутні в mappings/reuse counts | bindings-red: 0 замість 1 → green 1/1. Показано реальні bind/reuse IDs; source counts/totals не збільшено bindings. |
| Непридатний reused reference для нових rows | ref-profile-red приймав HTTP200 замість422; тепер нові залежні rows повторно перевіряють warehouse/buy/active type. Green1/1; чистий історичний replay залишається доступним. |
| Receipt довіряв тільки вхідним сумам | verify_created перечитує фактичні ORM rows, source/FK/ціни/нульове received/SO/Movement. Справжній SQLite AFTER INSERT price+1 спричиняє відмову та rollback; late SQL abort теж відкочує весь пакет. |
| Multipart parsing до whole-body limit | Два мінімальні hooks у LocalDemoGuard/TrustedProxyMiddleware викликають bounded reader перед CSRF. Baseline hooks фактично дозволяли downstream parser; нові hooks відмовляють до нього. Missing/forged Content-Length представленого WSGI stream читає не більше 160KiB+1. CSRF не вимкнено, middleware order не змінено. |
| Decimal залежав від ambient context | Ранній pure-function probe виявив зміну1234567.89 при prec6. Авторський actual HTTP decimal-red отримав500; tuple-конструкція integer cents і localcontext50/HALF_EVEN на normalize/live_totals/prepare/confirm/apply дають green1/1. Перевірено точні source308641.95000/current308641.95 і незмінність зовнішнього prec6/ROUND_DOWN. Фінальні45/45 включають цей тест. |
| B01 reverse test стартував із вже нової B02 схеми | Збережений final-focused red44: тільки changed=['migrations'], бо спершу відкотилася порожня0004. Fixture перевіряє порожній ledger, реально переходить до0003, потім створює approved PO черезHTTP. Початкові state/assertions дослівно збережені, cleanup повертає latest. final-focused-2:44/44; final-frozen45/45. Жодного стирання populated snapshots. |

Whole-body proof стосується байтів, уже представлених застосунку WSGI. Він не відновлює відкинуті upstream bytes і не доводить поведінку raw HTTP framing або A09 proxy13MiB.

## Additive перевірки без послаблення старих критеріїв

Gate5 manifest зберігає буквально старі **84 methods / 89 records / 26 actions**, незалежно звірені з baseline, SHA `db06988865d19aff6aae73c1300c7127ff77df76a8c70a8ca3f5f1ab8c56f462`. Додано тільки 4 methods, 3 currency records та action import_batch. Фактичний `gate5-additive.json` complete=true, runner_failures=0; **88/88 methods,92 records**, log45.042s. Його manifest SHA `40d74910623f38d01f151fc7d9514a911d9bf90f05b6184175501bb4a6e2e0a9`. Цей прогін передує останнім вузьким Decimal/fixture правкам; інтегрований full verify має виконати остаточний код.

Access доповнено чотирма routes, старі patterns/oracles залишилися. Фактичний additive access test: **180 request combinations =4 routes×5 roles×9 methods**, green1/1,4.645s; resolver catalogue exact176. Це не підміна виконання всього canonical access gate. Серверний шаблон27 синтетичних rows має ненульові EUR/UAH/USD, фактичні JSON і manifest+CSV preview входять у focused набір.

Окремий populated B02 reverse guard стоїть останнім forward/першим backward та відмовляє за наявності ImportBatch АБО ImportIdentity. Реальний тест перевіряє весь SQLite schema SQL, migration recorder, domain rows і ledger до/після відмови. Інший тест виконує actual populated snapshot → typed export → нову мігровану DB → exact47 tables/sequences/media/references/logical schema, збереження receipt/canonical source/PO snapshot та source replay. preservation-2:2/2,2.307s; ці перевірки також включені у фінальні45.

## Окрема root restore/transfer сумісність

Усі три файли root compatibility manifest входять у ті самі перевірені28source:

- check_restore: `89ab46d9da7c300c791b72ed7842079969495c27773d32226851ca7b5fe2a655`.
- test_full_data_transfer: `6a3718317e893fffb010fa36faaf5e6822a13cb71deb573c6f08c7cfb428e0df`.
- table_inventory: `890b43d888eb575a59b5bf4de1a66f91e4d37e8c6d3ffb5d7a5bb23dccd4dd99`.

Fixed45 set буквально відповідає independently generated old45; новий47 містить рівно дві додані таблиці erp_importbatch/erp_importidentity. Старі10 native cases/assertions, два первісні documents/bytes та початкові три валютні seed amounts збережено. Додано третій approved DocRef та actual HTTPS import до capture.

Root native red на старому45 assertion збережений. Попередня версія checker фактично пройшла **12/12**, exact native restore/JSON export/receipt/source bytes; restore-green SHA `eaf8449e012e384a6cd7db2a4813353d5a6bc2d771978027643d1bad88e437dc`. Після цього додано GET ERP snapshot до/після restored replay і deep equality, label виправлено на no_new_business_effects. Цю останню assertion прийнято за кодом; у попередніх12/12 її ще не було. Вона має виконатися в canonical full22.

## Відкриті межі

Canonical full22 ще необхідний для приймання інтегрованого B02 та регресій A01–B01. Цей review не підтверджує браузерний UX, фактичну роботу клієнтських даних, PostgreSQL, Windows, CI, наскрізні gates6/9/10 або готовність MVP. Усі 11 gates зберігаються. Відомий A09 13MiB reset із непідтвердженим413 лишається відкритим без додаткових спроб; activation/upgrade/rollback також не приймаються. Нових blocking findings усередині погодженого та фактично перевіреного B02 backend scope немає.
