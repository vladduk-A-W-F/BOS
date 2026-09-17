# C03 core checkpoint 2: незалежний scoped review

12.09.2026. Читання frozen source delta та збережених фактичних доказів; нових тестів, серверів, браузера, PostgreSQL, A09 або змін checkout не виконано.

**П’ять зауважень checkpoint1 закриті. Прочитаний core2 відповідає цим виправленим межам і показаним20 focused tests. Загальний C03 ще не прийнятий: final combined manifest, typed/schema/body/concurrency та canonical verify попереду. Одна уточнена верхня body boundary передана автору його вже активного boundary-підетапу.**

| Об’єкт | SHA-256 |
|---|---|
| CORE_CHECKPOINT_2.json | `f5b2a962b1e70fa959c83b9ea8571337256d9837ba447ac69e17006d49bf02f2` |
| Source package | `6387158eb680adbe635608d49e9dbdeb6d64b66630705d1e6903e6aaea668b27` |
| finance/statements.py | `c973fc9f1996835025301574d7f88d59658c7724a7195eb2b1c2d951f2892f71` |
| finance/statement_reads.py | `7fa41bb7a3c25f4d278b4d04bf29f34ec2950a558b554b7dec25514c6601c9f9` |
| finance/statement_csv.py | `869a96195a86d714968f72ab1b9b06d0cae5bbdb454416ddc96967b7265a92b3` |
| operations/views.py | `641cedfeb361e9c0439a9a3a8e222cccb28c3ec4f5ec5fb8f28e9c0e0ec27cfa` |
| erp/service.py | `708ce8d0ef4d5d4d0b2eb7a8f7ea602d3224418a98936e8f88e21e78fcc35a63` |
| finance/test_statement_integrity.py | `99a58eaabfd8ff98a5861d3c686da1f4c31eb2842bf6c4aa65a804c4eccc95c6` |

Незалежно звірено21 source,7 fixture supplement,3 успадковані C01 fixes та11 evidence entries — без розбіжностей. supplement частково перетинається зі source, це не твердження про31 унікальний продуктовий файл. Решта core1 product files побайтово незмінні.

## Закриття попередніх findings

1. Create → later existing_transaction того самого boundID тепер дозволений, але інший ID відхиляється, точні поля транзакції та matching перевіряються. First binding snapshot не переписується. Actual HTTP regression підтверджує одну Transaction, binding_created=false, transaction_created=false і повну рівність початкового snapshot.
2. Summary приймає та перевіряє status і використовує той самий current_line derived predicate, що lines. Actual unallocated scope дає recorded EUR10.00.
3. Import current summary зберігає попередні lines й додає currencies через спільний exact currency_totals саме для ordered Line refs цього Import. First receipt/source_totals незмінні; UI сумісний з додатковим currencies. Actual import detail дає unallocated EUR10.00.
4. CSV export доповнено явними import_id/line_id/document_id/source_sha256/first_import_id/first_document_id/first_source_sha256/transaction_id/status/allocated/unallocated. Оригінальні8 стовпців залишилися, формули у тексті екрануються; original source не перезаписується. Actual export перевіряє конкретні фактичні ID/SHA/Tx/status.
5. Duplicate existing payment_event_id у одному payload відхиляється до proposal незалежно від різних allocation_key. DB OneToOne збережений. Actual red200 → green422, count state незмінний; вже врахований payment не проводиться повторно.

## Додаткові виправлення автора

- Fresh postwrite Transaction refresh і порівняння всіх TX_FIELDS із планом; fresh Invoice settlement порівнюється з погодженим after. Actual SQLite AFTER INSERT trigger змінював Transaction.amount+1: початково confirm200, тепер409 та rollback Transaction/FinancialIntent/Audit/Allocation/paid/receipt. Це фактичний Tx drift proof. Окремого Invoice-drift trigger тесту у цих20 немає; не приписуємо йому цей доказ. Перевірка Invoice після запису прочитана у source.
- CSV quote scanner тепер відстежує logical record, physical line і column зі збереженням quoted newlines. Actual bare quote у третьому logical record: було record1, стало record3,422 і Document0.
- Для valid C03 command у перевіреному діапазоні >30000 та <=1MiB body дає413 замість попереднього422 ще до створення proposal; legacy malformed/other action статуси не переписані. Actual UTF-8 oversized request перевірено у final20.
- Обидві statement actions додані до explicit SCHEMAS, generic dispatcher їх відхиляє: потрібний спеціальний preview/confirm з чинним CEO, не довільний виклик ERP dispatch.

## Фактичні докази та їхня точна межа

`integrity-before.log` SHA `9f11b61645b7d54cfd9134c82f7a220dfde637288a2ea1c5dcfe6c7536910d31`:18 методів,4 failures і1 fixture error. Окремий error був неправильним створенням ImportBatch з неіснуючими полями, а не відмовою продукту. Фінальний тест отримує B02 ImportIdentity через справжні HTTP preview/confirm і звіряє namespace/target/row_sha.

`integrity-after-1.log` SHA `1dd041e12613294438a3d93eb5749f8f3bcd74638724f59c55038db17796dacb`:10/10,1.664с. Combined summary/export тест спершу зупинився на status400; окремі downstream export/current_summary red assertions до цього не виконалися. Їхній дефект підтверджено source-review, а після fix усі послідовні assertions фактично виконалися. Не називаємо три дефекти трьома незалежними red runs.

`duplicate-payment-before.log` SHA `a9d1ed81f161f734f41a0abf56406f126bc6d3c292b23016dd25fda0fafca099`:1 failure на200 замість422. `command-limit-before.log` SHA `41625a50e45bfa0c308fd80fb24203e017e95764cf7aa281fbdf1b5ce5d19826`:1 failure на422 замість413.

`core-twenty-1.log` SHA `48dab75e066c950b65dadddcd94ecebaf5e3bcf978bfe49d95df14a5b1829b78`:**20/20,3.031с,OK**. Охоплює первісні8 і12 integrity methods: immutable source/tamper навіть на replay, cross-CEO global identity no-change, historical existing Transaction з inactive counterparty, незмінний description через чинний financial writer, фактичну Salary виплату та її source link, фактичний B02 mapping, три окремі валюти при caller Decimal precision6 без зміни caller context, п’ять findings та зазначені нові guards. Це локальні actual HTTP/SQLite/private-owned-file докази; concurrent/PG proof не підмінено.

## Відкрита уточнена body boundary

У core2 `operations.views.body` розпізнає oversized C03 action тільки коли length<=1MiB. Валідний JSON C03 довжиною більше1MiB, але нижче загального upload обмеження, потрапить у generic422 замість контрактного413. Це конкретний висновок із source branch; нового runtime red рецензент не запускав. Автору/root передано для вже активної перевірки body boundaries. Це не A09 13MiB експеримент. Final manifest має зафіксувати вирішення або точну неприйняту межу; цей звіт не оголошує всі body cases зеленими.

Остаточний combined C03 verdict потребує фактичних typed/reverse/schema/complete concurrency/body доказів, узгодженого wire та нового immutable manifest. Browser, зовнішній PostgreSQL/Windows/CI, production, activation/upgrade та цілий MVP цим висновком не прийнято. UI має окремий SHA-bound висновок; старі звіти залишаються незмінними.
