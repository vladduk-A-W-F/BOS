# Незалежний review BATCH-01: цільовий PostgreSQL 16

Дата: 2026-09-20. Рецензент: `bos_batch_review`, незалежно від авторів патчів і CI runner.

**Вердикт: ACCEPT_SCOPED.** Збережені первинні журнали підтверджують три очікувані baseline RED, 26 успішних методів у PostgreSQL-етапах та сім окремих unit-методів. Блокерів у перевіреному обсязі не виявлено. Це прийняття цільових регресій BATCH-01, а не повне прийняття системи.

## Походження та цілісність доказів

Перевірено артефакт запуску [35503944302](https://github.com/vladduk-A-W-F/BOS/actions/runs/35503944302), attempt `1`, його `artifact-metadata.json`, `job.log`, `artifact/report.json`, `runner-started.json`, індекс і всі первинні stdout/stderr журнали.

| Параметр | Значення |
| --- | --- |
| Candidate commit | `aecf8ee1f556b60f3fa34b66a001372e332d02ab` |
| Candidate source SHA-256 | `31c692c5f3113446452e8d15faf95c29b019f433550bf4d0658c4f0428e54d20` |
| Baseline commit | `7d46dced3bcf06d44755cf53366c9e16bd465582` |
| Baseline source SHA-256 | `10d86748d682926a898d2d2dfecd43fd7f6962f6ed38602da7ae704e52aca154` |
| Runner SHA-256 | `30046f9c933b7a0fefc8e1813e07ca2fbea782bb6ebba9974d74a8dd59a13cfb` |
| Artifact ID / name | `10603616377` / `bos-batch01-targeted-35503944302-1` |
| ZIP SHA-256 | `542a3c5975a0a4e1533f0f744bf3ad57e2f0f111afe232f04fb4efaf28185247` |
| ZIP size | `28579` bytes |
| Фактична СУБД | PostgreSQL `16.15`, `server_version_num=160015` |
| Середовище | Python `3.12.14`, Django `6.0.5`, DRF `3.17.1`, psycopg `3.3.6` |

Незалежним читанням байтів і обчисленням SHA-256 підтверджено:

- ZIP hash і size збігаються зі збереженими GitHub artifact metadata; run ID і head SHA узгоджені зі звітом та job log.
- Індекс охоплює рівно 22 файли; всі 22 розміри та хеші збігаються. Сам індекс є 23-м файлом архіву. Всі 23 ZIP entries побайтово збігаються з розпакованими файлами.
- Хеші первинних журналів кожного етапу збігаються з `report.json`. Runner має раніше незалежно перевірений hash.
- Для REQUEST RED baseline містить лише доданий тест `operations/test_request_lengths.py`, SHA-256 `0adbbcf48d8a500f3a199b1c51569358ca200564f14e73b56b5e677a9183598c`; source digest цієї копії — `75dda11a795921ab7b129df15013b774d2214993f11bb30facecd29c8662e962`. Runtime залишається baseline.

## Первинні результати

Кількість методів, підсумок runner і process exit звірено з первинними журналами, а не лише зі статусами JSON. На кожному етапі рівно один підсумок; немає skipped, expected failures, unexpected successes або timeout.

| Етап | Методи | Exit | Підтверджений результат |
| --- | ---: | ---: | --- |
| `postgres-red-p10-003` | 1 | 1 | Очікуваний RED: старий `name.startswith('check_')` guard, `FAILED (failures=1)` |
| `postgres-red-f03` | 1 | 1 | Очікуваний RED: fixture code перевищує `varchar(30)` для EUR/USD/UAH, `FAILED (errors=3)` |
| `postgres-red-n1-request` | 1 | 1 | Очікуваний RED: raw-length регресія, `FAILED (failures=36)` |
| `postgres-green-import` | 15 | 0 | `OK`: реальний імпорт, import concurrency і guard unit-перевірки |
| `postgres-green-finance` | 5 | 0 | `OK`: statement concurrency, import/reconcile, held transaction |
| `postgres-green-request-invoice` | 4 | 0 | `OK`: два REQUEST методи й два наявні invoice boundary методи |
| `postgres-green-n1-ship` | 2 | 0 | `OK`: shipping reference boundaries через прямий шлях, адаптери й stored confirm |
| `artifact-unit-f06` | 5 | 0 | `OK`: синтетичні fixtures перевірки E2E-артефактів |
| `source-unit-digest` | 2 | 0 | `OK`: синтетичні inventories та PureWindows/PurePosix path semantics |

**Точний облік:** 26 green methods у PG-етапах = 16 реальних business/HTTP методів з PostgreSQL + 10 методів guard з підставними з’єднаннями. Окремо виконано сім unit-методів. Три baseline RED методи не зараховані як успішні бізнес-тести. Кількість subtest failures також не є кількістю методів.

REQUEST RED не означає 36 SQL-помилок: журнал містить 12 невідповідностей тексту відмови, 12 випадків зміни стану для trailing-space overflow та 12 HTTP 500 для leading-space overflow із SQL `value too long`. Це очікувані дефекти baseline; відповідні candidate методи завершилися `OK`.

Фактичний три валютний import залишив `A06_PASS` для EUR/USD/UAH з `one_effect=true` та `replay_unchanged=true`. Finance журнал містить `C03_HELD_TRANSACTION` з `actual_vendor=postgresql`, очікуванням блокування в обох порядках, невидимістю незакомічених змін і відмовою stale reconcile/bound-source edit; також є `A06_PASS` import/reconcile для трьох валют. Це первинні runtime-докази в межах заявлених методів.

## Ізоляція

У семи PG-етапах використано сім різних синтетичних source databases і відповідні точні Django names `test_<source>`. Для кожного етапу stdout містить фактичні `current_database()` / `server_version_num` із PostgreSQL test connection: vendor `postgresql`, version `160015`, очікуване ім’я. Журнали фіксують створення та видалення test databases.

До і після кожного етапу source canary має той самий перелік таблиць — лише `public.bos_batch_source_canary` — та той самий єдиний рядок. Усі сім порівнянь збігаються. Candidate/baseline source digests також залишилися незмінними. `source_databases: {}` означає відсутність попередніх source SQLite-файлів у цих checkout; це не доказ перевірки чи збереження будь-якої історичної або production БД.

## Межі висновку

- Це один цільовий CI run на конкретному candidate/source digest, без повторного виконання під час незалежного review.
- P10-003, F03 і N1-REQUEST отримали фактичний PG16 RED→GREEN; N1-SHIP має PG16 GREEN, а його раніше перевірений RED був локальним SQLite доказом.
- F06 перевірено лише на artifact fixtures: реальний бізнес-E2E не виконувався. SOURCE unit tests перевіряють Windows path semantics через PureWindowsPath; запуску на native Windows не було.
- Не виконано full suite, повне прийняття всіх 11 gates, навантажувальну перевірку, production upgrade/rollback або UI acceptance. Результат не переносить історичні PASS на новий source і не розв’язує архітектурне питання N2.
- Звіт коректно залишає `technical_ready=false`, `pilot_allowed=false`, `full_run=false`, `business_e2e_run=false`; історичний P05 лишається `3/3`, `A09_retried=false`, `A10_retried=false`, `A11_retried=false`.
- Пізніший docs-only run не входить у цей незалежно перевірений набір доказів.

Незалежний review включав читання збережених файлів, перевірку хешів/розмірів та розбір первинних журналів стандартною бібліотекою. Канонічний код не змінювався; застосунок, БД, тести й CI повторно не запускалися. Доказів достатньо для `ACCEPT_SCOPED`; підстав для повтору цього запуску не виявлено.
