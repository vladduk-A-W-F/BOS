# B03 · підтверджені уточнення UI wire

12.09.2026. Основний контракт — `tmp/B03_WIRE_UI_UA.md`. Нижче точні додаткові рішення, отримані від backend автора a08_upload_review та root під час незалежного source review; це не HTTP acceptance.

- Receipt `erp_cancel_remaining.cancelled_quantity` — кумулятивна скасована кількість джерела після цього погодження. `cancellation.quantity` — кількість саме нового документа. `effective_open` у replay є історичним результатом першого виконання, не новим поточним станом.
- `lines/purchases.return_visibility` = `complete` або `restricted`. За прихованої історії `returned_quantity` і `return_allocated_cost` можуть бути null. UI не показує null як нуль і не відновлює суму з неповного списку.
- `source_movements` включає всі дозволені receipt/shipment та exact `result_id` видимих GoodsReturn. Поля як у початковому wire. Це bounded source/history read, а не довільний необмежений журнал.
- `correction_events` включає лише Event IDs, пов’язані з видимими B03 cancellation/return/claim/adjustment. CEO — той самий Event shape `id/action/role/created_at/payload/result`. Non-CEO — лише operational metadata `id/action/role/created_at`; фінансових подій немає, навіть коли operational факт claim confirmation видимий.
- UI resolution `find(events,id)` може читати `correction_events` після звичайного `events`. Для відсутнього за поточними правами financial event кнопка не показується як робоче посилання.
- Pending ID-only queue має стабільний key за user/mode/role. `access_revision` залишається серверною перевіркою поточних прав; зміна revision не ховає невідомий намір.
- Повторний preview використовує той самий operation_id, а всі попередні proposal_id лишаються до фактичного receipt. Після reload повторне введення явно позначено як відновлення того самого наміру. Financial payload не кешується.
- Receipt settlement показується окремо: чотири поля під «Результат цього погодження». Поточні amount/paid/effective_credit/net_amount/receivable/customer_credit мають окремий заголовок «Поточний стан рахунку». Квитанція не доповнюється пізнішою оплатою.
