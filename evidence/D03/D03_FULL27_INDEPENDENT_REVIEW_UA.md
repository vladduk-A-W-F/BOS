# D03 · незалежний огляд документації та full27

**Погоджено локальний checkpoint документації D03 0.2.16-dev. Нових локальних регресій у фактичному full27 не виявлено.** Повний результат — exit 1, complete=false; це не готовність MVP, клієнтського onboarding, браузера або CI. F04 першого адміністратора залишається відкритим продуктовим питанням.

Огляд 12.09.2026 виконано read-only: документи, manifests, записані JSON/logs та SHA файлів. Нових тестів, парсера, рендеру PDF, Django/API, серверів, браузера, БД/media або конфігурацій установок не запускали й не відкривали. Canonical не редагувався. Власне повторне обчислення fingerprint застосунку не виконувалось; його provenance звірено за runner evidence.

## Документація: точний склад і завершені докази

Перевірено SOURCE_MANIFEST.json SHA **5ccd5e214efed0a0b0ccbc50737a9d7ac3117ab4900afe974c1d63578c312211**, рівно **22 файли**. Їхні фактичні canonical SHA та всі base SHA проти C03 commit **ab39229831c93095214b16ce542aaa974b26adf1** збігаються. Карта файлів у INTEGRATION_SHA256.json буквально та сама. Попередній final source review SHA **58f27a91c62aace8eaf4bd7b42f7f9c8703089a1ec3171fd600d5d8eb9271777** прочитано; перевірені ролі, команди, числові приклади, мінімальна заміна одного UI абзацу та версії не підмінені іншими файлами.

Повторно прочитано рольову інструкцію, 30-хвилинний сценарій, ручний тривалютний приклад та явний F04 у SERVER_INSTALL. Вони розрізняють навчальну й робочу установку; права User/групи й Employee; прогноз/погодження/первісну квитанцію; факт складу й очікування; гроші в журналі та оплати рахунків; невідомий результат і повтор того самого наміру. Банківські перекази, автоматичне надсилання та зовнішня модель не заявлені підключеними.

| Доказ D03 | Що фактично доведено |
|---|---|
| D03_DOCS_BEFORE → DOCS_AFTER | Ті самі 15 названих статичних умов: 1/15 → 15/15. Final complete=true; SHA усіх зазначених документів збігаються. Це не 15 runtime/browser тестів |
| D03_CSV_ACTUAL.json | Actual чистий parser: 3 вхідні рядки, EUR17.39 / USD123.45 / UAH9801.07 окремо; порожні counterparty/invoice refs. Без Django setup, БД, API або проведення грошей |
| ROLES_PDF_QA.json | Root QA зафіксував 3 сторінки, по одній на роль, читабельність без обрізання. PDF у canonical має точний QA SHA e87c6f44737de19fd5fa618554317f5da0c129c5a70825f983bdd9747d558a01. Reviewer звірив походження/байти, не виконував власний візуальний огляд |
| Попередні pending links | Усі 4 цілі тепер існують: C03 RESULT, D03 RESULT, D03_OPERATOR_BOOTSTRAP та history/TEST_REPORT |
| Історичний TEST_REPORT | Збережено точні старі байти SHA821af2f05a63d5ce1438440840fe008922a79c76523b87c98553f3bcba97bf38; старі твердження відокремлені від сучасної інструкції |

ROLE_GUIDE правильно називає PDF коротким витягом; спільні правила та приклади збережені у Markdown. Ручний CSV не змішується зі стандартним SO-101 або однорядковим E2E. Статична документація не стверджує, що 30-хвилинний показ уже проведено клієнту.

F04 виправлено лише як правдиве пояснення: provision не створює першого технічного адміністратора; підтриманого operator CLI для запуску createsuperuser/link_bos_user з перевіреною приватною конфігурацією ще немає. Неперевірений bootstrap не запропоновано як готову команду. Product gap і погоджений backlog після блоку 3 збережені.

## Full27: джерело та фактичні журнали

| Об’єкт | Перевірений SHA-256 |
|---|---|
| verify-1/report.json | 1a195f8a06ad5f49d19f04a65d7b06038391b92f8237ef505bca10aa0d8e5649 |
| AFTER_FULL27.json | e0a9338a838091cbba259ae642fd9cc31adfc9aa50044833b9f8fb3517af624d |
| PROCESS_EXIT.json | cb7003ab03781a5e5cb5a57f05031b708e4647b11d268f7aa6afe9bdb2f4667a |
| verify-1/gate-06-actual.json | e30340539de6dce336097db1ba8411bc341ba0f190d6fe25a5b9cb34b58a398b |

Source **833498c2aad1f0f2262fd74c664e315b874438b2d990bb425ad804d68ca7bac9** однаковий у BEFORE, integration, report, raw E2E та AFTER before/after. PROCESS_EXIT фіксує реальне завершення exec45589 з exit1; suite=full, Linux/Python3.12.14, фактичний SQLite3.53.1. Дві recorded source DB SHA до/після рівні; report source_database_count=2 та unchanged=true. Ці файли БД повторно не читались.

| Перевірка | Зіставлений raw результат |
|---|---|
| Старі функції й launcher | 22+49+48+32 = 151 та окремі 5, exact expected, exit0 |
| Django | Found571, Ran571 за339.894s, OK |
| Інваріанти | Усі п’ять по1000, complete=true; JSON буквально відповідає AFTER |
| Права | 9432/9432 HTTP +9 redirects, failures=[]; 57 discovered/executed, без skips; усі12 C03 controls passed, 130 їхніх HTTP; старі C01 controls збережені |
| Одночасність | 109 discovered/started/finished/succeeded; 116 required/observed/unique records, без missing/duplicates; 35 required/actual actions; 3 held records; source maps незмінні |
| Наскрізний процес | Повний raw JSON збережений, його SHA дорівнює gate6 stdout; 821 check entry, 42 confirm HTTP, 14 intents, complete=true, protected source before/after рівні |
| Native restore | 18 case objects, усі passed; exact56 таблиць і4 private files; чистий restore та наступний restored HTTPS перевірені окремими cases; statement replay без нового бізнес-ефекту |
| Серверна установка | 31 case, один known failure: 13MiB ConnectionResetError, status=null, documents_and_private_bytes_unchanged=true; private_canaries_absent=true для29 log files |

Повний report містить **рівно ID1–11**. SQLite підперевірки не підміняють PG: 1/2/3/5/6 та Windows11 загалом НЕ ЗАПУЩЕНО; 4/7 ПРОЙДЕНО; 8 ПОМИЛКА; 9/10 НЕ РЕАЛІЗОВАНО. CI pipeline/job/commit=null. Це ті самі відомі відкриті умови, а не нові D03 runtime регресії.

## Межі рішення

Погоджено фіксацію D03 як локально перевірених інструкцій/артефактів і мінімального пояснювального UI тексту. Результати не є виконаним клієнтським навчанням, browser acceptance, першим server login або готовим пілотом. Повна незалежна оцінка готовності викладена окремо у D04_INDEPENDENT_READINESS_UA.md.

На момент читання evidence/D03/RESULT_UA.md ще містив історичне «verify №27 запускаються». Root повідомлено оновити цей підсумковий статус перед commit за вже наявними AFTER/PROCESS_EXIT, без зміни frozen product. Це залишок оформлення результатів, не розбіжність raw доказів і не підстава повторювати full27. Нових необов’язкових запусків для цього scoped consensus не потрібно.
