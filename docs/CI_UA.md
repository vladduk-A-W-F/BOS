# BoS · перевірки та CI

Master v2.1. Повний критерій незмінний: 11 пунктів. `verify` повертає 0 лише коли всі обов’язкові перевірки вибраного набору пройдено; лише набір `full` є повним прийманням. Компонентні набори `sqlite`, `postgres`, `e2e`, `ui`, `windows` не є релізним прийманням.

## Поточний стан

Каркас створено й запущено локально. Зовнішній конвеєр **НЕ ЗАПУЩЕНО: у BoS немає remote, доступ до репозиторію GitLab не встановлений**. Доступний GitHub показує тільки інший проєкт `vladduk-A-W-F/FOS`; BoS туди не завантажувався. `.gitlab-ci.yml` підготовлено для заявленої користувачем платформи GitLab. Непідтвердженої URL прогону немає. Після надання доступу до фактичного репозиторію файл конвеєра треба запустити й додати справжні URL та вивід у `evidence/0.0/`.

Відсутні `scripts/check_invariants.py`, `check_access.py`, `check_concurrency.py`, `e2e_scenario.py`, `check_restore.py`, `check_install.py`, `check_upgrade.py`, `check_ui.py` позначаються **НЕ РЕАЛІЗОВАНО**, а не успіхом. Відсутній PostgreSQL чи Windows-артефакт — **НЕ ЗАПУЩЕНО**. Виняток перетворюється лише на червоний результат; він не поглинається як успіх.

## Запуск

Потрібні Python 3.12 та залежності `requirements-ci.txt`. Для повного локального прогону з ізольованим PostgreSQL:

```bash
python3 -m pip install -r requirements-ci.txt
docker compose up -d --wait postgres
BOS_PG_DISPOSABLE=1 BOS_PGHOST=127.0.0.1 BOS_PGPORT=55432 BOS_PGUSER=bos_ci BOS_PGPASSWORD=bos_synthetic_ci_only bash scripts/verify.sh --suite full
```

Пароль у цьому прикладі стосується виключно одноразового синтетичного контейнера. У ньому немає робочих даних; його стан зберігається в tmpfs. Це не конфігурація сервера BoS. Windows-обгортка: `scripts/verify.ps1`; вона повертає код дочірнього Python-процесу. Запуск із Python `-O` або `PYTHONOPTIMIZE` відхиляється.

Перелік критеріїв: `python scripts/verify.py --list`. Результати й повний stdout/stderr кожної перевірки зберігаються поряд із JSON-звітом. Звіт містить ОС, Python, SHA джерел, обов’язкові підперевірки та фактичні коди завершення. Кожен функціональний сценарій перевіряє справжній `connection.vendor` і версію сервера; автоматичного переходу PostgreSQL → SQLite немає.

## Набори конвеєра

| Job | Реальне призначення |
|---|---|
| `tests-sqlite` | Міграції, наявні та нові тести, інваріанти, конкурентність на SQLite. |
| `tests-postgres` | Те саме на сервіс-контейнері `postgres:16`. |
| `e2e` | Повний процес і еталон на обох СУБД після реалізації сценарію. |
| `ui-playwright` | Встановлює headless Chromium; відсутній сценарій UI дає червоний статус. |
| `tests-windows` | Справжня Windows/Python 3.12, пункти 1–3 і 6 на обох СУБД. Зараз manual. |
| `verify-full` | Усі 11 критеріїв на `release/*` або тегу; Windows-звіт обов’язковий і має збігатися за SHA/поточним pipeline. |

`tests-windows` має `allow_failure: false`; залежність `verify-full` не є optional. Невиконаний Windows job не дозволяє назвати конвеєр зеленим. `artifacts: when: always` зберігає вивід червоних запусків. Синтаксис YAML перевірено локальним парсером; це не перевірка GitLab CI Lint і не запуск GitLab.

## Незмінність перевірок і даних

У чотирьох старих сценаріях змінено тільки початкове налаштування тестової БД і запис її фактичного типу. Усі тіла перевірок після `django.setup()` збережено без змін, що зафіксовано SHA у `evidence/0.0/ORIGINAL_CHECKS.json`. Усі п’ять перевірок launcher залишено повністю незмінними. Їхні наявні mocks не є доказом чистої Windows-установки.

`verify` створює тимчасову копію джерел без робочих баз, media, секретів, evidence та віртуальних середовищ. У ній створюється нова синтетична `db.sqlite3` як контрольний файл для старих SHA-перевірок. Кожен сценарій отримує власну нову SQLite або PostgreSQL-базу й тимчасовий media-каталог. DROP виконується тільки для випадкової PostgreSQL-бази, яку створив цей конкретний запуск. Реальна `db.sqlite3` не використовується як fixture; її звірка 0.5 залишається локальною.

## Джерела конфігурації

- [GitLab: PostgreSQL service](https://docs.gitlab.com/ci/services/postgres/).
- [GitLab: manual jobs та allow_failure](https://docs.gitlab.com/ci/jobs/job_control/).
- [GitLab: YAML, needs та artifacts](https://docs.gitlab.com/ci/yaml/).
- [Playwright: запуск у CI](https://playwright.dev/python/docs/ci).
