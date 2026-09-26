# A07 · незалежні DB-межі та безпечні SQLite CHECK міграції

Дата: 11.09.2026. Агент a06_finance_tests. **Локально: 12/12 DB-методів і 3/3 постійних migration-методів пройшли.** Другі справді виконали 7 окремих SQLite subprocess сценаріїв. Це не приймання PostgreSQL, реального перенесення клієнтської бази або всього A07.

Checkout і оригінальні SQLite цей агент не змінював. Усі джерела й DDL-проби — у tmp на нових синтетичних файлах. Root інтегрує код і повторно перевіряє загальний source SHA.

## Передача

| Тимчасовий файл | Постійний шлях |
|---|---|
| `a07_db_boundary_tests.py` | `erp/test_database_boundaries.py` |
| `a07_migration_operations.py` | `boss_project/migration_operations.py` |
| `a07_finance_0007_money_boundaries.py` | `finance/migrations/0007_money_boundaries.py` |
| `a07_operations_0005_invoice_boundaries.py` | `operations/migrations/0005_invoice_boundaries.py` |
| `a07_erp_0002_row_boundaries.py` | `erp/migrations/0002_row_boundaries.py` |
| `a07_check_constraint_upgrade.py` | `scripts/check_constraint_upgrade.py` |
| `a07_test_constraint_upgrade.py` | `erp/test_constraint_upgrade.py` |

Міграції містять 20 локальних CHECK: 4 finance, 3 Invoice, 13 ERP. Meta-обмеження моделей root має лишити синхронними зі станом міграцій. Операція серіалізується як `boss_project.migration_operations.PreserveSequenceAddConstraint`; цей import path стає частиною історії міграцій і має зберігатися.

## Чесний red і виправлення

`a07_db_before.log`: 12 методів, **37 падінь subTests у 11 методах, errors=0**, один позитивний метод пройшов. Реальні SQL UPDATE / QuerySet.update обходили model.clean/serializer. Red не підміняє SQL і не додає штучний trigger замість відсутнього CHECK.

`a07_db_before_schema.json` / `a07_db_after_red_schema.json`: ті самі моделі та всі міграції трьох застосунків до/після. SHA карти schema: `0e4e3b96649e12aa0a22c40d590b25de5eec55888479afb4980709d632ca6605`. Початковий тестовий код збережено в `a07_db_tests_original_red.py`, SHA `73b390f6127106867a7cc4a6d59a04ff8e5309ddd18ac3f51ed6e9326bb75113`; відновлення точно звірене з зафіксованим pre-run SHA.

Після red лише уточнено переносний клас помилки для трьох явних numeric capacity випадків: PostgreSQL може дати DataError ще до CHECK, тоді як SQLite дає IntegrityError від CHECK. Для інших порушень DataError не приймається. SQLite red від цього не змінюється; business assertions, межі та rollback не послаблено. Старі тести не редагувалися.

Звичайний AddConstraint спочатку давав 12/12, але окрема реальна upgrade-проба виявила **скидання sqlite_sequence з 90001 до 7** на таблиці з живим PK 7: `a07_migration_probe_results.json`, case `sequence`, exit 1. Це дефект сумісності першого draft, не твердження про зміни робочої бази. Початкові migration drafts і probe збережені в `a07_original_constraint_drafts/`.

Мінімальне виправлення — підклас AddConstraint. Він читає high-water лише таблиці цієї операції, виконує стандартний DDL і на SQLite відновлює max(old,current) у тій самій atomic migration. Domain rows не перезаписуються. Та сама поведінка працює при reverse. На PostgreSQL обробка sqlite_sequence не виконується. Помилка DDL не запускає додаткових SQL у зламаній транзакції. NULL/від’ємний/нецілий або неоднозначний sequence не ремонтується автоматично.

## Результати

- `a07_db_final.log`: **12 тестів, 0,088 с, exit 0**.
- `a07_permanent_upgrade.log`: **3 тести, 5,280 с, exit 0**, усі 7 `BOS_A07_MIGRATION` записів мають actual backend SQLite 3.53.1.
- Після forward і reverse непорожня та порожня таблиці зберігають 90001; два INSERT дають 90002/90003. Якщо старий high-water 5 нижчий за чинний max PK 7, лишається 7, наступні IDs 8/9.
- Невалідні старі Transaction, Invoice та Purchase відхиляються; рядки, DDL й sequence незмінні, migration не позначена застосованою. Invoice відмова на другому CHECK відкочує і попередній успішний DDL у тій самій міграції.
- NULL sequence відхиляється до DDL без зміни джерела: `a07_sequence_null_refusal.json` і постійний сьомий probe.
- `a07_migration_operation_serialization.json`: stable module path підтверджено справжнім OperationWriter, ProjectState дорівнює стандартному AddConstraint.

Для draft-перевірок використано тимчасовий MIGRATION_MODULES профіль і копію тільки Python-пакета boss_project у tmp, щоб імпортувати helper за його майбутнім сталим шляхом. Це не підміна DB/команд: DDL і SQLite виконувалися реально. Профіль/копія не є частиною продукту. Один проміжний запуск мав помилку шляхів імпорту helper; тести тоді не почалися. `a07_db_draft_fixed.log` збережений як помилка тимчасового harness, не як дефект BoS. Після виправлення робочого каталогу всі методи виконані.

## Межі сумісності

1. Не застосовувати нові CHECK автоматично до робочих файлів. Невалідна історія має пройти refusal preflight на копії; жодного trim/round/dedup/backfill. Поточні constraint drafts не містять ремонту даних.
2. Signed Movement.quantity, нульові released Reservation, zero-price Invoice amount=paid=0, рівність received/produced/invoiced/shipped з кількістю й тимчасовий FinancialIntent NULL/NULL лишилися допустимими. DB CHECK status→paid/source не вводився: старі inconsistent Salary fixtures лишаються джерелом A02 перевірки, не переписуються.
3. Ці локальні CHECK не замінюють валідацію точності до SQL, типів legacy SQLite, JSON/Binary, міжрядкових FK-сум, документів і валютної узгодженості пов’язаних сутностей. Усі межі вхідних даних та повний preflight залишаються частиною root A07.
4. `sqlmigrate` у режимі collect_sql для SQLite явно відмовляє: статичний SQL не може зафіксувати runtime source high-water. Для виконання потрібен звичайний migrate на перевіреній копії. На PostgreSQL ця SQLite-гілка пропускається.
5. Постійний CLI приймає один case та вимагає свіжу абсолютну `check_<32hex>.sqlite3` поза проєктом. Він фіксує A06 baselines і не підхоплює майбутні сторонні leaf migrations. Import модуля не виконує DDL. SimpleTestCase не користується parent DB; повідомлення Django «unused database» не означає skip тестів. Кожен дочірній процес явно запускає SQLite навіть у зовнішньому PostgreSQL suite й не видає це за PG-доказ.

## Точні ID

- `erp.test_database_boundaries.DatabaseMoneyStockBoundaryTests.test_invoice_amount_capacity_and_paid_range_are_enforced_by_sql`
- `erp.test_database_boundaries.DatabaseMoneyStockBoundaryTests.test_purchase_quantity_and_received_are_bounded_in_database`
- `erp.test_database_boundaries.DatabaseMoneyStockBoundaryTests.test_purchase_price_and_extras_cannot_be_negative_via_raw_sql`
- `erp.test_database_boundaries.DatabaseMoneyStockBoundaryTests.test_production_quantity_and_produced_are_bounded_in_database`
- `erp.test_database_boundaries.DatabaseMoneyStockBoundaryTests.test_production_planned_and_actual_cost_cannot_be_negative_via_sql`
- `erp.test_database_boundaries.DatabaseMoneyStockBoundaryTests.test_sales_line_invoiced_shipped_quantity_chain_and_price`
- `erp.test_database_boundaries.DatabaseMoneyStockBoundaryTests.test_lot_unit_cost_cannot_be_negative_via_raw_sql`
- `erp.test_database_boundaries.DatabaseMoneyStockBoundaryTests.test_movement_cost_cannot_be_negative_but_quantity_stays_signed`
- `erp.test_database_boundaries.DatabaseMoneyStockBoundaryTests.test_finance_positive_amount_and_field_capacity_also_hold_below_commands`
- `erp.test_database_boundaries.DatabaseMoneyStockBoundaryTests.test_existing_three_currency_domain_is_enforced_below_writers`
- `erp.test_database_boundaries.DatabaseMoneyStockBoundaryTests.test_valid_zero_equal_maximum_and_temporary_boundaries_remain_legal`
- `erp.test_database_boundaries.DatabaseMoneyStockBoundaryTests.test_invoice_constraint_failure_rolls_back_prior_stock_line_and_audit_writes`
- `erp.test_constraint_upgrade.ConstraintUpgradeTests.test_invalid_old_rows_refuse_each_migration_without_partial_ddl`
- `erp.test_constraint_upgrade.ConstraintUpgradeTests.test_forward_reverse_high_water_and_next_ids_for_sparse_empty_and_larger_current`
- `erp.test_constraint_upgrade.ConstraintUpgradeTests.test_null_high_water_is_refused_without_repairing_source_metadata`
