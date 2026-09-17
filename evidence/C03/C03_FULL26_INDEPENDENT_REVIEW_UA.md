# C03 · незалежний огляд завершеного full26

**Погоджено локальний C03 checkpoint 0.2.15-dev у перевірених Linux/SQLite межах. Нових локальних регресій у фактичному full26 не виявлено.** Повний результат лишається **exit1 / complete=false**: BoS MVP, PostgreSQL, Windows, CI, браузер та upgrade/rollback цим висновком не прийняті. D03 і окрема знахідка F04 не є предметом цього C03 рішення.

Огляд 12.09.2026 — тільки збережені звіти, журнали та manifests. Нових тестів, серверів, браузера, A09 retries, activation або міграцій не виконано; робочі БД, конфігурації й private media не відкривались; canonical не змінено.

## Прив’язка доказів

| Артефакт | Перевірений SHA-256 |
|---|---|
| evidence/C03/verify-1/report.json | 7f32a07725662158d7cf105e098896c9585b27069c2f7f126653aa6ee1dc1ff8 |
| evidence/C03/BEFORE_FULL26.json | 00d5d9301c18c172b16d2c69f1ff6c60acc52cd4347d58b73b8f983db0ce6fba |
| evidence/C03/AFTER_FULL26.json | 55c8fdd45b34149e963305f0208ccf3870adfc7329fa4b43b3cf8b6a74a4c9fa |
| evidence/C03/INTEGRATION_SHA256.json | cb5851430282d5b3b58d68bea83d51de0bb673bfa8af5655119869cdeb8a6407 |
| verify-1/gate-06-actual.json | 786eb970a0b0983e39b17eeb17f18045bfa8dc4cbd95475af2eb2bffc07443bb |

Source **7be2d6ba56ff8d99198645ffe7e1bb5b16d7ad0c37ca72e53b8f3c410dfe8011** збігається у BEFORE, integration, full report, raw E2E, AFTER before/after. Це зіставлення зафіксованого provenance, без нового обчислення source fingerprint чи читання БД. Linux/Python3.12.14, фактичний SQLite3.53.1 підтверджені raw runner metadata; suite=full.

Integration record містить 44 source entries: backend36, UI3, native2, E2E3. Усі шість referenced component manifests перевірено за SHA; кожний із 36 backend source/base SHA точно збігається з раніше погодженим frozen manifest ac16a12c… на базі C01 commit ed3a299a6c497ed89ca98f12a0957b7d3fb9cdf2. Поле full_verify=pending_26 у самому integration record описує момент інтеграції; завершення доведене новими AFTER/report, історичний record не переписано.

Full report фіксує source_database_count=2 та source_databases_unchanged=true. Recorded before/after SHA двох джерельних баз однакові: db.sqlite3 — ec6b89ac86011906881ab686581a0b96f63f17741873c355d2cb459896db02d5; BoS_Demo.sqlite3 — 58fcd32532c6abebfa95ad06ae18d76ddccac2242fb25dc64350ad3203bd0dc8. Raw E2E також має свої рівні protected-before/after карти. Це evidence runner, а не повторне відкриття оригіналів рецензентом.

## Незмінні 11 критеріїв і фактичний результат

IDs у full report — рівно 1–11, без пропусків, дублювання або заміни порогів. SQLite subpass не видається за pass критерію, який також вимагає PostgreSQL.

| № | Фактичний результат full26 |
|---|---|
| 1 | SQLite empty migrations пройшли; загалом НЕ ЗАПУЩЕНО через PG |
| 2 | SQLite22+49+48+32=151, launcher5, Django571 пройшли; загалом НЕ ЗАПУЩЕНО через PG |
| 3 | Усі п’ять SQLite інваріантів по1000 пройшли; PG не запущено |
| 4 | ПРОЙДЕНО:9432 основні HTTP +9 redirect responses,57 field tests;12 C03 controls/130HTTP |
| 5 | SQLite109 methods/116 ERP records/35 actions пройшли; загалом НЕ ЗАПУЩЕНО через PG |
| 6 | SQLite наскрізний сценарій821 checks/42 confirm HTTP пройшов; загалом НЕ ЗАПУЩЕНО через PG |
| 7 | ПРОЙДЕНО:18/18 native restore checks, точні56 таблиць |
| 8 | ПОМИЛКА:30/31; відомий13MiB ConnectionResetError замість отриманого client413 |
| 9 | НЕ РЕАЛІЗОВАНО:actual live upgrade/rollback |
| 10 | НЕ РЕАЛІЗОВАНО:actual browser acceptance |
| 11 | НЕ ЗАПУЩЕНО:немає реального Windows/Python3.12 report |

Коди дочірніх SQLite перевірок 1–7 —0, installer gate8 —1. Full log завершується НЕ ПРИЙНЯТО, full report complete=false; повідомлений root загальний exit1 узгоджений із цими даними. CI pipeline_id/job_url/commit залишилися null.

## Перевірено саме raw logs, а не лише AFTER summary

**Тести та інваріанти.** sqlite-django-tests.log має Found571, Ran571 за348.598s і OK. Старі151+5 залишились окремими обов’язковими перевірками з точними expected counts. Gate3 JSON збігається з AFTER для всіх п’яти invariant IDs, runs1000 і complete=true.

**Права.** З повного gate4 log витягнуто його власний JSON, не друкуючи весь4.2MB журнал. 9432 cases/9432 passed, failures=[],57 discovered/executed без skip/expected failure. Всі12 C03 control objects мають passed=true, їхні actual HTTP масиви сумарно130; всі12 попередніх C01 controls також passed=true. Каталог190 patterns/205 concrete URLs. Counts буквально збігаються з AFTER. Це вже повний інтегрований доступ на final source; попередні target-only closures не підміняють цей результат.

**Паралельність.** Gate5 raw JSON має109 discovered/started/finished/succeeded, нуль failures/errors/skips/expected failures/unexpected successes і runner_failures=0. Required/actual schema actions —35, ERP records required/observed/unique —116, missing/duplicates порожні. Source hash maps до/після runner однакові. Є три held records EUR/USD/UAH: PATCH→reconcile[200,409], reconcile→PATCH[200,400], незмінний bound source; SQLite conflict не видається за PostgreSQL row-lock waiting. Raw log також містить Ran109 і OK.

**Наскрізний процес.** SHA повного збереженого gate-06-actual.json буквально дорівнює SHA в gate6 stdout. Raw report має complete=true,821 виконаний check entry,42 confirm HTTP,14 confirmation intents, той самий source SHA та actual SQLite. Check labels можуть повторюватися на різних кроках;821 не названо821 унікальним тестом. Підтверджені фактичні кінцеві counts:5Movement/13Event/14ActionProposal/3Audit, один StatementImport/Line/Allocation/Transaction. Original and late receipts та джерела перевірені раніше погодженим executable oracle; він тепер фактично пройшов у canonical full. Поля до/після protected source databases рівні.

**Native restore.** Gate7 raw JSON complete=true,18 case objects і всі passed=true. Чисте відновлення саме по собі має чесний scope clean_restore_data_and_code_only та post_restore_http_verified=false; наступні окремі cases доводять реальні restored HTTPS/login/document/version. Точні56 таблиць і4 private files, backup_unchanged=true. C03 after-restore case:три statement ledgers populated,3 lines/1allocation,1new cash Transaction/2existing bindings, archived Transaction залишається в totals,4 первісні receipts, old-session execution refused,0new business effects. Старі B03/C01 cases присутні; C01 має4tasks/6task proposals, history/owner receipt/new-session read і0new effects.

**A09.** Gate8 має рівно31 case; єдиний passed=false — oversized_request_413_no_partial_document:status=null,error_type=ConnectionResetError,documents_and_private_bytes_unchanged=true. Звичайні HTTP cases використовують свої exact status поля; їхня відсутність універсального passed ключа не трактувалась як failure. Обидві зупинки власних Caddy/Waitress дали exit0 без force, private_canaries_absent=true для29 log files. Це повтор відомої межі в mandatory full, а не новий boundary експеримент або доведене виправлення. Попередній одиничний31/31 не закриває нестабільність.

## Висновок у перевіреній межі

Нових розбіжностей між AFTER summary, основним report, raw gate logs та погодженим C03 provenance не знайдено. Погоджено фіксацію C03 як локально перевіреного окремого checkpoint. Цей висновок не ослаблює11 gates і не дозволяє назвати весь продукт готовим.

PostgreSQL, Windows, зовнішній CI, браузер, A10 activation/upgrade/rollback і відома A09 межа залишаються відкритими. D03-F04 та майбутнє D04 мають окремі докази й рішення; тут вони не позначаються виконаними. Повторні optional тести або нові зміни для завершення цього scoped C03 review не потрібні.
