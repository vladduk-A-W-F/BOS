# A06 — обмежений незалежний план регресій gate 5

Дата: 11.09.2026. Статус: **план; A06 тести та зміни продукту не виконувалися**.

Прочитано поточні `docs/PROGRESS_UA.md`, master v2.1, заморожений `evidence/INVENTORY/WRITE_PATHS.json` (85 шляхів / 12 канонічних місць), `erp/service.py`, `operations/service.py`, адаптери HTTP, `finance/commands.py`, `finance/models.py`, архівні команди та старі тести конкурентності. Інвентар не перебудовувався. Робочі SQLite бази не читалися. Старий `plan_data_races.py` прочитаний як джерело сценаріїв, **не запускався**: він має власні звернення до оригінальної БД.

## 1. Межа та значення «повтор»

Master §2.5 вимагає два одночасні виклики кожної грошової та складської операції: один матеріальний результат, другий — той самий результат або узгоджена відмова, без дублювання рухів. Це **повтор одного наміру або конкуренція за один обмежений ресурс**, а не заборона двох незалежних законних фактів.

- ERP: один `ActionProposal.id`, та сама сесія й власник — один намір. Два `proposal_id` — різні погодження; якщо вони спираються на один старий fingerprint, друге має відмовити після першої зміни стану.
- Виплата зарплати: `Salary.pk` уже є ідентифікатором однієї виплати. Повтор не створює нової витрати, навіть коли передано іншу дату або джерело вже архівоване.
- Створення `Transaction`: наразі немає operation key. Однакова сума, дата, валюта чи контрагент не доводять повтор. Дві POST без ключа не можна звести в одну транзакцію за цими полями.
- Оновлення наявного запису: повтор того самого присвоєння має один кінцевий стан. Два різні дозволені присвоєння можуть серіалізуватися як дві правки; без очікуваної ревізії API не обіцяє optimistic conflict.
- Архівування: один маркер та одна подія архівування на запис. Архів не зменшує ledger, не видаляє ID і не розриває джерела.

Немає нової інвентаризації чи нового модуля ERP. Для замкненого покриття наявної approval boundary таблиця нижче містить усі **26 поточних `SCHEMAS`**: 14 створюють грошові/кількісні факти або рухи; 12 — наявні передумови та керування ними. Для останніх явно перевіряється **нуль нових рухів**, а не вигаданий фінансовий ефект.

## 2. Реальний harness для обох СУБД

1. `TransactionTestCase`, окремий файловий SQLite test DB через `verification_settings`, окремий disposable PostgreSQL profile. Не `TestCase` з зовнішньою транзакцією, не shared in-memory SQLite. На початку логувати фактичні `connection.vendor`, версію СУБД і назву синтетичної бази.
2. Два workers, дві незалежні DB connections, `threading.Barrier(2)` перед HTTP/ORM викликами; `connections.close_all()` у `finally`. Час очікування обмежений; зависання або необроблена DB помилка — провал, а не успіх.
3. Справжній `Client(enforce_csrf_checks=True)`, GET CSRF і POST `/api/auth/login/`, звичайний синтетичний `User` з єдиною групою `ceo`. Для ERP одного погодження клонувати cookies **вже ввійшовшого** клієнта у два різні `Client`: owner і session_key мають збігатися. Два незалежні `login_test_client()` створюють різних користувачів і не відтворюють повтор того самого погодження.
4. Fixture створюється до бар’єра; бізнесові ORM-об’єкти для worker читаються з його connection. Для stale-instance сценарію обидва читають старий запис до barrier, потім викликають справжню команду. Не `force_authenticate`, не monkeypatch HTTP/ORM і не підміна lock функцій.
5. У загальних pair тестах достатньо одночасного старту. Для точного міжкрокового порядку дозволене лише прозоре SQL спостереження/пауза через `execute_wrapper`: кожен реальний SQL виконується один раз; не змінювати результат, SQL або дані. Бар’єр після отримання взаємовиключного lock для обох workers неможливий і спричинить штучний deadlock.
6. Для HTTP ERP правильні варіанти — `[200, 200]` з ідентичним receipt або один `200`, один явний `409`. Після завершення повтор того самого `proposal_id` має повернути receipt першого успіху й не змінити бізнесовий стан. Не зараховувати `[409, 409]`, `500`, порожнє тіло, неповний `running` receipt або 200 з повідомленням про невиконання.
7. Для різних конфліктних payload прямого ORM: один успіх, другий — предметний `ValueError`/`Conflict` або реальний transient lock conflict з повним rollback. HTTP adapter має перетворити DB conflict на 409; дозволену предметну відмову — на чинний 4xx. Виняток сам по собі не є доказом: обов’язковий точний постстан.
8. Для кожного успіху звіряти `Lot.quantity = Sum(Movement.quantity)`, `0 <= reserved <= quantity`, межі shipped/invoiced/paid, суми `Decimal`, джерельні ID, кількість рухів/подій та відсутність часткових артефактів. Порівнювати дельту від fixture, а не загальну кількість усіх рухів.
9. Зберігати лог двох workers, HTTP status/JSON, ідентифікатори proposal/key/result, фактичний постстан і тестову версію коду. PostgreSQL, який не запущено, лишається червоним gate, без skip або зарахування SQLite замість нього.

## 3. Спільна синтетична основа

Позначення в таблицях — локальні PK, отримані після справжніх ORM insert у чистій fixture; це не production ID.

- `E`: Employee «Синтетичний оператор A06»; User входу окремий, зайвий Employee для авторизації не потрібен. `CUS`: Counterparty type=customer; `SUP`: type=supplier.
- `W`: Location warehouse; `P`: Location production. `M`: Item material/buy, revision=A, unit=шт., currency=`C`, required_documents=[]; `F`: product/make, та сама валюта, BOM `[M × 1]`, routing `[Виготовлення]`, planned_cost=3.00.
- `L`: approved Lot з M, quantity=10.000, unit_cost=2.00, revision=A, currency=`C`. Обов’язковий початковий Movement `+10.000`, cost=20.00. Для виробництва L розташована у P; для продажу/переміщення — W.
- `SO/SL`: confirmed SalesOrder CUS/E з одним SalesLine M × 10.000, price=5.00, shipped=invoiced=0; для job із line_id створити окремий рядок F. `PO`: Purchase M × 10.000, price=2.00, extras=10.00, received=0, revision=A.
- `J`: Production F × 10.000, BOM `[M × 1]`, planned_cost=30.00, actual_cost=0, produced=0, location=P, revision=A, owner=E. Стан і операторські записи встановлюються окремо за рядком тесту.
- `DA/DB`: синтетичні Document одного code, revision A/B, непорожній text, відповідний checksum, content з синтетичними bytes. Коли потрібна лише DA, DB **ще не створювати**. CEO має доступ без додаткової document capability.
- `INV`: Invoice amount=10.00, paid=0, currency=`C`. `SAL`: pending Salary E, amount=100.00, currency=`C`, period=2026-09, без transaction/payment_date.
- Дата потреби: 2026-09-20; нова дата: 2026-10-01. Коди нових об’єктів починаються `A06-`, відрізняються між незалежними fixtures. Кожен рядок таблиці — окрема fixture.
- Грошові сценарії повторювати для `C ∈ {EUR, USD, UAH}` без конвертації або складання різних валют. Числа й дати передавати явно. Не доводити збереження валюти лише типовим EUR.

## 4. Один proposal_id: точне покриття ERP

Для **кожного** рядка: реальний POST `/api/erp/preview/` з `action=erp_<назва>` та параметрами; snapshot/рухи після preview не змінені. Потім **два одночасні POST** `/api/operations/confirm/` з `{"proposal_id": "<id>", "confirmed": true}`. Спільне очікування розділу 2: один Event, один матеріальний ефект, незмінний повторний receipt. У прямого `dispatch` proposal ключа немає; він не є окремим HTTP маршрутом.

| Inventory / дія | Додаткові умови та payload без action | Матеріальний постстан одного успіху |
|---|---|---|
| ERP-opening | `code=A06-OPEN, item_id=M, location_id=W, quantity=10, unit_cost=2.00, currency=C, revision=A` | Одна нова pending Lot 10; один opening +10, cost 20.00. |
| ERP-receive | PO як вище; `purchase_id=PO, code=A06-RCV, location_id=W, quantity=7` | PO.received=7, status=partial; одна pending Lot 7, unit_cost=3.00; один receipt +7, cost 21.00. |
| ERP-reserve | L=10 і SL=10; `lot_id=L, line_id=SL, quantity=7` | Один Reservation=7, free=3; physical=10 і нових Movement=0. Окремий варіант production_id=J на дільниці P. |
| ERP-release | Reservation R=10; `reservation_id=R, quantity=7` | Той самий R з quantity=3; physical=10, рухів=0. Нульовий резерв при повному звільненні зберігає ID. |
| ERP-transfer | L у W; `lot_id=L, quantity=7, location_id=P, code=A06-TR, reason=Синтетичне переміщення` | L=3, нова Lot у P=7; рівно transfer_out -7 і transfer_in +7, кожен cost=14.00; сумарна кількість не змінена. |
| ERP-finish / DEF-01 | J running, операція done, два резерви L по 5; `production_id=J, quantity=7, code=A06-OUT, location_id=W, labor_cost=7.00` | L=3, резерви сумарно=3; два consume -5/-2 і один production +7; J.produced=7, actual_cost=21.00, status=running; одна output Lot unit_cost=3.00. |
| ERP-ship | L=10, резерв SL=10; `line_id=SL, lot_id=L, quantity=7, reference=A06-SHIP` | L=3, резерв=3, SL.shipped=7; один shipment -7, cost=14.00. |
| ERP-return | Початкове відвантаження 10 з L, L=0, SL.shipped=10; `line_id=SL, lot_id=L, quantity=7, code=A06-RET, location_id=W, reason=Синтетичне повернення` | Одна blocked Lot=7 і return +7, cost=14.00. SL.shipped/invoiced та попередні shipment ID незмінні. Це не credit note і не зменшення старого invoice. |
| ERP-invoice | Реально відвантажені 10, SL.price=5.00, invoiced=0; `order_id=SO, code=A06-INV, due_date=2026-10-01` | Одна Invoice=50.00 C, один InvoiceLink з line/quantity=10/price=5; SL.invoiced=10; рухів складу=0, finance.Transaction=0. |
| ERP-payment | INV amount=10, paid=0; `invoice_id=INV, amount=7.00, reference=A06-PAY` | INV.paid=7.00; один Event erp_payment; finance.Transaction=0. Це локальне погашення invoice, не банківська операція. |
| ERP-adjust | L=10, reserve=0; `lot_id=L, delta=-7, reason=Синтетична інвентаризація` | L=3, один adjustment -7, cost=14.00. Додатковий позитивний варіант +7 дає L=17, один +7; повтор proposal не дає 24. |
| ERP-order | `code=A06-SO, customer_id=CUS, owner_id=E, due_date=2026-09-20, currency=C, lines=[{item_id:M, quantity:10, price:5.00}]` | Один SalesOrder quote і один SalesLine 10 × 5.00; жодних invoice, reservation чи Movement. |
| ERP-purchase | `code=A06-PO, item_id=M, supplier_id=SUP, quantity=10, price=2.00, extras=10.00, currency=C, due_date=2026-09-20, revision=A` | Один Purchase, received=0, price/extras збережені; жодної Lot, оплати чи Movement. |
| ERP-job | `code=A06-J, item_id=F, quantity=10, location_id=P, owner_id=E, due_date=2026-09-20` | Один J planned, produced=0, planned_cost=30.00 C, frozen BOM/revision; reservation і Movement не створені. |
| ERP-item | `code=A06-NEW, name=Синтетичний компонент, unit=шт., kind=component, method=buy, revision=A, currency=C` | Один Item із вказаною валютою; Lot, Movement і Transaction=0. Це контроль спільного механізму погодження довідника. |
| ERP-location | `code=A06-W2, name=Синтетичний склад, kind=warehouse` | Одна Location; запасів та рухів не додається. |
| ERP-confirm_order | SO має status=quote; `order_id=SO` | SO.status=confirmed один раз; рядки, ціни й рухи незмінні. |
| ERP-quality | L pending, required_documents=[]; `lot_id=L, result=approved, inspector_id=E, note=Синтетичний контроль` | L.approved; одна Inspection, фізична кількість і рухи незмінні. Окрема документна admission гонка — нижче. |
| ERP-attach | M.required_documents=[cert], L.documents={}, чинна approved DA; `lot_id=L, kind=cert, document_id=DA` | Один запис mapping cert→DA у тій самій Lot; кількість, quality, рухи незмінні. |
| ERP-start | J planned, резерв M=10 у P, L approved; `production_id=J` | J.running один раз; резерв=10, produced=0, actual_cost=0, рухів=0. |
| ERP-operator | J running, routing=[Виготовлення]; `production_id=J, operation=Виготовлення, operator_id=E, result=done, minutes=10, defects=0, note=Синтетичний запис` | Один OperatorEntry; він дозволяє finish, але не списує матеріал і не створює випуск. |
| ERP-change | M revision=A, approved latest DB revision=B; `code=A06-ECO, item_id=M, document_id=DB, target_revision=B, reason=Синтетична зміна` | Один ChangeOrder draft; Item.revision лишається A, партії та рухи незмінні. |
| ERP-apply_change | Draft ECO на DB, Item A, одна відкрита й одна done робота; `change_id=ECO, disposition=Розглянути відкриту роботу` | ECO approved; Item.revision=B/document=DB; лише відкрита робота needs_review=True. Старі Lot/SL/job revision не переписані, рухів=0. |
| ERP-resolve_job | J.needs_review=True, frozen revision=A; `production_id=J, disposition=Погоджено завершити версію A` | J.needs_review=False, J.revision=A; кількість, BOM, витрати і рухи незмінні. |
| ERP-postpone | PO due/original_due=2026-09-20; `purchase_id=PO, due_date=2026-10-01, reason=Синтетичне перенесення` | Лише due_date=2026-10-01; original_due, received, price/extras і рухи незмінні. |
| ERP-postpone_job | J due=2026-09-20; `production_id=J, due_date=2026-10-01, reason=Синтетичне перенесення` | Лише due_date=2026-10-01; produced, BOM, cost, reservation і рухи незмінні. |

Усі рядки також покривають `CORE-erp-preview`, `CORE-execute`, `CORE-confirm`, `CORE-dispatch`; рухи — `CORE-move`, створення партій — `CORE-newlot`. Окремі smoke перевірки обох preview entrypoints покривають `CORE-proposal`/`CORE-ops-preview` та `CORE-preview-effect` з обов’язковим rollback; це aliases, не нові фінансові операції.

## 5. Різні погодження й прямі ORM конкуренти

Старі 11 сценаріїв з `evidence/INVENTORY/PRIOR/plan_data_races.py` лишаються основою. Перенести fixture/оракули, **не його запуск оригінальної БД й не assertion старого salary defect**. Для кожного рядка: два справжні `dispatch(..., role='ceo', log=True)` із різними payload, окремими connections і одночасним стартом. Окремо по одному HTTP варіанту цих рядків: два preview з однаковим поточним fingerprint, різні proposal_id, два одночасні confirm; після першого другий — 409 через застарілий fingerprint, без другого ефекту.

| Inventory | Два виклики / fixture | Точний допустимий постстан |
|---|---|---|
| ERP-reserve | Два різних SL потребують по 7; одна L=10 | Один резерв=7, free=3; другий резерв не створений. |
| ERP-release | Один R=10, кожен звільняє 7 | R=3; фізичний залишок та рухи незмінні. |
| ERP-receive | PO залишок=10; приймання по 7 з різними lot codes | PO.received=7; одна нова Lot=7 й один receipt, без orphan Lot другого коду. |
| ERP-transfer | L=10; по 7, різні нові lot codes | Source=3, одна destination=7, рівно два рухи. |
| ERP-finish / DEF-01 | J залишок=10, матеріал/резерви=10; по 7, різні output codes | produced=7, матеріал=3; лише один випуск і його матеріальні списання. |
| ERP-ship | SL/L/reserve=10; по 7, різні references | shipped=7, L=3, reserve=3, один shipment. |
| ERP-return | Одне історичне відвантаження=10; повернення по 7, різні codes | Одна return Lot=7; повернуто сумарно 7, shipped/invoiced history незмінна. |
| ERP-adjust | L=10; два delta=-7 | L=3, один adjustment=-7; немає -4 або двох списань при залишку 3. |
| ERP-invoice | Неінвойсоване відвантаження=10 × 5; різні invoice codes | Одна Invoice=50, один InvoiceLink, invoiced=10. |
| ERP-payment | INV.amount=10; по 7 з різними references | paid=7, один payment Event, без finance.Transaction. |
| ERP-payment (старий payment_dup) | INV.amount=20; двічі 7 з **однаковим reference** | paid=7, один Event цього reference; другий — відмова навіть коли відкритої суми вистачає. |

Не підміняти ці тести лише повтором proposal: без спільного operation key саме обмеження ресурсу й поточні reads мають відхилити другого конкурента. Не вимагати одного результату від двох різних дозволених partial операцій, наприклад двох надходжень по 3 до PO=10: це законні received=6 та два різні рухи.

## 6. Фінансові команди та архівування

Наведені паралельні HTTP/ORM пари — доповнення до існуючих A02/A05 assertions, не їх заміна. Для create/update API використовує `FinancialCommandSerializer` → `save_salary`/`save_transaction`. Admin і legacy helpers мають перевірятися через ті самі команди; не створювати другий фінансовий writer.

| Контракт / frozen mapping | Два реальні виклики й маршрут | Оракул / fixture |
|---|---|---|
| Pay: DEF-02, API-pay, AI-pay-salary | Два POST `/api/salaries/{SAL}/pay/`; також два stale `Salary.mark_paid()`; змішаний ORM `_pay_salary` + HTTP | SAL=100 C. Обидва повертають той самий transaction ID або один явний transient 409 із наступним тим самим replay. Рівно одна expense 100 C, salary/out/date/link узгоджені. Зберегти сильні чинні A02 assertions `[200,200]`, де вони вже виконуються; не послаблювати їх до 409. |
| Salary create: DEF-03, API-salary-adapter, DEF-08, AI-create-salary | Два POST `/api/salaries/` або два `save_salary` з одним E/2026/09 | Один pending Salary=100 C, жодної expense. Природний UNIQUE(employee,year,month) уже забезпечує один запис; другий повертає явну validation/conflict відмову або keyed receipt після додавання ключа. Два різні місяці — два законні Salary. |
| Salary update: ті самі aliases | Два PATCH `/api/salaries/{SAL}/` з amount=120.00 або два `save_salary` | Pending 100→120; кінцевий amount=120, одна зміна audit, expense=0. Обидва stale callers читають 100 до barrier; shared command має перечитати під lock і не втратити archive marker. |
| Pay проти зміни зарплати: DEF-02 + DEF-03/DEF-08 | Одночасно pay SAL=100 і PATCH amount=120 | Якщо edit першою: paid 120 + єдина expense 120. Якщо pay першою: paid 100 + єдина expense 100, edit відхилено. Не допускається paid 120 з expense 100 або навпаки. Дві різні команди можуть обидві успішно завершитися в першому порядку. |
| Transaction create: API-transaction-create, DEF-09, AI-create-transaction | Два POST `/api/transactions/` із тим самим новим Idempotency-Key; два `save_transaction(operation_id=...)`; admin/AI aliases | Payload: in, amount=100.00, currency=C, date=2026-09-11, description=Синтетичний платіж A06, category=customer. Один Transaction, один audit і той самий ID receipt. **Нині ключ відсутній; це очікуваний red нового контракту.** |
| Transaction create, різні наміри: ті самі mapping | Той самий фінансовий payload, але два різні keys | Два Transaction з різними PK; сума=200.00 C, два audit. Це обов’язковий позитивний контроль проти хибної дедуплікації за сумою/датою. Без ключа збережена семантика — незалежний ручний факт, а не доказ idempotent replay. |
| Transaction update: DEF-04, API-transaction-adapter, DEF-09 | Два PATCH `/api/transactions/{TX}/` з amount=120 або `save_transaction` | Для ручного неархівного TX=100: кінцевий 120, одна зміна audit. Для linked expense оплаченої SAL: обидві спроби змінити core відхилено, paid/source/amount/currency незмінні. description не вважати immutable core, якщо поточний контракт його дозволяє. |
| Salary archive: DEF-05, DEF-10 | Два DELETE `/api/salaries/{SAL}/`; ORM `.delete()` + admin `delete_selected` того самого PK | Row count/PK/source лишаються, один archived_at і одна salary.archive подія. Повтор не створює другий audit, не скасовує виплату. |
| Transaction archive: DEF-06, DEF-11 | Два DELETE `/api/transactions/{TX}/`; ORM + admin bulk | Linked paid expense=100 C збережена разом із SAL.transaction_id. Ledger totals незмінні; один transaction.archive audit. |
| Employee archive: DEF-07, DEF-12, AI-delete-employee | Два DELETE `/api/employees/{E}/`; ORM + admin bulk | Один employee.archive, усі Employee/Salary/Transaction ID/FK збережені, виплати не видаляються. |
| Archive Salary проти pay: DEF-05/10 + DEF-02 | Пара DELETE SAL + POST pay SAL | Якщо archive першою: archived pending, витрат=0, pay 4xx. Якщо pay першою: archived paid + рівно одна expense; обидва можуть завершитися. Історія не зникає в жодному порядку. |
| Archive paid expense проти pay replay: DEF-06/11 + DEF-02 | DELETE linked TX + POST pay уже paid SAL | Той самий transaction ID, archived marker збережений, кількість/сума expense не збільшилися. |
| Archive Employee проти Salary create: DEF-07/12 + DEF-03/08 | DELETE E + POST нової SAL на E | Якщо Employee lock/archive першими: create 4xx, SAL=0. Якщо create lock/commit першими: одна SAL лишається історією, Employee може потім архівуватися. Не вигадувати заборону будь-яких існуючих SAL в архівного E. |
| Restore history: AI-undo → `restore_record` | Два ORM `restore_record()` для одного архівного джерела, або відповідний справжній helper undo з валідною synthetic history | Один restore audit, той самий PK/FK/суми, без нового нарахування/транзакції. Змішане archive/restore — дві різні команди; допустимий будь-який послідовний порядок, не довільна втрата audit. |

Admin: single та bulk archive використовують справжні POST з валідним staff CEO і відповідними Django permissions. Перевіряється постстан, не лише 302. У A06 не додається новий admin маршрут pay. Ризики A05 щодо immutable core, rollback та PROTECT не переозначаються.

## 7. Мінімальний новий контракт ключа financial create

Це пропозиція в межах прямого уточнення root, **не реалізований API**. Не переносити фінансові команди у нову систему й не обходити `finance.commands._save`.

| Пункт | Пропонований контракт |
|---|---|
| Передача | HTTP `Idempotency-Key: <UUID>` → окремий аргумент `operation_id` у shared create command. Ключ не є полем Transaction/Salary і не входить у звичайні модельні зміни. |
| Один намір | Ключ створюється перед першим submit; double click, timeout/retry і повтор форми зберігають його. Нова ручна операція створює новий ключ. Сервер не виводить ключ із суми/дати. |
| Збереження | У тій самій DB transaction: claim унікальної пари command+operation_id, binding власника/походження, hash нормалізованих валідованих параметрів, виклик наявного shared save, audit, receipt із тим самим result PK. Усі частини commit/rollback разом. Не in-memory cache та не локальний mutex процесу. |
| Ownership | Receipt прив’язаний до чинного principal; повтор іншого користувача не відкриває фінансових полів. Перед replay повторно застосовується A04 policy; зниження ролі не обходиться старим receipt. Для внутрішнього виклику має бути явне походження, а не вигаданий користувач. |
| Однаковий ключ / ті самі параметри | Один запис; другий повертає збережений результат або явний in-progress conflict з подальшим тим самим результатом. Результат не відновлюється створенням нової транзакції. |
| Однаковий ключ / інші параметри | 409, без другого запису й без мовчазного прийняття нової суми/валюти/дати/FK. |
| Різні ключі | Два законні Transaction навіть за цілком однакових реквізитів. Для Salary додатково діє незалежний UNIQUE періоду: два ключі не дозволяють друге нарахування того самого employee/month. |
| Збій | Реальний constraint/trigger failure після financial INSERT або перед receipt commit відкочує запис, audit і claim. Повтор ключа після виправлення тестового тригера може виконати операцію рівно один раз. Втрачена HTTP відповідь після commit повторно повертає первісний PK. |
| Сумісність | Старі бізнесові assertions не міняти. Якщо no-key create лишається доступним для сумісності, він явно означає новий незалежний факт і не зараховується як replay guarantee. Усі повторювані користувацькі create flows повинні передавати ключ; нові keyed assertions додаються окремо. Якщо root обере обов’язковий ключ у working mode, старим тестам можна додати лише header-передумову, зберігши assertions. |

Адаптери, яким потрібен ключ:

1. `POST /api/transactions/` → `TransactionSerializer.create` → `save_transaction`: основний невкритий writer. Це ж стосується actual frontend submit/повтору одного введення.
2. `TransactionAdmin` add/re-submit → наявний shared save: стабільний ключ конкретної форми, не новий ключ на кожен серверний POST. Наявні edit не є новою Transaction і не потребують create key задля row count.
3. Legacy `_create_transaction`/`execute_tool` → `save_transaction`: caller передає той самий operation_id. `tool_use_id` наразі лише використовується як прив’язка відповіді моделі й не є durable financial receipt. Відсутня LLM або HTTP 503 не доводять цей шлях; тестувати справжній helper без підміни LLM, не називати це запущеним chat.
4. `POST /api/salaries/`, SalaryAdmin add, `_create_salary` → `save_salary`: можна використати той самий контракт для узгодженого response replay. Природний employee/period вже забороняє duplicate row; це не нова незалежна фінансова команда і не причина прибрати UNIQUE.

`Salary.pay` уже має Salary.pk. ERP має proposal_id, а ERP payment додатково reference; додатковий create key цим командам не потрібний для існуючого контракту. Жоден чинний CLI writer із frozen inventory не створює ручну finance.Transaction через цей API; не вводити нову CLI команду заради тесту.

## 8. Допуск складу та Document mutex: лише прийнятий вузький ризик

Поточний `write_lock()` захищає ERP dispatch/approval, але `operations.views.upload` та `document_review` пишуть Document **без нього**. `usable()`/`accepted_documents()`/`newest()` використовуються у reserve, quality, start, finish, ship, change/apply_change. ERP fingerprint містить document id/checksum/status. Отже, записи, що визначають допустимість складу, не мають спільної серіалізації з цією допустимістю. Це статична межа, для якої ще потрібен реальний red; не твердження про вже доведену втрату грошей.

| Mapping / пара | Валідна fixture та реальні виклики | Оракул, який не плутає порядок |
|---|---|---|
| OPS-upload + ERP-ship (або ERP-finish) + CORE-execute | M.required_documents=[cert], L approved з latest approved DA; готовий proposal відвантаження 7. Одночасно confirm та multipart upload DB тієї самої code, revision=B. | Якщо DB commit перед admission reads — старий proposal відхилено, рухів=0. Якщо ERP захищене рішення перше — допустимий один рух 7; upload має серіалізуватися після цього рішення/commit. Контрольована пауза навколо фактичних SQL має довести, чи upload може закомітитися між fingerprint/admission та Movement при утримуваному ERP lock. Не оголошувати сам фінальний факт «є нова версія і старий рух» дефектом: законний попередній рух є історією. |
| OPS-review + ERP-quality + CORE-execute | DA latest, text/checksum валідні, status=needs_review; L pending з DA. Одночасно review checksum=DA.checksum та реальний quality preview/confirm. | Не отримати approved Lot на підставі неперевіреного документа. Якщо review завершився першим, новий перегляд і погодження можуть дозволити quality; якщо quality перевіряло раніше — предметна відмова з нульовим Inspection/рухом. Старий fingerprint не має перетворитися на мовчазно інший погоджений стан. |
| OPS-review + OPS-upload, пов’язано з ERP-quality/ship | DA needs_review; POST review DA та upload DB під тим самим document code; потім справжній ERP admission для Lot із DA | Приймати лише документ, який справді був latest під спільним порядком; після DB чинні ERP quality/ship не використовують DA як latest. Негативний ERP запит не змінює залишок/рухи. Не змінювати старі bytes/version ID і не розгортати A08 storage design. |

Важливо для тестової дисципліни: довільне планування потоків не встановлює, хто виграв. Або явно спостерігати/контролювати реальний порядок SQL, або приймати обидва законні послідовні результати. Сам timeout, ORM exception або наявність пізнішого документа після законного руху не є доказом цього gap.

## 9. Rollback та порядок locks

Це спільні регресії wrappers, а не нові money operations:

- `CORE-erp-preview`, `CORE-proposal`, `CORE-execute`: реальним SQL trace підтвердити `write_lock` перед fingerprint та snapshot «Було», а також fresh proposal/actor після очікування lock. Чинні A01 assertions зберегти; додати конкурентний сценарій, не лише послідовний trace.
- Синтетичний DB trigger на фінальному Event/receipt UPDATE після Movement INSERT: rollback повертає всі Lot/Reservation/SalesLine/Invoice значення, не лишає Event, running receipt чи orphan Lot. Два callers того самого proposal при failure не створюють частковий стан; після зняття тригера retry створює один результат.
- Для financial key та audit: аналогічний реальний failure у кінці однієї transaction, повний rollback, повтор того самого ключа. A02 payment rollback і A05 archive/audit rollback лишаються чинними, не дублювати їх без прив’язки до нового claim.
- Поточні фінансові lock порядки: update Salary перед поточним читанням; для нового/зміненого Employee у save_salary — Employee no-op UPDATE перед archive guard; update Transaction перед reverse salary-link validation; archive бере write lock тієї самої моделі. Не вводити lock inversion новим receipt claim.
- Поточний ERP mutex робить `get_or_create`/читання Configuration перед UPDATE. На SQLite це може дати lock-upgrade 409; на PostgreSQL update все одно бере row lock. Не використовувати JSON revision counter як oracle монотонності: поточний запис revision не є F increment і цей counter не входить у ERP fingerprint. Oracle — справжня серіалізація та бізнесовий постстан.

## 10. Решта frozen inventory: mapping без штучного розширення

| Рядки | Як ураховано в межах A06 |
|---|---|
| 26 ERP + 9 CORE | Таблиці 4–5, preview rollback, proposal receipt, conflict та lock order. Aliases не рахуються як нові 35 операцій. |
| DEF-01 / DEF-02 | Додаткові concurrent finish/pay, зі збереженням чинних A01/A02 перевірок. |
| DEF-03…DEF-12, API-salary-adapter / API-transaction-adapter | Спільні save/archive сценарії таблиці 6 плюс реальні API/admin aliases; зміст A05 не змінено. |
| API-transaction-create / AI-create-transaction | Новий ключ повтору — таблиця 7; нині гарантії немає. |
| API-contract-save / ADMIN-contract-save / AI-create-contract | Зберігають умови/суму договору, не проводку чи рух. Немає operation key, number не UNIQUE; повтор create може створити два договори. Не видавати це за ідемпотентний create і не дедуплікувати за сумою. Це межа keyed create охоплення; не переносити Contract у новий writer у цьому плані. |
| API/ADMIN-counterparty-save, API/ADMIN-employee-save, ADMIN-branch-save; AI-create/update-employee, AI-create-counterparty | Довідники, не окремі грошові/складські проводки. Employee archive/create Salary race включено там, де є конкретний вплив. Не розширювати gate 5 до всіх nonfinancial lost updates. |
| API-contract-delete / API-counterparty-delete; ADMIN-contract-delete / ADMIN-counterparty-delete / ADMIN-branch-delete; AI-delete-counterparty | A05 PROTECT не має зникати при конкуренції з прив’язкою фінансового джерела. Додатковий вузький mixed pair за потреби: delete довідника проти save_transaction із цим FK — або створений TX і delete conflict, або довідник видалений і create відхилено; ніколи мовчазний NULL існуючого source. Не додавати архівування нових сутностей. |
| OPS-upload / OPS-review | Лише складський admission і спільний lock — таблиця 8. |
| OPS-request / OPS-quote / OPS-settings | Request/quote з UNIQUE code та organization settings не створюють Movement/Transaction. Quote→Purchase integration — B01; cash key цим settings endpoint не змінюється. Не переносити це в A06. |
| AI-create-salary / AI-pay-salary / AI-delete-employee / AI-undo | Реальні внутрішні helpers у таблицях 6–7, із власними dict аргументів на worker, без зовнішнього LLM запиту. |
| AI-dispatcher / AI-loop / AI-chat / AI-chat-file | Це aliases виконання, не нові фінансові команди. Durable operation_id треба передавати до shared writer. HTTP 503 за відсутності ключа моделі не є green concurrency доказом. |
| CLI-bos-demo / CLI-erp-demo / CLI-workspace / CLI-branches | Demo seed/setup, не повтор користувацької проводки. Старі dataset markers/PROTECT guards зберігаються; жодного запуску на оригінальних БД. Direct dispatch фінансово-складські дії вже охоплені ORM pair таблицею. Не обіцяти одночасний bootstrap двох seed processes як перевірений production workflow. |

## 11. Що реально є та чого ще немає

Наявне: реальні A02 одночасні stale ORM та HTTP pay тести; послідовні A01 finish/replay і SQL lock-order; A05 single-path archive/save/rollback. Старий inventory probe має 11 SQLite ORM конкуренцій, але його assertions фіксують тодішні результати й він не є поточним gate 5.

Відсутнє/не доведене на час огляду:

1. `scripts/verify.py` посилається на gate 5 `scripts/check_concurrency.py`; повне поточне покриття кожної ERP/financial операції ще не реалізоване.
2. Transaction create не має durable operation_id/receipt ні в API, ні у shared command/admin/AI alias. Два однакові no-key POST не є відповідною failing regression: red має явно передавати той самий новий ключ.
3. Немає повного парного HTTP покриття 26 ERP actions, різних stale proposals, змішаних pay/edit/archive та нового фінансового claim rollback на обох СУБД.
4. Document upload/review не входять до ERP mutex; треба довести й закрити лише їхній конкретний вплив на складський admission, без A08 redesign.
5. Direct `dispatch` не має власного operation ID. Для internal command з достатнім ресурсом два окремі виклики можуть законно виконатися двічі; ідемпотентність клієнтського ERP наміру забезпечує proposal wrapper. `Movement.reference` не є загальним UNIQUE key; payment reference перевіряється через Event під ERP mutex, окремий DB constraint — A07.
6. Повний PostgreSQL concurrency результат — **НЕ ЗАПУЩЕНО**. SQLite та code review не замінюють його.

Порядок реалізації для root: (а) зберегти red keyed financial create + повний pair harness; (б) мінімально додати ключ усередині shared command, не другий writer; (в) провести 26 proposal pairs та 11 contention cases з постстаном; (г) відтворити вузький document admission gap і виправити спільний порядок; (ґ) запуск на обох реальних СУБД, потім повний verify. Цей документ не позначає A06 чи gate 5 зеленими.
