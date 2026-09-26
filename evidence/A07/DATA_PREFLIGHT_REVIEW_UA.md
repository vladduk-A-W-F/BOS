# A07 · незалежна перевірка data preflight

Дата: 11.09.2026. Файл `a07_test_data_preflight.py` призначений для `erp/test_data_preflight.py`.

**4/4 методи пройшли, exit 0, 4,840 с.** Це перевірка вже реалізованого preflight, а не red до виправлення. Падінь, помилок fixture, змін оракулів, mocks або skipped tests немає.

Дві базові схеми створені справжнім Django MigrationExecutor у дочірніх процесах: latest та історична finance.0003_transaction_branch з її реальними залежностями. Тестовий runner не відкривав свою default DB; кожен case працював із новою копією synthetic template. Перевірка виконувала справжній `scripts/preflight_data.py` CLI сім разів, а не підмінений inspect_schema/validate_snapshot. Усі DB, BLOB та media bytes після перевірки звірені з SHA/байтами до неї; original templates теж незмінні.

Перевірено:

1. Завершений FinancialIntent з джерелом приймається. Документ має BinaryField із нульовим байтом та всіма 256 значеннями байта; ChatFile збережений разом з архівним ChatMessage. Два preflight-запуски не змінюють DB/байти/FK/PK. Маніфест повертає точні bytes/SHA файла й 123,45 EUR.
2. Окремий Django subprocess завершує atomic block з FinancialIntent NULL/NULL та закриває connection. Це committed orphan, а не тимчасовий claim. Preflight відмовляє з FINANCIAL_INTENT_WITHOUT_SOURCE, точним table/PK, без видалення/ремонту; повтор дає ту саму відмову. Сама schema лишається допустимою для тимчасового NULL/NULL.
3. Два різні keyed Transaction по 100,25 UAH з однаковою датою лишаються різними PK. Preflight повертає candidate/unlinked попередження, confirmed_duplicate=false, stop_required=false; жоден запис не видаляється чи зливається. Повторний preflight зберігає обидва факти й суму 200,50 UAH окремо від EUR. Поточний технічний can_migrate=true з warnings не є підтвердженням банківських фактів або дозволом production cutover.
4. Справжня відома історична finance-схема без ERP не є пошкодженою metadata: schema complete/known_migrations=true, profile=historical. Але accounting incomplete, can_migrate=false, SCHEMA_MISSING та SOURCE_RECONCILIATION_INCOMPLETE явні. Preflight не добудовує відсутні таблиці заради зеленого результату.

Документи перевірки: `a07_data_preflight.log`, `a07_data_preflight_before.json`, `a07_data_preflight_after.json`, `A07_DATA_PREFLIGHT_MANIFEST.json`. Чотири файли product scope (preflight_data/schema_preflight/data_transfer/reconcile_data) та набір тестів мають той самий SHA до/після: **true**. SHA набору: `75570ebbd718d1ed99fe332364c084d18e9d2fb9e3ba4a6e17b458c0f7499f0c`.

PostgreSQL, transfer target і production cutover цим набором не перевіряються. Оригінальні бази й checkout агент не змінював.

## Точні ID

- `erp.test_data_preflight.DataPreflightAdmissionTests.test_complete_intent_document_and_archived_file_are_accepted_without_changing_bytes`
- `erp.test_data_preflight.DataPreflightAdmissionTests.test_committed_financial_intent_without_source_is_refused_without_repair`
- `erp.test_data_preflight.DataPreflightAdmissionTests.test_equal_amount_date_expenses_remain_candidates_and_keep_distinct_ids`
- `erp.test_data_preflight.DataPreflightAdmissionTests.test_known_incomplete_historical_schema_is_explicitly_refused_without_new_tables`
