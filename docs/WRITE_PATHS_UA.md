# BoS · інвентаризація шляхів запису 0.1

Дата: 11.09.2026. Код: `/workspace/sites/bos-original-refined`.

**Знайдено 12 канонічних місць із вердиктом «дефект»: 2 вже прийняті A01/A02 і 10 додаткових. Стоп-умова 8.6 спрацювала. Виправлення не починалися.** Поточні дефекти доведені 18 відтвореннями на новій синтетичній SQLite. Серед них справжні HTTP запити через чинні middleware/CSRF і авторизований Django admin; два конкурентні `mark_paid` — справжні ORM-з’єднання з бар’єром після читання, без mocks.

Консервативний рахунок: `SalarySerializer.create/update` — одне місце; single/bulk delete одного ModelAdmin — одне місце; URL aliases, `pay→mark_paid`, `ModelViewSet→Serializer` не подвоюються. Ці групи містять різні функції, усі названі в матриці. Навіть якщо не враховувати жодного admin-шляху, є 7 незалежних місць: finish, mark_paid, два serializers і три API видалення.

## Докази та межі

Команда:

```bash
/workspace/scratch/c7b51e996a9f/demo-check-env/bin/python -B /workspace/scratch/c7b51e996a9f/tmp/evidence/INVENTORY/probe.py
```

Фактичний stdout: `cases=18`, `all_defects_reproduced=true`, `checkout_databases_unchanged=true`, `application_python_sources_unchanged=true`; exit 0. **Цей exit 0 означає успішне відтворення дефектів, а не приймання BoS.** Повні факти, HTTP trace, writable serializer fields, admin registry, вихідний код успадкованих DRF/Django write-методів і SHA до/після — у `evidence/INVENTORY/DETAILS.json`. Python 3.12; Django 6.0.5; DRF 3.17.1; SQLite 3.53.1. Migrations виконані тільки на новому `tmp/master_inventory_db_*/audit.sqlite3`.

Код застосунку/checkout не змінено. Наявні `*.sqlite3` у checkout лише хешувалися; їхні фінансові записи для 0.5 не читались. PostgreSQL, HTTP-конкурентність, браузер, Windows, зовнішня LLM, клієнтська звірка, весь suite і `verify` у цьому аудиті **не запускалися**. Наявність mutex не прирівнюється до приймання PostgreSQL; BinaryField не оголошується доведено несумісним із ним.

Статичне охоплення: `rg` по всіх Python writers (`create/save/update/delete/get_or_create/update_or_create/bulk_*`), фактичні URLconf/DRF routes, serializer write fields, Django admin registrations, FK CASCADE/SET_NULL/PROTECT, legacy tool handlers і management commands. У custom коді не знайдено додаткових raw SQL writers, signal receivers, ERP ModelViewSet/admin registrations. Усі **26/26** ERP `SCHEMAS` відображено. Read-only getters, snapshots/search/export і Task/Chat writers без впливу на гроші/склад позначені в межах охоплення нижче; вони належать наступній матриці прав A04, а не додатковим проведенням.

Вердикти: **«дефект»** — відтворене поточне порушення складського/платіжного/історичного інваріанта; **«ризик»** — є write-path або контрактна прогалина, але її конкретний ефект не відтворено в цьому класі; **«перевірено локально»** — тільки названий SQLite сценарій, не універсальна гарантія. Для попередніх ERP concurrency/rollback доказів прямо вказано `DATA_AUDIT_UA.md`; це не новий запуск.

## Підтверджені місця

| ID | Місце | Фактичний результат | Доказ у JSON |
|---|---|---|---|
| DEF-01 | `erp.service.dispatch[finish]` | Два резерви5+5, випуск10: залишок5, рухи0, produced10. Повтор proposal повертає той самий receipt без нових рядків. | `finish_repeated_lot` |
| DEF-02 | `Salary.mark_paid` | Два pending ORM-об’єкти у двох потоках: 2 витрати100, Salary посилається на одну. Додатково EUR зарплата→UAH витрата. | `salary_concurrent_payment`, `salary_payment_currency` |
| DEF-03 | `SalarySerializer.create/update` | POST paid→201 без проводки; PATCH amount→200 з різними сумами; PATCH pending→pay дає нову витрату при збереженні старої. | `salary_serializer_create_paid`, `salary_serializer_update_paid`, `salary_serializer_reopen_then_pay` |
| DEF-04 | `TransactionSerializer.update` | PATCH витрати100 на дохід300→200; Salary лишається paid100. | `transaction_serializer_update_salary_expense` |
| DEF-05 | `SalaryViewSet.destroy` | DELETE→204; Salary зникла, Transaction лишилася без джерела. | `salary_api_destroy` |
| DEF-06 | `TransactionViewSet.destroy` | DELETE→204; Salary лишилася paid, transaction=NULL. | `transaction_api_destroy` |
| DEF-07 | `EmployeeViewSet.destroy` | DELETE→204 для працівника без ERP PROTECT; Salary каскадно зникла, expense лишився. | `employee_api_destroy_salary_cascade` |
| DEF-08 | Salary admin `save_model` | Справжня форма paid без Transaction→302; неузгоджений стан збережено. | `salary_admin_save_model` |
| DEF-09 | Transaction admin `save_model` | Форма переписує витрату100 на дохід400→302, Salary не змінюється. | `transaction_admin_save_model` |
| DEF-10 | Salary admin `delete_model/delete_queryset` | І одиничний, і масовий delete→302; джерело expense видалено. | `salary_admin_delete_single/bulk` |
| DEF-11 | Transaction admin `delete_model/delete_queryset` | І одиничний, і масовий delete→302; Salary paid без expense. | `transaction_admin_delete_single/bulk` |
| DEF-12 | Employee admin `delete_model/delete_queryset` | І одиничний, і масовий delete→302; payroll історія каскадно втрачена. | `employee_admin_delete_single/bulk` |

Проблема admin не полягає у відсутності будь-якої транзакції: Django обгортає change/delete форми в `atomic`, а Collector робить каскадне видалення атомарним. Помилка — відсутність доменного правила незмінної виплати та її обов’язкового джерела. Атомарне видалення історії все одно порушує інваріант. Для старого AI встановлена фактична недоступність поточних LLM POST через порожній API key; його приховані callers перелічено, але не додано до count доступних дефектів.

## Повна матриця функцій

Для ERP «M» означає фактичний `UPDATE Configuration(key='erp_write')` у `dispatch:151–152`. Він відбувається до предметних читань усередині dispatch. До fingerprint/before у preview/execute він **не** відбувається — цей ризик явно виділено в обгортках. `ActionProposal.receipt` і CAS вже забезпечують повтор одного proposal; відсутність UNIQUE для JSON payment reference не означає відсутність чинної локальної ідемпотентності.

### ERP

| ID · модуль/функція | Читає | Пише | Atomic | Lock | Proposal/confirm | Ідемпотентність | Вердикт |
|---|---|---|---|---|---|---|---|
| ERP-item · `erp/service.py:154–160` `dispatch[item]` | BOM-компоненти; довідники, ціни, валюта | Item | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | ризик |
| ERP-location · `erp/service.py:161–164` `dispatch[location]` | Постачальник для місця supplier | Location | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | ризик |
| ERP-order · `erp/service.py:165–173` `dispatch[order]` | Customer, Employee, Item.revision; рядки, ціни | SalesOrder + SalesLine | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | ризик |
| ERP-confirm_order · `erp/service.py:174–177` `dispatch[confirm_order]` | SalesOrder.status | SalesOrder.status | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | ризик |
| ERP-opening · `erp/service.py:178–181` `dispatch[opening]` | Item, Location; початкова кількість і ціна | newlot → Lot + Movement | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | ризик |
| ERP-purchase · `erp/service.py:182–187` `dispatch[purchase]` | Item, Supplier, Production.bom; умови закупівлі | Purchase | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | ризик |
| ERP-receive · `erp/service.py:188–193` `dispatch[receive]` | Purchase.quantity/received/price/extras; місце | Lot + Movement(receipt) + Purchase.received/status | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | перевірено локально |
| ERP-job · `erp/service.py:194–207` `dispatch[job]` | Item.bom/routing/cost; SalesLine.shipped; інші Production | Production | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | ризик |
| ERP-reserve · `erp/service.py:208–224` `dispatch[reserve]` | Lot, SUM Reservation, потреба SalesLine/Production, документи | Reservation | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | перевірено локально |
| ERP-release · `erp/service.py:225–228` `dispatch[release]` | Reservation.quantity | Reservation.quantity | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | перевірено локально |
| ERP-transfer · `erp/service.py:229–235` `dispatch[transfer]` | Lot.quantity, резерви, ціна, місце та job | Movement(out/in), вихідна Lot, нова Lot | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | перевірено локально |
| ERP-quality · `erp/service.py:238–244` `dispatch[quality]` | Lot; чинність документів; inspector | Lot.quality + Inspection | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | ризик |
| ERP-attach · `erp/service.py:236–237` `dispatch[attach]` | Lot.documents; Document | Lot.documents | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | ризик |
| ERP-start · `erp/service.py:245–251` `dispatch[start]` | Production.status/BOM; Reservation; придатність Lot | Production.status | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | перевірено локально |
| ERP-operator · `erp/service.py:252–260` `dispatch[operator]` | Production.status; попередні OperatorEntry; Employee | OperatorEntry | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | перевірено локально |
| ERP-finish · `erp/service.py:261–278` `dispatch[finish]` | Production; окремі застарілі r.lot для повторних резервів | Reservation, Lot.quantity, consume/production Movement, job.produced/cost | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | дефект (DEF-01) |
| ERP-ship · `erp/service.py:279–288` `dispatch[ship]` | SalesLine, Lot, Reservation, документи/валюта | Reservation, Lot, shipment Movement, SalesLine.shipped | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | перевірено локально |
| ERP-return · `erp/service.py:289–296` `dispatch[return]` | SUM shipment/return по line+lot | Нова blocked Lot + return Movement | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | перевірено локально |
| ERP-invoice · `erp/service.py:297–304` `dispatch[invoice]` | Order/SalesLine shipped−invoiced та price | SalesLine.invoiced + Invoice + InvoiceLink | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | перевірено локально |
| ERP-payment · `erp/service.py:305–309` `dispatch[payment]` | Invoice.amount/paid; Event.payload.reference | Invoice.paid + Event(erp_payment) | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | перевірено локально |
| ERP-change · `erp/service.py:310–313` `dispatch[change]` | Item; чинний approved Document | ChangeOrder | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | ризик |
| ERP-apply_change · `erp/service.py:314–321` `dispatch[apply_change]` | ChangeOrder, Document, Item, відкриті Production | Item.revision/document, Production.needs_review, ChangeOrder | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | ризик |
| ERP-resolve_job · `erp/service.py:322–326` `dispatch[resolve_job]` | Production.needs_review | Production.needs_review | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | ризик |
| ERP-postpone · `erp/service.py:327–330` `dispatch[postpone]` | Purchase | Purchase.due_date | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | ризик |
| ERP-postpone_job · `erp/service.py:327–330` `dispatch[postpone_job]` | Production | Production.due_date | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | ризик |
| ERP-adjust · `erp/service.py:331–336` `dispatch[adjust]` | Lot.quantity; SUM Reservation | Lot.quantity + adjustment Movement | Так: dispatch @atomic | UPDATE Configuration[erp_write] до предметних читань | Так для поточного HTTP; service/seed можуть викликати напряму | receipt/CAS одного proposal_id; не ключ довільного payload | перевірено локально |

- **ERP-item**: Складського руху немає; окремі межі довжини/Decimal належать A07. Доказ: `статичний огляд erp/service.py`.
- **ERP-location**: Руху немає; виклик статично під спільним mutex. Доказ: `статичний огляд erp/service.py`.
- **ERP-order**: Одне замовлення й усі рядки атомарні; приймання конкурентності окремо не запускалося. Доказ: `статичний огляд erp/service.py`.
- **ERP-confirm_order**: Є перевірка quote; окреме повторне підтвердження не досліджувалося. Доказ: `статичний огляд erp/service.py`.
- **ERP-opening**: Створення початкового залишку входить у protected dispatch; окремий HTTP opening у новому probe не запускався. Доказ: `evidence/INVENTORY/DETAILS.json:finish_repeated_lot (початковий баланс — синтетична fixture, не окремий opening endpoint)`; `DATA_AUDIT_UA.md:матриця ERP`.
- **ERP-purchase**: Не створює приходу; зв’язок із RFQ/quote — окремий B01, не гонка залишків. Доказ: `статичний огляд erp/service.py`.
- **ERP-receive**: Локальне паралельне відтворення попереднього аудиту: один успіх, один SQLite conflict. Вартісне округлення окремо не приймалося. Доказ: `DATA_AUDIT_UA.md:receive`.
- **ERP-job**: Агрегація незавершеної потреби під mutex; окрема конкурентна перевірка не запускалася. Доказ: `статичний огляд erp/service.py`.
- **ERP-reserve**: Два послідовні резерви тієї самої партії дозволені; на цьому кроці залишок не списується. Дефект виникає у finish. Доказ: `evidence/INVENTORY/DETAILS.json:finish_repeated_lot`; `DATA_AUDIT_UA.md:reserve`.
- **ERP-release**: Нульовий резерв зберігається законно; попередній SQLite race не показав дубля. Доказ: `DATA_AUDIT_UA.md:release`.
- **ERP-transfer**: Усі ефекти в dispatch atomic; попередній аудит відтворив повний rollback при конфлікті коду нової партії. Доказ: `DATA_AUDIT_UA.md:transfer,rollback_after_move`.
- **ERP-quality**: Документні writers обходять mutex: їх взаємодія з якістю/відвантаженням — неперевірений ризик A06. Доказ: `статичний огляд erp/service.py`.
- **ERP-attach**: Зміна набору документів під mutex, але зовнішні зміни Document — поза ним; A06. Доказ: `статичний огляд erp/service.py`.
- **ERP-start**: У новому probe фактично пройшов start після двох резервів; це не повна перевірка всіх станів. Доказ: `evidence/INVENTORY/DETAILS.json:finish_repeated_lot`.
- **ERP-operator**: У новому probe фактично записано завершену операцію; право кожної ролі ще не прийняте. Доказ: `evidence/INVENTORY/DETAILS.json:finish_repeated_lot`.
- **ERP-finish**: Після резервів 5+5 з партії10: produced10, залишок5, сума рухів0. Mutex не усуває stale ORM усередині одного виклику. Доказ: `evidence/INVENTORY/DETAILS.json:finish_repeated_lot`.
- **ERP-ship**: Локальна паралельна пара попереднього аудиту серіалізувалась; документи потребують спільного lock-контракту. Доказ: `DATA_AUDIT_UA.md:ship`.
- **ERP-return**: Історію shipped/invoiced навмисно не переписує; кредит-нота — окремий процес, не прихований дефект. Доказ: `DATA_AUDIT_UA.md:return`.
- **ERP-invoice**: Грошова гонка локально не відтворилась. Окремо доведено: clean допускає code31 при model max30; це дефект контракту типів A07, не додатковий RMW writer. Доказ: `DATA_AUDIT_UA.md:invoice,sqlite_invoice_code_over_model_limit`.
- **ERP-payment**: Є mutex і перевірка reference; Invoice та Event — локальний факт оплати, не Transaction і не банківський переказ. UNIQUE scalar key відсутній: A07. Доказ: `DATA_AUDIT_UA.md:payment,payment_dup`.
- **ERP-change**: Руху немає; конкурентна заміна документа не запускалася. Доказ: `статичний огляд erp/service.py`.
- **ERP-apply_change**: Інженерний writer впливає на дозволені складські дії; role ceo перевіряється. Документна гонка — A06. Доказ: `статичний огляд erp/service.py`.
- **ERP-resolve_job**: Дозвіл продовжити стару версію; mutex наявний, окреме приймання не запускалося. Доказ: `статичний огляд erp/service.py`.
- **ERP-postpone**: Дата постачання під mutex; не створює приходу або оплати. Доказ: `статичний огляд erp/service.py`.
- **ERP-postpone_job**: Дата виробництва під mutex; не створює руху. Доказ: `статичний огляд erp/service.py`.
- **ERP-adjust**: Локальна гонка попереднього аудиту серіалізується; неправильний порядок fingerprint щодо lock — окремий ризик A06. Доказ: `DATA_AUDIT_UA.md:adjust`.

### Обгортки

| ID · модуль/функція | Читає | Пише | Atomic | Lock | Proposal/confirm | Ідемпотентність | Вердикт |
|---|---|---|---|---|---|---|---|
| CORE-move · `erp/service.py:97–102` `move` | Переданий Lot.quantity + SUM Reservation | Lot.quantity + Movement | У поточних production callers: так; власного atomic немає | Успадкований M; helper не блокує сам | Через dispatch callers | Через caller | перевірено локально |
| CORE-newlot · `erp/service.py:104–107` `newlot` | Item, documents, ціна/кількість | Lot, далі move→Movement | Через dispatch | Через dispatch | Через dispatch | UNIQUE code + receipt caller | перевірено локально |
| CORE-dispatch · `erp/service.py:146–153,337–339` `dispatch (спільна частина)` | Configuration[erp_write]; далі за гілкою | Mutex revision; Event; гілка ERP | Так @atomic | M до предметних читань | Не примушує сам; production HTTP входить через confirm | receipt у execute; власного operation_id немає | перевірено локально |
| CORE-preview-effect · `erp/service.py:341–345` `preview_effect` | Стан dispatch | Тимчасові ERP записи з примусовим rollback | Так | M через dispatch | Лише симуляція | Не зберігає результат | ризик |
| CORE-erp-preview · `erp/views.py:18–24` `preview` | fingerprint + before snapshot ДО M | Тимчасовий dispatch, rollback; далі ActionProposal | Так для симуляції; proposal поза ним | M пізніше fingerprint/before | Створює proposal | Новий proposal кожного preview | ризик |
| CORE-proposal · `operations/service.py:79–85` `preview` | role/session; validate + fingerprint | ActionProposal | Немає outer atomic; INSERT атомарний | Немає | Створює proposal | UUID; повтор створює інший proposal | ризик |
| CORE-execute · `operations/service.py:87–112` `execute` | Proposal, role, expiry, fingerprint; snapshot | CAS receipt; ERP/Event або Task/Audit; final receipt | Так @atomic | CAS proposal; ERP mutex лише після fingerprint/before | Так; session-bound proposal | receipt early return + CAS receipt IS NULL | ризик |
| CORE-ops-preview · `operations/views.py:99` `preview` | Payload/session через service.preview | ActionProposal через service.preview | Як caller preview | Як caller preview | Так | Як caller preview | ризик |
| CORE-confirm · `operations/views.py:103–106` `confirm` | confirmed + proposal_id | Через execute | Через execute | Через execute | Вимагає confirmed is True | Через execute | перевірено локально |

- **CORE-move**: Є перевірки new>=0 та new>=reserved; precondition: актуальний ORM-об’єкт. Порушення precondition у finish уже враховане DEF-01. Прямого HTTP/admin/legacy caller немає. Доказ: `evidence/INVENTORY/DETAILS.json:finish_repeated_lot`; `DATA_AUDIT_UA.md:rollback_after_move`.
- **CORE-newlot**: accepted_documents викликається, але його список missing не відхиляє creation: нова партія pending; не названо помилкою дозволене приймання з карантином. Доказ: `evidence/INVENTORY/DETAILS.json:finish_repeated_lot`.
- **CORE-dispatch**: Усі 26 гілок перелічені окремо. Не дублює DEF-01; direct service є в seed. Відсутність select_for_update не означає відсутність серіалізації. Доказ: `DATA_AUDIT_UA.md:матриця ERP`; `evidence/INVENTORY/DETAILS.json:finish_repeated_lot`.
- **CORE-preview-effect**: Production caller не знайдений; helper присутній. Самостійне приймання не запускалося. Доказ: `статичний огляд call sites`.
- **CORE-erp-preview**: Порядок читань перед mutex доведений кодом. Наслідок для двох PostgreSQL транзакцій не відтворено; це ризик A06, а не доведена SQLite корупція. Доказ: `evidence/INVENTORY/DETAILS.json:request_trace`; `erp/views.py:20–23`.
- **CORE-proposal**: Не проводить склад або гроші; відсутність спільного lock належить узгодженню snapshot A06. Доказ: `статичний огляд operations/service.py`.
- **CORE-execute**: Ідемпотентність одного proposal вже є і новим HTTP повтором підтверджена. Ризик A06: різні proposals можуть перевірити fingerprint до спільного mutex; PostgreSQL не запускали. Доказ: `evidence/INVENTORY/DETAILS.json:finish_repeated_lot`; `DATA_AUDIT_UA.md:rollback_after_move`.
- **CORE-ops-preview**: Маршрут-обгортка CORE-proposal; не додатковий writer чи дефект. Доказ: `operations/urls.py:3`.
- **CORE-confirm**: Маршрут-обгортка CORE-execute; той самий finish дефект не рахується знову. Доказ: `evidence/INVENTORY/DETAILS.json:request_trace`.

### Фінанси/API

| ID · модуль/функція | Читає | Пише | Atomic | Lock | Proposal/confirm | Ідемпотентність | Вердикт |
|---|---|---|---|---|---|---|---|
| DEF-02 · `finance/models.py:153–189` `Salary.mark_paid` | self.status/amount/currency; Employee/branch; дата | Transaction + Salary.status/date/transaction | Лише create+save; paid check ДО atomic | Немає; self отриманий раніше | Ні | Лише self.status; старі об’єкти та reset обходять | дефект |
| API-pay · `finance/views.py:31–39` `SalaryViewSet.pay` | get_object із select_related employee/transaction | Через Salary.mark_paid | Тільки всередині mark_paid | Немає | Ні | Як mark_paid | дефект (DEF-02; alias не рахується повторно) |
| DEF-03 · `finance/serializers.py:42–49` `SalarySerializer.create / update (успадковані)` | Вхідні amount/currency/status/transaction/employee; instance на update | Salary напряму; Transaction не синхронізує | Немає request-wide atomic | Немає | Ні | UNIQUE employee+period захищає лише новий місяць | дефект |
| API-salary-adapter · `finance/views.py:27–29` `SalaryViewSet.create / update / partial_update` | DRF request/instance; select_related salary | Через SalarySerializer.save | Немає outer atomic | Немає | Ні | Через serializer | дефект (DEF-03; alias не рахується повторно) |
| API-transaction-create · `finance/serializers.py:32–39` `TransactionSerializer.create (успадкований)` | FK та вхідний факт платежу | Transaction | Один INSERT; outer atomic немає | Немає | Ні | Немає operation/proposal key | ризик |
| DEF-04 · `finance/serializers.py:32–39` `TransactionSerializer.update (успадкований)` | Transaction instance; writable amount/direction/currency | Переписує Transaction, не звіряє Salary | Немає request-wide atomic | Немає | Ні | Немає | дефект |
| API-transaction-adapter · `finance/views.py:22–24` `TransactionViewSet.update / partial_update` | get_object Transaction | Через TransactionSerializer.save | Немає outer atomic | Немає | Ні | Немає | дефект (DEF-04; alias не рахується повторно) |
| DEF-05 · `finance/views.py:27–29` `SalaryViewSet.destroy / perform_destroy (успадковані)` | Salary instance та залежності Collector | DELETE Salary; Transaction лишається | DELETE має ORM transaction; get_object раніше | Немає предметного lock | Ні | Повтор DELETE→404; не фінансова ідемпотентність | дефект |
| DEF-06 · `finance/views.py:22–24` `TransactionViewSet.destroy / perform_destroy (успадковані)` | Transaction та reverse Salary | DELETE Transaction; Salary.transaction SET_NULL | ORM deletion atomic; get_object раніше | Немає предметного lock | Ні | Повтор DELETE→404 | дефект |
| DEF-07 · `employees/views.py:8–19` `EmployeeViewSet.destroy / perform_destroy (успадковані)` | Employee + пов’язані Salary | CASCADE Salary; витрати Transaction лишаються | ORM deletion atomic; get_object раніше | Немає предметного lock | Ні | Повтор DELETE→404 | дефект |
| API-contract-save · `finance/serializers.py:24–29` `ContractSerializer.create / update (успадковані)` | Contract instance/FK; amount/currency/status | Contract | Немає outer atomic | Немає | Ні | Немає; number не UNIQUE | ризик |
| API-counterparty-save · `finance/serializers.py:5–21` `CounterpartySerializer.create / update (успадковані)` | Counterparty, на update queryset із total_debit/credit | Довідникові поля Counterparty | Немає outer atomic | Немає | Ні | Немає | ризик |
| API-contract-delete · `finance/views.py:17–19` `ContractViewSet.destroy / perform_destroy` | Contract, related Transaction/Document | DELETE Contract; SET_NULL Transaction.contract/Document.contract | ORM deletion atomic | Немає предметного lock | Ні | 404 після видалення | ризик |
| API-counterparty-delete · `finance/views.py:12–14` `CounterpartyViewSet.destroy / perform_destroy` | Counterparty, contracts, транзакції; ERP PROTECT | CASCADE Contract; SET_NULL фінансових посилань | ORM deletion atomic | Немає предметного lock | Ні | 404 після видалення | ризик |
| API-employee-save · `employees/serializers.py:6–30` `EmployeeSerializer.create / update (успадковані)` | Employee, branch | Employee; наступна Salary.mark_paid читає Employee | Немає outer atomic | Немає | Ні | Немає | ризик |

- **DEF-02**: Два потоки дають дві витрати100; nullable OneToOne не створює обов’язкового джерела на Transaction. Додатково currency не передано: EUR→UAH. Це одне канонічне місце. Доказ: `evidence/INVENTORY/DETAILS.json:salary_concurrent_payment`; `evidence/INVENTORY/DETAILS.json:salary_payment_currency`.
- **API-pay**: Alias DEF-02: той самий дефект не рахується ще раз. HTTP pay реально використано для fixtures виплат. Доказ: `evidence/INVENTORY/DETAILS.json:request_trace`.
- **DEF-03**: POST status=paid дає201 без проводки; PATCH amount дає200 при незмінній проводці; PATCH pending → pay створює другий expense. Create/update одного serializer консервативно згруповано. Доказ: `evidence/INVENTORY/DETAILS.json:salary_serializer_create_paid`; `evidence/INVENTORY/DETAILS.json:salary_serializer_update_paid`; `evidence/INVENTORY/DETAILS.json:salary_serializer_reopen_then_pay`.
- **API-salary-adapter**: Alias DEF-03: ModelViewSet маршрути POST/PUT/PATCH ведуть до того самого serializer. Доказ: `evidence/INVENTORY/DETAILS.json:drf_write_routes`.
- **API-transaction-create**: Прямий mutable ledger обхід A05; для окремого ручного факту відсутність RMW-lock сама по собі не доводить корупцію. Повтор HTTP create не має узгодженого replay-контракту. Доказ: `evidence/INVENTORY/DETAILS.json:serializer_fields`.
- **DEF-04**: PATCH витратної проводки зарплати100 на дохід300 повертає200; Salary лишається paid100. Доказ: `evidence/INVENTORY/DETAILS.json:transaction_serializer_update_salary_expense`.
- **API-transaction-adapter**: Alias DEF-04: маршрути update не окреме місце корупції. Create описаний окремо як ризик. Доказ: `evidence/INVENTORY/DETAILS.json:drf_write_routes`.
- **DEF-05**: DELETE paid Salary дає204, історію нарахування втрачено, витрата не має джерела. Доказ: `evidence/INVENTORY/DETAILS.json:salary_api_destroy`.
- **DEF-06**: DELETE зарплатної Transaction дає204, Salary лишається paid з transaction=NULL. Доказ: `evidence/INVENTORY/DETAILS.json:transaction_api_destroy`.
- **DEF-07**: Для працівника без ERP PROTECT-залежностей DELETE дає204 і знищує його payroll history. Наявність інших PROTECT FK не захищає всіх працівників. Доказ: `evidence/INVENTORY/DETAILS.json:employee_api_destroy_salary_cascade`.
- **API-contract-save**: Грошові умови напряму змінюються через ContractViewSet17–19; рухів не створює. Немає доведеного payroll/stock розходження; включити контракт запису A05. Доказ: `finance/views.py:17–19`; `finance/models.py:53–77`.
- **API-counterparty-save**: Агрегати total_debit/credit є read-only і не зберігаються. Зміна довідника впливає на атрибуцію фінансів, але не списує баланс. Доказ: `finance/views.py:12–14`; `finance/serializers.py:6–8`.
- **API-contract-delete**: Статично встановлена втрата посилань при видаленні. Окремий сценарій історичної атрибуції не запускався; це ризик A05, не доданий підтверджений monetary defect. Доказ: `finance/models.py:108`; `operations/models.py:14`.
- **API-counterparty-delete**: ERP Purchase/Invoice/SalesOrder можуть заборонити delete; без них FK атрибуція змінюється. HTTP окремо не відтворювався. Доказ: `finance/models.py:69,107–108`; `erp/models.py:43,90`; `operations/models.py:59`.
- **API-employee-save**: Записує довідник, а не нарахування; історичні проводки не переписує напряму. Контракт actor/policy належить A03/A04/A05. Доказ: `employees/views.py:8–19`.

### Admin

| ID · модуль/функція | Читає | Пише | Atomic | Lock | Proposal/confirm | Ідемпотентність | Вердикт |
|---|---|---|---|---|---|---|---|
| DEF-08 · `finance/admin.py:7` `Salary ModelAdmin.save_model / save_form` | Salary + форма/FK | Salary.save() | save/change: admin.changeform_view @atomic; delete_view також atomic; bulk — ORM Collector atomic | Немає ERP/Salary lock | Ні; admin submit не proposal | Немає | дефект |
| DEF-09 · `finance/admin.py:6` `Transaction ModelAdmin.save_model / save_form` | Transaction + форма/FK | Transaction.save() | save/change: admin.changeform_view @atomic; delete_view також atomic; bulk — ORM Collector atomic | Немає ERP/Salary lock | Ні; admin submit не proposal | Немає | дефект |
| ADMIN-contract-save · `finance/admin.py:5` `Contract ModelAdmin.save_model / save_form` | Contract + форма/FK | Contract.save() | save/change: admin.changeform_view @atomic; delete_view також atomic; bulk — ORM Collector atomic | Немає ERP/Salary lock | Ні; admin submit не proposal | Немає | ризик |
| ADMIN-counterparty-save · `finance/admin.py:4` `Counterparty ModelAdmin.save_model / save_form` | Counterparty + форма/FK | Counterparty.save() | save/change: admin.changeform_view @atomic; delete_view також atomic; bulk — ORM Collector atomic | Немає ERP/Salary lock | Ні; admin submit не proposal | Немає | ризик |
| ADMIN-employee-save · `employees/admin.py:5–14` `Employee ModelAdmin.save_model / save_form` | Employee + форма/FK | Employee.save() | save/change: admin.changeform_view @atomic; delete_view також atomic; bulk — ORM Collector atomic | Немає ERP/Salary lock | Ні; admin submit не proposal | Немає | ризик |
| ADMIN-branch-save · `branches/admin.py:6–11` `Branch ModelAdmin.save_model / save_form` | Branch + форма/FK | Branch.save() | save/change: admin.changeform_view @atomic; delete_view також atomic; bulk — ORM Collector atomic | Немає ERP/Salary lock | Ні; admin submit не proposal | Немає | ризик |
| DEF-10 · `finance/admin.py:7` `Salary ModelAdmin.delete_model / delete_queryset` | Salary та Collector залежностей | DELETE Salary + CASCADE/SET_NULL | save/change: admin.changeform_view @atomic; delete_view також atomic; bulk — ORM Collector atomic | Немає предметного lock | Ні; admin confirmation не ActionProposal | 404/empty queryset після delete | дефект |
| DEF-11 · `finance/admin.py:6` `Transaction ModelAdmin.delete_model / delete_queryset` | Transaction та Collector залежностей | DELETE Transaction + CASCADE/SET_NULL | save/change: admin.changeform_view @atomic; delete_view також atomic; bulk — ORM Collector atomic | Немає предметного lock | Ні; admin confirmation не ActionProposal | 404/empty queryset після delete | дефект |
| DEF-12 · `employees/admin.py:5–14` `Employee ModelAdmin.delete_model / delete_queryset` | Employee та Collector залежностей | DELETE Employee + CASCADE/SET_NULL | save/change: admin.changeform_view @atomic; delete_view також atomic; bulk — ORM Collector atomic | Немає предметного lock | Ні; admin confirmation не ActionProposal | 404/empty queryset після delete | дефект |
| ADMIN-contract-delete · `finance/admin.py:5` `Contract ModelAdmin.delete_model / delete_queryset` | Contract та Collector залежностей | DELETE Contract + CASCADE/SET_NULL | save/change: admin.changeform_view @atomic; delete_view також atomic; bulk — ORM Collector atomic | Немає предметного lock | Ні; admin confirmation не ActionProposal | 404/empty queryset після delete | ризик |
| ADMIN-counterparty-delete · `finance/admin.py:4` `Counterparty ModelAdmin.delete_model / delete_queryset` | Counterparty та Collector залежностей | DELETE Counterparty + CASCADE/SET_NULL | save/change: admin.changeform_view @atomic; delete_view також atomic; bulk — ORM Collector atomic | Немає предметного lock | Ні; admin confirmation не ActionProposal | 404/empty queryset після delete | ризик |
| ADMIN-branch-delete · `branches/admin.py:6–11` `Branch ModelAdmin.delete_model / delete_queryset` | Branch та Collector залежностей | DELETE Branch + CASCADE/SET_NULL | save/change: admin.changeform_view @atomic; delete_view також atomic; bulk — ORM Collector atomic | Немає предметного lock | Ні; admin confirmation не ActionProposal | 404/empty queryset після delete | ризик |

- **DEF-08**: Збереження status=paid без Transaction через справжню admin форму проходить302. Доказ: `evidence/INVENTORY/DETAILS.json:salary_admin_save_model`.
- **DEF-09**: Зарплатна витрата100 переписується на дохід400 через admin302; сума Salary не змінюється. Доказ: `evidence/INVENTORY/DETAILS.json:transaction_admin_save_model`.
- **ADMIN-contract-save**: Пряме збереження amount/currency/status; не спільний фінансовий command. Окремий грошовий дефект не відтворювався. Доказ: `evidence/INVENTORY/DETAILS.json:admin_registry`.
- **ADMIN-counterparty-save**: Зміна довідника впливає на атрибуцію, руху не створює; policy/proposal контракт відсутній. Доказ: `evidence/INVENTORY/DETAILS.json:admin_registry`.
- **ADMIN-employee-save**: Зміна Employee/branch впливає на майбутню виплату; проведень безпосередньо немає. Доказ: `evidence/INVENTORY/DETAILS.json:admin_registry`.
- **ADMIN-branch-save**: Оргструктура визначає групування фінансів; save_model і list_editable не записують amount. Доказ: `evidence/INVENTORY/DETAILS.json:admin_registry`.
- **DEF-10**: Single і bulk delete знищують джерело витрати; обидва фактично302. Одне місце реєстрації, не дві оцінки. Доказ: `evidence/INVENTORY/DETAILS.json:salary_admin_delete_single`; `evidence/INVENTORY/DETAILS.json:salary_admin_delete_bulk`.
- **DEF-11**: Single і bulk delete лишають Salary paid без Transaction; обидва302. Доказ: `evidence/INVENTORY/DETAILS.json:transaction_admin_delete_single`; `evidence/INVENTORY/DETAILS.json:transaction_admin_delete_bulk`.
- **DEF-12**: Single і bulk delete каскадно видаляють Salary, витрата лишається; обидва302. Доказ: `evidence/INVENTORY/DETAILS.json:employee_admin_delete_single`; `evidence/INVENTORY/DETAILS.json:employee_admin_delete_bulk`.
- **ADMIN-contract-delete**: Видалення знімає Transaction.contract і Document.contract; окреме відтворення не запускалося. Доказ: `evidence/INVENTORY/DETAILS.json:admin_registry`.
- **ADMIN-counterparty-delete**: Видаляє contracts та знімає посилання, якщо немає ERP PROTECT; окреме відтворення не запускалося. Доказ: `evidence/INVENTORY/DETAILS.json:admin_registry`.
- **ADMIN-branch-delete**: CASCADE дочірніх Branch + SET_NULL Transaction.branch/Employee.branch; атрибуція змінюється, сума не зникає. Не запускалося. Доказ: `evidence/INVENTORY/DETAILS.json:admin_registry`.

### Документи/закупівлі

| ID · модуль/функція | Читає | Пише | Atomic | Lock | Proposal/confirm | Ідемпотентність | Вердикт |
|---|---|---|---|---|---|---|---|
| OPS-upload · `operations/views.py:91–95` `upload` | Файл; metadata; parse/checksum | Document (нова версія) | Один INSERT; outer atomic немає | Немає ERP mutex | Ні | UNIQUE(code,revision), без receipt | ризик |
| OPS-review · `operations/views.py:220–226` `document_review` | Document.checksum/text; newest; Contract | Document.status/contract | Немає read+write atomic | Немає | Ні; checksum — передумова, не proposal | Немає operation key | ризик |
| OPS-request · `operations/views.py:183–195` `request_create` | Employee, Document, newest; кількість/валюта | ProcurementRequest | Немає outer atomic | Немає | Ні | UNIQUE code; без повторного receipt | ризик |
| OPS-quote · `operations/views.py:199–216` `quote_create` | Request, Supplier, Document; ціна/умови | SupplierQuote | Немає outer atomic | Немає | Ні | UNIQUE code; без receipt | ризик |
| OPS-settings · `operations/views.py:132–141` `settings_update` | Configuration[organization] | Configuration[organization] | get_or_create внутрішній atomic; merge/save поза спільним atomic | Немає | Ні | Повтор значень, без operation key | ризик |

- **OPS-upload**: Версія документа змінює newest і придатність Lot; запис не координується з ERP writers. PostgreSQL interleaving не відтворено; A06. Доказ: `operations/models.py:17`; `DATA_AUDIT_UA.md:документні writers`.
- **OPS-review**: Між перевіркою newest і save може змінитися версія. Поточне паралельне відтворення відсутнє; не видається за підтверджений дефект залишків. Доказ: `operations/views.py:221–225`.
- **OPS-request**: Передетап закупівлі; грошового чи складського руху немає. Актуальність документа читається поза lock. Доказ: `operations/views.py:190–194`.
- **OPS-quote**: Умови відокремлені від Purchase; RFQ→PO є B01. Немає другого складського приходу. Доказ: `operations/views.py:203–215`.
- **OPS-settings**: Цей writer НЕ змінює cash або erp_write: key жорстко organization. Lost update налаштувань можливий, фінансова RMW корупція не заявляється. Доказ: `operations/views.py:133,141`.

### Legacy AI

| ID · модуль/функція | Читає | Пише | Atomic | Lock | Proposal/confirm | Ідемпотентність | Вердикт |
|---|---|---|---|---|---|---|---|
| AI-create-transaction · `ai_assistant/views.py:523–531` `_create_transaction` | Counterparty, amount/direction | Transaction | Один INSERT; outer atomic немає | Немає | Ні | Немає | ризик |
| AI-create-salary · `ai_assistant/views.py:567–574` `_create_salary` | Employee, amount/period | Salary | Один INSERT; outer atomic немає | Немає | Ні | UNIQUE employee+period | ризик |
| AI-pay-salary · `ai_assistant/views.py:577–581` `_pay_salary` | Salary.objects.get | Через mark_paid | Лише mark_paid inner atomic | Немає | Ні | Лише stale status | ризик |
| AI-create-contract · `ai_assistant/views.py:548–554` `_create_contract` | Counterparty + умови | Contract | Один INSERT | Немає | Ні | Немає | ризик |
| AI-create-counterparty · `ai_assistant/views.py:498–502` `_create_counterparty` | Args | Counterparty | Один INSERT | Немає | Ні | Немає | ризик |
| AI-delete-counterparty · `ai_assistant/views.py:515–520` `_delete_counterparty` | Counterparty + Collector | DELETE Counterparty; CASCADE Contract; SET_NULL tx links | ORM deletion atomic; SELECT раніше | Немає | Ні | Немає | ризик |
| AI-create-employee · `ai_assistant/views.py:359–372` `_create_employee` | Args | Employee + EmployeeChangeLog | Немає спільного atomic | Немає | Ні | Немає | ризик |
| AI-update-employee · `ai_assistant/views.py:375–390` `_update_employee` | Employee + before | Employee + EmployeeChangeLog | Немає спільного atomic | Немає | Ні | Немає | ризик |
| AI-delete-employee · `ai_assistant/views.py:393–404` `_delete_employee` | Employee + before + related Salary | EmployeeChangeLog + DELETE Employee/CASCADE Salary | Немає outer atomic; DELETE atomic | Немає | Ні | Немає | ризик |
| AI-undo · `ai_assistant/views.py:417–495` `_undo_last_change` | Останній Task/EmployeeChangeLog; before | У employee-гілці delete/create/update Employee + delete log; cascade Salary | Немає outer atomic | Немає | Ні | Немає; останній log глобальний | ризик |
| AI-dispatcher · `ai_assistant/views.py:621–656` `execute_tool` | Handler map + args | Виклик writer; ловить винятки після можливих commits | Немає | Немає | Ні | tool_use_id не використовується | ризик |
| AI-loop · `ai_assistant/views.py:841–891` `_run_tool_loop` | Модельні tool_use; контекст | execute_tool для кожного model instruction | Немає загального atomic | Немає | Ні | Немає | ризик |
| AI-chat · `ai_assistant/views.py:935–986` `ChatView.post` | Повідомлення/історія; finance context | ChatMessage; через tool loop → writers | Немає загального atomic | Немає | Ні | Немає | ризик |
| AI-chat-file · `ai_assistant/views.py:1177–1278` `chat_with_file` | Файл/історія/finance context | ChatFile/ChatMessage; через tool loop → writers | Немає загального atomic | Немає | Ні | Немає | ризик |

- **AI-create-transaction**: HTTP LLM POST блокує LocalDemoGuard (порожній ANTHROPIC_API_KEY); service callable з Python. Може створити будь-яку amount без ModelSerializer/full_clean; validation/idempotency шляху потребує A05 до активації. Доказ: `ai_assistant/views.py:523–531`; `boss_project/demo_middleware.py:11–13`; `demo_settings.py:18`.
- **AI-create-salary**: HTTP LLM POST блокує LocalDemoGuard (порожній ANTHROPIC_API_KEY); service callable з Python. Параметри period/amount без доменної валідації; default pending. Невалідні значення не відтворювалися через недоступний HTTP. Доказ: `ai_assistant/views.py:567–574`; `boss_project/demo_middleware.py:11–13`; `demo_settings.py:18`.
- **AI-pay-salary**: HTTP LLM POST блокує LocalDemoGuard (порожній ANTHROPIC_API_KEY); service callable з Python. Використовує DEF-02; додаткового поточного місця в count немає. Доказ: `ai_assistant/views.py:577–581`; `boss_project/demo_middleware.py:11–13`; `demo_settings.py:18`.
- **AI-create-contract**: HTTP LLM POST блокує LocalDemoGuard (порожній ANTHROPIC_API_KEY); service callable з Python. Грошові умови напряму; не проводить склад. Доказ: `ai_assistant/views.py:548–554`; `boss_project/demo_middleware.py:11–13`; `demo_settings.py:18`.
- **AI-create-counterparty**: HTTP LLM POST блокує LocalDemoGuard (порожній ANTHROPIC_API_KEY); service callable з Python. Довідниковий writer; не створює транзакції. Доказ: `ai_assistant/views.py:498–502`; `boss_project/demo_middleware.py:11–13`; `demo_settings.py:18`.
- **AI-delete-counterparty**: HTTP LLM POST блокує LocalDemoGuard (порожній ANTHROPIC_API_KEY); service callable з Python. PROTECT ERP може відхилити частину delete; історична атрибуція без нього змінюється. Доказ: `ai_assistant/views.py:515–520`; `boss_project/demo_middleware.py:11–13`; `demo_settings.py:18`.
- **AI-create-employee**: HTTP LLM POST блокує LocalDemoGuard (порожній ANTHROPIC_API_KEY); service callable з Python. Payroll ще не створюється; audit може не збігтися при помилці після Employee.create. Доказ: `ai_assistant/views.py:359–372`; `boss_project/demo_middleware.py:11–13`; `demo_settings.py:18`.
- **AI-update-employee**: HTTP LLM POST блокує LocalDemoGuard (порожній ANTHROPIC_API_KEY); service callable з Python. Змінює дані, які читатиме виплата; не створює руху прямо. Доказ: `ai_assistant/views.py:375–390`; `boss_project/demo_middleware.py:11–13`; `demo_settings.py:18`.
- **AI-delete-employee**: HTTP LLM POST блокує LocalDemoGuard (порожній ANTHROPIC_API_KEY); service callable з Python. Та сама cascade-проблема DEF-07, але цей entrypoint зараз не доступний через LLM HTTP. Доказ: `ai_assistant/views.py:393–404`; `boss_project/demo_middleware.py:11–13`; `demo_settings.py:18`.
- **AI-undo**: HTTP LLM POST блокує LocalDemoGuard (порожній ANTHROPIC_API_KEY); service callable з Python. Undo(create employee) може каскадно видалити зарплати; undo(delete) відновлює лише Employee з новим ID, Salary не відновлює. Зараз dormant. Доказ: `ai_assistant/views.py:417–495`; `boss_project/demo_middleware.py:11–13`; `demo_settings.py:18`.
- **AI-dispatcher**: HTTP LLM POST блокує LocalDemoGuard (порожній ANTHROPIC_API_KEY); service callable з Python. Мережевий tool_use_id не стає фінансовим idempotency key; обгортка не окремий writer у count. Доказ: `ai_assistant/views.py:621–656`; `boss_project/demo_middleware.py:11–13`; `demo_settings.py:18`.
- **AI-loop**: HTTP LLM POST блокує LocalDemoGuard (порожній ANTHROPIC_API_KEY); service callable з Python. Неочікувана зовнішня помилка після effect не відкотить уже записану фінансову операцію; не перевірялося з моделлю. Доказ: `ai_assistant/views.py:841–891`; `boss_project/demo_middleware.py:11–13`; `demo_settings.py:18`.
- **AI-chat**: HTTP LLM POST блокує LocalDemoGuard (порожній ANTHROPIC_API_KEY); service callable з Python. При exception видаляє user_msg, не відкочує доменні зміни; цей LLM endpoint нині блокується до виконання. Доказ: `ai_assistant/views.py:935–986`; `boss_project/demo_middleware.py:11–13`; `demo_settings.py:18`.
- **AI-chat-file**: HTTP LLM POST блокує LocalDemoGuard (порожній ANTHROPIC_API_KEY); service callable з Python. Фінансовий доступ лише через той самий legacy dispatcher; поточний POST недоступний без ключа. Доказ: `ai_assistant/views.py:1177–1278`; `boss_project/demo_middleware.py:11–13`; `demo_settings.py:18`.

### Службові команди

| ID · модуль/функція | Читає | Пише | Atomic | Lock | Proposal/confirm | Ідемпотентність | Вердикт |
|---|---|---|---|---|---|---|---|
| CLI-bos-demo · `operations/management/commands/seed_bos_demo.py:15–46` `Command.handle / doc` | Перевірка demo/порожньої БД; synthetic JSON | Invoice.amount/paid; cash snapshot; Request/Quote/Document; довідники | Так @atomic | Немає ERP mutex | Ні; seed | dataset marker; UNIQUE code | ризик |
| CLI-erp-demo · `erp/management/commands/seed_erp_demo.py:14–44` `Command.handle / act / doc` | demo/dataset; synthetic records | Document; ERP через dispatch; erp_dataset | Так @atomic | ERP частина має M | Ні; seed | dataset marker | ризик |
| CLI-workspace · `erp/management/commands/seed_bos_workspace.py:14–30` `Command.handle / act` | demo/dataset; наявна ERP synthetic база | ERP dispatch; workspace_dataset | Так @atomic | ERP частина M | Ні; seed | dataset marker | ризик |
| CLI-branches · `branches/management/commands/seed_branches.py:81–115` `Command.handle / upsert` | Branch; reset option | DELETE Branch дерево; SET_NULL Transaction.branch; upsert | Так @atomic | update_or_create має ORM row lock; немає ERP mutex | Ні; CLI | Повтор upsert по code; --reset руйнівний | ризик |

- **CLI-bos-demo**: Службовий synthetic writer, не production HTTP. Лише demo; не переписує наявний dataset. Саме тут є прямі початкові Invoice і Configuration[cash]. Не запускали. Доказ: `статичний огляд seed`.
- **CLI-erp-demo**: Demo-only command; direct Document insert поза mutex, але ERP actions всередині нього. Не production write endpoint; не запускали. Доказ: `статичний огляд seed`.
- **CLI-workspace**: Demo-only service caller dispatch без proposal. Не запускали. Доказ: `статичний огляд seed`.
- **CLI-branches**: На відміну від інших seeds, немає BOS_DATA_MODE guard. --reset може змінити історичну атрибуцію; не запускали. До production package це окремий guard/command-контракт A05/A09, не нове фактично відтворене розходження грошей. Доказ: `branches/management/commands/seed_branches.py:81–91`.

## Що включено в охоплення, але не є окремим фінансовим проведенням

- `operations.Configuration[cash]` має лише synthetic seed writer; `settings_update` жорстко записує `organization`. Немає runtime API редагування cash balance у цьому checkout.
- `operations.Invoice` записується у `erp.dispatch[invoice/payment]` та synthetic seed. Окремий Invoice CRUD/admin не зареєстрований. `InvoiceLink`, `Movement`, `Lot`, `Reservation`, інші ERP моделі також не мають стандартного admin/serializer обходу.
- `BranchSerializer` використовується для дерева GET; write-route для нього немає. Branch змінюється через admin/seed, що перелічено.
- `Counterparty.with_totals`, finance serializers get_balance, `erp.queries`, `operations.summary`, exports/search/context читають суми, але не зберігають баланс. Проблеми видимості полів або змішування валют у read-проєкції — окрема A04/предметна перевірка, не writer у цій таблиці.
- Task CRUD, task admin, `operations.execute[create_task/update_task]`, legacy task handlers, ChatMessage/ChatFile/ClaudeUsageLog та їх admin не змінюють Lot/Movement/Invoice/Salary/Transaction. EmployeeChangeLog включений у legacy undo, де справді є payroll cascade. Видалення/редагування іншої історії потребує загальної A05/A04 політики, але не додано до поточного грошового count.
- `scripts/start_local.py` мігрує БД і викликає demo seeds; backup/API читання не є додатковою доменною проводкою. `scripts/check_*`, `evaluate_scenarios`, `export_erp_demo` використовують ізольовані БД для перевірок/експорту; їх writes — fixtures, а не production UI. Міграції — окрема A07, не прихований API endpoint.

## Причини, оцінки та конкретне розширення A05

Причини різні: **stale ORM усередині однієї операції** (DEF-01); **перевірка paid до atomic + відсутнє обов’язкове джерело** (DEF-02); **запис сутностей в обхід доменного сервісу** (DEF-03/DEF-04/DEF-08/DEF-09); **мутабельна фінансова історія та CASCADE/SET_NULL** (DEF-05–DEF-07/DEF-10–DEF-12). Саме лише додавання `atomic` або приховування кнопок не усуває ці класи.

A05 було **3–5**, уточнення — **6–10 людино-днів** (приріст **3–5**), без повторного рахунку A01/A02/A03/A04/A06/A07. Це планова оцінка реалізації й цільових перевірок, не обіцянка строку.

| Частина A05 | Людино-дні | Межі |
|---|---:|---|
| Фінансові serializer/API команди: поля нарахування й проводки, create/update та replay; DEF-03/DEF-04 | 1.5–2.5 | Єдина доменна перевірка й адаптери; базовий mark_paid race не включений |
| Збереження історії і джерела при API видаленні; DEF-05/DEF-06/DEF-07 | 1–1.5 | Контрольоване архівування/відмова з узгодженим бізнесовим результатом; не виправлення історичної БД |
| Admin save/delete/single/bulk на тих самих командах; DEF-08–DEF-12 | 1–2 | Власна adapter-поверхня admin, без повторної реалізації фінансової логіки |
| Решта CRUD/document/RFQ writer adapters і legacy AI до того самого write-контракту | 1–2 | Зберегти поточний режим LLM; не запускати платну модель; без RFQ→PO workflow B01 |
| Цільові справжні DRF/admin перевірки всіх writer сімейств і повторів; звірка inventory | 1.5–2 | Тестування результатів адаптерів; не рольова матриця A04, не PostgreSQL contention A06, не DB-migration A07 |

Окремо: A01/A02 зберігають прийняті оцінки 1–2 дні кожна. Пропущена currency у тому самому `mark_paid` потребує орієнтовно **0,25–0,5 дня в A02** на коректну передачу валюти й перевірки EUR/USD/UAH; це не A05 і не новий writer. Нормальна передумова «працівник/сума/валюта/період/джерело незмінні після проведення» має перевірятися і перед create, і перед update/delete.

Не додаються до A05 повторно: User↔Employee (A03), ролі й видимість усіх полів/маршрутів (A04), порядок mutex до fingerprint і реальні PostgreSQL паралельні прогони (A06), UNIQUE/CHECK/довжини/Decimal/міграції (A07), workflow RFQ→PO (B01) і повноцінні повернення/корекції (B03). Прийнятий дефект `code31` при `Invoice.max_length30` лишається в A07; це вже доведена розбіжність контракту типів, але не нове місце RMW корупції у консервативному лічильнику 12. Брак цих майбутніх перевірок не перекласифіковано в поточні дефекти і не сховано.

**Конкретне питання за 8.6:** погодити розширення A05 з 3–5 до 6–10 людино-днів: єдиний command для фінансових/складських/інженерних writes, адаптери для DRF/admin/доступних імпортів і dormant AI, обов’язкове стабільне джерело виплати, збереження історії при update/delete і реальні перевірки всіх цих entrypoints. Після погодження повернутися до A01→A02 та наступних кроків майстер-промпта; жодні знайдені додаткові дефекти не виправляти в рамках самої 0.1. Альтернатива — залишити A05 непогодженою й роботу заблокованою: критерій `verify` за незмінним списком без цих шляхів не прийняти.

Ці знахідки не доводять помилковості Django/поточного frontend або окремої інсталяції на компанію. Вони змінюють обсяг дисципліни запису, а не прийняту архітектуру. Звірка накопичених клієнтських грошей 0.5 ще не виконувалася; жодного рішення про виправлення історичних рядків не приймалося.


Ідентифікатори `DEF-01…DEF-12` позначають дефектні місця цієї інвентаризації й не є ID задач D01…D12 плану. Незалежний повтор root: `evidence/INVENTORY/ROOT_RUN.json`; його повний результат: `evidence/INVENTORY/DETAILS.json`.


## Після замороження · спостереження без зміни лічильника

- **UI-FIN-CURRENCY (читання коду, 11.09.2026):** старі Bank/Salaries підсумки додають суми різних currency й підписують однією валютою; це не новий шлях запису і не розбіжність перевіреної робочої БД. Відображення валюти рядка Salary уточнено в A05, але групування підсумків і форми валют ще потребують окремої числової/браузерної регресії в A11. Оцінка 0,5–1 людино-день у роботі з інтерфейсом; не включено до12канонічних місць і не видано за завершене виправлення. Умова закриття: синтетичні EUR/USD/UAH не змішуються без явного курсу, архівні проведення залишаються в історичних сумах.

## A04 · фінансовий format alias

Обхід усіх маршрутів відтворив 500 на POST `/api/salaries/{id}/pay.json` та варіанті зі slash: `SalaryViewSet.pay` не приймав DRF параметр `format`. Це дефект адаптера існуючого writer, без нової команди та без грошової розбіжності. Оцінка 0,1–0,25 людино-дня; у A04 додано `format=None`, спільна A02 виплата незмінна. Доказ red: `evidence/A04/gate-before.json`, обидва `allowed_drf_write` зі статусом500. Frozen85/12 та історичні результати не переписуються.


## Поза замороженим інвентарем · D03-F04

12.09.2026 під час перевірки інструкції встановлення знайдено прогалину першого входу: немає підтриманого операторського CLI, який завантажує перевірену конфігурацію конкретної приватної установки для `createsuperuser` / `link_bos_user`. Вхід і рольові команди в коді є; їхній готовий bootstrap для оператора не прийнятий. Це не новий шлях грошей/складу і не зміна бази 85 шляхів / 12 дефектних місць.

Потрібний окремий обсяг після блоку 3: обмежена операторська команда через наявні ownership/config/lock helpers, інтерактивний пароль без запису в журнали, перевірки власного нового синтетичного target і відмов. Попередня оцінка: 0,5–1,5 людино-дня; це не дата релізу. До реалізації серверна інструкція прямо називає bootstrap відкритим. Доказ: [D03_OPERATOR_BOOTSTRAP_UA.md](../evidence/D03/D03_OPERATOR_BOOTSTRAP_UA.md). Історичні дані для цієї перевірки не відкривалися й не змінювалися.
