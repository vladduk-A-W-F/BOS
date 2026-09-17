# C01 full24: два історичні тестові джерела

Виправлено тільки підготовку двох синтетичних історичних схем. Поточна міграція tasks.0005_controlled_tasks залежить від erp.0005_source_corrections. Попередні targets фіксували стару ERP, але залишали tasks на leaf. На порожній новій БД forward closure цього leaf застосовував нову ERP та її залежності: A07 отримував profile=latest, а A08 вже мав quote_id/approval_snapshot замість справжньої pre-B01 схеми.

Мінімальна зміна: в обох existing old/previous target dictionaries додано tasks=0004_task_branch; додано лише пояснювальний коментар. Міграції продукту, schema_preflight, migration runner, _preserve, джерельні рядки, native DDL/schema oracle та high-water assertions не змінювалися. Не відкочували populated базу, не видаляли snapshot нових погоджень. Весь код скопійовано package_server у новий каталог; обидва тести самі створюють нові синтетичні SQLite ресурси.

Фактичний before: ті самі два failures, exit 1, 2 методи / 9.569 s. Після вузького setup fix: ті самі 2 методи GREEN, exit 0, 7.799 s. A08 зберіг document high-water 400001, chat high-water 500001, actual next ID 400002; вхідні БД/медіа незмінні. Автоматична AST-звірка засвідчила буквальну незмінність усіх test_* methods і всіх assert/assert* nodes у двох файлах.

Це scoped SQLite proof, не повтор full24/25, PostgreSQL, A09 чи browser. Інших виправлень або необов’язкових прогонів не виконувалося. Root інтегрує лише два source files після незалежного огляду; C03 implementation була призупинена на час цього repair.
