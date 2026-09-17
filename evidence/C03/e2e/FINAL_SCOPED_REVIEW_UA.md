# Gate 6 · actual SQLite golden result

Повний заморожений EUR сценарій пройшов з першого запуску на окремій синтетичній БД: **821 assertions / 42 actual confirm HTTP calls**. Жодної правки API adapter, production code або business/source oracle після запуску не знадобилося. Canonical, source checkpoint та приватні вихідні БД не змінювалися.

Перевірений вхід: `tmp/c03_candidate/core_checkpoint_1`; master manifest SHA `86be441eca09e2bea33420fda70b2d97261a77c345ac13e9646fd1f2d4f772ed`; усі 20 спеціально перелічених файлів та всі 303 файли BOS_PACKAGE.json збіглися. Code-only package повторно побудовано штатним packager: source package SHA `e4d6e0adbb507018a8f0973f287a3994b54536edd141be1637b6346cdc6107b2`. Окремо скопійовано fixtures/tests і лише три gate6 deliverables. Виконаний source_digest з ними: `8c70fd2d794b2338261a4dc9ff3fd88dbefe4d1fa68fafeffb4ade23042c648d`.

Фактичне середовище: Linux, Python 3.12, SQLite 3.53.1; fresh owned database/media. ORM використано лише для довідників до baseline та подальшого читання. Джерельні TXT/CSV пройшли справжні HTTP upload/review/download; source hashes збіглися. Лише bootstrap operational classification трьох TXT — погоджене root довідникове налаштування перед baseline; банк CEO-only через actual C03 API.

| Перевірений результат | Значення |
|---|---:|
| Movement / ERP Event / ActionProposal / AuditEvent | 5 / 13 / 14 / 3 |
| First / immediate replay / late replay confirm | 14 / 14 / 14 |
| Відвантаження / carrying cost / gross difference | 4.68 / 2.54 / 2.14 EUR |
| Paid / receivable / customer credit | 4.68 / 0.00 / 0.00 EUR |
| Stock / stock carrying value | 1.000 / 1.27 EUR |
| PO gross received / open / open value | 4.000 / 6.000 / 7.62 EUR |
| Supplier return / carrying cost / agreed claim | 1.000 / 1.27 EUR / null |
| Recorded in / out / net movement | 4.68 / 0.00 / 4.68 EUR |
| Task result | done, фактичний manager FK/actor |

Числа звірено незалежними Decimal comparisons з незмінним oracle; raw ERP cost projections у звіті можуть мати більше нульових десяткових знаків, але суми точні. C03 summaries окремо перевірені як fixed2 JSON strings. Банківський залишок — null, початкового залишку немає.

Перевірено незмінність первісних Event/Movement/Audit/ActionProposal receipts, InvoiceLink, FinancialIntent та statement ledgers після наступних законних дій. Full business snapshot незмінний після кожного replay; виключено тільки authentication/session rows і ERP mutex revision. Чотири оригінали повторно завантажено через HTTP після late replays і звірено literal bytes. Manager завершив Task власною HTTP session; історичний виконавець і CEO create actor збережені. Bank source/detail/Transaction закриті для manager; old exports/context/list/.json/Task history не містять frozen bank canaries. Операційні TXT доступні manager з точним SHA.

Дві canonical вихідні БД захищено read-only SHA before/after; обидві незмінні. Фактичні IDs отримано з receipts або однозначних source lookups; numeric PK не зашито.

Raw докази: `reports/FULL_ACTUAL_1.json` SHA `ef3cf22b2f94a91abaf1d2ba606095f3a9692ed14c90bab96872552acd519a8a`, `reports/FULL_ACTUAL_1.log`, `reports/FULL_SOURCE_1.json`; повний manifest додає SHA всіх deliverables/evidence. Попередні STATIC/PREFIX reports є історичними checkpoint-доказами й не замінюють цей full scenario.

Межа висновку: green **лише SQLite gate6 у цій власній копії**. PostgreSQL, Windows, browser, усі 11 gates, ширші C03/C01 concurrency/roles/lifecycle та C03 загальне приймання цим запуском не доведені. PO має відкриті 6 одиниць, supplier claim лишається непідтвердженою. Root вирішує інтеграцію та запускає обов’язковий canonical verifier.
