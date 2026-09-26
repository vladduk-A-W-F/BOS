# B02 · повторний незалежний огляд UI

12.09.2026 · агент `a11_ui_review`. Перевірено фінальний tmp-кандидат після виправлень root. Попередній звіт `tmp/B02_UI_REVIEW_UA.md` зберігає початкові знахідки; цей документ фіксує їхній стан **на наведеній нижче точній версії**.

**Scoped source-consensus: відкритих блокерів у перевірених нових UI-шляхах не знайдено.** Три початкові знахідки та два вузькі follow-up зауваження враховані в коді. Це не приймання UI у браузері, не доказ інтеграційного HTTP-потоку й не готовність B02/MVP. Backend-кандидат ще має пройти власні перевірки та root integration/full verify.

## Версія й фактична перевірка

| Джерело | SHA-256 |
|---|---|
| canonical B01 `frontend/boss_app_source.html` | `943ed8347c1f0fc3248c5d0483d3a3d46c9d9ad605232b8fd3d278c85325798b` |
| tmp B02 `frontend/boss_app_source.html` | `95cd53cfdea137bcc8635b9da0f7c3aaf502c91bbd4726889f4a9d7dad967abb` |
| tmp B02 `assets/app.js` | `5e6c1fc38538cf648c90acf9519836fae220a0de8fe1a4e53da71a01c70fcf42` |
| `tmp/B02_IMPLEMENTATION_CONTRACT_UA.md` | `055ab9afb15ff95a2a5ecc0fcb2cbc1f71e0fcb413a8cba9ce82bf4394a5aa66` |

Незалежно виконав Babel React transform **у пам’яті** з фактичного JSX. Компіляція пройшла, отриманий JavaScript **буквально дорівнює** вже зібраному `assets/app.js`. Build script повторно не запускав, assets/source не перезаписував. Канонічний source лишився з B01 SHA вище.

Прочитано actual JS regression proof root: `tmp/b02_quantity_result.json` і runner `tmp/check_b02_quantity.cjs`. Runner бере старий receive-вираз та нову функцію безпосередньо із source; expected strings задані незалежно. Proof посилається на ту саму фінальну source SHA. Це реальне виконання ізольованої JavaScript-функції в Node, **не браузерний тест**. У цьому read-only огляді runner повторно не виконувався.

## Результат за знахідками

| Знахідка | Стан на фінальному source | Доказ виправлення |
|---|---|---|
| B02-UI-01: reset/Escape втрачали unknown proposal | **Виправлено на рівні коду** | До першого confirm ID записується в sessionStorage; reset не видаляє queue; при повторному відкритті відновлюється той самий proposal; HTTP non-OK, включно з5xx, лишає unknown; actual succeeded/GET batch receipt очищає запис цього batch |
| B02-UI-02: пізній snapshot відкривав inspector після Escape | **Виправлено на рівні коду** | Parent opener приймає predicate й перевіряє його після await до setData/setSelection; accepted cancel і close синхронно ставлять alive=false та abort до parent onClose |
| B02-UI-03: дробовий receive preset мав зайві знаки | **Виправлено у source; є окремий Node proof root** | `purchaseRemaining()` віднімає цілі thousandths через BigInt, повертає canonical Q3; обидві receive кнопки та нова imported source-картка використовують функцію |
| Follow-up: alive змінювався лише у passive effect cleanup | **Виправлено на рівні коду** | Guard інвалідовується синхронно в onCancel/onClose. Під час active confirm Escape навмисно prevented; наступна unknown-відповідь лишає ID для відновлення |
| Follow-up:20 нерозв’язних pending блокували всі нові confirm | **Виправлено на рівні коду** | Прибрано slice(0,20) і штучну capacity20 відмову. Pending не видаляються через припущення про фінальний стан; browser storage failure зупиняє новий confirm до HTTP POST |

Вилучення ліміту20 не означає нескінченне сховище: фізична quota браузера існує. Обробка quota явна, не знищує історію непідтверджених намірів і не відправляє нову операцію, якщо її ID не вдалося зберегти. Це прийнята мінімальна межа, а не нова система довготривалого чергування.

## Збереження наміру й відновлення

- Ключ будується через `bosStorageKey('initial-import-pending')`: scope за поточними mode/user/role в межах browser origin/tab. У storage потрапляють proposal_id, batch_id, namespace і expires_at; файл, гроші, mappings або повний payload там не дублюються.
- Запис відбувається **до** confirm POST. Неуспіх запису storage блокує цей POST з видимою помилкою. Для вже збереженого proposal повтор використовує попередній UUID.
- «До файла» очищає поточний report/помилку, але queue лишається. Панель pending дозволяє свідомо відкрити старе погодження або виконати GET `/api/erp/import/batches/<batch_id>/`.
- GET-recovery показує `first_commit_receipt`, не конструює success із клієнтського стану. Після успіху доступні справжні mappings та повний export; сучасні зміни дивляться через свіжі картки.
- Stale/expired/404 не видаються за performed чи за гарантовану відсутність старого commit. Вони лишаються pending для явного перегляду/повторного імпорту того самого джерела.
- Queue не динамічно модифікує незмінний серверний receipt. `replay` — локальна ознака `report.first_commit_receipt`; історичні source/live-before/live-after в receipt лишаються історичними.

**Точна межа відновлення:** sessionStorage зберігає queue після закриття **діалогу**, не гарантує його після закриття вкладки/очищення даних браузера. Текст UI тепер прямо називає поточну вкладку. Для повторного відтворення semantic payload після втрати вкладки потрібен оригінальний файл **і ті самі явні UI bindings**, якщо вони додавалися окремо: незмінений файл не містить цього multipart sidecar. Це обмеження треба врахувати в інструкції; воно не блокує перевірений сценарій відновлення в поточній вкладці. Автоматичного durable background replay тут немає й не заявляється.

## Закриття, пізні відповіді й actual record IDs

`onCancel` приймає Escape, коли не виконується confirm: одразу `alive=false`, abort локального request, потім native close. `onClose` повторно робить цю інвалідацію перед parent callback. Effect cleanup лишається додатковим захистом.

Parent async opener отримує predicate саме від екземпляра діалогу. Після snapshot await він перевіряє predicate **до** застосування даних/selection; закритий старий діалог не може відкрити новий inspector. Перевірки та наступні setState не розділені другим await. Це також захищає сценарій «закрив старий імпорт, відкрив новий» від відповіді попереднього екземпляра.

Кнопки «Відкрити» з’являються тільки після receipt і з фактичним target_id. Mapping sales_line перетворюється на фактичний order_id зі свіжої line; решта entity відповідають contracts counterparty/item/location/lot/order/purchase. Preview create rows не отримали fictitious ID. Якщо target недоступний, active dialog показує помилку; source-review не перевіряє реальну server visibility.

## Точна кількість і суми

`purchaseRemaining(quantity,received)` приймає звичайний невід’ємний десятковий рядок з0–3 десятковими знаками, переводить його у BigInt thousandths, перевіряє невід’ємність результату й повертає рівно3 знаки. У кількісному payload немає binaryfloat subtraction. `erpNum` використовується лише для показу готового Q3.

Root Node evidence: старе0.300−0.200 дало `0.09999999999999998` (red); нове — `0.100`. Шість явних green-cases включають5−2,0.001−0,2.125−1.875,999999999.999−0.001 та рівність. Від’ємний залишок відхилено. Це достатній вузький доказ знайденої arithmetic регресії; він не підтверджує browser/native form/server acceptance.

`ImportTotals` зберіг попередню коректну поведінку: server Decimal strings показуються буквально, money рядки окремі за EUR/UAH/USD, без сумування валют чи перерахунку через Number. Raw scale5 і movement scale2 лишаються різними показниками. Фізичний/доступний stock розділено за item/location/unit/revision/currency. Source controls, new delta і живі before/after не змішані; після receipt їхні назви відповідають історичному першому commit.

Imported `PurchaseSource` продовжує пояснювати original / до зрізу / перенесено / після зрізу / залишилось. Не вигадує старих Movement, нове погодження постачальника чи0 замість недоступного historical value. В обох imported receive точках preset тепер canonical Q3.

## Явні bindings і файли

R7 gap попереднього огляду частково закрито реальним вузьким редактором: користувач задає entity (`counterparty/item/location`), зовнішній ID і вибирає наявний запис за code/name. Зміна entity очищає target; порожні поля позначені required. Замість перезаписування raw input File UI додає окремий multipart part `bindings` з JSON array. Inputs disabled під час активного запиту; server errors лишаються видимими в modal.

Перевірено точний relevant backend source `tmp/b02_candidate/source/erp/import_views.py`: parser виділяє optional `bindings` part, вимагає list і додає його до bindings JSON batch або CSV manifest. Отже назва/тип sidecar збігається з погодженим доповненням. Це **читання двох сторін контракту**, не виконаний HTTP-test; duplicate IDs,100-row/bytes limits, permissions і canonical SHA має довести backend suite. У документі implementation contract цю sidecar-деталь варто зберегти явно поряд із попереднім wire addendum.

Файл користувача лишається raw File, без JSON.parse/rewrite. JSON template — один JSON; CSV template — manifest і окремі files[].content_utf8, кожний завантажується власною кнопкою. Template wrapper не використовується як manifest, ZIP не з’явився. Human owner picker лишився для synthetic template. Вибір відомого target у bindings не є автоматичним matching за назвою; eligibility перевіряється сервером.

Bindings, які користувач додав у формі, живуть у поточному діалозі, а не у pending queue. Збереження canonical source й повного журналу після commit забезпечує server export, не browser state. UI не претендує на імпорт усіх можливих клієнтських форматів.

## Межі висновку й наступне приймання

Незалежно підтверджено тільки source diff, узгодженість вузького bindings wire й точний Babel output. Root надав окремий actual Node red→green arithmetic proof з перевіреним source SHA. У цьому проході я не запускав site, DB, браузер, HTTP-сценарії, playwright або install; не редагував canonical/candidate.

Наступні обов’язкові фактичні сценарії після backend freeze: JSON і CSV preview/confirm; row422; semantic totals mismatch; actual lost confirm reply → same-ID retry/GET receipt; same batch replay після нового receipt; late record GET + Escape; role/session change; bindings duplicate/mismatch; міжвалютні exact totals/export. Браузерні390/768/1440,200%,keyboard/Escape залишаються **НЕ ЗАПУЩЕНО** за вже зафіксованим A11 блокуванням. Наявність відповідних handlers не є pass gate10.

Цей source-scoped consensus дозволяє координатору перейти до інтеграційної перевірки замороженого кандидата. Він не закриває B02, A11, PostgreSQL/Windows або загальний MVP acceptance.
