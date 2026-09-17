# A09 · серверний профіль: обмежений план перевірки

Дата: 12.09.2026. Підготовка після читання `docs/PROGRESS_UA.md`, master v2.1 та TASK_TABLE. A08 ще не прийнято: цей документ не починає A09, не змінює код checkout і не надає статусу готовності. Виконавець інтеграції — root; окремий перевіряльник працює на синтетичних установках.

## Факти поточного стану

1. `boss_project/settings.py` імпортує `demo_settings`; стандартний `boss_project.wsgi:application` реально створив WSGI application з `BOS_DATA_MODE=demo` та відомим локальним secret. Запитів до БД не було: audit guard відхиляв би кожну `sqlite3.connect`, журнал спроб порожній. Це штатний локальний профіль, а не доказ зламу прав.
2. Немає серверних entrypoint/settings/install/check_install/check_upgrade. `scripts/start_local.py` явно вибирає demo_settings, працює через Django runserver, створює локальну venv, мігрує локальну копію та сіє демо. Його не можна використовувати як серверний інсталятор. Поточні 5 launcher checks залишаються незмінними.
3. DRF уже має `IsAuthenticated`, A03/A04 відсікають demo endpoint у робочому режимі та захищають API/admin/private media. Не потрібно повторно реалізовувати ідентичність чи видаляти цей захист.
4. Реальний Django security check дав W001/W002/W003/W009/W012: немає SecurityMiddleware / XFrameOptionsMiddleware / глобального CsrfViewMiddleware, локальний secret, не secure session cookie. Власна API CSRF перевірка існує; W003 не доводить її відсутності. `CSRF_COOKIE_SECURE=False`, `SECURE_SSL_REDIRECT=False`, `SECURE_PROXY_SSL_HEADER=None`, `CSRF_TRUSTED_ORIGINS=[]`, явного LOGGING немає.
5. `/api/runtime/status/` повертає поточну VERSION, але `mode='local'` і `dashboard='demo_generated'` зашиті. Це потребує точного відображення реального серверного профілю, не нових вигаданих KPI.
6. Публічного health endpoint немає. Статичний app.js уже віддається дозволеним маршрутом `/assets/<name>`; admin static потрібно зібрати окремо. `/media/` має залишитися 404 і на proxy.
7. `scripts/verify.py` уже очікує `scripts/check_install.py` для gate 8 і `scripts/check_upgrade.py` для gate 9. Перелік 11 критеріїв не змінюється.

Докази підготовки: `tmp/A09_CURRENT_PROFILE_READONLY.json`, `tmp/A09_RUNTIME_READONLY.json`, `tmp/A09_PRIMARY_RUNTIME_READONLY.json`. Exit 0 діагностики означає успішний збір фактів, а не приймання A09. Немає до/після тестів A09; наведені нижче сценарії спочатку потрібно перетворити на реальні падаючі регресії.

## Реальна доступність середовища

| Компонент | Факт на 12.09.2026 |
|---|---|
| ОС / Python | Linux 6.18.35, Python 3.12.14 |
| Django / DRF | 6.0.5 / 3.17.1 |
| TLS Python / CLI | Python ssl OpenSSL 3.5.8; `/usr/bin/openssl` 3.0.13 |
| cryptography | 46.0.0 лише у додатковому primary runtime site-packages; не в залежностях BoS |
| Nginx / Caddy | виконуваних файлів немає |
| Gunicorn / Waitress / Uvicorn / Hypercorn | немає executable або Python distributions у venv BoS та додатковому runtime |
| systemd | команда `systemctl` — повідомлення-заглушка: systemd у контейнері не працює |
| Docker / Podman / PostgreSQL / PowerShell | executable не знайдено; native PG пакет також відсутній |

TLS бібліотека не замінює реальний reverse proxy / WSGI server. Локальний самопідписаний тестовий сертифікат може перевірити TLS-з'єднання на стенді, але не підтверджує публічний сертифікат/домен. `wsgiref`, Django test client і runserver не видаються за production deployment. Нічого не встановлювалося, порти не відкривалися, сервісів не запускали.

## Найменша реалізація після приймання A08

Одна компанія — окремий каталог інсталяції, база, MEDIA_ROOT і секрет. Зберегти Django, frontend та local launcher. Серверний runtime: один підтримуваний WSGI server за одним TLS reverse proxy; версії залежностей визначити й зафіксувати під час A09 за офіційним джерелом та реальним встановленням. Не вибирати другий стек для обходу відсутнього runtime.

| Файл / місце | Зміна | Що не дублювати |
|---|---|---|
| `server_settings.py` (новий) | Явні server mode, secret, hosts/origin, DB/media/static paths, security middleware/cookies, trusted proxy та структуровані logs; обов'язкові параметри без demo defaults | Не змінювати поточні local/test settings; спільні несекретні app/template constants можна перевикористати без зміни їх значень |
| `boss_project/server_wsgi.py` (новий) | Єдиний підтримуваний production entrypoint; відмова для іншого DJANGO_SETTINGS_MODULE і небезпечної кінцевої конфігурації до bind/SQL | Не перетворювати локальний WSGI в серверний неявно |
| `boss_project/server_config.py` (новий компактний модуль) | Один валідатор ефективних налаштувань для install/start/check: секрет, режим, exact hosts/origins, auth classes, middleware, isolation paths | Не мати окремих слабших правил у launcher і WSGI |
| `boss_project/server_middleware.py` (якщо потрібно) | Встановити довіру до forwarding headers тільки від явно довіреного peer; відкидати/очищати решту до SecurityMiddleware; структурований журнал без payload/query/headers | Не приймати довільний X-Forwarded-Proto/For/Host клієнта |
| `boss_project/health_views.py`, `boss_project/urls.py` | Окремі GET liveness/readiness; readiness перевіряє DB/schema і приватне сховище, без клієнтських даних/шляхів/секретів | Не відкривати runtime/snapshot API анонімно |
| `boss_project/refinement_views.py` | Показати реальний mode/version авторизованому користувачу | Без демо фактів у server mode |
| `requirements-server.txt`, `deploy/` | Закріплені WSGI залежності, конфіг proxy, service template, env/config example без секрету; static-only alias, deny media, loopback/Unix upstream | Не вимагати Node.js від клієнта; не публікувати порт upstream |
| `scripts/install_server.py`, `scripts/start_server.py` | Одна команда на нову порожню інсталяцію; venv/deps, власний каталог, migrate, collectstatic, manifest версії; start перевіряє конфіг/manifest і використовує server entrypoint | Не копіювати db.sqlite3, не сіяти демо, не користуватися BoS_Demo.sqlite3/BoS_Working.sqlite3, не переписувати наявну невідому установку |
| `scripts/check_install.py` | Реальне встановлення у нову синтетичну інсталяцію та HTTP/TLS перевірки нижче; report із середовищем, командами, source SHA та точними результатами | Відсутній proxy/runtime — НЕ ЗАПУЩЕНО, не skip/pass |
| `scripts/check_upgrade.py` | Реальні два пакети N і N+1, копія синтетичних даних, запуск до/після; джерельна установка незмінна | Остаточний rollback DB+files+config+code — спільне приймання з A10; зворотна migration сама по собі не rollback |
| `tests` або `boss_project/test_server_*.py` | Скінченні регресії таблиці нижче; після додавання health routes оновити фактичний access manifest і пройти gate 4 | Не змінювати старі assertions/пороги заради нового профілю |
| `docs/SERVER_INSTALL_UA.md`, `CHANGELOG_UA.md`, `docs/PROGRESS_UA.md` | Команди, конфіг, межі перевіреного, версія, фактичний статус | Немає release passport до 11 зелених gates |

## Скінченна регресійна матриця

| ID | До виправлення / дія тесту | Обов'язковий результат після |
|---|---|---|
| SRV01 | Запустити підтримуваний server entrypoint без secret, з `local-demo-only`, `synthetic-verification-only`, коротким/неприпустимим secret | Відмова до відкриття socket і БД; причина українською без значення secret |
| SRV02 | DJANGO_SETTINGS_MODULE=demo_settings/verification_settings; mode demo; кінцева permission class AllowAny; demo guard замість серверного profile | Кожен небезпечний варіант відхилено; підтверджена DRF IsAuthenticated і всі A03/A04 guards збережені |
| SRV03 | Порожній/`*` ALLOWED_HOSTS, недовірений origin, відносні або checkout/local-demo DB/media paths; дві інсталяції з одним шляхом | Неприпустимі конфігурації відхилено; дві нові інсталяції мають різні секрети/DB/media/session boundary |
| SRV04 | Порожня owned інсталяція, одна команда install, нова venv і pinned dependencies | Реальні migrate+collectstatic+startup пройшли, VERSION/source digest у manifest і UI; немає demo записів; original DB не відкрито |
| SRV05 | Обрив install після створення venv/до manifest; повтор; target з невідомими файлами | Повтор на власній незавершеній установці коректний; невідомий target відхилено; нічого не видалено/перезаписано |
| SRV06 | HTTPS через реальний proxy; HTTP на вхідному порту; правильний і неправильний Host | Валідний TLS response; HTTP переходить на погоджений HTTPS origin без open redirect; wrong Host відхилено; немає redirect loop |
| SRV07 | Через proxy передати клієнтські X-Forwarded-Proto/Host/For, дублікати та comma values; запит напряму до upstream | Proxy перезаписує заголовки; недовірений peer не задає secure scheme/host/client IP; upstream недоступний з зовнішньої мережі за конфігом стенду |
| SRV08 | Реальний CSRF login/logout цикл через HTTPS; unsafe API без token; чужий Origin з валідним cookie | Secure/HttpOnly/SameSite session, secure CSRF cookie; CSRF відмови; logout відкликає сесію; staff/admin login також під CSRF |
| SRV09 | Анонімний і old-demo-session доступ до API/admin; POST demo endpoint; GET raw media; авторизований download | Анонімний/демо доступ відхилено, demo endpoint 404, raw media 404 на Django і proxy, scoped checksum download працює |
| SRV10 | GET liveness/readiness при чистій і мігрованій DB, pending migration, непридатному media; POST health | 200 тільки за визначеним healthy станом, 503 при залежності неготовій, POST 405; JSON не розкриває DB paths, rows, account IDs, secret, SQL |
| SRV11 | Запити з synthetic canary у password/token/cookie/Authorization/query/body/filename; 4xx/5xx і помилка конфігурації | Реальні stdout/stderr/access/error logs містять event/status/version/correlation ID, не містять canaries, body, query чи секрети; newline не створює підроблений log record |
| SRV12 | Два екземпляри на одному installation root; graceful stop/start та перезапуск після помилки | Власник процесу/lock визначений; другий не починає міграцію, файли/історія збережені, повторний start не сіє/не мігрує неявно дані |
| SRV13 | Статика frontend/admin, довгий/завеликий upload через proxy і app | Assets працюють із production DEBUG=False; приватний каталог не alias; узгоджені ліміти proxy/app, 413/422 без часткового документа |
| SRV14 | Версія N з реальним synthetic dataset+private files → пакет N+1 на isolated clone | Source SHA і обидві версії відомі; процес N зупинено перед копією, migration/післяперевірка запускаються реально; ID/FK/Decimal/SHA/document versions точні |
| SRV15 | Контрольована помилка після migration N+1 → rollback у чистий власний target | Відновлені разом N code/config/DB/files, перевірки N сходяться; source N не змінено. До реалізації A10 цей пункт і повний gate 9 лишаються червоними |
| SRV16 | Запуск gate 8/9 без WSGI/proxy/installer або без одного пакета версії | Report НЕ ЗАПУЩЕНО/НЕ РЕАЛІЗОВАНО із причиною, exit nonzero; ніяких статичних assertions замість стенду |

Примітки: SRV10 використовує справді створені непридатні залежності/порожню БД у subprocess, а не mock результату health. SRV11 перевіряє фактичні process logs, а не лише formatter unit test. SRV07 довіра до клієнтського IP впливає також на наявний login limiter: proxy peer не повинен видаватися за кожного користувача, але довільний X-Forwarded-For теж не може обходити ліміт. Public health — новий технічний маршрут; його потрібно явно включити до повного role crawl, без ослаблення заборони поля.

## Послідовність і межа приймання

1. Дочекатися зафіксованого A08 і незалежного scoped consensus. Прочитати PROGRESS повторно.
2. Спершу реальні red SRV01–03/10 та встановлення відсутнього entrypoint. Додати тільки server configuration/guard/middleware/health; повторити red → green на порожній новій SQLite. Нічого не запускати проти original DB або A08 робочої копії root.
3. Під'єднати один справжній WSGI+proxy стенд і реалізувати SRV04–13. Якщо runtime неможливо встановити у дозволеній мережі, зберегти точну причину й готові конфіги; local settings tests не закривають gate 8.
4. Протокол SRV14–15 спирається на наявний A07/A08 exact transfer; не переписувати codec і не створювати окремий недоказаний exporter. A09 готує update; A10 приймає повний backup/restore/rollback. Два пакети — справжній archive N та новий N+1, без підміни рядка VERSION.
5. Повний verify + independent review; source digest включає нові deploy/server settings. Усі доступні раніше зелені частини мають залишатися зеленими. PostgreSQL, Windows, CI та інші відсутні gates залишаються червоними до реального запуску. Наявність файлів конфігурації не є прийманням.

Підготовка не знайшла нового грошового/складського дефекту поза 85/12. Реальна серверна конфігурація відсутня і є відомою задачею A09, а не підставою змінювати заморожений інвентар.
