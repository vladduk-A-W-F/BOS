# NETWORK-PLAN-CURRENCY

Статус ACCEPT_SCOPED. User20.09.2026: «делай все этапы». Підготовлено за NETWORK-CONTINUATION та CODEX_NETWORK_TASK_UA.

Причина: production-material next_step міг пропонувати роботу, матеріал або закупівлю іншої валюти, після чого штатний writer відхиляв дію. Історичні несумісні резерви могли створювати невиконуване продовження.

Allowlist: erp/experience.py, erp/test_network_currency.py, ця картка/evidence. Сумісні ресурси підбираються у валюті роботи/замовлення й потрібній точці; при несумісних видимих історичних резервах повертається пояснення без команди. Історичні суми/валюти не змінено. Policy та writer лишаються чинними.

12 незмінних нових regression tests: RED12 → GREEN12, exit1→0, 4.249s після виправлення. Реальні preview/confirm включають reserve→start→finish та transfer/receive; лише synthetic SQLite. Використано2/3 invocations, reviewer не повторював модуль. Автор currency_completion, незалежний reviewer integration_diagnosis. Evidence: docs/orchestration/evidence/network-acceptance/currency/.

Висновок не охоплює всю можливу повноту підказок: приховані або непридатні старі резерви можуть бути відхилені writer під час preview. Не розкриваємо приховані записи. PostgreSQL та браузерна оцінка не випливають з цього тесту.
