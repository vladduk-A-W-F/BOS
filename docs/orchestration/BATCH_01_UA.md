# BoS · пакет 01 · результати за модулями

20.09.2026. Режим BATCH_EXECUTION: власник дозволив паралельну реалізацію й самостійну перевірку. Перевірений runtime SHA256: `31c692c5f3113446452e8d15faf95c29b019f433550bf4d0658c4f0428e54d20`. CI-кандидат: `aecf8ee1f556b60f3fa34b66a001372e332d02ab`. Робота збережена в приватному [PR №1](https://github.com/vladduk-A-W-F/BOS/pull/1), draft до fix-гілки.

## Результат

Оркестрацію налаштовано; шість вузьких коригувальних карток інтегровано окремими комітами після незалежного review. SQLite: 24/24 інтегровані регресії; F06/SOURCE: 7/7 unit. PostgreSQL 16: **PASS_SCOPED**, [run 35503944302](https://github.com/vladduk-A-W-F/BOS/actions/runs/35503944302); 26 green methods складаються з 16 справжніх PG business/HTTP перевірок і 10 fake-connection guard regressions, виконаних у тому самому test stage; додатково 7 unit. Точний обсяг і результат кожного етапу — `evidence/batch01/PG16/SUMMARY.json` та первинні журнали.

Це адресні перевірки нових карток. **P06 BLOCKED; TECHNICAL_READY=false; PILOT_ALLOWED=false.** Причини F04/F05 не встановлені; повне приймання, actual E2E і production-запуск не виконані. Історичні P05 3/3 та A09/A10/A11 збережено.

| Модуль | Що зроблено | Доказ / межа |
|---|---|---|
| Оркестратор GPT/Codex | 9 ролей, максимум 4 паралельні субагенти, окремі копії, незалежний reviewer, послідовна інтеграція | TOML/черга/11 GATES перевірені статично. CLI відсутній; файл конфігурації не запускає службу |
| P10-003 / імпорт | Guard перевіряє справжній backend, видану test DB та живе з’єднання до запису fixture | 10 boundary tests + справжній import; evidence/P10-003. PostgreSQL — див. CI |
| PLAN-F03 / фінанси | Валідні invoice-коди у concurrency fixture; business assertions збережено | SQLite 5/5; PostgreSQL — див. CI |
| PLAN-N1 / вхідні дані | Raw max_length до write_lock для procurement request; ship raw100 + чинне stripped60 | Red/green збережено. Invoice validation уже існувала; не видається за нову правку |
| PLAN-F06 / CI evidence | Детальні E2E JSON усередині output; відмова при неповних/суперечливих доказах | 5 unit, у тому числі негативні fixtures. Actual E2E/archive цього процесу не перевірений |
| PLAN-SOURCE | Детермінований порядок відносних компонентів шляхів | 2 production-helper tests, Windows/POSIX path simulation; native Windows не запускався |
| PLAN-TIME | Зіставлено історичні timeout logs, 29 source hashes і 11 receipts | F04/F05 OPEN. Fixture fixes не оголошено лікуванням тайм-ауту |
| PLAN-N2 / конкурентність | Один ізольований SQLite probe: 24 SELECT на fingerprint; unrelated confirm B → 409 для A при незмінному графі A | 5.581 s, exit0, два справжні користувачі/CSRF. Не load/PG benchmark; механізм незмінний. ADR — пропозиція |
| PLAN-LINKS / зв’язки | Gap-map, джерела метрик, контракт одного order trace, scope доступів/URL catalogue | Нова GET-проєкція й секція inspector лише специфіковані; production allocation не вигадано |
| PLAN-UX | Brief для керівника, менеджера, спостерігача в чинному BoSHome/BoSInspector | Немає нової UI-реалізації чи browser PASS; карта Figma є, prototype pending |
| PLAN-GPT | Explanation-only контракт, source refs, Decimal-перевірки, відмови й 14 eval-сценаріїв | Зовнішній API off; mock/spec не є live-model eval |
| PLAN-PILOT | Паспорт процесу, baseline, формули метрик, звірка, людське приймання | Компанія/люди/дані ще не визначені, пілот не розпочато |

## Інтеграції та середовище

GitHub, Figma й Sites доступні. OpenAI Developers та Codex Security запропоновані, але їх установку має завершити власник у UI; без підтвердження вони не позначені підключеними. Інші сервіси не потрібні для цього пакета.
Python 3.12.14, Django 6.0.5, DRF 3.17.1, psycopg 3.3.6 встановлені в окремому venv. Локальний PostgreSQL недоступний через OS permissions; для адресної перевірки використано GitHub PG16 service. CLI runtime не перевірений.
Figma: https://www.figma.com/board/7j5K5Iw9TZOmPd3LHZgxso . Sites: https://bos-industrial-workspace.vladduk134.chatgpt.site — чинна приватна v1, backend не підтверджений; публікацій цим пакетом немає.

## GitHub і походження

База: `7d46dced3bcf06d44755cf53366c9e16bd465582`, історичний source `10d86748d682926a898d2d2dfecd43fd7f6962f6ed38602da7ae704e52aca154`.

| Картка | Коміт |
|---|---|
| P10-003 | a393a881f203557bc0951b9e6368818127b9430f |
| PLAN-F03 | f079902166e14fce5dfcd4c2273472fec507437b |
| PLAN-N1-REQUEST | 6ba28309f98d8b409874642a0eb703ab46d96002 |
| PLAN-F06 | fbceef29d005a720b036a434484d43c98b5c09d4 |
| PLAN-N1-SHIP | f2fa1e91e518a69cf729f1acedeac426dddd5009 |
| PLAN-SOURCE | 73e9905a86fc61cde4be2337ef14fb0f6a134192 |
| PLAN-LINKS | 448681aadd849f7648cf40ef7f1e3e38cbe192b1 |
| PLAN-GPT | ba923bfeee913475263707376b7ba3dd8e6175e5 |
| PLAN-PILOT | 7f8c0c3cae739d9de37589f33c0c0a4cbb6d1579 |
| PLAN-TIME | 823ed804b33316257ac5e62e5aedcf093e72646b |
| CI preparation | e5886c4942b1ecf2432e554604766a4b00c39bab |
| CI context correction | aecf8ee1f556b60f3fa34b66a001372e332d02ab |
| PLAN-N2 + ADR proposal | b633243401a6a4e4b3f5f29507bb0b5826d83ebd |
| PLAN-UX brief | a1dbbbd65305f6020d64246b51b05c105debb97a |

Перший workflow run35503531221 відхилено GitHub до jobs через недоступний runner.temp у job env; PG/тести не починалися. Збережено відмову, diff і незалежний review виправлення. Новий run — перший фактичний адресний PG-прогін, без повтору історичних suites.
SQLite 24/24 виконувався на f2fa1e91/source b9722ed1 до картки сортування SOURCE; 7/7 unit — на кінцевому source31c692c5. Ці кандидати не змішуються. Raw outputs, невдалі red/проміжні спроби й SHA receipts збережені в `evidence/batch01/`.
main `ecb8cf7f62a4b333b61481481d2eea97b3400b54` не змінено. До майбутнього merge потрібна окрема звірка розбіжних CI-комітів main. Автоматичного merge немає.

## Наступні чекпоінти

| Чекпоінт | Результат цього пакета | Наступна конкретна дія |
|---|---|---|
| C0 | Setup/config/context готові в перевіреному scope | Власник завершує дві plugin connections; CLI smoke лише в доступній інсталяції |
| C1 | Шість scoped corrections; N2/TIME діагностика | Розглянути ADR N2; окрема картка залежностей перед зміною механізму; F04/F05 лишаються відкритими |
| C2 | Контракт trace і карта фактичних зв’язків | Реалізувати PLAN-LINKS-READ з additive catalogue й Policy regressions |
| C3 | UX brief | Figma-прототип → чинний inspector → дозволена UX/access перевірка |
| C4 | GPT contract | Визначити дозволені поля, API-проєкт і caps; до цього adapter off |
| C5 | BLOCKED | Усі 11 критеріїв на одному кінцевому кандидатові; не скидати вичерпані ліміти |
| C6 | Паспорт пілота | Обрати готові вироби / підряд / власне виробництво, людей і synthetic→pilot dataset |

Рекомендація щодо N2: покрокова dependency-scoped validation для однієї дії з консервативним global fallback; не послаблювати stale protection для всіх дій одразу. Це предмет ADR, не ввімкнений механізм і не обіцянка прискорення.
