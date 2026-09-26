# B01 · Сумісність синтетичних transfer fixtures

Дата: 12.09.2026. Тільки власний code-only кандидат; canonical B01 fullverify source не редагувався. Оригінальні робочі БД/медіа не читалися, не копіювалися й не змінювалися. Усі SQL-сценарії самі створюють нові синтетичні SQLite джерела/цілі та власні файли в TemporaryDirectory.

## Причини й мінімальні зміни

1. `fixtures/synthetic/transfer.py:249` створював нову пряму закупівлю без нового обов’язкового B01 `direct_reason`. Цей єдиний purchase writer у transfer fixtures викликається для EUR/USD/UAH. Додано тільки змістовне обґрунтування синтетичної закупівлі. Ціна, quantities, extras, строки, приймання, IDs та старі assertions незмінні. Це не legacy backfill.
2. Після виправлення seed проявився старий A08 highwater setup: він робив downgrade operations→0005, а dependency graph знімав також B01 erp.0003. Нові PO вже мали законний snapshot; reverse guard правильно відмовляв. Guard і production `_preserve` не змінювалися. Для highwater додано окреме NEW джерело з реально створеною pre-A08/pre-B01 схемою через MigrationExecutor, трьома історичними Document і справжнім ChatFile. Усі інші таблиці створюються в історичному migration state; PO порожні, нові snapshot ніколи не створюються й не стираються. На виданій власній копії виконуються лише A08 operations0006 та ai0009.

Збережено всі попередні highwater assertions: `_preserve(before, after, schema=True)` перевіряє всі таблиці/рядки/PK/міграційні ID/applied/nullable поля та всі sequences; seq Document=400001, ChatFile=500001; справжній наступний Document ID=400002. Додано фактичну перевірку відсутності B01/A08 нових колонок у старій схемі, рівність bytes/hash історичного source DB/media після upgrade та незмінність переданого сучасного синтетичного source. A08 highwater тепер перевіряє populated Document/Chat, а не populated PO. Повне збереження сучасних PO/snapshots залишається в тому ж green full-model typed transfer (45 таблиць) і в існуючих B01 legacy/null migration та lossy reverse refusal тестах. Останні B01 тести не повторювалися в цьому bounded прогоні; їх assertions і код незмінні.

## Фактичні прогони

| Evidence | Результат |
|---|---|
| `evidence/red.log` | 1 actual failure / 2.631s: full transfer seed → missing direct_reason. |
| `evidence/green.log` (перший after, діагностична назва) | 10/11 / 19.505s: full transfer і missing media вже green; один A08 highwater правильно впав на B01 reverse guard. Це не повністю green лог. |
| `evidence/highwater-green.log` | 1/1 / 4.386s: справжній історичний source + A08 upgrade. |
| `evidence/final-green.log` | 11/11 / 19.621s, без пропуску methods: full transfer, missing media, всі 9 A08 migration cases. Додаткова рівність hash історичного source уже включена. |

Команда остаточного запуску:

```sh
PYTHONDONTWRITEBYTECODE=1 DJANGO_SETTINGS_MODULE=verification_settings BOS_VERIFY_DB=sqlite BOS_TEST_DB_NAME=/workspace/scratch/c7b51e996a9f/tmp/b01_transfer_fixture_fix/check_final.sqlite3 BOS_TEST_MEDIA=/workspace/scratch/c7b51e996a9f/tmp/b01_transfer_fixture_fix/media /workspace/scratch/c7b51e996a9f/demo-check-env/bin/python -B manage.py test erp.test_full_data_transfer erp.test_preflight_missing_media operations.test_document_migration --noinput -v 2
```

CWD — `tmp/b01_transfer_fixture_fix/source`. Усі substantive SQL виконує канонічний ownership-protected runner у нових child DB. `Skipping setup of unused database(s): default` стосується зовнішнього unittest контейнера; 11 actual subprocess сценаріїв виконані, не пропущені.

Кандидат отримано через канонічний code-only package_server: version0.2.11-dev, base sourceSHA8266f1b1750e7e492d6ecb486af3d2c6717478c4dc1da42e191dad5ace8eb07c,269 runtime files,0database files; окремо скопійовано 4 regular code/JSON fixtures. Initial manifests збережені як BASE_SOURCE_PACKAGE.json і FIXTURE_BASE_SHA.json; edited кандидат не видається за immutable runtime package.

Інтеграція: лише два файли з `B01_TRANSFER_COMPATIBILITY.patch`/manifest. Нових product writers, migrations або послаблень доменного допуску немає. Canonical fullverify запускає root після завершення замороженого full20; цей scoped тест не заміняє PostgreSQL/Windows/клієнтське приймання.
