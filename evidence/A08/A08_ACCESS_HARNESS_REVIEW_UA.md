# A08 · незалежний огляд ізоляції критерію 4

12.09.2026. Локальну правку checker погоджено. Код бізнес-маршруту, durable-транзакція, каталог, ролі, методи, дозволи та очікуваний HTTP 201 не змінювались.

У `verify-1` лише два дозволені upload (CEO/manager) повернули 500, оскільки старий checker обгортав кожний запит у зовнішню `transaction.atomic()`. Окремий фактичний probe перевірив `response.exc_info`: в обох випадках причина — `RuntimeError: A durable atomic block cannot be nested within another atomic block.` Це конфлікт способу ізоляції перевірки з необхідним справжнім commit, а не підстава вимикати durable.

Новий helper видає право відновлення тільки після власного `open('xb')` нового файлу SQLite, фіксує inode та перевіряє actual DB path, vendor, PRAGMA database_list, відсутність сторонньої attached DB і autocommit. П’ять POST upload випадків виконуються зі справжнім commit та тим самим response/state oracle. Решта випадків зберігає попередню atomic-ізоляцію. Помилка під час finally/restoration завжди робить case червоним.

Для кожного такого запиту helper зберігає SQLite backup і працює з новою копією MEDIA_ROOT. Після запиту відновлює лише власний початковий SQLite файл, порівнює всі SQL-рядки включно з system/session та sqlite_sequence; початковий media manifest має бути незмінним. Нова файлова копія й commit не підміняються mock. `:memory:` та не підтримана native PG-ізоляція явно відхиляються, а не отримують позначку успіху.

Фактичний `a08_gate4_owned_isolation_after.log` підтверджує:

- Два очікувані nested red 500 з точним RuntimeError.
- Два справжні 201 зі зміною БД, перевіреними приватними bytes/SHA/size та наступним точним відновленням baseline.
- Відмову для existing DB, підробленого owner та заміненого inode без перезапису їхнього вмісту.
- Відновлення baseline після навмисного exception вже після справжнього commit.

Підготовлено import-safe постійний SimpleTestCase: `a08_access_isolation_test.py`. Його worker фактично запущено проти канонічного helper; exit 0. Повні 8370+9 HTTP, 57 обов’язкових перевірок полів та загальний verify повторює root. Цей review не приймає PostgreSQL, Windows або реліз. SHA переглянутих файлів — у `A08_ACCESS_HARNESS_REVIEW.json`.
