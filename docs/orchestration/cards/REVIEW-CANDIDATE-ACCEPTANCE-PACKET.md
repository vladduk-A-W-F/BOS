# REVIEW-CANDIDATE-ACCEPTANCE-PACKET

Пріоритет P1. Власник bos_readiness_auditor. Статус BLOCKED_DEPENDENCIES.
Залежності: REVIEW-BRANCH-RECONCILE, REVIEW-NETWORK-PAYMENT-DIAG, REVIEW-EVIDENCE-PORTABILITY. Незалежний попередній збір можливий паралельно; фінальне приймання пакета — після залежностей.

## Проблема й доказ
Немає єдиного прийнятого PR1+PR2 runtime. Gate10 exact646d3b8 не охоплює PR2. Gates1–9/11 не прийняті для поточного кандидата. LOCAL-GATE1-4 має незавершений access-current-1/checks=[]; PG preflight має 0 test attempts. Core views на abb8845 мають component/static, не browser proof. Success scope job/skipped/echo-only CI не є продуктовими доказами.

## Дозволені файли й наступний крок
Read-only: STATE/QUEUE, ACCEPTANCE_GATES.json, scripts/verify.py (без виконання), reports/raw, Git refs/diffs/jobs. Write: новий docs/orchestration/acceptance-packets/* і погоджені PLAN/STATE/QUEUE; тестовий код і workflows не змінювати.
Після опублікованого й незалежно перевіреного integrated candidate зафіксувати його Git SHA та source digest. План reconciliation не означає, що цей кандидат уже існує. Якщо інтеграція ще не виконана, лишити відповідну зовнішню передумову OPEN.
Для кожного з 11 незмінних gates вказати: вимогу, exact source, evidence/CI job, реально виконані cases, skipped/missing, reviewer, ліміт і конкретний наступний дозволений scope.
Спочатку підготувати адресні prerequisites Gate1/4 та PG fixture; full/PG-suite/E2E не запускати. Restore/Linux/wheels/Caddy/OpenSSL лишаються непідтвердженими до власних доказів.
При перенесенні PR2 зберегти історичний PG2 PASS/currency accepted, але не переносити їх на новий source без обґрунтованого impact review. Ліміти network workflow/read/composition/core views збережені.

## Приймання
Незалежний reviewer підтверджує матрицю, відсутність чужих SHA/непов'язаного CI і мінімальний decision packet лише для дій, яким справді бракує дозволу/середовища. Це приймання документа, не TECHNICAL_READY чи PILOT_ALLOWED.
Потрібні людські рішення описуються точно; загальний запит «дозвольте все повторити» неприйнятний. Заборонено зміну frozen gates/AGENTS/production/Sites/реальних даних/API. Автоматичне merge й запуск suites не входять у картку.
