# A09 · чернетка серверної конфігурації та її контракт

12.09.2026. Scope: SRV01–03 і перевірка довіри до proxy на рівні middleware. A08 залишається поточною задачею root; A09 у checkout не інтегровано. Жодних original DB не відкривалося; мережевих серверів, залежностей, service units або інсталятора не створено.

## Файли кандидата

Корінь: `/workspace/scratch/c7b51e996a9f/tmp/a09_server_draft`.

| Чернетка | Майбутнє місце в checkout |
|---|---|
| `server_settings.py` | `server_settings.py` |
| `boss_project/server_config.py` | `boss_project/server_config.py` |
| `boss_project/server_wsgi.py` | `boss_project/server_wsgi.py` |
| `tests/test_server_config.py` | `boss_project/test_server_config.py` або `scripts/check_server_config.py` (import-safe, unittest.TestCase) |

SHA початкової перевіреної редакції: `tmp/A09_DRAFT_SHA256.json`; актуальної після незалежного огляду: `tmp/A09_REVIEW_DRAFT_SHA256.json`. Root — єдиний редактор checkout. Не копіювати кандидата до приймання A08. Це не production package і не прийнятий A09.

## Поведінка кандидата

- Окремий entrypoint приймає лише відсутній DJANGO_SETTINGS_MODULE або явний `server_settings`; чужий profile відхиляє. Ефективні налаштування перевіряє **до** `get_wsgi_application()` та ще раз після його створення. Підтримуваний запуск не виконує міграцій і не відкриває БД сам по собі.
- Із demo_settings імпортуються лише явно перелічені спільні несекретні constants: app list, templates, мова/пояс/тип PK/BASE_DIR. SECRET_KEY, DATABASES, MIDDLEWARE, режим і REST_FRAMEWORK сервера задаються окремо. Спільні lists/templates копіюються; local settings не змінюються.
- Обов'язкові env: `BOS_DATA_MODE=working`, `BOS_DATABASE_ENGINE=sqlite3`, `BOS_INSTALLATION_ID` (канонічний UUID), `BOS_INSTALLATION_ROOT`, `BOS_DATABASE_PATH`, `BOS_MEDIA_ROOT`, `BOS_PUBLIC_ORIGIN`, `BOS_ALLOWED_HOSTS`, `BOS_TRUSTED_PROXY_IPS`, `BOS_SECRET_KEY`.
- Каталог інсталяції має вже існувати; на POSIX — owner read/search без прав group/world. Read-only top-level 0500 допускається, коли підкаталоги вже підготовлено; запис у них та provisioning належать інсталятору. DB/media/static розміщуються всередині нього та не перекриваються; root не може бути checkout, його батьком або підкаталогом. Symlink/junction в шляху й hardlink DB відхиляються. Валідатор нічого не створює, не chmod, не мігрує та не читає байти DB. Він перевіряє конфігурацію шляхів; це ще не manifest/provisioner доказ власності інсталятора.
- Один канонічний HTTPS origin і точний hostname. Порожні/wildcard hosts, довільні origin/path/query/credentials відхиляються. SECURE_SSL_HOST фіксує canonical authority, тому http redirect не бере довільний порт із Host клієнта.
- `IsAuthenticated`, `SessionAuthentication`, поточний LocalRoleGuard та необхідні security/CSRF middleware обов'язкові. AllowAny, demo mode, DEBUG, ослаблені cookies/middleware після імпорту налаштувань також відхиляються.
- Secret не має demo/synthetic/django-insecure prefix, має не менше 50 ASCII символів і 12 різних символів. Це валідація якості, не доказ ентропії. Генерація/довговічне зберігання нового secret на кожну установку належить інсталятору. Старі fallback secrets у цьому кандидатові не підтримані.
- Secure/HttpOnly/Lax session cookie має installation UUID у назві. CSRF cookie лишається `csrftoken`, бо frontend читає саме її; обидві cookies host-only. Зовнішній AI adapter не вмикається.
- Довіра — тільки точним налаштованим IP proxy, без wildcard/CIDR/unspecified адрес. Недовірений upstream peer отримує 403. Заголовки forwarded спочатку очищаються; довірений proxy має передати один точний `http`/`https` і одну канонічну client IP. Client IP передається чинному login limiter. X-Forwarded-Host і RFC Forwarded не враховуються. Proxy **повинен** сам перезаписувати forwarding headers і закривати upstream порт від зовнішнього доступу; ця чернетка не доводить мережеву ізоляцію.
- На цьому bounded кроці є **лише явний SQLite profile**. `postgresql` відхиляється; він не видається за перевірений серверний backend. Native PG profile/driver/runtime додаються окремим наступним кроком A09/0.6 за фактичними умовами й офіційною документацією.

## Початкова редакція перевірок

Постійних DB не створюється. Кожен subprocess має власну порожню synthetic installation. Audit observer перехоплює будь-який `sqlite3.connect`, `socket.bind` або `socket.connect` і відхиляє його; фактичний список таких спроб у всіх записах порожній. Перевірки також звіряють склад файлів до/після: application creation нічого не записує.

8 методів, 52 фактичні subprocess probes:

1. Дві явні коректні конфігурації → два WSGI application, working mode, різні надані secrets/session cookie UUID; локальні constants незмінні.
2. Шість відмов для відсутнього/порожнього/demo/synthetic/слабкого/insecure secret.
3. Сім відмов для неправильного entrypoint, відсутнього/демо mode та неявного/непідтриманого backend.
4. Вісім відмов для hosts/origin.
5. Дев'ять перевірок isolation path (включно з POSIX mode, synthetic symlink/hardlink; original DB тільки як заборонений рядок шляху, без відкриття).
6. Десять ефективних мутацій налаштувань після їх імпорту: AllowAny/auth/mode/DEBUG/cookies/redirect/middleware.
7. Шість відмов для порожніх/широких/повторених proxy peers.
8. Чотири реальні виклики middleware: trusted peer; untrusted peer; неоднозначний proto; список client IP. Це in-process middleware, **не реальний HTTP/TLS proxy**.

Фінальні результати:

| Запуск | Результат |
|---|---|
| `A09_CONFIG_BEFORE_FINAL.log/.json` | На фактичному checkout: 8 методів, 51 assertion failure, 0 errors, 52 probes; усі відмови через відсутній server module; exit 1 |
| `A09_CONFIG_AFTER_FINAL.log/.json` | Той самий тестовий файл з draft overlay: 8/8, 52 probes, 0 failures/errors, 0 DB/socket attempts; exit 0 |
| `A09_CURRENT_PROFILE_READONLY.json` | Окремий попередній read-only факт: старий local WSGI створюється з demo secret/mode; немає DB attempts. Не є доказом серверного defect fix |

Нова функція ще була відсутня: baseline red означає саме відсутність server entrypoint. Тести навмисно **не** приймають ModuleNotFoundError за правильну config refusal; очікують контрольований ImproperlyConfigured українською. Це не 51 окремий дефект замороженого інвентарю.

До фінальних запусків tests були зроблені import-safe для подальшого Django discovery, а canonical SSL authority додано з окремою регресією. Попередні `A09_CONFIG_BEFORE/AFTER_1` журнали збережені як попередні редакції тестового harness. Продуктовий кандидат не мав невдалих green запусків; фінальний red/green використовує ідентичні assertions.

Команди (Python у прикладі — фактично використаний):

```sh
PYTHONDONTWRITEBYTECODE=1 /workspace/scratch/c7b51e996a9f/demo-check-env/bin/python /workspace/scratch/c7b51e996a9f/tmp/a09_server_draft/tests/test_server_config.py --source /workspace/sites/bos-original-refined --output /workspace/scratch/c7b51e996a9f/tmp/A09_CONFIG_BEFORE_FINAL.json
PYTHONDONTWRITEBYTECODE=1 /workspace/scratch/c7b51e996a9f/demo-check-env/bin/python /workspace/scratch/c7b51e996a9f/tmp/a09_server_draft/tests/test_server_config.py --source /workspace/sites/bos-original-refined --draft /workspace/scratch/c7b51e996a9f/tmp/a09_server_draft --output /workspace/scratch/c7b51e996a9f/tmp/A09_CONFIG_AFTER_FINAL.json
```

## Межа

Не перевірено й не реалізовано тут: installation ownership manifest, installer/start runner, health endpoints, production log redaction, actual TLS/proxy/WSGI process, static collection/proxy permissions, real HTTPS CSRF/login/admin цикл, upgrade, backup, PG, Windows. Приватний root потребує продуманого доступу proxy до зібраної public static без відкриття private media — це приймає майбутній installer/runtime стенд. Профіль не приймає довільні middleware override: коли root додасть log middleware, треба додати його до канонічного переліку та регресій, а не вимикати validator.

Ці локальні 8/8 **не закривають gate 8 або A09**. Після прийняття A08 root інтегрує кандидата, повторить реальні тести на checkout, додасть решту bounded сценаріїв і full verify. PostgreSQL/Windows/CI та інші відсутні gates лишаються червоними.


## Незалежний огляд і поточна редакція

Перевіряльник a08_migration знайшов три пов'язані shape/isolation проблеми: media всередині шляху майбутнього DB-файла; source-root alias через початкові `//`; існуючий звичайний файл як предок DB/media/static. Також effective cookie mutation ламала frontend contract (`csrftoken`) або installation-specific session name. До root checkout ці чернетки не потрапляли.

- Reverse nesting: `A09_PATH_DESCENDANT_BEFORE.log/.json` — реальний `started` замість `refused`, 1 failure; `A09_PATH_DESCENDANT_AFTER.log/.json` — 1/1. Перевірено обидва напрями вкладення DB і media/static.
- Alias: незалежний `A09_INDEPENDENT_PROBES.json` зафіксував accepted для двох шляхів до тієї самої синтетичної source directory (`samefile=true`). `_absolute` тепер відхиляє початкові `//`/UNC, не розкриває шлях у повідомленні. Окремий постійний тест відтворює samefile-ситуацію на власному synthetic root з 0700, щоб інша permission-відмова не приховувала порушення source boundary.
- Ordinary-file ancestor: незалежні `A09_FILE_ANCESTOR_PROBE.json/.log` та root-owned draft `A09_REVIEW_PATHS_BEFORE.json/.log` зберегли actual `started` для `data`-файла як батька DB path. Тепер існуючий предок кожного шляху обов'язково directory. Майбутні відсутні каталоги залишаються допустимими конфігураційно; інсталятор ще має їх реально створити й перевірити.
- У `A09_REVIEW_PATHS_BEFORE` — 4 методи, 3 assertion failures: ordinary-file ancestor та дві cookie mutations. Root 0000/0400/0200 у цьому непривілейованому runtime вже відхилялися permission error при перевірці шляхів; явний owner read/search check закріплює вимогу незалежно від UID. Це не три додаткові red defects. Позитивний root0500 із підготовленими дітьми збережений.
- `SESSION_COOKIE_NAME` має відповідати canonical installation UUID; `CSRF_COOKIE_NAME` мусить залишатися `csrftoken`. Зміна налаштувань після імпорту більше не обходить цей contract.

Актуальний `A09_REVIEW_FINAL.log/.json`: **12/12 методів, 62 реальні subprocess probes, 0 failures/errors, 0 DB/socket attempts**, exit 0. SHA — `A09_REVIEW_DRAFT_SHA256.json`. Тест filesystem mode не ставить fake pass на Windows: до native ACL перевірки його Windows запуск має червоний результат. Перевірки каталогів у parent harness тимчасово додають read/search лише для переліку власного synthetic дерева, після чого **відновлюють тестований mode до запуску worker**; бізнес-операції та DB/socket не підміняються.

Незалежні та попередні журнали збережено без перезапису; поточний повний прогін відокремлений від початкових 8/8. Gate 8, A09 та серверний реліз цими локальними тестами не прийнято.

## Первинні джерела

Root перевірив офіційну документацію Django 6.0 12.09.2026:

- [SECURE_PROXY_SSL_HEADER](https://docs.djangoproject.com/en/6.0/ref/settings/#secure-proxy-ssl-header): довіра допустима лише до контрольованого proxy, який прибирає вхідні клієнтські значення заголовка і встановлює його за фактичним TLS. У BoS збережено explicit peer та очищення forwarded headers; deployment proxy ще має підтвердити цю поведінку реальним тестом.
- [Deployment checklist](https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/): production налаштування перевіряються окремо; secret/hosts/HTTPS/static/media потребують фактичної перевірки установки.

Джерела обґрунтовують конфігурацію, але не є доказом виконаного TLS/runtime тесту. Нових runtime залежностей не обирали й не встановлювали.
