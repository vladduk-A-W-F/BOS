# B02: виконуваний backend кандидат

Статус: ізольований кандидат для інтеграції root; приймання повного BoS ще потребує canonical full verify. Змінено лише власну копію в tmp. Оригінальні DB/media не відкривалися і не переносилися.

Реалізовано CEO-only JSON/manifest+CSV preview → чинний confirm із proposal ID → один atomic batch/event/receipt. Підтримано counterparty, buy catalog, warehouse, pending opening lots, незавершені SO/позиції та історичні remaining supplier PO. Для останніх збережено первинну кількість/отримане до зрізу/залишок/прострочену дату; минулі приймання й платежі не вигадуються. Звичайний B01 purchase writer зберігає свої обов’язкові погодження; typed in-process importer context недоступний довільному JSON.

Джерело має namespace + UUID4, стабільні external IDs, canonical Decimal суми окремо за EUR/UAH/USD, exact source-part SHA. Explicit bindings не переписують source bytes; mappings показують create/bind/reuse і поточний target ID. Повторне підтвердження повертає первинний receipt. Нові записи повторно перевіряють чинні довідники/документні bytes/права під mutex; виконаний результат перечитується перед commit. SQL failure/value tampering відкочує пакет цілком.

Фактичні вузькі докази:

- Початковий red: відсутні HTTP routes. Після реалізації перевірено багатовалютні суми, часткове приймання та незмінний replay, JSON/CSV еквівалентність, конфлікти джерел/UUID/складу, stale права/owner, explicit bindings, malformed bytes/types, реальний checksum tamper, фактичний пізній SQL abort і AFTER INSERT зміна ціни.
- Review red → green: нечисловий UUID/source text і bool/float control counts; current_targets для повного reuse/mixed; відсутній binding mapping; new rows із уже непридатним reused reference.
- Pre-CSRF bounded-body helper: baseline hooks фактично пропускали downstream parsing; нові hooks відмовляють до parser. Missing/forged Content-Length presented stream читає рівно максимум160KiB+1. Глобальний CSRF не вимкнено; реальний multipart без CSRF має403. Upstream WSGI framing поза цим proof.
- Decimal red: справжній HTTP preview500 при ambient precision6/ROUND_DOWN. Green: точні source308641.95000/current308641.95 та1234567.89 після fixed integer-cent conversion і localcontext50; зовнішній context не змінюється.
- Нові чотири routes:180 фактичних request combinations (5roles×9methods×4routes) з чинним незалежним role/status/response/canary oracle; exact resolver manifest176 definitions.
- Gate5 additive:88/88 methods,92/92 ERP case/currency records. Старі84/89/26 буквально збережено й закріплено SHA baseline db06988865d19aff6aae73c1300c7127ff77df76a8c70a8ca3f5f1ab8c56f462. Додано4 methods,3currency records,action import_batch.
- Populated ImportBatch1/ImportIdentity9 пройшли справжній SQLite snapshot → повний typed export → нову власну мігровану DB → exact47table/sequence/media/logical-schema manifest comparison. Source rows/receipt/snapshot/IDs незмінні; повтор source proposal повернув той самий receipt без нової події.
- Populated B02 reverse migration відмовила без schema/rows/migrations змін. Старий B01 reverse test спочатку пінує справжню0003 при порожніх B02 ledgers, створює справжній approved PO черезHTTP, а далі зберігає state() та всі попередні assertions буквально. Red full44 бачив лише removed0004 migration receipt; після setup-only pin44/44green, B01 changed=[].
- Root передав три SHA-checked compatibility files: точні old45+2 таблиці та native restore checker. Його native proof12/12 green перед останнім додатковим restored-replay snapshot assertion; цей final assertion виконується root у full verify, тут не оголошується окремо пройденим.

Серверний шаблон має27 синтетичних рядків: ненульові EUR/UAH/USD; відповідальний задається з чинних employees. Реальні JSON та generated manifest+CSV пройшли preview.

Не перевірено цим кандидатом: PostgreSQL виконання, робочі клієнтські дані, публічний сервер, весь canonical full verify та UI. Наявні відкладені A09/A10 межі не змінювалися. Новий endpoint не читає обхідним шляхом WSGI/HTTP framing і не виконує full database restore.

Фінальний виконаний focused набір:45/45green,15.342s (`evidence/final-frozen.log`); включає попередні18 B01 tests і27 B02 tests.
