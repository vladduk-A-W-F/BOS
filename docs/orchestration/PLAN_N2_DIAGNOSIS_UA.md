# PLAN-N2 · один адресний SQLite micro-experiment

20.09.2026. Статус: **SCOPED_FINDING_CONFIRMED**, незалежний review: ACCEPT_SCOPED_DIAGNOSTIC. Виконано один окремо погоджений діагностичний процес, attempt1, exit0, `timed_out=false`, 5.581 s з обгорткою / 5.328 s усередині probe; зовнішня межа 60 s. Це не повтор P05, gate3, PostgreSQL suite, full або E2E.

**Встановлено:** зміна lot B через справжній preview/confirm робить непридатним раніше підготовлений proposal lot A іншого користувача, хоча граф джерел A не змінився. На малій синтетичній БД кожен із десяти fingerprint викликів виконав 24 SELECT. Ці дані не встановлюють причину 600-секундних F04/F05 і не доводять виробничу затримку або частку конфліктів.

## Середовище й ізоляція

- Python 3.12.14, Django 6.0.5, SQLite 3.53.1.
- Окрема копія коду: `execution/n2/source`; runtime/source SHA256 `31c692c5f3113446452e8d15faf95c29b019f433550bf4d0658c4f0428e54d20`; до/після probe збігається.
- Нова власна файлова БД `execution/n2/owned/check_ad13b612da4349b3b482dc6abc8505d3.sqlite3`; її відсутність перевірено до запуску, фактичний шлях перевірено через `PRAGMA database_list`. Media тільки `execution/n2/owned/media`.
- `verification_settings`; migrations лише на цій новій БД. Джерела fixture створено явно: по два Item, Location, Lot і opening Movement, без історичних/реальних даних.
- Кожний користувач має власні User ID і session, роль CEO; логін через реальні `/api/auth/csrf/` та `/api/auth/login/`. Django Client із `enforce_csrf_checks=True` проходить справжні URL/view/service/middleware; це HTTP-адаптер усередині процесу, не браузер і не мережевий сервер.
- У вимірюваних preview/confirm mutex, permissions, CSRF, перевірка fingerprint та транзакції не підмінялися. `connection.execute_wrapper` тільки спостерігав десять читань fingerprint; preview виконував dispatch як симуляцію з rollback, а збережені бізнес-зміни виникали лише через HTTP-confirm. Direct ORM inserts були виключно побудовою початкового синтетичного fixture.

## Фактичний шлях двох користувачів

| Крок | Користувач / сесія | Результат |
|---|---|---|
| CSRF + login | A, User 1, власна session | GET 200, POST 200 |
| CSRF + login | B, User 2, інша session | GET 200, POST 200 |
| `POST /api/erp/preview/` | A: `erp_adjust`, lot1, delta −1 | 200, pending proposal A |
| `POST /api/erp/preview/` | B: `erp_adjust`, lot2, delta −2 | 200, pending proposal B |
| `POST /api/operations/confirm/` | B, власний proposal B | 200, lot2: 10 → 8, один новий Movement та Event |
| `POST /api/operations/confirm/` | A, власний proposal A | **409**, lot1 лишився 10, receipt A порожня |

Це перекриття строків життя двох pending proposals із послідовним підтвердженням B → A. Одночасних потоків чи заміру очікування mutex тут немає; спостережений 409 не є оцінкою частоти збоїв під навантаженням. Строк обох proposal у raw — на десять хвилин вперед; уся діагностика тривала 5.6 s.

Граф A: Item1/Location1/Lot1/Movement1. Граф B: Item2/Location2/Lot2/Movement2. Усі чотири прямі source ID попарно різні. SHA графа містить повний row lot, item, location і всі movements цього lot.

| Стан | Lot A / B | Movement / Event | Mutex revision |
|---|---|---|---|
| До preview | 10 / 10 | 2 / 0 | 0 |
| Після обох preview | 10 / 10 | 2 / 0 | 0 |
| Після confirm B | 10 / 8 | 3 / 1 | 2 |
| Після відхиленого confirm A | 10 / 8 | 3 / 1 | 2 |

Fingerprint до preview й у двох proposal: `caf53624ca043c30afdd7f9d2cade932c19600b44f1f1a3968c7310095a34dfc`; після B: `e1068d22d60b00f801e1b9788987437ce5bdd2ccc12ac1b7bcbfce4b19addbc2`. Hash графа A в усіх станах: `7a1c24e04fafb426cddeb3c6d79ac199905f1ea83262945dbdb78907054ed6eb`. Граф B змінився; після відхиленого A незмінними лишилися виміряні fingerprint за 24 querysets, hashes двох графів A/B, кількості Movement/Event та mutex revision. Порівняння всіх таблиць не виконувалося. Повні graph/revision/response SHA та session SHA без сирих cookie збережено в `report.json`.

Пояснення підтверджене кодом і спостереженням: `erp.views.preview()` зберігає глобальний `service.fingerprint()`; `operations.service.execute()` звіряє його перед першим застосуванням proposal. `erp.service.fingerprint()` включає всі Lot і Movement, тому зміна B змінює fingerprint A, попри незмінність власного lot A. Це доведений конкретний випадок надто широкої інвалідації, а не твердження про всі типи погоджень: ready-receipt replay, task-команди та спеціальні statement/correction гілки мають окремі умови.

## Вартість fingerprint у цьому fixture

Десять послідовних викликів на незмінному fixture, без окремого warm-up і без масштабування:

| Метрика | Спостереження |
|---|---|
| Query count кожного виклику | 24 / 24 / 24 / 24 / 24 / 24 / 24 / 24 / 24 / 24 |
| Wall min / median / max | 7.776 / 8.343 / 16.635 ms |
| Wall mean | 9.443 ms |
| Медіана сумарного часу SQL execute | 0.692 ms |
| Дані у fixture | 2 Items, 2 Locations, 2 Lots, 2 Movements; решта охоплених ERP/фінансових наборів порожні, dataset config 1 |

Wall включає побудову queryset, fetch/матеріалізацію, JSON/SHA і overhead спостерігача. SQL execute timing не включає весь fetch/матеріалізацію, тому різницю не можна назвати чистим CPU SHA. У `report.json` є всі десять вимірів, усі 240 query observations із таблицями й тривалістю. Жодного прогнозу для PostgreSQL або 1k/10k/100k рядків із цих десяти вимірів не робиться.

## Межі й наступне рішення

Механізм не змінений. Канонічні файли не редагувалися; тести/suite не запускалися; виконано лише один описаний probe, без retry. P05 3/3, F04/F05 OPEN, `TECHNICAL_READY=false`, `PILOT_ALLOWED=false` лишаються чинними. SQL-профіль малого SQLite fixture не закриває PLAN-TIME.

Наступний результат для review/ADR — конкретно визначити read/write dependencies ERP дії й варіант адресної валідації або версій так, щоб зберегти stale protection, locks, права, атомарність і replay. Це пропозиція предмета рішення, не вже обраний механізм і не обіцяне прискорення. Обмеження «один активний користувач» не прийняте. Нові runtime заміри або правки потребують своєї точної картки; поточний probe автоматично не повторюється.

## Докази

- `probe.py`: точний виконаний одноразовий діагностичний код; SHA `157c05d97161eb410e92c3e8a9944372d28f3614b75fa1854aa260c3f2a676b7`.
- `raw.log`: фактичні HTTP payload/response, підсумок і час; SHA `a9b599dc6c4d7019bdead4a486bf1f0cd218cda3bed58cb7214b59dbcde4f8ad`.
- `report.json`: усі observations, distribution, ефекти та hashes; SHA `be08ad917db86d6bf998a1071acadeb7eafa4f14227cf67e8fdd092a4b87fa2d`.
- `receipt.json`: точна команда, attempt1, timeout60, exit0 та тривалість; SHA `6956c52c734a052e53248e1afb88ac7a2d7d34a122c4c0d753c1f8a740ac1d43`.
- `SOURCE_AND_ARTIFACT_SHA256.json`: hashes одинадцяти релевантних source файлів та чотирьох первинних артефактів.

Команда: `/workspace/scratch/4dbe5b4c73ee/execution/venv/bin/python -B /workspace/scratch/4dbe5b4c73ee/execution/n2/probe.py`. Нового Git commit цього виконавця немає; прийнятий source ідентифікований власним повним runtime SHA. Root інтегрує лише після незалежного review.
