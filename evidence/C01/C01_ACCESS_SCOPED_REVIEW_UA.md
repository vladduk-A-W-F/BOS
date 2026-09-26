# C01 — незалежна перевірка access-патча

12.09.2026. **Три access-файли погоджено в межах прочитаного коду й фактичних синтетичних доказів. Конкретних блокувальних зауважень до цього патча немає.** Backend, canonical full verify, PostgreSQL та browser цим висновком не приймаються.

Прочитано всі три diff, fixture/writer альтернативу, outcome/history/body/field oracles, finite probe sources та їхні результати. Reviewer не запускав нових HTTP, tests, server або full gate і не читав початкові DB/media. SHA трьох source-файлів та 11 evidence-файлів незалежно звірені, розбіжностей немає.

| Файл | SHA256 |
|---|---|
| scripts/access_fixtures.py | `6d787e06862fba2149b946a7950b95f02b0877b82cb30ad6c73cd16b6e62b323` |
| scripts/check_access.py | `0e0f4b6ebd2b2af77d750d466eeb5bc83bce682c5ff0cb3a2688862159ee5694` |
| scripts/access_routes.json | `182639ea19916ca2c8f4a7c51b1b936e6bcf19d7148f5328b1166d5ca73d8597` |

Source: `tmp/c01_access_candidate/source`. Results ledger SHA `e15a96737b6b0cbb06dacebde4f695080ed1238f9579f13d4fc3f8b5b5604602`; evidence-hash manifest SHA `67b6dba7028a8334c63baa36804e8facd29269eeee12221b950373880528738a`.

## Збереження попередніх перевірок

Незалежне JSON-порівняння підтвердило: старі 177 route objects є незмінним початком нового manifest; усі 57 required field IDs буквально рівні B03. Додано три явні definitions: plain history, format history, owner proposal status. Фактичний resolver має 180 definitions. Старий маршрут або обов’язковий тест не вилучено.

Прийнята зміна продукту замінює прямий Task CRUD погодженим writer. Для чотирьох оголошених write-комбінацій raw REST потрібен 403 із точним `approval_required`; business digest включає всі business models, і при відмовах/читанні незмінний. Непідтримувані list PUT/PATCH/DELETE і detail POST зберігають старий 403/405 oracle: відмова 405 не повинна вимагати body-код неіснуючого writer. Технічний Task admin читає, але повні валідні add/change/delete/bulk форми не змінюють рядки. Це не підміна write перевірки невалідним порожнім input.

Позитивна альтернатива реально створює й завершує Task, архівує та відновлює його через preview/confirm. Fixture не підставляє receipts або нові AuditEvent замість writer: п’ять Task створені й завершені через HTTP, archive/relink також погоджені. Окремі legacy payload і 101 стороння подія явно позначені як синтетичні, не історичне відновлення.

## Фактичні докази та їхня межа

| Доказ | Результат |
|---|---|
| RED_FOCUSED → GREEN_FOCUSED_FIXED | Ті самі сім груп: 0/7 → 7/7. Реальні raw201, відсутні API/поля та format500 залишилися в історичних red. |
| SURFACES_FIRST | 13 явних Task definitions, 16 URL, 774 HTTP cases; 730 пройдено, 44 відмови. |
| SURFACES_PATCH1 | Рівно 44/44 попередні невдалі ключі повторено й пройдено. Reviewer самостійно порівняв множини route/method/role/variant; вони точно рівні. |
| CONTROLS_FINAL | 12/12 явних груп, 104 HTTP. Додано фактичні home/KPI assertions для archive/restore. |

20 format failures усунені підтримкою DRF `format=None`; 24 unsupported-method oracle failures усунені обмеженням `approval_required` саме оголошеними CRUD writers. Це комбінований результат першого прогону та адресного повтору; **нового повного 774-case прогону не було**. 57 field tests збережені, але в цьому підетапі не запускалися.

Дванадцять груп перевіряють дозволений structured history та legacy redaction, поточні/історичні закриті джерела після relink, archive/restore з точним збереженням полів і KPI, позитивний writer, owner/foreign outcome, відкликання ролі, нову session для read без execute, pending/expired без writer, відмову читати чужий action через recovery, keyset pagination/cursor binding, відкликання document capability та technical admin без writes. Тексти закритих результатів і довільний старий payload перевірені canaries. Restore змінює total/done на +1 і зберігає active/process/overdue; no-op не створює Task/Proposal/Audit.

Ці докази отримані на попередньому стабільному backend snapshot. Остаточні backend fixes дати/reopen/довгого assignee_id потребують власних доказів та наступного canonical full verify. Access-файли не змінюють writer, role policy чи міграції й не оголошують повної готовності C01/BoS MVP.
