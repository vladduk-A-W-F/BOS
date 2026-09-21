# REVIEW-NETWORK-PAYMENT-DIAG

Пріоритет P1. Власник bos_diagnostician. Статус READY_READ_ONLY. Залежності: немає; паралельно з reconciliation.

## Проблема й доказ
[Run 35516896359](https://github.com/vladduk-A-W-F/BOS/actions/runs/35516896359) на `929a395547fa1ed496171120a14b19bc8d5b6f87`, source `c15dfe0e3aeefde2fd4fa7af0e9dd2c7c04072a59b185554b821576b4c2111ca`.
PG job 106094275478 PASS для двох mutex-cases; browser job 106094275495 exit1 після 57 assertions, остання «hold preserves receivable». Timeout 15000ms при очікуванні response payment preview. Причина не встановлена: це не доказ несправного backend або невідправленого запиту. Payment/release/final settlement, mobile і manager/observer не прийняті. Network workflow вже 3/3.

## Дозволений наступний крок
Read-only: .github/ci/network_browser_acceptance.py, frontend/boss_app_source.html, preview/confirm handlers, збережені network-acceptance/final reports, raw request/response/DOM/console/screenshot evidence на точних SHA. Не виконувати код із evidence.
Write allowlist: нові docs/orchestration/diagnostics/network-payment/* і погоджені orchestration записи у review-гілці.
Побудувати timeline: UI payload/selector → дія → початок очікування → наявні HTTP/console events → timeout. Відокремити harness, UI state, request/response та серверні гіпотези. Зіставити з новішим core views diff, не переносити 57 assertions на abb8845 або майбутній merge.

## Приймання
Точна першопричина з посиланнями на raw+source або явна мінімальна прогалина спостереження; незалежний reviewer; окрема картка виправлення лише за доведеного дефекту. Якщо журналів недостатньо, результат BLOCKED_MISSING_EVIDENCE і конкретний безпечний план, не вигаданий діагноз.
Не збільшувати timeout або послаблювати assertion заради PASS. Жодного четвертого запуску workflow/обходу ліміту через локальну копію, новий ID чи агент. Ніяких продуктових змін цією карткою.
