# C01 · контракт доручень, історії й архіву

12.09.2026. Консолідовано C01_READY_PLAN, незалежний C01_PLAN_REVIEW та рішення root. **Лише контракт майбутньої реалізації: код, БД, міграції, браузер і тести цим підетапом не запускалися/не змінювалися.** Git HEAD при початковому читанні — `c71e601e4681d8b7bb08cd08669f2e204f30ff4d`; canonical B02 уже інтегровано, full verify №22 завершено на source SHA `dbff81af9070a059c48f91ae6bbbedd58c7448dc766469112bef120e307c73a0`. Це більше не окремий backend candidate. Локальна перевірка не означає загального приймання; черга B02 → B03 → C01 → C03 збережена.

## 1. Межа та виправлення рішення про видалення

Усі зміни Task проходять один proposal → confirm writer, включно з title/category/priority. Нові відповідальний Employee FK, SalesOrder FK, result та archived_at додаються без backfill і без перейменування історичних полів. Task result — зафіксований результат відповідального, не автоматичний доказ відвантаження/оплати. C02/LLM, сповіщення, банківські команди, payroll, generic source registry не входять у C01.

**Root змінив попередню пропозицію повної заборони видалення:** функція прибрати задачу з робочого списку зберігається як погоджуване архівування; є окремий архів і відновлення. Raw hard DELETE лишається `approval_required`, але кнопка не зникає й робота користувача не блокується. Архівування не означає done/cancelled і не стирає status/result/assignee/джерела/історію.

## 2. Additive модель Task

| Поле | Storage | Правило |
|---|---|---|
| assignee | Наявний CharField100, без зміни | Історичний рядок. Міграція/перепризначення/Employee rename його не переписують. Нове доручення зберігає тут `''`. |
| assignee_employee | Новий nullable FK Employee, PROTECT | Legacy NULL. Новий create потребує явного активного Employee ID. Дві однакові особи за ПІБ не зливаються. |
| sales_order | Новий nullable FK SalesOrder, PROTECT | Legacy NULL. Лише явне order_id та чинний доступ до всього order/source chain. |
| result | Новий nullable TextField(max_length=2000) | **Legacy NULL**, жодного вигаданого результату. Новий create явно ставить `''`. Read зберігає nullable стан, UI може показати fallback; update result=null заборонено. |
| archived_at | Новий nullable DateTimeField, indexed | Legacy NULL. Ставиться/скидається лише update_task archive/restore, timestamp серверний. Не приймається з JSON. |

Старі title/status/priority/deadline/category/branch/created_at/ID не змінюються міграцією. Task manager за замовчуванням **не ховає** archived rows від FK/history; робочі списки застосовують явний active filter. Це той самий принцип збереження історії, що Employee archive, без автоматичного виклику непогодженого DELETE writer.

Read projection додає `assignee_id,assignee_name,order_id,order_code,result,result_recorded,archived_at,archived,is_overdue`. `assignee_id` — alias FK, не старого CharField. `assignee_name` — поточне Employee.full_name або legacy assignee при NULL; `result_recorded` означає наявність змістовного тексту, не доведеність факту. Початковий `assignee` і persisted `status` віддаються окремо без підміни.

Нові migration поля залишають legacy rows NULL, включно з result/archived_at. Перед змінами таблиці зафіксувати original rows та sequence high-water; використати чинний sequence-preserving helper. Reverse відмовляє **до першого DDL**, якщо існує non-null assignee_employee/sales_order/archived_at або непорожній result. Старі all-NULL/порожні нові поля допускають empty reverse зі збереженням high-water; жодного data repair. A07 transfer/schema і A10 cleanrestore враховують нові колонки, а не повторюють старий proof без них.

## 3. Два строгі command payloads

Зберегти `create_task` та `update_task`, чинні `/api/operations/preview/` і `/confirm/`. Не вводити change_task або raw auto-confirm adapter. Невідомі/повторні JSON ключі, bool замість ID, floating ID, actor/branch/diff/receipt поля відхиляються. Existing strict JSON/30000-byte limit збережений. Усі права беруться з актуального actor, не з payload.

### Create

Обов’язково: `action='create_task',title,assignee_id,deadline`. Optional: `category,priority,order_id,request_code`.

- title: trimmed3–200, Unicode без NUL/surrogate;
- assignee_id: integer>0, явний існуючий активний Employee; Employee без User допускається як виконавець;
- deadline: строгий календарний `YYYY-MM-DD`, не раніше server `as_of`;
- category: Text≤50; default «Закупівлі», якщо request_code, інакше «Загальне»; explicit `''` зберігається;
- priority: high/medium/low/null, default medium; для сумісності `''` і `'none'` нормалізуються в null **до** fingerprint та показуються як null;
- order_id: absent/null означає без SalesOrder; positive ID — явна прив’язка;
- request_code: optional непорожній чинний доступний ProcurementRequest.code, зберігається у source history. Вигаданий/прихований code відхиляється;
- початкові statusactive, result='', archived_atNULL; ці поля не приймаються як довільний create input. Branch виводиться з обраного Employee. Старе assignee=''.

### Update

Обов’язково: `action='update_task',task_id,reason`. Окрім них має бути принаймні одне заявлене поле зміни: `title,category,priority,assignee_id,deadline,order_id,status,result,archived`.

Reason: trimmed3–1000 для **кожного** update, включно з metadata, archive і restore. Omitted поля unchanged; explicit null має правила нижче. Title/category/priority ті самі типи, що create. Перед mutation береться свіжий Task, а не ModelSerializer edited instance.

| Поле / дія | Точна семантика |
|---|---|
| assignee_id=null | Відмова. Legacy NULL не виправляється від зміни title. Нове явне призначення — існуючий активний Employee; записати FK, старий assignee не змінювати. |
| deadline=null | Відмова. Legacy deadlineNULL може лишитися без змін. Явна дата для існуючої Task може бути в минулому: reason та overdue diff обов’язкові. |
| order_id=null | Явне відв’язування поточного order з reason/history; історичний source scope залишається. Request code не переприв’язується update payload у v1. |
| result=null | Відмова. Text≤2000, буквальні newlines/пробіли зберігаються; змістовність перевіряється trimmed length≥3, без довільного обрізання. `''` допустимий до done, якщо це явна зміна. |
| status | Нові значення active/process/done. `overdue` — похідна ознака, не новий persisted transition. Старий overdue лишається до явної зміни, міграція його не переписує. |
| Новий перехід у done | Потрібні explicit збережений assignee_employee FK і result≥3. Під «explicit» мається на увазі наявний перевірений FK або новий assignee_id цього update, не збіг legacy name. Result в input обов’язковий для нової completion, щоб після reopen не повторити старий текст мовчки. |
| Legacy done з NULL/порожнім result | Дозволено читати, архівувати/відновлювати й змінювати metadata без вигаданого result/FK. No-op statusdone не означає нову completion. Якщо змінюється result — діють нові strict FK/result правила. |
| Done→done result correction | Reason + явний FK + змістовний новий result; append-only diff. Очищення result на done відхиляється. |
| Reopen done→active/process | Зберігає попередній result. UI називає його попереднім результатом; лише наступна explicit completion з input result означає нове завершення. |
| Priority при новій completion | Якщо priority omitted, стає null і це видно в server diff. Явний priority не змінюється приховано. Reopen автоматично не відновлює старий priority. |
| Branch при reassignment | Existing Task.branch лишається історичним, не переноситься між філіями неявно. Новий selected Employee.branch впливає тільки на створення. |
| Уже призначений archived Employee | Історичний FK лишається. Нове призначення archived заборонено; metadata/archive не потребують вигаданого нового працівника. Сам факт пізнішої архівації не стирає історичного виконавця або джерело результату. Current actor перевіряється чинними правилами. |

### Archive та restore

`update_task` з `archived:true|false` є **окремим update**: body містить тільки action/task_id/reason/archived. Змішування з title/status/result/assignee/deadline/order/priority/category відхиляється, щоб archive не приховував іншу зміну.

- archivedtrue: current archived_atNULL → серверний timestamp; усі інші Task поля незмінні;
- archivedfalse: current non-null → NULL; усі інші поля незмінні, включно зі старим deadline/status/result;
- already archivedtrue / already activefalse → no_change, без нового timestamp/audit/proposal;
- архівну Task не редагують, доки її явно не відновлено; GET/detail/history/restore доступні за чинною Policy;
- відновлення старого past deadline відразу повертає overdue у робочих показниках; це не зміна самого deadline;
- нова архівація після restore створює нову audited дату, старі archive/restore події незмінні.

No-op звичайного update означає, що всі **заявлені** нормалізовані поля вже рівні поточним і немає побічної completion зміни priority. Відсутність будь-якого заявленого поля — validation422, а не no_change.

## 4. Preview, commit та атомарний writer

Новий `tasks/commands.py` — вузькі validate/preview/apply helpers, викликані чинним operations service. Немає другого writable API. Manager/CEO з доступною Task можуть керувати нею за нинішньою політикою; **не вводиться** нове непогоджене правило «бачити/редагувати тільки власні задачі». Observer без write. `assignee` не є actor: AuditEvent завжди фіксує справжнього автора зміни.

Lock order: outer atomic → чинний ERP write mutex **до предметних читань** → fresh Task (для update) → обрані Employee за PK asc із evaluated `select_for_update` → fresh archive/activity/branch/source checks → fingerprint. SQLite отримує реальний write lock через ERP mutex; PostgreSQL row locks потрібні для конкурентних Employee update/archive. Не читати та не приймати assignment за об’єктом до lock. Actor/role/permissions/source checks повторюються при confirm і receipt replay.

Task fingerprint включає payload, усі захищені/відображені current Task поля, current+historical source references, обраний Employee ID/full_name/archived_at/branch, фактичні order/request/document fields і dataset.as_of. Навіть metadata writer інвалідовує старе погодження. Сумісність lock order з Employee archive/identity update перевіряється реально; сам source review не є PostgreSQL proof.

Preview200 для зміни:

```json
{"id":"UUID","payload":{"action":"update_task","task_id":123,"archived":true,"reason":"Перенесено до архіву за рішенням відповідального"},"expires_at":"UTC ISO datetime","effect":{"entity":"task","task_id":123,"operation":"archive"},"impact":[{"kind":"tasks","id":123,"field":"archived","label":"В архіві","before":false,"after":true}]}
```

Нове create effect.task_id=null; майбутній rollback PK не видається за committed. Impact від сервера, сумісний із `ImpactTable`: kind/id/field/label/before/after, optional code=title. Employee/order значення в diff включають verified ID та тодішнє дозволене ім’я/code. Архівування preview показує false→true; точний timestamp призначається лише при confirm, не обіцяється час preview.

No-op200:

```json
{"state":"no_change","id":null,"payload":{"action":"update_task","task_id":123,"archived":false,"reason":"Перевірка поточного стану"},"expires_at":null,"effect":{"entity":"task","task_id":123,"note":"Зміни не потрібні."},"impact":[]}
```

No-op не створює ActionProposal/Task/AuditEvent. Технічна mutex revision у rollback preview не є бізнес-зміною. Confirm чинний: `POST /api/operations/confirm/` з `{proposal_id:UUID,confirmed:true}`. Task change + FK/result/archived_at + **один** AuditEvent + final receipt в одній atomic transaction. Receipt зберігає старі keys `state=succeeded,task_id,audit_id` та додає `impact`; повтор того самого ID за тих самих прав literal-equal. Немає нового ERP Event для Task і немає грошових/складських ефектів.

AuditEvent payload schema=`bos.task-change.v1`, action create_task/update_task, transition create/update/archive/restore/reopen/complete/result_correction; actor_id/role/display snapshot, reason (create — явний server marker створення), as_of, structured before/after та source references. State snapshots містять title, legacy assignee, assignee_id/name, deadline, order_id/code, request_code/history refs, status, priority, category, branch_id, result, archived_at. Старі AuditEvent/TaskChangeLog не переробляються. Archive й restore кожний дають нову update_task подію, не сторонній дублюючий task.archive аудит через другий writer.

Відмова після Task.save, наприклад реальний SQL failure AuditEvent, відкочує Task та proposal running marker. Same proposal retry після усунення тимчасової помилки виконує один effect. Різні proposals з одного стану — переможець та stale409; no last-write-wins. Відсутній результат confirm не вважається невиконанням.

## 5. Закрити raw writers, зберегти читання й функції

- TaskViewSet raw POST/PUT/PATCH/DELETE, включно з `.json`, для authenticated manager/CEO повертає403 `{code:'approval_required',error:'Зміни доручень потребують попереднього перегляду та погодження.'}`. Observer також403 за policy; unauthenticated401. Немає auto-preview+confirm усередині старого route.
- TaskSerializer read-only для захищених writes; не приймає старий assignee як новий actor/FK. Усі зміни title/category/priority теж через command.
- Technical TaskAdmin read-only: GET/list/search/detail лишаються за native permissions; add/change/delete/bulk-delete не виконують Task mutations. Business-role admin gate збережений.
- Hard DELETE не стирає Task, FK/result чи AuditEvent.task через SET_NULL. UI кнопка стає «Архівувати» і відкриває погоджуваний reason; archive view має «Відновити». Видалення зі списку тепер має історію замість втрати даних.
- Закриті legacy AI POST routes залишають503; helpers `_create_task/_update_task/_delete_task/_undo_last_change` не стають C01 adapters. Не заявляти, що прямий ORM зовні застосунку «заборонений БД»; підтверджується фактичний HTTP/admin/command scope.
- Seed тільки створює нові owned synthetic rows; повтор seed не backfill старі FK/result/archive. Legacy fixture rows можуть бути задані test setup для перевірки міграції, не production repair.

## 6. Source visibility та read API

`Policy.tasks()` повертає всі **доступні** Task, включно з archived для detail/restore/history. Active list/KPI filter окремий. Task недоступна, якщо недоступне хоча б одне **поточне або історичне** SalesOrder/request source. Джерела беруться з current sales_order + всіх фактичних AuditEvent source refs, не лише останніх100 подій. Це запобігає витоку старого Task.result після relink на відкритий order. Прихований source не стає доступним через archive/restore, rename чи іншу роль.

New audit використовує явні `order_id,task_id,request_code,assignee_id`, не generic `{kind,id}`. Legacy audit request_code перевіряється існуючим механізмом; не вигадувати пропущений source заднім числом. Arbitrary текст не вважається автоматично класифікованим: scope гарантується за заявленими typed джерелами, а не «розумінням» вільного тексту.

| Endpoint | Read contract |
|---|---|
| GET `/api/tasks/` | Default archivedfalse; зберегти наявну list response форму та filter/search/order. Додаються `archived=true|false` (false default), `assignee_id=ID`, `overdue=true|false`; malformed values400. |
| GET `/api/tasks/?archived=true` | Окремий архів лише доступних Task. Те саме read projection/search/order, без сирих фінансових полів інших джерел. |
| GET `/api/tasks/<id>/` | Доступний archived або active detail; current source scope,404 для недоступного. `archived`/`archived_at` пояснюють стан, не ховають history. |
| GET `/api/tasks/<id>/history/?limit=20&cursor=…` | **Новий** scoped history, опис нижче. Архівна Task допустима. |
| GET `/api/operations/task-proposals/<uuid:proposal_id>/` | **Новий** read-only recovery status виключно create_task/update_task, опис §7. Не існуючий B02 batch route. |

Search знаходить current FK full_name і legacy fallback; full_name200 не обрізається до assignee100. Старий exact `status=overdue` лишається фільтром persisted legacy state; новий `overdue=true` та UI використовують похідне правило. Format suffix права такі самі. Default operations export/summary/home дають active tasks; archived записи доступні через явний archive list/detail/history, не губляться в storage.

History: limit integer1–50, default20; keyset за `(created_at,id)` descending, стабільний cutoff першої сторінки, щоб нові події не дублювали старі між сторінками. Cursor підписаний server signing, прив’язаний до task_id/actor/access_revision/cutoff/last tuple; це не дозвіл, Policy перевіряється кожного разу. Невалідний cursor400; чужий/недоступний Task404.

Відповідь `{task_id,items,next_cursor}`. Item нового schema містить `{id,action,transition,created_at,actor,reason,before,after,changes,legacy:false}` лише з allowlist Task fields. Actor — записаний ID/role/display, без email/phone/salary. Manager бачить дозволений Task diff, не весь arbitrary operations AuditEvent payload. Старі записи без structured schema повертають дозволені metadata, `legacy:true`, пояснення «структурований diff раніше не збережено»; before/after не вигадуються. Всі historic order/request refs перевіряються до видачі будь-якого text/result.

## 7. Pending identity та точне read-only recovery

До першого confirm UI зберігає pending proposal_id, action/task context і verified user ID у сховищі поточної вкладки, яке переживає демонтування ControlledTask. Зберігання не включає result/джерельний приватний текст. Якщо використовується sessionStorage, це межа вкладки, не обіцянка відновлення закритої вкладки. Failure storage handling відбувається **до** відправлення confirm, не після.

Network error/5xx/timeout після confirm → невідомий результат; не очищати ID, не створювати новий proposal і не скидати pending за expiry чи довільним retry limit. Close/reopen зберігає цей ID. Після фактичного receipt очистити pending саме цього наміру; помилка refetch не означає rollback і не створює нову дію.

**Мінімальне нове wire рішення:** GET `/api/operations/task-proposals/<uuid:proposal_id>/`, owner-only (`request.user.pk == proposal.user_id`) і exact current role==proposal.role, action лише create_task/update_task. Поточна Task/source Policy перевіряється. Missing/foreign/інший action404; revoked role403. GET ніколи не виконує команду, не продовжує expiry й не переносить proposal між sessions.

Success payload:

```json
{"proposal_id":"UUID","action":"update_task","state":"succeeded","expires_at":"UTC ISO datetime","same_session":true,"receipt":{"state":"succeeded","task_id":123,"audit_id":"UUID","impact":[]}}
```

Інші стани: `pending` (no committed receipt, ще не expired), `expired` (no committed receipt, час минув), `unknown` (незавершений/неочікуваний persisted marker). Receipt=null для них. Позитивний succeeded віддає canonical receipt у current projection; навіть після expiry це успіх уже виконаної операції.

**Відсутність receipt у read-only GET не доводить невиконання паралельного confirm:** він може бути ще в atomic transaction. Тому pending/expired/unknown GET **не дозволяють** UI автоматично створити новий намір або видалити pending. Остаточна перевірка в тій самій session — повтор POST confirm **з тим самим ID**, який бере mutex і повертає committed receipt або структурований terminal409 після перевірки відсутності receipt під lock. Розрізняти error codes `proposal_stale|proposal_expired` (під lock і без застосування) та generic `write_conflict|temporary_failure` (повторити той самий ID). Не трактувати кожний409 як дозвіл забути намір.

GET допускає owner/current-role read після нової session, щоб знайти факт успіху, але `same_session=false` **не** дозволяє виконати old proposal: чинна confirm session boundary зберігається. Якщо receipt ще не видно й початкової session немає, автоматичного replay під іншим ID немає; UI пояснює, що треба відновити/перевірити попередній результат. Це чесна межа recovery v1, не прихований B02 batch/adopt route.

No-op preview не породжує pending. Definitive stale/expired confirm без effect залишає draft для **явного** нового preview. Пізня read/preview відповідь після Escape/зміни task не відкриває старий діалог: синхронний alive token/cancel перед onClose; parent openers перевіряють його перед setState.

## 8. Єдина простроченість і архівні фільтри

Новий `tasks/queries.py` (або еквівалент) має один as_of та спільні Python/ORM-compatible predicates:

`is_overdue = archived_at is None AND status!='done' AND deadline!=None AND deadline<as_of`.

Для поточного active queryset segments взаємовиключні: done; overdue; process без overdue; решта active/legacy-other без overdue. Сума4 сегментів=active total. Archived excluded з denominator/KPI/alerts; окремий archive count можливий лише явно. Legacy persisted overdue з майбутньою датою не створює неправдиву простроченість, його persisted статус лишається доступний як історичний.

Helper обов’язково використовується в Task list/filter, Task projection, `operations.service.summary`, operations export context, `erp.experience.home`, BoSHome/dashboard/Tasks, `branches.views._task_stats`, `_scoped_operational`, helicopter `real_overdue`, branch-health/alerts. Скрізь той самий policy-scoped набір і branch filter. Frontend `refetchTasks` більше не переписує status на overdue.

Нуль фактичних прострочень/активних задач — реальний нуль. Архівування останніх задач не запускає demo fallback, що повертає вигадані борги по задачах. Навчальні приклади дозволені тільки як явно позначений synthetic dataset, не підміна отриманого current query result. Deadline change/archive/restore мусять однаково змінювати всі read consumers.

## 9. UI entry points і контракт адаптації старих тестів

Один розширений **ControlledTask** використовується з Tasks create/edit/status/priority/archive/restore, Topbar «+ Нове доручення», Procurement, OperationsAssistant та JSON action importer. Зберегти існуючий екран/пошук/фільтри. Employee selector показує full_name+role/branch/ID для однакових імен; передає ID. Archive tab показує історію/restore, не відновлює status за замовчуванням. UI source/result/diff користуються серверними projections; жодного виконання побічних грошей/складу.

Потрібні **пояснені адаптації**, а не видалення old tests. Причина: прийнятий C01 змінює дозволений спосіб write, raw DELETE замінюється archive/restore без втрати функції. Кількість старих сценаріїв не зменшується, зміст кожного зберігається новим позитивним маршрутом плюс негативна bypass перевірка.

| Старий файл / сценарій | Адаптація зі збереженням мети |
|---|---|
| `tasks/tests.py::test_create_task` | Create preview/confirm з explicit assignee/deadline; перевірити1 Task, FK/title/priority та1 audit. Додати raw POST approval_required/no row. |
| `test_title_too_short_rejected`, `test_deadline_in_past_rejected_for_new_task` | Ті самі invalid title/date, але валідні інші mandatory fields через preview;422 і нуль proposals/domain writes. Raw rejection не підміняє field validation. |
| `test_deadline_in_past_allowed_for_update` | Legacy fixture + update reason → preview/confirm; старий минулий deadline законно збережений, overdue diff і audit доведені. |
| `test_priority_none_normalized` | Той самий none→null зміст через create command з explicit assignee/deadline; жодної втрати підтримуваного «без пріоритету». |
| `test_filter_and_search` | Legacy fixtures залишаються; додати FK name+однакові ПІБ, archive default/explicit filter і derived overdue. Не замінити старі assertions тільки новими. |
| `test_delete_task` | Замість фізичного знищення: raw DELETE denied; archive preview/confirm прибирає з default list, Task row/history лишаються; archive view і restore повертають ті самі ID/поля. Це збережена користувацька функція з історією. |
| `scripts/check_original.py` quick task/edit/empty title/search | Quick create тепер explicit Employee ID+deadline → proposal/confirm; done має explicit result/reason; збереження/read/search ті самі. Додати raw bypass refusal, не прибирати маршрут з обходу. |
| `scripts/check_operations.py` create/replay/stale/update | Create вже controlled: зберегти його, legacy seeds8/IDs/as_of не переробляти. Done payload додає assignee_id для legacy NULL, result/reason; stale test досі міняє Task між preview/confirm. Count1 AuditEvent на зміну та same receipt збережені. |
| `scripts/access_fixtures.py`, `access_routes.json`, `check_access.py` | Усі фактичні old API/admin/.json маршрути залишити. Positive raw tasks expectations замінити explicit approval_required; позитивне керування перевірити через task proposals. Додати history/status routes й archive/restore field canaries. Не виключати route з inventory. |
| Task proposal tests в operations/identity/auth suites | Переглянути exact references до create_task/update_task, доповнити mandatory new completion fields, не змінювати очікування current-role/session/source/replay. Будь-яка зміна fixture має evidence explanation. |
| `scripts/check_workspace.py`, branch/HR tests | Без нових credits/archive старі суми та сценарії незмінні. Додати archive/overdue/restore consumers; якщо fixture persisted overdue без past date очікував динамічний overdue, явно розділити legacy exact filter і прийнятий derived KPI oracle. |
| Migration/transfer/restore/schema tests | Додати mixed legacyNULL/newFK/result/archive records та lossy reverse guard; старі PK/bytes/high-water assertions лишаються. Не оголошувати попередній schema hash proof нового schema. |

Окремо evidence/C01/TEST_ADAPTATIONS_UA.md: старе твердження → прийнята причина зміни → нове позитивне/негативне твердження → фактичний red/green. Заморожені11 gates, старі фінансові/складські тести й baseline action inventory не послаблюються. C01 не додає ERP action, але Task concurrency/access coverage розширюється явними required methods/IDs, а не dynamic discovery.

## 10. Мінімальні meaningful acceptance checks

1. Mixed legacyNULL/однакові ПІБ/довге ім’я200: migration не backfill, explicit FK/date/result/архів зберігаються після transfer/restore; заповнений reverse відмовляє доDDL.
2. Actual create → reassignment/date/priority → done+result → result correction → reopen → нова completion: окремі before/after actors/IDs/імена; старі events незмінні після Employee rename. New done безFK/result, unknown fields, invalidnull відмовляють.
3. Archive/restore: row та усі status/result/FK/date/branch/history незмінні; default list/KPI/alerts виключає, archive view/detail/history показує; restore old deadline повертає overdue. Replay/no-op не створюють нову дату/audit.
4. Два proposals одного стану, archive проти update/restore, Employee archive/reassign race, revoked role/source: контрольований результат або conflict; жодної часткової зміни. SQLite/PG окремо.
5. Реальний SQL trigger failure на AuditEvent після Task mutation → повний rollback; same-ID retry один Task/audit. Lost HTTP response після commit → replay literal receipt,0 extra rows.
6. Proposed status GET: owner/current-role/scope gates, іншій action404, succeeded afterexpiry; pending/expired не запускає новий writer. GET під паралельним незакоміченим confirm не видається доказом відмови; same-ID confirm — authority. Same_session=false не обходить session bound confirm.
7. Hidden historical order після relink, Task.result canary, history старше100 global events, pagination/new concurrent events, archive/history/export/assistant/cache — немає leak; manager має дозволений structured diff.
8. Один deterministic as_of та policy/branch Task set: list/home/summary/branch/helicopter збігаються, mutually exclusive segments, real zero без demo fallback. Archived task не повертається до alerts без restore.
9. Всі Tasks/Topbar/Procurement/assistant entry points реально виконують preview/confirm; raw REST/admin/bulk/legacy AI не обходять. Existing функції create/edit/remove-from-list/restore збережені.
10. Actual browser390/768/1440, zoom200%, keyboard/Escape, довгі names/result, подвійне натискання, close/reopen/late reads/refetchfailure. Source/build check не приймає браузер; недоступність — НЕ ЗАПУЩЕНО.

Після scoped green і незалежного review root запускає full verify на frozen source, зберігає actual outputs/SHA/environment, update PROGRESS/CHANGELOG/PARAMETERS та один C01 commit. Відкриті A09/A10/A11/PG/Windows умови не приховуються. Файл не є запуском роботи або прийманням C01.
