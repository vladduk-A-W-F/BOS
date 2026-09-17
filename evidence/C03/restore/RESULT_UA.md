# C03 · actual native restore

Перша повна репетиція — 18/18, exit0, на новій синтетичній інсталяції з власним loopback TLS. Базові16 checks збережені; додано2. Exact56 таблиць = старі53 +3 C03 ledger. Backend core checkpoint1, ще не finalC03.

Actual CSV3 рядки: EUR4.56 створює одну транзакцію; USD123.45 та UAH9801.07 зв’язуються з попередніми synthetic seed transactions. Рознесення USD2.34 погашає окремий рахунок, залишає121.11 нерознесеними. Архівування EUR не прибирає cash; journal EUR21.95/USD123.45/UAH9801.07.

Populate order: початковий імпорт → C01Tasks → C03statements → B03corrections; старий B03 whole ERP+home snapshot зберігається буквально. Перша оригінальна CSV, downloadSHA, Import/Line/allocation, current summaries, journal, export,4immutable receipts і старі task6receipts/correction7 збережені після чистого native restore. Старий session confirm403, новий no-change preview повертає first receipt без нових domain effects.

До першого запуску root усунув тільки помилкове припущення draft: erp_order.lines не приймає revision; поле вилучено за чинним source schema. Після actual run code/oracles не змінювалися. Реальні userDB/media не використовувалися як fixture. Запуск не виконував activation/upgrade/rollback/A09 oversize/browser/PG/Windows. Фінальний canonical fullC03 ще обов’язковий.
