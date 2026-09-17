# A07: native PostgreSQL schema admission — підготовлено, runtime UNRUN

Файл `a07_schema_postgres.py` призначений для `scripts/schema_postgres.py`.
Є лише перевірка синтаксису. Реальний PostgreSQL тут не підключався; цією
чернеткою не приймаються PG transport, gates, CI або реліз.

API:

```python
inspect_postgres(connection, *, django_config, owned_guard) -> dict
```

`connection` — raw psycopg connection з `autocommit=True`, без відкритої
транзакції. `owned_guard` — точний канонічний
`scripts.data_transfer.ConnectionOwnership`, виданий реєстром після успішного
створення саме цієї нової БД. Довільний об’єкт із методом `assert_owned` не
приймається. Перевірка типу виконується до будь-якого SQL на аргументі.

`django_config` явно передає ENGINE, NAME, USER, PASSWORD, HOST, PORT та OPTIONS.
NAME мусить дорівнювати щойно створеному `bos_verify_<16hex>`.
Паролі/DSN не відновлюються з raw connection і не потрапляють у результати
або повідомлення про помилки. Відокремлений Django alias має повторно
підтвердити ту саму фактичну БД, користувача, сервер і кодування UTF8.

Інтеграція з фабрикою:

```python
target = new_disposable_postgres(
    provision=provision_actual_new_database,
    inspect_target=lambda conn, owned_guard: inspect_postgres(
        conn, django_config=explicit_config_for_minted_database,
        owned_guard=owned_guard,
    ),
)
```

Потрібен той самий callback з guard для повторної schema-перевірки перед
імпортом. `ConnectionOwnership` перевіряється його канонічним методом,
тому підклас/перевизначений метод не може підмінити registry proof.

Фактичний `django_migrations` визначає `ProjectState`, а не поточні ORM
моделі без історії. Для цього стану `schema_editor` створює еталон у новій
випадковій namespace тієї самої owned disposable БД. Міграції на public
не запускаються. SQL SQLite не перекладається вручну у PostgreSQL.

Порівнюються нативні `pg_catalog` факти: стовпці з повними типами/typmod,
nullability, identity/generated/default, collation; PK/UNIQUE/FK/CHECK
з validated/deferrable/діями; індекси з expressions/predicate/opclass,
NULLS NOT DISTINCT та include/order; структура й власник sequences.
Row security, policies, user triggers/rules, невідомі relation/schema
також не зникають із перевірки. Довільна невідома функціональність дає
відмову, а не skip. PostgreSQL 14+ є явним підтриманим профілем чернетки;
фактична версія потрапляє в runtime proof лише під час справжнього виклику.

Cleanup перевіряє namespace OID/owner, дозволяє лише власний набір таблиць
і застосовує `DROP TABLE ... RESTRICT`, потім `DROP SCHEMA ... RESTRICT`.
`CASCADE`, `DROP DATABASE`, очищення public або чужих schemas відсутні.
Зовнішня залежність блокує cleanup і залишає результат червоним.
Структура public, applied recorder та сторонні schemas перечитуються
після перевірки. Невдалий cleanup також забороняє `complete=True`.

`tables` і `migration_state_hash` мають той самий логічний формат, що в
SQLite inspector. `postgres_schema_hash` та actual/expected native proof
зберігаються окремо; це не твердження про тотожність SQL двох СУБД.

До PG acceptance потрібно виконати справжній CI-прогін: fresh latest,
known historical, table/constraint/index/type drift, неправильний guard
без доступу до переданого connection, відмову на іншій БД, успішний
reference cleanup і RESTRICT-відмову за зовнішньої залежності. Підміна
pg_catalog відповідей або лише green syntax не замінює ці перевірки.
