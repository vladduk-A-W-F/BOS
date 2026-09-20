# BATCH-02 · незалежний review фактичного PostgreSQL16 artifact

20.09.2026. Reviewer `/root/bos_batch02_review`, не автор source чи CI. Вердикт **ACCEPT_SCOPED_POSTGRES_EVIDENCE**. Жодних додаткових app tests, повторів CI, міграцій або GitHub actions reviewer не запускав.

Run ID `35507888776`, attempt1; candidate commit `8060075455206257d6283c70906facca98f0bc1a`; runtime source `ce495b29214f21a80b8efd5bf41f6f219b5cb182b0453a7c43dac8899bc06ed5`. GitHub native success/provenance перевірив root; цей незалежний review перевіряє наданий ZIP, його повний вміст і вже прийнятий runner/source контракт.

## Цілісність та backend

- ZIP `BoS_BATCH02_PG16_35507888776.zip`:11719 bytes; SHA256 `4908b2ad522fde391d254061a41560fd8e3336c692d3ad5f6819eff7fe97b6ec` звірено.
- Усі9 ZIP entries побайтово збігаються з raw extraction. Усі8 записів sha256-index мають правильні sizes/SHA; дев’ятий файл є самим індексом.
- Runner SHA `12aa5083f8ba4baea625617c55555b265d3f07e164f9b03613c4f92dcd0a8371` і reused helper SHA `30046f9c933b7a0fefc8e1813e07ca2fbea782bb6ebba9974d74a8dd59a13cfb` збігаються з попереднім independent static review.
- Обидва stage source SHA/commit збігаються із frozen candidate. Report.source_unchanged=true за перевіреним runner before/after digest/database-hash алгоритмом; report.errors порожній.
- Raw `BOS_BATCH_TEST_DATABASE` доводить PostgreSQL `160015` (16.15), actual test DB саме `test_`+issued source DB, по одному proof кожного stage. Python3.12.14, Django6.0.5, psycopg3.3.6.
- Source DB `bos_verify_e4990e32bd2b4f38` та `bos_verify_77a8896a2ca54378`: до/після рівні tables/rows/version; жодна не підмінена test DB. Текст canary містить BATCH-01 через reuse helper, але перевіряє ті самі fresh disposable джерела цього BATCH-02 run.

## Фактичні результати

| Stage | Raw результат | Час stage |
|---|---|---|
| postgres-order-trace |18/18, exit0, один `OK`, без skips/expected failures/unexpected successes|9.280s|
| postgres-adjust-dependencies |24/24, exit0, один `OK`, без skips/expected failures/unexpected successes|48.662s|

Разом42/42 адресних methods. У second stage raw прямо називає21 portable та3 PG-only concurrency methods. Review звірив raw counts, summaries, database proofs і source-canaries, не покладався лише на accepted=true.

## Реальне очікування mutex

У кожному raw `N2_POSTGRES_CONCURRENCY` є три різні backend PID. Порядок timestamps: A mutex_acquired → B mutex_attempt → monitor blocking_proven → B mutex_acquired. Monitor фактично спостерігає B у wait_event_type=Lock і PID A у pg_blocking_pids(B), перш ніж test відпускає A.

| Сценарій | A/B/monitor PID | HTTP | Підтверджений ефект |
|---|---|---|---|
| independent |192/193/191|200/200|Різні lots; quantity9.000 і8.000; events13 і14; assertions двох Movement/Event пройшли|
| same |202/203/194|200/409|Другий намір stale; quantity9.000; один Movement/Event, pending receipt відмовленого лишається null за пройденими assertions|
| replay |205/206/204|200/200|Однаковий JSON receipt/event16 та impact; один Movement/Event за пройденими assertions|

Це закриває раніше знайдену прогалину authored test, де signal перед execute доводив лише attempt order: фінальні raw містять незалежне спостереження PostgreSQL Lock.

Блокувальних findings у цьому artifact не виявлено. Read-only trace/access boundaries та scoped adjust behavior тепер мають адресні SQLite і PostgreSQL16 докази. Це не повний access sweep, UI/browser/E2E, навантажувальний тест або доказ F04/F05 виправлення. Міграція виконувалася лише в disposable test DB; production не активовано.

TECHNICAL_READY=false, PILOT_ALLOWED=false, full_run=false, business_e2e_run=false. P05 3/3 та A09/A10/A11 незмінні. Root окремо повідомив native verification старого BATCH-01 run35507888700 як targeted SKIPPED; цей reviewer не виконував повторного connector-запиту і не приписує це artifact BATCH-02.
