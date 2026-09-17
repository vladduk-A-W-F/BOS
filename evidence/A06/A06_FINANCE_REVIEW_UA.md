# A06 · незалежний фінансовий набір

Дата: 11.09.2026. Перевіряльник: агент a06_finance_tests. Вихідний HEAD під час завершення: `92097ecd0f7d40776c793c0405ac80b16bb5f0b8`; фінансові зміни A06 ще не закомічені.

**Результат: 33/33 методи пройшли, exit 0, 15,369 с, SQLite.** PostgreSQL не запускався; це не приймання всього gate 5 чи всього BoS. Root сам переносить файл у `finance/test_concurrency.py`. Checkout і робочі бази цей агент не змінював.

## Файли

- `a06_finance_tests.py` — самостійний набір із абсолютними імпортами; після перенесення немає tmp-залежностей.
- `a06_finance_run2.log` — повний stdout/stderr Django.
- `a06_finance_run2_before.json`, `a06_finance_run2_after.json` — SHA 10 залучених фінансових файлів і тестового набору перед/після.
- `a06_finance_manifest.json` — усі 33 точні ID та результати.
- `a06_finance_before.log` — перший незалежний діагностичний запуск; **не називати red до виправлення продукту**.

SHA256 набору: `6677a51aa65cb213e1910c134ba7cc47cab5c8484c89226e3118611b64f286dd`.
SHA256 впорядкованої карти 10 фінансових файлів: `2d4273b87f84e87ede168f300a6a79b8eb329e3b62856d58615874d58951d477`.
Початок фіксації: 2026-09-11T20:43:30.085837+00:00. Кінець фіксації: 2026-09-11T20:44:01.681897+00:00. Усі SHA однакові; `scope_unchanged=true`. Це SHA фінансового scope, а не повного незмінного tree. Повний source SHA встановлює root verify.

## Що перевірено

Реальні `TransactionTestCase`, дві живі незалежні DB connections у потоках, barrier перед двома викликами, справжні CSRF/login HTTP-сесії. HTTP/ORM/команди/зовнішня LLM не підмінялися. Зовнішня LLM не викликалася; legacy create helpers виконувалися напряму.

1. HTTP та shared ORM повтор одного ключа для Transaction і Salary у EUR/USD/UAH: один PK, одна фінансова сутність, один audit і один durable receipt. Два HTTP 201 дозволені лише з одним PK; за 409 послідовний retry обов’язково повертає первісний PK. Для ORM приймається лише явний FinancialIntentConflict, сирий DB exception падає.
2. Mismatch повного payload, одночасний mismatch, різні ключі для однакових законних Transaction та Salary UNIQUE періоду; окремі namespaces за моделлю й актором.
3. Відсутній/невалідний HTTP ключ, допустимі межі ASCII 1/128, format aliases, канонічно рівнозначні Decimal/дати/FK/defaults.
4. Replay після архівування повертає чинний archived_at зі старим PK; replay Salary create після pay лишає paid і одну первісну витрату. Зниження ролі перед HTTP replay дає 403.
5. Реальні SQL triggers SQLite/PostgreSQL-профілю відхиляють audit після фінансового INSERT. HTTP 409, financial row/audit/claim відкочені; повтор після видалення тестового trigger проводить рівно один результат. PostgreSQL-код написаний, але не виконаний.
6. Legacy `_create_transaction` / `_create_salary` передають той самий operation_id у shared command.
7. Pay/edit у трьох валютах, pay/archive, create Salary/archive Employee, edit/archive Transaction, однаковий Salary edit, подвійні archive та restore Employee/Salary/Transaction: допускаються законні послідовні результати без втрати PK/джерела/суми й без зайвих audit.

У поточному наборі 29 викликів парного harness (58 конкурентних операцій); цей лічильник виведено з виконаних циклів тестів, це не повний closed-world інвентар BoS. Admin перевіряється окремим набором root; ERP — іншим агентом.

## Єдина корекція нового оракула

Перший запуск уже бачив `finance.0006_financialintent` та реалізований ключ. Він дав 33 методи, 32 зелені та один FAIL: тест різних ключів вимагав `[201, 201]` і одержав `[409, 201]`. Це помилка мого нового оракула, а не доказ дублювання чи втрати коштів. Вона суперечила уточненню root/master, яке дозволяє явний конфлікт запису.

Змінено лише цей новий тест: початкова пара має складатися з 201/409 та містити успішний результат; потім retry **кожного власного ключа** має дати 201. Кінцеві PK обов’язково різні, збережено точні assertions двох Transaction, двох audit, двох receipts і суми 200,40 UAH. Якщо перший виклик дав 201, його retry мусить повернути той самий PK. Це не дозвіл непомітно втрачати другий намір. Старі тести не змінювалися; skip/xfail/mock немає.

Перший діагностичний файл історично названо `before.log`, але SHA до запуску не було зафіксовано і продукт уже змінював root. Не використовувати його як доказ pre-fix. Справжній red A06 root зберіг окремо в `evidence/A06/adapters-before.log`.

## Команда другого запуску

```sh
env PYTHONPATH=/workspace/scratch/c7b51e996a9f/tmp:/workspace/sites/bos-original-refined BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages DJANGO_SETTINGS_MODULE=verification_settings BOS_TEST_DB_NAME=/workspace/scratch/c7b51e996a9f/tmp/a06_finance_run2.sqlite3 BOS_TEST_MEDIA=/workspace/scratch/c7b51e996a9f/tmp/a06_finance_run2_media PYTHONDONTWRITEBYTECODE=1 /workspace/scratch/c7b51e996a9f/demo-check-env/bin/python -B -m django test a06_finance_tests --noinput -v 2
```

Django створив і видалив `/workspace/scratch/c7b51e996a9f/tmp/a06_finance_run2.sqlite3_django_test`. Оригінальні бази не відкривалися й не мігрувалися.

```text
Ran 33 tests in 15.369s
OK
System check identified no issues (0 silenced).
```

## Точні ID

- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_transaction_http_same_key_concurrent_all_currencies`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_salary_http_same_key_concurrent_all_currencies`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_transaction_orm_same_key_concurrent_all_currencies`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_salary_orm_same_key_concurrent_all_currencies`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_transaction_http_same_key_changed_full_payload_is_409`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_salary_http_same_key_changed_full_payload_is_409`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_transaction_http_same_key_concurrent_mismatch_has_one_winner`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_salary_http_same_key_concurrent_mismatch_has_one_winner`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_different_keys_identical_transaction_facts_remain_two_legitimate_rows`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_different_keys_cannot_duplicate_one_salary_period`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_required_http_header_missing_is_400_without_writes`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_invalid_http_keys_are_400_without_writes`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_http_key_ascii_boundary_and_model_namespace`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_transaction_format_aliases_replay_one_intent`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_salary_format_aliases_replay_one_intent`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_orm_transaction_equivalent_decimal_date_and_fk_forms_replay`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_orm_salary_equivalent_numbers_fk_and_explicit_defaults_replay`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_transaction_http_replay_after_archive_returns_fresh_historical_row`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_salary_http_replay_after_archive_preserves_marker_and_id`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_salary_create_replay_after_payment_does_not_reopen_or_add_expense`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_same_key_second_actor_creates_separate_legitimate_intent`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_role_revocation_is_checked_before_financial_intent_replay`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_transaction_audit_failure_rolls_back_intent_money_and_retries`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_salary_audit_failure_rolls_back_intent_accrual_and_retries`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_orm_mismatch_raises_explicit_intent_conflict_without_mutation`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_legacy_transaction_helper_propagates_one_operation_key`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_legacy_salary_helper_propagates_one_operation_key`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_same_salary_pay_racing_edit_keeps_matching_expense_all_currencies`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_same_salary_pay_racing_archive_preserves_one_serial_history`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_salary_create_racing_employee_archive_never_rewrites_history`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_transaction_edit_racing_archive_keeps_one_historical_id`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_same_assignment_concurrent_salary_edit_has_one_update_audit`
- `finance.test_concurrency.FinancialIntentConcurrencyTests.test_archive_and_restore_each_duplicate_command_has_one_audit_and_same_ids`
