# B03 · узгоджений wire для root UI

Кандидат ще red; shapes нижче цільові й незмінні без повідомлення root/UI/reviewer. Mutation actions/fields — рівно B03_IMPLEMENTATION_CONTRACT_UA.md3717… (шість дій). Нового write URL немає.

## Read / approval

- Snapshot: `GET /api/erp/snapshot/`.
- Preview: `POST /api/erp/preview/` з action payload; відповідь `{id,payload,expires_at,effect,impact}`.
- Confirm: `POST /api/operations/confirm/` з `{proposal_id,confirmed:true}`.
- Outcome: `GET /api/erp/corrections/outcome/?action=erp_…&operation_id=<canonical UUID4>`; лише шість B03 actions, невідомі query keys відмова422.
- Outcome200: `{state:"succeeded",action,operation_id,receipt:<той самий дозволений canonical receipt>}`. Не містить payload, не створює proposal/Event, не запускає writer.
- Outcome404: `{state:"unknown",receipt:null}` однаково для absent/hidden. **Не означає, що commit не відбувся**; queue/proposal_id/operation_id зберігаються. Недозволена поточна роль/action403. Новий login сам не дозволяє повторити чужий POST; він дозволяє read lookup за поточними правами.
- Same action+operation_id/same normalized payload через новий proposal повертає перший domain receipt без нового Event. Чужий changed payload409.

## Числа / статус

Q — канонічні рядки3dec, M —2dec, UUID string, IDs integer. Gross поля quantity/shipped/invoiced/received/amount/paid не переписуються. Null ніколи не показувати як0. Previeweffect має `prospective:true`; майбутні document/movement/lot IDs —null, source IDs лишаються справжніми. New-row impact має `id:null,prospective:true`; before/after чинних source IDs збережені.

## Snapshot поля

| Collection | Поля, доступні всім дозволеним source roles | Додатково тільки CEO |
|---|---|---|
| lines (чинна) | cancelled_quantity,open_quantity,returned_quantity | return_allocated_cost |
| purchases (чинна) | cancelled_quantity,open_quantity,returned_quantity,effective_status | return_allocated_cost |
| invoices (чинна) | існуючий обмежений whitelist | amount,paid,open,effective_credit,net_amount,receivable,customer_credit,credit_basis,credit_source_error |
| source_movements (НОВА повна scoped collection) | id,kind,lot_id,lot_code,item_id,location_id,line_id,purchase_id,quantity,revision,currency,reference,created_at | cost,unit_cost |
| cancellations | id,operation_id,code,line_id,purchase_id,quantity,business_date,created_at,event_id | actor_id,reason,before_snapshot,after_snapshot |
| cancellation_releases | id,cancellation_id,reservation_id,quantity,before_quantity,after_quantity | — |
| goods_returns | id,operation_id,code,direction,source_id,result_id,lot_id,source_lot_id,line_id,purchase_id,quantity,source_quantity,currency,business_date,created_at,event_id | actor_id,reason,source_cost,unit_cost,allocated_cost,source_snapshot |
| supplier_claims | id,record_kind,return_id,parent_id,code,currency,business_date,created_at,event_id,confirmed_by_id | actor_id,operation_id,reason,agreed_amount,source_document_id,source_snapshot |
| invoice_adjustments | **[] для manager/observer** | id,operation_id,code,kind,basis,invoice_id,reversed_credit_id,basis_snapshot,basis_hash,total,currency,source_document_id,source_snapshot,reason,business_date,created_at,actor_id,event_id |
| invoice_adjustment_lines | **[] для manager/observer** | id,document_id,invoice_line_index,line_id,return_id,quantity,amount,source_snapshot |

`source_movements` містить усі дозволені Movement.kind receipt/shipment, не обрізані300. Для supplier обирається receipt, для customer shipment; UI не обчислює eligibility за цим списком: authoritative preview перевіряє full history/stock/reserve/source caps. Звичайна collection movements зберігає старі limits/shape.

`effective_status` PO: received якщо gross fully received; closed_cancelled якщо open0 іcancelled>0; partial якщоreceived>0 таopen>0; open інакше. Base status лишається старим. Supplier return не збільшує open.

`confirmed_by_id` pending claim — ID confirmation абоnull; confirmation row має parent_id pending. Pending agreed_amount=null (CEO бачить null), не0. Manager бачить факт вимоги/підтвердження без суми/причини/джерельного документа.

`credit_basis` CEO invoice: `{invoice_id,code,amount,currency,customer_id,lines:[{index,line_id,quantity,price,raw_value,budget}],hash}`. Ordinal index походить саме з InvoiceLink.lines. Якщо джерельний amount/shape не відповідає джерелу, `credit_basis:null`, `credit_source_error` пояснює відмову, без виправлення історії. Уже погоджені basis перевіряються за тим самим snapshot/hash. Нульовий budget0.00 допустимий.

## Committed receipt

Спільні: `{state:"succeeded",action,operation_id,erp_event_id,actor_id,actor_role,impact,...}`. Для non-CEO actor_id та довільні фінансові вкладення не повертаються; metadata action/operation_id/event_id зберігаються. Impact whitelist застосовується знов за поточною роллю/source chain.

| Action | Domain result |
|---|---|
| cancel_remaining | cancellation_id,line_id абоpurchase_id,cancelled_quantity,effective_open,released:[{reservation_id,quantity,before_quantity,after_quantity}] |
| return_supplier | goods_return_id,receipt_id,movement_id,lot_id,claim_id,quantity,currency; CEO такожallocated_cost |
| return_from_shipment | goods_return_id,shipment_id,movement_id,lot_id,quantity,currency; CEO такожallocated_cost |
| credit_invoice | invoice_adjustment_id,invoice_id,total,currency,settlement,allocation_ids |
| reverse_credit | invoice_adjustment_id,invoice_id,reversed_credit_id,total,currency,settlement,allocation_ids |
| confirm_supplier_claim | supplier_claim_id,parent_claim_id,goods_return_id,amount,currency |

settlement = `{effective_credit,net_amount,receivable,customer_credit}` (M strings). Receipt не містить editable source snapshot або payload. Snapshot inspector дає read-only історичні деталі за документом. Усі фінансові дії/receipt лишеCEO; operational receipt manager отримує тільки IDs, Q, currency та дозволений impact.

Для переходів: cancellation_id→cancellations; goods_return_id→goods_returns; claim_id/supplier_claim_id→supplier_claims; invoice_adjustment_id→invoice_adjustments; movement_id→Movement; lot_id→lots. Source receipt/shipment inspector використовує source_movements, якщо запис старший за300 останніх movements.

Невиконані в цьому v1: atomic commercial replacement, AP/cash refund, автоматична заміна поставки, netCOGS/margin та бухгалтерський close. UI не додає відповідних кнопок.

## Уточнення доступних історичних посилань
- `source_movements`: усі видимі receipt/shipment та точні `result_id` видимих GoodsReturn; та сама схема полів. Це не загальний dump рухів.
- `correction_events`: повна колекція тільки Event IDs видимих B03 документів. CEO отримує чинну Event-схему; manager/observer тільки `{id,action,role,created_at}` операційних дій. Фінансових events у слабших ролей немає.
- `return_visibility`: `complete` або `restricted`. Якщо будь-яке історичне джерело повернення недоступне, `returned_quantity` та `return_allocated_cost` дорівнюють null; це не нуль.
- Receipt `cancelled_quantity` — накопичений підсумок. `cancellation.quantity` — кількість конкретної дії. Supplier-return preview зберігає існуючий source `lot_id`.
