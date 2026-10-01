# Включення актуалізованого плану єдиним інтегратором

Прямий запит власника: «исполни актуализацию плана». Контролер підготував CURRENT_PLAN_UA.md у цій папці; незалежний reviewer перевіряє його точні байти. Канонічне дерево контролер не змінював. Мета цього пакета — фактично оновити чинний план і його покажчики, не обмежитися ACK.

Вхідний canonical HEAD на свіжій звірці — dec599752d2703e18dc9b53fbf2e2585b0ede3e0, clean. Remote main — 87e1a4f504d24f6d47add511eb8b68a7fa592efc, PR10 merged; відкритих PR до main немає. Перед застосуванням root звіряє свій актуальний HEAD/dirty state; жодних reset/amend або відкидання чужих змін.

1. Включити прийнятий датований current-розділ у docs/orchestration/bos3/ACTIVE_WORK_PLAN_RU.md. Старі записи залишити як історію або зберегти точним архівом із SHA. Старі формулювання «PR10 draft», «наступна картка очікує допуску», «writer/design map не прийнято» не мають лишатися чинною верхньою сводкою.
2. У RELEASE_PLAN_RU.md оновити поточну сводку й посилання на active plan. Повний погоджений обсяг, gates, дата 04.10 23:59 Berlin, false readiness і всі межі залишаються.
3. У STATE.json відобразити чинний BoS3 active_workstream/next_action та окремі canonical/published/immutable pins. Історичні V17/V18 freezes/PR8/source зберегти з явним історичним scope. Не перетворювати чинний вузький source-допуск на blanket product_execution/CI/deploy/production permission.
4. У QUEUE.json актуалізувати current BoS3 pointer/next action/delivery gate. Не перебудовувати історичний tasks backlog, не знімати чужі claims, не змінювати automatic_execution_allowed/ліміти заради статусу.
5. У CONTROL_STATE/операційному delta та current stage синхронізувати фактичні призначення: UI WIP, два contract outputs у роботі, quality чекає exact результат, runtime decision окремо. Прийнятий UXD04 trace не повертати в executable queue. Native observer goal blocked не підміняти старим usageLimited або ACTIVE; root goal обліковується окремо.

Документ є зрізом на00:38 Berlin. RECOVERED_STATUS.json містить пізнішу окрему native звірку active/inProgress для main/design/writer/enablement. Внести цю подію окремим operational записом. Авторські commentary/чернетки не перетворювати на independent acceptance. WIP HTML уже змінюється; його спостережений hash не є final result pin. Фінальний pin береться тільки з exact результату автора й review.

Продовження перерваних задач root уже передав через main. Не надсилати його вдруге через цю актуалізацію; не скидати існуючі копії. Нові контрольні точки від root:00:55/01:15 Berlin. Пакет оновлення плану не змінює product/runtime й не дозволяє повтор діагностики Windows.

Після включення: metadata JSON parse, path/hash checks, git diff --check, незалежна перевірка лише нової структурної дельти за потреби; один документаційний commit і окремий новий PR у межах чинного дозволу на публікацію. Не зливати в main цим пакетом. Повернути exact applied receipt із files/hash, commit/branch/PR і розділенням applied/published; delivery ACK цим не є. Продуктові автори продовжують свою вже допущену роботу паралельно.
