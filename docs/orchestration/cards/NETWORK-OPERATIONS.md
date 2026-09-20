# NETWORK-OPERATIONS · робоча мережа BoS

Статус: ACCEPT_SCOPED_NO_PG_OR_BROWSER. Доручення власника 20.09.2026: інтегрувати карту, точки та процеси практикуму як функціонал системи, поліпшити й адаптувати; після цього підготувати завдання для Codex на ПК.

База: PR1 HEAD `87b679888c18ed1920f4735aa945dacad514bcaa`. 1834 наявні локальні файли збігаються з Git blobs; runtime збігається. Новіші control/evidence файли читаються з exact HEAD; нерелевантні remote файли зберігаються через base_tree.

Мета: розділ ERP «Мережа та операції» читає фактичні доступні записи Django. Дії проходять чинний preview/confirm, mutex, Policy та журнал. У browser немає окремого фінансового стану.

Підкартки:

1. NETWORK-DOMAIN: явні зв’язки точок/філій та місць замовлень; два етапи переміщення; договірні утримання; правила доступної оплати. Allowlist: erp/models.py, erp/migrations/0006*, erp/network_commands.py, erp/service.py, erp/balances.py, erp/payments.py, erp/corrections.py, finance/statements.py, boss_project/policy.py, operations/projections.py, erp/test_network_commands.py, operations/models.py, operations/migrations/0008*.
2. NETWORK-READ: карта й реєстри з однаковими фільтрами, Decimal/окремими валютами та Policy; scoped CSV/JSON export. Allowlist: erp/network.py, erp/network_views.py, erp/urls.py, erp/queries.py, erp/test_network.py, erp/experience.py, operations/service.py для структурованого stale/expired conflict.
3. NETWORK-UI: наявний React frontend, навігація, робочі форми, карта із джерелом, безпечне повторення confirmation. Allowlist: frontend/boss_app_source.html, scripts/build_frontend.cjs, assets/network-map.js, generated assets/app.js і frontend/boss_app_html.html, boss_project/refinement_views.py, адресні UI перевірки.
4. NETWORK-DEMO: три синтетичні UAH набори лише у demo-профілі та порожній бізнес-БД, повтор без дублювання. Allowlist: erp/network_demo.py, erp/management/commands/seed_network_demo.py, erp/test_network_demo.py, docs/NETWORK_DEMO_UA.md.
5. NETWORK-WORKFLOW: документи, доступні зв’язки, фактичні стадії й час; nullable creationtimestamps без backfill та RFQ/quotes у наборі. Allowlist: erp/network_workflow.py, erp/test_network_workflow.py, erp/models.py, operations/models.py, erp/migrations/0007*, operations/migrations/0009*, erp/network_demo.py, erp/test_network_demo.py, docs/NETWORK_FLOW_METRICS_UA.md, docs/NETWORK_DEMO_UA.md, erp/network.py для композиції.
6. NETWORK-HANDOFF: інтеграційний review, evidence, довідка, завдання Codex і оновлення control документів. Без зміни readiness gates.

Автори працюють у виділених копіях. Root послідовно інтегрує reviewed зміни; незалежний reviewer перевіряє патч і raw output. Нові адресні synthetic тести дозволені. Повні suite/PG/E2E з вичерпаним лімітом не повторюються. Реальні БД, production activation, main, 85/12, 11 GATES і прапорці готовності не змінюються. Історичні EUR записи не перетворюються на UAH; нові набори задані у гривні.

Нові HTTP-перевірки NETWORK-READ спочатку містили дефект harness: не передавали чинний обов’язковий `confirmed:true` і віднімали Decimal від рядкового атрибута щойно створеної fixture. Виправлено саме виклик/тип fixture, бізнес-очікування не послаблено; невдалий raw збережено. Три invocations включали один випадковий повтор до застосування виправлення. Повний модуль більше не повторювався. Незалежні дві нові регресії перевірені окремо RED→GREEN.

Фінальна композиція та її виправлення: NETWORK-WIRING. Звіт: docs/orchestration/NETWORK_OPERATIONS_UA.md. Нові CI/control commits бази до edd5227 збережені.
