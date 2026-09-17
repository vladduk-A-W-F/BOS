# D03 · незалежний аудит фактів документації

Дата: 12.09.2026. Перевірена інтегрована C03, frontend SHA `78136013163756fa033e59726a1296dc8c0938850621cfc7b093ce1ea7c1886a`; parent повідомив про full26 на source `7be2d6ba`. Результат full26 тут не прогнозується.

Метод: читання чинних документів, JSX, конфігурації, команд запуску й синтетичних seed-файлів; SHA та перевірка наявності локальних Markdown-посилань. Застосунок, тести, браузер і API не запускалися. Бази, приватні документи та backup не читалися. Canonical не змінено. Це аудит інструкцій, а не приймання інтерфейсу чи сервера.

Орієнтир: master v2.1, §2 — усі 11 критеріїв; §3 — PROGRESS є джерелом статусу; §5 — D03 інструкції ролям, D04 після повного verify; §9–10 — незапущене не називати перевіреним. ROLE_GUIDE пише окремо c03_statement_plan; цей звіт не дублює його.

## Конкретні виправлення перед передаванням інструкцій

| ID | Точне місце | Розбіжність і підстава в коді | Мінімальна рекомендація |
|---|---|---|---|
| F01 · навігація | `/workspace/sites/bos-original-refined/README_UA.md:76`; `/workspace/sites/bos-original-refined/docs/STATEMENTS_UA.md:9` | Документи ведуть у «Фінанси → Банк», але NAV має `bank` з видимим підписом **«Операції»**: `/workspace/sites/bos-original-refined/frontend/boss_app_source.html:289`. Bank має вкладки журналу/виписок. | Для CEO вказати **Фінанси → Операції → Виписки**. Внутрішній route ID не перейменовувати. |
| F02 · відновлення документів | `/workspace/sites/bos-original-refined/docs/DEMO_AND_IMPORT_UA.md:26` | Описано повернення тільки SQLite-файла. Launcher справді копіює лише БД (`scripts/start_local.py:104–106`), але нові Document зберігають `content=b''`, `original_file=receipt.name` (`operations/views.py:150–151`), а локальний MEDIA_ROOT — `rehearsal-media` (`demo_settings.py:16`). Одного DB-backup недостатньо для відновлення відсутніх оригіналів на чистій установці. | Назвати launcher-копію **резервною копією лише БД**. Для повного відновлення явно вимагати узгоджені БД і відповідне приватне сховище; окремо послатися на A10 для керованої серверної установки. Не подавати A10 як перевірений автоматичний local-demo restore. |
| F03 · команди перевірки чистого архіву | `/workspace/sites/bos-original-refined/docs/TEST_REPORT_UA.md:46–59` | Перелік окремих команд не є поточним відтворюваним прийманням. `scripts/check_workspace.py:24` та `scripts/check_erp.py:22` безумовно читають кореневу `db.sqlite3`, якої немає в описаному README чистому пакеті. Без BOS_TEST_MEDIA bootstrap залишає спільний MEDIA_ROOT (`scripts/check_support.py:36–39`). `scripts/evaluate_scenarios.py:14–20` використовує старий bootstrap, а `:54` перезаписує історичний JSON-звіт. | Позначити блок як історичні команди 10.09; для актуальної перевірки посилатися на `docs/CI_UA.md` і `scripts/verify.sh` / `scripts/verify.ps1`. Саме `verify.py:230–238` створює ізольовану копію й синтетичний контрольний файл, `:89` — окремий media. Не пропонувати підкладати реальну БД заради запуску старого скрипту. Source-висновок; ці команди повторно не виконувалися. |
| F04 · перший серверний вхід | `/workspace/sites/bos-original-refined/docs/SERVER_INSTALL_UA.md:54–58`; `/workspace/sites/bos-original-refined/docs/ACCESS_UA.md:18` | Після порожньої установки пропонується вхід і створення акаунтів технічним адміністратором, але немає кроку створення самого першого адміністратора, завантаження **конфігурації конкретної установки**, а також точного виклику зв’язування User/Employee. Installer лише мігрує та збирає статику (`scripts/provision_runtime.py:134–153`). Конфігурація і runtime Python окремі (`scripts/lifecycle_server.py:90–94`, `scripts/install_server.py:223–235`). | Додати вузьку операторську інструкцію bootstrap з приватною конфігурацією цільової установки, її Python/release, інтерактивним паролем і наступним `link_bos_user --user-id … --employee-id …`. Не радити звичайний `manage.py` без профілю й не вигадувати готовий CLI, якого немає. Це прогалина інструкції, не доказ зламаної автентифікації. |
| F05 · контрольні суми показу | `/workspace/sites/bos-original-refined/docs/DEMO_AND_IMPORT_UA.md:11` | У стандартному свіжому START_DEMO запускаються всі три seed-команди (`scripts/start_local.py:108–111`). Початкові I01–I03 дають 20 000 EUR відкрито (`operations/seed/invoices.json:2–27`), а завершені SO-090/091/092 додають ще 1 600 EUR (`erp/management/commands/seed_bos_workspace.py:23–31`). Асистент на «Що потребує уваги?» підсумовує **всі** Invoice (`operations/service.py:24–30`, `operations/views.py:240–244`). Отже після стандартного чистого запуску очікується **21 600 EUR**, а не 20 000; 5 000 прострочених залишаються. 24 000 береться з навчального Configuration.cash, не з C03 журналу. | Або явно назвати старий operations-only зріз, або описати стандартний повний seed із 21 600 EUR та окремим походженням 24 000. Це виведено з коду/синтетичних fixtures, не заявлено як новий фактичний UI-прогін. |
| F06 · старі межі доручень | `/workspace/sites/bos-original-refined/docs/TEST_REPORT_UA.md:25`; `/workspace/sites/bos-original-refined/docs/NEXT_STEPS_UA.md:22` | «Зміна терміну не реалізована», додавання FK/відповідального/API diff як майбутня робота вже не відповідають C01. `tasks/commands.py:19–20, 29, 43–44, 86–112` приймає assignee/deadline/order/result/reason і створює структуровані зміни; ControlledTaskDialog та історія є в чинному JSX. | Старі результати зберегти з датою й явним historical label; поточний стан перенаправити до `TASKS_UA.md` / ROLE_GUIDE / PROGRESS. Не переписувати старий JSON так, ніби його заново прогнали. |
| F07 · облікові записи як нібито відсутня функція | `/workspace/sites/bos-original-refined/docs/MVP_GUIDE_UA.md:60`; `/workspace/sites/bos-original-refined/docs/NEXT_STEPS_UA.md:3,33`; також видимий текст `/workspace/sites/bos-original-refined/frontend/boss_app_source.html:4198` | Тексти кажуть, що серверні акаунти ще не підключені або потрібен «справжній вхід». Чинний сервер має IsAuthenticated і session/cookie-профіль (`server_settings.py:31–45`); сам README:44 вже розрізняє demo та робочий вхід. | Написати: локальне демо має навчальні акаунти, робочий режим — автентифікацію й призначені права; повне серверне/міжплатформне приймання залишається відкритим. Правку видимого тексту BoSProductGuide передати root як окрему погоджену текстову зміну; тут JSX не редагувався. |
| F08 · кому доступний наскрізний показ | `/workspace/sites/bos-original-refined/docs/MVP_GUIDE_UA.md:14–40`; `/workspace/sites/bos-original-refined/docs/ERP_GUIDE_UA.md:40–53`; `/workspace/sites/bos-original-refined/README_UA.md:24–32` | Фінансові KPI/оплата показані без явної передумови ролі. Payment/costs — CEO (`frontend/boss_app_source.html:221,227`). У manager батьківське меню називається «Партнери й закупівлі» (`:235`), «Операції» — лише metadata-журнал (`:4372`), observer не має цього маршруту (`:229`). | На початку повного демо вказати роль **Керівник**, потрібні дозволи документів/завантаження, свіжий синтетичний набір. Для manager/observer дати посилання на ROLE_GUIDE; не обіцяти однакові меню, суми й кнопки для всіх. |

## Менші, але конкретні неточності

1. `/workspace/sites/bos-original-refined/README_UA.md:44` поширює фразу «доступний лише на вашому комп’ютері / ця збірка не призначена…» на весь пакет, тоді як `:63–65` описує окремий серверний профіль. Мінімум: звузити перше твердження до **START_DEMO / локального launcher**. Загальну виробничу готовність не додавати.
2. `/workspace/sites/bos-original-refined/docs/TEST_REPORT_UA.md:1,7–17,42` — історичний звіт 10.09.2026; 151+5, причину тодішнього browser failure й 26 старих сценаріїв не подавати як повне поточне приймання. Достатньо помітного історичного статусу та посилання на PROGRESS. Те саме для старих browser/серверних майбутніх дій у `docs/NEXT_STEPS_UA.md:19,26,33–39`; C02/черги/локальна LLM не входять у поточний master (§5 блок4, §9).
3. `/workspace/sites/bos-original-refined/docs/BACKUP_RESTORE_UA.md:7` каже «усі 45 таблиць» без прив’язки до A10 початкової версії. Чинний C03 oracle в `scripts/check_restore.py:192–194` вимагає 56. Назвати 45 історичним checkpoint, а актуальний обсяг брати з manifest конкретної копії. Старі успішні 10/10 або 151+5+442 у `:34,38` не підміняти прогнозом full26.
4. `/workspace/sites/bos-original-refined/docs/ACCESS_UA.md:20` досі каже, що процес A08 «завершується»; поточний PROGRESS описує завершену локальну частину. Вказати чинний локальний scope A08 і окремо відкриті платформні перевірки.
5. `/workspace/sites/bos-original-refined/docs/PROGRESS_UA.md:56` називає точкою поновлення C01, хоча `:44` уже C03/full26; `:60` містить старе пояснення A07 щодо критерію6. Оновити **root після завершення поточного кроку**, зберігши історичні результати й причини блокування. `/workspace/sites/bos-original-refined/docs/ERP_GUIDE_UA.md:102` і `docs/STATEMENTS_UA.md:5` також оновлювати лише відповідно до фактичного підсумку інтегрованої збірки.

## Що не є помилкою та не потребує переписування

- 21 операція SO-101 у README:28 і TEST_REPORT:9 — окремий попередній workspace-сценарій. Це не суперечить 14 діям / 42 confirm нового gate6 (`tests/e2e_expected.json:624–628`). Достатньо розрізнити назви й scope; числа не зрівнювати.
- Початкові 3640 / 2040 / 1600 EUR для SO-090/091/092 підтверджуються seed-кодом. Цикл повних 50 виробів у MVP_GUIDE та альтернативних 30 у ERP_GUIDE мають різні явно задані кількості; не об’єднувати еталони.
- README:20–22 відповідає launcher: стандартний виклик відкриває demo, `--check-only` не запускає сервер і не виконує міграції/seed (`start_local.py:97–99`). Node не потрібен для звичайного запуску з готовим app.js.
- 10 хвилин погодження ERP_GUIDE:20 відповідають `operations/service.py:104`. Повтор не є дозволом розкривати закриті джерела: поточні рольові правила зберігаються.
- SERVER_INSTALL правильно лишає A09 неприйнятою 30/31; BACKUP_RESTORE правильно не заявляє upgrade/rollback і загального A10. WINDOWS_RUNNER не видає manual job за фактичну Windows-перевірку. Не змінювати ці межі заради презентації.
- У 12 перевірених основних Markdown-документах усі явні локальні посилання формату `[текст](шлях)` ведуть до наявних файлів. Це перевірка файлових посилань, не HTTP і не зовнішніх URL.

## Рекомендований мінімальний D03 результат

Спершу виправити F01–F05, додати ROLE_GUIDE, позначити старі звіти історичними й замінити суперечливі межі F06–F08. У README залишити короткий вхід: запуск, роль, один демонстраційний процес, фактичні межі та посилання на актуальне приймання. Після full26 root впише тільки підтверджені результати. Нові функції, зміна ролей або перебудова UI для цього аудиту не потрібні.

## SHA прочитаних опорних файлів

| Файл від `/workspace/sites/bos-original-refined/` | SHA-256 |
|---|---|
| `README_UA.md` | `3c05780e5b48eaf7a8d0343d7c7080b1142c22937785ed6d5d55df7f2093db4b` |
| `docs/ERP_GUIDE_UA.md` | `796711efbabbbcf9f9a31d64d3aa420286b6edaa981ed5bb570708a2861eaba1` |
| `docs/TEST_REPORT_UA.md` | `821af2f05a63d5ce1438440840fe008922a79c76523b87c98553f3bcba97bf38` |
| `docs/MVP_GUIDE_UA.md` | `0e8fe3bf55cf0d782d8f31fc8f941208ea0f390169af72cd49780924b83b8b58` |
| `docs/STATEMENTS_UA.md` | `c31ee06b0efb25fb872f8fad7ebca7c9c0bb3808b72e442eb3618a4a17b1c9f4` |
| `docs/DEMO_AND_IMPORT_UA.md` | `20ebba2e5ba712dbb42887d5fc27112882a672b1484d6d41f316f0929bd5b1c9` |
| `docs/SERVER_INSTALL_UA.md` | `7c02e13510d0f087e84b98c78b405ee1663892ee6a137f81024ed878a1d140f5` |
| `docs/BACKUP_RESTORE_UA.md` | `353630d1d8c668fb0369ee9056a8470be3b7a2fada976f00eb3d92d7d7f4cf02` |
| `docs/WINDOWS_RUNNER_UA.md` | `255886dc0c68464c85bdbc86da5ab4714cbe0deea8d42c5b972eab04232c53ed` |
| `docs/CI_UA.md` | `48b82247d93654d1696d2e3639d94de878c51ffc1d5c9096adae4633320b2ac3` |
| `docs/NEXT_STEPS_UA.md` | `9c9a496a69489799d4553736a73b6de23c334f49321491ccc99c96f9a5c8cbc5` |
| `docs/ACCESS_UA.md` | `8ba3ada05775eb72693fa35321193356ff38ecd328e35cfe386380234eff7339` |
| `frontend/boss_app_source.html` | `78136013163756fa033e59726a1296dc8c0938850621cfc7b093ce1ea7c1886a` |
| `scripts/start_local.py` | `f821a0a93269989674d464b8a136c3cf3d978b305da6d770cb1d0c48a9fe3e80` |
| `scripts/check_support.py` | `7e16b2bfe82db850b90a96b531a0186d7a7d3e68563b867bbdcc6e0e6d9f59f4` |
| `operations/service.py` | `7628774ed3a76966d2e4ae42dcd714fcfe29a9b046a0bd52b83e0b3372135260` |
| `operations/views.py` | `2ca2e6ce48586ab953060816a66ab53d4d801bc176e5737b4ad09232a39190ea` |
| `tasks/commands.py` | `2c5ff841f303edb54ab4e35d75cf795f863985353db69a80b4ddf81f40f41550` |

Master v2.1: `/workspace/scratch/c7b51e996a9f/upload/BoS_MASTER_PROMPT (1).md`; SHA `4ab578d4ab1a6c959ed7aa791f09a7c8284c04df1d48b6a575671f53df7c4caf`.
