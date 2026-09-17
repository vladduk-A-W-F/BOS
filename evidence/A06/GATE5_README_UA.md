Gate 5 · інтеграція незалежного verifier draft

Root копіює a06_check_concurrency.py до scripts/check_concurrency.py, a06_concurrency_manifest.json до scripts/concurrency_manifest.json. Поточний verify уже має entrypoint scripts/check_concurrency.py; wrapper працює окремо на кожному фактичному backend.

Обов'язковий статичний набір: erp.test_concurrency — 37 methods; operations.test_document_mutex — 4; finance.test_intent_adapters — 3; finance.test_payment_integrity — 6; finance.test_concurrency — 34. Разом 84 унікальні IDs. Фінансовий набір включає змішані A05 операції; останній, явно доданий root метод перевіряє duplicate monetary updates Transaction/Salary у трьох валютах. Старі 33 фінансові IDs збережено.

Manifest фіксує 26 ERP SCHEMAS, точний COVERAGE_MANIFEST і 89 mode/case/currency keys: 56 HTTP proposal/replay та 33 ORM contention. Очікування не перебудовуються з поточних тестів під час запуску. Нові/видалені method IDs, schema або coverage entries потребують явного перегляду manifest.

Verifier виконує реальний DiscoverRunner; окремо звіряє discovered, started, finished і succeeded IDs. Failures/errors мають traceback у JSON; skip, expectedFailure, unexpectedSuccess, дублікати або відсутні методи залишають complete=false. Реальний stdout зберігається в зовнішньому verify log, а A06_PASS прив'язуються до поточного test ID. 89 records мають бути унікальні й точні за mode/case/currency; потрібні one_effect, event ID та відповідний replay/loser-retry доказ. Надруковані records не замінюють успішного результату самих тестів.

Перед підключенням бази вимагаються новий абсолютний check_<uuid>.sqlite3 поза checkout, файловий TEST.NAME та окремий BOS_TEST_MEDIA. Існуючий SQLite test DB не видаляється. PostgreSQL допускається лише з BOS_PG_DISPOSABLE=1, bos_verify_<hex> та явними параметрами; відсутній backend не підмінюється SQLite. Наявність derived test_<name> у PostgreSQL перевіряється до DiscoverRunner, щоб не допустити його автоматичного DROP. Порожність початкової verify DB, фактичні test NAME/vendor/version, SHA джерел до/після фіксуються окремо.

Звичайний виклик після копіювання: python -B scripts/check_concurrency.py. Параметри --project-root, --manifest і --output підтримуються; test subset або режим пропуску недоступні. Env і одноразову базу надає чинний scripts/verify.py. Один успішний SQLite виклик підтверджує лише SQLite; PostgreSQL є окремою обов'язковою частиною загального verify.

Незалежно виконано лише AST/syntax та статичну валідацію JSON: 84 IDs, 26 схем, 89 keys. Django setup, підключення DB і комбінований набір цим агентом не запускалися. Перший інтегрований запуск і підсумкові докази створює root. Браузер, Windows і зовнішній LLM у цьому gate не приймаються.
