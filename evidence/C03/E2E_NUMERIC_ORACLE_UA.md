# Gate 6 · незалежний числовий еталон EUR

12.09.2026. **Пропозиція еталону; застосунок, сценарій gate 6, БД, міграції й браузер не запускалися.** Виконано лише 12 незалежних арифметичних assertions стандартними `Decimal` (precision40) і `Fraction`, без імпорту BoS/Django. Всі задані root числа підтвердилися; підгонки під production helpers немає.

Машинний draft: `tmp/e2e_expected_draft.json`, SHA-256 `10e8b6e671db8e2656683ebfa16bfabc1a75989543e353b6c37d17e43e27616f`. Це не встановлений `tests/e2e_expected.json` і не evidence виконаного тесту. C01/C03 implementation wire ще не frozen: перед реалізацією зв’язати адаптер з фактичним API, зберігши числові/source/replay очікування.

## 1. Сценарій і часові межі

Нова порожня синтетична компанія; `as_of=2026-09-12`, EUR, без ПДВ/податків/FX. Після міграцій створити лише потрібних користувачів/працівників, постачальника/клієнта, одну buy номенклатуру, два склади та три source документи. Не запускати загальний demo seed із додатковими історичними замовленнями. **Baseline counts** фіксується після цих довідників і трьох документів, перед заявкою/quote.

Заявка10 → quote10×1.23+delivery0.40 → B01 PO10 → receipt4 → supplier return1 → quality approval реальних3 → transfer2 → справжній customer SO2×2.34 → confirm/reserve/ship2 → Invoice4.68 → CSV source/import → явна reconciliation4.68 → C01 Task/responsible/deadline/result → CEO report.

Погоджена PO due_date/original_due=`2026-09-20`, request.required_by=`2026-10-01`; quote valid_until=`2026-10-01`, lead_weeks1, calculated arrival=`2026-09-19`. Фактичне погодження9/20 задається явною synthetic manager attestation. Invoice due9/25; Task deadline9/15. Recorded timestamps лишаються реальними серверними; не backdate їх для картинки. OTD, який нинішній код рахує з Movement.created_at, не входить у цей фінансовий oracle як «100%» за синтетичною датою.

## 2. Незалежна арифметика

| Величина | Формула, без функцій BoS | Точний результат |
|---|---|---:|
| PO загалом | 10×1.23+0.40 | 12.70 EUR |
| Ціна одиниці складського обліку | 1.23+0.40/10 | 1.27 EUR |
| Receipt4 | 4×1.27 | 5.08 EUR |
| Supplier return1 | 5.08×1/4 | 1.27 EUR |
| Transfer2 | 2×1.27 | 2.54 EUR у кожному з двох transfer movements |
| Shipment2 | 2×1.27 | 2.54 EUR |
| Customer invoice | 2×2.34 | 4.68 EUR |
| Gross difference | 4.68−2.54 | 2.14 EUR |
| PO gross remaining | 10−4 | 6.000 шт. |
| PO open value | 6×1.27 | 7.62 EUR |
| Receipt source lot final | 4−1−2 | 1.000 шт. / 1.27 EUR |
| Transfer/shipped lot final | 2−2 | 0.000 шт. / 0.00 EUR |
| Звірена оплата | 4.68−4.68 | receivable0.00 EUR |

Додаткові незалежні рівності: `5.08−1.27−2.54=1.27`; `12.70−5.08=7.62`; загальний фізичний stock `4−1−2=1`. Fraction значення: unit127/100, receipt127/25, return127/100, shipment127/50, invoice117/25, gross107/50. Цей fixture не має rounding remainder: source-cost B03 та нинішній unit-based receive/ship дають ті самі суми. Ширші half-cent/fractional tests B03 лишаються окремими.

## 3. Точні складські рухи

| Alias | kind | Lot code | Quantity | Cost | Джерело |
|---|---|---|---:|---:|---|
| receipt_movement | receipt | E2E-RCV-001 | +4.000 | 5.08 | Purchase E2E-PO-001 |
| supplier_return_movement | supplier_return | E2E-RCV-001 | −1.000 | 1.27 | GoodsReturn → саме receipt_movement |
| transfer_out_movement | transfer_out | E2E-RCV-001 | −2.000 | 2.54 | transfer reference E2E-XFER-001 |
| transfer_in_movement | transfer_in | E2E-XFER-001 | +2.000 | 2.54 | original lot reference E2E-RCV-001 |
| shipment_movement | shipment | E2E-XFER-001 | −2.000 | 2.54 | SalesLine of E2E-SO-001, reference E2E-SHP-001 |

Саме **5** нових Movement і **2** Lot. Transfer не додає власний stock/value: пара −2/+2, її costs не сумуються як нова витрата. `Σ quantity по lot = поточна lot.quantity`; origin lot1, shipped lot0. Reservation створений на transferred lot2, після ship quantity0, рядок зберігається. Усі фізичні залишки/резерви невід’ємні. Обидві lot після quality/transfer approved, з точним certificate source; origin available1, shipped available0.

PO.received **4.000 назавжди після receipt**, незалежно від return1. PO quantity10, cancelled0, open6, statuspartial. B01 request allocation10/remaining_unallocated0; повернення не відкриває ще1 до закупівлі. Pending supplier claim amount=null; carrying cost1.27 не підставляється як підтверджене відшкодування. AP invoice, supplier payment/refund та replacement incoming не створюються.

## 4. Sales, Invoice, bank і Task

SalesOrder `E2E-SO-001`: одна line item `E2E-ITEM-001`, quantity2, price2.34 EUR, shipped2, invoiced2, open_delivery0. Base statusconfirmed, не вигаданий persisted done. Invoice `E2E-INV-001` за цим фактичним shipment: amount4.68, paid спершу0, після reconciliation4.68, credit0, open0, customer_credit0. Shipment/InvoiceLink history не редагується після оплати.

CSV — один явний рядок `(source_system=synthetic-bank, account_ref=E2E-EUR-ACCOUNT, external_id=E2E-BANK-0001)`, booking date9/12, in4.68EUR, customer external code E2E-CUSTOMER-001, exact Invoice reference E2E-INV-001. Після **import, до reconcile** є1 StatementLine, але0 Transaction/payment і paid0/open4.68. Далі create_transaction + new_payment allocation дають рівно1 Transaction,1 erp_payment Event,1 StatementAllocation; allocated4.68/unallocated0.

Одна Transaction: in/customer,4.68EUR, date9/12, customer FK рівно Invoice.customer, source line OneToOne, actor=verified CEO. Finance FinancialIntent та `transaction.create` AuditEvent по1. Customer code mapping заданий fixture явно до реального counterparty ID, не виведений з назви/суми/дати. Один allocation key UUID4 зберігається для всіх повторів. Proposed reference `STMT-417a95373de84bf5b99c638cefcb96f0` ≤60 символів; якщо frozen C03 обере інший namespace, це треба явно узгодити до встановлення oracle, не підміняти expected після падіння.

Task створює CEO, виконавець — явний Employee FK менеджера Марії Еталонної (Employee.user → username `bos-e2e-manager`), linked SalesOrder `E2E-SO-001`, request_code `E2E-REQ-001`, deadline9/15. Статус active → done, completion саме manager, результат і reason задані literal у JSON. Результат підтверджує shipment2 та відкриті PO6/pending supplier claim; не містить недоступної менеджеру банківської інформації й не імітує автоматичну оплату. Task completion дає0 stock/payment/Transaction дельти. Новий legacy assignee='' і stable FK, done priority=null за C01 proposed contract; ці поля треба остаточно freeze перед gate6.

## 5. Counts та повтори

Від baseline після довідників/трьох джерел:

| Модель / журнал | Δ |
|---|---:|
| Document (CSV) / ProcurementRequest / SupplierQuote / Purchase | +1 кожний |
| Lot / Movement | +2 / +5 |
| GoodsReturn / pending SupplierClaim / Inspection | +1 кожний |
| SalesOrder / SalesLine / Reservation / Invoice / InvoiceLink | +1 кожний |
| StatementImport / StatementLine / StatementAllocation | +1 кожний |
| Transaction / FinancialIntent / Task | +1 кожний |
| ActionProposal | +14 |
| ERP Event | +13 |
| AuditEvent | +3: transaction.create, create_task, update_task |
| Cancellation/Release/Credit/Reversal/Production/Salary/extra Item/Location | 0 |

ERP Event13 = purchase,receive,return_supplier,quality,transfer,order,confirm_order,reserve,ship,invoice,statement_import,statement_reconcile **по1** + child erp_payment1. Нового erp_payment немає в user proposals: це підоперація однієї погодженої reconciliation. Task2 використовують AuditEvent, не ERP Event. Bootstrap Item/Locations можуть мати свої події до baseline, вони не губляться й не додаються вдруге до цих дельт. Для майбутніх implementation audit-доповнень спочатку явно зафіксувати контракт, а не динамічно прийняти будь-який фактичний count.

На кожну з14 погоджуваних дій:1 новий proposal,1 first confirm,1 immediate same-ID replay. Після завершення всього сценарію ще1 late replay усіх14 у початковій actor/session. Разом **42 confirm HTTP calls**,14 proposals, без додаткових domain effects. Late replay важливий: PO/lot/invoice/Task після першої дії уже змінені іншими законними діями, але receipt повертається первісний і не ремонтує їх назад.

Порівнювати повні business/source snapshots: old Event/Movement/FK, domain rows, Task history, FinancialIntent, receipt, document bytes. Допустимо виключити тільки session/auth activity та службову `erp_write` revision; не money/stock/history. Число14 не включає requirement/quote raw create з їх unique codes, upload/review документів чи bootstrap; для них окремо перевірити реальні результати й незмінність source.

## 6. Сталі коди, bytes та збереження джерел

JSON містить literal UTF-8/LF тексти трьох source TXT та одного CSV, byte lengths і SHA. В future fixture записати саме ці bytes, upload справжнім приватним механізмом, download оригіналу й порахувати його фактичний SHA. `Document.text`, OCR чи внесений у таблицю очікуваний checksum не підміняють actual bytes proof.

| Документ | SHA-256 UTF-8/LF оригіналу |
|---|---|
| E2E-SPEC-001 A | `e50f628c1ec5a969f42300032b240815c6f3ae627db0723497f1104a6cce34a8` |
| E2E-QUOTE-DOC-001 A | `6e23b8419214b509ef1a8e97dcc5bb71543c4e841c0eddd078f5d18403795406` |
| E2E-CERT-001 A | `fac5f85a2f2766cb1a1f5d437464556e5e88b2d461ae2b963915a082c0adb978` |
| E2E-STMT-001 revision1 | `abc40883040bef29f0cd6bd3868026fa5f3734f6ac7d957e10e1fb75365c9869` |

Spec/quote/certificate operational; bank source CEO-only і новий code, без успадкованого management доступу. Всі джерела approved. Quote wire має рівно дозволені нинішнім `quote_create` terms: зайвий `tax_basis` там зараз відхиляється; excluding_VAT уже зазначено у source/requirement/B01 snapshot. Це відмінність формату, не зміна суми.

Receipt ID, Shipment ID, Proposal ID, GoodsReturn/Claim ID, Task ID отримуються з committed response й конкретних FK/kind/reference; числові PK не закодовуються. Employee та Counterparty **не мають поля code**: alias maps зв’язують actual returned PK; Employee додатково має unique User.username. Task теж без code — використовувати receipt.task_id. Lookup за source code має знайти рівно один запис, неоднозначність — failure.

Checkpoint source history після B01 approval і після receipt: Request/Quote/documents/approval_snapshot/original_due незмінні; receipt Movement всі поля/ID незмінні після return. Після invoice зберігаються amount/currency/customer/due_date/InvoiceLink і shipment; змінюється лише paid під час реальної reconciliation. Робочі db.sqlite3/BoS_Demo.sqlite3 не відкривалися цим arithmetic prep; майбутній root harness має довести before/after SHA обох та працювати лише на новій власній DB/media.

## 7. Що повинен показати звіт керівника

Клікабельні джерела: Request/Quote/PO → receipt/return/transfer/shipment → SO/Invoice → StatementLine/Transaction/payment Event → Task/history. Числа: shipment revenue4.68, shipment cost2.54, gross difference2.14, paid/reconciled4.68, receivable0, stock1/value1.27, PO open6/value7.62, supplier return1/carrying1.27, claim agreed amount=null, task done1.

Cash in4.68/out0/net movement4.68 — **не банківський closing balance**, бо початкового банківського залишку немає. Supplier claim не підтверджений, PO ще має6 до приймання: компанійний процес цілком не завершений. AR оплата звірена, конкретна поставка2 і Task завершені. AP debt, refund, чистий бухгалтерський прибуток, гарантія строку постачальника й реальне клієнтське приймання не заявляються.

EUR/USD/UAH broader suites, fractional credits/returns, cancellation, B02 cutover, C01 lifecycle/roles, C03 partial/unrecognized/replay, всі11 gates залишаються окремими обов’язковими перевірками. Цей один EUR oracle їх не замінює.
