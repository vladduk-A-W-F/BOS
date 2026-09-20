# FRONTEND-GLOBALS · 20.09.2026

Проблема перевірки, не зміна UI: на незміненому 8fec7753 scripts/check_frontend.cjs помилково визначає TextEncoder, sessionStorage та AbortController як unresolved references. Усі три — browser globals, уже вживані на baseline. Незалежний infrastructure owner підтвердив ту саму відмову.

Allowlist: scripts/check_frontend.cjs (додати лише три назви до явного Set), ця картка. Зберегти невідомі references як помилку. Перевірка: фактичний checker на інтегрованому JSX; початкові raw baseline/current errors збережено в UI evidence. Автор root, потрібен незалежний review; не змінює writer inventory, application behavior або критерії gate.

ACCEPTED_SCOPED: time_probe_review незалежно звірив baseline usages/мінімальний diff, поточний інтегрований checker PASS. Невідомі references як і раніше дають exit1.
