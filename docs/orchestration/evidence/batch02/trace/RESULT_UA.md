# BATCH-02 · PLAN-LINKS-READ backend

Статус автора: SCOPED_IMPLEMENTED; незалежний review потрібний перед інтеграцією. Канонічний BOS не змінено. Реалізація у `execution/batch02/trace/source`.

Додано GET одного замовлення `bos.order-trace.v1`: точні Decimal-рядки, відкрита кількість за чинною семантикою balances, допустимий резерв за `usable()`, джерела резервування/відвантаження/скасування та пряме походження партії, роботи, доручення й дозволені InvoiceLink refs. `Policy.tasks()` зберігає обмеження історичних джерел. Ціни, суми, raw payload/result, approval_snapshot та приватні HR поля відсутні. Прихований складник робить похідне значення null/restricted; приховані IDs/counts/назви не повертаються. Вже дозволений SalesLine.shipped залишається видимим навіть за прихованого руху; це не новий агрегат із прихованих джерел.

Два проходи матеріалізують залежності, допуск документів включно з перевіркою bytes і найновішої видимої версії, склад наборів і показані metadata. Приватні digests, три читання erp_write та свіжі Policy/фінальна identity перевірка дають 409 без business payload за змін; відкликана identity зберігає 401/identity_denied. GET не створює Configuration, не викликає snapshot(), fingerprint(), writer, LLM чи повтор читання. Це оптимістична перевірка, не атомарний DB snapshot.

Додано лише один route до каталогу: 190 → 191 definitions; старі 57 required field IDs збережено, додано 18 (разом 75). Додано точний method/role/no_documents oracle, позитивні anchors і синтетичні hidden canaries. Історичний інвентар 85/12 та 11 GATES не змінені.

## Перевірки

- Red: одна нова HTTP-перевірка, exit 1, відсутній route дає 404 замість 200. `red/raw.log` і `report.json`.
- Green01: 17 методів HTTP/ORM, exit 0, 6.453 с разом, 1.833 с методи. `green01/raw.log` і `report.json`.
- Green02: адресно 2 методи, exit 0, 5.675 с разом, 0.259 с методи: додана reviewer-перевірка прихованого shipment та повтор Decimal/read-only після виправлення лише вимірювального збереження SQL-списку. Це 18 різних перевірених методів, 19 успішних виконань; не окремий прогін усього фінального модуля.
- Read-only resolver/discovery у тому самому `boss_project.server_urls`, що використовує check_access: 191/191 точних signature Counter; усі 18 нових IDs відповідають discovery; cursor заборонений, БД не створювалась, test methods не виконувались. Початкова діагностика з default URLconf не знайшла два наявні health routes; причину збережено в `CATALOGUE_DIAGNOSTIC_INITIAL.json`, product-файли через це не змінювались.
- На малій синтетиці CEO 74 SQL/41.603 мс без скасування; manager 124 SQL/59.399 мс; observer 124 SQL/55.587 мс. CEO зі скасуванням 76 SQL/40.610 мс. Це вимір вартості конкретного запиту, не доказ продуктивності чи масштабування. Попередній виведений 0 SQL для повторного CEO GET є недійсною метрикою через скидання Django query log наступним запитом; збережено як invalid у `METRICS.json`, виправлена метрика 76 SQL наведена окремо. Перевірка відсутності INSERT/UPDATE/DELETE використовує заморожений фактичний SQL-список.

## Межі

Синтетична SQLite лише. PostgreSQL, повний access sweep, E2E/browser та загальні gates не запускались. Нові fixture/oracle гілки підготовлено й незалежно перевірено статично, їхній повний sweep не оголошується PASS. Frontend інтегрує інший виконавець за погодженим DTO, приклад фактичної відповіді у `DTO_SAMPLE.json`.

Policy має глобальну вартість і повторно обходить частину ERP. ERP-дія поза order може консервативно відхилити читання. `generated_at` не дає snapshot isolation. Ліміт 100 стосується кожної видимої секції; суми не обрізаються. Readiness/pilot flags не змінено; main/production не зачіпалися.

Вісім source-файлів та SHA записано в `SHA256.json`; patch `PLAN-LINKS-READ.patch`. Окремий `PLAN_LINKS_READ_ROUTE_DELTA.json` призначений root для evidence-інтеграції після review. Наступний крок: незалежний вердикт, атомарна інтеграція root і погоджене з UI джерельне підтвердження без нового full retry.
