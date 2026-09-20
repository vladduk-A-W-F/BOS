# PLAN-F03 · валідний код рахунку в concurrency fixture

Попередні 15 subtest errors у п’яти методах StatementConcurrencyTests виникали до конкурентного сценарію через Invoice.code max_length=30. Джерельний generator включає довільно довгий test tag. Картка змінює лише побудову синтетичного коду: C03 + currency + 12 випадкових hex, 20 символів для EUR/USD/UAH. Коди не обрізаються; бізнес-assertions і довжина поля не змінюються. Назви методів і currency subTest зберігають діагностичний контекст; tag лишається параметром виклику, але не частиною коду рахунку.

Доказ red: попередній PostgreSQL gate-05 log і запланована адресна перевірка baseline на PostgreSQL16. Нова перевірка: та сама StatementConcurrencyTests на PG16/SQLite, не весь gate5 або full. До фактичного запуску результат НЕ ПЕРЕВІРЕНО.
