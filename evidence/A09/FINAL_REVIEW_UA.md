# A09 — незалежний фінальний огляд часткової контрольної точки

**Рішення: A09 загалом НЕ ПРИЙНЯТА.** Підтверджено вузький консенсус щодо реалізованих і фактично перевірених частин. Повний MVP і виробниче розгортання цим рішенням не приймаються.

Дата: 12.09.2026. Рецензент: окремий агент `a09_server_review`. Перевірка була read-only щодо checkout `/workspace/sites/bos-original-refined`; нових HTTP/boundary/full-suite запусків не виконували. Бази даних рецензент не відкривав. Файли A10 не включені до цього приймання A09.

## Точний перевірений стан

- A08 HEAD: `cdebfd697d2e94ad33b9cadace4855c2635a3722`.
- `evidence/A09/verify-1/report.json`: suite `full`, `complete=false`, Linux, Python 3.12.14.
- SHA коду у звіті: `681d1470aedacb9db929c416a8d8f2c521b92e8e498b99a4c954e3bef4a014df`.
- Незалежно обчислений SHA поточного checkout за тим самим набором коду **точно збігається**. Прочитано 277 файлів коду/ресурсів, жодного SQLite/DB-файлу.
- `scripts/verify.py` байт-у-байт не змінений від A08 HEAD. Через AST окремо звірено незмінні ідентифікатори 1–11, назви та набір GATES.
- Повний звіт вказує `source_database_count=2`, `source_databases_unchanged=true`. Це доказ із перевіреного звіту; рецензент не повторював читання вихідних баз.

## Збереження локальних результатів A01–A08

Прочитано основний звіт і фактичні журнали `sqlite-django-tests.log`, `gate-03-sqlite.log`, `gate-04-sqlite.log`, `gate-05-sqlite.log` та записи повернення попередніх перевірок.

| Локальна перевірка | Фактичний результат A09 verify-1 |
|---|---|
| Порожня SQLite та міграції | Пройдено, returncode 0. |
| Існуючі функціональні перевірки | 22+49+48+32 = **151**, без зменшення очікуваних кількостей. |
| Launcher | **5/5**, returncode 0. |
| Решта Django | **421/421**, `OK`; A08 мав 378, у кандидата додано 43. |
| П’ять інваріантів | Кожний **1000/1000**, усі п’ять `ПРОЙДЕНО`. |
| Права | **8460/8460 HTTP +9 redirect**, **57/57** перевірок полів, `complete=true`. Дві health-поверхні додані; попередній policy oracle не послаблено. |
| Одночасні дії | **84/84** методи, **89** фактичних ERP pair PASS, `complete=true`, runner failures 0. |
| Перенесення A08 у загальному наборі | Збережені зелені факти перевірки ownership, checksum, rollback, missing mutex, mixed 45-table transfer та high-water IDs. |

За цими фактичними локальними gates регресій A01–A08 не виявлено. Це не замінює відсутню PostgreSQL/Windows/CI-перевірку попередніх задач.

## Gate 8: точний результат, без перенесення історичних успіхів

Прочитано `evidence/A09/verify-1/gate-08-sqlite.log` і поточні `scripts/check_install.py`, `scripts/server_http_checks.py`, `scripts/provision_runtime.py`.

У поточному прогоні **31 запис перевірки: 30 успішних, 1 непройдений**. Це **26/27 HTTP-сценаріїв** та чотири перевірки встановлення/lifecycle/logging. Загальний gate 8: `ПОМИЛКА`, returncode **1**, `complete=false`.

Підтверджені частини:

- Новий окремий package, приватна venv з точними залежностями, фактичні міграції, collectstatic, порожні бізнес-таблиці.
- Реальні Caddy 2.11.1 → Waitress 3.0.2, TLS із перевіркою сертифіката; приватний loopback.
- Secure CSRF cookie; login із Secure/HttpOnly/Lax session; anonymous/API та CSRF/foreign-origin відмови.
- Health GET, відмова іншого методу, вимкнений demo endpoint, серверний runtime/status 0.2.9-dev, frontend і assets.
- Відмова чужого Host, очищення підроблених forwarded headers, точний HTTP redirect, непублічний `/media/`.
- Реальні upload 201, exact-original download із SHA, review; logout; native Django admin із CSRF та забороною бізнес-ролі технічному admin.
- Другий екземпляр відхилено; stop/restart збережено точні байти синтетичної DB і приватних файлів. Поточний A09 тест завершував уже неактивні запити; він не доводить drain активних записів — це окрема A10 робота.
- Непорожні нормалізовані журнали: **40** application records і **82** proxy records; рівно `event/status/version/correlation_id`. Перевірено accepted/rejected requests. У **29** журналових файлах перевірені приватні canaries відсутні.

Єдина непройдена поточна перевірка: `oversized_request_413_no_partial_document`. Для 13 MiB клієнт отримав **ConnectionResetError**, `status=null`, `passed=false`. Список документів і точні приватні байти залишилися незмінними. Наявність 413 у proxy log **не зарахована** як отримана клієнтом HTTP 413. Код зберігає цю відмову, виконує інші незалежні сценарії та залишає фінальний результат червоним.

Історичні спроби 13 MiB та неприйнятий concurrent-client candidate не підміняють результат цього verify. Відомий boundary залишається заблокованим за правилом обмеження спроб; нових boundary-запусків у цьому огляді немає.

## Чесність інструкції встановлення

`docs/SERVER_INSTALL_UA.md` коректно розрізняє встановлення програми і приймання HTTPS: `application_provisioned=true`, **exit 2**, **complete=false**. Це відповідає фактичному `provision_runtime.py` та вкладеному installer result у gate-08 log. Команда не видає незапущені WSGI/TLS/health як пройдені.

Інструкція явно обмежує стенд Linux amd64/Python 3.12/SQLite/loopback, окремо залишає публічний домен, PostgreSQL, Windows, update/restore. Типові паролі не обіцяються; тестові акаунти створюються лише acceptance harness. Readiness не видається за перевірку фінансів/backup. Демо KPI та browser-local organizer прямо позначено їхнім фактичним статусом.

Рекомендоване суто документальне доповнення перед передачею checkpoint: на початку цієї інструкції зазначити, що поточний gate 8 ще червоний через 13 MiB. Поточний текст не стверджує complete=true; доповнення зробить обмеження помітним читачеві без пошуку окремого звіту. Рецензент checkout не редагував.

## Незмінні 11 gates

| Gate | Стан повного звіту | Межа |
|---:|---|---|
| 1 | НЕ ЗАПУЩЕНО | SQLite green; PostgreSQL відсутній. |
| 2 | НЕ ЗАПУЩЕНО | SQLite 151+5+421 green; PostgreSQL відсутній. |
| 3 | НЕ ЗАПУЩЕНО | SQLite 5×1000 green; PostgreSQL відсутній. |
| 4 | ПРОЙДЕНО | Локальний повний обхід прав із health additions. |
| 5 | НЕ ЗАПУЩЕНО | SQLite concurrency green; PostgreSQL відсутній. |
| 6 | НЕ РЕАЛІЗОВАНО | Немає прийнятого e2e_scenario.py. |
| 7 | НЕ РЕАЛІЗОВАНО | Немає прийнятого check_restore.py. |
| 8 | ПОМИЛКА | 30/31; 13 MiB HTTP не підтверджено. |
| 9 | НЕ РЕАЛІЗОВАНО | Немає прийнятого check_upgrade.py. |
| 10 | НЕ РЕАЛІЗОВАНО | Немає прийнятого check_ui.py. |
| 11 | НЕ ЗАПУЩЕНО | Реального Windows runner report немає. |

CI identifiers у звіті порожні; зовнішній CI не прийнятий. Успішні частини дозволяють зберегти **partial checkpoint**, але не перевести A09 або MVP у готовий стан. Продовження A10 є роботою над наступним обмеженим блоком, а не обходом червоного gate 8.
