# A07: перевірка схеми SQLite-знімка

Готова чернетка: `a07_schema_preflight.py`, API `inspect_schema(path) -> dict`.
Checkout і справжні бази не змінювалися та не відкривалися. Усі перевірені
джерела створені заново в `tmp` справжнім `MigrationExecutor`.

## Що доведено виконанням

SQLite 3.53.1: **16/16 окремих випадків** пройшли очікуваний результат.

| Випадок | Фактичний результат |
|---|---|
| Усі поточні міграції, включно з A07 | `latest`, 45 таблиць, 0 findings |
| ERP 0001 / finance 0006 / operations 0004 та решта відомих міграцій | `historical`, 45 таблиць, 0 findings |
| Recorder актуальний, але таблиці немає | `missing_table`, відмова |
| Видалено CHECK невід’ємного залишку | `checks_mismatch`, відмова |
| CHECK ослаблено до −1 | `checks_mismatch`, відмова |
| Видалено UNIQUE | `unique_mismatch`, відмова |
| FK посилається на іншу таблицю | `foreign_keys_mismatch`, відмова |
| FK перестав бути deferred | `foreign_key_deferral_mismatch`, відмова |
| Втрачено NOT NULL | `column_definition_mismatch`, відмова |
| Змінено SQLite affinity | `column_definition_mismatch`, відмова |
| Додано інший SQL DEFAULT | `column_definition_mismatch`, відмова |
| PRIMARY KEY замінено на UNIQUE | `pk_mismatch`, відмова |
| Невідома таблиця | `unknown_table`, відмова |
| Невідома міграція | `unknown_migrations`, відмова |
| Recorder не містить потрібної залежності | `inconsistent_migration_history`, відмова |
| Змінено лише ім’я CHECK і стиль лапок його стовпця | Семантично тотожна схема прийнята |

Кожна deliberate-drift база перебудована справжнім SQL; результати SQLite
не підмінялись. `--fake` і `writable_schema` не використовувались.
SHA всіх перевірених джерел та початкового synthetic fixture залишилися незмінними.

Фактичні звіти:

- `a07_schema_latest_probe/schema.json`
- `a07_schema_historical_probe/schema.json`
- `a07_schema_drift_probe/summary.json` і окремі 14 JSON

Відтворення: `a07_schema_synthetic_probe.py <новий каталог>`;
для історичного профілю додати `--historical`. `a07_schema_drift_probe.py`
використовує лише конкретний synthetic fixture і створює новий каталог;
наявний результат не затирає. Python: `demo-check-env/bin/python -B`,
`BOS_TEST_DEPENDENCIES` — чинний runtime каталог залежностей.

## Контракт

Джерело відкривається як `mode=ro&immutable=1`, додатково `query_only=ON`.
Наявні `-wal`, `-shm` або `-journal` заборонені. Після читання перевіряються
SHA та поява sidecars. З’єднання явно закривається.

`MigrationLoader(None)` бере граф із переглянутого коду. Точна множина
applied-міграцій визначає `ProjectState`; залежності перевіряються. Схема
цього стану створюється `schema_editor` в іншій новій тимчасовій SQLite,
без запуску міграцій на джерелі. Порівнюються PRAGMA та нормалізовані CHECK:
стовпці, affinity, SQL defaults, nullability, PK, FK із діями й deferral,
UNIQUE із collation/порядком/умовою, AUTOINCREMENT, STRICT і WITHOUT ROWID.
Python defaults не прирівнюються до SQL defaults.

`tables` містить типізовані описи з історичного стану, включно з M2M та
`django_migrations`. `sqlite_sequence` зберігається окремо.
Є actual/expected structural proof, SHA схеми й стану міграцій.
`DateTimeField.sqlite_naive_utc` походить із явно активного
`configured_profile.USE_TZ`; інспектор не може встановити часовий пояс
старої сторонньої програми з самих SQLite-рядків. Для `ChatFile.file`
явно задано `file_size_column='size'`.

`can_migrate=True` означає лише структурну відповідність відомому профілю.
Перевірку значень, файлів, cross-row інваріантів і транспорт виконує окремий
typed transfer. `historical` не дозволяє безпосередній імпорт до latest:
потрібна окрема контрольована staging-міграція і новий export.

Невідомі міграції/таблиці, unmanaged таблиці, view/trigger, невідомі типи,
непідтримані expression UNIQUE або ON CONFLICT, а також історія зі
складним replacement/squash дають явну відмову. Це не мовчазний skip.
Довільно різні, хоча логічно еквівалентні CHECK не доводяться математично:
окрім безпечної нормалізації лапок/пробілів/зовнішніх дужок/операторів
вони вважаються різними й потребують окремої перевірки.

PostgreSQL, Windows, браузер, backup/install gates і випуск продукту
цими результатами не перевірені та не прийняті.
