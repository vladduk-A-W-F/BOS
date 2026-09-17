# B02 · Контракт першої реалізації

12.09.2026. Консолідовано `tmp/B02_READY_PLAN_UA.md` і всі погоджені R1–R7 із `tmp/B02_PLAN_REVIEW_UA.md`. Це специфікація наступного tmp-кандидата, не виконання B02. B01 source/БД/медіа не змінювалися; для цієї консолідації тести не запускалися.

## 1. Межа й wire types

Профіль: каталог buy, supplier/customer, warehouse, початкові партії pending, повністю невиконані продажі, **залишок історичного supplier PO**, включно з простроченим і частково отриманим до зрізу. Жодного upsert існуючої історії, історичних Movement/payment, production/BOM, нових файлів документів, банківських операцій або restore БД.

Усі об’єкти нижче закриті: невідомі/повторні ключі відхиляються. JSON numbers заборонено для кількостей і грошей. Типи:

- `UUID`: canonical lowercase UUID4. `namespace`: `[a-z][a-z0-9_-]{0,47}`, зберігається для всіх повторних імпортів цього джерела в цій компанії; нове джерело обирається явно. В одному deployment працює одна company DB; namespace не дає доступу до іншої DB.
- `ID`: integer >0, не bool. `ExternalID`: 1–120 Unicode символів без NUL/surrogate, без початкового/кінцевого whitespace; case-sensitive, без trim/casefold/іменного matching. `Ref` — ExternalID у цьому namespace, тип визначає назва поля. `bos_code`: 1–60, явний унікальний код BoS, без обрізання; source_order_code/source_line_id — 1–200.
- `Q`: невід’ємний десятковий рядок без exponent/grouping/comma, після перевірки значення з точністю ≤0.001 canonical `0.000`; позитивність за полем. `M`: аналогічно ≤0.01, canonical `0.00`. Чинні `number`/місткість model fields лишаються нижніми межами допуску, не розширюються.
- `Date`: строгий `YYYY-MM-DD`. `Currency`: EUR/UAH/USD. Ніякого FX/податків; `tax_basis` тільки excluding_VAT. `Text(n)`: буквальний Unicode довжиною ≤n, не executable інструкція.
- `DocRef`: `{document_id:ID,code:Text(80),revision:Text(40),checksum:64hex}`. Доступність, фактичні bytes/status і потрібна версія перевіряються сервером для нових записів. Документ спочатку завантажується/перевіряється чинним A08.

Input decimal1.0 і1.000 дають однакове Q1.000; надлишкова *ненульова* точність відхиляється, не округлюється. Значущі тексти незмінні. Explicit defaults канонічні. Rows сортуються за entity/external_id, sales lines — за external_id; порядок CSV/JSON не входить у identity.

## 2. Запит і CSV envelope

`POST /api/erp/import/preview/` приймає `application/json` або `multipart/form-data`. Authentication+CSRF до даних. CEO-only, без довіри до role з body. Власний малий ліміт цього adapter: **100 рядків, 128 KiB decoded manifest+files, 160 KiB whole request**. Кожна sales_line рахується рядком; bindings теж у ліміті100. Загальний `operations.views.body()` 30000 байтів не змінюється. Streaming bounded read і сумарний ліміт застосовуються до парсингу; відсутній/підроблений Content-Length не знімає обмеження. Узгодження відправляє тільки короткий proposal ID.

JSON envelope має рівно:

```json
{
  "format": "bos.initial-import.v1",
  "batch_id": "8b7a87f5-c759-46cc-90f6-7f407710915a",
  "namespace": "synthetic-starter",
  "cutover": "2026-09-12",
  "tax_basis": "excluding_VAT",
  "bindings": [],
  "rows": [],
  "expected_source_control_totals": {
    "counts": {"counterparty":0,"item":0,"location":0,"opening_lot":0,"sales_order":0,"sales_line":0,"purchase_open_balance":0},
    "money": [],
    "stock": []
  }
}
```

Це shape, порожній пакет не проходить apply. `money` завжди містить три валютні об’єкти з усіма ключами з §4, включно з нулями. `cutover` не пізніше server as_of; джерело з майбутнього відхиляється. Повтор за старим cutover допускається, не змінює поточний dataset date.

`bindings`: масив `{entity:"counterparty"|"item"|"location",external_id:ExternalID,target_id:ID}` для **явно вибраних наявних** записів. Нове зв’язування теж зберігається атомарно; вже відомий Ref можна використати без повторного binding. Ніякого автоматичного злиття за назвою/ЄДРПОУ/сумою. Employee вибирається за ім’ям у UI, wire передає owner_id. Довільні model/table labels заборонено.

CSV: multipart містить part `manifest` (JSON envelope без rows, натомість `csv_files`) та по одному part на entity. `csv_files=[{entity:"item",part:"rows_item"},…]`; part суворо `rows_`+known entity. Duplicate/невідомі/зайві parts заборонено; filenames не є шляхами. `bindings` лишаються в manifest. UTF-8, optional BOM, comma delimiter, quoted CSV, LF/CRLF; жодного sniffing/ZIP. Обов’язкові header — external_id і всі required поля рядка; дозволені лише його optional поля. Складні `documents`/`source_documents` — strict JSON у quoted cell; пусте optional cell означає заданий default. Жодних money floats. Source byte SHA зберігається окремо по parts; CSV presentation escaping не змінює canonical JSON.

## 3. Рядки: required; optional(default)

Кожний JSON row містить `entity`, `external_id` і такі поля. У CSV entity задає manifest, не колонка.

| Entity | Required | Optional / default |
|---|---|---|
| counterparty | name:Text(200), type:supplier/customer | edrpou:Text(20)="", phone:Text(50)="", email:Text(100)="", address:Text(1000)=""; is_active завжди true |
| item | bos_code, name:Text(200), unit:Text(20), kind:product/material/component, revision:Text(40), currency | method=buy; planned_cost:M=0.00, minimum:Q=0.000, lead_days:int0..730=7, material:Text(200)="", document:DocRef=null, required_documents:list[Text(60)]=[]; без BOM/routing |
| location | bos_code, name:Text(200) | kind=warehouse |
| opening_lot | bos_code, item_ref, location_ref, unit, revision, quantity:Q>0, unit_cost:M, currency, source_reference:Text(1000), reason:Text(1000) непорожній | documents:map(kind→DocRef)={} |
| sales_order | bos_code, customer_ref, owner_id:ID, due_date, currency, source_status:quote/confirmed | notes:Text(1000)=""; source_shipped/source_invoiced не підтримано й не приймаються |
| sales_line | order_ref, item_ref, unit, revision, quantity:Q>0, price:M | немає; Ref order обов’язково входить у rows; усі його lines входять у hash шапки |
| purchase_open_balance | bos_code, item_ref, supplier_ref, unit, revision, source_order_code, source_line_id, original_quantity:Q>0, received_before_cutover:Q, remaining_quantity:Q>0, price:M, original_extras:M, remaining_extras:M, currency, original_due:Date, due_date:Date, source_reference:Text(1000) непорожній | source_documents:map(kind→DocRef)={} |

Повністю нове SO створюється `erp_order`, підтверджується `erp_confirm_order` лише за source_status=confirmed. Item.unit/revision зіставляються буквально, без конверсії; валюта Item не блокує фактичну валюту PO/Lot (B01). Existing reused SO може повторити тільки весь той самий immutable набір lines; доданий/видалений/змінений line — conflict, не update. Source order number і line ID історичного PO окремі від унікального bos_code: PO-7/line1 та PO-7/line2 не зливаються.

Opening conflict перевіряє **persisted pre-batch** запас/рухи по item+location перед будь-яким apply: два нові різні lots2+3 у порожній групі допустимі, giving5; persisted lot1 блокує весь новий зріз. Спочатку відокремити reuse. Повний replay не перевіряється як новий opening; mixed batch із новим opening у вже заповненій групі відхиляється. Чинний ручний opening не змінюється.

Історичний PO: original_quantity−received_before_cutover=remaining_quantity; remaining_extras≤original_extras, усе невід’ємне. Переноситься лише remaining: Purchase.quantity=remaining_quantity, received=0, price/remaining_extras, dates буквальні навіть overdue. Жодних минулих Lot/Movement/payment. Повний partial SO профіль відкладено; never zero чужий shipped/invoiced.

## 4. Точні totals і час (R2)

`SourceControlTotals` = `{counts,money,stock}`. Counts рівно сім ключів вище, integer≥0; bindings не рахуються створеними source rows. Money масив EUR,UAH,USD у цьому порядку; кожний елемент має:

```json
{"currency":"EUR","opening_raw_value":"2.92500","opening_movement_cost":"2.92","sales_open_value":"10.30000","purchase_original_value":"10.64000","purchase_cutover_open_value":"6.55000"}
```

Raw products/sums мають scale5 (Q3×M2). `opening_movement_cost`: сума округлених per-lot quantity×unit_cost до scale2, ROUND_HALF_EVEN — чинна семантика writer, не округлення quantity. Purchase original=original_quantity×price+original_extras; cutover open=remaining_quantity×price+remaining_extras. Stock елемент: `{item_ref,location_ref,unit,revision,currency,quantity:Q}`; sort за цими п’ятьма ключами. Група містить усі source opening lots; різні unit/revision/currency не додаються одним числом. Expected totals — незалежний input, сервер ніколи не замінює їх обчисленими для прийняття.

`planned_delta` = той самий SourceControlTotals shape **тільки для нових source rows**. У разі повного replay counts/money нуль, stock=[]; це не старий source total. Reused lines/шапки атомарно не дають частини нового SO.

`LiveTotals` = `{scope:"batch_targets_and_opening_groups",money,stock}`. Money (три валюти) рівно `{currency,inventory_raw_value:scale5,opening_movement_cost:M,sales_open_value:M,purchase_open_value:M}`. Stock: ті самі group keys + `physical:Q,available:Q`. Це чинні batch targets і всі persisted lots у його opening groups, **не весь баланс компанії**. Sales open — сума per-line округлених (quantity−shipped)×price. Purchase open — сума per-PO округлених `(quantity−received)×(price+extras/quantity)`; округлення точного раціонального значення до0.01 HALF_EVEN, без binaryfloat. Для нецілого розподілу extras правила не залежать від випадкового Decimal context. Ця сума не є оплатою чи invoice. Після нового receipt2 із EUR PO5×1.23+0.40 поточне open value=3.93, source cutover value лишається6.55000.

`live_before` і `projected_after` переобчислюються для поточного стану; не прирівнюються до source controls. На replay до/після однакові, pending opening available0. `first_commit_receipt` незмінний назавжди, current_targets читаються окремо й можуть змінюватися. Ні receipt replay, ні import row identity не порівнюють увесь сьогоднішній target із первісним source snapshot для автоматичного repair.

## 5. Відповіді, identity та commit

Preview HTTP200:

```json
{
  "valid":true,"batch_id":"8b7a87f5-c759-46cc-90f6-7f407710915a","namespace":"synthetic-starter",
  "semantic_sha256":"64hex","errors":[],"warnings":[],
  "rows":[{"entity":"purchase_open_balance","external_id":"po7-line1","row":2,"part":"rows_purchase_open_balance","decision":"create","bos_code":"IMPORT-PO7-1","target_id":null}],
  "source_control_totals":{},"planned_delta":{},"live_before":{},"projected_after":{},
  "proposal":{"id":"UUID","expires_at":"UTC ISO datetime"},"first_commit_receipt":null
}
```

`{}` тут означає точно визначений Totals type із §4, не довільний JSON. Future target_id завжди null: preview rollback IDs не можна рекламувати як committed. Рядки `reuse` можуть показувати дійсний ID. Source row locator: JSON row — 1-based rows index, part="json"; CSV row — physical record number з header=1, quoted multiline не зміщує logical record index. В hash адреса помилки не входить.

Row validation HTTP422: та сама top shape, valid=false, proposal=null, errors=[{entity:known|null,external_id:string|null,row:int|null,part:string,field:string,code:string,message:UA text}], decision=create/reuse/error/blocked, недостовірні totals=null. Зібрати всі незалежні input errors; залежні rows мають DEPENDENCY_FAILED. Parse/schema400, byte-limit413, auth401/403, method405, semantic conflict/stale409. Не повертати сирі приховані refs/комерційні поля в denied відповіді. Відомі error codes включають DUPLICATE_ID, DUPLICATE_HEADER, UNKNOWN_FIELD, BAD_VALUE, MISSING_REFERENCE, CODE_CONFLICT, IDENTITY_CONFLICT, COMPOSITION_CHANGED, OPENING_EXISTS, TOTALS_MISMATCH, DEPENDENCY_FAILED.

Confirm лишається `POST /api/operations/confirm/` із `{proposal_id:UUID,confirmed:true}`. Success HTTP200 — чинний receipt envelope `state=succeeded,erp_event_id,impact` плюс `batch_id,namespace,semantic_sha256,rows,source_control_totals,committed_delta,live_before,live_after`; всі committed rows мають справжні target IDs. Повтор цього proposal повертає **ідентичний** перший receipt. Не додавати динамічний replay flag усередину незмінного receipt; UI знає повтор зі свого запиту/preview. Новий `GET /api/erp/import/batches/<uuid:batch_id>/` повертає `{first_commit_receipt,current_targets}`; `GET .../export/` віддає повний JSON `{format,batch_id,namespace,cutover,semantic_sha256,source_part_sha256,canonical_source,first_commit_receipt}`, а не обрізаний snapshot300/150.

Semantic batch SHA: canonical UTF-8 sorted-key JSON від format/namespace/cutover/tax_basis/bindings/normalized rows/expected controls, без batch_id/filename/byteSHA/row order. Row SHA включає namespace/cutover/entity/external_id/усі source поля; SO — повний відсортований склад lines. Той самий batch UUID+SHA → first receipt, інший SHA під UUID →409. Новий UUID+незмінні row identities → reuse; змінений row під старим external ID →409. Законний receive після commit не змінює row SHA. Навіть replay перевіряє чинні actor/role/session/target type/existence/visibility; тільки нові rows проходять нові eligibility й source byte checks. New rows, що посилаються на reused target, перевіряють його поточну придатність.

Моделі: ImportBatch UUID PK, namespace/cutover/source SHA/canonical source/source bytes hashes, actor FK PROTECT, immutable commit receipt; ImportIdentity UNIQUE(namespace,entity,external_id), original row SHA, first_batch PROTECT, explicit target FK (counterparty/item/location/lot/order/line/purchase), CHECK рівно один target відповідає entity. UNIQUE(namespace,target_fk) для кожного ненульового FK. Жодних GenericForeignKey, source-auth imports, PK replacement чи прихованого cleanup. Заповнений журнал/походження захищені від lossy reverse migration. Bindings мають власний canonical binding SHA; не перетворювати row identity на binding identity мовчки.

## 6. Locked coordinator і історичний контекст (R1)

Одна дозволена orchestration action `erp_import_batch`; не приймати довільний масив erp_actions. Raw пакет входить лише dedicated import preview; generic ERP preview не стає обходом authenticated importer. Погодження зберігає normalized source; confirm заново видає серверний authority. `operations.service.execute` лишається CAS/session/expiry/receipt boundary. Жодного commit між rows. Child writers працюють із log=False; один batch Event посилається на повний row journal і impact. Це зберігає правило одного receipt/event на одну погоджену batch action.

Порядок: authentication CEO → normalize/validate shape → outer atomic → **erp.write_lock перший DB write** → evaluated select_for_update на existing Counterparty за PK asc, потім Employee за PK asc → перечитати identity/тип/активність/архів/всі binding поля → інші refs/identity under ERP mutex → before state → issue phase authority → dispatch rows → independent totals/row checks → batch ledger/Event/receipt → commit. Ні lazy queryset без evaluation, ні довіра до даних до lock не є достатніми. Для нового Counterparty потрібен вузький reusable writer із чинною model/serializer validation під уже взятим mutex.

Для PostgreSQL ця конструкція призначена блокувати звичайний UPDATE/DELETE відповідних Counterparty/Employee до завершення batch; для SQLite select_for_update сам не дає row lock, тому реальний write ERP mutex має бути першим. Якщо updater завершився раніше — importer бачить новий запис і відхиляє stale binding. Snapshot fingerprint включає релевантні Counterparty/Employee/dataset/import identities, відсутні в нинішньому ERP fingerprint; порівняння після locks. Немає потреби переписувати весь CRUD лише для цих refs.

Lock-order оцінка: import не викликає financial save/salary/payment/employee archive, не бере їх locks і не робить зовнішніх HTTP. Чинні Counterparty CRUD не беруть ERP mutex; employee archive бере Employee і AuditEvent, financial salary може брати Salary/Intent перед Employee. Сам import не бере цих залежних locks, отже тут не додається очевидний зворотний цикл. Однак це read-only оцінка, **не доказ deadlock-free/PG pass**: реальні import↔Counterparty update/delete та import↔Employee archive/update тести обов’язкові; lock timeout/deadlock дають rollback409, без автоповтору частини пакета. Membership revocation перевіряється чинним actor повторно; цей контракт не оголошує весь auth/CRUD глобально серіалізованим.

`ImportedPurchaseContext` — immutable issued object, не JSON і не одного type-check. In-process registry зв’язує точний object identity, phase=preview/apply, normalized row SHA, actor/namespace/cutover, DB connection і lifetime outer transaction. Видача тільки coordinator після перевірок під mutex. preview context не застосовується в apply, не переживає rollback/вихід/зміну row; confirm видає новий. `dispatch(...,import_context=...)`/purchase writer приймає context тільки для точної історичної PO row. Без нього B01 purchase_source перевіряється без винятків.

Snapshot source=imported_open_balance має окремий shape: source, namespace, batch_id, row_sha256, external_id, source_order_code, source_line_id, cutover, original_quantity, received_before_cutover, remaining_quantity, price, original_extras, remaining_extras, currency, original_due, due_date, unit, revision, source_reference, source_documents, actor_id. Усі bytes/ID джерел перевірені, первинний external номер не оголошується BoS Document. request/quote/production FK=null. Жодного supplier_confirmation/direct_reason як вигаданого нового погодження. PROTECT/immutable provenance не вимагають заборонити звичайне наступне receive/postpone.

## 7. Файлова відповідальність і додаткове покриття

Власник backend-кандидата a08_upload_review, **лише tmp/b02_candidate**, без canonical edits до root integration. Основні нові файли: `erp/importing.py`, `erp/import_views.py`, `erp/test_initial_import.py`, `erp/test_import_concurrency.py`, `fixtures/synthetic/initial_import/*` (готові JSON/manifest+CSV). Зміни: `erp/models.py` + наступна new migration, `erp/service.py` (27th action/context), `erp/procurement.py` (typed historical branch), `erp/urls.py`; `operations/service.py` (batch approval), `operations/projections.py`, `boss_project/policy.py` (CEO/source projection). Новий migration не змінює старі rows/schema history. Фінансові CRUD не рефакторити; вузький reusable counterparty validation helper може бути локальним importing adapter, без другого неперевіреного create path.

Root володіє UI `frontend/boss_app_source.html`, build assets і документами PARAMETERS/KNOWLEDGE/PROGRESS. R7: готовий шаблон → явні human mappings → row errors і before/delta/after → один confirm → клікабельний журнал/export; після commit не delete import. R3: окрема «Перенесений залишок замовлення», original8 / до зрізу3 / перенесено5 / у BoS2 / залишок3; кнопка receive пропонує3. Source card/table/inspector використовують ті самі поля; manager отримує дозволені джерела, observer тільки явно дозволені identifiers, без commercial snapshot/text. Недоступні original figures не виводяться як0.

Access contract: додати три named маршрути `bos-import-preview`, `bos-import-template`, `bos-import-batch`, `bos-import-export` у `scripts/access_routes.json`, fixture/independent expected matrix `scripts/access_fixtures.py`/`scripts/check_access.py`; усі чотири CEO-only. Звичайний purchase/receive source projection лишається чинною рольовою. Наявні URL/method/role/field assertions зберігаються, нові додаються; frontend прихована кнопка не є доказом auth. Детальний touched-file список evidence перед canonical integration узгоджує root.

Concurrency contract: **зберегти всі 84 прийняті methods, 89 старих pass records та 26 старих actions буквально, додати 27th import_batch**. Не прибирати schemas-equality oracle й не перетворювати exact manifest на динамічне «скільки виявлено». Пропозиція: окремий `ERPImportConcurrencyTests.test_http_pair_import_batch` із трьома явними EUR/UAH/USD records та exact receipt/Event/rows oracle; додати 1 method → мінімум85 і 3 pass records →92 у reviewed manifest. Старий ERP_ACTIONS26 лишається frozen baseline; перевірка union цього baseline+explicit import action повинна рівнятися всім27 schemas. Окремі competing-batch/CRUD/rollback методи додають required IDs/records понад ці числа явно, а не замість старих. `scripts/check_concurrency.py`/`scripts/concurrency_manifest.json`/`erp/test_concurrency.py` потребують вузького узгодженого доповнення, не wholesale переписування. Backend автор готує patch до цих gates; root застосовує після review.

Meaningful acceptance додає до8 сценаріїв READY_PLAN R1–R7: справжній overdue preview rollback/context misuse refusal; replay після receipt зі source6.55/live3.93; two same-group opening lots; PO duplicate source number/different lines; canonical1.0=1.000/changed1.001conflict; reused SO composition; bounded bytes/CSV errors; 3currency totals, late SQL rollback, genuine concurrent HTTP, own synthetic refs CRUD race, projection/access та actual UI click. Жоден з11 gates не послаблюється; full gate6/PG/Windows/D01 не приймаються за цим документом. Перший backend proof створюється лише на нових власних синтетичних БД/медіа; accepted B01 історія не входить у мутації.

### Wire уточнення для root UI перед кодом

Multipart також приймає рівно `batch=<raw file.json>` як альтернативу manifest+CSV; ці режими взаємно виключні. Raw application/json лишається доступним. Final preview response використовує `mappings` замість response `rows`, та додає `counts={create,reuse,bind}`. Mapping рівно `{entity,external_id,row,part,decision,target_model,target_id,bos_code,display_name}`; target_model один із counterparty/item/location/lot/order/line/purchase. У receipt аналогічно `counts,mappings`, input rows незмінні. Remainder полів і totals типи як вище.

`GET /api/erp/import/template/?owner_id=ID&format=json|csv`: CEO-only, server перевіряє обраного owner. json повертає готовий source batch із новим UUID/namespace та окремими synthetic кодами. csv повертає `{manifest:<CSV manifest>,files:[{part,filename,content_utf8}]}`, UI зберігає кожний part окремим файлом без ZIP. Template wrapper не є manifest для upload. Користувацький файл UI не переписує, не JSON.parse перед надсиланням. Після отримання proposal UI зберігає саме його ID для повтору confirm.

## Остаточні уточнення виконуваного B02 кандидата

- Необов’язковий multipart part `bindings` містить strict JSON array `{entity,external_id,target_id}`. Він додається до embedded bindings після окремого розбору. Повтор entity/external_id між джерелами — помилка, без overwrite; SHA точних bytes кожного part зберігається. JSON/CSV джерело користувача не переписується.
- `mappings` включає rows і bindings. Нова прив’язка має `decision="bind"` та існуючий `target_id`; повторна — `reuse`. `counts.reuse` включає повторні bindings. Source counts/money/stock обчислюються тільки з rows. Для binding-only пакета вони нульові.
- Нові bindings/new dependent rows перевіряють активний supplier/customer, каталог buy і warehouse за поточними полями. Законний replay первинної identity після пізніших змін цілі зберігає історію; `current_targets` показує всі targets поточного batch, включно з reused та bindings, без переприв’язки `first_batch`.
- Шаблон сервера: 27 синтетичних рядків, три незалежні ненульові приклади EUR/UAH/USD; owner обирається явно з чинних співробітників. Шаблони JSON і manifest+CSV перевірені реальним preview з CSRF.
- Для точного POST `/api/erp/import/preview/` чинні local/server middleware кешують не більш як 160 KiB+1 доступного Django потоку до CSRF/multipart. 128 KiB лишається лімітом source parts. Заявлена довжина не замінює bounded read; missing/forged length перевірено на власному presented-stream. Байти, які upstream WSGI вже обрізав за HTTP framing, цим шаром не відновлюються. Порядок middleware/CSRF і решта URL не змінені.
- Atomic commit перечитує створені моделі/кількості/ціни/походження перед receipt. Пізній SQL trigger зі зміною ціни дає rollback всього batch.
- ERP action 27 `import_batch` додає 4 concurrency methods і 3 фактичні валютні receipts: 88 methods/92 records загалом. Початкові 84/89/26 та їхні орієнтири залишено буквально, SHA baseline перевіряє gate5.
- ImportBatch/ImportIdentity додають рівно дві таблиці до frozen45. Старі filled table/sequence/bytes oracles збережено; populated import ledger окремо пройшов typed transfer; root виконує native restore proof. Це початковий імпорт, не відновлення повної БД або оновлення історії.

- Усі B02 numeric normalize/preview/confirm/live computations виконуються в явному Decimal context50/HALF_EVEN; integer cents перетворюються Decimal tuple без ambient-context ділення. Low-context real HTTP regression зберігає точні суми.
