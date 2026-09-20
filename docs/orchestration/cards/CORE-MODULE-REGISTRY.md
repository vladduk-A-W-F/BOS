# CORE-MODULE-REGISTRY

Авторизація: нове повідомлення власника та BoS_prompt.md, 20.09.2026. Розвивати функціональні модулі навколо спільної системи, після незалежного приймання оновити PR/план/Codex. Рішення: чинні Django/React, Policy, Decimal, writers та UAH; архітектурна карта MODULAR_PLATFORM_UA.md.

Allowlist: erp/module_registry.py, erp/module_views.py, erp/urls.py, erp/test_module_registry.py, docs module contract/evidence. GET /api/erp/modules/ — серверний whitelist metadata реально наявних колекцій/видів/форм. Без нових моделей, міграцій, ledger або generic writer. Конфігурація модулів лише складає інтерфейс, не замінює Policy й не видаляє дані. Unknown config fail closed. Поля грошей/керівні дії/утримання відсутні для non-CEO; observer без write actions.

Автор pg_acceptance у execution/core-registry/source; незалежний reviewer business_scenarios. До3 вузьких нових test invocations, raw outputs і точні SHA; історичні suites не запускати. Критерії: auth/roles, GET/no-store/no writes, зв’язність manifest source/model/actions/views, невідомі налаштування. Це CORE-01, не завершення всієї Фази1 або семи фаз.
