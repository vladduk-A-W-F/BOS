# PLAN-LINKS-READ · пропозиція наступної мінімальної кодової картки

20.09.2026. Статус: SPEC_REVISED_AFTER_SCOPED_REVIEW; повторний review уточнень очікується. Реалізація і тести цієї картки не виконані. Ключ остаточно реєструє оркестратор; не перейменовує P10-003 чи історичні P-ID.

## Проблема та результат

У чинній картці замовлення вже є його позиції, роботи, резерви, рахунки та відвантаження. Проте немає одного серверного read-контракту, що пояснює походження кількості й відділяє прямі зв’язки від лише схожої закупівлі. Окремий `source_movements` із `erp.corrections.snapshot_rows()` уже містить доступні receipt/shipment без глобальної межі, і чинний `BoSInspector` замовлення його використовує. Межі загальних movements=300/events=150 не доводять втрату відвантажень. Новий контракт потрібний для ясного походження показників і явного обсягу джерел одного order; він не виправляє вигадану втрату shipments.

Картка додає **тільки читання джерел виконання одного замовлення**: позиції, придатний резерв, фактичні відвантаження, скасування, прямо пов’язані роботи та доручення; ідентифікатори дозволених рахунків. Доповнення вставляється в існуючий `BoSInspector`. Нових models/migrations, стороннього framework, graph DB, черги, LLM, універсального timeline, зовнішнього надсилання чи нового mutation API немає.

## Контракт, який треба реалізувати

Новий GET `/api/erp/orders/<int:pk>/trace/`, name=`bos-order-trace`, callback=`erp.views.order_trace` — **запропонований маршрут, зараз відсутній**. Він одразу дістає order через `Policy(request).queryset(SalesOrder)`; довільний order ID не розширює доступ.

Повернення `schema='bos.order-trace.v1'`: `order`, `as_of`, `generated_at`, `access_revision`, `scope`, `lines[]`, `linked_jobs[]`, `linked_tasks[]`, `linked_invoice_refs[]`, `limits`, `completeness`.

Для рядка:

- `line_id`, видимий item/revision/unit;
- `ordered`, `shipped`, `cancelled`, `open` — Decimal-рядки з чинних balances;
- `usable_reserved`, `source_refs`: line, cancellation, reservation, shipment; жодних «порожніх ID»;
- резерв має власний ID, quantity, lot ID і придатність; shipment — ID, lot ID, signed quantity, created_at;
- доведене походження прийнятої партії: receipt ID та purchase ID тільки для прямого `Movement.purchase` тієї самої партії. Поле позначається `relation='lot_origin'`, а не `allocated_purchase`;
- `basis` явно вказує, що gross shipped не зменшується від фізичного повернення;
- стан неповних/недоступних складників не підміняється нулем.

**Непризначені закупівлі не включати в `linked_*` і не обчислювати тут обіцяну дату.** Перший зріз показує текст: «Призначення очікуваних закупівель цьому замовленню не зафіксовано». Для детальної симуляції лишається чинний `plan_line()`/екран забезпечення. Це робить картку малою і не вводить новий механізм розподілу.

Рахунки в першому зрізі — лише через `Policy.queryset(InvoiceLink).filter(order=order)` з перевіреним доступним order, потім allowlist `invoice_id/code/currency/due_date`. Не шукати всі Invoice за customer і не використовувати `Policy.queryset(Invoice)` як самодостатній доказ належності. Доручення — лише `Policy.tasks().filter(sales_order=order)`, щоб зберегти перевірку поточних і історичних source_refs; прямий `Task.objects.filter(sales_order=...)` не замінює цей scope. Відсутність FK-належності не виводиться з тексту title/result. Суми/settlement залишаються у чинних фінансових проєкціях. Власник order, власник job і assignee task підписуються окремими ролями. Закупівлі без власника не отримують вигаданого відповідального.

Джерела беруться scoped ORM-запитами за конкретним order; `queries.snapshot()` не викликається. Кількості обчислюються сервером із чинною семантикою `balances` та `usable` і явною перевіркою видимості всіх складників. `free()`/`reserved()` не приймають Policy та враховують усі резерви партії: результат не можна прямо включати в новий role-scoped DTO. За прихованого reservation або іншого потрібного джерела — value=null, completeness=restricted; не підміняти повний резерв сумою лише видимих рядків. Перший trace взагалі не потребує глобального показника вільного запасу, лише доведеного резерву цієї line. Не дублювати формулу float-арифметикою в JSX.

`Policy.erp_ids()` уже обчислює глобальні sets через Item/Lot/SalesOrder/Production/Purchase; `Policy.tasks()` також перевіряє historical refs. Тому endpoint scoped за результатом і власними запитами, але **не гарантовано локальний за вартістю**. Свіжа повторна перевірка доступу повторить частину цих обходів. Не замінювати Policy дешевшим неповним фільтром у цій картці; адресно записати кількість SQL/час на дозволеній синтетиці та передати надмірну вартість окремій PLAN-N2/оптимізаційній картці.

Перед detail-відповіддю застосовується allowlist полів до всіх вкладених refs; не передавати raw event payload/result чи `approval_snapshot`. Для недоступного джерела — загальне повідомлення про неможливість повного пояснення, без IDs/counts/type/name цього джерела. Вже дозволені оприлюднювані quantity з order/line не розширювати до прихованих рухів; агрегат, що потребує неавторизованих складників, позначити null/restricted.

### Узгодженість читання

`generated_at` означає час підготовки, а не DB snapshot. Потрібна перевірка змін до/після всього збору фактів; звичайний `transaction.atomic()` на PostgreSQL READ COMMITTED цього сам не доводить. Запропонований протокол першого endpoint:

1. Створити свіжий `Policy`, зберегти `access_revision_before`; прочитати внутрішню ревізію `Configuration(key=erp_write)` без `get_or_create`, `update` чи виклику `write_lock()`. Відсутній запис — окремий sentinel, не створений рядок. Ця ревізія глобальна й збільшується чинним керованим writer.
2. Матеріалізувати дозволені source rows/поля й ознаки повноти одного order. У внутрішній `read_revision_before` включити ревізію erp_write та детермінований digest усіх спожитих значень/ID, включно зі складом наборів, doc admission і показаними employee/task metadata. Body обчислювати тільки з цих матеріалізованих значень, без подальших lazy-read під час JSON serialization.
3. Створити **новий** `Policy` і заново прочитати доступні залежності та metadata; не використовувати закешовані `_erp_ids` першого Policy. Обчислити `access_revision_after`, `read_revision_after`; повторно прочитати erp_write після цього проходу. Перевірити незмінність access revision, digest і erp_write протягом обох проходів.
4. Якщо обліковий запис відкликано — чинна identity-відмова; якщо права чи залежності змінилися — HTTP 409 `read_state_changed` з нейтральним повідомленням і **без** order/source payload. Жодних автоматичних server/UI retry, polling або повного повтору suite. Користувач може явно оновити картку.
5. Відповісти тільки якщо перевірки збіглися. Внутрішній read_revision, global mutex revision і хеші недоступних залежностей не повертаються клієнту чи GPT. У відповідь входить чинний access_revision; generated_at не називається часом atomic snapshot.

Це оптимістична перевірка стабільності керованого read-шляху; не новий універсальний механізм версій моделі. Зміна будь-якого іншого ERP-об’єкта може змінити глобальний erp_write і консервативно відхилити читання. Не вводити новий глобальний `erp.service.fingerprint()` у GET: він дорожчий та охоплює інший контракт. Обмеження вартості й конфліктів лишається явним предметом вимірювання. Якщо конкретний спожитий writer не покритий mutex/повторним digest, це finding до реалізації, а не привід назвати generated_at стабільним зрізом.

### Межа відповіді

Перший варіант не є журналом необмеженої довжини. Встановити документований ліміт 100 видимих рядків на секцію джерел; агрегатні суми обчислюються за повним дозволеним набором, незалежно від ліміту. Повернути `has_more` лише для дозволених джерел і `completeness='partial'`, якщо refs обрізані. Безпомилковий повний перелік понад ліміт потребує наступної окремої пагінації; перший зріз не називає себе повною історією.

Не додавати лічильник прихованих записів. Ліміти й правила мають бути в одному серверному місці. Для початкового малого синтетичного замовлення всі джерела вкладаються в ліміт, тому кожна показана кількість пояснюється повністю.

## Точний allowlist реалізації

| Файл від кореня BoS | Зміна |
|---|---|
| `erp/order_trace.py` — новий | Побудова scoped read-проєкції; явні DTO/allowlists/source refs; ліміти; без мутацій |
| `erp/views.py` | Один GET handler під чинними `errors`/`require_GET` і `Policy` |
| `erp/urls.py` | Один маршрут `orders/<int:pk>/trace/` |
| `erp/test_order_trace.py` — новий | Ізольована синтетика: refs/Decimal, права, незменшення source_movements, hidden constituents, дозволені InvoiceLink/Task, зміна read/access revision, read-only; нові названі access-тести включити в catalogue field suite |
| `scripts/access_routes.json` | Additive definition нового route та нові required_field_tests; усі 190 поточних definitions і 57 прийнятих field IDs зберегти |
| `scripts/check_access.py` | Додати новий RAW_GET, явний method/role/no_documents oracle, default field module `erp.test_order_trace`; жодних broad allowed-status/skip |
| `scripts/access_fixtures.py` | Явні positive anchors і hidden canaries нового route; чинний route_values для api/erp/orders вже використовує реальний synthetic order PK; решту fixtures не послаблювати |
| `docs/ACCESS_UA.md` | Датований additive опис нового читання й меж; старі правила не переписувати |
| `docs/orchestration/evidence/PLAN_LINKS_READ_ROUTE_DELTA.json` — новий | Окремий запис: доданий route, колишні/нові catalogue SHA та counts, method/role coverage; historical85/12 unchanged |
| `frontend/boss_app_source.html` | Компактна секція «Джерела виконання» у `BoSInspector` для orders; loading/error/denied; відкинути відповідь попереднього ID або access_revision; клавіатурні кнопки до чинних карток |
| `frontend/boss_app_html.html`, `assets/app.js` | Тільки похідні від штатної збірки, коли картка отримала дозволений профіль збірки; вручну не правити |

`scripts/build_frontend.cjs` фактично читає source HTML і пише `assets/app.js` та `frontend/boss_app_html.html`; змінювати сам скрипт у цій картці не потрібно. На етапі цієї специфікації збірка не запускалась, JS assets не читались. Якщо чинна allowlist виконавця забороняє generated assets, оркестратор спочатку оформляє окремий дозволений frontend-крок; серверна частина може залишатися самостійною карткою.

Файли models, міграції, policy, middleware, service dispatch, task commands, finance writers, readiness, master, історичний WRITE_PATHS85/12, критерії gates, CI та production налаштування не входять в allowlist. Названі вище access catalogue/harness/fixtures — обов’язкове additive охоплення нового маршруту, а не зміна критеріїв gate4. Точне рішення наведено в `PLAN_LINKS_ROUTE_SCOPE_UA.md`. Якщо читання виявить дефект чинної policy або інваріанта, оформити окрему C1/грошову/складську картку; не маскувати його зміною цієї проєкції.

## Мінімальне приймання реалізації

1. Синтетична line quantity=10 з частковим shipment, reservation, cancellation: `open` точно збігається з `sales_open`, усі відкриті refs належать тій самій справі.
2. Друга sales line іншого order з тією самою item/revision і спільною закупівлею не з’являється як належність першого; post-receipt lot_origin не проголошує всю PO виділеною.
3. Свіжі фікстури для ceo/manager/observer доводять допустимі поля; приховані документи/грошові дані не просочуються через nested refs, помилки чи labels. Читання після зміни прав перевіряє поточний Policy.
4. Receipt/shipment поза глобальними movements300/events150 уже доступні через чинний source_movements; новий контракт не зменшує це охоплення. Понад 100 власних дозволених refs дають partial/has_more, сума лишається точною лише за повної видимості складників; UI не називає refs повними.
5. GET не змінює ERP, задачі, proposals чи audit; не викликає зовнішній adapter. Повтор GET за незмінного стану дає ті самі бізнес-факти, хоча generated_at може відрізнятися.
6. Зміна резерву/документа/рольового доступу між проходами читання дає 409 без business payload або чинну identity-відмову. Недоступний reservation робить похідний показник null/restricted; invoice без дозволеного InvoiceLink і задача з прихованими historical refs не включаються.
7. UI показує loading/error/недоступність; після швидкого перемикання order або зміни ролі не показує попередній результат. Видимі лінки відкривають чинні картки; немає автоматичного preview/confirm із GET чи автоматичного повтору 409.
8. Catalogue diff — лише additive route/field-test IDs, усі старі definitions/oracles збережені. Для нового route є позитивне непорожнє читання й негативні role/method/no_documents/hidden tests. Підготовка такого harness не є запуском чи PASS gate4.

Тести запускати лише за окремою активною карткою й дозволеним синтетичним профілем. Для плану достатньо статичної перевірки джерел. Scope-test не закриває full gate, не замінює PostgreSQL 16 і не скидає P05 3/3. Ліміти повторів та A09/A10/A11 зберігаються.

## Перед інтеграцією

Потрібні незалежний review diff + raw output, один атомарний коміт у дозволеній гілці та запис фактичного source SHA. Новий API включається в чинну інвентаризацію маршрутів доступу в межах належної картки, без ослаблення master §2. `TECHNICAL_READY=false`, `PILOT_ALLOWED=false` залишаються незмінними до окремого приймання.

Ця read-only картка не залежить від вибору GPT-провайдера/бюджету чи підтвердження власного виробництва. Ці рішення потрібні для наступних функцій, а не для показу вже наявних зв’язків.
