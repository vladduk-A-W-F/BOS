# B01 · кандидат серверного зв’язку пропозиції із закупівлею

**Кандидат заморожено для незалежного огляду та інтеграції координатором. Повний verify, PostgreSQL і браузер у цій роботі не запускалися.** Оригінальний checkout не редагувався; виробничі/історичні бази не читалися й не змінювалися.

Файли: `B01_FROZEN_MANIFEST.json` містить точні SHA 13 файлів, базового пакета та журналів. `B01_BACKEND.patch` — той самий кандидат для огляду. Інтегрувати лише перелічені файли із `source/`; власний synthetic `source/db.sqlite3`, тестові БД та `media*` до продукту не входять.

## Що змінено

- Збережено єдиний writer `erp_purchase` та чинні preview/confirm/mutex/receipt. Нові optional аргументи: `quote_id`, `supplier_confirmation`, `direct_reason`. Нових маршрутів або способів запису немає.
- Quote-покупка перевіряє явний request/item mapping, одиницю й версію, точну відповідність supplier/price/extras/currency, MOQ, чинність, комплектність, актуальність і SHA оригіналів. Погоджена дата — від `as_of` до `required_by`; розрахунковий lead time не підміняє підтвердження менеджера. Валюта планової калькуляції Item не обмежує фактичну валюту закупівлі.
- `Purchase.quote` — nullable PROTECT, `approval_snapshot` — nullable JSON. Новий PO записує джерела, погоджені умови, кількість/дату та причину або засвідчення менеджера. Snapshot не має шляху редагування; перенесення дати зберігає snapshot/original_due. Історичні записи міграція лишає без вигаданого погодження.
- Усі PO вимоги враховуються у розподілі під mutex; часткові/дробові розподіли допускаються, перевищення ні. Пряма закупівля потребує причини; за наявності request застосовуються ті самі mapping/date/currency/allocation перевірки.
- Request/Quote входять до ERP fingerprint; їхні creation writers беруть чинний mutex до джерельних читань. Окремо перевіряються байти файла при confirm — пошкодження не маскується незмінним DB checksum.
- Нові поля compare: request.id/original_quantity/allocated_quantity/remaining_quantity, row.id/supplier_id. Якщо частина PO недоступна ролі, projection повертає `null/null` та `allocation_visibility='restricted'`; неповний розподіл не видається за повний.
- Видимість PO враховує поточний Quote та історичні source document IDs snapshot. Observer отримує лише source IDs/codes; комерційні поля й довільні підтвердження не повертаються. Поточна операційна видимість Lot за item/власними документами збережена.
- Міграція використовує `PreserveSequenceAddField`: forward/backward для історичних null-джерел зберігають SQLite high-water. Reverse guard до видалення полів відмовляє, якщо будь-який PO вже має quote або approval_snapshot. PROTECT не дозволяє видалити Quote, що є джерелом PO.
- Доповнено чинний assistant parameter guide. Два seed command payloads і одна стара конкурентна purchase-фікстура отримали явні синтетичні причини; кількості, суми та старі assertions не змінені. ORM-створені історичні PO не доповнювалися вигаданими умовами.

## Фактична перевірка

| Перевірка | Результат | Журнал |
|---|---|---|
| Початковий контракт | 11 методів, 13 failures: зокрема пряма закупівля без причини проходила, quote-поля не підтримувалися, creation mutex відсутній | `evidence/red-1.log` |
| Сумісність `tax_basis` | Реальний red відмови чинним netto terms; мінімально дозволено тільки optional `excluding_VAT`, оригінал зберігається; невідомий tax basis відхиляється | `evidence/tax-basis-red.log`, `evidence/after-2.log` |
| Нові B01-регресії до reverse guard | **17/17, без пропусків, 4,050 с** | `evidence/after-2.log` |
| Нові B01-регресії після reverse guard | **18/18, без пропусків** | `evidence/final-18.log` |
| Відмова втраті погодження при reverse + збережений legacy-null/high-water сценарій | **2/2**; фактична відмова, columns/constraints/rows/migrations/sequence незмінні | `evidence/reverse-source-green.log` |
| Чинні operations | **48/48** | `evidence/compat-operations.log` |
| Чинні ERP | **49/49** | `evidence/compat-erp.log` |
| Чинний конкурентний purchase oracle | **1 метод / 3 валюти**, незмінні assertions | `evidence/compat-concurrency.log` |

Нові сценарії включають: partial receive 4+6 із рівно 128,40 у кожній з трьох валют; HTTP replay без повторного руху; різні concurrent proposals на 6+6 при вимозі 10 → фактичні 200/409 і лише один PO; private-file та BLOB corruption; зміни джерел між preview/confirm; реальний DB trigger failure після створення PO → повний rollback → успішний повтор; прихований історичний snapshot source; операційно видиму Lot без прихованих реквізитів; restricted aggregate; реальну forward/backward міграцію історичних рядків та наступних ID.

Старі checker-скрипти читають `source/db.sqlite3` для oracle незмінності. Тут для них створено новий окремий synthetic SQLite canary; обидва скрипти перевірили його незмінний SHA. Це не копія й не читання клієнтської бази. Реальні тестові SQL-записи спрямовано в окремі явно задані `check_*` БД кандидата.

## Уточнення нової фікстури, без послаблення старих oracle

Перший after містив чотири test-only failures. `fixture('USD')`/`fixture('UAH')` помилково задавали лише suffix, залишаючи currency=EUR; виклики виправлено явним другим аргументом. Новий state helper помилково рахував службову revision `Configuration[erp_write]` бізнес-даними: чинний accepted replay бере mutex і збільшує revision. Порівняння лишило всі PO/Lot/Movement/Event і всю іншу Configuration; виключено тільки цю службову revision. Нову непогоджену заборону 1,5 одиниці замінено точним перевищенням 10,001 та позитивним розподілом 6,5+3,5 — відповідно до погодженого Decimal-контракту. Жоден старий assertion не змінено.

Виявлений координатором `tax_basis` відтворено до мінімальної правки; одна спроба виправлення, результат зелений. Ліміт трьох спроб однієї проблеми не вичерпано.

Після першої фіксації координатор знайшов втрату populated source під час reverse 0003. Окремий реальний red (`evidence/reverse-source-red.log`) створив PO через HTTP preview/confirm і довів, що rollback видаляв columns/constraints/rows/migration receipt. Мінімальний `RunPython` reverse guard відмовляє до будь-якого видалення полів за OR `quote_id IS NOT NULL` / `approval_snapshot IS NOT NULL`. Фактичний green довів незмінність схеми, даних і sequence; попередній all-null reverse/high-water тест збережено. Одна спроба виправлення. Початковий manifest збережено як `B01_FROZEN_MANIFEST.v1.json`, чинний повторно фіксує тільки нові SHA двох файлів.

## Межі

`supplier_confirmation` — засвідчення менеджера, не незалежне підтвердження від постачальника. Податки, валютна конвертація, повернення/корекції B03, імпорт B02, банківська виписка C03 та повний e2e критерій 6 не реалізуються цим кандидатом. Frozen 85 шляхів / 12 місць не переінвентаризовано. Root веде frontend, канонічні документи PARAMETERS/KNOWLEDGE, інтеграцію та повний verify після завершення поточної A10-фіксації.
