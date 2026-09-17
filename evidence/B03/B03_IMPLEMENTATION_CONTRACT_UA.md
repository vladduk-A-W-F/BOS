# B03 · контракт реалізації синтетичного v1

12.09.2026. Консолідовано B03_READY_PLAN, незалежний B03_PLAN_REVIEW R1–R8 та рішення root. **Це контракт майбутнього кандидата, не виконана реалізація.** Канонічний HEAD при читанні: `c71e601e4681d8b7bb08cd08669f2e204f30ff4d`; B02 ще готується окремо. Реалізацію B03 root призначить після freeze B02 і старту його full verify. Код, БД, тести й історичні записи для цього документа не змінювалися.

## 1. Прийнята межа

Первісний `output/BoS_Plan_UA.md` B03 вимагає: звільнення резерву за скасуванням; історію виправлень; простежуване повернення; кредитове коригування без повторної оплати. Цей контракт реалізує саме це шістьма конкретними діями та шістьма моделями, без універсального journal framework.

- Дати змінюються чинним audited `erp_postpone` / `erp_postpone_job`; кількість до виконання зменшується новим cancellation.
- Окреме нове замовлення — нове зобов’язання. **Атомарної заміни quantity increase/ціни/версії немає**: UI не обіцяє такої кнопки; залежності старого виконання, invoice, WIP показані явно. Це межа v1, не невиконана вимога універсальної replacement-системи.
- Customer return і supplier return — різні фізичні дії. Credit і supplier claim — окремі документи. Payment/cash/податки/AP/COGS автоматично не змінюються.
- Кредит лише в межах первісного Invoice; reversal — повний одного credit. Часткове сторно, debit понад Invoice, refund, FX, автоматичний залік переплат, бухгалтерські закриті періоди, переробка WIP і автоматичне зіставлення старих return відсутні.
- Gross Q/shipped/invoiced/received, Invoice.amount/paid, первісні Event/Movement, B01 approval snapshot, B02 canonical source/receipt не переписуються. Складський баланс Reservation/Lot та факт нової оплати змінюються тільки чинними спільними writers.

## 2. Wire types і шість дій

Закритий JSON: невідомі/повторні ключі відхиляються через strict JSON/portable value validation. Загальний ліміт чинного `operations.views.body()` 30000 байтів не змінюється. До 30 credit allocations в одній дії. Нові дії входять у `erp.service.SCHEMAS`; старі 26 payloads та B02 `erp_import_batch` не змінюються заради B03.

| Тип | Контракт |
|---|---|
| ID | integer>0, не bool; тільки фактичний збережений запис відповідного типу. |
| UUID | canonical lowercase UUID4; operation_id зберігається UI для всіх повторів цього наміру. |
| Q | Десятковий **рядок**, невід’ємний, без exponent/comma/grouping; ≤3 значущих десяткових знаків, canonical `0.000`; додатність за полем. Чинний `number`/місткість полів не розширюються. |
| M | Аналогічний рядок ≤2 знаки, canonical `0.00`; валюти EUR/UAH/USD окремо. Нуль дозволений для claim/credit allocation, не payment. |
| code | 1–60 Unicode символів, буквальний, без NUL/surrogate, без прихованого обрізання; UNIQUE у відповідному document model. |
| reason | 3–1000 Unicode символів після перевірки непорожнього змісту; канонічне значення зберігається. Не інструкція до виконання. |
| business_date | ISO `YYYY-MM-DD`, не пізніше server `as_of`; recorded_at завжди серверний. Для нового reversal/claim не раніше business_date його нового B03 джерела. Не переписує timestamp старого Movement. |

Кожна нова дія має `action,operation_id,code,reason,business_date` та такі поля:

| Action | Додаткові обов’язкові поля | Умовні поля | Роль |
|---|---|---|---|
| `erp_cancel_remaining` | quantity Q>0 | **рівно один** line_id або purchase_id | manager/CEO за доступним source chain |
| `erp_return_supplier` | receipt_id, quantity Q>0 | немає | manager/CEO |
| `erp_return_from_shipment` | shipment_id, quantity Q>0, location_id | немає | manager/CEO |
| `erp_credit_invoice` | invoice_id, basis=`return|commercial`, allocations | source_document_id **обов’язковий лише для commercial**, за return відхиляється як зайвий | CEO |
| `erp_reverse_credit` | credit_id | немає; amount не приймається, reversal повний | CEO |
| `erp_confirm_supplier_claim` | claim_id, amount M≥0, currency, source_document_id | немає | CEO |

`erp_credit_invoice`:

- return allocations: `[{return_id:ID,invoice_line_index:int≥0,quantity:Q>0}]`;
- commercial allocations: `[{invoice_line_index:int≥0,amount:M≥0}]`;
- змішані shapes/повтор однакового `(return_id,index)` або commercial index відхиляються; кількість і ціна відсутні у commercial wire, вони не вигадуються;
- currency, source cost та return-credit amount визначає сервер, клієнт їх не підставляє;
- source_document для commercial/claim: доступний актуальний Document.status=`approved`, оригінальні bytes і SHA перевірені, immutable source snapshot збережений. Погоджувана вимога не стає банківською операцією.

Приклад:

```json
{"action":"erp_return_supplier","operation_id":"9e15f73e-a6fc-4659-9d63-5358cf43b7a5","code":"RET-S-001","receipt_id":123,"quantity":"1.000","reason":"Погоджено фізичне повернення дефектної одиниці","business_date":"2026-09-12"}
```

ID123 тут лише ілюстрація shape. Реальна форма вибирає збережений receipt та показує його PO/lot; fixture бере фактичний ID зі справжнього receipt writer.

## 3. Моделі та межі БД

Шість нових моделей у `erp`; наступна additive migration після фактичного B02. Це конкретні документи/allocations, не generic journal. Усі джерельні FK — PROTECT. Raw CRUD відсутній, admin не реєструє write forms. Append-only rows не можна save/update/delete звичайним командним API; current фізичні баланси залишаються в наявних Lot/Reservation.

| Модель | Поля / джерела | DB constraints |
|---|---|---|
| OrderCancellation | bigint ID, operation_id UUID, payload_hash64, code, line XOR purchase, quantity Q15.3, reason/business_date, actor, Event FK; before/after snapshot | operation_id UNIQUE; code UNIQUE; XOR line/purchase; 0<quantity<10^12 як field capacity (командний допуск не ширший за existing number); FK PROTECT. |
| CancellationRelease | cancellation FK, reservation FK, quantity Q15.3, before_quantity/after_quantity Q15.3 | UNIQUE(cancellation,reservation); quantity>0; before≥quantity; after=before−quantity; before/after≥0. |
| GoodsReturn | bigint ID, operation_id, hash/code, direction supplier/customer, source Movement FK, result Movement OneToOne, quantity Q15.3, source_quantity Q15.3, source_cost M15.2, currency, unit_cost M15.2, allocated_cost M15.2, reason/date/actor/Event, source snapshot | operation_id/code UNIQUE; direction enum; 0<quantity≤source_quantity; source_quantity>0; source_cost/unit_cost/allocated_cost≥0; allocated_cost≤source_cost; currency enum; source Movement≠result Movement; FK PROTECT. source_quantity=abs(source Movement.quantity). |
| SupplierClaim | bigint ID, record_kind pending/confirmation, GoodsReturn FK, nullable parent pending claim OneToOne; nullable operation_id/hash/code for generated pending; agreed_amount nullable M14.2, currency, nullable source Document FK, source snapshot, reason/date/actor/Event | pending: parent/amount/document/operation_id=null; confirmation: всі ці поля non-null, amount≥0. UNIQUE operation_id/code для ненульових значень; parent OneToOne дозволяє рівно одне підтвердження. Обидва rows append-only. |
| InvoiceAdjustment | bigint ID, operation_id/hash/code, kind credit/reversal, basis return/commercial/reversal, Invoice FK, nullable reversed_credit OneToOne self FK, basis snapshot/hash, total M14.2, currency, nullable source Document FK, reason/date/actor/Event | operation_id/code UNIQUE; total≥0; currency enum; credit має reversed_credit=null і basis return/commercial; reversal має reversed_credit non-null та basis reversal; self reverse заборонено. |
| InvoiceAdjustmentLine | document FK, invoice_line_index, SalesLine FK, nullable GoodsReturn FK, quantity Q15.3, amount M14.2, source-budget/cumulative snapshot | index≥0; quantity/amount≥0; return ref → quantity>0; no return ref → quantity=0; conditional UNIQUE(document,index,return) для return та UNIQUE(document,index) для commercial. |

Верхні **точні** межі всіх Decimal полів застосовуються так само, як A07: `Q15.3 < 10^12`, `M15.2 < 10^13`, `M14.2 < 10^12`, scale не губиться. Табличний приклад не зменшує/розширює чинний command limit 1e9; validation перевіряє обидві межі. Нормалізовані JSON числа не перетворюються на float.

Міжрядкові SUM, source kind, узгодженість invoice/return/claim FK, тип попереднього credit і equality валюти перевіряються **під реальним ERP mutex до запису**; Django CHECK не може чесно гарантувати cross-table SUM. Source columns не оновлюються заднім числом. Новий Event може бути призначений новим domain rows до завершення тієї самої outer transaction; committed документ ніколи не лишається без фактичного Event.

Generated pending claim виникає в supplier_return transaction; його внутрішній code — `CLM-`+GoodsReturn UUID/token hex (довжина≤60), а не необмежений prefix user code. У v1 він не має окремого user operation_id. Confirmation має власні operation_id/code і parent pending ID. Якщо потребу в pending code буде реалізовано nullable, UI показує стабільний ID; не підставляти 0 як погоджену суму.

Міграція не backfill старі return, не змінює старі constraints/PK/sequence. Заповнення хоча б однієї нової таблиці блокує lossy reverse **до будь-якого DDL**. Порожній downgrade зберігає всі старі таблиці, IDs, FK і high-water marks. Transfer registry/schema/source digest та clean restore включають фактичні нові таблиці/зв’язки; старе число45 не вважається актуальним складом.

## 4. Спільні кількісні helpers

Новий вузький `erp/balances.py` або еквівалент у corrections module, без дублювання формул:

| Helper | Точний результат | Обов’язкові споживачі |
|---|---|---|
| `cancelled_quantity(line_or_po)` | SUM відповідних OrderCancellation.quantity | admission та всі projections нижче |
| `sales_open(line)` | line.quantity−line.shipped−cancelled; не від’ємне | service reserve/ship/job; queries.plan_line; experience.next_step; B02 importing.live_totals sales_open_value; sales UI |
| `purchase_open(po)` | po.quantity−po.received−cancelled; не від’ємне | service receive; queries material/purchase coverage, replenishment, late_purchases; experience.home purchase_open; B02 importing.live_totals purchase_open_value; PO UI |
| `request_allocated(request)` | SUM(po.quantity−cancelled) для actual request_id | erp.procurement.purchase_source admission; operations.service.compare; request remaining показники |
| `invoice_settlement(invoice)` | §7, Decimal/строки за валютою | service payment cap; queries.snapshot invoices; operations.service.summary; experience.home/next_step; C03 майбутній reconciliation writer |

SourceControlTotals/first_commit_receipt B02 лишаються історичними, тільки **LiveTotals** отримують effective open. `tmp/b02_candidate/source/erp/importing.py` на момент читання має `live_totals()` рядки332/334 з raw quantity−shipped/received; остаточні рядки/імпорт helper уточнити після freeze, функція та семантика відомі. C03 не записує минулі платежі з imported snapshot.

Imported PO: `Purchase.quantity` уже remaining_at_cutover, тому **ніколи не підставляти** approval_snapshot.original_quantity. Еталон original8/pre_received3/currentQ5 → новий receipt2 → cancel1 → open2. Supplier return1 з цього receipt змінює stock, received2/open2 лишаються. request/quote/production imported PO=null; capacity B01 не виникає. Replay B02 не відновлює cancelled частину.

SO cancellation допустиме для підтвердженої line, qty≤sales_open. Незавершена Production на цій line блокує cancellation у v1: WIP/material reserves не редагуються. Звільнити `max(0,held−new_open)` тільки власних Reservation, **новіші PK першими**, створити CancellationRelease на кожну змінену reservation. Lot.quantity та Movement не змінюються. PO cancellation qty≤purchase_open; поточне production_id з незавершеною роботою також блокує його у v1. Supplier receipt чи customer shipment не «скасовуються».

Не ставити PO.status='received' за cancellation. Похідний `effective_status=closed_cancelled|partial|open|received` надається окремо; base status/received лишають історичний зміст. Без cancellation helper повертає точно стару поведінку.

## 5. Фізичні повернення

### Supplier

Source Movement.kind=`receipt`, quantity>0, purchase FK non-null; source lot/item/revision/currency/PO узгоджені. На source lot рівно один positive origin receipt, немає інших positive movements. Новий opening/transfer_in/customer return не підміняє receipt. Якщо provenance неоднозначне або positive adjustment додає сторонній stock — відмова з конкретними залежностями.

`origin_remaining = source.quantity − Σ(abs(all negative Movement.quantity на source lot))`. Включає старі shipment/consume/transfer/adjust/supplier_return. `qty ≤ origin_remaining` і `qty ≤ lot.quantity−reserved(lot)`; сумарні GoodsReturn за source також≤source.quantity. Pending/blocked lot допускає повернення; `usable()` не застосовується як блокування фізичного виходу. Частина, ще фізично в origin lot після часткового transfer, повертається; похідна transfer lot у цей v1 path не входить.

Створити один negative `Movement(kind='supplier_return',purchase=source.purchase,lot=source.lot)` через спільний stock writer + GoodsReturn + pending SupplierClaim. **Нової supplier-owned lot немає**. Receipt/received/PO open/capacity заявки не змінюються; замінна поставка не виникає. Прийняті до B02 cutover товари не мають нового receipt: їх цей path не повертає.

### Customer exact і legacy

Новий `erp_return_from_shipment`: source Movement.kind=`shipment`, quantity<0, line FK non-null; повертається саме його товар/версія/валюта. Ліміт per-source `abs(source.qty)−Σ GoodsReturn.quantity`; додатковий aggregate cap усіх shipment lot+line мінус усіх old/new return Movement для цієї lot+line. Невідома legacy return allocation → conservative refusal exact path до явного mapping, без вгадування FIFO/«останнього відвантаження».

Фізичний результат — нова blocked lot з початковим unit_cost/currency/revision/documents та positive `Movement(kind='return',line=source.line,reference=source.lot.code)`; GoodsReturn містить точний source FK. Цей reference потрібен для спільного ліміту із **незмінним старим `erp_return`**. Старий signature, поля результату, row counts і фінансові дельти не змінюються; новий UI нових повернень вибирає exact source. Ні S, ні invoiced не зменшуються, замінний SO не створюється.

### Оцінка нового return руху

Поточний `move()` за замовчуванням рахує qty×unit_cost; це default усіх old actions зберігається. Для нового exact return сервер обчислює cumulative allocation **джерельного вже записаного cost**:

`allocated_cost = HALF_EVEN(source_cost × cumulative_return_Q / abs(source_Q), 0.01) − prior_return_allocated_cost`.

Використати integer cents / integer Q3 units або точний Fraction; випадковий глобальний Decimal context не впливає. Внутрішній source-aware writer задає cost лише новому Movement в тій самій транзакції; JSON cost_override відсутній. При full return source cost відновлюється рівно до копійки. Example Q0.003/cost0.01, три Q0.001 → costs0.00/0.01/0.00. Source0 cost дозволений.

Lot.unit_cost не ремонтується; raw quantity×unit_cost і ledger cost можуть відрізнятися на rounding. Projections називають обидві бази чесно; це не cash чи COGS reversal. Supplier claim погоджується окремою сумою в валюті PO, не копіює автоматично carrying cost/extras.

## 6. Source invoice budgets та credit allocations

CreditBasis — JSON на новому InvoiceAdjustment, не сьома таблиця. Первинне джерело: незмінні Invoice amount/currency/customer + InvoiceLink.lines (`line_id,quantity,price`) у **початковому ordinal порядку**. Для кожної line raw=`qty×price`; budget_i=`HALF_EVEN(cumulative_raw_i,0.01)−HALF_EVEN(cumulative_raw_(i−1),0.01)`. Сума budgets рівно Invoice.amount. Якщо ні — source mismatch/refusal, жодного history repair. Hash basis і всі фактичні source fields перевіряються при наступному credit. Не брати поточну SalesLine.price/Item.planned_cost/Quote.

Дві raw line0.005 +0.005 → Invoice0.01, budgets0.00/0.01. Нульовий budget є реальним, не округлюється вгору. Invoice line index з UI перевіряється проти source line_id; exact GoodsReturn має direction customer і source.shipment.line_id той самий. Return та Invoice currencies однакові. Не можна кредитувати supplier return в customer Invoice.

Active credit allocations = credits, що **не мають повного reversal**. Для return allocation одночасно перевірити:

1. active allocated quantity цього GoodsReturn + newQty≤GoodsReturn.quantity;
2. active physical credit quantity Invoice line + newQty≤source invoice line quantity;
3. server-derived amount на line: cumulative prorata budget за physical credited quantity мінус вже allocated physical amount; commercial amount не зменшує базову ціну фізичного товару, але зменшує **залишковий monetary cap**;
4. active all credit amount line + new amount≤budget_i; all credit total≤Invoice.amount.

Коли попередній commercial credit не лишає суми для нового full physical credit — відмова з показаним лімітом, не silent clamp. Commercial allocation quantity=0, return FK=null, amount явний і≤невикористаного line budget. Return allocation quantity>0, amount може0.00 через source rounding. Загальний credit total може0.00 для документованої quantity allocation; payment amount>0 лишається окремим правилом.

Первісний кредит створює InvoiceAdjustment(kind=credit), його lines, Event, receipt. Повний reversal створює InvoiceAdjustment(kind=reversal,reversed_credit=original) і позитивні за величиною **точні copies** його allocation amounts/quantities зі знаком, що визначається kind. `reversed_credit` OneToOne не допускає другого reversal; credit може бути тільки kind credit. Reversal не сторнується у v1; нове законне credit рішення після повного reversal створює окремий credit. Source capacity звільняється, всі старі документи збережені.

Customer return до invoice: **gross invoice + окремий credit**. Invoice writer не переходить на net billing: створює рахунок лише за gross shipped−invoiced. Після цього оператор явно вибирає return і invoice line basis. До такого рішення next_step показує unresolved return і не називає оплату/повернення звіреними. Supplier return до customer invoice не кредитує майбутній продаж автоматично.

## 7. Settlement і projections

Єдиний `invoice_settlement()` повертає Decimal/канонічні M-строки:

`effective_credit = credits − full_credit_reversals`;
`net_amount = Invoice.amount − effective_credit`;
`receivable = max(net_amount − Invoice.paid,0)`;
`customer_credit = max(Invoice.paid − net_amount,0)`.

`erp_payment` використовує receivable як cap під старим ERP mutex. Сам writer/manual payload/Event/унікальність reference не змінюються. Credit/reversal не змінюють paid, Finance.Transaction, Salary чи cash. C03 викликає цей самий helper, не віднімає credit вдруге; existing-payment linkage не повторює paid.

Фінансовий еталон: amount123.40/paid100.00/credit24.68 → net98.72, receivable0.00, customer_credit1.28; reversal → receivable23.40. При paid50.00 післяcredit → receivable48.72, payment48.73 відхилено.

Чинні `order_value`, `shipped_value`, `shipped_cost`, `gross_margin` лишають gross семантику. Нові effective/return/credit показники окремі. `invoices.open` тепер receivable; за відсутності credit старі значення буквально ті самі. Не робити «net margin» із gross shipment cost та credit invoices з різними базами; повернутий карантинний stock не означає автоматичне визнання COGS reversal. B02 LiveTotals використовує effective quantities, історичні SourceControlTotals ні.

`erp.queries.snapshot`, `erp.experience.FIELDS/impact/home/next_step`, `operations.service.summary`, `operations.projections` отримують конкретні нові поля/колекції `cancellations,cancellation_releases,goods_returns,supplier_claims,invoice_adjustments,invoice_adjustment_lines`. Усі списки для лімітів/звірки читаються повністю ORM, не з UI обрізаних movements300/events150.

## 8. Approval, lock order та стійкий replay

Короткий POST `/api/erp/preview/` повертає наявний envelope `{id,payload,expires_at,effect,impact}`. Prospective нові IDs з rollback не видаються за збережені; effect має prospective values/джерела, committed IDs лише після confirm. POST `/api/operations/confirm/` body **точно** `{proposal_id:UUID,confirmed:true}`; success200 `{state:'succeeded',erp_event_id,impact,...domain_result}`. Invalid422; forbidden403; source unavailable404; stale/identity conflict409. Ніяких нових execute URL.

Порядок нової мутації:

1. actor/session/role + strict payload; outer atomic;
2. чинний `erp.write_lock()` — перший реальний DB write до читання quantity/money/fingerprint;
3. перечитати actor/permissions і source chain, активні cancellations/returns/credits; перевірити operation receipt;
4. для нового intent перевірити expiry/fingerprint, actual source bytes і всі source bounds; жодного рішення на stale ORM instance;
5. CAS proposal running; source-aware спільні writers; domain rows/release/movement; **один** Event цієї B03 дії; domain linkage, exact impact, immutable canonical receipt; commit разом;
6. будь-яка помилка повністю відкочує всі нові rows, current stock/reserve, Event і receipt. Private files у temporary preview не створюються.

Повтор того самого proposal з receipt повертає перший receipt після поточних role/source перевірок. Новий proposal з тим самим **action+operation_id** і тим самим canonical payload повертає також попередній бізнес-результат: lookup відбувається **до extra Event і до повторного domain writer**. Lookup включає вже завершений source record/Event receipt; original Event.result/actor не переписується. Інший payload під цим ключем →409. Code collision під іншим operation_id →409, не upsert. Uniqueness scoped фактичним model/action, не actor: двоє користувачів не створюють дубль одного source intent. GoodsReturn та InvoiceAdjustment спільні між своїми action kinds, тому hash включає action.

Канонічний перший receipt має фактичний actor/результат; віддача через поточну projection може звузити його для меншого доступу. При тих самих повноваженнях replay literal-equal. Новий ActionProposal може послатися на раніше виконаний canonical receipt, але це не новий domain Event. Наявний `operations.service.execute` і `dispatch` потребують **вузької B03 branch** для цього: не пропускати replay через загальне unconditional Event.create/result.update, що перезапише автора старої операції.

Credit source Invoice/Movement змінюються чинними ERP writers під тим самим mutex. Документи A08 теж під mutex; `verified_document_bytes` перевіряє actual bytes. Сторонні editable Employee/Counterparty refs у payload не додаються; actor і invoice.customer беруться з перевірених джерел. Якщо реалізація додає залежність від current Counterparty fields — застосувати evaluated row locks у B02 порядку, а не покладатися лише на fingerprint. Жодних зовнішніх HTTP/банківських запитів під lock.

Fingerprint включає B03 domain rows, full source state та dataset.as_of; B02 importing.fingerprint базується на розширеному ERP state. Старе preview до cancel/credit/claim/return стає stale. Replay завершеного intent не переобчислює старий receipt за сьогоднішніми quantities.

## 9. Права, UI й точні посилання

Policy явно перевіряє `receipt_id,shipment_id,return_id,claim_id,credit_id,source_document_id` та ланцюги Movement→lot→line/PO→documents; поточний `check_reference` сам цих нових ключів не знає. CEO_ACTIONS доповнюється credit/reversal/claim confirmation. Нові queryset/projections закриті за замовчуванням: жодної невідомої колекції без whitelist.

Manager/observer не отримують credit, claim amount, return carrying cost, source budget/hash JSON чи free-text фінансові причини через snapshot/receipt/events/search/export/assistant/cache. Operational return/cancellation metadata доступні тільки за source chain. Observer не має write. Current access_revision використовується для кешу. Input/reference denied errors не розкривають приховані коди/суми.

Нові кнопки в чинних inspectors: «Скасувати залишок», «Повернути постачальнику» з receipt, «Повернення від клієнта» з shipment, «Кредитове коригування» з Invoice, «Сторнувати кредит», «Підтвердити вимогу». Кожна відкриває існуючий тип controlled dialog з відповідним source/payload, реальним before→after та поясненням cash/no cash. Після commit — конкретний document/lot/claim/credit inspector. Немає декоративної кнопки unsupported atomic replacement.

UI зберігає operation_id і proposal_id після втрати відповіді. Зміна наміру створює новий operation_id тільки до підтвердження або після явного переходу до нової дії; double click не створює його заново. Пока невідомий результат confirm — показано повтор цього самого підтвердження. Source dropdowns показують коди/дати/кількості, wire тільки actual IDs; нульовий claim не підміняє null. Недоступні суми не показуються як0.

## 10. Тести та файли кандидата

Окремі code-only copy/нові own synthetic DB/media. До правки — реальні red outputs. Старі тести/expected records не змінювати. Нові тести лише значущі, інваріанти незалежні від production helpers:

| Група | Конкретний oracle |
|---|---|
| C1 · cancellation | SOQ10/S2/reserves3+4/cancel5 → open3/released4 (newest first), physical unchanged; POQ10/R4/cancel6→open0, B01 newPO6 дозволено; WIP/чужий reserve/overcancel refusal. |
| C2 · imported PO | Source8/pre3/current5, receipt2/cancel1/return1 → received2/open2/stock−1; B02 source/first receipt bytes незмінні, replay no repair; opening/precutover return відхилено. |
| R1 · supplier | Partial receipt4/return1 → gross received4, stock3, source receipt exact, pending claim amount null, нуль Invoice/paid/Transaction; reserved/foreign/source ambiguity refusal. |
| R2 · customer/legacy | Old return signature/results проходять; exact source має per-source+aggregate cap; old unmapped не дублюється новим path; new blocked lot, S/invoiced незмінні. |
| R3 · rounding | SourceQ0.003/cost0.01 → три0.001 costs0.00/0.01/0.00; повна сума0.01, усі source fields незмінні; низький/інший Decimal context не змінює oracle; три валюти. |
| F1 · invoice basis | Дві raw0.005 → budgets0.00/0.01; source amount mismatch відхилено; source line index/FK/currency перевірені; zero-valued physical allocation не вигадує копійку. |
| F2 · settlement | 123.40/paid100/credit24.68→receivable0/customer_credit1.28, full reversal→23.40; paid50 cap48.72; cash/Salary/первісний Invoice/Event незмінні. |
| F3 · source caps | Два credits на той самий return/invoice line, commercial+return, multi-invoice line, repeated reversal; aggregate source cap ніколи не перевищено, ambiguity refusal. |
| I1 · replay | Same proposal literal receipt; новий proposal/same action+operation_id той самий domain receipt/Event ID; змінений payload409; stale after cancel/credit; original actor/result не переписано. |
| I2 · atomicity | Справжня SQL trigger error після release/return/credit rows до receipt → повний rollback; retry same intent створює один результат. Не мокати внутрішній writer. |
| I3 · concurrency | Real HTTP pairs усіх6 нових actions; cancel↔ship/receive/reserve/B01allocate; supplierreturn↔transfer/reserve/return; credit↔payment/credit/reversal; one accepted outcome або controlled conflict, без duplicate money/stock. |
| P1 · scope | Кожна роль через прямий API/admin route inventory, hidden source, revoked document, snapshot/receipt/export/assistant/cache; forbidden monetary/free text canaries не виходять. |
| M1 · migration/restore | Additive empty/legacy DB, old IDs/constraints/bytes unchanged; filled-new-table reverse refusal beforeDDL; transfer/cleanrestore з усіма6 моделей та source FK/costs. |
| U1 · UI | Кліки source→preview→confirm→receipt, keyboard/Escape, 390/768/1440, zoom200%, double click/повільна мережа. Недоступний браузер = НЕ ЗАПУЩЕНО. |

Для gate5 **усі 84 old methods/89 old records/26 old actions збережені** плюс фактично frozen B02 explicit coverage. Додати шість action names у reviewed manifest, по реальному HTTP-pair за EUR/UAH/USD для кожної (мінімум18 нових pass records), exact delta oracle та кожні додаткові conflict tests явними IDs. Schema equality = frozen old actions + B02 + шість B03, жодного dynamic discovery замість exact manifest. Щонайменше 6 нових required methods, але фактичні додаткові concurrency methods теж фіксуються. Gate4 існуючі шляхи не вилучаються; нові read routes, якщо потрібні inspectors, додаються з реальною матрицею доступу.

Пропоновані файли кандидата: `erp/corrections.py`, `erp/balances.py`, `erp/test_corrections.py`, `erp/test_correction_concurrency.py`, additive migration, synthetic fixtures. Touched: erp models/service/procurement/queries/experience, B02 importing.live_totals, operations service/projections, policy, exact access/concurrency manifests, A07 transfer registry за потреби. UI/build/docs root інтегрує тільки після freeze API й review. Жодних змін finance Salary/Transaction writers для B03.

Після scoped green — незалежний source/evidence review, root canonical integration, повний verify, evidence/B03, PROGRESS/CHANGELOG/PARAMETERS, один B03 commit. Відомі A09/A10/A11/PG/Windows gates лишаються фактичними червоними/незапущеними; нова регресія не ховається серед них. Повна бухгалтерія, реальний D01 і весь MVP не заявляються готовими за цим synthetic v1.

## 11. Gate 6 та джерела

Синтетичний end-to-end: заявка/quote → B01 PO → partial receipt → **supplier return** → quality approval реального залишку → transfer → справжній customer SO/reserve/shipment → AR Invoice тільки за shipment → C03 incoming statement/звірка → C01 доручення з результатом → CEO source report. Claim окремо; AP invoice/cash refund не вигадуються. Реальний D01 може вимагати AP як окрему майбутню частину.

Джерела консолідації:

| Файл | SHA-256 прочитаного документа |
|---|---|
| tmp/B03_READY_PLAN_UA.md | `cf999c9f112ed77044a7d5fbf6da6fffd742786869329273c228cfdd21fd93ff` |
| tmp/B03_PLAN_REVIEW_UA.md | `41cd0e911f312b9f0ecf56dae13647fca15fc5be849d6d2ae6712a9c7520c7f3` |
| tmp/B02_IMPLEMENTATION_CONTRACT_UA.md | `055ab9afb15ff95a2a5ecc0fcb2cbc1f71e0fcb413a8cba9ce82bf4394a5aa66` |
| tmp/C03_READY_PLAN_UA.md | `85e0470ce01905dc0ed7c5160232d5fc15fb39c875d74ac822afddca7f14cf4e` |

Остаточні B02 candidate hashes ще не заморожені; документ не видає його current source read за прийнятий build. Окремий B03_PLAN_REVIEW містить точні SHA канонічних source файлів c71e601. Root явно прийняв R1–R8 та уточнив, що universal atomic replacement не є обов’язком цього B03.
