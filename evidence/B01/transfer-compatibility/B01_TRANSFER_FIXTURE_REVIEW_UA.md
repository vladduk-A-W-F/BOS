# Незалежний перегляд B01: сумісність синтетичних fixtures

Дата: 2026-09-12. Переглядач: `/root/a09_server_review`. Код checkout не змінювався; нових тестів, міграцій, серверів або звернень до робочих БД не запускав. Перевірено кандидат, фактичні журнали автора та відповідні незмінні оракули в checkout.

**Висновок: scoped consensus для двох змін fixtures. Блокувальних зауважень у цих межах немає.** Це дозвіл інтегрувати перевірений diff і виконати наступну повну перевірку, а не прийняття всього B01 чи MVP.

## Що змінилося

`fixtures/synthetic/transfer.py`: в один наявний виклик реального `_run('purchase', ...)` додано явну причину: «Синтетична пряма закупівля матеріалу для перевірки перенесення та часткового приймання.» Після вилучення тільки нового keyword `direct_reason` AST кандидата точно дорівнює AST початкового файла. Кількість 10, ціна 2.00, додаткові витрати 10.00, часткове приймання 7, три валюти, старі очікувані суми, джерела та всі assertions залишилися тими самими. Причина проходить звичайне правило B01; допуск без причини не додано. Запис нових B01 snapshot через реальну команду очікуваний.

`operations/test_document_migration.py`: лише сценарій highwater отримав окрему історичну підготовку. Новий файл SQLite створюється через `xb` у щойно створеному каталозі цього тесту. MigrationExecutor спочатку будує справжню схему operations 0005, ai_assistant 0008 та erp 0002; PRAGMA assertions підтверджують відсутність B01 quote/snapshot і нових A08 полів. Документи з ID 7/1001/90001, повідомлення та ChatFile створюються historical ORM, а не шляхом очищення сучасних PO. Оновлення застосовується тільки до нової копії, що отримала `OwnedDocumentCopy`; історичне джерело і спільне актуальне джерело перевіряються на незмінність.

Сценарій виконує тільки A08 migrations і зберігає старий `runner._preserve(..., schema=True)` без змін. Він порівнює всі наявні таблиці й рядки, дозволяє лише очікувані nullable A08 поля та дві точні записи migrations, зберігає попередні migration ID/timestamps і кожну верхню межу ID. Верхні межі document=400001/chat=500001 встановлено на історичному джерелі; фактичний наступний Document має ID 400002. Додано точну перевірку media до/після. Інші вісім A08 methods та їх assertions не змінені.

Історичний highwater dataset тепер цільовий: документи/чат у справжній старій схемі. Це не окрема перевірка заповненого старого PO в цьому методі. Повний актуальний dataset з PO, трьома валютами, оплатами, складом і replay перевірений незмінним full-model transfer у фінальному прогоні; legacy-null PO/high-water і відмова втрати populated B01 source мають окремі наявні тести B01. Не називаю новий historical метод дублюванням усіх цих доказів.

## Фактична послідовність

- Канонічний full20 зберігає червоний результат: спільний seed відмовив через відсутній direct_reason. Старий звіт не переписано зеленим.
- `red.log`: один реально виконаний full-model transfer тест відмовив на тому самому правилі.
- `green.log`, попри назву файла: **10/11**, а highwater відмовив. Після додавання причини сучасна закупівля законно має snapshot; спроба старого тесту відкотити operations до 0005 також відкотила б erp 0003. Reverse guard правильно відмовив. Цей результат залишено як історичний red, не приховано.
- `highwater-green.log`: **1/1**, 4.386 с, справжня історична схема → оновлення A08, document next ID 400002, джерела незмінні.
- `final-green.log`: **11/11**, 19.621 с, без skips. Full transfer підтвердив 45 таблиць, точні незалежні суми окремо EUR/USD/UAH, next IDs 90002/90003, рівний HTTP receipt і незмінність джерела. Всі дев’ять A08 document cases та missing-media refusal також пройшли.

Перевірка базового package manifest показала зміну тільки `operations/test_document_migration.py`; окремий fixture base manifest — тільки `fixtures/synthetic/transfer.py`. `erp/procurement.py`, `erp/service.py`, B01 migration guard та `scripts/check_document_migration.py` незмінні. Поповнені snapshot не видаляються і не обнуляються; reverse guard не послаблено. Звірені 2 hashes source, 4 hashes logs та повний patch hash manifest.

## Фіксація кандидата

Усі шляхи evidence нижче відносні до `tmp/b01_transfer_fixture_fix/`.

| Артефакт | SHA-256 |
|---|---|
| Кандидат: fixtures/synthetic/transfer.py | `cb85fd0358618abaec10d0d89746a1306ca3dac761aa21545040f027659609df` |
| Кандидат: operations/test_document_migration.py | `0212400de39aad5bf9219d8d8ef895bf580d953df6975df8d12f78869594472f` |
| Повний patch | `08abfe9ab3faffe2719171c5030872baeec583d6284816ee8db6900b131c1364` |
| Manifest | `8f263abe206fd557e9bfaa7be7be31bba5fd01401c3c9b625fc8e1004cbc344c` |
| evidence/final-green.log | `28e6049612774d30866ada0ab6437902126dc379805ba2d6550c8189961e39b0` |
| evidence/green.log | `13767f6383fa8e3ad40d9855a326fc518146d79f34dc7b85a277d401139540cd` |
| evidence/highwater-green.log | `ab1db583dc3048df695649c0f56b5f382cde837506feab9d2403bc8f743601cc` |
| evidence/red.log | `17dd1a07e7609f2ae36fd8292b64834027117ffe7a8537f2352f6839d90605c6` |
| Незмінний B01 reverse guard | `a81774d834ed82a5e68beb9ef745bdaff2b99d01c6173d246a988f4f8ee27e18` |
| Незмінний A08 oracle | `0c1f820660c917c21a6bbce1271bd94efc06985d31b69674264d320679e02b14` |

## Межі

Прийнято виправлення синтетичного seed і коректну історичну постановку одного migration regression. Прочитані журнали автора не замінюють повний canonical full21 після інтеграції. Не запускалися нові перевірки PostgreSQL, Windows, CI або зовнішніх даних; 11 приймальних gates і раніше відкриті A09/A10/A11 обмеження не змінюються. Це не доказ production cutover, activation/upgrade/rollback або готовності всього BoS до MVP.
