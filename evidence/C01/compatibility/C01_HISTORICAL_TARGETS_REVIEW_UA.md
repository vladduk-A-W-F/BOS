# C01 full24: незалежний review двох історичних targets

12.09.2026. Read-only; без нових запусків, змін checkout або читання бізнес-БД.

**Погоджено два exact fixture файли. Блокерів немає; full25 залишається обов’язковим.**

Manifest `tmp/c01_full24_compat/FROZEN_MANIFEST.json`: SHA-256 `3ea3d2c6ddab1c3ca3bc7dca985648db1ddabe970a0a76a76d3eaa01eb75c8a9`. Незалежно звірено обидва source/base SHA та всі 6 evidence SHA — без розбіжностей.

| Файл | Candidate SHA-256 |
|---|---|
| erp/test_schema_preflight.py | `fe5907bc4910ba1bd5aa0af7970c691031eb47fda04430f8f1463939ec1648aa` |
| operations/test_document_migration.py | `1608185fbb133e7aa58fb24c3ca7a5f9a8392ef39d9766e813cd0be41dcf9144` |

Actual red збережений у before.log, SHA `1f4a633a3d07051b94f6d688c3705ada9dac17a85c087998a6541be299489476`: 2 методи / 2 failures, 9.569 с. Перший отримав latest замість historical; другий виявив quote_id/approval_snapshot, які не повинні існувати у pre-B01 fixture. Прочитана tasks.0005_controlled_tasks фактично залежить від erp.0005_source_corrections. Залишений task leaf у старих targets тому знову підтягував пізню ERP/A08 схему через migration graph.

Мінімальний diff додає тільки tasks=0004_task_branch у два existing old-target dictionaries та пояснювальні коментарі. Це створення нової порожньої історичної БД, а не відкат заповненої робочої бази. Не видаляються й не обнуляються історичні snapshots. Schema inspection, міграції продукту, reverse guard, _preserve(schema=True), source/media checks і фактичний INSERT після high-water незмінні.

Незалежна AST-звірка підтвердила всі **29 test methods** і **94 assertion nodes** незмінними: 20/44 та 9/50 у відповідних файлах. Усі додаткові рядки поза тестовими методами лише налаштовують історичний граф. Повні row/schema/migration/sequence та byte-oracles не звужувалися.

Actual after.log, SHA `d161b3d267beabfd260276a2fe7891497c145db06f96bd50994f269215864f54`: ті самі **2/2 GREEN**, 7.799 с, OK. A08 звіт містить document high-water 400001, chat high-water 500001, actual next document ID 400002, historical_schema_created=true, b01_source_fields_never_created_or_erased=true, input/media unchanged. Root/author повідомили exit0; він також зафіксований у manifest actual.

Прийнято лише дві fixture адаптації. Це не новий повний прохід 29 методів, не завершення full24/25, не PostgreSQL/Windows/A09/browser acceptance. Старі продуктові вимоги та 11 gates не змінено.
