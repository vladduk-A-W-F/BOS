# C01 · ранній wire checkpoint

Прийнятий контракт C01_IMPLEMENTATION_CONTRACT_UA.md збережений. Це API для паралельного UI; кандидат у tmp/c01_candidate/source, canonical root не змінюється.

## Запис

POST `/api/operations/preview/`, raw JSON з existing strict parser. `create_task`: required action/title/assignee_id/deadline; optional category/priority/order_id/request_code. `update_task`: required action/task_id/reason + щонайменше одне title/category/priority/assignee_id/deadline/order_id/status/result/archived. `archived` тільки boolean та окремий update, без інших полів. Result зберігає буквальні рядки; null заборонено. Нова completion потребує input result≥3 і явний FK; no-op statusdone не вигадує completion. При completion без input priority сервер задає null.

Зміна: `{id,payload,expires_at,effect:{entity:'task',task_id:null|ID,operation:'create'|'update'|'archive'|'restore'|'reopen'|'complete'|'result_correction'},impact:[...]}`. `payload` — серверна канонізація; create priority ''/'none'→null. No-op: `{state:'no_change',id:null,payload,expires_at:null,effect:{entity:'task',task_id:ID,note:'Зміни не потрібні.'},impact:[]}` — не створює proposal.

Impact: `{kind:'tasks',id:null|ID,field,label,before,after,code:title}`. FK `assignee_id` before/after — `{id:null|ID,name:string}`; `order_id` — `{id:null|ID,code:null|string}`. Інші before/after — null/string/bool. Архівування field='archived' false→true, без prospective timestamp. `is_overdue` — окремий boolean diff, коли змінився. UI показує серверний diff, не обчислює його сам.

POST `/api/operations/confirm/`: `{proposal_id:UUID,confirmed:true}`. Success200 `{state:'succeeded',task_id:ID,audit_id:UUID,impact:[...]}`. Same-ID replay literal-equal за однакових прав. Error403/404/422; definitive409 `{code:'proposal_stale'|'proposal_expired',error:...}` тільки після mutex і перевірки відсутнього receipt. Generic409 `write_conflict`/`temporary_failure` не очищує pending. Старі ERP errors не змінюються.

## Читання

GET `/api/tasks/`: колишній список, default archived=false. Filters `archived=true|false`, `assignee_id=positiveID`, `overdue=true|false` (інші oldfilters/search/order збережені); malformed400. GET `/api/tasks/<id>/` читає active/archived однаково за Policy. Нові поля разом зі старими:
`assignee_id:null|ID,assignee_name:string,order_id:null|ID,order_code:null|string,result:null|string,result_recorded:boolean,archived_at:null|ISO,archived:boolean,is_overdue:boolean`.
`assignee` — незмінний legacy рядок; `status` — persisted, UI не підміняє його overdue. Новий create assignee='', result='', statusactive. Employee picker бере чинний Employee directory, не вводить вручну ID. FK name — повний до200 символів; nullable FK має legacy fallback.

GET `/api/tasks/<id>/history/?limit=20&cursor=...`: `{task_id,items,next_cursor:null|string}`. Limit1–50. Item `{id,action,transition,created_at,actor:{id,role,display},reason,before,after,changes,legacy:false}`. before/after whitelist task state: title/assignee/assignee_id/assignee_name/deadline/order_id/order_code/request_code/history_refs/status/priority/category/branch_id/result/archived_at. changes = той самий impact shape. Legacy item має legacytrue, before/after null, changes[], note='Структурований diff раніше не збережено.'; довільний старий payload не повертається. Cursor400 malformed;404 hidden/foreigntask. Результат можна показувати лише після актуального source scope.

GET `/api/operations/task-proposals/<proposal_id>/`: owner-only/current same role; нова session дозволяє READ, не POST. `{proposal_id,action,state:'succeeded'|'pending'|'expired'|'unknown',expires_at,same_session:boolean,receipt:null|canonical}`. Missing/foreign/otheraction404; revokedrole403. Pending/expired/unknown не доводить відсутність паралельного commit і не створює новий намір. Збереження IDs доconfirm, точнийsameIDretry, без result/text уtab storage.

Raw task REST POST/PUT/PATCH/DELETE403 `{code:'approval_required',error:'Зміни доручень потребують попереднього перегляду та погодження.'}`. Кнопки ведуть до ControlledTask; native admin read-only.

Усі summary/home/dashboard counts беруть policy-scoped active tasks; archived — окремий список. Segments done/overdue/process/active взаємовиключні, total — active count. New alerts спираються на deadline<server as_of, status!=done, archived_atnull. Реальний0 не підміняєтьсяdemo fallback.


## Уточнення 12.09.2026 після scoped перевірки

- Звичайне active/process оновлення result зберігає literal текст≤2000, включно з `OK` чи пробілами. result_recorded лише trimmed≥3; новий done і done→done result correction вимагають FK та trimmed≥3. result=null відхиляється.
- Reopen зберігає попередній result; одночасна зміна result відхиляється. Окремий subsequent active/process update може зберегти нову чернетку.
- home.tasks має assignee_name/is_overdue; legacy overdue — alias is_overdue. Persisted status ніколи не переписується для read.
- History regular і .json підтримують той самий scoped payload. Новий task-proposals route suffix не додає.
