# B01 — фінальний незалежний огляд прийнятих меж

12.09.2026. Переглядач: `/root/a09_server_review`. Канонічний звіт: `evidence/B01/verify-2/report.json`, suite=full, Linux / Python 3.12.14. **У перевірених локальних межах B01 нових регресій не виявлено; блокувальних зауважень до B01 checkpoint немає.** Прийняття стосується зв’язку пропозиції → закупівлі, збереження джерел та перевіреної сумісності. Це не прийняття всієї BoS як MVP, не підтвердження всіх 11 gates і не фактичне браузерне приймання.

Код, БД, тести та evidence checkout не змінював. Повторні прогони, boundary probes, міграції та сервери не запускав; читав наявні звіти/журнали й перерахував лише hashes вихідних файлів.

## Точна відповідність коду

Повторний read-only розрахунок за алгоритмом `scripts.verify.source_digest` охопив 291 файл і дав **`762576437f9a93ee3fb900dea2237fded7cc3a1b7591b40810557f3abfce495d`**, точно як full21. Це hash складу verifier; окремий code-only install package використовує інший склад файлів і закономірно має інший hash.

- Усі **13/13** канонічних файлів B01 збігаються з раніше незалежно перевіреним frozen manifest `8da3ff8ad0b27329bc9f5fa1b852ca728840c85a0a72b535c0a8bd10b902a59c`.
- Обидва виправлення сумісності збігаються з перевіреним manifest `8f263abe206fd557e9bfaa7be7be31bba5fd01401c3c9b625fc8e1004cbc344c`: transfer fixture `cb85fd0358618abaec10d0d89746a1306ca3dac761aa21545040f027659609df`, historical A08 regression `0212400de39aad5bf9219d8d8ef895bf580d953df6975df8d12f78869594472f`.
- Канонічний frontend `943ed8347c1f0fc3248c5d0483d3a3d46c9d9ad605232b8fd3d278c85325798b` точно відповідає фінальному source review в `tmp/B01_UI_REVIEW_UA.md`. Попередня перевірка generated assets/Babel залишається source/build доказом; візуальна поведінка браузера цим не доведена.

Чинними залишаються попередні незалежні `tmp/B01_BACKEND_REVIEW_UA.md`, `tmp/B01_UI_REVIEW_UA.md` та `tmp/B01_TRANSFER_FIXTURE_REVIEW_UA.md`. Не переінтерпретую їх як нові runtime прогони.

## Що підтвердив фактичний full21

| Перевірка | Прочитаний результат і межа |
|---|---|
| SQLite migrations | Порожня синтетична база, returncode=0. PostgreSQL не запускався. |
| Старий функціональний контракт | **22 + 49 + 48 + 32 = 151**, окремо **5 launcher**, кожна кількість дорівнює старому expected, engine_verified=true. |
| Django regression suite | **460 tests**, 190.246 с, OK / returncode=0. Попередні fixture-помилки full20 у цьому прогоні не повторилися. |
| Інваріанти, SQLite | П’ять інваріантів по **1000** прогонів: рухи, невід’ємний склад, одна зарплатна витрата, повтор proposal, доступ ролей; complete=true. |
| Права | Gate 4 complete=true, **8460** cases, failures=[], і додатковий журнал **57 tests OK**. Новий B01 scope доповнює старий контроль доступу, не замінює його. |
| Конкурентність, SQLite | Gate 5 complete=true: **84** required/discovered/started/finished/succeeded, 0 failures/errors/skips; **26** ERP actions required=actual. Це локальний SQLite доказ, не PostgreSQL. |
| Повний перенос і A08 | Фактичний `BOS_A07_TRANSFER`: 45 таблиць, точні окремі EUR/USD/UAH totals, receipt_equal=true, source_unchanged=true, наступні ID 90002/90003. Дев’ять A08 cases green; historical highwater показує 400001/500001 → новий Document 400002 без створення/стирання B01 source fields. |
| Native backup / clean restore | Gate 7 **10/10**, complete=true, версія 0.2.11-dev. Реальні own TLS процеси, quiescence, native capture, 45 таблиць / 2 приватні файли, рівний DB SHA до наступних HTTP writes, незмінний backup, новий installation UUID/cookie namespace, restored login і точні document bytes, own clean stop. Це same-N restore, не upgrade/rollback. |
| Установка / HTTP | Gate 8 **30/31**; єдиний false — вже відомий A09 oversized request. Інші перевірки TLS/cookies/proxy/health/login/private files/duplicate/restart/logging пройшли в межах чинного набору. |

Звіт декларує два вихідні DB-файли незмінними (`source_databases_unchanged=true`). Сам переглядач ці бази не відкривав. Установка лишається `application_provisioned=true`, `complete=false`, exit_code=2 до приймання всіх необхідних умов.

## Незмінні відкриті критерії

Full21 чесно містить **`complete=false`**. Усі 11 критеріїв збережено:

| Gate | Сукупний статус full21 |
|---|---|
| 1, 2, 3, 5 | НЕ ЗАПУЩЕНО в цілому: SQLite частини green, потрібен фактичний ізольований PostgreSQL. |
| 4 | ПРОЙДЕНО у зазначених локальних межах. |
| 6 | НЕ РЕАЛІЗОВАНО: наскрізний `scripts/e2e_scenario.py`. |
| 7 | ПРОЙДЕНО: фактичний same-N backup/clean restore. |
| 8 | ПОМИЛКА: незакритий A09 13 MiB oracle. |
| 9 | НЕ РЕАЛІЗОВАНО: `scripts/check_upgrade.py`, N→N+1 і справжній rollback. |
| 10 | НЕ РЕАЛІЗОВАНО: `scripts/check_ui.py`, реальні viewport/zoom/keyboard/network сценарії. |
| 11 | НЕ ЗАПУЩЕНО: реальний Windows / Python 3.12 runner. |

CI pipeline_id/job_url/commit — null. Дані джерела, source review, HTML shell 200 та Babel не замінюють фактичні CI/Windows/UI докази.

**Gate 8 конкретно:** `oversized_request_413_no_partial_document` має passed=false, status=null, error_type=ConnectionResetError; `documents_and_private_bytes_unchanged=true`. Це доказ відсутності часткових DB/file writes у цій спробі, але не доведена клієнтом HTTP 413. Збережено відомий блокер A09, не додано нових експериментів і не змінено oracle. `private_canaries_absent=true`, 29 перевірених log files — тільки межа наявних canary перевірок, не універсальна гарантія відсутності будь-якого витоку.

## Прийнятий бізнес-результат B01

Попередній source review та поточна точна інтеграція зберігають такі межі: нова закупівля має явне погоджене джерело Quote або причину direct; предмет, валюта, кількість, актуальні документи та права перевіряються сервером під ERP mutex; розподіл 6+4 законний, перевищення потреби відхиляється; первісний snapshot умов і доказові документи зберігаються. Поточна видимість джерел та історичних snapshot перевіряється окремо; повтор підтвердження не створює другого PO. Міграція залишає старі null джерела без вигаданого backfill, зберігає high-water і відмовляє втратити populated source під час reverse до DDL.

Атестація supplier_confirmation лишається явною заявою відповідального, не зовнішнім підтвердженням постачальника. UI зв’язок і картка джерел погоджені за кодом; натискання, layout, race/keyboard/browser сценарії чекають gate10.

**Scoped consensus:** B01 можна фіксувати окремим commit із цими доказами та відкритими обмеженнями. Повний MVP, A09 загалом та activation/upgrade/rollback цим висновком не приймаються.

## SHA-256 прочитаних evidence

Шляхи таблиці — від `evidence/B01/verify-2/`.

| Артефакт | SHA-256 |
|---|---|
| `report.json` | `946af655186120a9242b768773425acf618b2453ea651c79d3a0895ec0c20445` |
| `sqlite-django-tests.log` | `9c6f8e1a2286f16e8ecd90da7cf187f48d05e3b5dfab42912ba21de49786f5fe` |
| `gate-03-sqlite.log` | `e5a5054b4aeda8ab297f86856abefcc740b9388bd913edcfd5f1855d4e0181ac` |
| `gate-04-sqlite.log` | `d9491e633f4c7d9a2fe86c6de05a49d6c25352ef56722efbd017f7a507639129` |
| `gate-05-sqlite.log` | `692cddbdb24f7c6fab3de61decd95e8e239dd58ffe768f33254f7225445eddeb` |
| `gate-07-sqlite.log` | `d7f87b1921b5030a6808528ac4ef6a6dfa5b06ce78ce1b810daf3484461ab708` |
| `gate-08-sqlite.log` | `de82a3277849557cd7b45de4b4686c5a36cbab1e29ff6d9f161605e9307b041f` |
