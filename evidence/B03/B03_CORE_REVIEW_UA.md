# B03 — незалежний review робочого core checkpoint

12.09.2026. Перевірений checkpoint `CORE_REVIEW_CHECKPOINT.json` SHA `26b46ba05f932dd147227abbfef2b837f1cb84bab195cb4d3266740e02a88aa4`; усі15 зазначених source SHA збіглися при читанні. Це стабільний core, але ще не фінальний freeze тестів/gates. Канонічний checkout і кандидат не змінено, додаткових тестів/серверів/БД не запускалося.

**Висновок checkpoint: усі шість writer paths прочитано; є дві конкретні незакриті projection-помилки нижче. Остаточного приймання B03 немає до виправлення й named evidence/freeze.**

## Підтверджено за source

| Дія | Перевірена поведінка |
|---|---|
| cancel_remaining | XOR line/PO, positive Q, confirmed SO, current Q−executed−cancelled, WIP refusal; власні резерви newest-first через спільний release writer, CancellationRelease before/after. Gross quantity/shipped/received, stock і Movement не переписуються. Imported PO використовує тільки current Purchase.quantity. |
| return_supplier | actual positive receipt/PO та lot/item/revision/currency; єдиний positive origin, усі negative movements і current free stock обмежують Q. Negative source-cost Movement через спільний writer, append-only GoodsReturn, pending claim amount=null. Received/cash не змінюються. |
| return_from_shipment | actual negative shipment/line і відповідні item/revision/currency; per-source cap плюс old/new lot+line aggregate cap; legacy unmapped return відхиляється. Нові blocked lot/positive return Movement, reference=source lot.code зберігає старий erp_return cap. |
| credit_invoice | immutable InvoiceLink ordinal basis, cumulative raw budgets із точним amount equality; actual customer GoodsReturn+line+currency, global return Q cap і invoice-line Q cap, physical prorata amount та спільний commercial monetary cap. Немає silent clamp/автоматичної оплати. |
| reverse_credit | тільки первісний credit, один full reversal через OneToOne; дата не раніше credit; exact allocation copies, не reprice. Active credit фільтрує сторновані документи; paid/Invoice/старі allocation rows незмінні. |
| confirm_supplier_claim | тільки pending supplier return, одна confirmation через parent OneToOne; amount≥0, same currency, business_date≥pending; approved newest actual-byte source Document. Окремий confirmation row, без Transaction/Salary/refund. |

`money()` використовує точний Fraction, integer-cent HALF_EVEN та Decimal tuple. `return_cost()` = rounded(source cost×cumulative returned Q/source Q)−prior allocated cost у localcontext50. Credit basis budgets отримуються з первісної ціни/кількості ordinal InvoiceLink, сума має збігатися до копійки; поточні SalesLine.price/Item.planned_cost не використовуються. Перевіряються вже збережені basis/hash попередніх credits/reversals.

`invoice_settlement()` дає effective_credit/net/receivable/customer_credit; чинний payment writer використовує receivable як cap під ERP mutex. Shared sales_open/purchase_open/request_allocated інтегровані у reserve/ship/job/receive, B01 allocation і B02 live totals. Старі gross totals та B02 source totals/receipt збережені.

## Replay, authorization та history

Clean strict шести action shapes, canonical UUID4 і закриті Decimal strings застосовано до dispatch. Canonical dispatch бере ERP write_lock, actor перечитується; correction replay виконується до нового Event та domain writers. Новий proposal із тим самим canonical intent може повернути старий receipt до expiry/fingerprint; changed payload409. Early return обходить стару unconditional Event.result update, первісний actor/receipt не перезаписується.

Outcome GET `/api/erp/corrections/outcome/` має рівно action+operation_id, rejects duplicate/unknown query keys, тільки шість дій. Exact domain row/Event action lookup, current role, stored payload, domain source scope, projected receipt. Payload не віддається; missing/hidden404unknown не є доказом відсутності commit. Нових proposals/events цей read endpoint не створює.

За checkpoint виправлено historical GoodsReturn visibility: current source/result Movement плюс snapshot documents мають бути доступні. Replay перевіряє queryset доменної моделі; event projection перевіряє не лише input, але й result IDs. Null/restricted aggregate більше враховує hidden exact-return domain. NonCEO return/claim receipt має явний whitelist; invoice adjustments/lines порожні, source budgets/allocated costs/financial reasons не виходять.

source_movements — повні scoped receipt/shipment плюс result IDs тільки видимих GoodsReturn; correction_events — тільки видимі B03 ledger-linked Event IDs. Це не повний event dump. Старі300movements/150events limits не збільшуються.

## Закриті review findings до checkpoint

Фактичний initial-red:4HTTP failures422 «unknown ERP tool», first-after4/4. Окремі review red показали historical source omission, занулення existing supplier lot у preview, ambient Decimal вплив на HTTP gross snapshot і cancelled PO у BOM ETA. `review-green.log` SHA `5ce2c211ede62937ba0c88dd30211f2cd6cc77058d9d465e3c5c0ab311a2b26a`:8/8,5.350s. Historical source test справді змінює current attach до D2, відкликає D і перевіряє source-visible lot/hidden return+claim+events+outcome+replay. Low-context test виконує HTTP preview/confirm/snapshot із prec6/DOWN та точним cost1233999.99; caller context збережено. Supplier preview зберігає existing lot_id, нові domain/movement IDs null. BOM planning виключає fully cancelled PO з dates.

Окрему no-action підказку customer_credit>0 додано до CEO next_step; старе «оплати звірено» тепер не підміняє необхідність рішення щодо такого залишку. Потрібна відповідна assertion у final tests.

## Конкретні блокери checkpoint, передані автору

1. **Дубль Event у nonCEO snapshot.** `operations.projections.snapshot` обходить `events + correction_events`; якщо нова B03 подія входить до обох, вона двічі потрапляє до проміжного events. Повернений `data.events` фільтрує originalIDs, але не dedup. Мінімум: кожний original ID один раз із початковим порядком; source regression — actual return і унікальні event IDs. Це projection bug, не дубль DB Event.
2. **NonCEO next_step залежить від закритого credit state.** `unresolved_returns` читає active InvoiceAdjustmentLine без role scope, а `next_step` викликає його перед nonCEO branch. Для того самого фізичного повернення manager/observer відрізняє pending credit від completed credit через зміну підказки. Мінімум: nonCEO operational next_step не залежить від financial allocations; CEO зберігає точну credit resolution логіку. Так само не читати hidden GoodsReturn financial state після historical revocation.

## Що має довести фінальний кандидат

Наявні8tests не доводять весь контракт. Автор ще додає погоджені named regressions: усі6actions (включно claim confirmation), cumulative cents0/.01/0 у3currency, credit zero-budget/commercial+return/multi-source caps, payment/reversal caps, imported-current-Q/source immutable replay, SQL rollback, role matrix/history>300, actual concurrency pairs, populated reverse/typed53 і стару сумісність. Цей review не вимагає нових загальних функцій чи optional full/A09/browser probes. Фінальний висновок звірятиметься з actual logs та exact frozen SHA; root canonical full B03 окремий.

## Root additive restore fixture — source-only consensus

Прочитано `tmp/b03_restore_fixture.py` і фактичний B02 template. EUR PO unit1.23+.40/5=1.31, receive2→supplierreturn1→claim1.31→cancel1 дає currentQ5/R2/cancel1/open2. SOQ2.5/reserve2.5/cancel.5/release.5/ship1/invoice4.12/customerreturn.5 дає returncost1.17,credit2.06,fullreversal4.12receivable. Ledger counts2/1/2/2/2/2 і7 source-intent receipts правильні. Fullsnapshot equality до/після cleanrestore й7replay через newproposals/outcome збережені. Wire/semantic mismatch у цьому fixture не знайдено; його actual run ще не виконано при цьому читанні.

PG/Windows/CI/browser/upgrade/E2E межі цим review не приймаються. B02 mandatory full22 gate8 green31/31 описано окремим addendum; попередню транспортну нестабільність не оголошено виправленою.
