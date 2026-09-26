# BoS · незалежний огляд A02

Дата: 11.09.2026. Read-only перевірено diff `finance/models.py`, `finance/views.py`, `scripts/check_support.py`, новий `finance/test_payment_integrity.py`; checkout не змінено. Це огляд реалізації, не власний повторний прогін тестів.

**Висновок: блокувальних дефектів у вузькому A02 не знайшов.**

1. `mark_paid()` починає захищену транзакцію зі справжнього no-op UPDATE Salary, потім перечитує `self` і лише після цього перевіряє стан. Це усуває старе рішення на основі застарілого ORM-об'єкта. Подальша витрата, статус, дата та прив'язка зберігаються в тій самій atomic.
2. Повтор узгодженого paid повертає існуючу Transaction до обробки нової дати. Перевіряються direction/category/amount/currency/date. Paid без transaction лишається помилкою та не «відновлюється» автоматично; старий тест із таким станом не потрібно змінювати на успіх.
3. EUR/USD/UAH передаються у витрату явно. Pending із наявною transaction, cancelled, невалідні сума/валюта/дата відхиляються. `self.refresh_from_db()` потрібний і правильно використаний: чинний view серіалізує той самий початковий об'єкт.
4. DB-помилки ловляться view вже після виходу з atomic та повертають 409, а не успіх. Внутрішній exception не приховується всередині транзакції. Це не замінює вимогу тестів про дві однакові успішні відповіді: новий concurrent HTTP тест явно вимагає `[200, 200]` і однакові JSON.
5. Нові регресії змістовні: два stale ORM з'єднання для кожної валюти, два реальні HTTP запити, replay з іншою запропонованою датою, перевірка прив'язки джерела, неузгоджена історія. Barrier стоїть до критичної секції; ORM/HTTP не мокаються.
6. Trigger-тест правильно перевіряє помилку після INSERT Transaction: no-op pending → pending проходить, paid UPDATE відхиляється справжньою БД, атомарний відкат прибирає витрату, після зняття trigger повтор успішний. PostgreSQL trigger визначений окремо, але його реальний запуск цим оглядом не підтверджено.
7. Файловий `TEST.NAME` додано тільки до верифікаційного SQLite-профілю з явним тимчасовим `BOS_TEST_DB_NAME`. Це коректно для реальних міжпотокових блокувань і не змінює робочі бази. Конкурентні тести використовують `TransactionTestCase`, а не зовнішню TestCase atomic.
8. Межа висновку: A02 захищає команду виплати. Обхідні зміни/видалення зарплати, витрати чи працівника через CRUD/admin залишаються A05. Виправлення не є прийманням усіх фінансів, PostgreSQL, Windows або повного `verify`.

## Перевірка локального PostgreSQL runtime

Збережені факти: `tmp/postgres_runtime_review.json`. Без встановлення пакунків, запуску серверів або зовнішніх з'єднань виконано перевірку PATH, стандартних каталогів, dpkg/apt metadata, назв runtime-файлів і локального pip cache.

- `postgres`, `initdb`, `pg_ctl`, `psql`, `docker`, `podman` не знайдено в PATH.
- `/usr/lib/postgresql`, `/opt/postgresql`, `/usr/local/pgsql` не існують.
- У `/var/lib/dpkg/status` немає встановлених пакунків `postgresql*` або `libpq*`. Відповідь `dpkg-query` про `postgresql-pgmp` має статус `unknown ok not-installed`, а не встановлений сервер.
- `/var/lib/apt/lists` порожній; `apt-cache policy postgresql postgresql-16 postgresql-client-16` не повернув metadata.
- `/var/cache/apt/archives` містить тільки `lock` і `partial`. Каталог `partial` недоступний для читання; його вміст не перевірено, тому повну відсутність будь-якого кешованого фрагмента там не стверджую.
- `/root/.cache/pip` і `/root/.cache/uv` не існують. `pip cache list postgres` і `pip cache list pgserver` повідомили `No locally built wheels cached`.
- Пошук назв `postgres/initdb/pg_ctl/psql/pg_config`, postgres `.deb/.whl`, `pgserver`, `libpq`, `psycopg` у `/opt/codex` із `--hidden --no-ignore` не знайшов збігів. Це перевірка доступних назв файлів, а не всіх можливих архівів невідомого формату. `/opt/codex/cache` містить кеші Sites npm/pnpm.
- У поточному основному Python не знайдено модулів `psycopg`, `psycopg2`, `pgserver`, `pglite`, `embedded_postgres`, `testing.postgresql`.

У перевірених доступних місцях готовий PostgreSQL runtime або відомий offline пакунок не знайдено. Це не прогноз неможливості встановлення чи запуску CI; такий запуск не виконувався.
