# PLAN-N1-SHIP · довжина посилання відвантаження

Дата: 20.09.2026. Діагност/виконавець: делегований агент N1. Незалежний reviewer — очікується.

## Висновок

Підтверджено й виправлено окремий raw-length дефект `erp_ship.reference`. Існуючий `clean()` перевіряв лише `1 <= len(reference.strip()) <= 60` і загальний raw cap4000. Запис `Movement.reference` має `max_length=100`, але `ship` був відсутній у metadata target map; `move()` перевіряв тільки кількість Lot. Тому `A` ×60 + 41 пробіл (raw101) проходив сервіс і всі переглянуті HTTP шляхи; SQLite фактично зберігав некоректне значення разом зі змінами залишку, резерву, відвантаження та журналу.

Мінімальна правка додає **`'ship': Movement`** до вже існуючої таблиці цільових моделей `erp.service.clean`. Наявний `field_values` застосовує raw limit100 з моделі й повертає українську помилку `erp.movement.reference: максимум 100 символів.` до змін складу/резервів. Перевірка бізнес-межі stripped 1–60 залишається незмінною. Рядки в межах raw100 з допустимими крайніми пробілами зберігаються буквально; немає обрізання або нормалізації. Колонка й міграції незмінні.

| Фактичний вхід | Поле | ДО | ПІСЛЯ | Модель |
|---|---|---|---|---|
| `erp.service.dispatch` | reference | stripped 1–60, raw ≤4000 | stripped 1–60 + raw ≤100 metadata | Movement.reference:100 |
| `/api/erp/preview/` | reference | та сама недостатня перевірка | clean → metadata100, до preview writes | Movement.reference:100 |
| `/api/operations/preview/` | reference | та сама недостатня перевірка | validate → clean → metadata100, до proposal | Movement.reference:100 |
| stored proposal → `/api/operations/confirm/` | reference | приймав raw101 | повторна validate → clean; 422, mutex/claim rollback | Movement.reference:100 |

## Походження й allowlist

Окремий snapshot `execution/n1/ship-src` створений із кандидата `7d46dced3bcf06d44755cf53366c9e16bd465582`, runtime source SHA `10d86748d682926a898d2d2dfecd43fd7f6962f6ed38602da7ae704e52aca154`. Не містить попередню REQUEST правку. Після лише SHIP правки source SHA: `3903a67c49c56ebacc16c5a91eaf3e239c10afc62d04a48e60aea197fb15c409`.

Allowlist рівно два файли:

- `erp/service.py`: одна змінена runtime-лінія metadata map.
- `erp/test_shipping_reference_lengths.py`: два нові методи реальних сервісних/HTTP регресій.

Точний diff — `ship.patch`; SHA файлів до/після — `ship-files.json`. REQUEST diff та REQUEST raw logs залишені незмінними для окремого review. Канонічний BOS цим агентом не змінено. Жодні concurrency fixtures не редагувались.

## Фактичні регресії

Нові тести користуються тільки helper-класом `ERPConcurrencyBase`, який не містить test methods; concurrency suite не запускається. Справжня HTTP автентифікація і CSRF, production dispatcher/preview/confirm, синтетичні fixtures. Жодних mocks або підміни моделей.

| Запуск | Методи | Результат | Raw output |
|---|---:|---|---|
| RED, незмінний product candidate + нові tests | 2 | exit1, 24 failing subcases, 21.644 с | ship-red.log |
| GREEN, точний ship.patch | 2 | **2/2 PASS**, exit0, 15.913 с | ship-green.log |
| AST parse обох файлів | 2 файли | exit0 | ship-files.json / tool output |

Позитивний метод: 3 абетки (ASCII, Ї, emoji) × 3 варіанти (60 символів; 60 + 40 крайніх пробілів; 40 початкових пробілів + 60) × 3 входи (dispatch, ERP preview, operations preview) = **27** успішних сценаріїв. Кожен HTTP сценарій проходить confirm і повторний confirm; перевіряє точний raw reference у Movement, Event payload, receipt; одну відвантажену кількість7, вартість14, залишок3, резерв3; preview не змінює бізнес-джерела, replay не дублює записи.

Негативний метод: 3 абетки × 3 варіанти (raw101 з кінцевими пробілами; raw101 з початковими; 61 непробільний символ) × 4 входи (dispatch, два preview, stored-proposal confirm) = **36** відмов. 24 raw101 subcases були реальними RED змінами стану; 12 business61 вже відхилялися до правки й залишилися відхиленими. Порівнюється exact physical business state, proposal receipts та Configuration mutex **до** тестового cleanup. Відмова: ValueError у сервісі або 422 в HTTP, без часткових відвантажень/зняття резерву/аудиту.

Ця вузька регресія використовує EUR. Інші валютні правила не змінені й не видаються за заново перевірені.

## Команда

```text
BOS_VERIFY_DB=sqlite
BOS_TEST_DB_NAME=<новий абсолютний check_ship_*.sqlite3>
BOS_TEST_MEDIA=<окрема тека>
PYTHONDONTWRITEBYTECODE=1
/workspace/scratch/4dbe5b4c73ee/execution/venv/bin/python -B manage.py test erp.test_shipping_reference_lengths --settings=verification_settings --noinput --verbosity=2
```

Обидва запуски виконані у `ship-src`, Django 6.0.5, із новими файловими SQLite test DB та окремими media. PostgreSQL16 локально не запускався; root готує дозволений адресний runner. Full suite, CI, E2E, deploy, історичні або інсталяційні БД не запускались. Readiness не змінена.

## Уточнення загального N1 аудиту

У попередньому незмінному `DIAGNOSIS_UA.md` рядок ERP quality містить описку: точні result choices — **approved / blocked / rework**, а не approved / rejected / blocked. Це лише виправлення тексту, product diff не зачіпає quality.

Початковий invoice31 finding **ALREADY_COVERED**: shared validator уже бере Invoice.max_length30; дві незмінні L01 регресії пройшли в REQUEST green run. Окремий UX finding `next_step` генерує `INV-<order.code>-1` понад30 для довгих order.code; validator безпечно його відхиляє. UX генерація не змінена в N1-REQUEST/N1-SHIP.

Наступний крок: незалежний review точного SHIP diff і raw logs, потім послідовна інтеграція root; scoped PostgreSQL16 перевірка.
