# VERTICAL-UA-DATA · 20.09.2026

Статус: ACCEPTED_SCOPED. Автор root; незалежний reviewer time_probe_review. SQLite15/15 та PostgreSQL16.15 15/15,192/192route catalogue,86required fieldtests metadata, migration drift absent. Full gates не запускалися. Raw/evidence у звіті VERTICAL_UA_UA.md.

Проблема: чинні ERP Location/SalesOrder не записують філію; окремий Site не є ERP-моделлю. Користувач дозволив реальний вертикальний інкремент у поточному draft PR.

Контракт: nullable PROTECT branch FK, старі записи лишаються без філії; існуючі erp_location/erp_order preview/confirm приймають optional branch_id. Філія замовлення і фізичне місце партії різні виміри. Довідник філій загальний у межах чинної установки; нової tenant/branch permission моделі немає.

GET workpoints: лише Policy-доступні ID; Decimal строки, окремі номенклатури/одиниці/валюти; для non-CEO money=null, available=null, visible reservations only, generic restricted. Рахунки враховують чинні кредити та переплату; це не cash balance. Рухи latest300visible позначені явно. Подвійне читання й access/source guard повертають409 при зміні; атомарний snapshot не заявлено.

Синтетичний seed: 3 філії України/склади/замовлення UAH, чинні service transitions; додає лише свій префікс, не перераховує EUR/USD, working mode заборонений, idempotent marker і collision refusal.

Allowlist: erp/models.py; erp/migrations/0006_branch_links.py; erp/service.py; boss_project/policy.py; operations/projections.py; erp/queries.py; erp/workpoints.py; erp/views.py; erp/urls.py; erp/management/commands/seed_bos_ua.py; erp/test_workpoints.py; ця картка/evidence. UI та перший CEO — окремі ізольовані картки.

Перевірки: міграція на порожній synthetic DB; preview rollback/confirm/replay branch links; invalid branch/observer refusal; UAH точні суми і валютна ізоляція; private IDs/counts/hidden reservations; зміна джерела/прав409; seed idempotency/nooverwrite/working refusal; адресні PostgreSQL16 тести без full suite/E2E. P05 3/3, A09/A10/A11 та 11gates збережені; readiness/pilot=false.

Allowlist уточнено після незалежного review: scripts/access_routes.json та scripts/check_access.py — додати лише новий GET до закритого каталогу, oracle і no_documents contexts; scripts/start_local.py — додати seed_bos_ua після наявних demo seeds. Перевірка catalogue окрема статична, не full access sweep. Старі route definitions/85/12 збережено.
