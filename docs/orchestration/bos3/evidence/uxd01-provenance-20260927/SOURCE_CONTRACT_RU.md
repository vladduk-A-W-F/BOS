# UXD01 provenance: exact source contract

Read-only explorer uxd01_source_contract; base3d1eabe3b8f54ebc6c6d6bf0241beba219d1fc3c.
No edits, imports, test/build, browser/network or database execution.

Endpoint: /api/erp/snapshot/, erp/urls.py:7, views.py:16-19,
queries.py:83-138. Policy filter is CEO full installation, other roles
document/item/link-derived visibility (operations/policy.py:140-212).
Non-CEO projection redacts finance/home, then task-only home is re-added
(operations/projections.py:42-77; erp/views.py:18). No branch selector exists.
Use account-visible records, not all company records for every role.

The frontend sets at=new Date().toISOString() only after identity, scope,
access-revision and payload-shape checks, frontend/boss_app_source.html:5209-5222.
This is successful local reading time, not the data-update time.
as_of comes from Configuration dataset.as_of or server date.today,
operations/service.py:16-18; snapshot output queries.py:133. homeBusinessDate
validates YYYY-MM-DD at frontend:5114. This is a calculation reference date,
not a calendar range or a guaranteed historical snapshot/date filter.

Per-metric existing sources and destinations (frontend:5248-5263):

1. Orders with at least one line b03OpenLine>0: effective open_quantity,
   otherwise quantity-shipped (4350-4351). SalesOrder/SalesLine projection.
   Destination erp/sales: ERP -> Продажі.
2. Production jobs where status != done. Destination erp/production:
   ERP -> Виробництво.
3. Lots quantity>0 with quality!=approved or missing_documents nonempty.
   queries.py:100-105. Destination erp/quality: ERP -> Якість і зміни.
4. Unarchived home.tasks status!=done. CEO experience.home tasks, non-CEO
   Policy.tasks; overdue calculation uses as_of. Destination hr/tasks:
   HR -> Доручення.
5. CEO-only selected-currency financial.receivable: current invoice open
   amount after active credits and payments, queries.py:112-114,
   experience.py:62-78, balances.py:59-65. Destination erp/costs:
   ERP -> Фінансовий результат. Not a period report or AR ledger route.

Shared truthful Ukrainian wording: Джерело: знімок ERP. Обсяг: записи,
доступні поточному обліковому запису; філію окремо не вибрано.
Бізнес-дата розрахунку: дата або не надано; це не період.
Прочитано у цьому вікні: час; це не час оновлення даних.

ready is only fresh/empty (frontend:5233-5235). Not-ready or unavailable
navigation disables buttons (5173), onNavigate also checks canUse/available
(5263). Context drift, access revision,401/403/404/409 clear data; stale
retains at internally but must not expose trusted metric values/provenance
or enable navigation. No new request, permission or record-specific target.

The proposal is valid narrowly, but its generic source-record action is not
implemented: routes are section-level only. Full UXD-01 source/period/branch/
deviation and cross-role acceptance remain open. Owner learning and waiting
questions and historical caps are independent and unchanged.
