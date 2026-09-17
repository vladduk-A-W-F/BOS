# B01 · незалежний огляд кандидата frontend

12.09.2026. Перевірено тільки код: `/workspace/scratch/c7b51e996a9f/tmp/b01_ui_candidate/frontend/boss_app_source.html` проти `/workspace/sites/bos-original-refined/frontend/boss_app_source.html`. Перед роботою прочитано поточний PROGRESS та прийнятий master v2.1. Базовий frontend SHA256: `c669c95ee8c4356b8a2c7964f22c8c17751fe2294a8ddf2275f3fc3751d712fd`; базовий Git HEAD `9ad8edcdf2eef231443b555c16314b6d034924e7`.

**Фінальний висновок у межах source review:** для frontend SHA256 `943ed8347c1f0fc3248c5d0483d3a3d46c9d9ad605232b8fd3d278c85325798b` нових блокувальних зауважень до зв’язку Quote → ERP purchase preview/confirm → фактичний receipt → PO inspector → receive не залишилося. Неправильний текст результату, cancellation і відсутню картку погоджених джерел виправлено root та повторно прочитано агентом. Ключі картки збігаються з фактично прочитаним кодом backend candidate; незалежна Babel-перевірка відповідності generated файлів пройшла. Остання окрема правка змінює тільки видимий код Quote у confirm summary; перевірка нижче. Браузер і HTTP цим оглядом не запускалися; це не gate10 і не повне приймання B01.

## Знайдені нові питання B01

| ID | Конкретна поведінка | Стан |
|---|---|---|
| B01-UI-01 | Початковий receipt вважав кожний результат без purchase_id створенням партії `pending`. Через PO inspector також запускається postpone; його фактичний контракт — `{id,code,due_date}`, тому успішне перенесення дати описувалося б як нова партія. | Root виправив. У повторно прочитаному SHA `5bb3f514e0a8d570fd636e4d187462cbf1e99ba3156b599ca376c8ff05969a3c` є окремі purchase_id / lot_id / нейтральний результат. `openReceiptRecord` заново читає snapshot. Помилкової обіцянки створення/якості більше немає. Source review, не browser pass. |
| B01-UI-02 | Початковий `beginPurchase` показував error за відкритою Quote modal; закриття Quote під час snapshot не заважало старій відповіді відкрити новий purchase dialog. | Root додав purchaseError безпосередньо в QuoteInspector та purchaseCancelled guard після await. Прочитано у SHA `de0058f9a7ccaa7d547d9cb3c50b6ded8f06bbfb1f50aaec09ba8042ed4bd499`. Окремий залишковий шлях — B01-UI-03. |
| B01-UI-03 | При pending `beginPurchase` кнопка «Доручити перевірку / уточнення» залишалася активною. Її `onTask` у SHA de0058f9… прибирав Quote й відкривав task, але не встановлював purchaseCancelled. Старий snapshot міг відкрити purchase поверх task. | Root виправив; повторно прочитано SHA `93f146b00ab99519eb250a0e2dfcea8d07bdf0cc83e60a60a4a188f8601ba42d`: source/task disabled під час purchaseBusy, onTask додатково встановлює purchaseCancelled. Close/Escape лишаються доступними. Code path закрито, browser race наразі не відтворений. |
| B01-UI-04 | Початковий `BoSInspector(kind='purchases')` показував request_id, але не схвалений Quote, джерельні документи/версії, supplier_confirmation або direct_reason. Після reload джерело погоджених умов не можна було перевірити з PO. | Закрито source review у SHA `213dfb288b05a987bbdd801bc99e9213586e8790b40a75ad17ff8f0f951f4aee`: новий PurchaseSource читає саме r.approval_snapshot, показує погоджені умови/джерела, відділяє первісну дату від поточної і чесно описує історичний null. Observer не отримує commercial блоки. Ключі звірено з erp/procurement.py та operations/projections.py. |

Питання item.currency перевірено й **не вважається дефектом**. Спочатку запропоновано звірити фільтр номенклатури з backend; root уточнив контракт: item.currency — валюта планової калькуляції, фактична валюта Purchase/Lot може відрізнятися. Перевіряти потрібно Purchase.currency = Quote.terms.currency = Request.currency. Вимога фільтрувати item.currency знята; її не слід додавати для зручності тесту.

## Звірка payload і поведінки

Backend кандидат — `/workspace/scratch/c7b51e996a9f/tmp/b01_candidate/source`. На початку огляду автор ще реалізовував код після red-tests; перед фінальним висновком агент прочитав фактичні erp/procurement.py, operations/service.py, operations/projections.py і policy. Контракт нижче звірено з цим кодом; він не видається за фактично виконаний endpoint. Backend-прогін і остаточна інтеграція лишаються авторові/root.

| Поле / перехід | Поточний frontend | Вимога до остаточного backend |
|---|---|---|
| quote_id | Preset бере `quote.id`; визначення `integer?`; preview перетворює всі `_id` через Number; порожнє пропускає. Значення у формі readonly. | Compare має повертати фактичний row.id; права на quote перевіряються сервером. Не можна мовчки опустити відсутній id і вважати quote-покупку прямою. |
| request_id | Preset бере `data.request.id`; readonly при quote. Пряма закупівля має старий необов’язковий select requests. | Compare має містити request.id; сервер перевіряє quote.request і кількість нерозподіленого залишку. |
| supplier_id | Preset із quote.supplier_id; readonly, label через фактичний snapshot partners. | Compare row.supplier_id має бути наданий і дорівнювати вибраній пропозиції. |
| item_id | Користувач явно обирає. За purchaseContext список обмежено однаковими unit/revision та однаковим document_id **або** code = request.part. | Backend повторює предметну перевірку відповідності, не довіряє фільтру UI. Item.currency не є фільтром. |
| price / extras / currency / revision | Дані із Quote; extras складається з setup/shipping/tooling/special_processes у цілих cents; поля readonly при quote. | Сервер заново бере погоджувані terms та звіряє клієнтські поля, точні Decimal і валюту Request. Клієнтський Number не є джерелом фінансової істини. |
| quantity | Початково quantity поточного compare, зокрема simulation; користувач може змінювати. | Сервер перевіряє позитивну величину, MOQ і нерозподілену потребу. Split 6+4 законний; ще 1 — відмова. Після першого PO UI може запропонувати повну стару кількість, тому діагностика перевищення має бути зрозумілою; це не підстава заборонити split. |
| due_date | Порожня дата, її вводить відповідальний; розрахунковий quote.arrival не підставляється як підтверджений строк. | Перевірка від as_of до required_by за погодженим контрактом. |
| supplier_confirmation | `text?`; для quote показано required Input із порожнім значенням і прикладом лише в placeholder. Для direct приховано; порожнє пропускається. | Непорожня атестація відповідального стосується саме кількості/ціни/дати; її текст зберігається з автором. Це не зовнішня перевірка постачальника чи гарантія строку. |
| direct_reason | `text?`; required тільки за відсутності quote_id. Для quote приховано; порожнє пропускається. | Пряма нова закупівля без причини відхиляється. Історичні PO не переписуються вигаданою причиною. |
| production_id | Старий optional `jobs?` збережений. | Перевірка зв’язку з матеріалом роботи залишається на сервері. |
| preview → confirm | Старі ERP endpoints, proposal_id, lock і «Було → Стане» збережені. Нового обхідного writer немає. | Preview не створює PO/рухи; confirm атомарно створює PO і receipt; повтор того самого proposal повертає той самий PO. |
| afterPurchase → PO | Результат сервера збережений до refresh. За purchase_id читається свіжий snapshot і відкривається purchases inspector; refresh failure чесно каже, що операцію вже збережено. | Receipt має справжній purchase_id і фактичний impact. Не повторювати команду запису через помилку оновлення екрана. |
| PO → receive | Використовується наявна дія receive з purchase_id і залишком quantity-received. | Реальний receive створює pending Lot/Movement і змінює received; перевищення відхиляється. Не створювати залишок або оплату при purchase confirm. |
| Receipt після receive | Виправлений кандидат пропонує «Відкрити партію» за result.lot_id із повторним читанням snapshot. | Стан якості читається з фактичної картки; результат будь-якої іншої lot-операції не називається новим приходом. |

Умовне приховування optional полів у нових purchase-гілках не ламає generic renderer: `quote_id` оброблено до загальної numeric-гілки, `_id` гарантує Number при preview; `text?` для confirmation/reason також має окрему гілку. Порожні `''`/null/undefined пропускаються до серіалізації. Нульовий quote_id, помилкові JSON типи та непорожні суперечливі optional поля все одно повинні відхилятися backend; UI readonly цього не доводить.

## Що вже коректно сформульовано

Кнопка називається «Підготувати закупівлю», а не «Надіслати постачальнику». Рекомендація прямо позначена як не розміщене замовлення. Порівняльна дата названа розрахунковою; supplier_confirmation не заповнюється автоматично; текст каже, що склад і оплата змінюються окремими операціями. Observer не отримує кнопку запису. На створення PO використано існуючий механізм погодження; на приймання — існуючий receive. Ці висновки засновані на коді й не доводять поведінку HTTP або DOM.

## Остаточна картка джерел та збірка

`PurchaseSource` читає `approval_snapshot.source`, request_code/quote_code, agreed_quantity/agreed_due_date, unit/revision/currency/price/extras, original_terms, direct_reason, supplier_confirmation та source_documents. Джерела request/quote відкриваються за **збереженим document_id**, без підміни поточною версією за code. Початкова погоджена дата відділена від змінюваної due_date PO. Null snapshot названо історичним записом без знімка умов; вигаданого погодження не додається.

Комерційні умови в компоненті доступні CEO/manager; observer бачить тільки source code/documents. Прочитана backend projection додатково вилучає для observer original_terms, price/extras, supplier_confirmation/direct_reason та поля погоджених умов. UI не відновлює їх із суміжних записів. `supplier_confirmation` підписано засвідченням менеджера; текст прямо пояснює, що незалежного підтвердження від постачальника BoS не отримував.

SHA256 backend файлів, прочитаних для цієї звірки:

| Файл кандидата | SHA256 |
|---|---|
| erp/procurement.py | 0d8f7d752c28a9b90b66c59861070d949ca18fcc9b7ad264f149533a8ddf1b6e |
| operations/projections.py | 3d58edd8d40196d8618061aa633c308dad6495965f4161b6dd2370d7e20818f2 |
| operations/service.py | 0ede54c4852c3f087839a7696eaecc8f14e8981632fb06a449799211bdd1fac1 |

Незалежно виконано Node/Babel transform JSX у пам’яті та точне відтворення HTML-перетворення штатного build-скрипта. Жодного DOM, React dispatcher чи HTTP mock. Результат exit 0:

```json
{"source_sha256":"213dfb288b05a987bbdd801bc99e9213586e8790b40a75ad17ff8f0f951f4aee","babel_transform":true,"compiled_js_matches":true,"served_html_matches":true,"read_only":true,"browser_started":false}
```

Це доводить синтаксичну збірку й однаковість source/generated, а не браузерну поведінку чи права endpoint.

## Обов’язкові наступні докази без mock UI

1. Backend frozen: фактичний compare JSON для CEO/manager/observer та snapshot нового PO, з ключами approved snapshot і role projection. Звірити кожне поле source card без відновлення прихованих цін/текстів.
2. Справжній HTTP quote→preview→confirm→snapshot→receive: точні ID, суми, незмінні джерельні умови й оригінальні байти; порожній/прямий optional payload; повтор та конфлікт. Це робота backend автора/root, не виконана цим оглядом.
3. Фінальні cancellation/source-card рядки прочитано і source/generated звірено для SHA 213dfb28…; останню суто текстову зміну та JS повторно звірено для frozen SHA 943ed834… нижче. При зміні цієї версії повторити перевірку лише зміненого контракту та штатну збірку. Не використовувати pure React render із підміною dispatcher як приймання.
4. Коли браузер доступний — пройти справжню кнопку Quote, required fields, скасування pending, source card, actual receipt і partial receive. A11 viewport/keyboard/slow-network залишаються окремим відкритим gate. Установку Chromium не повторював; мережеві/OS обмеження не змінював.

## Старі A11 питання — не правки B01

Збережено окремо: втрата proposal_id при catch у загальному ERPActionDialog.confirmAction; старі compare/document response races; Escape/focus/accessible names; mixed-currency старих Bank/Salary; demo-text у порожньому working workspace. Вони наведені у `tmp/A11_UI_REVIEW_UA.md`, не виправлялися цим оглядом і не є новими регресіями B01. Розширення області перевірки на ці старі компоненти не підміняє завершення конкретного procurement bridge.

Checkout, бази та браузерне оточення агент не змінював. Усі результати огляду — тільки в цьому tmp документі. B01 не оголошена прийнятою; повний продукт не оголошений готовим.

## Остання перевірена правка · код Quote у погодженні

Root змінив тільки display-гілку confirm summary: за `k==='quote_id' && purchaseContext` показується `purchaseContext.quoteCode`, наприклад Q13; без context зберігається попередній fallback числового ID. Payload, optional fields, writer і proposal_id не змінено.

Для незалежної перевірки агент у пам’яті замінив цю єдину нову гілку на попередню. SHA відновленого source **точно** дорівнює вже переглянутому 213dfb28…; додаткових source-змін не виявлено. Babel transform нового source і порівняння з generated JS дали exit 0:

```json
{"source_sha256":"943ed8347c1f0fc3248c5d0483d3a3d46c9d9ad605232b8fd3d278c85325798b","previous_source_sha256":"213dfb288b05a987bbdd801bc99e9213586e8790b40a75ad17ff8f0f951f4aee","display_only_change":true,"compiled_js_matches":true,"browser_started":false,"read_only":true}
```

Нових зауважень у цій вузькій правці немає. Межі попереднього висновку, зокрема відкрите браузерне приймання, збережено.
