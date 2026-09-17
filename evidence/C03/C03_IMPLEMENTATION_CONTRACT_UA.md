# C03 · контракт синтетичної виписки та звірки

12.09.2026. Read-only консолідація C03_READY_PLAN, незалежного C03_PLAN_REVIEW, прийнятих B03/C01 контрактів та незалежного EUR oracle. **Цей підетап не змінював код/БД, не запускав Django, міграції, браузер або ERP-сценарій.** B02 уже інтегровано: full №22 source `dbff81af9070a059c48f91ae6bbbedd58c7448dc766469112bef120e307c73a0`; під час поточного читання root зафіксував HEAD `0b694b11b91abf3e46d3c4bb009df56852384ca5`. B03/C01 — наступні залежності, а не нібито вже наявні функції.

## 1. Межа v1 та рішення незалежного review

Синтетичний CSV → приватний перевірений оригінал → погоджений імпорт незмінних рядків → явне створення/прив’язка локальної Transaction → незалежне рознесення на AR Invoice → джерела й точні валютні підсумки. Імпорт сам не реєструє грошей. Виписка — джерело обліку, а не команда банку.

Прийняті п’ять уточнень review: ERP mutex → фактичний row write-lock наявної Transaction до fingerprint; незалежні осі Transaction/payment; стабільний allocation key з DB uniqueness; actor лише із server identity та незмінна підстава; CEO-only CSV захищений також у старих document/transaction/context маршрутах.

Не входять AP invoice, перекази/API банків, FX/комісія в іншій валюті, opening/closing bank balance, податки, chargeback/сторно, автоматичне повернення/залік переплат, split одного історичного payment Event між різними рядками, many-statement-lines → одна агрегована Transaction, OCR, автоматичні повідомлення, LLM. Нерозібрані випадки залишаються видимими. Імпорт справжнього клієнта та D01 acceptance не випливають із синтетичного тесту.

## 2. CSV і точна ідентичність

Фіксований формат `bos_statement_csv_v1`, parser version `1`. UTF-8, необов’язковий початковий BOM, delimiter comma, стандартне CSV quoting, LF або CRLF. Strict reader, рівно такий header у такому порядку:

```csv
external_id,booking_date,direction,amount,currency,counterparty_external_id,invoice_reference,purpose
```

| Поле | Правило v1 |
|---|---|
| external_id | Непорожній точний код 1–120 символів; без крайніх пробілів/control chars. Регістр значущий, код не генерується з суми/дати/номера рядка. |
| booking_date | Строго валідний `YYYY-MM-DD`, повний ISO calendar date. Історична дата допустима; created_at залишається фактичним серверним часом. |
| direction | Тільки `in` або `out`; сума завжди додатна. |
| amount | Лише decimal string `\d+(\.\d{1,2})?`; 0 < amount ≤ `999999999999.99`, canonical `0.00`. Коми, exponent, signs, NaN/Infinity, зайві знаки після крапки, bool/числовий JSON не приймаються. `1.230` також відхиляється, а не тихо округлюється. |
| currency | Точно EUR, USD або UAH. В одному файлі можливі різні валюти, але кожен рядок одновалютний. |
| counterparty_external_id | Порожньо або точний код ≤120 за тими самими правилами кодів. Порожній код не підставляється з назви. |
| invoice_reference | Порожньо або буквальний текст ≤120 без крайніх пробілів/control chars. Повна рівність Invoice.code — лише джерело підказки; реквізит не розбивається евристично. |
| purpose | Буквальний текст 0–2000 Unicode символів, без NUL та небезпечних control chars; quoted перенос рядка допустимий. Немає silent trim/truncate. Не виконувати як HTML/формулу/інструкцію. |

Рівно 1–1000 data records, не більше 1 MiB оригінальних bytes. Порожній рядок CSV усередині, невідповідна кількість cells, duplicate/extra/missing header, malformed quoting або duplicate external_id всередині файла відхиляють **весь** імпорт. Один термінальний newline не є зайвим record. Error містить logical CSV record number (header=1), column і code; за потреби physical end-line окремо. Оригінал не нормалізується й зберігає власний SHA.

`source_system` — стабільний lowercase slug `[a-z0-9][a-z0-9._-]{0,47}`; `account_ref` — локальний uppercase код `[A-Z0-9][A-Z0-9_.:-]{0,119}`. Значення, що потребують trim/case conversion, відхиляються; UI вибирає вже відомі source/account, а створення іншого account явно відокремлене від зміни display name. Це локальні synthetic account codes, не банківські credentials. Немає автоматичного припущення, що два різні коди — один рахунок.

Незмінна природна ідентичність Line: **(source_system, account_ref, external_id)**, незалежно від filename, row order, booking_date/amount. Semantic SHA обчислюється з canonical JSON первісних восьми полів (amount fixed2, інші точні значення), UTF-8, sorted keys, compact separators. Та сама identity + ті самі поля → reuse; інші canonical поля → 409 `statement_identity_conflict`, без перезапису. Інші ID з тією самою сумою/датою — окремі записи, можуть показуватись як сумнівні, але не зливаються.

StatementImport має UNIQUE(source_system, account_ref, source_sha256). Exact bytes повторно, навіть під іншим Document/filename/actor, повертають перший import/receipt. Reordered/overlapping файл має інший SHA: створює новий Import та його provenance/Event; Line з тим самим змістом reuse. При всіх repeated Lines та новому SHA це новий запис джерела, **0 грошей та 0 нових Lines**. Version2 parser не reinterpret-ить існуючий v1 ledger без окремого майбутнього контракту.

## 3. Приватне завантаження та джерело

**Новий маршрут**, не оголошений наявним: `POST /api/statements/sources/`, multipart `file,code,revision,title`, рівно по одному полю, без інших fields. Усі записи/форматні подробиці — authenticated current CEO; manager/observer403, unauthenticated401 до читання/парсингу файла. File має `.csv`, filename ≤200, code1–80/revision1–40/title1–200. Максимум multipart body 1 MiB + 64 KiB; file ≤1 MiB. Це вузький форматний ліміт у чинній private-storage quota; A09 13 MiB oracle та ліміт спроб не змінюються.

CSV структурно валідовується перед записом. Перевикористати current durable upload/ERP write_lock/save_verified/on_commit finalize/discard_new; жодного запису файла з rollback preview. Document створюється `access_level='ceo'`, status needs_review, original_file/size/checksum; `text` — непорожній службовий опис формату/кількості рядків, **не джерело parser**, `sections` — server-generated marker `kind='bos_statement_csv_v1'` та summary, не вміст усіх purpose. В оригіналі зберігаються всі bytes.

Код документа можна продовжити новою revision тільки якщо **всі** попередні revision цього code — CEO-only statement sources. Існуючий management/operational або звичайний document code відхиляється до створення source; його access_level не виправляється. Загальний documents/upload лишається без довільного CSV parser й відмовляє повторне використання statement source code іншим форматом. Це закриває обхід успадкованого management access.

Використати чинний `POST /api/operations/documents/<id>/review/` з `{checksum}`: для statement source review лише CEO, verified bytes, contract_id не додається. Upload/review не додають нового accounting AuditEvent або ActionProposal — як нинішній механізм документів. Source може зберегтися, якщо користувач не погодив імпорт: це приватний завантажений файл, не частково проведені гроші.

Import вимагає approved marker-bearing CEO-only source, exact document_id/checksum, читає **verified_document_bytes**. Новіша revision не переписує старий Import/Line і не є підставою підмінити його bytes. На подальшій звірці перевіряються first-source bytes і збережена approved attestation; latest document не заміняє історичне джерело. Reupload source із тим самим bank identity та іншими даними дає conflict, не repair.

Для не-CEO documents policy назавжди виключає statement-marked sources і всі Document ID, що вже є джерелами StatementImport, незалежно від mutable access label; код та історичні revision враховуються при download/text/versions/export. Наявна історія Import — другий незмінний доказ класифікації. Server marker не є дозволеним полем довільного write API; не створювати generic CRUD Document для обходу.

## 4. Три additive моделі finance

| Модель | Обов’язкові дані та зв’язки |
|---|---|
| StatementImport | UUID PK; Document FK PROTECT; source_sha256, format/parser_version; source_system/account_ref; verified actor FK PROTECT, created_at; immutable source_snapshot (code/revision/checksum/size/status, schema, counts); first receipt JSON. UNIQUE(source_system,account_ref,source_sha256). |
| StatementLine | UUID PK; first_import FK PROTECT; server created_at; source_system/account_ref/external_id DB UNIQUE; original record number; canonical восьми полів, Decimal(14,2) amount; semantic_sha256; nullable Transaction OneToOne PROTECT; nullable bound_at/bound_by FK PROTECT/binding_snapshot JSON. Source поля незмінні; transaction+binding заповнюються **один раз атомарно** й більше не замінюються. |
| StatementAllocation | UUID PK; line FK PROTECT; **allocation_key UUID globally unique**, додатковий UNIQUE(line,allocation_key); Invoice FK PROTECT; payment Event OneToOne PROTECT; amount Decimal(14,2)>0, currency; mode new_payment/existing_payment; actor FK PROTECT, created_at; immutable intent_sha256 та source_snapshot/matching/reason. Жодного raw update/delete. |

Більша за review глобальна uniqueness allocation_key навмисна: вона забезпечує глобальний namespace payment reference. Повтор ключа на іншому Line — conflict; UI не переносить один намір між рядками. First Import receipt містить ordered references до **всіх** прийнятих Line та create/reuse counts; overlapping imports не змінюють first_import. Нової join-моделі для overlapping sources немає: immutable receipt має їх точний перелік.

DB CheckConstraints: amount positive/max, EUR/USD/UAH, direction in/out, allocation mode, all-or-none Transaction/binding fields. Суми SUM allocations, customer equality і source consistency перевіряються командою під lock, а не видаються за міжтабличний CheckConstraint. Після commit Import receipt і всі нові allocations мають завершені IDs/джерела. In-flight значення існують тільки всередині atomic, rollback не лишає напівприв’язаної Line.

Міграція лише додає три таблиці. Нуль inferred FK/backfill між історичними Invoice.paid/Event/Transaction. Reverse відмовляє до першого DDL, якщо хоча б одна нова таблиця непорожня. Empty forward/reverse зберігає всі старі ID/FK/sequence high-water/private bytes. Transfer/schema registry та restore додають точні три імена поверх фактично frozen B03/C01 schema; не покладаються на старий baseline45/47 і не оголошують попередній restore доказом нової схеми. Ledger admin або не зареєстрований, або лише scoped read-only без bulk/delete/import/save.

## 5. Exact write wire та попередній перегляд

Дві нові ERP actions у наявному `POST /api/erp/preview/`; confirm — наявний `POST /api/operations/confirm/` із `{proposal_id,confirmed:true}`. New actions CEO-only у схемі, Policy.action, replay, context contracts та actual manifests. JSON strict, ≤30000 bytes; невідомі/duplicate keys, bool замість ID, float замість integer/string, actor/role/paid/reference/source_snapshot поля відхиляються. Dates/decimals/UI diff обчислює сервер.

### 5.1 Import

```json
{"action":"erp_statement_import","document_id":17,"source_sha256":"<64 lower hex>","source_system":"synthetic-bank","account_ref":"E2E-EUR-ACCOUNT","format":"bos_statement_csv_v1","parser_version":"1"}
```

Рівно ці поля. Preview показує source identity/SHA, всі errors, create/reuse mappings, per-currency in/out/net, нуль Transaction/payment delta. Будь-яка помилка422/409 не створює proposal або Import/Line. File size/body413. Коли exact Import уже існує, відповісти `state='no_change', id=null, first_commit_receipt=<original>, current_summary=<fresh>` без нового proposal/Event; не називати історичний receipt поточними totals.

Нове погодження має стандартні `id,payload,expires_at,effect,impact`; prospective UUID/PK з rollback preview не подаються як збережені. Effect містить стабільні external codes, counts і decimal strings; жодних persistence IDs, які не пережили preview.

### 5.2 Reconcile

```json
{
  "action":"erp_statement_reconcile",
  "line_id":"<statement-line-uuid>",
  "transaction":{"mode":"create_transaction","category":"customer","description":"Синтетична оплата рахунку E2E-INV-001"},
  "matching":{"kind":"manual","counterparty_id":12,"counterparty_external_id":"E2E-CUSTOMER-001"},
  "reason":"Звірено зовнішній код клієнта з його карткою та рахунком.",
  "allocations":[{"allocation_key":"417a9537-3de8-4bf5-b99c-638cefcb96f0","mode":"new_payment","invoice_id":9,"amount":"4.68","currency":"EUR","invoice_match":"exact_reference","reason":"У виписці зазначений повний номер рахунку E2E-INV-001."}]
}
```

Цифрові PK в прикладі — placeholders; реальний fixture отримує actual IDs. Верхні поля усі обов’язкові. reason — trimmed3–1000; allocations — array0–50. Порожній array допустимий для нерознесеного cash record або вихідної операції. Кожен allocation reason3–1000; stable allocation_key canonical UUID v4 видається до першого confirm, зберігається з наміром. Новий додатковий partial allocation — окремий явний намір/новий ключ.

**Transaction object, рівно один режим:**

- `create_transaction`: тільки mode,category,description. category — чинні supplier/customer/utility/rent/tax/other, **не salary**. description trimmed3–300; purpose довший за300 вимагає явного опису користувача, без substring truncation. amount/currency/date/direction — тільки з Line; counterparty — з matching; contract/branch=null у новій Transaction v1. Надалі вони не дописуються до statement-linked Transaction. Якщо вже є source-bound Transaction, той самий create intent перевіряється й reuse, не викликає нового save_transaction.
- `existing_transaction`: тільки mode,transaction_id (positive int). Обрана Transaction існує, ще не прив’язана до іншої Line; при раніше прив’язаній Line ID мусить бути тим самим. Перевірити exact amount/currency/direction/date=booking_date і контрагента. Історичні category/description/contract/branch/archived_at не переписуються. Дату не наближати допустимим інтервалом. Несумісність — відмова з конкретними полями.

**Matching object, рівно один варіант:**

- `manual`: kind,counterparty_id (positive int або explicit null),counterparty_external_id (exact значення Line, включно з empty string). Це явна attestation, не автоматичний mapping. null допустимий для generic нерознесеного запису, allocations тоді порожні. Нове створення з ненульовим ID вимагає active Counterparty; historical existing Transaction можна звірити з її вже неактивним Counterparty, не змінюючи його. При AR потрібен ненульовий ID рівно Invoice.customer.
- `import_identity`: kind,identity_id (positive int),counterparty_id, counterparty_external_id. Взяти **фактичну B02 ImportIdentity**, entity=counterparty, ID/зовнішній код/target exact; snapshot з namespace/first_batch/row_sha/target. C03 не створює/змінює ImportIdentity, не пише в порожню колонку неіснуючий ExternalRef. Namespace не виводиться з source_system. Без такого імпорту працює manual варіант, як у EUR oracle.
- `salary_source`: kind,salary_id (positive int),counterparty_id=null,counterparty_external_id (exact Line code). Лише existing_transaction, direction out, allocations=[]; Salary.status=paid та Salary.transaction_id=selected Transaction, точні amount/currency/payment_date, category salary. Employee FK та вихідний salary snapshot є підставою поряд із reason. Не шукати Salary тільки за сумою/датою; не брати її write-lock після Transaction і не проводити нову зарплату.

**Allocation object:** allocation_key,mode,invoice_id,amount,currency,invoice_match,reason; лише existing_payment додатково потребує payment_event_id (positive int). amount — positive canonical fixed2 у DB bounds. invoice_match exact_reference вимагає Line.invoice_reference==Invoice.code; manual — явний вибір цього ID та reason, без автоматичного висновку з amount/date. Для обох Invoice.customer==matching.counterparty_id==Transaction.counterparty_id, Invoice.currency==Line.currency==allocation.currency; Line.direction=in. Одна Line може покрити кілька рахунків того самого контрагента/валюти. Один рахунок — кілька Lines.

Preview показує cash layer і invoice layer **окремо**: existing/new Transaction, exact фінансові поля, before/after Invoice paid/credit/receivable, source-derived allocation references, allocated/unallocated, existing/reused records, count deltas, reason. Сума всіх старих+нових allocations ≤Line.amount. Для same key+same canonical allocation intent — reuse незмінного запису; інший Line/invoice/mode/event/amount/currency/invoice_match/reason →409. Actor і mutable display names не входять до identity hash; історичний actor/snapshot не переписуються при replay іншим CEO.

Коли Line уже прив’язана і всі allocations reused/порожні, preview no_change без нового proposal. Якщо proposal був виданий раніше, а ідентичний намір виконав інший proposal, confirm може зберегти no-change receipt у своєму вже існуючому proposal, але **0 нових ERP/Audit/FinancialIntent/Allocation**, без переписування першої події. Додаткова причина не редагує попередній binding; нова дія з новим allocation має свою причину.

## 6. Два незалежні облікові шари

Нова Transaction викликає **finance.commands.save_transaction** із verified server actor і `operation_id='stmt-tx:'+Line.uuid.hex` (40 символів). Природна Line identity, OneToOne і ERP mutex забезпечують cross-actor dedupe: actor-scoped FinancialIntent сам по собі недостатній. Для reuse не робити другий create під іншим actor. Не використовувати Transaction.objects.create у C03.

Одна Transaction відповідає **повній** Line.amount. Allocations не створюють окремі доходи; unallocated залишається частиною вже записаного надходження. C03 не повторює Invoice revenue, не змінює Shipment cost/quantity, не дорівнює бухгалтерській проводці подвійного запису.

`new_payment` викликає єдину виділену з erp.service гілку payment: fresh B03 invoice_settlement → amount≤receivable → global reference uniqueness → paid increment → **один erp_payment Event**. Ручний erp_payment використовує той самий helper зі старим payload/result semantics та без автоматичної Transaction. Не викликати повний dispatch повторно для child payment і не додавати другий generic Event після helper.

Reference нового statement payment **зафіксований до тесту:** `STMT-` + `allocation_key.hex`, 37 символів; EUR oracle лишається `STMT-417a95373de84bf5b99c638cefcb96f0`. Bank external_id/purpose/reference зберігаються окремо, не обрізаються до60. Якщо namespace вже зайнятий несумісним історичним Event — conflict, не підміна та не автоматичне перевидання ключа.

`existing_payment` — actual Event.action=erp_payment, payload.invoice_id exact, payload.amount точно **повна** allocation amount, nonempty reference, Invoice.currency exact, жодної попередньої Allocation на цей Event. Зберегти original Event payload/result та дату як snapshot. Поточні gross paid повинні покривати історичні payment Events цього Invoice; явна суперечність history/paid блокує прив’язку. Дата Event.created_at не прирівнюється до банківської booking_date: це різні факти. Explicit invoice/customer/source attestation необхідна. Не застосовувати поточний receivable cap до already-existing payment: його уже враховано в paid. Нового paid/ERP payment Event немає.

| Намір | Δ Transaction / FinancialIntent / finance Audit | Δ paid | Δ child erp_payment | Δ Allocation |
|---|---:|---:|---:|---:|
| Нова Transaction, allocations=[] | +1/+1/+1 | 0 | 0 | 0 |
| Нова Transaction + k new_payment | +1/+1/+1 | Σ new amounts | +k | +k |
| Нова Transaction + k existing_payment | +1/+1/+1 | 0 | 0 | +k |
| Existing Transaction + new_payment | 0/0/0 | Σ new amounts | +k | +k |
| Existing Transaction + existing_payment | 0/0/0 | 0 | 0 | +k |
| Раніше прив’язана Line + додаткові allocations | 0/0/0 | Тільки суми нових payment | Лише нові payment | Лише нові keys |
| Existing Salary.transaction, out, allocations=[] | 0/0/0 | 0 | 0 | 0 |
| Повний reuse/no-op | 0/0/0 | 0 | 0 | 0 |

У кожному рядку таблиці з реальною новою binding/allocation додається **один власний erp_statement_reconcile Event**, незалежно від кількості child payment; не generic AuditEvent зверху. Змішаний список existing/new дозволений: дельти адитивні, старий payment не проводиться двічі.

B03 єдині формули: effective_credit=credits−reversals; net_amount=amount−effective_credit; receivable=max(net_amount−paid,0); customer_credit=max(paid−net_amount,0). 123.40/paid100.00/credit24.68 → receivable0/customer_credit1.28/paid100 незмінні; new_payment відхилено, existing_payment linkage можливе за його фактичним джерелом. SupplierClaim pending/confirmed — не AR, AP або cash; C03 не оплачує її автоматично. B02 opening lots/PO cutover balances не створюють минулих Invoice, paid або банківських Lines.

## 7. Atomic writer, replay та конкретні спільні touchpoints

Порядок confirm: current identity/session/role → **ERP mutex як перший фактичний business write lock** → refresh proposal/current actor/Policy → literal succeeded receipt replay до нових Events і до перевірки застарілого business fingerprint. Для ще не виконаного proposal: визначити selected/bound Transaction → no-op UPDATE її direction (той самий row lock як finance._save) → fresh Transaction/зворотні зв’язки/Salary read/source bytes/Invoice/B03 state → **domain replay lookup за exact source/intent keys**. Якщо весь намір уже підтверджено іншим proposal, можна записати no-change receipt без нового domain ефекту, до загальної stale перевірки. Жодна непідтверджена частина змішаного наміру тут не виконується. Якщо потрібний хоча б один новий ефект, далі strict expiry+fingerprint → claim proposal → команди → всі Event/Audit/ledger → receipt → atomic commit. Отримання receipt для вже здійсненого наміру не подовжує строк дозволу на нові записи.

Для preview з існуючою Transaction порядок такий самий **до fingerprint**. Використати маленький спільний lock helper з реальним UPDATE і `_base_manager`, не empty save заради lock. Звичайний finance PATCH/admin writer лишається Transaction → validate StatementLine; validator не бере ERP lock, інакше виникне зворотний порядок. C03 не бере Salary write-lock після Transaction. Source/counterparty/ImportIdentity snapshots читаються свіжими; якщо в майбутньому потрібні кілька Transaction в одному намірі — PK order, але v1 має лише одну.

Fingerprint C03 розширює поточний ERP стан на нові Import/Line/Allocation, selected/bound Transaction **усі financial fields+archived_at**, explicit Counterparty/ImportIdentity/Salarу джерело, current actor/access revision та approved source identity/checksum/marker. bytes reread дає незалежний checksum proof. Preview rollback не залишає FinancialIntent/Audit/Event/Line чи файлів. Prospective IDs не обіцяються як збережені. Shared DB alias той самий, немає callback/side effect поза atomic.

Concrete інтеграція:

- `erp.service.SCHEMAS/clean`, `boss_project.policy.CEO_ACTIONS/action` та assistant tools schema: рівно дві actions з §5; explicit ID checking нових моделей, не permissive generic queryset.
- `erp.views.preview`: підставляє **server command context** verified actor/proposal context для C03 і захоплює потрібну Transaction до fingerprint. API client actor поля не приймає. Старі actions зберігають compatibility.
- `operations.service.execute`: окрема явна C03 confirm branch в існуючій системі proposals, як наявний B02 branch. Вона повертає finished receipt і не потрапляє в generic post-dispatch Event.update, якщо reuse повернув стару подію. Це запобігає зайвому Event та переписуванню історичного result/actor.
- `finance.statements` (новий вузький модуль): чистий CSV parser, canonical validators, first-source/history projections, import/reconcile writer. Він створює рівно один own ERP Event на новий ефект, child payment — спільний helper. Не новий глобальний financial service.
- `erp.service` shared payment helper: manual action повертає її один Event; C03 отримує child ID. Server actor/proposal/source IDs фіксуються при створенні C03/child Events; existing Events не редагуються. Legacy result/note/reference validation збережені.
- `finance.commands.validate_transaction`: при історичному StatementLine reverse link захистити **TRANSACTION_FIELDS включно з description**, а не лише TRANSACTION_CORE, через API/admin/shared command. Звірочна причина лежить у ledger. Archive/restore дозволені чинною командою, беруть row lock, зберігають суму та джерело; archived Transaction лишається в cash totals і звірці.

Receipt import: state,schema,import_id,source/document IDs+SHA,create/reuse counts,ordered Line references,per-currency source totals,erp_event_id. Receipt reconcile: state,schema,line_id,transaction_id,transaction_created,binding_created,new/reused allocation IDs,created/reused payment Event IDs,amount/currency,allocated/unallocated,invoice before/after summaries,erp_event_id,actor та actual impact. Історична квитанція незмінна; read current_summary окремо. Native generic Audit/financial counters не додаються для краси.

Same-ID replay після наступних змін PO/Invoice/Task/Transaction archive повертає первісний receipt після current access gate, не repair current state. Role downgrade/revoked identity блокує стару квитанцію. Повторний proposal з ідентичними stable keys не породжує нові гроші навіть іншому CEO. Network timeout/5xx не очищає proposal/allocation keys; за unknown outcome підтверджувати той самий ID. Наявність Line/receipt може довести успіх; відсутність receipt у read не доводить, що паралельний confirm не commit-иться.

C01 task-proposal status GET не рекламується як C03 route. У v1 C03 використовує same-ID confirm та scoped committed Line/Import reads. Якщо UI потребуватиме окремого proposal status GET, його треба явно додати для **двох** CEO-only actions зі строгим owner/current-role/source gate і тим самим pending semantics; це не неіснуючий B02 batch endpoint. Не створювати нове погодження лише тому, що dialog закритий або expires_at минув при unknown outcome.

## 8. Read API, доступ та Bank UI

Наступні маршрути **нові**, не заявлені вже доступними:

| Метод / шлях | Мінімальний результат |
|---|---|
| GET `/api/statements/imports/` | Пагінований перелік source/account/import/source_document/created_at/counts. |
| GET `/api/statements/imports/<uuid>/` | Original first receipt/source SHA, ordered Line refs та fresh поточні totals окремо. |
| GET `/api/statements/lines/` | Line projection, source/account/date/direction/currency/amount, transaction_id, cash_recorded,allocated/unallocated,status. Фільтри source_system/account_ref,currency,direction,status,from,to. |
| GET `/api/statements/lines/<uuid>/` | First source/record/bytes download link, immutable normalized input, binding/current Transaction, allocations/payment/Invoice/SO sources, before/after history. |
| GET `/api/statements/lines/<uuid>/candidates/` | Тільки підказки exact invoice reference+currency та явно наявна ImportIdentity/показане manual mapping; пояснення basis/conflicts. Existing Transaction кандидат — explicit selection; збіг amount/date не означає доведену звірку. |
| GET `/api/statements/summary/` | За тими самими account/date/currency filters: imported in/out/net, recorded in/out/net, unposted amounts, incoming allocated/unallocated; кожен шар окремо. |
| GET `/api/statements/imports/<uuid>/export/` | CEO export з original source references та current statuses, не заміна оригіналу. |
| GET `/api/transactions/summary/` | Окремий новий collection read у TransactionViewSet: точний local journal by currency/date, in/out/net та expense categories; archived entries включені. Не приписує unlinked manual transactions певному bank account. |

Списки: `{items,next_cursor}`, limit default20/max100; invalid filters400, scope404, auth401/403. Stable signed cursor binds user/access revision/filter/cutoff, ordering created_at+PK; не сирий необмежений dump. Detail/history — тільки поточний CEO. Export потребує чинного export permission; source download — чинного download permission. Усі amount/totals fixed2 **JSON strings**, жодного float. Агрегати 1000 великих рядків обчислюються Decimal/Fraction з достатнім precision, не кладуться у менший DecimalField і не переповнюють його.

Статуси derived: unposted (Transaction=null, allocations0); incoming unallocated/partial/reconciled за точним SUM; outgoing cash_recorded позначає зіставлення витрати з журналом, не AR settlement. Немає stored «успішно» без FK. Архівована Transaction не стає unposted, не втрачає джерело/суми. Import і Allocation не архівуються в C03.

Старі `/transactions/` для manager виключають StatementLine-linked Transaction цілком, як salary sources; не показують їх metadata. Для document sources захист §3. Нові ledger не додаються сирим top-level у ERP snapshot; дозволені лише окремий CEO read/explicit allowlist. `operations.projections.snapshot/receipt/audit`, exports, assistant context, UI cache, direct `.json`/admin routes перевіряються на canaries. ERP statements/payment events CEO-only; finance audit вже закритий не-CEO. Після downgrade очищаються client cached finance/source data за access_revision. Історична конфіденційність не зникає після rename labels.

Bank зберігає поточну навігацію: вкладки «Журнал» і «Виписки», upload→review→preview→confirm. Натискання row відкриває джерело, original bytes, Transaction і конкретні Invoice/payment IDs; перед confirm — exact «було → стане». Income/expense/net графіки журналу переходять із Number-сумування змішаних валют на серверний `/transactions/summary/`, explicit currency selector і period. Manual Bank create зберігається, але UI явно надсилає обрану currency; існуючий generic finance API не втрачає функцій. Старі Counterparty aggregate floats не використовуються як C03 фінансовий oracle і не видаються за виправлені цим блоком.

Statement raw movement, posted local cash і invoice allocation **не додаються між собою**. «Чистий рух періоду» не називається банківським залишком: opening/closing balance немає. CSV export neutralizes текстові formula prefixes `=,+,-,@` (у тому числі після початкових whitespace/control); original source bytes/SHA не переписуються. Числові стовпці експорту — контрольовані canonical числа. CSV text не виконується як instruction або HTML.

C01 Task archive незалежний: default active tasks/KPI виключає archived_at, explicit archive/history/restore збережені. C03 не завершує/не відновлює/не архівує Task, не копіює bank purpose в доступний менеджеру результат. Task можна завершити окремою C01 дією за його FK/deadline/result/reason; архівування не відміняє Invoice/payment. CEO бачить фінансовий source chain поряд із чинними доступними задачами, історичні Task IDs не зникають.

## 9. Gate 6: підтвердження чисел і counts ДО freeze

`tmp/E2E_NUMERIC_ORACLE_UA.md` та `tmp/e2e_expected_draft.json` **не змінено**. Контракт C03 підтверджує всі їхні суми: PO12.70, receipt4/cost5.08, supplier return1/carrying1.27/pending claim amountnull, approved3, transfer2/cost2.54, shipment2/AR4.68/cost2.54/gross difference2.14, paid4.68/receivable0.00, stock1/value1.27, PO gross received4/open6/value7.62. AP/refund/customer credit0 у цьому сценарії; ніщо не backfill-иться з B02.

| Крок групи після baseline | Δ ERP Event | Δ ActionProposal | Δ AuditEvent |
|---|---:|---:|---:|
| Purchase, receive, supplier return, quality, transfer, order, confirm_order, reserve, ship, invoice | 10 | 10 | 0 |
| Statement import одного нового Line | 1 | 1 | 0 |
| Reconcile: create Transaction + один new_payment | 2: reconcile + child payment | 1 | 1: transaction.create |
| C01 create_task + update_task(done) | 0 | 2 | 2 |
| **Разом** | **13** | **14** | **3** |

Statement source upload/review додають один Document після baseline, але0 accounting Event/Proposal/Audit. Джерельні requirement/quote raw creates як і раніше не входять у14 proposals. У reconcile +1 Transaction/+1 FinancialIntent/+1 Allocation, жодного окремого user payment proposal. Кожна з14 дій: first confirm+immediate replay+late replay = **42 confirm HTTP calls**. Replays повертають ті самі first receipts та0 domain/history дельт.

Reference freeze STMT-key (§6) **підтверджує literal reference draft**, не потребує поправки. manual matching із actual Counterparty ID та exact external code відповідає oracle alias map, B02 ImportIdentity не додається задля fixture, тож нових B02 batch/actions немає. C01 Task done має FK/result/reason, archive=null; архівування тестується окремо й не додає подій до gate6. Додаткових accounting audits на import/reconcile/source upload не пропонується: власні ERP Events+immutable ledger є слідом, finance audit тільки від справжнього save_transaction.

Отже **13 ERP /14 proposals /3 audit підтверджено як контрактний oracle до реалізації**, без зміни numeric JSON. Якщо реалізація потребуватиме ще однієї власної події, це окреме пояснене контрактне рішення до freeze; не адаптувати expected до фактичного провалу. Цей файл не є виконаним gate6 або D01 acceptance.

## 10. Мінімальні meaningful red→green докази

1. Strict source/parser: UTF8/BOM/quoted newline, bounds1MiB/1000, duplicate header/row, identity collision/mismatch, exact semantic amounts, unsupported parser/date/currency, corruption verified bytes. Repeated file vs reordered/overlap counts окремі. Жодного partial Import/Line або proposal при invalid data.
2. Exact currency fixtures EUR17.39/USD123.45/UAH9801.07; Invoice123.40 оплати40.10+83.30; кілька invoices/partial leftovers і maximum-money sums. Derived totals містять тільки обрану валюту. Old Bank mixed currency behavior має власний actual red перед правкою читання.
3. Таблиця §6 по обох осях: manual ERP payment без Transaction + new cash record; existing Transaction+existing payment; salary counterpartynull; outgoing без AR. Assertions усіх шарів і actor snapshots, не лише status='reconciled'.
4. Same key30 із Line100 → lost response → новий proposal same key: allocated30, не60. Changed intent/key on other Line409. Same-ID late replay після archive/credit/інших records; cross-CEO domain reuse1 Transaction і первісний actor.
5. B03 credits: 123.40/100/24.68 → cap0/customer_credit1.28; existing-payment linkage без повторного paid; credit reversal відновлює належний receivable, не payment. Supplier claim/return/B02 cutover не генерують cash або fake AP.
6. Actual concurrent HTTP: reconcile/link ↔ finance PATCH, archive/restore; два confirm/proposals одного Line; same allocation key; ручний payment/credit ↔ reconcile на одному Invoice. Transaction lock до fingerprint, жодного зворотного Salary/ERP lock. SQLite і PostgreSQL окремо, немає pretend PG proof.
7. Actual SQL trigger failures після Transaction/Audit, child Event, Allocation та перед receipt → всі таблиці/paid rollback, той самий intent завершується один раз. Не mock writer, не компенсувати committed history видаленням.
8. CEO-only source canaries: upload management code, generic upload statement code, marker+historical-import access навіть при label change; manager download/text/.json/transactions/context/export/audit/old receipt/admin; revoked role/cache. Жодного purpose/money metadata leak.
9. Immutable source/transaction: REST PUT/PATCH/admin/shared command відхиляють зміни source-linked financial fields+description; archive/restore зберігають cash totals/OneToOne. Старі source bytes/ID/receipt/Event не переписані після Counterparty rename/нової revision/import replay.
10. Mixed legacy/new ledger migration, lossy reverse доDDL, actual transfer/clean restore усіх нових FK/IDs/high-water/CSV bytes/replay. Явний schema/table baseline additive3, а не динамічне прийняття будь-яких таблиць.
11. Actual EUR gate6 через accepted APIs і frozen numeric JSON: усі числа/13/14/3/42/source SHA/privacy/Task result. Обидві вихідні приватні бази SHA unchanged, лише нова власна synthetic DB/media.
12. Browser390/768/1440, zoom200%, keyboard/Escape, largepurpose, delayed response/dialog close/reopen/refetch failure, preview field mismatch, duplicate click, persistent same-ID. Без браузера — НЕ ЗАПУЩЕНО; Babel/source review не є UI acceptance.

Нові actions/routes додаються явними записами до gate4/gate5 manifest, їх own counts/HTTP pairs/required test methods та відомі baseline actions залишаються. Старі finance/payment/source/role/Task тести не видаляються; мінімальні fixture/read contract adaptations документуються old assertion→accepted cause→new positive+negative proof. Жодного послаблення11 gates, приховування A09 нестабільності чи A10/A11/PG/Windows/CI невиконання. Після scoped green — незалежний review, frozen canonical full verify та один root commit; цей контракт реалізацію не підміняє.

## 11. Provenance прочитаних джерел

| Джерело | SHA-256 при читанні |
|---|---|
| tmp/C03_READY_PLAN_UA.md | 85e0470ce01905dc0ed7c5160232d5fc15fb39c875d74ac822afddca7f14cf4e |
| tmp/C03_PLAN_REVIEW_UA.md | e74d60164a51336ee064a4508d117ae7c3cfd9044ba2fb280b562bd900699d9b |
| tmp/C01_IMPLEMENTATION_CONTRACT_UA.md, provenance corrected | cd52d99ea0f9bb8ae8172deace69c6f32da29513ce02d358593dea22d61d2a04 |
| tmp/E2E_NUMERIC_ORACLE_UA.md | cc4d4ba290205dfc88313a34a9d99ed2d862cb5c85b64cffe17ee75a52234409 |
| tmp/e2e_expected_draft.json, unchanged | 10e8b6e671db8e2656683ebfa16bfabc1a75989543e353b6c37d17e43e27616f |
| erp/service.py, canonical B02 | cee88c707e7aae35dc8c7df21ee4dd00ffcf5ca344dc38e0356720fe02e21955 |
| erp/views.py | ac015006daf8b7f90a34dadf8ee10a8f8fb0733deaa1c1d3bae640cdb37a0b32 |
| operations/service.py | 259dab6c7f418638fa8b591632d8ba1628ef58cf55c2d4e383aefbbc7120ea59 |
| finance/commands.py | e9c2f3e5abca117bf20b754ea9722b3843960ed4c4e3a9d4d1d34bf4d2e9d791 |
| boss_project/policy.py | 03fd69a02cf0e6f7301e506e01253f2484a5673bb6a546d9140f6a6fb48071f9 |
| operations/views.py | 5323442b77ddb19a1cc358c31295f6e8dc3472126fb64ee9be3bbf7bc82b040a |

Це snapshot джерел для рішення; root може далі змінити canonical у погодженій черзі. Перед реалізацією C03 звірити фактично frozen B03/C01 helpers та схему з цим контрактом, не запускати повторну інвентаризацію85/12 і не змінювати історичні докази.
