# C03 · незалежний огляд трьох access-адаптерів

**Рішення: погоджено в заявленій межі source/evidence review. Блокувальних прогалин у трьох access-файлах не знайдено.** Це не новий запуск HTTP або загальна готовність C03/MVP.

Перевірено frozen `tmp/c03_access_candidate/FINAL_ACCESS_MANIFEST.json`, SHA-256 `23c9bbdc8cb01835d2bc20327034e4be41ac7542b9ad2ea3c11b2339622c649e`. Огляд read-only: без запуску Django, API, тестів, браузера, міграцій/fullverify; без відкриття БД, private backup/media та без змін canonical або кандидатів. Новий файл — лише цей звіт.

## Цілісність і збереження попередніх вимог

| Артефакт | Фактичний SHA-256 |
|---|---|
| scripts/access_fixtures.py | 85dc7ae5fbe0d1cb51b061fc90ecfd54369500ad74ae32ddf843d1c43429ecb8 |
| scripts/access_routes.json | 23c70fc3b70f638d54ce2d43082c285c2b37a7be3020c42e9ab7cab3c68ab1be |
| scripts/check_access.py | 3170d8e0516466f7640152c92a774490556dddc5315d6e5146607afc91eac467 |

Усі три збігаються з маніфестом. Усі **21** наведені в його evidence-map файли перевірено за bytes/SHA: невідповідностей немає. Шість source-hash посилань у AFFECTED_CHECKPOINT2_GREEN.json збігаються з поточною похідною копією — три адаптери, operations/service.py, finance/statements.py і finance/statement_reads.py.

Незалежно порівняно сирі JSON-літерали, а не лише множини назв: перші **180 route objects** і всі **57 required_field_tests** тотожні C01_BASELINE_ROUTES.json. Додано рівно 10 визначень: 8 Django statement routes та 2 DRF transaction-summary definitions. Їх materialization дає 11 URL, оскільки suffix route охоплює .json і .json/. Нових ledger admin routes немає.

Canonical три access-файли під час читання ще збігалися з SHA C01 у BASELINE.json; вони використані лише як read-only порівняльна база. `run_c01_controls` з усіма 12 ID тотожний до символу, SHA `cc48fe13b8f845642b0935ee755d63c3695a17482bbfae4d7f6e7884964cec5d`. `state_digest` і старий `admin_payload` також побайтово незмінні. Доданий runner не заміняє старий виклик C01/57, а виконує новий окремий run_c03_controls із фіксованим кортежем 12 ID та assert проти скорочення.

## Реальні джерела fixture та 12 контролів

Fixture справді викликає Django HTTP client для private upload → exact-checksum review → ERP import preview → confirm → чотири reconcile preview/confirm. StatementImport/Line/Allocation або їх receipts не створюються прямим ORM для імітації успіху. Рядки EUR17.39/USD123.45/UAH9801.07 зв’язуються з фактичними synthetic Invoice; четвертий outgoing salary line використовує вже наявну виплачену Salary та її Transaction, без нового cash/payment. ProcurementRequest ORM і навмисні зміни legacy document labels/sections є явно названими негативними canary fixture, а не підтвердженими бізнес-операціями. Task create/done проходять власний controlled HTTP шлях.

Нові контролі покривають: первісні bytes/SHA/receipt; незмінну приватність marker; історичне джерело та version lineage; Task/history/chat/context/export; повне приховування statement-linked Transaction/Salary; export/download permission і відмову не-CEO preview/confirm; source-bound Transaction REST/admin; archive/restore без зменшення сум; exact replay; окремі Decimal валютні шари; filters/cursors; admission malformed CSV та code reuse. Позитивні anchors не дозволяють прийняти порожній 200 як правильне читання.

## Три спеціально перевірені місця

**Native admin.** Остаточний protected_transaction бере реальний зареєстрований ModelAdmin/get_form для source-bound Transaction, збирає всі його поля і підтверджує валідність незміненої форми. Лише потім змінює description і відправляє справжній HTTP POST technical_admin на `/admin/finance/transaction/<id>/change/`. Вимагає помилку незмінності та повністю незмінний business state_digest. Так контроль доходить до HTTP admin boundary; попередній позитивний helper більше не перехоплює навмисно заборонене редагування ще до POST. Старий helper не ослаблено.

**Replay.** `records()` бере всі rows/fields усіх business_models через `_base_manager`, включно з Configuration, Transaction, Event/payment, ActionProposal/receipt, Line, Allocation і Audit. Expected snapshot змінюється тільки в єдиному Configuration key=erp_write, у value з рівно одним ключем revision: **точно +1 на кожний confirm**. Після кожного з п’яти literal-equal replay responses вся свіжа карта має дорівнювати expected; інших винятків або вилучення фінансових таблиць немає. Два no-change preview додатково вимагають незмінного загального state_digest. Це доказ про business rows, а не заявлена перевірка всіх SQL sequences, файлів чи browser state.

**Export.** Остаточний oracle перевіряє точний порядок **19 колонок**, кількість **4 рядки**, унікальність external_id і повну рівність кожного CSV row незалежно очікуваним даним: оригінальні 8 полів, import/line/document/SHA, first-source refs, фактичний Transaction ID, reconciled або cash_recorded, allocated/unallocated. Ledger IDs походять із fixture receipts. Старий 8-column export справді залишений у EXPORT_EXACT_RED.json; новий 19-column export проходить цей самий остаточний oracle. Заміна старого generic anchor account/source текстів на погоджені exact refs не приховує початковий red. Цей fixture перевіряє конкретний 4-row експорт; він не підміняє загальну перевірку всіх formula-prefix варіантів.

## Ланцюжок доказів та його точна межа

| Етап | Записаний результат | Інтерпретація |
|---|---|---|
| RED_FOCUSED | 1/8 green, 7 red; 7 HTTP | Реальні відсутні C03 поверхні на C01 base |
| GREEN_FOCUSED_CORE_ONLY | 8/8; 34 HTTP | Checkpoint1 core з початковими adapters, явно окремий від нового suite |
| SURFACES_FIRST | 503/504; 10/12 controls, 127 control HTTP | 10 нових definitions, 11 URL × 5 ролей × 9 methods + 9 no-export |
| REPLAY_DIAGNOSTIC | 5 exact receipts; тільки mutex +1; 2 preview без delta | Підстава вузького replay oracle |
| CONTROLS_TWO_FIXED | 2/2; 11 HTTP | Виправлені власні admin/replay runner assumptions на checkpoint1 |
| EXPORT_EXACT_RED | 1 конкретний export red | Остаточний 19-column oracle проти старих 8 колонок |
| AFFECTED_CHECKPOINT2_GREEN | 2/2 controls, 11 HTTP; export 1/1 | Тільки три раніше невдалі випадки на checkpoint2 |

Три initial failures ідентифіковані, а не приховані: export source anchors/wire, positive-admin helper до HTTP, надто широкий zero-state replay expectation. Десять незачеплених nested control bodies окремо порівняно із source_before_core_1 — буквально ті самі. Fixture між першим і фінальним adapters змінено лише додаванням точних export positive anchors.

Отже послідовність закриває всі зафіксовані failures цього bounded access scope. **Немає доказу нового повного 504/504 прогону на checkpoint2**, і цей огляд його не заявляє. Усі 180 старих маршрутів, 57 field suite та C0112 збережені, але не повторно виконані цим вузьким запуском. Загальний інтегрований full gate, native/restore та browser gate залишаються відповідальністю root за окремими доказами.

Погоджено передавання рівно трьох frozen access-файлів до фінального backend/integration package. Жодних додаткових optional tests або policy changes для закриття цього source-review не потрібно.
