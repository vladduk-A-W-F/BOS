# PLAN-TIME — результати обмеженої діагностики P06-F04/F05

Статус: **BOUNDED_DIAGNOSTICS_COMPLETE_CAUSES_OPEN**. Два дозволені зразки завершилися на PostgreSQL 16.15. Причини історичних 600-секундних timeout залишаються недоведеними; runtime-виправлення не застосовано. P06 BLOCKED, technical_ready=false, pilot_allowed=false; історичний P05 залишається 3/3.

## Джерело та перевірені докази

Діагностика: [run 35513613026, attempt 1](https://github.com/vladduk-A-W-F/BOS/actions/runs/35513613026), commit `1876ad00412b558fcfe0f23ab5291c90caeba63a`. Незмінний runtime походить із `8060075455206257d6283c70906facca98f0bc1a`; SHA256 до та після — `ce495b29214f21a80b8efd5bf41f6f219b5cb182b0453a7c43dac8899bc06ed5`. Python 3.12.14, Django 6.0.5, DRF 3.17.1, psycopg 3.3.6.

[Оригінальний ZIP](evidence/plan-time/20260920/BoS_PLAN_TIME_35513613026.zip): artifact 10606505258, 22 338 bytes, SHA256 `1fd89539b1fd46fbd27a6b8a79549aad00288519a6ead3b78032749fbb0d53fb`. Root і незалежний reviewer окремо відновили ZIP у пам'яті та перевірили 11 елементів архіву й усі 10 записів [SHA-індексу](evidence/plan-time/20260920/sha256-index.json).

Для отримання вже створеного архіву використано [evidence-only reader 35514074336](https://github.com/vladduk-A-W-F/BOS/actions/runs/35514074336), commit `56a718116577799cca5c098b427b88322b60cd82`. Він виконує лише GET і перевірку даних у пам'яті: без checkout, встановлення пакетів, програми чи БД. На цьому commit PLAN-TIME targeted job 106086955521 і обидва BATCH targeted jobs мали SKIPPED. Повторного PG-експерименту не було.

Повні первинні дані: [supervisor](evidence/plan-time/20260920/report.json), [Django](evidence/plan-time/20260920/django.json), [replay](evidence/plan-time/20260920/replay.json), [receipt](evidence/plan-time/20260920/receipt.json), [незалежне review](evidence/plan-time/20260920/REVIEW.md).

## Обсяг і результат

| Зразок | Фактично виконано | Процес worker | Разом із підготовкою та очищенням |
|---|---|---:|---:|
| F04 | Один чинний test_http_pair_item, три subtest EUR/USD/UAH | 6,431 с | 6,801 с |
| F05 | Одна opening → confirm → adjustment → чотири replay послідовність | 5,825 с | 5,856 с |

Обидва процеси завершилися з exit 0, timed_out=false. Для кожного виділялася окрема синтетична PostgreSQL 16 БД. У Django підтверджені source/test identities, незмінний source canary та очищення обох БД. У replay перед міграціями підтверджено відсутність user tables; після rollback відновилися кількості рядків усіх 55 перевірених managed-model таблиць. Очищення виділеної БД також підтверджене.

## F04: поточний Django-зразок

Рівно один метод `erp.test_concurrency.ERPProposalConcurrencyTests.test_http_pair_item`: Found 1, Ran 1, OK, без skip/xfail. Raw містить три A06_PAIR і три A06_PASS. У кожній валюті два HTTP worker виконувалися з перекриттям, отримали 200/200, а чинні assertions підтвердили один ефект та незмінність replay.

Підготовка test database зайняла 2,533410 с; тіло тесту — 1,589567 с. Реальний HTTP login зайняв 0,574287 с. Два PBKDF2 encode по 1 200 000 ітерацій сумарно зайняли 0,551669 с. Hasher не замінювався.

Спостережено 6 fingerprint із сумою wall-time 0,111823 с та 12 snapshot із сумою 0,868505 с. SQL instrumentation зареєстрував 2740 execute/executemany викликів у семи записах потоків без SQL errors. Сума SQL-time по потоках — 1,624309 с; вона не є elapsed time і не додається до вкладених фаз.

Це визначає витрати одного поточного concurrency-методу. Історичний лог повного процесу не містить test ID або stack на момент 600-секундного переривання. Наявність витрат на auth/snapshot не встановлює причину того timeout.

## F05: поточна replay-послідовність

Preview, first confirm і чотири replay отримали HTTP 200. Receipt повторів не змінювався; перевірки fingerprint/events, quantity, movement/event/proposal counts та rollback пройшли.

Фактично викликалися 8 глобальних fingerprint: кожний виконав 24 SQL-запити, сумарний function wall-time — 0,134974 с. Чотири повні snapshot виконали 148 SQL-запитів за сумарні 0,099371 с. Новий scoped dependency path для erp_adjust не замінює глобальний шлях дослідженого erp_opening.

Чотири cached replay HTTP зайняли 0,021380–0,022307 с кожний. У цих HTTP-фазах не було product fingerprint/snapshot; наступні самостійні oracle перевіряли fingerprint. Mutex/auth залишаються частиною шляху.

Міграції — 2,429155 с; одноразова підготовка/auth клієнта — 1,070058 с. Це одноразові витрати зразка, їх не можна множити на кількість replay у історичному циклі.

Існуючий oracle одразу після first confirm обчислює значення, яке згодом перезаписується після adjustment. Його fingerprint виміряно: 24 SQL і 0,015666 с, плюс окремий Event.count. Його збережено у зразку. Вимірювання не доводить, що цей виклик спричинив історичні 600 секунд, і не дає підстав позначати F05 як виправлений.

## Межі висновків

Фази replay включають запис checkpoint report на вході. Наприклад, unused_oracle phase має 0,192884 с, але її fingerprint function — 0,015666 с. Час фази не можна цілком приписувати бізнес-операції або fingerprint. Instrumentation overhead не калібровано.

Один зразок не характеризує 1000 випадкових послідовностей чи повний Django suite. Вкладені timings не складаються; жодного прогнозу тривалості повного gate тут немає. Polling раз на п'ять секунд із ClientRead без blocking PID не виключає коротких очікувань між опитуваннями.

Повний suite, gate-3, E2E, seed та повтор вичерпаного P05 не запускалися. Ліміт 600 секунд, продуктові семантики, schema, main і Site не змінювалися. Landing v3 acceptance та історичні результати BATCH збережені.

Поточний пакет завершує підготовку, два обмежені вимірювання та незалежну перевірку evidence. Для встановлення історичної причини бракує точного активного тесту/фази й stack того процесу; новий повний прогін цим звітом не дозволяється. Підготовлені вимірювання придатні для подальшого окремо визначеного адресного дослідження, якщо з'явиться конкретна перевірювана гіпотеза.
