# A07: контракт типізованого перенесення

Статус: незалежна **чернетка для синтетичної репетиції**, 11.09.2026. Checkout і справжні робочі БД не змінювалися та не читалися. Це нижній транспортний рівень, не production migration runner і не приймання A07.

Файли поряд із цим документом:

- `a07_transfer_draft.py`: codec, validation/export, disposable target factories, transactional import.
- `a07_transfer_tests.py`: 14 фактично виконаних SQLite тестів із SQL INSERT, FK, реальним trigger rollback, файлами та sequence proof inserts.
- `a07_transfer_sqlite.log`: останній лог; усі 14 пройшли. Це перший набір перевірок нового API; він **не видається за pre-fix red baseline**.
- `a07_schema_preflight.py`: окрема чернетка Fermat. Обов’язковий inspector actual SQLite schema проти ProjectState за recorder; транспорт її не замінює.

## API

```python
validate_snapshot(sqlite_path, media_root, *, inspect_schema) -> manifest
export_snapshot(sqlite_path, media_root, bundle_dir, *, inspect_schema) -> manifest
new_disposable_sqlite(work_root, *, bootstrap, inspect_schema) -> DisposableTarget
new_disposable_postgres(*, provision, inspect_target) -> DisposableTarget
import_to_disposable(bundle_dir, target, *, verify_actual_schema) -> receipt
```

`inspect_schema` — функція Fermat. Поля: `tables[name].columns` із `name`, `kind`, `django_type`, `nullable`, `pk_order`, `max_length`, `max_digits`, `decimal_places`, `fk`, `auto_increment`; окремо `sqlite_schema_hash`, `migration_state`, `migration_state_hash`, `complete`, `can_migrate`, `findings`. Для `DateTimeField` потрібне явне `sqlite_naive_utc=True` лише для `USE_TZ=True`; для `ChatFile.file` — `file_size_column='size'`. `django_migrations` та auto-created M2M включені як звичайні typed tables. `sqlite_sequence` експортується окремо.

`bootstrap(conn)` створює перевірену цільову схему лише в новому SQLite файлі, який сама factory відкрила exclusive (`xb`). Міграції виконує orchestration root; транспорт не підробляє migration recorder. До імпорту дозволені bootstrap рядки лише в `django_migrations`, `django_content_type`, `auth_permission`; усі інші таблиці мають бути порожні. UUID-назва цілі, справжня identity connection і fingerprint bootstrap зафіксовані при створенні factory. Довільно сконструйований `DisposableTarget`, змінена connection/identity або повторне використання відхиляються.

`provision(name)` для PostgreSQL має **створити** нову базу із заданим випадковим `bos_verify_<16hex>` та виконати міграції; при колізії CREATE DATABASE відмовити, не під’єднувати стару. Повертає справжню psycopg connection з `autocommit=True`. Factory перевіряє current_database, public schema та UTF8. Після цього видається mint-only `ConnectionOwnership` із методом `assert_owned(connection)`; конструктор без зареєстрованого успішного створення не дає capability. Його отримує `inspect_target(connection, owned_guard=guard)`; далі він доступний як `target.owned_guard`. Root адаптує до `inspect_postgres(connection, django_config=..., owned_guard=guard)` Fermat. `verify_actual_schema(target)` зобов’язана повторно перевірити фактичні PostgreSQL columns/constraints проти того самого migration state; повернути source descriptor без читання каталогу недостатньо. Гілка PostgreSQL написана, але **не виконувалася**; inspector/provisioner цей draft не реалізує.

## Межа між transport і бізнесовим допуском

Нижній рівень перевіряє схему, типи, цілісність SQLite/FK, медіа та точність перенесення. Manifest і receipt прямо містять `not_checked: business_reconciliation`. Це не дозвіл мігрувати робочу установку.

За рішенням root high-level preflight/rehearsal перед імпортом запускає реальний `scripts.reconcile_data.analyze` на **тій самій** sealed snapshot та прив’язує звіт до її SHA. Відмова: неповне покриття, `stop_required`, класи `confirmed_monetary`, `discrepancy`, `not_checked`. `candidate`/`unlinked` лишаються видимими фактами для перевірки, а не доказом дублювання. Усі їхні рядки зберігаються; немає dedup за сумою/датою, cleanup або repair.

High-level також перевіряє committed `FinancialIntent` без source, конкретні предметні JSON форми, поточні ledger/stock invariants та дозволені історичні профілі. Відомий historical export не можна імпортувати до іншого migration state: спочатку окрема staging copy та відомі міграції, потім новий preflight/export. Розпізнавання схожих назв колонок або автоматичного mapping немає.

## Формат пакета та manifest

Пакет: `schema.json`, `manifest.json`, `tables/NNNN.jsonl`, `media/<original-relative-path>`, `COMPLETE`. Кожна таблиця має файл, у тому числі порожня; schema зберігається повністю й має SHA. Маркер `COMPLETE` із SHA manifest записується останнім. Невдалий export лишається неприйнятним staging, ніколи не стає target/live.

Кожний рядок — масив tagged cells у явному порядку колонок. Приклади:

| Тип | Точне представлення |
|---|---|
| SQL NULL | `{"t":"null"}` |
| JSON null | `{"t":"json","v":"null"}` |
| Decimal | `{"t":"decimal","v":"0.1"}` — числове значення без округлення; scale визначає model descriptor |
| Integer / UUID | десятковий рядок / canonical UUID, без зміни PK/FK |
| FloatField | `float.hex()` для exact binary double; NaN/Infinity відхилено |
| JSON | canonical JSON text; exact Decimal parsing для numeric tokens; bool/string/null збережені, array order збережено |
| Binary | base64, bytes і фактичний SHA-256 |
| DateTime | UTC ISO із шістьма microseconds; date-only окремим типом |
| File | вихідний відносний шлях; незалежний запис manifest із bytes/SHA |

Manifest містить source snapshot SHA; фактичний SQLite schema hash; повний migration state/hash; logical field descriptor hash; по **кожній** таблиці count, full row digest, PK digest, FK digest, Decimal totals за валютою і додатково `decimal_totals_by_direction` для таблиць із direction. JSON/Binary/archive/date/digests входять у row hash. Для перевірки конкретного ID повні typed PK/FK лишаються в row files. Sequences містять actual stored `last_value`, `max_pk`, `high_water`, column, включно з порожніми таблицями.

Media manifest містить усі регулярні файли MEDIA_ROOT, включно з непов’язаними, та окремі посилання FileField за table/PK/column/path. Перевіряються шлях, bytes і SHA кожного файла. Старий `Document.checksum` зберігається буквально; він не оголошується універсально SHA(content), бо text-only legacy seed має інший provenance. Фактичний SHA blob додається окремо.

## Строгі відмови

До читання значень — `inspect_schema` і порівняння з фактичною migration-state схемою; потім raw SQLite cursor без Django-конвертера/quantize. Snapshot відкривається `mode=ro&immutable=1`, жодних `-wal/-shm/-journal`, SHA повторно перевіряється після read та export. Спочатку SQLite backup API чинного `make_snapshot` створює узгоджену копію; просте копіювання live WAL-файла не є допустимою підготовкою. Джерело не мігрується.

Відмовляємо при schema drift, невідомому типі, PK/FK conflict, NUL/непарному surrogate, перевищенні довжини, nonfinite, надлишковій Decimal scale/overflow, duplicate JSON keys, JSON numeric поза підтриманими межами, missing/wrong-size media, symlink/path traversal, зміні snapshot/bundle/media. JSON numbers розбираються через Decimal, не float. Decimal magnitude перевіряється через tuple/adjusted без `abs/normalize/quantize`, які залежать від Decimal context. Вхід `1e9999999` явно відхиляється без `decimal.Overflow` від abs.

Для SQLite REAL у Decimal колонці codec використовує збережене binary value та його shortest decimal representation; перевіряє scale і однозначність сусідніх model quanta. **Первісний текст до запису в SQLite відновити неможливо**; transcript не обіцяє знайти вже втрачені цифри. `PRECISION_UNCERTAIN` відмовляє при злитті сусідніх quantum. Високоточні суми рахуються через Decimal із достатнім локальним context; різні валюти не зводяться в одну суму.

Помилка row codec містить table, структурний PK, column і code; не друкує description, document text, HR або raw value. Transport bundle містить самі дані й призначений лише для приватної репетиції: каталог 0700, row/media/schema/manifest файли 0600.

## Транзакція та службові IDs

Target перевіряється до початку: його випадкова назва/connection, actual schema, той самий migration state, лише дозволений bootstrap. У транзакції повторно звіряється повний fingerprint bootstrap; нові сторонні рядки спричиняють відмову та лишаються збереженими.

SQLite використовує `BEGIN IMMEDIATE`; PostgreSQL — `BEGIN`, `ACCESS EXCLUSIVE` на переносимих таблицях, `SET CONSTRAINTS ALL DEFERRED`. Чинні FK/UNIQUE/CHECK не вимикаються. Далі `DELETE` лише трьох bootstrap-таблиць (без CASCADE/TRUNCATE) і параметризовані INSERT **усіх** source rows, з точними IDs і datetime. ORM save, domain commands, auto timestamp та виконання proposal тут не викликаються.

Зберігаються source User/Group/ContentType/Permission IDs, відповідні M2M, admin-log ContentType FK, Employee user зв’язки та FinancialIntent hashes. Немає uncontrolled natural-key remap. Також буквально зберігаються source `django_migrations` rows/PK/timestamps після порівняння applied-state, auth/session/runtime tables включно. Це транспортне збереження; root визначає окремо, як інвалідовувати сесії при справжньому cutover, а не приховано в importer.

До commit: full rows/PK/FK/totals збігаються; FK перевірені; source high-water перенесено; sealed bundle/media повторно rehashed. Після commit знову читаються raw rows і перевіряється manifest. Media лишається в isolated bundle, **не** перемикається у live storage. ORM/HTTP сценарії після імпорту є окремим критерієм.

PostgreSQL sequence reset використовує `pg_get_serial_sequence` + `setval(high_water, is_called)`, лише для Auto/BigAuto columns. Zero/never-used sequence зберігає можливість першого ID=1. Оскільки PG sequences не відкочуються разом із row transaction, будь-яка import failure споживає guard: створену ціль треба відкинути; повторний import у неї заборонений. У draft немає автоматичного DROP DATABASE.

## Фактично перевірено та що ще лишається

14 unittest cases реально створюють нові SQLite файли й медіа. Серед них: повний transport round-trip із різними bootstrap IDs; archived highest PK; SQL NULL проти JSON null; exact великий JSON numeric; усі 256 binary bytes і legacy declared digest; UTC microseconds; Decimal `0.1+0.2` та currency/direction totals; empty-table sequence=340003; два справжні INSERT з IDs 340004/340005 і наступний sparse-table ID=99002. Source SHA незмінний. Реальний target trigger відхиляє пізній INSERT: усі rows і видалений bootstrap відкочуються. Решта тестів — явні негативні fixtures, а не симуляція успіху.

Міні-схема в цих 14 тестах має незалежний точний DDL hash, але **не є повною BoS схемою**. Потрібні окремі фактичні прогони: Fermat ProjectState + повний fixture Averroes/Hypatia; high-level reconcile gate; PostgreSQL actual schema inspector/provisioner і справжній SQL round-trip; sequence `last_value/is_called` inspection та два звичайні PG insert; forced PG rollback; ORM/HTTP після import; Windows/media filename/case semantics; повний verify. Ці пункти не позначено green.

Ще дві межі чернетки: усі rows тримаються в пам’яті для exact comparison (не масштабований production streaming); `verify_actual_schema` є обов’язковою довіреною інтеграцією, але PostgreSQL implementation поки зовнішня. High-level CLI має не дозволяти використовувати transport-only receipt як бізнесове приймання.
