# BoS · GitHub CI

P04, 17.09.2026. Конфігурацію підготовлено для приватного `vladduk-A-W-F/BOS`. Вона ще не виконувалася. Поточна кодова база перенесена в `setup/bos-transfer-p02`; старий `.gitlab-ci.yml` збережений як історичний файл. Активна конфігурація — `.github/workflows/verify.yml`.

Повне приймання має ті самі 11 критеріїв `scripts/verify.py`. Компонентний зелений job не означає готовності MVP. Не виконана або не реалізована перевірка не є PASS. У P04 не змінено застосунок, verifier, його suites, оракули, залежності або історичні результати.

## Як запускати після дозволу на відповідний пункт

Workflow має тільки `workflow_dispatch` з вибором одного набору. Значення за замовчуванням — `sqlite`; `full` явно запускає всі п’ять компонентів та фінальний job. Push і PR не запускають CI. Ручний запуск має бути на точній погодженій гілці/commit.

| Вибір | Середовище | Незмінна команда verifier | Картка |
|---|---|---|---|
| sqlite | Ubuntu 24.04 / Python 3.12 / нові SQLite | `--suite sqlite` | P05 |
| postgres | Ubuntu / Python 3.12 / власний PostgreSQL 16 | `--suite postgres` | P06 |
| e2e | Ubuntu / Python 3.12 / SQLite та PG16 | `--suite e2e` | P06 / узгоджений наскрізний прогін |
| windows | Windows 2025 / Python 3.12 / SQLite та native PG16 | `--suite windows` | P07 |
| ui | Ubuntu / Python 3.12 / дозволений Chromium | `--suite ui` | P09 |
| full | Усі п’ять jobs плюс справжній `--suite full` | усі 11 критеріїв | P19 після передумов |

**Перша реєстрація:** GitHub обробляє `workflow_dispatch`, коли workflow є в default branch. Зараз `main` має лише README. У P04 `main` не змінюється; перед P05 потрібно окремо довести до завершення реєстрацію перевіреного workflow у default branch у межах дозволеного перенесення. Не видавати наявність YAML у setup-гілці за вже доступну кнопку запуску. [GitHub: workflow_dispatch](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch).

Не купувати runner, хвилини, сервер або інші ресурси автоматично. Відмова квоти/Actions/прав або відсутній runner фіксується як НЕ ЗАПУЩЕНО. P04 не розпочинає P05–P09 і не є серверним розгортанням.

## Дані та середовища

Тести отримують лише нові синтетичні бази та media. Чинний verifier створює окрему копію джерел без робочих БД, `.env`, media, evidence та віртуальних середовищ. Для кожного сценарію він створює власну БД; видаляє тільки випадкову PostgreSQL-базу, яку створив сам. Вихідні SQLite-файли перевіряються на незмінність.

Linux PostgreSQL jobs мають окремі `postgres:16` service containers, тимчасове сховище та динамічний порт. Перед verifier helper запитує фактичні `server_version_num` і `version()`. Інша major version дає помилку; заміни PostgreSQL на SQLite немає. `bos_synthetic_ci_only` — значення лише для одноразового тестового сервера без робочих даних.

Windows не використовує Linux service container: GitHub підтримує service containers на Linux runner. [GitHub: PostgreSQL service containers](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers).

`.github/ci/windows-pg16.ps1` шукає native binaries через repository variable `BOS_PG16_BIN` або `C:\Program Files\PostgreSQL\16\bin`. Він перевіряє справжню `postgres --version`, створює власний каталог у `RUNNER_TEMP`, запускає `initdb` / `pg_ctl` на loopback 55432 та зупиняє лише свій кластер з відповідним run/attempt. Системний сервіс не змінюється. Парольний файл видаляється після initdb.

**Передумова Windows відкрита:** поточний образ Windows 2025 описує PostgreSQL 17.11, тому наявність PG16 не припускається. Відсутність native PG16 створює `pg-start-failure.json`, exit 1 і NOT_RUN-квитанцію. У P07 потрібен справді дозволений runner із PG16 або окремо перевірене його встановлення. P04 не встановлював PostgreSQL і не виконував PowerShell. [Офіційний склад Windows 2025](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md).

## Звіти й невдалі запуски

Кожен job працює поза checkout у `RUNNER_TEMP/bos-ci/<suite>`. Артефакт має назву `bos-<run_id>-<run_attempt>-<suite>`; строк зберігання 30 днів. Після помилки використовується `always()` та `if-no-files-found: error`. Якщо runner взагалі не стартував або примусово перерваний до upload, артефакту може не бути — це не успіх.

`.github/ci/evidence.py` викликає незмінний verifier, зберігає його справжній exit code, stdout/stderr і JSON. Окрема `ci-receipt.json` містить commit, runtime SHA, SHA всього `.github` (workflow, helpers і тести), repository, run ID, attempt, job key, справжній job URL з GitHub API, ОС/Python та фактичні версії БД. Вона містить SHA кожного файла доказів. Помилка встановлення залежностей/PG/браузера дає квитанцію `not_run`, а не вигаданий verifier report. Логи кроків встановлення також зберігає сам GitHub job; у квитанції є їхні outcomes.

GitHub metadata передається verifier через `CI_PIPELINE_ID=repository/run_id/attempt`, `CI_COMMIT_SHA`, `CI_JOB_URL`. Ідентифікатор job отримується API поточної спроби; `GITHUB_JOB` не підставляється замість числового ID у вигадану URL. Права: тільки `contents: read`, `actions: read`; checkout не зберігає credentials. Actions зафіксовані повними commit SHA.

Фінальний job перевіряє всі п’ять `needs` і завантажує артефакти тільки поточного run/attempt. Немає fallback до історичного `evidence/ci/windows/report.json`. Відсутній, змінений, застарілий, неповний артефакт; інший commit/source/config/run/attempt; неправильні ОС/Python/PG; ненульовий exit або skipped job блокують успіх. Далі потрібен реальний `--suite full`, а не підсумовування зелених підписів. Після зміни коду докази не переносяться на нову версію.

## Відкриті умови

1. `scripts/check_upgrade.py` відсутній. Gate 9 — НЕ РЕАЛІЗОВАНО. Історична відмова автоматичної перевірки щодо A10 чинна: helper додатково зупинить full, якщо з’явиться цей executable; P04 не дозволяє його виконання, повтор або делегування.
2. `scripts/check_ui.py` відсутній. Gate 10 — НЕ РЕАЛІЗОВАНО. Chromium встановлюватиметься тільки за наявності реального сценарію на дозволеному CI runner. Заблоковані локальні CDN/loopback маршрути не повторюються.
3. A09: ліміт цільових спроб вичерпано. У CI немає окремого 13 MiB job. Незмінний oracle залишається тільки в потрібному full; історичний full27 мав gate8 30/31.
4. **P04-F01:** старий `source_digest` сортує `Path` по-різному на Windows і Linux. Це підтверджено моделлю однакових 336 файлів, не запуском Windows. Непримінена мінімальна правка — `evidence/P04/PROPOSED_PATH_ORDER.patch`. Виправлення потребує окремої картки P10, red→green і нового приймання; до цього Windows/Linux SHA не збігаються й full залишається червоним. Helper не підміняє SHA.

## Що перевірено в P04

Локальні синтетичні тести перевіряють лише CI-квитанції, відмови та збереження exit code. YAML розібраний PyYAML; структура зіставлена з усіма 11 критеріями; Python helpers перевірені синтаксично. Окремий рецензент перевіряє точний diff. Це не GitHub server lint, PowerShell execution, Windows/PG/browser тест чи виконаний CI. Реальні запуски та їхні URL з’являться тільки у відповідних наступних картках.
