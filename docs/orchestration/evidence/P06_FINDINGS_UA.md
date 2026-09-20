# P06 · підтверджені результати та відкриті проблеми

18.09.2026. Авторизацію відновлено. PostgreSQL suite FAIL; E2E suite PASS, але повнота детальних E2E доказів INCOMPLETE.

## P06-F01 · OPEN · Після демонаповнення PostgreSQL не створює нове доручення

check_operations.py зупинився на confirm create_task. Raw SQL доводить duplicate tasks_task_pkey, id=1, для того самого title «Перевірити покриття».

Причина: seed_bos_demo явно вставляє Task.id 1…8 і не узгоджує PostgreSQL sequence з цими ID.

Мінімальне відтворення: У вже виконаному disposable PG: migrate → seed_bos_demo → CEO preview create_task (title «Перевірити покриття», assignee_id=2, deadline=2026-09-11, request_code=R01) → confirm. Наявний check_operations.py:48 є збереженим red; повтору не було.

Наступна дія: Наступна окрема P10-002: виправити узгодження Task sequence після demo seed, зберігши чинні ID, історію та ідемпотентність. Спершу перечитати межі й журнал спроб; цього ходу код не змінюється.

Докази: `actual-20260918/postgres/artifact/postgres-check_operations.py.log`, `actual-20260918/postgres/JOB_LOG.txt`.

## P06-F02 · OPEN · Тестова передумова імпорту приймає лише SQLite-ім’я БД

Чотири ERPImportConcurrencyTests завершилися FAIL у setUp до конкурентних дій.

Причина: InitialImportFixture.setUp вимагає префікс check_, тоді як фактична ізольована PostgreSQL test DB має дозволене ім’я test_bos_verify_0242b5901c024d81.

Мінімальне відтворення: Наявний gate5 на PostgreSQL → setUp одного з чотирьох ERPImportConcurrencyTests → assert startswith(check_) → FAIL. Raw trace erp/test_initial_import.py:26.

Наступна дія: Окрема правка harness: перевіряти справжню ізоляцію для кожного backend. Не видаляти guard, не пропускати методи і не зараховувати відсутні гонки.

Докази: `actual-20260918/postgres/artifact/gate-05-postgres.log`.

## P06-F03 · OPEN · Тестові коди рахунків перевищують дозволені 30 символів

15 errors у п’яти StatementConcurrencyTests × EUR/USD/UAH виникли до бізнес-гонок при Invoice.objects.create.

Причина: Fixture формує C03-RACE-<tag>-<currency>-<8hex> довжиною 32–36 символів; Invoice.code має max_length=30. PostgreSQL коректно відхиляє переповнення.

Мінімальне відтворення: Фактично виконаний source(EUR, PAIR-IMPORT) створює код із 33 символів → INSERT Invoice → StringDataRightTruncation. Аналогічні trace збережено для всіх 15 subtests.

Наступна дія: Окремо зробити fixture валідною та унікальною в межах 30 символів. Не розширювати поле застосунку лише для тесту; зберегти всі конкурентні assertions.

Докази: `actual-20260918/postgres/artifact/gate-05-postgres.log`.

## P06-F04 · OPEN · Повний Django suite не завершився за 600 секунд

Виявлено 578 тестів, але немає фінального Ran/OK/FAILED summary. Receipt: timed_out=true, timeout_seconds=600, returncode=null; часткові F/E та skip збережено.

Причина: Невстановлена. Ранні F/E або SQL-повідомлення не доводять, що саме спричинило перевищення часу. Частковий вивід не дозволяє назвати повний список невдалих test IDs.

Мінімальне відтворення: Збережений red: фактичний postgres functional → manage.py test --noinput --settings=verification_settings --verbosity=1 → timeout600. Нового експерименту не виконано.

Наступна дія: Планувати подальшу діагностику лише з повним обліком попередніх спроб. P05 timeout cycle 3/3 залишається вичерпаним; новий ID не дозволяє четвертий повтор. Не підвищувати 600s навмання.

Докази: `actual-20260918/postgres/artifact/report.json`, `actual-20260918/postgres/artifact/postgres-django-tests.log`, `actual-20260918/postgres/JOB_LOG.txt`.

## P06-F05 · OPEN · П’ять інваріантів не мають завершеного PostgreSQL-звіту

Gate3 timed_out=true після 600s, returncode=null. Є checkpoints Склад1000/1000 і Виплати1000/1000; фінального JSON, завершення replay та role_access немає.

Причина: Невстановлена. Конкретне порушення інваріанта не доведено; частковий поступ не є 5×1000 PASS.

Мінімальне відтворення: Незмінний check_invariants.py у фактичному PG suite35361765561 → наявні checkpoints → timeout600. Повторів немає.

Наступна дія: Окрема діагностика в межах загального обліку спроб. Зберегти п’ять інваріантів і мінімум1000 прогонів кожного; не позначати незавершене PASS.

Докази: `actual-20260918/postgres/artifact/report.json`, `actual-20260918/postgres/artifact/gate-03-postgres.log`.

## P06-F06 · OPEN · CI не зберігає повні звірки успішного E2E

Actual E2E PASS/exit0; кожний backend повідомив passed821 і confirm_HTTP_calls42. ZIP містить лише п’ять файлів: receipt, verifier report, console, два gate6 logs. Детальних e2e-report.json немає.

Причина: verify.extension викликає e2e_scenario.py без --output. Деталі залишаються у /tmp/bos-gate6-*, поза runner.temp/bos-ci/e2e, що завантажує workflow.

Мінімальне відтворення: Actual run35364824265 → відкрити його ZIP → зіставити два summary.report paths і SHA з manifest: відповідних звітів у ZIP немає. Самі SHA не заміняють байти звірок.

Наступна дія: Окрема правка збереження evidence: архівувати обидва справжні детальні звіти й звіряти їх SHA. Не підміняти їх старим локальним звітом і не змінювати actual suite PASS на application FAIL.

Докази: `actual-20260918/e2e/ARTIFACT_FILES_SHA256.json`, `actual-20260918/e2e/artifact/gate-06-sqlite.log`, `actual-20260918/e2e/artifact/gate-06-postgres.log`.

## Межі

P06-ENV01 RESOLVED: вхід підтверджено приватною сторінкою GitHub та двома фактичними dispatch. Попередній main run35360689207 не мав requirements-ci.txt/evidence.py, тому зупинився до бізнес-тестів; це окрема помилка вибору гілки.

Gate5: 109 методів завершено, 100 успішні; 4 failures та 15 subtest errors охоплюють 9 методів. 107 із116 ERP records наявні; C03 held-transaction evidence відсутній. Це не 109PASS і не 19 окремих зламаних бізнес-функцій.

Raw PG також містить sqlite_master missing, а частковий Django stderr — skip. Повний перелік PG harness прогалин потребує доказів із test ID; довільного зарахування або відкидання немає. P05 DONE лише у SQLite scope; старі ризики й ліміти чинні. Код, схеми, CI та oracle не змінені. P07 і P10-002 не починалися.
