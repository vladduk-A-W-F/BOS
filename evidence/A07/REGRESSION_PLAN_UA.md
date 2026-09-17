# A07 · типи, обмеження та репетиція SQLite → PostgreSQL

Дата: 11.09.2026. Незалежний план, **не виконана міграція і не приймання A07**. Checkout не змінювався; фактичні `db.sqlite3` / `BoS_Demo.sqlite3` не відкривалися. PostgreSQL недоступний — його частина залишається **НЕ ЗАПУЩЕНО**, не green.

Прочитано актуальний `docs/PROGRESS_UA.md` (A06 триває), заморожений `docs/WRITE_PATHS_UA.md`, A07 у `output/BoS_Plan_UA.md`, чинні money/stock моделі, міграції та їхні write commands. База 85 шляхів / 12 місць не переглядається. Нові приклади нижче — конкретизація прийнятої A07 перевірки типів, не нові місця RMW у лічильнику.

Приймання A07 у погодженому плані: довжини, Decimal, JSON, Binary, FK і послідовності; перенесені копії збігаються за кількостями, сумами та SHA файлів; є rollback. Залежності: A01, A02, A06. A08 відповідає за подальший storage workflow, A09/A10 — за розгортання й оновлення установки. Тут не змінюється стек, формат фінансового обліку або історія.

## 1. Пріоритетні розриви поточного контракту

| Прийнятий ризик / джерело | Поточний факт коду | Мінімальна дія A07 |
|---|---|---|
| ERP-invoice, `operations.Invoice.code` | Поле `max_length=30`; спільний `erp.service.clean` приймає code до 60. Code31 уже відтворено в замороженому аудиті. | Перевіряти саме межу цільового поля до INSERT/зміни invoiced; не обрізати код і не розширювати поле до 60 заради тесту. |
| ERP-invoice, `Invoice.amount` | `DecimalField(14,2)` — максимум 999999999999.99; `money_total` дозволяє значення менше 10^13. | Перевіряти місткість **кінцевого Invoice.amount**, а не лише окремі quantity/price чи універсальний total. Відмова відкочує попередні SalesLine.invoiced. |
| ERP revision | Item/Lot/SalesLine/Production/Purchase.revision та ChangeOrder.target_revision мають 40; clean для revision/target_revision допускає 60. | Спільна перевірка потрібної моделі/поля для нових команд, без зміни старих версій. |
| ERP-location / ERP-item | Location.name=200, Item.material=200; загальна текстова межа clean=4000 не замінює їх. Item.name/unit мають окремі guards. | Перевіряти пропущені фактичні межі; контрольні допустимі 200 символів не відхиляти. |
| Числа в БД | Нові finance save_* уже викликають full_clean; ERP `.objects.create()` сам по собі цього не робить. | Не створювати другий financial writer. Для ERP поєднати цільову валідацію перед записом і локальні DB CHECK, які не змінюють дозволені бізнесові операції. |
| ERP-payment reference | Ключ зараз перевіряється у JSON Event під ERP mutex; окремого UNIQUE немає. | Кандидат: умовний унікальний індекс на text reference лише для `action=erp_payment`, після preflight. Тип reference має бути рядковим; не вводити UNIQUE для всіх Movement.reference. |
| A06 FinancialIntent | `key`/`payload_hash` по 64; CHECK дозволяє не більше одного source FK. Під час claim обидва FK тимчасово NULL. | Не замінювати CHECK на «рівно один» під час INSERT: це зламає чинну атомарну команду. Preflight після завершених транзакцій має виявляти committed intent без джерела. |

Підтверджена поведінка платформ: SQLite не застосовує параметр довжини `VARCHAR(n)` як обмеження; PostgreSQL застосовує `varchar(n)`. `numeric(p,s)` PostgreSQL може округлити зайві дробові знаки **до** перевірки місткості. Тому вхід `1.005` не повинен непомітно ставати `1.01` при переїзді. Це потребує валідації до SQL, а не лише CHECK на вже приведеному значенні. Див. [S1–S3](#джерела-перевіреної-поведінки-платформ).

## 2. Конкретні перевірки граничних значень

Це скінченний перелік предметних сценаріїв. Не генерувати «тест на кожне поле кожної моделі», який лише повторює metadata. Для кожної негативної ERP команди: справжній HTTP preview/confirm та прямий dispatch, поточний actor/CSRF; явний 4xx або validation exception, нуль часткових business writes, старі ID й receipt незмінні. Finance — ті самі shared save_* / serializers / admin, з ключем A06 там, де він потрібен.

### L · довжини й текст

| ID | Fixture / дія | Очікування на SQLite і PostgreSQL |
|---|---|---|
| L01 | Відвантажені 10 × 5.00, invoiced=0; `erp_invoice` з code=`A`×30, окремо `B`×31. | 30: один invoice=50.00, один link. 31: явна відмова; invoice/link/Event не додані, invoiced=0. `preview` також не змінює дані. Це первинний red A07. |
| L02 | `erp_item(revision='R'×40/41)` і `erp_opening(revision='R'×40/41)` при валідній номенклатурі/складі. | 40 зберігається точно; 41 відхилено до commit. Жодного обрізання, нової Lot чи opening при відмові. Позитивний код 60 символів у Lot лишається дозволеним. |
| L03 | `erp_location(name='С'×200/201)`; `erp_item(material='М'×200/201)` з рештою валідних полів. | 200 збережено; 201 відхилено. Це конкретні нині пропущені поля, не автоматичний обхід усіх CharField. |
| L04 | Code30 із українських символів/emoji; code із 30 символів плюс пробіл; текст/JSON рядок з U+0000; окремо BLOB з байтом 0x00. | Довжина рахується в символах, а не UTF-8 bytes. Не використовувати cast/strip/truncate для приховування понаднормового коду. NUL у тексті/JSON відхилено до SQL; нульовий байт у BinaryField є допустимим і зберігається. |

Для L04 не змінювати case sensitivity або Unicode normalization старих code. `ABC`, `abc`, composed/decomposed назви не зливати. Відмінність правил collation фіксується як конфлікт preflight, якщо цільовий UNIQUE вважає два існуючих ключі однаковими. PostgreSQL також може обрізати зайві пробіли або явний cast до varchar(n), тому importer має перевіряти довжину до cast [S2].

### N · Decimal та обчислений результат

| ID | Точні значення | Предметний оракул |
|---|---|---|
| N01 | `quantity=0.001` проти `0.0001`; price/unit_cost/labor_cost=`0.01` проти `0.001`; amount=`1.005`; `NaN`, `Infinity`, `-Infinity`. | Прийнята точність 3 для кількості й 2 для грошей. Зайва точність/нескінченність відхилена до SQL; не quantize з втратою значення. При дозволеній 0.001 фізичний залишок і рухи сходяться до 0.001. |
| N02 | Відвантажена quantity=1000000, price=1000000.00, invoiced=0: сума invoice=1000000000000.00. Обидва окремі inputs проходять поточні межі clean. | Відмовити через місткість Invoice(14,2); `invoiced` не змінюється, Invoice/InvoiceLink/Event відсутні. Позитивний сусідній приклад: quantity=1000000, price=999999.99 → invoice=999999990000.00, без втрати копійок. |
| N03 | Фінансові максимуми й наступний quantum із таблиці нижче; кожен для EUR/USD/UAH. | Граничне **поле** зберігає точне значення через відповідний валідований writer/тест перенесення; вихід за межу відхиляється. Не вимагати від HTTP дозволяти максимум БД, коли бізнесовий input limit навмисно нижчий. |
| N04 | Послідовність рухів +0.100, +0.200, −0.300; окремі записи грошей 0.10 і 0.20. | Склад=0.000; money total=0.30 у відповідній валюті. Manifest рахує через Decimal із значень рядків, не через float або змішану суму EUR+UAH. Порівняти також приклад біля допустимого верхнього значення, де cents критичні. |
| N05 | Purchase.quantity=0; received > quantity; Production.produced > quantity; Invoice.paid < 0 / > amount; SalesLine.invoiced > shipped; негативна ціна/собівартість. | Відмова через предметні/DB обмеження. Позитивні межі: received=quantity, produced=quantity, paid=amount, zero-price invoice=0, released Reservation=0. Від’ємний Movement.quantity для списання **дозволений**. |

Точний field map для меж місткості:

| Поля | Поточний тип | Максимум за типом / недопустимий наступний крок |
|---|---|---|
| Salary.amount | Decimal(12,2) | 9999999999.99 / 10000000000.00 |
| Transaction.amount; Contract.amount; Invoice.amount/paid | Decimal(14,2) | 999999999999.99 / 1000000000000.00 |
| Item.planned_cost; Lot.unit_cost; SalesLine.price; Production.planned_cost/actual_cost; Purchase.price/extras; Movement.cost | Decimal(15,2) | 9999999999999.99 / 10000000000000.00 |
| Item.minimum; Lot.quantity; SalesLine.quantity/shipped/invoiced; Production.quantity/produced; Reservation.quantity; Purchase.quantity/received; Movement.quantity; OperatorEntry.defects | Decimal(15,3) | 999999999999.999 / 1000000000000.000; знак і додатність визначає конкретне поле |

`money_total` може законно округлювати **обчислену** собівартість за чинним контрактом. Це не дозвіл округлювати надмірно точні вхідні або історичні записи при import. Не переводити існуючі DecimalField у float чи integer cents у цьому кроці. Небезпечно покладатися на CHECK виду `amount = round(amount,2)` у PostgreSQL: scale міг бути змінений самим numeric(…,2) раніше [S3].

### J/B · JSON та байти

| ID | Fixture | Оракул / мінімальна валідація |
|---|---|---|
| J01 | Item.bom, Production.bom/routing, Lot.documents, InvoiceLink.lines, SupplierQuote.terms, Event.payload/result, ActionProposal.payload/receipt; український текст, bool, null, integer ID, decimal **рядки**. | Round-trip зберігає структуру, типи чисел/рядків/bool, порядок масивів, IDs. Порядок ключів об’єкта та пробіли JSON не є бізнесовою зміною. Receipt/financial payload не перетворюється на нове виконання. |
| J02 | Неправильний корінь: Lot.documents=`[]` замість object, BOM=`{}` замість list; dangling `item_id` у BOM; рядковий `"false"` замість bool у quote. | Нові команди відмовляють за чинною структурою конкретного payload. Preflight називає таблицю, PK, JSON path, тип конфлікту; не конвертує значення. Перевіряти тільки форми, які код реально використовує, без універсальної вигаданої JSON-схеми історії. |
| J03 | Синтетична стара SQLite колонка/рядок: дублікати JSON keys, escaped `\u0000`, невалідний surrogate, NaN token, число поза numeric range; SQL NULL окремо від JSON null. | Preflight відмовляє до PG import там, де перенос втратив би зміст або став неможливим. Raw JSON треба розібрати з виявленням duplicate keys **до** звичайного json.loads/jsonb; не непомітно лишити останній key. NULL-tag зберігається окремо від JSON value. |
| B01 | Document.content: `b''`, `bytes(range(256))`, синтетичні PDF bytes і UTF-8 документ; окремий legacy text-only Document з content=b''. | Bytes зберігаються буквально, SHA-256 однаковий для кожного `(Document.pk, code, revision)`. BinaryField не є дефектом PostgreSQL. Не робити decode/encode або генерувати content із text для старих text-only записів. |
| B02 | ChatMessage/ChatFile із синтетичним файлом у test MEDIA_ROOT, Unicode original_name, size/relative path; старий архівний message теж має файл. | File row/зв’язок/назва/size/bytes SHA збережені. Відсутній або невідповідний файл — preflight conflict, не порожня заглушка. Файли копіюються в окремий staging media; layout та доступ не переробляються (A08 окремо). |

JSONField PostgreSQL використовує jsonb. Для порівняння — канонічна семантична форма; SHA оригінальних документів — від **байтів**. JSONB не зберігає whitespace/order/duplicate keys і не приймає NUL або всі можливі числові/Unicode послідовності SQLite; це конкретна причина J03 [S4, S5]. Binary/bytea підтримує довільні байти, зокрема нульові [S6].

Не перевіряти старий Document.checksum як «обов’язково SHA content» без класифікації джерела: seed/text-only формат міг обчислювати checksum з text. Manifest додатково зберігає фактичний SHA bytes; визначений provenance зберігається. Справжній конфлікт checksum/bytes за відомим алгоритмом — відмова й звіт, без перезапису checksum.

### F/U/S · джерела, унікальність, ID, дати

| ID | Fixture | Очікування |
|---|---|---|
| F01 | Salary→Transaction→Contract/Counterparty/Branch; Lot→Item/Location, Reservation→line або job, Movement→source; nullable FK як NULL. | Усі PK/FK й nullable значення збережені. Dangling required FK у синтетичній legacy schema — preflight conflict; import не створює порожніх довідників і не замінює FK на NULL. A05 PROTECT та архів не зникають. |
| F02 | Два pending Salary одного employee/year/month; дві Salary на один transaction; два InvoiceLink на один Invoice; два Document одного code/revision. | Існуючі UNIQUE/OneToOne зберігаються на обох СУБД. Конфліктний legacy набір не переноситься. Два резерви тієї самої Lot, released quantity=0 та різні invoices одного Order **залишаються дозволеними**. |
| U01 | Два Event erp_payment з однаковим валідним рядковим reference; контроль: однакове reference у різних нефінансових подіях/Movement. | Тільки повтор payment reference заборонений; невдала подія відкочує paid update. Історичні дублікати/відсутній reference — preflight відмова, не dedup/backfill старої події. Якщо expression UNIQUE не підтверджено на обох DB, цей підпункт не зараховувати. |
| U02 | A06 FinancialIntent: довгі external operation keys 128 символів; key/payload_hash — чинні 64 hex; completed intent→TX або Salary; архівне джерело. | Переноситься саме durable digest і той самий source FK; ключі не перераховуються за новими user ID. Claim із NULL/NULL може існувати в активній транзакції, але не як осиротілий committed receipt у quiescent snapshot. |
| S01 | Розріджені Auto/BigAuto PK: 7, 1001, 90001; архівний найбільший PK; sequence/high-water вище MAX живих рядків; UUID proposal/audit; FinancialIntent string PK. | IDs і UUID зберігаються, не natural-primary re-numbering. Після import два реальні INSERT без explicit ID отримують різні PK вище збереженої верхньої межі. Для UUID/string PK немає SQL sequence reset. |
| S02 | Порожня таблиця; непорожня таблиця після explicit-PK import; відкат невдалого INSERT. | Наступний INSERT не конфліктує й не перевикористовує історичний ID. Не вимагати gapless ID: PostgreSQL nextval/setval не відкочуються транзакцією. Snapshot і rollback мають зберігати/враховувати high-water [S7]. |
| S03 | Date-only payment/due date; UTC DateTime з мікросекундами; nullable archived_at/user; boolean needs_review=False. | Date не зсувається часовим поясом; DateTime представляє той самий UTC instant/мікросекунди; NULL не стає порожнім рядком, False не стає рядком. Не штампувати created_at заново під час import. |

## 3. Мінімальні сумісні constraints

Валідація нових команд і DB обмеження — різні рівні. Усі new validators працюють усередині наявного атомарного writer й до commit; при відмові лишається попередній стан. Фінанси продовжують йти через `save_salary`, `save_transaction` та `Salary.mark_paid`; ERP — через dispatch і proposal/confirm. Не обходити A06 ключ або mutex.

**Не перевизначати глобально `Salary.save()` викликом `full_clean()`:** захищений перехід `mark_paid` створює витрату і source link усередині своєї транзакції. A07 має додати цільові граничні перевірки в належному writer, зберігши цей шлях та його A02/A05/A06 assertions.

Кандидати для невеликої міграції, **лише після успішного preflight на конкретній копії**:

1. `Invoice`: `amount >= 0`, `0 <= paid <= amount`; `SalesLine`: доповнити чинні межі `0 <= invoiced <= shipped`. Нульовий invoice/нульова ціна дозволені поточним кодом; не змінювати їх на `>0` без іншої вимоги.
2. `Purchase`: quantity>0, 0<=received<=quantity, price/extras>=0. `Production`: quantity>0, 0<=produced<=quantity, planned_cost/actual_cost>=0. `Lot.unit_cost`, `SalesLine.price`, `Movement.cost` — невід’ємні. `Movement.quantity` лишається знаковим; Reservation.quantity=0 зберігається.
3. Верхні межі Decimal із field map та допустимі EUR/USD/UAH — у грошових/складських таблицях; Salary.amount/Transaction.amount>0; Salary period month 1…12, year 1…9999. Не додавати CASE-insensitive UNIQUE або нові правила currency conversion.
4. Переносимі length guards для реально записуваних кодів/версій/назв. SQLite DB length CHECK допустимий як додатковий захист після preflight; model CharField сам по собі не доводить його існування. NUL/Unicode і decimal scale перевіряти до SQL, без обіцянки, що DB typmod впіймає всі випадки однаково.
5. Умовний UNIQUE для Event payment reference: expression/JSON text extraction лише `action='erp_payment'`, якщо підтримка доведена actual SQLite/PG міграцією та U01. Додаткове поле або проєкція історії не потрібні лише заради індексу. Пропуски reference не приховувати NULL-правилами UNIQUE.

Не можна виразити простим row CHECK рівність `Lot.quantity = SUM(Movement.quantity)`, суму резервів чи рівність Salary.amount іншому рядку Transaction. Тут залишаються shared commands, locks, A01/A02/A06 та preflight звірка. Не додавати міжтабличні «CHECK», що насправді не перевіряють джерела.

Paid Salary локальний CHECK (paid → transaction/date not null) — можливе окреме посилення після inventory-compatible preflight, але не обов’язково змішувати з першим length fix. Потрібно зберегти тест неправильного історичного paid стану: якщо новий CHECK більше не дозволяє створювати його в latest schema, fixture має будуватися на справжній старій migration state або preflight копії. Бізнесове твердження «історія не переписується» не прибирати й не замінювати soft assertion; пояснити зміну передумови окремо.

Ніяких масових індексів «про всяк випадок». Індекси продуктивності лише після реального query/EXPLAIN; вони не усувають повне читання fingerprint/snapshot.

## 4. Preflight старих схем: класифікувати, відмовляти, не ремонтувати

Планується read-only preflight **з копії**, яка передана явно. Оригінальна установка не є ціллю мігратора. До будь-якого ALTER/INSERT target: джерельна версія schema/migration graph, SHA snapshot, справжня структура таблиць/колонок, constraints, типи PK/FK та доступність files.

| Клас синтетичної legacy schema | Як створити тест | Рішення preflight |
|---|---|---|
| Відомий старий migration state до operations/ERP | `MigrationExecutor` на окремій synthetic SQLite, узгоджені старі finance/employees/tasks/branches migrations; наповнити тільки існуючі на цьому state таблиці. | Розпізнати версію. Запропонувати/виконати відомий шлях міграцій лише на staging copy. Відсутність ERP даних не назвати перевіреним нульовим ledger; schema coverage позначити явно. |
| Відомий pre-A05/pre-A03 state | Старі джерельні ID, archived_at/user fields ще відсутні за migration graph. | Відомі AddField NULL і зміни constraints на staging із незмінними старими полями/PK. Не прив’язувати історичного працівника до нового вигаданого User. |
| Migration recorder каже latest, але колонка/таблиця/constraint відсутня | Окрема ручна synthetic schema fixture із навмисним drift. | `SCHEMA_DRIFT`, nonzero exit; жодного `--fake`, автоматичного «виправлення» django_migrations чи створення порожньої таблиці для зеленого звіту. |
| Невідома або частково імпортована схема | Synthetic missing migration history, невідомі перейменовані колонки, неправильний PK/тип FK. | `SCHEMA_UNSUPPORTED/INCOMPLETE`, список відсутнього та невідомого; explicit refusal. Не вгадувати mapping колонки за схожою назвою. |
| Схема відома, дані не відповідають A07 | Code31, зайві decimal digits, dangling FK, JSON conflict, duplicate UNIQUE, paid без source, неправильні межі, відсутній media file. | `DATA_CONFLICT`, таблиця/PK/поле або JSON path/код причини; до зміни target. Історичний рядок не обрізається, не округлюється, не видаляється, не прив’язується до «схожого» джерела. |

Валідність схеми не доводить валідності записів. Без читання робочих БД цей план встановлює **класи ризиків і спосіб їх перевірки**, а не стверджує наявність bad records у користувача.

Формат мінімального звіту: версії source/target, schema profile, source SHA, перевірені таблиці/поля, findings `[{code, table, pk, field/path, expected_rule, observed_type/length}]`, counts/totals, files `{id, relative_path, bytes, sha256}`, `can_migrate=false/true`, явні `not_checked`. Приватний звіт не потрапляє у Git/CI. Дані в тестах — лише синтетичні.

Для Decimal preflight читати raw SQLite storage class і числове представлення **до** Django-конвертера, що може quantize поле. `Decimal(str(raw_value))`, перевірка скінченності/масштабу/місткості; не round/CAST до меншої точності. Якщо первісна точність уже втрачена SQLite і її неможливо встановити з джерела, це `PRECISION_UNCERTAIN`, не «відновлення» цифр. Дозволене представлення після переносу має збігатися з обумовленим фінансовим значенням до копійки, а не з довільним float epsilon.

Після preflight дані не повинні змінитися до import: мігрувати ту саму зафіксовану immutable snapshot, повторно перевірити її SHA і manifest. Це запобігає TOCTOU без втручання у живу БД.

## 5. Репетиція переносу синтетичної SQLite → PostgreSQL

Потрібні два джерела: (а) відома стара schema + фінансові історичні рядки; (б) наповнена latest ERP schema. Кожне має окремий provenance/manifest. Не копіювати старі службові SQLite файли з checkout.

### Еталон latest fixture

Для **кожної** валюти EUR/USD/UAH, без FX:

- Один матеріал M, один виріб F; початкова Lot M=10.000 по 2.00; production BOM M×1, два резерви по 5, випуск 4.000 з labor=4.00 → raw=6.000, output=4.000 по 3.00, job.actual_cost=12.00. Перевірка якості output approved.
- Продаж F: quantity=3.000, price=5.00; reserve/ship 3 → output=1.000; invoice=15.00, paid=5.00, open=10.00; окремий return 1.000 у blocked Lot, cost=3.00. Shipment/invoiced history лишається 3; return не робить прихованої credit note.
- Purchase M=10.000, price=2.00, extras=10.00; receive 7.000 → received=7, pending receipt Lot=7 по 3.00. Загальний raw stock=13.000; finished/returned stock=2.000, stock value=39.00; production actual_cost=12.00. Всі quantities звірити окремо за item/lot/location, не лише глобальним підсумком різних SKU.
- Salary=100.00 paid → рівно одна linked expense=100.00; окрема manual in Transaction=200.00 → finance net=100.00. ERP payment не створює ще одну finance.Transaction. Приклад ще однієї archived Salary/expense або архівування цього paid джерела — totals не змінюються.
- Documents versions A/B з різними ID/bytes; лише правильна latest approved версія використовується активним допуском. Збережені незавершений та виконаний proposal, Event receipts, FinancialIntent на created finance sources, sparse IDs і архівні маркери. Pending proposal при import не виконується.
- Один archived ChatMessage з ChatFile; усі bytes лишаються. Dates/microseconds — фіксовані синтетичні значення, не timestamp міграції.

Цей еталон не є повним B01/C03 сквозним сценарієм. Він спеціально перевіряє A07 перенос типів і вже прийняті cash/stock invariants.

### Послідовність репетиції

1. Створити synthetic SQLite за відповідним migration state; сформувати fixture через справжні команди, де вони доступні. Для історичного state — справжні historical models. Зафіксувати source snapshot SHA, файли й контрольний manifest до міграції.
2. Зробити окрему staging copy. Перевірити preflight; застосувати лише відомі міграції до target schema на цій копії. Старі поля, PK/FK/UUID і bytes незмінні; додані schema/default поля позначити окремо. SHA **оригінального source** незмінний; SHA staging після DDL закономірно може змінитися.
3. Створити disposable PostgreSQL 16 database через чинний verification profile. Зафіксувати actual server version/encoding UTF-8 та migration plan. `migrate` на порожній target — окремий критерій, не заміна data transfer.
4. Перед import target не містить клієнтських/бізнесових рядків. Зберегти всі domain PK/FK, User/Employee/Group IDs, archive markers, UUID і A06 digests. Системні ContentType/Permission зіставити за природними ключами з явним mapping, якщо bootstrap ID відрізняються; не підміняти цим перенумерацію бізнесових ID. Якщо конфлікт mapping не описаний/перевірений, відмовити.
5. Перенести у транзакції, у порядку залежностей. Тимчасова deferral FK дозволена лише з обов’язковою перевіркою всіх constraints до commit; не `disable constraints`/skip bad row. File copies — у staging media. JSON експортується структуровано; bytes як bytes/base64 з перевіркою SHA; dates/Decimal/UUID передаються типізовано. Не re-save через доменні команди, що створюють нові виплати, Event чи змінюють created_at.
6. До commit звірити counts, exact IDs/FKs, Decimal totals по валюті/сутності, канонічну JSON семантику та files SHA. Після commit — повторити читання через звичайний ORM/HTTP, ledger/pay/replay invariants і checksum перевірки. A03/A04 role scopes не перевизначати.
7. Синхронізувати **лише target** sequences з імпортованим high-water. Два звичайні insert без explicit ID мають отримати різні нові IDs вище старої межі; перевірити new Document стає newest за ID. Ці proof inserts виконуються в окремій похідній тестовій копії/транзакції, не домішуються до контрольних sums еталона.
8. Зберегти повний log, manifest before/after, матеріальні порівняння та exit status. Усі count/sum/SHA відхилення — nonzero. Немає PG connection/server — явний `НЕ ЗАПУЩЕНО`, а не synthetic substitute.

Manifest переносимий: (1) counts по кожній реально перенесеній таблиці; (2) набір domain PK і кожного FK; (3) сумарні salary/transaction/invoice amount/paid/open **окремо за валютою**, gross та direction; (4) lot/movement/reservation по PK/item/location; (5) версії документів і SHA **кожного** blob/file; (6) JSON receipts/source references; (7) sequences/high-water і миграційний state. Один загальний SUM або загальний SHA archive не замінює цих перевірок.

## 6. Відмова та rollback — конкретні перевірки

| ID | Ін’єкція в синтетичному прогоні | Що має лишитися |
|---|---|---|
| R01 | L01/N02/J03/F01 конфлікт у source preflight. | Source bytes/SHA незмінні; target business rows не створені; звіт називає конфлікт; nonzero. |
| R02 | На staging SQLite є рядок, що порушує новий CHECK; запустити справжню A07 migration. | Відмова до логічної зміни даних; старі поля/ID/bytes збережені, migration не позначена застосованою. Не `--fake`, не data cleanup. |
| R03 | Реальний target DB trigger/constraint відхиляє останню зв’язану вставку після часткового import. | Всі domain вставки цього import відкочені; orphan FK/receipt/часткового invoice немає. Source не змінений; staging media не стала live. |
| R04 | Невідповідність одного file SHA або суми після завантаження. | Target не прийнятий/не перемикається; staging ізольований, report nonzero. Не видаляти історичний файл і не «перерахувати» checksum до нового вмісту. |
| R05 | Після setval/sequence proof штучна помилка транзакції. | Не очікувати старого sequence value від ROLLBACK. Відкинути тільки створений disposable target або відновити його з зафіксованого target snapshot/sequence state; вихідний source і його history незмінні [S7]. |
| R06 | Зворотне повернення з прийнятої rehearsal target до source N. | Запускається попередній schema/code N із незмінної копії source та matching media; counts/sums/IDs/fileSHA збігаються з manifest N. Це rollback репетиції без нових клієнтських записів після cutover, не обіцянка автоматично зливати production writes двох баз. |

Django `on_delete=PROTECT` — поведінка ORM та оголошений FK; це не привід покладатися на однаковий текст SQL ON DELETE. Перевіряти наслідок операції: джерело збережене, raw dangling FK не комітиться, архівний source доступний історичним join. Не припускати, що SQLite foreign_keys були ввімкнені в будь-якому сторонньому legacy файлі; це факт schema preflight [S5].

## 7. Обмеження висновків і передача root

Відомі факти без читання реальних рядків: code31/type30 та money_total/type14,2 — прийняті в аудиті розриви; revision40/clean60 та конкретні Char gaps — статичні кандидати на цільові red тести. Чинні A05/A06 guards і частину CHECK вже не треба будувати повторно. Старі файли frozen inventory описують стан до виправлень — не видавати їхні DEF-02…12 за нові A07 проблеми.

Рекомендований вузький порядок: L01 + N02 red → цільова валідація → решта L/N boundary cases → сумісні row constraints із refusal preflight → J/B/F/S переносні fixtures → справжній SQLite→PG import і R01…R06 → повний verify. Не змінювати 11 критеріїв. PostgreSQL, Windows, full live migration та A09/A10 ще не доведені цим документом.

### Джерела перевіреної поведінки платформ

Локальні факти взяті з перелічених на початку repo файлів; зовнішні правила звірено 11.09.2026 лише за офіційною документацією:

- [S1 · SQLite: Datatypes / type affinity](https://www.sqlite.org/datatype3.html).
- [S2 · PostgreSQL 16: Character types](https://www.postgresql.org/docs/16/datatype-character.html).
- [S3 · PostgreSQL 16: Numeric types](https://www.postgresql.org/docs/16/datatype-numeric.html).
- [S4 · PostgreSQL 16: JSON types](https://www.postgresql.org/docs/16/datatype-json.html).
- [S5 · Django 6.0: Model field reference](https://docs.djangoproject.com/en/6.0/ref/models/fields/).
- [S6 · PostgreSQL 16: Binary data types](https://www.postgresql.org/docs/16/datatype-binary.html).
- [S7 · PostgreSQL 16: Sequence functions](https://www.postgresql.org/docs/16/functions-sequence.html).
