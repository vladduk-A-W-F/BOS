# A07 · незалежне локальне приймання

Дата огляду: 11.09.2026, 21:55 UTC; доповнено після PG worker guard о 21:57 UTC. Checkout: `/workspace/sites/bos-original-refined`. Базовий HEAD під час огляду: `5bf3dbfc267038c0e7821c6c56b2df3ff273384f`; A07 ще перебуває в робочому дереві.

**Досягнуто консенсусу в перевіреному локальному обсязі A07. Невиправлених блокувальних зауважень для синтетичної SQLite-репетиції не виявлено.** Це не приймання PostgreSQL, Windows, релізу, реального клієнта або всіх 11 критеріїв. Фінальний загальний verify запускає root; його результат слід додати до підсумкового A07 evidence окремо.

Огляд виконано незалежно від автора інтеграції: прочитано `docs/PROGRESS_UA.md`, актуальні preflight/driver/transport, повний бізнес-оракул і replay helper, постійні інтеграційні тести, попередній review та фактичні журнали. Checkout не редагувався; оригінальні `db.sqlite3` і `BoS_Demo.sqlite3` не відкривалися. Цей огляд не запускав повторно вже зелені широкі набори. Наведені нижче результати підтверджено читанням evidence, а не оголошено незалежним повторним виконанням.

## Закриття попередніх зауважень

| Зауваження | Поточна реалізація й доказ |
|---|---|
| Worker приймав не видану поточним прогоном БД | `run_child` видає одноразовий випадковий ticket, прив'язаний до stage, exact database/backend, work directory, media, expected та minimum ID. `guard_worker` перевіряє ticket і nonce до `django.setup`, resolved absolute path, заборону symlink/checkout, шаблон і каталог БД. Початковий `runner-guard-before.log` містить реальне падіння; `runner-guard-after.log`: 1/1, OK. Самостійний guard-виклик без ticket більше не допускається. |
| Sequence proof перевіряв тільки MAX(pk) | Proof отримує high-water із manifest через той самий ticket і перевіряє `max(old_max, source_high_water) < first < second`. Працює на окремій похідній копії. Повний report: old_max=90001, high_water=90001, next IDs 90002 і 90003. Випадки high-water вище наявних рядків та порожньої таблиці окремо належать transport/upgrade тестам; цей повний fixture їх не підміняє. |
| Звірка не мала власного SHA джерела | `reconcile` обчислює SHA до/після read-only analyze, додає source_sha256. Admission також прив'язаний до незмінного snapshot. Export звіряє manifest SHA з `make_snapshot`, а завершення — із фізичними source/snapshot/target SHA. |
| Після переносу були тільки ORM-факти | `verify_replays` використовує справжню імпортовану session cookie, CSRF endpoint і HTTP confirm завершеного proposal; receipt точно збігається. На тій самій похідній proof-копії повторюються Salary.mark_paid та keyed financial commands у EUR/USD/UAH. Перевіряються первинні IDs, єдина зарплатна витрата та незмінні повні рядки, крім явно очікуваного збільшення службового ERP mutex на 1. Accepted target після proof фізично незмінний. |
| Committed FinancialIntent NULL/NULL проходив як завершений факт | High-level preflight явно відмовляє `FINANCIAL_INTENT_WITHOUT_SOURCE` з table/PK без ремонту. Постійний тест створює й завершує реальний atomic block, потім двічі викликає CLI і звіряє незмінність. Чинний CHECK не забороняє потрібний тимчасовий claim усередині write transaction. |
| Відсутній media-файл завершував preflight винятком без звіту | `OSError` перетворюється на FILE_ACCESS_CONFLICT у звіті з can_migrate=false. Збережено реальні before/after JSON та постійний CLI-тест: source/snapshot SHA незмінні, первинний файл лишився в повному media-наборі. |
| Різні витрати з однаковою сумою/датою могли бути трактовані як доведений дубль | Постійний тест з двома різними keyed Transaction перевіряє candidate/unlinked warning, confirmed_duplicate=false, окремі PK та збережені 200,50 UAH. Technical can_migrate з warnings не дає дозволу на production cutover або списання/об'єднання фактів. |

## Підтверджені локальні результати

| Evidence | Фактичний результат |
|---|---|
| `evidence/A07/boundaries-after-1.log` | 28/28, 13,039 с, OK. Writer/SQL boundaries та duplicate JSON refusal. |
| `evidence/A07/extreme-after.log` | 2/2, 0,855 с, OK. Великий finite Decimal відхиляється доменно, без HTTP 500 і змін джерел. |
| `evidence/A07/transport-schema-upgrade-after.log` | 37/37, 9,154 с, OK. Типізований transport, реальна migration-state schema inspection, upgrade/refusal та sequence preservation. |
| `evidence/A07/runner-guard-after.log` | 1/1, 0,036 с, OK. Refusal до доступу до невиданої БД. |
| `evidence/A07/pg-worker-guard-after.log` | 2/2, 0,070 с, OK після реального red на ticket без успішного CREATE proof. Перевірений guard; PostgreSQL сервер не підключався. |
| `evidence/A07/full-preflight-after.log` | 6/6, 15,083 с, OK. Повний transfer, чотири admission cases і missing-media CLI. `Skipping setup of unused database(s): default` означає, що SimpleTestCase не використовує default DB; самі шість тестів виконані й не пропущені. |
| `evidence/A07/full-transfer-first/report.json` | complete=true, фактично 45 таблиць, counts/PK/FK/typed row hashes, суми й файли збережені. Source незмінний, target незмінний після proof, повернення до source перевірене. |

Для кожної з трьох валют бізнес-оракул до/після показує: сировина 13, готовий залишок 2, вартість запасу 39, виробнича фактична вартість 12, рахунок 15, оплата 5, неоплачений залишок 10, фінансове надходження 200, витрата 100 і різниця 100. Ці факти обчислює незалежний ORM-оракул з джерельних рядків, а raw manifest додатково перевіряє всі 45 таблиць, включно із системними IDs та порожніми таблицями. Перенос не remap-ить ContentType/Permission, не викликає доменні save-побічні дії та не видаляє історію.

Target допускається тільки через фабрику нової БД, registry capability та повторну перевірку actual identity/schema/bootstrap. Реальні INSERT, constraints і deferred FK перевіряються в одній транзакції. Часткова невдача відкидає target для повторного використання; source не ремонтується. Bundle завершений тільки після запису COMPLETE й перевірки SHA. Manifest підтримує SQL NULL окремо від JSON null, точні Decimal, JSON numbers, Unicode та BinaryField bytes.

Початковий повний trial має source digest `8cadf18471827cd626934e736e9f0f0dc985abee41f8908cf457711f85a5aceb`; пізніший 6-test run — `e995a6f56141b37e0d40d43a6ccb530dfab6497c9f2a2a78568af307a60b882b`. Вони різні через наступні інтегровані зміни/тести; не слід подавати перший trial як запуск на остаточному SHA. Root повинен зафіксувати актуальний SHA та повний verify у підсумковому документі.

## Явні межі

- PostgreSQL і Windows **НЕ ЗАПУЩЕНО**. `rehearse_postgres` чесно відмовляє: native inspector/provisioner ще не інтегровані в цей runner. Додаткова реальна регресія виявила, що name ticket сам по собі не доводить успішний CREATE та власність PostgreSQL БД. Після правки PG worker безумовно відмовляє до django.setup/SQL; `pg-worker-guard-before.log` має реальне падіння, `pg-worker-guard-after.log` — 2/2 OK. Це захищена явна незавершеність PG-профілю, а не його приймання. Native schema drift tests, provisioner/CREATE ownership та повний PG transfer лишаються відкритими; синтаксична перевірка їх не замінює.
- Попереднє побажання канонічного сортування `media_references` і bootstrap fingerprint до hashing поки не реалізовано. У перевіреному SQLite шляху порядок стабільний і round-trip пройшов. Перед PG acceptance це слід вирішити й перевірити на реальному heap order, щоб уникнути хибних mismatch. Поточний алгоритм у цьому випадку відмовляє, а не приймає неправильні дані; це не блокер локального SQLite висновку.
- Відома історична схема без ERP розпізнається як historical, але high-level admission відмовляє через неповну грошову/складську звірку. У цьому A07 немає автоматичного production upgrade такого джерела до latest.
- A09/A10 установка, оновлення й production rollback, справжні клієнтські дані, браузерне приймання та фінальні 11 gates цим оглядом не прийнято. Синтетичний fixture не замінює D01 підпис клієнта або критерій 6.

## Зафіксовані джерела огляду

| Файл | SHA-256 |
|---|---|
| scripts/preflight_data.py | d946602d8c8dc3c299fb73d7cc4725aa3eb3ae25d87d1527348d7ff53bc3a965 |
| scripts/check_data_transfer.py | 5baa2f2c887109707266aa1b734d40d1f1fa485e557ed98ddc783b6fe70be98d |
| scripts/data_transfer.py | 8e0456ea7a89988050c86333e2cffa3e0b82a5742033b805c448c858c04d4be3 |
| fixtures/synthetic/transfer.py | 5ad1b8f82e2ad4baaf5ed4f07b44b876c6cb13d246373098716a8be9687dd475 |
| erp/test_full_data_transfer.py | b8c565ae9968d3dd18f11fa3f2b2e49dfd972e60e6a0afa83abc8624f186d434 |
