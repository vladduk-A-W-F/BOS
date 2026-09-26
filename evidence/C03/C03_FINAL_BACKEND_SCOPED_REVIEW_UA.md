# C03 · фінальний незалежний огляд backend

**Погоджено передавання рівно 36 заморожених файлів до інтеграції. Блокувальних зауважень у переглянутій межі не залишилося.** Це консенсус щодо коду та зафіксованих scoped доказів, а не приймання всього C03 або готовності BoS MVP. Обов’язковий спільний full26 після інтеграції залишається попереду.

Огляд 2026-09-12 виконано read-only: без нових тестів, серверів, браузера, A09, міграцій чи читання робочих БД/private media. Canonical і кандидати не змінювались. Попередні checkpoint1/core2 та UI висновки збережені окремо.

## Точна база і цілісність

| Об’єкт | SHA-256 / commit |
|---|---|
| C01 база | ed3a299a6c497ed89ca98f12a0957b7d3fb9cdf2 |
| FINAL_MANIFEST.json | ac16a12c05e082828bc7a766e2df7773798c46c9fa70712d71fa5977ddb15b0b |
| Сукупність 36 source SHA | 625e41f5327fbe9bcd0d53f9a1557a2a9a19b94abc7e78f20c775a9d81cc63d4 |
| Погоджений CORE_CHECKPOINT_2.json | f5b2a962b1e70fa959c83b9ea8571337256d9837ba447ac69e17006d49bf02f2 |
| Попередній незалежний core2 review | b2e264f42ac9766c7ad382625edfca12f236c30e15ba5cf3e8f5bcbb021a1cde |
| Фінальний operations/views.py | 2ca2e6ce48586ab953060816a66ab53d4d801bc176e5737b4ad09232a39190ea |

Незалежно перевірено всі 36 `frozen_source` файлів, усі 36 `base_sha256` проти `git show` зазначеного C01 commit, усі 22 evidence entries та чотири external SHA. Невідповідностей немає. 22 evidence entries — це 15 журналів та сім документів/маніфестів/diff, а не 22 окремі прогони. Сукупний source SHA відтворено як SHA-256 sorted compact JSON карти path→SHA. Три access і чотири G5 файли точно збігаються з відповідними окремими frozen manifests.

## Закриття названих прогалин core

Висновок core2 залишається чинним: наступне рознесення через `existing_transaction` того самого фактично bound ID дозволено без переписування першого binding snapshot; summary приймає status; import current_summary містить scoped currencies; export містить джерела/IDs/поточний статус; один historical payment Event не допускається двічі під різними keys у тому самому preview. Перевірені source permanence, global identity/replay між CEO, окремі cash/payment ефекти, незмінність bound Transaction, source-byte tamper та exact Decimal currency layers не змінені фінальною дельтою.

Серед 21 checkpoint2 source positions змінились лише product `operations/views.py` і додавання двох методів у `finance/test_statement_integrity.py`. Продуктова дельта прибирає тільки `<=1MiB` умову, яка заважала класифікувати валідний завеликий C03 JSON як 413. Межа дії 30000 bytes та глобальні Django/upstream ліміти не підвищені; malformed JSON і чужі actions залишають попередню generic поведінку. Класифікація відбувається до domain validation/proposal.

`body-upper-before.log` фактично має 422 замість 413 для C03 reason понад 1MiB; інший новий presented-stream метод уже тоді green. У фінальному журналі обидва green. Stream proof викликає справжній pre_body із реальною авторизованою особою: missing/forged Content-Length читає рівно MAX_BODY+1, відмовляє 413; коротший за declared body дає 400; manager отримує 403 до read. Це перевірка Django-presented stream, а не довільного зовнішнього HTTP framing або виправлення історичної A09 13MiB проблеми.

## Історична схема, збереження даних і fixtures

`TEST_COMPATIBILITY.diff` незалежно побудовано з фактичних frozen bytes проти C01 commit для шести файлів: результат буквально збігається з наданим diff. Старі assertions про rows, IDs, гроші, склад, файли, sequences, receipt і replay не вилучені.

Чотири typed-transfer fixtures вимагають **точно 56 таблиць**: попередні B03 53 плюс лише `finance_statementimport`, `finance_statementline`, `finance_statementallocation`. Очікувана множина задана явно, а не виведена з випадкового фактичного schema. Старі B02/B03/C01 populated cases зберігають власні позитивні anchors та всі решта перевірок.

У genuine historical A08 source додано finance0007 до вже чинного tasks0004 pin: finance0008 інакше повторно підтягувала ERP0005/operations0006. B03 historical reverse fixture отримав такий самий finance pin у власному issued child DB **до** old before-state. Helper перед цим явно вимагає, щоб усі три statement ledgers були порожні. Заповнені snapshots/receipts не очищаються; product migration guards не послаблено. Старий populated-six-ledgers reverse oracle збережений.

Нова finance0008 є additive. Її останній RunPython виконується першим при reverse і відмовляє при будь-якому populated StatementImport/Line/Allocation до DDL. Новий actual child порівнює всю схему, rows, sequences та migration recorder до/після відмови. Інший child справді створює Transaction на finance0007 через historical apps, піднімає й видаляє synthetic ID70001, проходить 53→56→53→56 і вимагає наступний business ID70002.

Єдина виправлена помилка нового migration oracle: реальний INSERT у `django_migrations` піднімає його high-water на **рівно 1**. Поправка не дозволяє змінювати жодну business sequence; після reverse всі recorder rows знов буквально старі, high-water не зменшено. Це не послаблення попереднього baseline тесту.

Populated C03 typed child створює один Import/Line/Allocation через controlled HTTP, перевіряє exact56, manifest tables/sequences/media/media_references/logical_schema_hash, literal binding JSON і дві збережені receipts. Source snapshot SHA та source database state незмінні. Після двох same-ID replay допускається тільки точна `operations_configuration.erp_write.value.revision +2`; усі інші поля/rows, schema і sequences порівнюються повністю.

## Фактичні результати, без змішування прогонів

| Доказ | Фактичний результат |
|---|---|
| integrity-before → integrity-after-1 | Названі core defects зафіксовані; 10/10 green після виправлень |
| duplicate-payment-before | Preview200 замість 422; відповідний метод green у core20 та final23 |
| command-limit-before / body-upper-before | 422 замість 413; обидві межі green у final23 |
| preservation-before | 11 old methods, 6 failures через explicit table set та historical dependencies |
| preservation-after-1 | Усі 11 old methods green; єдиний failure серед 12 — новий child recorder60≠59 |
| final-focused-1 | 23/23 top-level, 12.304s: 22 бізнес/parser/integrity методи та один harness із 3 actual child methods |
| Фінальні child markers | Exact53→56, old70001→new70002; populated reverse unchanged; exact56 typed і 2 literal receipts |

SHA `final-focused-1.log`: `0b38c4dbff98e405a6f9c0edb7c64867bedeb1cf955f6e2d61dd88c2632d2c19`.
SHA `preservation-after-1.log`: `5cdfc1de82851ccad906911a83183e558c100a65196b6a976a4d3baa693b9c5a`.
SHA `body-upper-before.log`: `c5c179cd1addf471750729029a402da3bf28acf57b80fdd930ba30acd52a601e`.

Фінальний авторський звіт чесно зазначає два наступні пояснювальні коментарі у test-only fixtures. Їхні frozen bytes перевірені source review; новий повтор запуску тільки заради коментарів не потрібний. SQL AFTER INSERT Transaction.amount fault реально відтворено з rollback409; окремий Invoice-trigger fault не виконувався і не заявляється.

## Access, G5 і сумісність із UI

Прочитано окремий незалежний access review SHA `958b8ad0b4e8f39de5b4a031c79e6ea628a129b34cfd610f7fe3bdbaad51a632`: exact three-file manifest `23c9bbdc8cb01835d2bc20327034e4be41ac7542b9ad2ea3c11b2339622c649e`, старі 180 route objects/57 fields/C01 12 controls збережені. Його послідовні targeted докази закривають три initial failures; **нового повного 504/504 запуску на checkpoint2 немає**. Це не перетворено на загальний access pass.

Прочитано незалежний G5 review SHA `45b11bc1b5e2bb1f17965f8144fb3081099d7e0fdc9602a669facce30ae37ac4`: exact four-file manifest `66a68868fab1ee68871e2a8a66134d8bd133a91f9634be5662b485e6ce483237`. Фактичний scoped SQLite runner має **109 methods / 116 ERP records / 35 actions**, додатково три held records; old baseline104/110/33 збережений. Held PATCH→reconcile у SQLite довів controlled conflict/stale, а не PostgreSQL row-lock waiting. PostgreSQL не прийнятий за цими даними.

Фінальний wire `143a7ad87936c4a1671c26fe4b3945d8d41262ea5ad00d8c8cb0efcb082ef881` та UI source `78136013163756fa033e59726a1296dc8c0938850621cfc7b093ce1ea7c1886a` сумісні в перевірених checkpoint2 уточненнях: literal upload metadata/format/parser; first-document domain replay за source identity SHA; current_summary.currencies плюс збережені lines; summary status; 19-column export link; наступний same-bound existing Transaction; opaque підписаний candidates cursor. UI не вимагає вигаданої created_at для Invoice/ImportIdentity.

Первісний UI manifest посилається на старий wire53bd7af9, тому ця сумісність зафіксована як **додаткове читання source**, не як переписування історичного UI proof. Його 37+5+9 extracted-JS checks, 189 protected declarations та Babel proof залишаються саме своїми scoped доказами. Це не actual browser/API інтеграція; root-owned native/E2E та повний full26 оцінюються окремо.

## Межа приймання

Погоджено exact-SHA інтеграцію backend36 та названих адаптерів. Немає відкритого конкретного blocker цього review. Не заявлено повного C03/MVP приймання, production readiness, PostgreSQL, Windows/Python3.15, CI, browser acceptance або усунення A09 нестабільності. Наявні зовнішні/операційні блокери не змінюються цим висновком.
