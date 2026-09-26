# Gate 4: інтеграція draft

Файли для перенесення root до `scripts/`:

- `tmp/check_access.py` — каталог, незалежний контракт прав, реальні HTTP кейси, рекурсивний oracle, runner обов’язкових тестів.
- `tmp/access_fixtures.py` — синтетичні записи, явні дозволи, справжні login/CSRF, чинні proposal, валідні CRUD/admin дані.
- `tmp/access_routes.json` — прийняті 170 definitions та точні 48 field/context test IDs. Це allowlist відомого контракту, а не автоматичне прийняття поточного handler.

Запуск із чинного verify: `python -B scripts/check_access.py`. Наявний `verify.EXTENSIONS[4]` уже вказує на цей шлях. Аргумент `--output` необов’язковий: JSON також друкується у stdout для журналу verify. Окремий діагностичний `--catalogue-only` завжди має `complete=false` і exit 1.

Потрібні `operations.test_access` (43 тести), `operations.test_blind_paths` (5 тестів), їхні прийняті fixtures та звичайні `verification_settings` / `check_support`. База та media надходять лише від verify. Скрипт відмовляється відкривати існуючий SQLite або довільне ім’я файлу; PostgreSQL перевіряється чинним disposable guard, а наявність таблиць до migrate дає red. Жодного flush робочої бази чи DROP у цьому gate немає.

Каталог resolver отримано без відкриття БД: 170 patterns = 73 API + 95 admin + 2 інші. API мають 69 унікальних patterns. Format aliases перевіряються зі slash і без slash. App-list розгортається в кожний наявний app label. Разом це 183 конкретні API/admin URL. Чотири відомі перекриті DRF root definitions записуються в `shadowed_definitions`; HTTP справді проходить перший доступний callback. Недосяжні callback не називаються протестованими.

Для кожного URL виконуються GET, HEAD, OPTIONS, POST, PUT, PATCH, DELETE, TRACE, CONNECT за anonymous / ceo / manager / observer / technical_admin. Додаються окремі контексти без view_document, download_document та export_workspace для відповідних маршрутів: разом 8 370 кейсів. Дані кожного кейсу відкочуються транзакцією, cookie jar копіюється з реальної сесії. Наявні об’єкти мають справжні PK; операції confirm отримують власний HTTP preview. Стан перевіряється до та після відповіді, включно з auth M2M: заборонений/читальний запит не повинен змінити записи. Валідний позитивний writer не зараховується лише за отриманням 400/404 або порожньою формою. Відповіді на читання мають містити відомі fixture записи; порожнього 200 недостатньо.

Technical admin — окремий staff/superuser без BoS Group; бізнес-API не отримує через нього роль CEO. Admin журналів є read-only. Фінансові форми й архівування зберігають A05. Autocomplete має справжній Salary.employee → EmployeeAdmin контроль. `/admin/r/<ct>/<object>/` має існуючі об’єкти, але в поточних моделях немає get_absolute_url: погоджений 404 має окрему категорію `existing_object_has_no_public_url`, без позитивної заяви про object authorization. Change/history/autocomplete є окремими позитивними контролями.

Для відомих unsupported admin methods приймаються як 405, так і безпечні GET-подібні 200/302 стандартного Django, якщо стан не змінився й дані дозволені технічному користувачу. Це окрема політика `*_read_only`, що перевіряє відсутність змін незалежно від успішного HTTP-статусу. Валідні POST журналів перевіряються тим самим способом; фактичне створення/зміна/видалення лишається red навіть при 200/302. Невідомі method declarations у Allow та невідомі converters не приймаються автоматично.

OPTIONS для відомих DRF службових views є законним metadata-контролем. Top-level metadata.description не трактуємо як фінансове поле Transaction.description; вкладені actions/fields та весь початковий bytes/JSON вміст продовжують перевірятися. Format-root посилається на `/api/tasks.json`, звичайний root — на `/api/tasks/`.

Тимчасовий 503 зовнішніх AI mutation endpoint для CEO/manager — категорія `external_adapter_not_executed`. Вона перевіряє тільки відмову й відсутність витоку, не підтверджує scoped tool adapter. Observer повинен отримати 403. Глибокі internal-context/ownership/proposal-revoke перевірки виконуються окремими обов’язковими 48 тестами. Реальна LLM не викликається.

JSON містить повний `catalogue`, `route_coverage`, кожен `case`, `failures`, `field_tests`, `counts`. Непройдений HTTP case містить `route`, `pattern`, `method`, `role`, `variant`, `expectation`, `status`, `policy`, знайдені поля/маркери та наявність небажаної зміни. Bytes, headers і JSON перевіряються незалежно від статусу, включно з streaming download. Приватні значення в цьому JSON — лише явно синтетичні canary.

Будь-який невідомий/відсутній route definition, converter, fixture, policy, недосяжний неочікуваний callback, невиконаний HTTP case або пропущений прийнятий test ID залишає gate червоним. Не прибирати fixture/поле або змінювати очікування на 400/500 заради green. При новому законному маршруті одночасно оновлюються manifest, policy, конкретний fixture і позитивний контроль.

Цей draft не позначає A04 готовим. Root переносить файли, зберігає перший red на зафіксованій ревізії і запускає gate після мінімальних продуктових виправлень. Окремий review probe використовує тимчасову синтетичну базу, а код checkout під час роботи root міг змінюватися: його результати придатні для перевірки працездатності самого gate, не для приймання ревізії продукту.

Інтеграційна перевірка механіки: 8 370 / 8 370 HTTP відповідей, жодної помилки fixture/скрипту; усі 48 прийнятих field/context тестів виконано без skip. Після неї виправлено наведені вище хибні тривоги metadata та уточнено read-only семантику стандартного admin. Додатковий smoke перевірив 372 GET/OPTIONS відповіді для позитивних записів; у ньому виявлено й виправлено format-root anchor та надмірний приватний marker для дозволеної історії task/HR керівника.

Наступні `operations.test_remaining_context` (2) та `operations.test_document_contract_visibility` (1) ще не внесено до manifest за прямою вказівкою root. Після фактичного копіювання додати ці labels і точні три test IDs, а мінімум змінити на 51. Без цього цей draft не називається перевіркою нового набору із 51 тесту.
