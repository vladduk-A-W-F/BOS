# A09 · SRV10/11: health та безпечний журнал

12.09.2026. Агент не редагував checkout, не відкривав original DB і не запускав мережевих серверів. Root інтегрує лише після SHA-звірки узгодженого загального snapshot A09.

## Готові файли

Корінь чернетки: `/workspace/scratch/c7b51e996a9f/tmp/a09_runtime_draft`.

| Файл | SHA-256 | Канонічний шлях |
|---|---|---|
| `boss_project/server_health.py` | `033d3dc0e8a4fccd127e20edc0ad409facb86ced6e5c3409ed888b1d6d3b7616` | той самий |
| `boss_project/server_logging.py` | `a39fe33d46796d068981542da27c50827e7f809f9fcdba07dff16366865bdf7c` | той самий |
| `boss_project/server_urls.py` | `e258179a527d62b56354e896b13e7406df2c48004b03ad341526b609d033e4d0` | той самий |
| `tests/test_server_health_logging.py` | `e2e3f7856d416cc0a67c1f54372fa28fbc909d8019f892604ee139842725ac2d` | `boss_project/test_server_health_logging.py` |

Інвентар: `tmp/A09_HEALTH_LOG_DRAFT_SHA256.json`. `a09_server_review` копіює ці файли до єдиного candidate, налаштовує ROOT_URLCONF і повторює canonical config/Waitress checks. Після цього root отримує **новий** загальний SHA manifest; старий config SHA 616b… стосується попередньої прийнятої чернетки, без health/logging.

## Поведінка health

Серверний ROOT_URLCONF=`boss_project.server_urls` додає два технічні маршрути та перевикористовує незмінену структуру `boss_project.urls`:

| Маршрут / name | Умова | Відповідь |
|---|---|---|
| GET `/health/live/` · `bos-health-live` | Процес обробляє HTTP | 200 `{"status":"alive"}`, жодного звернення до DB |
| GET `/health/ready/` · `bos-health-ready` | Серверний working profile, валідні шляхи, actual SQLite SELECT, усі required migrations applied, core table SELECT, придатне media | 200 `{"status":"ready"}` |
| GET readiness, залежність неготова | Відсутня/порожня/пошкоджена БД; pending migration; відсутній media, файл замість каталогу або owner не може читати/писати/проходити каталог | 503 `{"status":"unavailable"}` |
| POST та інші методи на обох | Завжди | 405 `{"status":"method_not_allowed"}`, `Allow: GET`, без dependency IO |

Всі health відповіді мають `Cache-Control: no-store`, без шляхів, SQL, назв міграцій, account IDs, рядків чи секретів. GET-only health views явно csrf_exempt, щоб POST завжди доходив до безумовної 405, без CSRF/session/DB операцій; це не поширюється на API/auth/admin. Маршрути технічно публічні, тому root має явно додати їх у server access catalogue/crawl. Readiness 503 означає справжню неготовність і не надає бізнес-доступу. Локальний URLconf лишається незмінним.

Readiness відкриває існуючий SQLite через `mode=ro`, вмикає connection-local `query_only`, виконує SELECT і закриває handle. Вона не робить migrate, ORM saves, INSERT/DELETE, не створює відсутню DB. Storage readiness перевіряє фактичні metadata, owner bits, os.access і scandir; **не** пише probe-файл або існуючі документи. Це перевірка доступності каталогу, не доказ fsync, вільних inode/дискової квоти чи повної бізнес-звірки. Тести використовують DELETE-journal синтетичні DB; read-only режим SQLite при WAL може потребувати службових sidecars, це не перевірка повного production backup/restore.

## Поведінка журналу

`CorrelationLoggingMiddleware` стоїть **першим**, перед TrustedProxyMiddleware, тому 403 peer refusal і HTTP redirect також мають server-generated UUID у `X-BoS-Request-ID`. Вхідний однойменний header не використовується. ContextVar розділяє запити; для Django status logs після повернення middleware formatter читає лише власне server-issued поле request, без META/body/query/headers.

`logging_configuration()` — один канонічний LOGGING dict. SafeJSONFormatter не форматує record message, args, traceback, SQL чи приватні request поля. Кожний application log має лише event, status, version, correlation_id. Навіть dict у недовіреному extra.bos_event не викликає небезпечний formatter fallback. Наявні default Django handlers замінюються; framework error/status logs проходять той самий formatter.

`report_configuration_failure()` може надрукувати безпечний JSON event до ініціалізації Django settings/logging. Server WSGI викликає його при ImproperlyConfigured і повторно піднімає ту саму контрольовану помилку. Bootstrap machine protocol start runner у stdout — окремий канал для trusted host/port/runtime; app request/error logs — stderr. Реальний Waitress/proxy процес перевіряє інший агент/root; ці тести не заявляють покриття всіх native proxy/server logs.

## Фактичні докази

- `tmp/A09_HEALTH_LOG_BEFORE.json/.log`: **7 методів, 12 failures, 0 errors** на незміненому server config snapshot без нових модулів. Health реально 404; correlation/config events відсутні; звичайні process logs містили синтетичні password/body/header/query canaries.
- `tmp/A09_HEALTH_LOG_AFTER_1.json/.log`: 7 методів, 1 failure healthy readiness. Виявлено помилку observer: audit event `sqlite3.connect/handle` виникає до повної ініціалізації Connection; ранній `set_trace_callback` сам заважав відкриттю. Змінено лише instrumentation на C-call profile перед фактичним execute. SQL не підміняється, існуючі assertions не послаблено.
- `tmp/A09_HEALTH_CORRELATION_BEFORE.json/.log`: **2 методи, 1 failure**. Після виправлення observer healthy readiness реально 200 і readonly SELECT підтверджено; окремий посилений assertion показав втрату request ID в Django status logs після context reset.
- `tmp/A09_HEALTH_LOG_AFTER_2.json/.log`: **7/7 методів, 12 subprocess сценаріїв, 17 actual Django HTTP responses, 0 socket calls**, 25.815 с. Всі HTTP статуси, мінімальні JSON, відмови залежностей, readonly SQL і незмінність synthetic installation files пройшли. Всі request/error/status logs використовують відповідний server-issued ID; canaries/newline fake record не виходять у stdout/stderr.

Сценарії: live без DB; ready healthy/missing/empty/corrupt/pending; missing/file/readonly media; POST обох health; конфіг-помилка; actual 200/500/404/400/403/301 із private canaries у body/password/token/cookie/Authorization/query/filename і підробленим correlation header. Trace observer записує лише verbs PRAGMA/SELECT, не SQL-текст.

У тестовому URL overlay є спеціальні view для контрольованого 500 і raw logging. Вони **не** входять до server_urls або root URLconf; це лише fixture для перевірки stdout/stderr. Постійний тестовий файл повторює ті самі справжні subprocess requests після канонічної інтеграції.

Команда green:

```sh
PYTHONDONTWRITEBYTECODE=1 /workspace/scratch/c7b51e996a9f/demo-check-env/bin/python /workspace/scratch/c7b51e996a9f/tmp/a09_runtime_draft/tests/test_server_health_logging.py --source /workspace/sites/bos-original-refined --config-draft /workspace/scratch/c7b51e996a9f/tmp/a09_server_draft --runtime-draft /workspace/scratch/c7b51e996a9f/tmp/a09_runtime_draft --output /workspace/scratch/c7b51e996a9f/tmp/A09_HEALTH_LOG_AFTER_2.json
```

SRV10/11 приймаються лише в цьому локальному application обсязі. Реальні TLS/proxy, installer, server lifecycle, log collection від proxy/Waitress, native PG, Windows і full gate8 — окремі відкриті перевірки. Наявність цих файлів не робить product release зеленим.

## Загальна заморожена редакція

Після передачі автор серверного кандидата створив immutable snapshot `tmp/a09_server_candidate_20260912T093109Z`; `tmp/A09_SERVER_FROZEN_MANIFEST.json` містить усі точні SHA. Мої health/logger/router/test SHA у snapshot збігаються з таблицею вище. У канонічній ізольованій копії джерела, без draft overlay або dependency override, автор реально повторив **21 метод: config 12/62 probes, health/logging 7/12 сценаріїв/17 HTTP, Waitress 2/7 HTTP — усі пройшли**. Контрольний git base: `cdebfd697d2e94ad33b9cadace4855c2635a3722`.

Root отримав frozen manifest і продовжує справжнє TLS/proxy приймання. Після snapshot автори не редагують candidate; подальші root зміни вимагають нової звірки SHA та відповідних фактичних перевірок.
