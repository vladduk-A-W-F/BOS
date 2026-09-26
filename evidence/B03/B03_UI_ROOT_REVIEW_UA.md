# B03 · незалежний огляд інтерфейсу

12.09.2026. Root перевірив окремий UI-кандидат після роботи автора. Канонічний frontend B02 не змінено. Висновок обмежений source, exact build та виконанням вузьких JavaScript-сценаріїв; реального DOM/браузерного приймання немає.

**Консенсус у цьому обсязі досягнуто:** два підтверджені дефекти виправлено. Невирішених блокувальних зауважень до цього UI freeze у погодженому B03 wire немає. Backend freeze, повний verify та зовнішні критерії залишаються окремими умовами.

## Перевірений код і поведінка

- `frontend/boss_app_source.html`: `340fbaf24ca3c0e75adfc18f3004034e24d7025fcb3ef7cf97bd250c2614943c`.
- `assets/app.js`: `3cf3aa31e160992f802e1af9c5f6e81fca1adab67a8f0d16732b39282bf0e758`.
- `frontend/boss_app_html.html`: `cc950098253dacfda9d6344555ebe1e78682d72b6614d7d8fcf1a5d94dcd3f6b`.

Прочитано compiled-source відповідність, шість payload builders, новий controlled dialog, pending queue, джерельні картки, інтеграцію в ERPWorkspace/BoSHome та inspector. UI передає фактичні ID, Decimal strings, ordinal позиції первісного рахунку й незмінний UUID наміру. Числові серверні підсумки не обчислюються повторно через Number. Нульове погодження вимоги відрізняється від відсутньої суми. Для фінансових дій потрібна роль керівника; клієнтські умови не заміняють серверні права.

Погодження зберігає proposal/operation IDs до POST; quota failure відмовляє до відправлення. Network/5xx/404 не очищають невідомий намір. Декілька погоджень одного UUID зберігаються до фактичної квитанції; явне повторне введення не створює нового UUID. Queue містить лише IDs та action, без сум, текстів чи payload. Escape/закриття синхронно скидає alive flag, відкладена відповідь не відкриває старий діалог. Це перевірка реалізації handlers, не реальний keyboard/network browser test.

Повні scoped source_movements та окрема correction_events використовуються для старих джерельних/result рухів і подій. Старі обмежені журнали не розширені до довільного повного dump. Недоступна фінансова подія не маскується робочою кнопкою. Остаточну серверну видимість цих нових collections має довести backend suite.

## Відтворені дефекти й рішення

1. **Ідентифікатори губилися при зміні access revision.** На source `4cdcec8263f7ab127af527ffc9d188431e21ee79a05aa3537c6b8680c5b10613` root виконав витягнуті функції в Node: той самий user/mode/role після revision change отримував порожню queue. Ключ тепер сталий за user/mode/role, а актуальні права перевіряє API. Root повторив той самий сценарій на final source — пройдено.
2. **Історична квитанція змішувалася з поточною оплатою.** На source `f49b1e0477059554ccd5fa6ec8b51086dec163b838242d2fb554ecd4e05b5b9d` фактичне виконання extracted compiled component показало в одній таблиці current paid110.00 з historical net98.72/customer_credit1.28. Тепер receipt має окремі чотири поля під «Результат цього погодження», а current invoice — шість полів під власним заголовком. Незмінний сценарій став зеленим; late replay більше не видає різні моменти за один стан.

Початкове припущення root про непрацюючу source_movements картку **не підтвердилося**: застарілий fragment відрізнявся від зібраного кандидата. Actual extracted BoSInspector одразу повернув правильний body/title. Це не враховується як знайдений дефект або виправлення; fragment синхронізовано для читабельності.

## Докази та межі

`B03_UI_ROOT_RED.json`, `B03_UI_ROOT_GREEN_FINAL.json` і незмінний runner `b03_ui_root_probe.cjs`: root фактично виконав дві перевірки витягнутого JavaScript з мінімальними React element/hook stubs. Вони підтверджують лише card dispatch і pending persistence. `SETTLEMENT_HISTORY_RED_GREEN.json`: два actual red → два green за історичними/current значеннями. Авторські `UI_HELPER_RESULTS.json` містять 18 виконаних точних сценаріїв payload/Decimal/queue/history fallback; старі ERP action definitions та B02 ImportDialog/ImportTotals/Q3 helper збережені. `BABEL_EXACT.json` підтверджує відповідність source/compiled SHA.

`UI_WIRE_CONFIRMATION_UA.md` фіксує погоджені cumulative cancellation, nullable restricted return totals, scoped source/result movement history та correction events. Source review не підміняє actual HTTP confirm/outcome або role matrix.

Ширини 390/768/1440, масштаб 200%, фокус/клавіатура, Escape з реальною мережею та всі браузерні взаємодії залишаються **НЕ ЗАПУЩЕНО** за відомим A11 обмеженням. PostgreSQL/Windows/CI та загальне приймання MVP цим оглядом не закриваються.
