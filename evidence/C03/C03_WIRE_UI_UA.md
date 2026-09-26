# C03 · точний wire checkpoint v1

Backend author owns finance/{statement_csv,statements,statement_views,statement_reads,models,commands,views}.py, нову finance migration, erp/{service,views,assistant}, operations/{service,views,projections}, Policy/middleware integration і власні тести. Root UI/native/docs окремо. Реалізація ще не green; нижче погоджуваний interface, не готовий сервіс.

## Routes і доступ

Вісім Django paths під `/api/statements/`, без автоматичного `.json`: `sources/`POST → `finance.statement_views.sources` (`statement-source`); `imports/`GET→imports (`statement-imports`); `imports/<uuid:pk>/`GET→import_detail (`statement-import-detail`); `imports/<uuid:pk>/export/`GET→export (`statement-export`); `lines/`GET→lines (`statement-lines`); `lines/<uuid:pk>/`GET→line_detail (`statement-line-detail`); `lines/<uuid:pk>/candidates/`GET→candidates (`statement-candidates`); `summary/`GET→summary (`statement-summary`).

`finance.views.TransactionViewSet.summary` @action(detail=False,methods=['get']) додає regular + `.json` `/api/transactions/summary/`. Усі нові reads/writes CEO-only; unauth401, manager/observer403. Ledger models НЕ реєструються в admin (жодних нових admin CRUD). Загальні sources download/export зберігають чинні permissions. Access expected180→190definitions, усі old180/57/C01controls12 залишаються.

Немає нового proposalGET. Unknown result queue тримає proposal_id/action та allocation keys, повторює той самий confirm; committed Import/Line reads показують факт. Missing/404 або expired без receipt не дозволяє automatic new intent. Оригінальний C01 proposalGET не приймає C03 actions.

## Upload/import

Upload multipart рівно `file,code,revision,title`, CSV file≤1MiB, multipart≤1MiB+64KiB. Response201: `{id,code,revision,title,status:'needs_review',checksum,filename,format:'bos_statement_csv_v1',parser_version:'1',row_count,source_totals}`. `id` — Document PK. Review existing POST `/api/operations/documents/<id>/review/` з `{checksum}`.

Parser failure422: `{error,code:'statement_csv_invalid',errors:[{record,column,code,message,physical_end_line?}]}`. Identity conflict409: `{error,code:'statement_identity_conflict',errors:[...]}`; size413. Record numbering header1. Інші validation422/error; invalid GETfilters400; жодних partial statements/proposals.

Import payload рівно §5.1 master. New preview200 `{id,payload,expires_at,effect,impact}`. `effect={schema:'bos.statement-import.v1',source:{document_id,source_sha256,source_system,account_ref},counts:{create,reuse,total},lines:[{external_id,decision:'create'|'reuse',line_id:null|existingUUID,record}],source_totals,transaction_delta:0,payment_delta:0}`. Impact — стандартний array, тільки фактичні повідомлені зміни; prospective UUID не показуються як записи.

Exact bytes already imported: `{state:'no_change',id:null,first_commit_receipt,current_summary}`; payload/поточні totals не підміняють original receipt.

Committed import receipt: `{state:'succeeded',schema:'bos.statement-import.v1',import_id,document_id,source_sha256,source_system,account_ref,counts,lines:[{line_id,external_id,record,decision}],source_totals,erp_event_id}`. source_totals завжди array3 `{currency,in,out,net}` fixed2strings.

## Reconcile

Payload рівно §5.2 master, без додаткових actor/date/reference/amount Transaction полів. UUID4 allocation_key генерується до першого confirm й зберігається з наміром. Reference `STMT-`+key.hex. Counterparty manual explicitnull дозволений тільки без AR allocations; import_identity/salary_source — точні alternatives master.

Preview effect `{schema:'bos.statement-reconcile.v1',line_id,amount,currency,transaction:{mode,transaction_id:null|existingPK,created,fields:{direction,amount,currency,date,category,description,counterparty_id,contract_id,branch_id}},binding_created,allocations:[{allocation_key,decision:'create'|'reuse',allocation_id:null|existingUUID,mode,invoice_id,payment_event_id:null|existingPK,amount,currency,reference}],allocated,unallocated,invoices:[{invoice_id,code,before,after}],deltas:{transactions,financial_intents,finance_audits,allocations,payment_events,reconcile_events}}`.

Committed receipt `{state:'succeeded',schema:'bos.statement-reconcile.v1',line_id,transaction_id,transaction_created,binding_created,new_allocation_ids,reused_allocation_ids,created_payment_event_ids,reused_payment_event_ids,amount,currency,allocated,unallocated,invoices,erp_event_id,actor_id,impact}`. invoice before/after `{amount,paid,effective_credit,net_amount,receivable,customer_credit,currency}`; allmoney fixed2strings. Старий receipt незмінний; current fields лише current_summary/read.

Повний domain reuse preview `{state:'no_change',id:null,first_commit_receipt,current_summary}`. Якщо нового proposal немає — жодного pending ID. Якщо після preview ідентичний intent виконав інший proposal, confirm повертає canonical no-change receipt з `{state:'succeeded',schema, no_change:true,line_id,transaction_id,allocation_ids,current_summary}`; не створює Event/Audit/Transaction. Не вимагати erp_event_id для цього конкретного no-change outcome.

## Read shapes

List envelope `{items,next_cursor}`; limit20..100 (мін1), cursor підписаний і bound actor/revision/filter/cutoff. Import filters: source_system/account_ref/from/to; Line/summary додатково currency/direction/status. from/to — booking dates для lines; created date для imports. Invalid query400. Known account pairs `summary.accounts:[{source_system,account_ref}]` беруться повністю з persistedImports, independent від filters. Новий pair вводиться явно без trim/case conversion, без окремого account writer.

Line row `{id,source_system,account_ref,external_id,booking_date,direction,amount,currency,counterparty_external_id,invoice_reference,purpose,first_import_id,record,created_at,transaction_id,cash_recorded,allocated,unallocated,status}`. statuses `unposted|unallocated|partial|reconciled|cash_recorded` (останній тільки out). Out allocated/unallocated='0.00', це не AR. Rowid UUID.

Import row `{id,source_system,account_ref,document_id,source_sha256,created_at,counts}`. Import detail `{import:<row>,first_source,first_commit_receipt,lines:[<all referenced Line rows>],current_summary}`. first_source `{document_id,code,revision,checksum,size,status,format,parser_version,download_url}`; first approved attestation, не нова revision.

Line detail `{line:<row>,first_source,normalized_input:<original eight fields>,binding:<stored binding_snapshot|null>,transaction:<current allowed Transaction fields|null>,allocations:[{id,allocation_key,mode,amount,currency,invoice_id,payment_event_id,created_at,actor_id,source_snapshot,intent_sha256}],invoices:[{id,code,customer_id,currency,settlement,order_ids}],payments:[{id,action,payload,result,created_at}],current_summary:<line current allocated/unallocated/cash/status>}`. Джерела actual ID, без truncated recent300 dependency.

Candidates: GET same line route with `section=invoices|transactions|payments|identities|salaries` (default invoices), optional limit/cursor. Reply `{line_id,section,items,next_cursor}`. Це suggestions/explicit selection, не автоматичний matching.

- invoices: `{id,code,customer_id,currency,amount,paid,settlement,exact_reference}`; samecurrency, historical paid теж допустимий.
- transactions: `{id,date,direction,amount,currency,category,description,counterparty_id,contract_id,branch_id,archived_at}`; exactfinancial matches Line і незайнятий іншоюLine/currentbound.
- payments: `{id,invoice_id,invoice_code,customer_id,amount,currency,reference,created_at}`; actual erp_payment source, не generic snapshot300.
- identities: `{id,namespace,entity,external_id,target_id,first_batch_id,row_sha256}`; фактичні B02counterparty identities із exact externalcode.
- salaries: `{id,employee_id,employee_name,transaction_id,amount,currency,payment_date,period_year,period_month}`; фактичні paidsalary/out sources, без нового salary writer.

Summary `{accounts,filters,currencies:[{currency,imported:{in,out,net},recorded:{in,out,net},unposted:{in,out,net},incoming:{allocated,unallocated}}]}`. Layers не додаються між собою. Transaction summary `{filters,includes_archived:true,balance_kind:'period_movement',currencies:[{currency,in,out,net,expense_categories:[{category,amount}],months:[{month:'YYYY-MM',in,out,net}]}]}`; filters currency/from/to. Manual unrelated journal records не приписуються bank account. Усі3 валюти окремо навітьzero; UIобираєявнуcurrency.

Export — CSV з refs/current statuses, formula-safe text; original download лишає exact uploadedbytes/SHA. Source/statement metadata ніколи не входять у manager/observer collections через нові чи старі routes.

## Уточнення checkpoint 2 (2026-09-12)
- `code/revision/title` у upload зберігаються literally; крайні пробіли відхиляються. `doc_dict` list/detail/versions для statement додає `format/parser_version/row_count/source_totals`; marker sections мають також безпечні `text/source`.
- Import/reconcile confirm повертає receipt прямо. Exact-byte replay може мати document_id першого джерела іншого upload; перевіряються source_sha256/source_system/account_ref, перше джерело не переписується.
- `summary` приймає той самий `status`, що й lines. `import_detail.current_summary` та no-change import `current_summary`: `{lines:[{line_id,allocated,unallocated,cash_recorded,status}],currencies:[...той самий per-currency shape summary...]}`; currencies обмежені refs конкретного import.
- Export: первісні COLUMNS8 + `import_id,line_id,document_id,source_sha256,first_import_id,first_document_id,first_source_sha256,transaction_id,status,allocated,unallocated`. Original CSV bytes/SHA незмінні; текстові formula prefixes екрановані лише в експорті.
- Для вже bound line `existing_transaction` того самого ID допустимий незалежно від того, чи перший binding створено через create_transaction. Перший binding_snapshot, matching і причини не переписуються.
- Cursor для Invoice та ImportIdentity використовує підписаний max existing PK (ці історичні моделі не мають created_at), actor/access revision/точні filters/section. Інші списки використовують created_at+PK cutoff. Жодна вигадана дата не зберігається й не повертається.
