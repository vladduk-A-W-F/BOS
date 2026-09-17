# C03: адаптація перевірок доступу

Готово до копіювання рівно трьох access-файлів. Canonical, backend, UI та історичні докази не змінював. Остання власна копія містить immutable author checkpoint 2 (package `6387158eb680adbe635608d49e9dbdeb6d64b66630705d1e6903e6aaea668b27`) плюс три наведені у FINAL_ACCESS_MANIFEST.json адаптери. BOS_PACKAGE.json описує вихідний пакет автора, а не похідну копію адаптерів.

## Незмінні вимоги

- 180 попередніх route objects залишилися буквально незмінними; додано рівно 10 погоджених definitions, підсумок 190. Вісім Django statement routes без .json; два DRF transaction-summary definitions із .json.
- Усі 57 required field IDs незмінні. Цей вузький запуск не виконував їхню suite.
- 12 C01 controls, їхня функція, глобальний state_digest та старий positive admin helper буквально незмінні. Остаточний C01 UI/wire review збережений окремо без перезапису.
- Нові три фінансові ledger models не зареєстровані в admin. Старий native finance admin залишається; захищену source-bound Transaction реально перевірено через нього.

## Дані й додані перевірки

Fixture використовує реальні upload → review → import → reconcile preview/confirm. Три income lines EUR 17.39, USD 123.45, UAH 9801.07 звірені з відповідними synthetic invoices. Четвертий outgoing line зв'язаний із реальною вже сплаченою synthetic Salary та її Transaction, без дублювання грошей. Окремі source markers, request/task FK й завершена історія Task створюють контроль доступу до поточних та історичних джерел. Legacy label/revision mutations існують лише як явні негативні fixture-кейси у rollback.

12 додаткових контролів охоплюють original bytes/SHA/receipt; permanent marker; immutable imported-source history і revision lineage; старі task/history/context/export paths; повністю приховані statement-linked Transaction і Salary; export/download permissions; незмінність Transaction через REST та admin; archive/restore без втрати валютних totals; exact replay; незалежні Decimal projections; filters/cursors; malformed upload та source-code reuse denial.

## Фактичні результати й межі доказу

| Evidence | Результат | Межа |
|---|---|---|
| RED_FOCUSED.json | 1/8 green, 7/8 red, 7 HTTP | C01 base до C03; реальні відсутні маршрути і permanent-marker gap |
| GREEN_FOCUSED_CORE_ONLY.json | 8/8, 34 HTTP | Exact checkpoint 1 до повернення нових трьох adapters; початкові 8 вимог |
| SURFACES_FIRST.json | 503/504 surfaces; 10/12 controls, 127 control HTTP | Exact 10 new definitions / 11 concrete URLs; п'ять ролей, дев'ять methods, додатковий no-export |
| REPLAY_DIAGNOSTIC.json | 5 literal-equal confirms і 2 no-change previews | Повний diff усіх business models; лише mutex revision +1 на confirm |
| CONTROLS_TWO_FIXED.json | 2/2, 11 HTTP | Два виправлення власного runner на checkpoint 1 |
| EXPORT_EXACT_RED.json | CEO export red | Старі 8 CSV колонок не проходять точний погоджений refs/status oracle |
| AFFECTED_CHECKPOINT2_GREEN.json | 2/2 controls, 11 HTTP + CEO export 1/1 | Checkpoint 2; повторені лише попередні три failures |

Це послідовний evidence chain, а не новий єдиний 504/504 або fullgate запуск на checkpoint 2. Після виправлень не залишилося відкритих failures цього bounded access scope. Root окремо виконує остаточну інтеграційну перевірку. Browser, fullverify, migration/restore/fullgate, A09 13MiB чи Gate 6 тут не виконувались.

## Пояснення трьох точкових змін oracle

1. Native admin: старий positive helper навмисно попередньо валідує змінену форму. Для source-bound record він закономірно зупинився ще до HTTP. Новий окремий C03 control бере всі реальні native form fields, підтверджує валідність незміненої форми, потім змінює description та надсилає HTTP. Відповідь має містити помилку незмінності; повний domain digest незмінний. Старий helper не змінено.
2. Replay: actual diagnostic довів точний єдиний diff — operations.Configuration pk=3/key=erp_write/value.revision 30→31→32→33→34→35. Це погоджений старий ERP mutex. Control зберігає всі rows усіх models і дозволяє лише +1 цього поля на кожен confirm; решта Configuration, Event, Proposal/receipt, Line, Allocation, Payment, Transaction, Audit та всі інші rows мають бути тотожно незмінні. Обидва no-change previews перевіряють повністю незмінний state_digest.
3. Export: початковий generic positive anchor очікував source_system/account_ref. Остаточний погоджений CSV wire передає import_id/line_id/document_id/source_sha256 і first-source refs замість цих текстових полів. Anchor уточнено під конкретний wire, а перевірку посилено до всіх 19 колонок, усіх 4 рядків, exact source references/transaction IDs/current status/allocated/unallocated. Старий export з 8 колонками зафіксовано RED саме цим фінальним oracle, новий — GREEN. Original source download/bytes/SHA незмінні.

Початковий check_focused.py відрізняється від RED runner лише кодом source fixture C03-RED-SOURCE, щоб не конфліктувати з новим A04-C03-SOURCE; очікувані вісім поведінкових перевірок не зменшувалися. Read-only checkpoint copy спочатку відмовив у перезаписі adapters через файлові права; core-only8 доказ явно відокремлений. Після цього chmod застосовано лише до власних трьох файлів, перевірено точну різницю з авторським пакетом.
