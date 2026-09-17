# C03 UI: остаточний незалежний висновок

12.09.2026. Read-only review exact candidate та збережених source/closure/build доказів. Нових тестів, браузера, API, серверів чи змін checkout рецензент не запускав.

**Погоджено UI candidate у перевірених межах. У відкритих source findings блокерів не залишилося. Інтеграційна сумісність з фінальним backend та повний canonical verify ще обов’язкові; browser/MVP acceptance не надано.**

| Артефакт | SHA-256 |
|---|---|
| UI_CANDIDATE_MANIFEST.json | `dcd6558a089d812f670fc022eb48568ef144d865c8531f4b6d22d367b1d5e141` |
| frontend/boss_app_source.html | `78136013163756fa033e59726a1296dc8c0938850621cfc7b093ce1ea7c1886a` |
| frontend/boss_app_html.html | `e215f02aa69d5931cbc41dca742fd850a02c471d07d45fc66a75c9aa3e244937` |
| assets/app.js | `34f99363ea8b89378001aba51253791a4b63438305283a4e7af24f1db530e95a` |
| Source base | `fd283ac01fd50fd2478a5902e492fbed5f16da943ac3731a01b4903a96dec801` |
| Wire checkpoint | `53bd7af9fc25ca152952c1f779f05145068fe084704a68e9e329f83341680a91` |

Усі3 release files та13 evidence entries незалежно перевірені за manifest SHA: розбіжностей немає. Новий pending identity addendum прочитаний окремо; його SHA наведено нижче.

## Перевірений бізнес-контракт

- Журнал, імпортовані рухи та рознесення на Invoice є окремими шарами. UI не додає їх між собою; existing_payment не надсилається як новий платіж. Outgoing і salary-source не створюють AR allocation.
- Currency та період явні. Фінансові totals/settlement показуються серверними fixed2 strings. BigInt використано для нормалізації суми payload; Number лише для геометрії графіка. «Чистий рух» не називається банківським залишком. Manual journal writer зберігає старий intent helper та надсилає currency.
- UI працює з повними scoped candidates для Transaction/Invoice/Event/ImportIdentity/Salary; не покладається на recent300. Проспективні UUID preview не відкриваються як committed записи. Квитанція й поточна картка розділені, B03 credit/receivable/customer_credit показані окремо.
- Preview звіряє повний нормалізований payload, import source identity, reconcile line/amount/currency/Transaction mode та набір allocation keys/fields. Чужий same-action response не відкриває confirm.
- UUID погодження та allocation keys зберігаються перед POST. Generic409/timeout/закриття/403/404 не створюють нового intent і не очищають unresolved queue. Storage/crypto failure блокує відправлення. Pending не обрізається і не приховується новим access_revision; ключ містить mode/user/role.
- Для import додано лише source_identity_sha256 = SHA-256 UTF-8 JSON.stringify([source_sha256,source_system,account_ref]) у точному порядку. Raw account/source, гроші, reason/purpose/payload у storage не додаються. Receipt і no-change звіряються з domain digest. Законний повтор може повернути інший перший document_id; він приймається тільки за однакової domain identity. Відсутній/некоректний digest залишає ID невідомим, не є success і не створює нової дії.
- CSV201 звіряється з фактичним локальним SHA, code та revision. Wrong source або нечитабельний successful response не показується як перевірений файл; unknown-upload блокує автоматичний повтор. Recovery шукає той самий code/revision та SHA. Upload/review не видається за проведення грошей.
- Session/source denial очищує показані source panels до JSON parse: HTML403/404 також закривають дані. Тексти документів/CSV рендеряться як текст, не HTML/instruction. Старі CSRF wrapper, C01/B03 pending/діалоги, App/AuthGate та інші захищені declarations не переписані.

## Фактичні вузькі докази

Прочитано самі harness: вони витягають функції та closures із фактичного JSX через Babel AST; підміняються transport/state/storage/DOM-bound refs, а не перевірювані бізнес-умови. Докази означають виконання JavaScript closures з контрольованими відповідями, не фактичний browser/API/DB.

- Основний UI_PROOF: **37/37** на final source78136013 — exact money/max, strict JSON, дві осі, ID-only queue до POST, storage fault, late reads, same-ID recovery, source recovery та Assistant dispatch.
- REVIEW_RED → REVIEW_GREEN: первісно **4 failures + 1 preservation**, тепер **5/5**. Non-JSON403/404 раніше не викликали deny; тепер викликають перед parse. Wrong-line preview раніше приймав proposal; тепер відхиляє. Wrong SHA/code/revision upload201 раніше приймав source; тепер source=null і unknown=true.
- IDENTITY_RED → IDENTITY_GREEN: первісно **6 failures + 3 preservation**, тепер **9/9**. Digest записаний до POST, wrong-domain receipt зберігає pending, інший first Document за тотожного domain приймається, missing/invalid digest не надсилає новий confirm, no-change identity перевіряється. Проміжні no-change та unreadable201 помилки збережені окремим red; фінальні обидві зелені.
- Разом **51/51 = 37+5+9**. Це скінченні named checks, а не 51 браузерний сценарій.
- PROTECTED_BUILD_PROOF: **189** початкових top-level declarations побайтово збережено; дозволені зміни лише Bank та OperationsAssistant. Прочитано механізм exact AST source slices та exact in-memory Babel output comparison; generated app SHA збігається, declarations_changed=[] і exact_babel=true. Build-script/Babel залежності не змінені.

Мою початкову гіпотезу про manager Bank було спростовано: незмінний App.renderContent повертає BoSReadOnlyRecords до нового Bank. Actual extracted App counterproof зелений і до, і після. Нова manager гілка не потрібна й права не розширено. Моє первісне припущення про обов’язкову рівність import document_id також уточнене root: для domain replay потрібен digest, а first Document законно відрізняється.

## Межі та наступна інтеграція

Фінальний UI source погоджено за exact SHA. Backend source status/current_summary/export та create→bound-existing Transaction виправлення має окремо підтвердити автор у своєму freeze; UI verdict не підміняє його. C01/B03/finance старі захищені області збережено у source, але новий integrated full verify ще потрібен. Немає тверджень про keyboard/Escape/focus/390–1440px/zoom200% browser-прохід, PostgreSQL, Windows, A09 boundary stability, CI, production або весь MVP.

Pending identity addendum SHA-256: `2a0c5f075ffb961fa1b0ff8dd875440444f9d6e0cf3db3744a67e4ac1e539d3c`.
