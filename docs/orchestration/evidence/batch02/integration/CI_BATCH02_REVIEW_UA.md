# BATCH-02 · незалежний review адресного CI та композиції

20.09.2026. Reviewer `/root/bos_batch02_review`. **ACCEPT_SCOPED_CI_CONFIGURATION** для одного нового адресного PG16 запуску замороженого кандидата. Це статичний review конфігурації, не PASS ще не виконаного PostgreSQL.

Складений erp/views.py перевірено як exact прийнятий N2 prefix + trace suffix (нормалізація лише переносів на стику), AST однаковий. Finding stale patch baseline і первісний resolver failure описано в INTEGRATION_VIEWS_REVIEW_UA.md. Raw failed attempt збережено. Integrated02: 39/39 portable methods, exit0, без skips; 28.811s wall /24.736s test; raw SHA256 `7a68c860d198732d18439a140052b53b7ba085397b37e89c8fc2235aaba13404` звірено. Reviewer повторів не запускав.

CI wrapper і workflow прочитані повністю разом із reused batch01 helper. Import helper не викликає його main/run або історичні stages. Новий план містить лише18 trace methods +24 N2 methods, включно з трьома PG-only реальними lock races. Exact method counts, єдиний test summary, exit0, відсутність skips/expected failures/unexpected successes та фактичний PostgreSQL16 Django-test DB обов’язкові.

Перевірки виконання: same-repo PR, дозволені base/head branches, перша attempt, checkout саме PR head SHA, Python3.12, clean tree, поточний HEAD змінює CI allowlist, reviewed runtime source hash. Кожен stage отримує нову disposable source DB, реальну test DB, ізольовані media/source, source-canary before/after; source SQLite hashes та runtime digest звіряються після runner. Stage budget180s, runner600s; infrastructure failure/timeout зупиняє без retry. Немає full/gate3/E2E або production команд.

`runner.temp` використано тільки у step env/with, не job env. Upload/finalize always зберігає raw stdout/stderr, report, hashes навіть при невдалому setup. Workflow scope job не запускає тести для пізніших docs-only HEAD commits. Відоме обмеження: reopen того самого CI HEAD створює новий run ID навіть з attempt1; root не має reopen/rerun цього дозволеного одноразового запуску.

Перевірені SHA256:

| Об’єкт | SHA256 |
|---|---|
| Runtime source, independently computed source_digest() | ce495b29214f21a80b8efd5bf41f6f219b5cb182b0453a7c43dac8899bc06ed5 |
| .github/ci/batch_02_targeted.py | 12aa5083f8ba4baea625617c55555b265d3f07e164f9b03613c4f92dcd0a8371 |
| .github/workflows/bos-batch02-targeted.yml | e1c45bc44685aaebf0e1b7f18b543cdfca0e38b2498826632e6e0e7ad9bcd650 |
| Незмінний helper batch_01_targeted.py | 30046f9c933b7a0fefc8e1813e07ca2fbea782bb6ebba9974d74a8dd59a13cfb |

Блокувальних findings у фінальному CI scope немає. Потрібний actual run/artifact review для будь-якого PG PASS. Readiness=false/pilot=false, P05 3/3 та A09/A10/A11 не змінюються.
