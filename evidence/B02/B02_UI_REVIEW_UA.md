# B02 · незалежний source/UI огляд кандидата

12.09.2026 · агент `a11_ui_review`. Межа: diff tmp-кандидата проти канонічного B01, компоненти `InitialImportDialog`/`ImportTotals`, imported `PurchaseSource`, ERP toolbar та перехід із receipt у картку. Контракт: `tmp/B02_IMPLEMENTATION_CONTRACT_UA.md`, включно з останнім wire addendum (`mappings`, вкладене `proposal`, JSON file multipart та чотири import routes).

**Поточний результат: потрібні виправлення трьох конкретних функціональних місць перед source-consensus.** Це не браузерне приймання. Backend B02 ще реалізується; інтеграцію з його відповідями тут не запускали. Нічого не змінено у canonical, кандидаті, БД або build assets. Виконана лише незалежна Babel-компіляція в пам’яті, результат звірено з уже зібраним `assets/app.js`.

## Відбиток перевіреної версії

| Джерело | SHA-256 |
|---|---|
| canonical `frontend/boss_app_source.html` | `943ed8347c1f0fc3248c5d0483d3a3d46c9d9ad605232b8fd3d278c85325798b` |
| tmp B02 `frontend/boss_app_source.html` | `349a3e47daa249cbbffff72be0683f02e16a0980526dd73bae64c64bd010fd82` |
| tmp B02 `assets/app.js` / незалежний in-memory compile | `5c100665821497211a863923cc9be8a3c21630c587ad4e4dd5620e919c7e7070` |
| B02 implementation contract | `055ab9afb15ff95a2a5ecc0fcb2cbc1f71e0fcb413a8cba9ce82bf4394a5aa66` |

`tmp/b02_ui_candidate/B02_UI_BASE.json` посилається на ту саму canonical source SHA. Babel React transform пройшов; `generated_js_matches=true`. Це не виконання React/DOM/HTTP і не mock-UI приймання.

## B02-UI-01 · невідомий результат confirm можна стерти

**Статус: BLOCKER у перевіреній версії.** `confirm()` зберігає `report.proposal.id` при timeout/network/невалідному success і ставить `uncertain=true` — правильна основа. Проте після завершення busy кнопка **«До файла»** завжди доступна й викликає `reset()`, де `setReport(null)`/`setUncertain(false)`. Escape поза активним `busy==='confirm'` також закриває діалог; його unmount втрачає report. Точний proposal ID з невідомим результатом більше ніде не збережений.

Окремо: parseable HTTP5xx йде через `!r.ok → setError → return`, тому не встановлює uncertain, хоча відповідь посередника/помилка відповіді сама по собі не доводить відсутність commit. Навіть тут same ID лишається у відкритому діалозі, але reset/close його знищують.

**Сценарій:** сервер записав batch → відповідь не отримана/timeout → UI показує «повторіть це саме погодження» → користувач натискає «До файла» або Escape → повторити саме цей ID вже неможливо. Backend external-ID replay є додатковим захистом, але не виконує UI-контракт збереження pending intent.

**Потрібне виправлення:** зберігати pending proposal+batch identity поза життям цього діалогу та відновлювати його при поверненні, або явно блокувати руйнівний reset невідомого результату до його звірки. Закриття не повинно непомітно видаляти unresolved intent. Урахувати 5xx як unknown; definitively rejected/stale відповіді відокремити. Не генерувати новий proposal автоматично для повтору. Якщо використовується durable client state, прив’язати його до поточної інсталяції/користувача, не відновлювати для іншої identity; payload/комерційні дані без потреби не зберігати.

**Oracle для подальшої перевірки:** один і той самий UUID у всіх повторних confirm після втрати відповіді, включно з поверненням у діалог; одна committed історія/receipt; «До файла» не скидає unresolved intent; 409 stale не видається за success. Після явного succeeded старий receipt доступний, новий імпорт можливий.

## B02-UI-02 · пізня відповідь картки скасовує Escape

**Статус: BLOCKER у перевіреній версії.** `InitialImportDialog.openRecord()` викликає `await onOpenRecord(row)`. Фактичний async callback знаходиться у parent ERPWorkspace: `await erpFetch('snapshot/')`, потім без cancellation/generation check виконує `setData`, `setInitialImport(false)`, `setSelection`.

Під час `busy==='record'` Escape дозволений, але `onCancel` abort-ить лише controller із локальної `request()`. Parent `erpFetch()` до нього не належить. Guard `alive.current` стоїть тільки в child catch/finally і не захищає parent `setSelection`.

**Сценарій:** receipt → «Відкрити» → повільний snapshot → Escape → діалог закрився → snapshot відповів → inspector відкривається всупереч скасуванню користувача. Можлива також пізня відповідь попереднього відкриття після повторного входу в імпорт.

**Потрібне виправлення:** передавати signal/generation або повертати дані з parent без побічного відкриття; перед застосуванням snapshot і `setSelection` перевіряти, що саме цей запит/діалог ще чинний. Close/Escape/unmount мають інвалідовувати застосування відповіді синхронно; нового inspector після скасування не має бути. Не достатньо додати guard лише після `await onOpenRecord`, бо parent уже виконав зміну.

**Oracle:** Escape під час record GET не відкриває inspector після будь-якої пізньої відповіді; повторне свідоме «Відкрити» отримує свіжий snapshot і справжній ID. Відмова GET показується в активному діалозі, не за ним.

## B02-UI-03 · дробовий імпортний залишок дає невалідний receive preset

**Статус: успадкований функціональний BLOCKER для нового B02 imported-PO сценарію; вираз існував у B01.** Це не новий глобальний A11 аудит. Новий профіль офіційно допускає Q3 залишки, але в purchase table та inspector receive preset досі:

```js
quantity: String(Number(r.quantity) - Number(r.received))
```

Для quantity `0.300` і received `0.200` JavaScript формує `0.09999999999999998`. Точний backend `erp.service.number(..., places=3)` відхиляє такий payload. `erpNum` маскує проблему в тексті («0,1»), але не виправляє рядок у preset. Приймання з кнопки для законного дробового залишку не працюватиме без ручного виправлення.

**Потрібне виправлення:** одна точна Q3-різниця для нового потоку й обох його receive кнопок; наприклад, розбір canonical Q3 у цілі thousandths і форматування результату як Q3. Не використовувати округлення money або зміну backend tolerance. Вхідні original quantities/received не переписувати.

**Oracle:** Q0.300−received0.200 → wire quantity`0.100`; інші межі0.001/великий припустимий Q; жодного exponent/зайвої точності. Видимий залишок і запропонована quantity однакові, валюта не бере участі в кількісному розрахунку. Інші старі ERP arithmetic місця не включені в цей scoped review.

## Що відповідає поточному wire-контракту

- Preview передає **оригінальний File**, без `JSON.parse`/перезаписування завантаженого джерела. JSON multipart part=`batch`, CSV part=`manifest` + `rows_<known entity>`. Заголовок multipart Content-Type не заданий вручну, браузер має додати boundary. Наявний global fetch wrapper додає CSRF до `/api/` POST.
- Використано саме `report.proposal.id`, а не верхньорівневий ID; confirm містить `{proposal_id, confirmed:true}`. `lock.current` перекриває подвійне натискання поки запит активний.
- HTTP422 з `errors`/`valid=false` потрапляє в report; row/field/external ID/message відображаються **всередині modal**, а загальна помилка має `role=alert`. Для create-row немає вигаданого clickable preview ID.
- Response/receipt читаються з `mappings` і `counts`. Кнопки карток дозволені тільки після receipt і з actual `target_id`. Sales line відкриває фактичне order_id через свіжу line зі snapshot. Зіставлення entity→target kind відповідає контрактним типам; lifecycle помилка цього переходу описана UI-02.
- `ImportTotals` показує money як серверні decimal strings; не використовує Number, додавання валют або форматування до втрати scale5. Currency — окрема колонка; stock містить item/location/revision/unit/currency, quantity/physical/available окремі.
- Source controls, planned/committed delta і before/after розділені. Після receipt shown totals — історичний first receipt; текст відсилає за сучасним станом у картки. UI не додає динамічний replay flag у receipt. `first_commit_receipt` з preview використовується лише як локальна ознака повтору.
- JSON template завантажується одним файлом. CSV template wrapper розділений: manifest JSON і кожний `files[].content_utf8` як окремий CSV за власним натисканням. Wrapper не підмінює manifest, ZIP не використано. Owner вибирається за іменем і передається template endpoint як ID.
- Imported `PurchaseSource` має окрему українську гілку, original/pre-cutover/remaining/post-cutover/outstanding. Необов’язкові недоступні historical values фільтруються, а не показуються як0. Підстави й ціна обмежені `commercial`; первинні документи більше не називаються пропозиціями. UI не створює supplier confirmation.
- ERP toolbar показує імпорт тільки CEO. Це лише зручність UI; actual server role checks чотирьох import routes мають бути доведені backend-тестами.

## Відкриті обмеження без розширення цієї правки

**R7 human bindings:** кандидат показує read-only результати mappings із завантаженого файлу. Вибору наявних Item/Counterparty/Location за назвою для підготовки `bindings` тут немає; owner picker діє лише на навчальний template. Для першого готового synthetic template цього достатньо. Не заявляти, що UI вже дозволяє нетехнічному користувачеві налаштувати всі прив’язки довільного клієнтського файла. Координатор може зафіксувати це як відкритий пункт R7 або додати вузький наступний крок; у цьому огляді backend scope не змінено.

**Чотири маршрути:** template, preview і batch export підключені; окремий batch GET/current_targets у цьому UI не використано. Поточні картки читаються через ERP snapshot. Це допустимо для актуалізації record links, але batch GET може знадобитися для відновлення unknown confirm і журналу після закриття. Наявність route сама по собі не є UI acceptance.

**Грошовий/кількісний показ:** `ImportTotals` не містить float-перетворень. Imported quantity outstanding зараз використовує старий `erpNum(Number(...)-Number(...))`; формат показу зазвичай приховує двійкову похибку, але payload defect UI-03 треба виправити явно. Не переносити Number у money totals заради локалізації.

**Історія джерела:** source branch залежить від точної backend projection. Observer має отримати тільки дозволені identifiers; цей огляд не доводить, що backend уже приховав original commercial fields. Відсутня дата показується `—`; історичні цифри не вигадуються. Counterparty/item документи, permission changes, expired sessions і replay boundaries потребують реального інтеграційного прогону.

## Наступна перевірка після правок root

Перечитати тільки змінені фрагменти UI-01/02/03, зафіксувати нові SHA й повторити in-memory Babel comparison. Потім заморожений кандидат передати координатору для інтеграції з backend, actual JSON/CSV HTTP/proposal/receipt тестів і канонічного verify. Браузерні 390/768/1440,200%,keyboard/Escape/повільна мережа лишаються **НЕ ЗАПУЩЕНО** через раніше зафіксовані A11 обмеження. Нових browser/install спроб не було. Source-consensus не є проходженням gate10/MVP.
