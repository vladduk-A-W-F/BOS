# A10 · скінченний план резервування, відновлення та відкату оновлення

Дата: 12.09.2026. **Статус: read-only підготовка; реалізацію і тести A10 НЕ ЗАПУЩЕНО.** План не закриває критерії 7 або 9. Початок реалізації — після фіксації root результатів A09 та SHA canonical пакета.

## Підстава й точний результат

Прочитано master `upload/BoS_MASTER_PROMPT (1).md` v2.1, таблицю `output/BoS_Plan_Pack_UA/BoS_Plan_UA.md`, `docs/PROGRESS_UA.md`, чинні A07/A08 helpers і A09 installer/lifecycle. У progress на момент читання A09 ще в роботі, A10 не розпочата; це не змінювалося цим агентом.

- Master §2.7: резервна копія розгортається в **чисту установку**, збігаються кількості, суми, версії документів і SHA файлів.
- Master §2.9 та §5: установка з даними N реально оновлюється до N+1, проходить перевірку й повертається до стану N автоматизованою командою.
- Рядок A10 первинної таблиці також вимагає виміряти час відновлення, втрату даних і затримки для явно названих даних та активних сесій. Факт існування 200 працівників не є доказом 200 паралельних сесій.
- Залишаються Django, поточний frontend, окрема установка компанії, незмінність історичних фактів. Зворотні Django migrations, повторний `seed`, ручна заміна DB, неперевірений `copytree` відкритої бази або читання старого snapshot самі по собі не є rollback A10.

Локальний обсяг першого доказу: Linux amd64 / Python 3.12 / actual SQLite / Waitress 3.0.2 / Caddy 2.11.1, ті самі обмеження loopback і явної довіри до тестового TLS, що в A09. PostgreSQL та Windows без фактичного запуску лишаються НЕ ЗАПУЩЕНО; перелік 11 критеріїв verify не змінюється.

## Що повторно використовується

| Наявний модуль / API | Використання в A10 | Межа, яку не можна приховати |
|---|---|---|
| `scripts/install_server.py`: `safe_path`, `identity`, `private_regular`, `new_file`, `InstallerRegistry`, `prepare_install` | Невкладені шляхи, exclusive creation, права 0700/0600, ownership та реєстр нової цілі | UUID/ім'я/скопійований manifest не надають права запису; completed provision не можна повторно запускати |
| `scripts/provision_runtime.py` | Той самий pinned offline runtime: `-I`, `--no-index --no-deps --only-binary=:all:`, pip check | Потрібне вузьке відокремлення підготовки code/venv/static від першої DB initialization; не копіювати resolver чи вимикати existing guards |
| `scripts/lifecycle_server.py`: `load_owned`, `instance_lock`, `serve`, `health` | Перевірка фактичної інсталяції, live HTTPS, контроль тільки власних процесів | Нині немає control IPC для maintenance; active lock дозволяє відмову, а не кероване оновлення живого процесу |
| `scripts/package_server.py`: `package`; `install_server.source_identity` | Точний code-only package, версія й manifest SHA | Manifest доводить цілісність відносно довіреного пакета, не підпис автора |
| `scripts/reconcile_data.py`: `make_snapshot`, `connect_readonly`, `analyze` | SQLite backup API, read-only звірка сум та складських інваріантів | DB snapshot окремо не створює узгоджений зріз media; потрібна зупинка всіх writers |
| `scripts/schema_preflight.py`: `inspect_schema`; `scripts/preflight_data.py`: `inspect_data` | Відомий migration state, фактична schema/type/FK/файлова перевірка | Невідома чи дрейфуюча схема відхиляється; історичні факти не ремонтуються |
| `scripts/data_transfer.py`: `validate_snapshot`, `export_snapshot`, `media_manifest`, `row_manifest`, `sequences`, `import_to_disposable` | Єдиний typed codec та oracle exact rows/ID/FK/суми/sequence/media. За потреби логічного імпорту — тільки чинний trusted factory + capability | A07 пакет не містить code/config/runtime; DB-layout після логічного імпорту може відрізнятися. Не створювати другий JSON/Decimal/UTC/BLOB codec |
| `operations/private_storage.py`: `verified_document_bytes`, `PrivateDocumentStorage`; A08 document plan | Перевірка оригіналів, declared checksum/size, квоти, прав і всіх версій, включно з archived ChatFile | Backup не запускає `apply_plan` як «ремонт». Змішані legacy BLOB/text і нові files зберігаються як є; відомий checksum не переписується |
| `fixtures/synthetic/transfer.py`: `populate`, `verify_facts`, `verify_replays` | Синтетичні дані з незалежними очікуваннями у 45 поточних таблицях, 3 валютах, архівами, receipts і FK | `populate` тільки в реально щойно створеній власній БД. Worker guard не послаблюється для довільного `bos.sqlite3`; потрібний вузький issuer для нового synthetic server bundle |
| `scripts/server_http_checks.py` та A09 `check_install.py` | Реальні auth/CSRF/roles/private download/TLS; ті самі canaries і lifecycle facts | Не видавати Django TestClient або сторонній listener за HTTP активної відновленої установки |

Native sealed SQLite snapshot буде payload повної резервної копії для того самого backend і версії. A07 typed manifest — спільна незалежна звірка, а не привід ще раз реалізувати SQL import. Чинний `import_to_disposable` лишається шляхом **окремого** логічного переносу; його не перетворювати на імпорт у наявну робочу БД.

## Передумови, яких ще немає

1. **Зафіксований A09:** accepted canonical code SHA, його actual install + TLS/lifecycle результати, доступні exact wheels/Caddy/OpenSSL. Без цього A10 runner повертає неповний результат, не бере старі журнали за proof нового SHA.
2. **Керований maintenance:** невеликий локальний control interface існуючого foreground supervisor. Дозвіл прив'язаний до installation UUID, root inode й поточного process incarnation; приватний канал та nonce, перевірка peer/ownership. Немає сигналів довільному PID з файла, захоплення чужого порту чи public management endpoint. Supervisor сам припиняє приймання нових запитів, дочікується завершення in-flight writes, зупиняє власні children й підтверджує sealed стан. Перший Linux варіант може використовувати приватний Unix socket; Windows канал перевіряється окремо.
3. **Єдиний writer fence:** один порядок maintenance/instance/registry locks без deadlock. Backup/upgrade/restore не можуть паралельно змінювати generation. ERP mutex охоплює не всі файлові й auth записи, тому його одного недостатньо. Активний unmanaged `start_server.py` не зупиняється навмання: явна відмова, поки немає trusted managed handle. Прямий сторонній SQL writer не вважається керованим; busy/active transaction або зміна source/media під час capture дають відмову.
4. **Generation authority:** A09 `InstallerRegistry.update` забороняє зміну `source`, а `load_owned` жорстко обирає `releases/<original SHA>`. Не послаблювати ці immutable поля. Додати вузький append-only запис нового покоління: parent generation hash, operation UUID, code/config/DB/media manifest, ownership identities, backup hash і результати перевірок. Окремий атомарний active pointer вибирає лише повністю прийнятий запис. Початкова інсталяція лишається початковою генерацією без переписування історії registry.
5. **Повторний запуск:** trusted launch profile має містити перевірені Caddy/TLS/CA/ports попереднього запуску; приватний ключ не копіюється в stdout чи argv payload. Команда може приймати шлях приватного launch profile. Наявний список аргументів supervisor недостатній без їх збереження або явної передачі.
6. **Новий restore target:** власний factory створює відсутній bundle й DB/media ексклюзивно, реєструє фактичні inode до використання, готує runtime потрібної версії N. Не створювати спочатку довільну latest DB, а потім непомітно перезаписувати її snapshot. Наявна installer empty DB initialization потребує лише вузького спільного staged interface; не другого інсталятора.

Це перелік мінімальних інтерфейсів майбутньої реалізації, не вже наявні гарантії. Реалізація control/generation буде окремим фактично червоним кроком після A09 record.

## Повна резервна копія й правила перемикання

Backup створює новий приватний каталог поза source/target/registry/wheelhouse. Спочатку створюється ownership receipt, останнім — COMPLETE з hash усього manifest. Якщо будь-який крок не завершений, ці байти не приймаються як backup; повтор може продовжити лише ті файли, для яких є issuer receipt та точний hash. Жодного очищення невідомих каталогів.

Обов'язковий склад: native sealed DB; повний private media manifest і байти, включно з неприв'язаними файлами та архівами; точний code package N; приватний config N; version/migration-state; exact pinned runtime inventory; static manifest; capture time і checkpoint; результати A07/A08 звірки. Code і config hash мають збігатися з активним generation receipt. Журнали runtime та IPC/PID/lock-файли не є переносною process authority. TLS key не потрапляє в публічний export; його зовнішня наявність перевіряється launch profile.

Послідовність capture: managed maintenance → завершення writers → read-only snapshot через SQLite backup API → копія media з перевіркою байтів → точна звірка source DB/media до й після → A07/A08 read-only admission → COMPLETE. WAL/SHM/journal живої БД не ігноруються. Сумісний WAL включає SQLite backup API; **sealed payload**, переданий A07, не має активних sidecars. Неперевірений hot journal, непогашений writer або відсутній fence спричиняють відмову, а не `immutable=1` на живому файлі.

Native DB у backup може мати інший фізичний SHA, ніж вихідний файл, через SQLite backup API. Окремо записуються source SHA та payload SHA. Restore повинен відтворити **точні байти payload** й ті самі logical rows/schema/sequences. Не стверджувати фізичну рівність source DB там, де перевірена логічна.

**Чиста restore:** нова фізична інсталяція отримує новий ownership UUID/root inode; не імпортує registry authority із backup. Всі бізнесові ID/User/Employee/групи/permissions/session rows/documents лишаються точними. Контрольоване remap конфігурації обмежене installation UUID і залежними від нового root шляхами; origin змінюється лише явним аргументом. Секрет і решта параметрів N беруться з приватного перевіреного backup; cookie namespace відповідає новому UUID, старий браузер повторно входить. Кожна відмінність config перелічується в приватному restore receipt; необмежений «нормалізатор» config заборонений. Це не активна копія другої компанії й не надання доступу її UUID.

**N→N+1:** N справді працює з populated DB. Після maintenance створюється checkpoint. Code N+1, окрема venv, копія DB/media й config готуються у власній новій generation; міграції застосовуються **вперед тільки до candidate DB**. Старі code/config/DB/media/venv N не змінюються. Readiness та read-only HTTP приймання candidate перевіряють actual N+1 перед атомарним перемиканням active receipt. Загальний період простою вимірюється. Це оновлення існуючої логічної компанії, тому installation UUID, секрет, User/Employee ID і права не змінюються; в config відрізняються лише generation paths, перелічені manifest.

**Rollback:** у вікні до відкриття бізнесових writes N+1 повертається active receipt N, його точні code/config/state та runtime. Перевіряються native snapshot/hash, усі row manifests, документи й справжній HTTPS N. За втрати old generation відновлення йде з sealed backup в нове owned generation, з контрольованим remap шляхів; не запускається `migrate <old target>`. Перший автоматичний rollback обмежений цим maintenance window. Якщо N+1 вже підтвердила нові бізнесові записи, команда відмовляє, зберігає актуальний стан і пояснює, що повернення старого snapshot втратить нові факти. Відмова не маскується як успішний rollback. Злиття після cutover або переписування історії не входить до цієї реалізації.

## Командний контракт, який належить реалізувати

Один операторський entrypoint — пропонований `scripts/maintenance_server.py`, одна команда на операцію. Ці команди **ще не існують**:

```sh
python scripts/maintenance_server.py backup --target /abs/company --registry /abs/registry --installation-id UUID --output /abs/new-backup --operation-id OP_UUID
python scripts/maintenance_server.py restore --backup /abs/backup --target /abs/new-company --registry /abs/registry --wheelhouse /abs/wheels --launch-profile /abs/private-launch.json --operation-id OP_UUID
python scripts/maintenance_server.py upgrade --target /abs/company --registry /abs/registry --installation-id UUID --source-root /abs/package-N1 --wheelhouse /abs/wheels --launch-profile /abs/private-launch.json --operation-id OP_UUID
python scripts/maintenance_server.py rollback --target /abs/company --registry /abs/registry --installation-id UUID --to-generation GENERATION_SHA --launch-profile /abs/private-launch.json --operation-id OP_UUID
```

Кожна команда видає JSON `operation_id/status/complete/stage/installation_id/generation/manifest_sha256/checks/timings` без секрету, текстів документів або персональних рядків. Відмова містить controlled reason та етап; приватний evidence file може містити структурні IDs/hash, але не довільні дані. Exit 0 тільки після всіх перевірок конкретної операції; incomplete/prerequisite failure — ненульові. Restore включає запуск за приватним launch profile та actual HTTPS readiness; backup керовано відновлює попередній runtime після capture. Повтор того самого OP_UUID й payload повертає підтверджений receipt без нової копії/міграції; інший payload з тим самим UUID — відмова. Успішний backup не видається за прийнятий restore.

Gate API вже заданий у `scripts/verify.py`: **`scripts/check_restore.py --output PATH`** для 7 та **`scripts/check_upgrade.py --output PATH`** для 9. Обидва acceptance runners створюють тільки власні нові fixtures; не приймають шлях клієнтської DB. Caddy/wheels беруться з тих самих явних prerequisites, що A09. Повні raw commands/exit/stdout/stderr та source/package/fixture SHA зберігаються; mock pipeline замість реальних CLI заборонений.

## Скінченна матриця: 12 груп, без необмеженого розширення

Кожний зазначений red — **заплановане очікування**, не твердження про вже виконаний тест. Спершу виконати відповідний тест на canonical A09, зберегти фактичну відмову; потім мінімальна реалізація й той самий тест. Не більше трьох повних спроб на конкретний дефект; перші журнали не перезаписувати.

| ID | Реальна перевірка / негативний випадок | Незмінний oracle |
|---|---|---|
| BK01 | Відсутні maintenance/check_restore/check_upgrade, wheels/Caddy або невідома schema | Ненульовий exit, complete=false, точна причина; жодних source writes чи заміни середовища вже встановленою venv |
| BK02 | Backup populated managed N; один справжній ERP writer і один upload починаються біля maintenance boundary | Кожен підтверджений write повністю включений у checkpoint; пізніший відхилений без DB/file побічних ефектів. DB/media одного зрізу; backup COMPLETE тільки після звірки |
| BK03 | Повний backup → нова відсутня clean installation → реальний HTTPS startup | 45 поточних таблиць, exact rows/PK/FK, EUR/USD/UAH суми, salary/intent/receipt/archive, sequence high-water, всі версії/size/SHA; код N і allowlist config remap. Після schema зміни число таблиць береться з exact descriptor, а не сліпо фіксується 45 |
| BK04 | Відновлені document original, legacy BLOB/text, archived ChatFile; CEO/manager/observer прямі HTTPS requests | Доступ/відмова ті самі; bytes download=manifest; hidden поля відсутні, raw /media закрита. Replay і наступні ID перевіряються на **окремій proof copy**, не забруднюють відновлений snapshot |
| BK05 | Окремо пошкодити DB, media, manifest, прибрати файл/COMPLETE; додати невідомий файл або конфлікт checksum/size | Уся restore відхилена до target DB writes/start; backup і сторонні дані не «ремонтуються». Controlled finding, complete=false |
| BK06 | Існуюча порожня/заповнена target; overlap target/backup/source/registry; symlink, `..`, hardlink; copied marker/root replacement; UUID компанії B | Відмова до мутації/запуску. До/після порівняти byte manifests A, B, input backup і registry. Root inode/назва самі по собі не достатні; descendants також перевіряються |
| BK07 | Два реальні maintenance процеси однієї компанії; повтор OP_UUID; той самий UUID з іншим payload | Один writer/receipt; другий deterministic busy або exact replay; ніяких двох cutover, duplicate snapshots чи втручання в активну B. Порядок locks не зависає |
| UP01 | N реально обслуговує populated fixture; CLI створює N+1 із справжньою тестовою additive migration та іншою версією | Actual migration applied, actual schema changed, HTTP показує N+1 і правильний generation SHA; старі IDs/суми/bytes unchanged. Зміна тільки version string не проходить |
| UP02 | По одному actual fault: відсутній wheel; migration викликає помилку після DDL; media copy I/O failure; candidate readiness/TLS failure | Candidate неповний і не active. Старий N доступний після контрольованого restart, його code/config/DB/media exact; усі created children завершені, чужий listener не чіпається |
| UP03 | Після успішних candidate checks у maintenance window виконати explicit rollback N+1→N | N HTTP і фактична schema/migration state, config, code, DB/media manifest збігаються з N checkpoint; в SQL/commands немає reverse migrate. Точні DB SHA порівнюються з правильним native payload/retained source, не змішуються |
| UP04 | Після відкриття writes N+1 підтвердити нову реальну складську/грошову операцію й спробувати rollback до старого checkpoint | Ненульова відмова без втрати нового запису, рухів, файлів чи receipts; поточний snapshot збережений. Це доказ межі безпечного rollback, не його успіх |
| UP05 | Реальний kill власного maintenance child після snapshot і перед active receipt; повтор recovery; втрачений/змінений ownership receipt | До COMPLETE/active commit не видно часткового покоління. Recovery продовжує тільки issuer-owned байти або відмовляє; старий N/backup/компанія B незмінні. Немає `kill(pidfile)` або cleanup невідомих файлів |

Для UP01 потрібні два immutable **синтетичні тестові** code packages: N — зафіксований A09; N+1 — його reviewed fixture variant з реальною additive migration, наприклад окремим індексом, що не переписує жоден бізнесовий факт. Це тестовий migration fixture, не вигаданий продуктовий release. Schema oracle працює під відповідним N/N+1 package й не дозволяє довільні DDL exceptions. В UP02 помилка після DDL також справжня міграція тільки в власному candidate; fault injection не підмінює migrator моками.

## Дані, вимірювання та приймання

Перша власна synthetic installation містить повний A07 fixture; A08 додає mixed/new/legacy documents і archived ChatFile, перевірені фактичним read path. Друга одночасна установка B має інші UUID/secret/DB/media та canaries. Власність обох підтверджується новим exclusive creation, а не переданим env flag. До й після небезпечних кроків зберігаються hashes immutable source package, backup та B; секрети в evidence не виводяться.

З цього самого actual прогону записати: розмір native DB/media/code; кількість файлів/версій/рядків; тривалість drain, capture, copy, validation, restore, candidate migrate і restart; час від початку maintenance до першого підтвердженого ready; останній прийнятий business operation ID до checkpoint і перший після resume. Втрата підтверджених до fence операцій повинна дорівнювати нулю. Частоту backup та максимальний допустимий RPO/RTO пілота не вигадувати.

Малий заздалегідь зафіксований інженерний вимір затримок — ті самі дані, **1 і 5 активних сесій**, по 20 read requests на сесію до maintenance та після recovery; фактичні count/errors/p50/p95/max. Він не замінює BK02 реальні writes. Це початкова виміряна межа, не погоджена потужність пілотного клієнта чи навантаження production. Пілотні SLA/дані/число користувачів залишаються окремими явно невідомими параметрами, але не зупиняють synthetic перевірки.

Порядок реалізації: (1) зафіксувати A09 → (2) BK01 red + ownership/fence interfaces → (3) backup/clean restore BK02–BK07 → (4) UP01–UP05 → (5) один повний canonical verify без регресій і незалежний review. Gate 7 зелений лише після справжнього clean install restore й HTTP; gate 9 — лише після managed live N→N+1, успішного bounded rollback та негативного post-write кейсу. Немає переходу до A11 через хибно зелений A10.

Докази майбутньої реалізації: `evidence/A10/BEFORE/`, `AFTER/`, `RESTORE.json`, `UPGRADE.json`, `ENVIRONMENT.json`, `MANIFESTS.json`, `RESULT_UA.md`, `FINAL_REVIEW_UA.md`. `docs/PROGRESS_UA.md` і `CHANGELOG_UA.md` оновлює root після конкретних виконаних кроків, а не цим планом. Тут жодний A10 результат не позначено виконаним.
