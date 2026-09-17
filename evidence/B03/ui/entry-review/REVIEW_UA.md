# B03: незалежний огляд доповнення входу через асистента

Вердикт: у погодженій вузькій області нових блокерів після двох виправлень не лишилось. Це source/build review та виконання ізольованих фактичних JS-функцій; браузерне приймання й gate10 лишаються відкритими.

Перевірено delta між замороженим UI `340fbaf24ca3c0e75adfc18f3004034e24d7025fcb3ef7cf97bd250c2614943c` і root-кандидатом `f00fe5165592b9e8a8a71fda7d16c2f70ba61620a94a864c7ef3eb4dc1635c60`. App `b41a8ffc3db25bc7892673edae0800d6f265e420649c370c40d777be0cfce14a` точно відповідає повторній Babel-компіляції в пам’яті. Зміни в canonical/заморожений UI/repo reviewer не вносив.

## Контракт і маршрути

Новий `b03ImportedAction` приймає шість оголошених дій, перевіряє закритий набір верхніх/вкладених полів, canonical UUID4, integer ID, XOR джерела скасування, allocation ordinal/returnID та передає десяткові рядки через чинний `b03Payload`. Дані не виконуються на етапі JSON-вводу: спочатку snapshot та форма, потім звичайний preview/confirm. Actual source/кількість/дата/право остаточно перевіряє backend.

Обидва parent entrypoints (`OperationsAssistant`, `Procurement`) тепер використовують `BoSActionDialog`, який направляє тільки B03 до `CorrectionActionDialog`; старі ERP дії й B02 залишилися незмінними. CEO-only monetary role gate дублюється у parser та dialog, а сервер перевіряє права повторно. Source imports не створюють prospective IDs як нібито збережені записи.

## Виявлені й закриті помилки

1. Наданий JSON `operation_id` спочатку зберігався тільки при mount; `change()` скидав його при редагуванні, отже preview міг мовчки створити новий намір. Actual extracted `change()` відтворив `UUID → null` у `REVIEW_RED.json`. Тепер imported `preset.operation_id` залишається незмінним при редагуванні; змінений payload із тим самим UUID перевірить сервер. Звичайна порожня форма зберігає свою попередню поведінку. Новий намір потребує явної нової форми або JSON із новим UUID.
2. Procurement після скасування PO використовував повідомлення звичайної закупівлі навіть при `effective_open=0.000`. `PROCUREMENT_RED.json` відтворив це на фактичному JSX receipt branch. Тепер гілка `erp_cancel_remaining` показує записане скасування та історичний залишок після саме цього погодження; поточний стан доступний через картку actual PO. Старий purchase текст збережено для звичайної закупівлі.

## Докази й межі

`FINAL_GREEN.json`: 13/13 вузьких перевірок, включно з actual import/change closures, manager rejection трьох грошових дій, observer rejection, зайвими/вкладеними полями, numeric quantity, string ID та invalid UUID; exact Babel match. `PROCUREMENT_GREEN.json`: known receipt-message red став green. Root окремо має свої шість actual entrypoint red→green доказів.

Snapshot у JS harness був контрольованим read-only значенням. Receipt JSX перевірено через дерево React-елементів, без DOM, CSS, pointer, keyboard чи network acceptance. Новий широкий UI sweep не проводився. Існуючі ризики async lifecycle в старих entrypoints цим вузьким оглядом не оголошуються закритими. Повний інтеграційний gate запускає root окремо.

Hashes входів/результатів — `REVIEW_MANIFEST.json`; точний scoped diff — `ROOT_UI_DELTA.patch`.
