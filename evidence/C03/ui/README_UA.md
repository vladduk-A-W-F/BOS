# C03 UI · кандидат для незалежного review

Кандидат створено з canonical frontend `fd283ac01fd50fd2478a5902e492fbed5f16da943ac3731a01b4903a96dec801`. Власний каталог `tmp/c03_ui_candidate`; canonical, backend, БД, залежності, браузер, A09 та fullverify цим підетапом не змінювалися й не запускалися.

## Реалізована межа

- Банк зберігає місце у навігації. Дві вкладки: «Журнал» / «Виписки», явна валюта та період. Підсумки та місячні значення читаються з server summary; Number застосований лише для геометрії стовпчиків, не сумування грошей чи payload. Ручна транзакція надсилає точну decimal string і вибрану currency; старий finance create-intent helper збережено побайтово.
- Приватний CSV: окремий шаблон, upload рівно file/code/revision/title, SHA первісних bytes у пам’яті, логічні row/column errors у діалозі, ручна review точного checksum. Unknown upload не запускається знову автоматично; пошук exact code/revision через існуючі documents/versions і порівняння SHA. Збережений файл ще не імпорт і не гроші.
- Імпорт: відома пара source/account або явно нові точні коди, preview counts/create/reuse та три окремі валютні source totals. Actual IDs відкриваються лише з committed receipt/read. Перша квитанція відокремлена від current summary.
- Рядки/імпорти та фактичні джерела пагіновані. Вибір existing Transaction, Invoice, payment Event, B02 ImportIdentity, Salary використовує точний candidates route; немає залежності від recent300. Вихідний cash і зарплатне джерело не розносяться на AR.
- Звірка: явні дві осі Transaction/payment. New payment створюється лише за обраним способом; existing payment тільки зв’язується. Кожне рознесення має UUID v4 та точну суму; невідомі/повторні JSON keys відхиляються. Нові результати/наявні рахунки/платіжні події відкриваються за actual ID; замовлення читається зі свіжого scoped snapshot.
- Pending queue зберігає тільки action/proposal_id/document_id або line_id/allocation_keys у поточній вкладці перед confirm. За окремим root addendum import також зберігає source_identity_sha256 = SHA-256(JSON.stringify([source_sha256, source_system, account_ref])): це відбиток очікуваного джерела, без raw account/source, сум або призначень у storage. Перед success звіряється цей digest; інший первісний Document допустимий за тотожної domain identity. Відсутній/некоректний digest не дозволяє success, видалення ID або automatic new intent. Немає truncation, access_revision не ховає ID. Закриття/unknown/403/404/generic409 не створюють новий намір. Повторний вхід для того самого рядка підхоплює unresolved pending. Після actual receipt прибирається тільки відповідний proposal ID.
- У вкладці помічника додано рівно дві C03 дії через окрему schema/form; жодного LLM або нового банківського writer. ERP/B02/B03/C01 дії не змінені.

## Докази

`BASELINE_RED.json`: 3 конкретні початкові red — змішані EUR/USD/UAH під однією валютою, manual create без currency, хибний «Баланс місяця». Виконані фактичні початкові Bank closures з контрольованими даними.

`UI_PROOF.json`: 37/37 actual extracted candidate JS/React-closure перевірок. Decimal точність/максимум; strict nested JSON; історичний payment; ID-only pending до POST; lost reply/409/403/404/storage quota/revision/reopen/no-change; late read після закриття; вибрана валюта/manual create; private source unknown/exact multipart/SHA recovery/no duplicate upload; actual Assistant дві дії/CEO gate.

`PROTECTED_BUILD_PROOF.json`: 189 початкових top-level source declarations побайтово збережені; винятки рівно Bank і дозволений sibling branch OperationsAssistant. Generated Babel helpers не маскуються під початковий source. Поточний assets/app.js точно збігається з повторним in-memory Babel transform.

Це code/source/build докази з контрольованим transport/state. Вони **не є** actual HTTP, browser, keyboard, mobile/zoom або повним UI acceptance. Gate10 лишається відкритим через раніше зафіксовану недоступність дозволеного браузерного маршруту. Backend wire/read/runtime ще має пройти незалежну перевірку та freeze автора; canonical C03 не інтегрується до завершення C01.

## Передача

Лише три release files: frontend/boss_app_source.html, frontend/boss_app_html.html, assets/app.js. SHA/bytes у UI_CANDIDATE_MANIFEST.json. Інші JSX/CSS fragments та compose.py — відтворюваний спосіб складання candidate; C03_UI.patch — тільки diff source проти точної base. assets/babel.js та build script скопійовані без змін, не є release delta. Checkpoint1 збережено для trace незалежного review.

## Закриті незалежні findings

`REVIEW_RED.json` → `REVIEW_GREEN.json`: 4 виправлені помилки й 1 збережений counterproof. Actual App bank route вже повертає старий BoSReadOnlyRecords для manager до Bank; права не розширено. Non-JSON403/404 тепер очищає source до JSON parsing. Preview звіряє нормалізований повний payload і точну identity effect/allocations. Upload201 мусить збігатися з локальним SHA та буквальними code/revision.

`IDENTITY_RED.json` → `IDENTITY_GREEN.json`: 9/9 named checks, з них 6 red на первісному f5fa freeze та 3 preservation. Digest записаний до POST; foreign-domain receipt відхиляється без втрати pending; законний samebytes/інший перший Document приймається; pending recovery використовує той самий proposal; missing/invalid digest блокує новий confirm і лишає ID. No-change preview теж перевіряє source identity. `IDENTITY_INTERMEDIATE_RED.json` зафіксував no-change omission і non-JSON201 regression під час правки; обидва закрито.

Підсумок поточної вузької перевірки: 37 основних + 5 review + 9 identity = 51/51 green. 189 protected declarations та exact Babel повторно підтверджено. Root/a09 виконують незалежний final review; нових optional probes не додано.
