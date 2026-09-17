# C03 G5 · незалежний огляд чотирьох файлів

**Рішення: погоджено в межі фактичного scoped SQLite G5 та source/evidence review. Блокувальних прогалин у переданих чотирьох файлах не знайдено.** Загальний C03 full acceptance і PostgreSQL цим висновком не замінюються.

Оглянуто FINAL_MANIFEST.json SHA `66a68868fab1ee68871e2a8a66134d8bd133a91f9634be5662b485e6ce483237`. Робота read-only: не запускалися тести, Django, API, база, браузер чи fullverify; не читались SQLite/private backup/media; canonical і candidate не змінено. Новий артефакт — лише цей звіт.

## Provenance

| Файл | Перевірений SHA-256 |
|---|---|
| finance/test_statement_concurrency.py | d216e553b1dba7e2044e0035f8ba2960c22f2b74c756e9599d6067705e7dcd04 |
| scripts/check_concurrency.py | a633790452d52d74abb720b8d616f981b7197e9fc2f3fd817699c2ea47581f3d |
| scripts/concurrency_manifest.json | c69d36fadbdeb5c30430ba3faf4d96792853ecdecff64ef3e99bb14cae971bb7 |
| erp/test_concurrency.py | b0730a1ad57327bc1cb84f55f2040e022cd2365b1a6cddd7ba3c4e405a0e3897 |

Усі чотири top-level deliverables збігаються з відповідними файлами фактично виконаної `source/` копії. Усі 11 evidence SHA і SHA авторського SCOPED_REVIEW_UA.md збігаються. У GATE5_1.json усі 12 source-hash позицій до/після виконання тотожні поточним reviewed bytes.

Base CORE_CHECKPOINT_2.json має погоджений SHA `f5b2a962b1e70fa959c83b9ea8571337256d9837ba447ac69e17006d49bf02f2`, package source `6387158eb680adbe635608d49e9dbdeb6d64b66630705d1e6903e6aaea668b27`. Незалежно перевірено SHA всіх 304 code-package файлів бази та 7 fixture supplement; невідповідностей немає. У похідному source від базових 304 відрізняються рівно три заявлені старі файли; четвертий новий finance/test_statement_concurrency.py раніше відсутній. Сім supplement незмінні. Дані SQLite не входять у ці 304 перевірені source files і під час огляду не відкривались/не хешувались повторно.

## Незмінний каталог

`baseline_c01` точно дорівнює попереднім test_labels, required_test_ids, erp_schema_actions, erp_coverage_manifest і required_erp_pass_records. Його canonical SHA `0910ff83b62173df7eedfd4c1cfb1f52fefe178c265f3e2915d7fce6da9ee214`: **104 методи / 110 records / 33 actions**. baseline_a06/b02/b03 та всі їх coverage objects збережені дослівно як дані. Жодного старого ID чи oracle entry не прибрано.

Повний diff erp/test_concurrency.py становить **один schema-set assertion рядок**: union доповнено statement_import і statement_reconcile. Інші bytes файлу, включно з оригінальним COVERAGE_MANIFEST, незмінні. Нові дві coverage entries беруться з окремого модуля і об’єднуються тільки runner, після чого порівнюються з явним manifest.

Додано рівно п’ять методів: same-ID import, same-ID reconcile, distinct import proposals/one source, distinct reconcile/global allocation key між двома CEO, held Transaction race у двох напрямках. Два HTTP action-methods дають ще 6 окремих валютних records; held метод — ще 3 власні explicit records. Поточний каталог: **109 methods / 116 ERP pass records / 35 actions**.

Runner порівнює Counter фактично discovered/started/finished/succeeded IDs із явним manifest, перевіряє відсутність failures/errors/skips/xfail/unexpected-success, точний набір schema actions, власника кожного stdout record та відсутність пропущених/зайвих/дубльованих pass records. Каталог не будується з фактично випадково виявлених тестів. Шляхи імпортованих test modules мають належати reviewed source; code SHA до/після контролюються.

## Реальність одночасних операцій

Переглянуто весь новий test module. Він використовує TransactionTestCase, ThreadPoolExecutor(2), threading.Barrier/Event, окремі Django connections у кожному worker, справжні Django HTTP Clients з CSRF. Source проходить actual upload → review → download exact bytes/SHA → preview/confirm; existing Transaction створюється через справжній finance POST з Idempotency-Key. Production money writer, clock, returned receipt чи суми не підмінено. Незалежні сталі EUR17.39/USD123.45/UAH9801.07 задані до результатів.

Same-ID pairs вимагають хоча б один 200, лише 200/409 на обох запитах, однакові отримані success receipts, один domain effect та незмінність повтору. Import перевіряє один Import/Line/Event і нуль нових Transaction/FinancialIntent/Audit. Reconcile перевіряє одну Transaction/FinancialIntent/Audit за нового cash, одну Allocation, рівно reconcile+child payment Events, точну валюту/суму/контрагента, сплачене Invoice та reference STMT-allocationUUID.

Distinct import proposals з тим самим джерелом мають один первісний receipt. Перше domain reuse може доповнити receipt програного ActionProposal після transport409; тому саме цей крок порівнює domain state без ActionProposal. Наступний same-ID replay вже порівнює повний збережений proposal state. Cross-CEO reconcile визначає справжнього winner, перевіряє його actor у binding/Allocation, один paid/cash ефект, незмінний first_commit_receipt і no-change receipt другого CEO з тими самими Transaction/Allocation IDs. Повтор після actual archive Transaction не створює нову оплату.

Held race не підміняє SQL: execute_wrapper лише записує спробу UPDATE і викликає оригінальний execute. Holder виконує HTTP writer усередині реально утримуваної transaction.atomic, waiter працює в іншому connection. До release перевіряється невидимість uncommitted бізнес-змін; після release — результат, відмова stale reconcile або незмінність уже bound Transaction. Порядок запуску та утримання керується Event, а не випадковим sleep.

## Фактичний результат і межа SQLite

GATE5_1.json: complete=true, runner_failures=0; **109 discovered/started/finished/succeeded**, tests_run109; порожні failures/errors/skipped/expected_failures/unexpected_successes. Method-ID множини збігаються точно. **116 observed/unique records**, без missing/duplicates; **35 фактичних actions** дорівнюють required. Рівно **3 held records** — по одному EUR/USD/UAH.

GATE5_1.log окремо містить `Ran 109 tests` та `OK`. Усі 116 raw A06_PASS і 3 raw C03_HELD_TRANSACTION значення незалежно витягнуто з логу й звірено з report: точна рівність і порядок. Manifest фіксує exit0. Engine metadata: requested SQLite, actual SQLite **3.53.1**, engine_verified=true; окрема нова file-backed check_<uuid> база і її Django test destination. Existing/неізольована база відхиляється runner.

Для всіх трьох валют:

| Послідовність | Фактичний результат | Що доведено |
|---|---|---|
| Held PATCH → reconcile | [200,409], first trace ERP mutex | SQLite повернув controlled conflict ще під lock; повтор same-ID після release дав stale409, paid/Allocation/binding не виникли |
| Held reconcile → PATCH | [200,400], reverse trace Transaction | Waiter реально очікував; після commit відхилив редагування bound source; повтор PATCH400, один cash/payment зв’язок |

Перший напрям у SQLite **не є виконаним доказом PostgreSQL row-lock waiting**: він показав SQLite conflict на ERP mutex. PostgreSQL branch у тесті вимагає waiting і Transaction trace, але цей backend не запускався. Це обмеження чесно збережене у manifest/review; за нього не видано pass.

## Red → green

BASELINE_RED правильно відмовив до виконання тестів через дві нові schema actions поза старим каталогом. FOCUSED_1 містить 6 subtest failures у двох нових методах: очікування повністю готового loser proposal receipt до його першого reuse і вимогу waiting там, де SQLite законно повернув409. Виправлені лише ці нові adapter assumptions: domain state не змінюється; перший reuse може зафіксувати власний receipt; SQLite409 вимагає подальшої строгої перевірки stale/bound state. FOCUSED_2 — 5/5. Після цього GATE5_1 повторно виконав увесь явний scoped набір109 без skips. Backend bytes від бази не змінювалися для отримання цього green.

Дозволена межа висновку: готові чотири G5 файли для exact-SHA інтеграції. Не заявлено PostgreSQL, browser, Windows/Python3.15, A09, backup/restore чи повний інтегрований C03 acceptance. Нових optional tests або коду для закриття цього незалежного review не потрібно.
