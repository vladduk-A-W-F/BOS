# A07 · перший незалежний червоний прогін

Дата: 11.09.2026. Набір: `tmp/a07_boundary_tests.py`. Початковий незмінений лог: `tmp/a07_boundary_first.log`.

Результат: **15 методів, 203 падіння assertions у subtests, 0 errors, exit 1; 15,404 с**. Дев’ять методів мають підтверджені дефекти; шість пройшли повністю. Це не 203 незалежні дефекти: той самий порушений контракт перевірено через різні адаптери, валюти та точний постстан.

Виконано 228 негативних ERP-викликів і 6 негативних викликів shared financial command. Позитивні контролі: 28 справжніх ERP preview → confirm → replay, 3 фінансові створення та реальне завантаження довільних BinaryField bytes.

## Фактичні результати

| Контракт | Результат на коді A06 до A07 | Падіння assertions |
|---|---|---:|
| L01 · Invoice.code 31 | ASCII, українські символи, emoji та 30 символів із кінцевим пробілом приймають dispatch, preview і confirm. Код не обрізається, але перевищує колонку 30. Невалідний preview створює proposal; confirm створює рахунок і журнал. | 72 |
| L02 · Item.revision 41 | Усі три адаптери приймають значення для поля 40. Позитивні 40 збережені буквально. | 6 |
| L02 · Lot.revision 41 | Так само, EUR/USD/UAH. Позитивні 40 пройшли. | 18 |
| L03 · Item.material 201 | Значення прийняте для поля 200; позитивні 200 пройшли. | 6 |
| L03 · Location.name 201 | Значення прийняте для поля 200; позитивні 200 пройшли. | 6 |
| L04 · вкладений JSON | NUL та непарні high/low surrogate приймаються у вкладених значеннях, ключах external_codes і routing.instruction. Dispatch записує Item/Event; preview повертає 200 і створює proposal. | 54 |
| L04 · скалярний текст | NUL записується в name/material. Surrogate відхиляється лише SQL-драйвером: прямий UnicodeEncodeError, HTTP 422, але вже після спроби INSERT. | 20 |
| L04 · shared save_transaction | NUL створює Transaction, AuditEvent і FinancialIntent. Surrogate дає UnicodeEncodeError замість ValidationError. Усі три валюти. | 9 |
| N02 · computed Invoice.amount = 10^12 | Direct dispatch завершується успішно та змінює SalesLine.invoiced, Invoice, InvoiceLink, Event. HTTP preview/confirm дають 500; їхні атомарні блоки відкочують усі записи та claim. | 12 |

Повністю зелені методи: L01 code 30 ASCII/український текст/emoji; L04 валідний Unicode/JSON/Binary; N01 quantity scale 3 проти 4; N01 money scale 2 проти 3; N01 NaN/sNaN/±Infinity; N02 точний максимум **999999999999.99**. N01 негативні відмови мають нульовий ефект через dispatch, preview і confirm.

## Відокремлення fixtures від дефектів

Помилок fixtures, авторизації, CSRF, відсутніх полів чи маршрутів не виявлено. Всі позитивні межі пройшли до правок продукту. Збережено справжню Django-ідентичність ceo через login; Employee створюються тільки як синтетичні бізнесові передумови.

Синтетичний рахунок 10^12: кількість 1000000.000 × ціна 1000000.00. Обидва вхідні значення допускаються чинним `number`; залишки, відвантаження і рухи узгоджені. Точний дозволений максимум: 999999.999 × 1000000.00 + 1.000 × 999.99 = 999999999999.99. Позитивний контроль доводить, що відмова не має просто блокувати великі суми.

До очищення кожного негативного сценарію знято точний фізичний snapshot усіх прийнятих business models, ActionProposal і FinancialIntent. Raw SELECT потрібен, бо ORM Decimal-конвертація сама може впасти на вже записаному SQLite overflow. Це тільки незалежне спостереження; операції виконуються реальними ORM/HTTP writers.

Зовнішня тестова транзакція відкочує небажано прийняті рядки **після** зняття фактичного постстану й перевірок. Це ізоляція сценаріїв, не доказ rollback продукту. Вона не дозволяє одному переповненому Invoice отруїти наступні fixtures. У звіті direct dispatch залишається дефектом запису; HTTP overflow — дефект явної помилки 500, із справжнім rollback.

`connection.execute_wrapper` прозоро передає первинний SQL, параметри, connection і результат; він не змінює ORM/HTTP та не підміняє драйвер. Для L04 перевірено відмову до будь-якого business INSERT/UPDATE/DELETE; auth SELECT і службовий mutex не є записом невалідного бізнесового тексту.

Історичні pending proposals із довгим кодом або некоректним числовим рядком створені синтетично через ORM і підтверджуються реальним HTTP. Для NUL/surrogate в JSON використані dispatch і preview: такий persisted JSONB proposal неможливо чесно створити як валідну PostgreSQL fixture. Позитивний Unicode/JSON шлях проходить preview, confirm і replay.

## Межі доказу

Запущена тільки нова одноразова SQLite за `verification_settings`. Реальні `db.sqlite3` та `BoS_Demo.sqlite3` не читались. Імпортований `ERPConcurrencyBase` не має test methods; успадковані A06 37 тестів не дублювались. Жодного редагування checkout цим агентом немає. Чернетка й початковий лог не переписувались після запуску.

PostgreSQL **НЕ ЗАПУЩЕНО**. DB constraints, preflight legacy-конфліктів і SQLite→PostgreSQL transfer/rollback залишаються окремою частиною A07; цей red їх не зараховує. A06 source на початку прогону ще не містив A07 правок; після повідомлення результату root почав інтеграцію.

Точна команда запуску:

```bash
BOS_VERIFY_DB=sqlite BOS_TEST_DB_NAME=/workspace/scratch/c7b51e996a9f/tmp/a07_boundary_first.sqlite3 BOS_TEST_MEDIA=/workspace/scratch/c7b51e996a9f/tmp/a07_boundary_first_media BOS_TEST_DEPENDENCIES=/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages PYTHONPATH=/workspace/scratch/c7b51e996a9f/tmp PYTHONDONTWRITEBYTECODE=1 /workspace/scratch/c7b51e996a9f/demo-check-env/bin/python manage.py test a07_boundary_tests --settings=verification_settings --noinput --verbosity 2 > /workspace/scratch/c7b51e996a9f/tmp/a07_boundary_first.log 2>&1
```

Робочий каталог команди: `/workspace/sites/bos-original-refined`. Django створив і видалив окрему `a07_boundary_first.sqlite3_django_test`.
