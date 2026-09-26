# A04 · незалежний огляд після 48/48

Обсяг: `boss_project/policy.py`, `operations/projections.py`, `operations/views.py`, `operations/service.py`, `erp/queries.py`, `erp/views.py`, `erp/assistant.py` та виклик `experience.next_step`. Вихідний позитивний доказ координатора: `evidence/A04/after-1.log`, 48/48 нових A04 tests.

Перевірка read-only. Реальні бази не відкривалися; нові відтворення виконані лише на окремих синтетичних SQLite. Зміни коду checkout та прийнятих 48 тестів не вносилися. Admin, frontend очищення сесії та старі fixtures ще в роботі координатора і не оцінюються тут як завершені.

## Підтверджені залишкові порушення

### 1. Закрите джерело в тексті наступного кроку

`erp.views.next_action` спочатку викликає `experience.next_step(order)` без policy. Пізніша відмова `p.action(payload)` зануляє лише payload, залишаючи вже обчислені title/why.

Відтворення: видиме замовлення й Item; історична Production BOM має закритий компонент. Snapshot правильно приховує цю роботу. Наступний крок manager та observer все одно називає `A04-HIDDEN-ITEM`.

- Коли компонент є на складі: `Зарезервувати A04-HIDDEN-ITEM`; заборонений payload згодом стає null.
- Коли компонента немає: `Потрібно забезпечити A04-HIDDEN-ITEM`; payload від початку null, тож перевірка action взагалі не запускається.

Виправлення має перевіряти джерела до формування тексту. Лише занулення payload чи обробка його винятку не закривають другу форму.

### 2. Replay повертає створений об’єкт, який тепер закритий

`operations.service.execute` перевіряє старий вхідний payload, але `projections.receipt` не перевіряє поточну видимість створених result IDs і рядків старого impact.

Відтворення: manager законно створює замовлення через ERP preview/confirm. Пізніше до замовлення додано закриту позицію; його поточний detail повертає 404. Первісні input IDs ще доступні. Replay старого proposal повертає 200 `succeeded` з `order_id`, кодом закритого замовлення та його старим impact.

Потрібна та сама поточна policy для результату та impact перед поверненням receipt. Збережений історичний receipt і бізнес-записи не змінювати.

Перші два порушення покриті двома методами у `/workspace/scratch/c7b51e996a9f/tmp/a04_test_remaining_context.py`. Остаточне відтворення, включно з початковим null payload: `/workspace/scratch/c7b51e996a9f/tmp/a04_remaining_before_v2.log` — 2 tests, 5 failures, 0 errors.

### 3. Видимий документ видає FK закритого договору

`Policy.documents()` використовує access_level, а `doc_dict(d,p)` безумовно повертає contract_id. Після перекласифікації пов’язаних джерел договір може бути закритим, тоді як документ лишається operational.

Відтворення: operational Document пов’язаний із Contract, який також має ceo Document. Для manager/observer Contract detail повертає 404, але documents list/detail видають його ID. Manager export повторює витік. Guard у новому review не усуває вже наявний зв’язок після зміни класифікації.

Дозволені варіанти: прибрати закритий FK із проєкції або приховати залежний документ. Оригінальний ORM зв’язок зберігається.

Один метод: `/workspace/scratch/c7b51e996a9f/tmp/a04_test_document_contract_visibility.py`. Доказ: `/workspace/scratch/c7b51e996a9f/tmp/a04_doc_contract_before.log` — 1 test, 5 failures, 0 errors.

## Що в перевіреному обсязі узгоджено

Централізована policy повторно отримує справжнього actor; permissions читаються на свіжому User. Є окремі document/download/export права. Recursive payload перевіряє вкладені IDs; snapshot фільтрує основні реєстри до побудови відповіді. Не-CEO projections прибирають фінансові зведення й довільні event payloads. Comparison повторно обирає рекомендацію серед видимих quotes. Confirm перевіряє input scope до повернення вже збереженого receipt; залишок стосується саме result/impact.

Повний консенсус A04 поки неможливий через три відтворені витоки. Після їх усунення достатньо повторного огляду цих місць і наявного regression набору; нових модулів чи тестів без конкретного ризику не пропонується.
