# A09 — незалежна перевірка HTTPS і журналів

Дата: 12.09.2026. Межа роботи: читання основного checkout; зміни лише у tmp і нових синтетичних інсталяціях. Оригінальну базу не відкривали. Це не підтвердження усіх 11 gates.

## Підтверджені дефекти та виправлення

1. `header_up -X-Forwarded-*` у Caddy видаляв щойно встановлені `X-Forwarded-For` і `X-Forwarded-Proto`. Перший справжній HTTPS-запит отримував BoS 400. Виправлено видаленням лише зайвих конкретних заголовків, а XFF/XFP явно перезаписуються значеннями фактичного з’єднання. BoS як і раніше перевіряє реальний peer до довіри до цих значень.
2. Неявний порядок Caddy виконував загальний `handle` раніше за відмову для чужого Host. Спостерігали Django 400 замість очікуваного proxy 421. Виправлено явним `route`: Host → private media → розмір тіла → static/app.
3. `msg delete` не видаляв `msg`: поле залишилося в усіх 40 фактичних рядках Caddy. Це підтверджена хибна гарантія фільтра, а не знайдений витік секрету. Офіційна документація прямо описує цю властивість основних полів. Підготовлений `proxy_logging.py` перетворює stdout/stderr процесу на чотири дозволені поля **перед записом**. Інтеграцію потоків виконує автор lifecycle; справжній lifecycle rerun ще потрібен.

Джерело для п. 3: https://caddyserver.com/docs/caddyfile/directives/log, секція `filter`, перевірено 12.09.2026. Поля msg/ts/level/logger спеціально додає базова logging library; фільтрація поля не є їх видаленням.

## Фактичні докази

- Початкова відмова: `tmp/A09_TLS_ACTUAL_2.log`.
- Після виправлення заголовків: `tmp/A09_PROXY_REVIEW_AFTER_HEADERS.log`; HTTPS 200, потім окрема відмова тесту Host.
- Після явного порядку route: `tmp/A09_PROXY_REVIEW_AFTER_ROUTE.log`, звіт `/tmp/bos-a09-tls-9fbfcqmd/report.json`: **16/16** справжніх перевірок Caddy 2.11.1 → Waitress 3.0.2 → BoS; TLS із перевіркою сертифіката та hostname.
- Вибірка структури журналів: `tmp/A09_PROXY_LOG_FIELDS.json`. Жодного перевіреного password/document canary не було в сирих журналах того прогону. Cookie canaries тоді ще не входили до цієї гарантії.
- Cookie patch `tmp/A09_COOKIE_CANARY.patch` включено root у новий `scripts/server_http_checks.py`: значення всіх отриманих Set-Cookie додаються до приватних canaries, не до звіту.
- Normalizer: `tmp/A09_PROXY_NORMALIZER_FIXTURES.log`, **4/4** методи. Реальний captured Caddy access record зберігається у fixture; до msg, cookie, authorization, exception, request, unknown fields додано синтетичний canary. Перевірено відкидання цих полів, неструктурних/завеликих/глибоких рядків, некоректних status/version, запис рівно чотирьох полів та новий UUID4.

## Заморожений normalizer

- `tmp/a09_proxy_logging_draft/proxy_logging.py` → `boss_project/proxy_logging.py`; SHA256 `bb935ba3591e8758d7090534716d8090ace492f63f5a298201de5bd7fb4e28e7`.
- `tmp/a09_proxy_logging_draft/test_proxy_logging.py` → `boss_project/test_proxy_logging.py`; SHA256 `b19fb0d8ded6ac27eb570530bb0471c72296b73729049fd12a53485f742e55d8`.
- Manifest: `tmp/A09_PROXY_LOGGING_FROZEN.json`. Копії read-only; більше не змінюються.
- API: `normalize_proxy_line(line, *, version)`, `write_proxy_line(line, stream, *, version)`. Version береться із перевіреного release manifest; незалежно перевіряється компактна SemVer-форма. Correlation ID проксі створюється сервером для події й не видається за application request ID.

## Читання нового installer acceptance harness

Прочитано `scripts/check_install.py`, `scripts/server_http_checks.py`, `scripts/package_server.py`. TLS context перевіряє власний тестовий сертифікат; потрібні фактичні executable/wheel prerequisites. Harness створює новий каталог, package, інсталяцію, облікові записи; config і DB беруться лише з нової інсталяції. Package дозволяє визначені корені/типи коду; SQLite-файли не входять до набору читання. Жодного runtime fallback на demo settings у перевірених шляхах немає.

Перевірки HTTP мають реальні переходи anonymous → CSRF login → authorized API → original upload/download/review → logout, окремий native admin та перевірку відмови його бізнес-ролі. Root також додав health, demo-off, frontend, runtime mode. Власні Popen-об’єкти визначають процеси, які можна зупиняти; restart порівнює точний hash лише нової DB і її приватних файлів.

Один переданий root вузький пробіл: тест 13 MiB порівнює список Document до/після 413, але сам по собі не доводить відсутності orphan-файлу. Потрібен snapshot приватного дерева навколо цього запиту. Назва `no_partial_document` відповідає вже наявній перевірці записів; формулювання `no partial file` до snapshot використовувати не слід.

Після заміни збереження Caddy logs acceptance має перевіряти не лише відсутність canaries, а й непорожні JSON-події від обох процесів. Чотири поля normalizer доведені fixture-тестами; їх застосування до фактичних обох потоків підтверджується новим lifecycle прогоном, а не історичними 16 TLS перевірками.

## Подальша незалежна перевірка lifecycle

Прочитано фінальний `tmp/a09_lifecycle_server.py`, SHA256 `e21fa92d85715bad84e8a37b9fc50545bce4044eea0107bbc98e9009315b8f5e`. Обидва потоки Caddy обробляє helper із перевіреного release; raw fallback відсутній, збій запису блокує ready та роботу. Власний startup event читається лише в пам’яті із власного stderr; health і повторний poll виконуються після нього. Конкретного блокера в цьому diff не знайдено.

Прочитано фактичний звіт автора `tmp/A09_LIFECYCLE_OWNED_READY_FINAL.json`: 3/3 відмови за наявності чужого validTLS listener без хибної ready, чужий listener залишився працювати; позитивний власний TLS/health, відмова duplicate та graceful stop пройшли. Повторний повний прогін рецензентом не проводився. Це вузький консенсус щодо ownership/logging, а не приймання нестабільної 13 MiB межі. Її окремий червоний handoff: `tmp/A09_OVERSIZE_HANDOFF_UA.md`.
