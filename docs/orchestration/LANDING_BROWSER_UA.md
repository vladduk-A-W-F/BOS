# Приймання лендингу BoS · version 3

20.09.2026. **ACCEPT_SCOPED_LANDING_NAVIGATION**.

[Лендинг](https://business-operating-system.vladduk134.chatgpt.site) · [демонстрація](https://business-operating-system.vladduk134.chatgpt.site/demo/).

## Результат і межі

План до лендингу виконаний: сторінка українською представляє поточний продукт, перевірений приклад SO-101 і шлях у демонстрацію. Впровадження, серверна готовність та майбутні GPT/інтеграції описані окремо. Усі необхідні перевірки лендингу й переходів завершені. Це не повне приймання transactional demo або Django: browser E2E з підтвердженням усіх операцій не проходили, TECHNICAL_READY=false, PILOT_ALLOWED=false.

## Виправлення та публікація

Той самий Site: `appgprj_6aa9057b8e5c8191abe7685fb7c9f145`. Version 3: `appgprj_6aa9057b8e5c8191abe7685fb7c9f145~appgver_0c7af09216588191a7e3a35d030c8efc`; source `ce0322034971a1ddc5cd66470e3792bb26f56493`; deployment `appgdep_6aafd80d7dc48191bd0e9f2d4b5711b3`, native status=succeeded, 2026-09-20T12:56:59.878586+00:00.

- Старі root-hash посилання працювали після повного завантаження, але ігнорували зміну hash уже відкритого лендингу. Додано обробник hashchange; суфікс запису зберігається.
- На 320 px прихований br склеював «Починаємоз». Пробіл між словами збережено.
- Мобільній кнопці пошуку додано доступне ім’я «Знайти в BoS».
- Текст демо більше не гарантує приватність: доступ визначають налаштування Site. Native get_site до й після публікації підтвердив public revision 2; політику доступу не змінювали.

Змінені лише landing.js/index.html, підписи/aria JSX із відповідним compiled app.js, description demo, README та regression test. Доменна модель, seed, ключ і поведінка localStorage не змінені. Django та GitHub main не змінювалися. Виправлення Site живуть у його canonical source repository; GitHub PR містить звіт і докази.

## Перевірки за вимогами

| Вимога | Доказ | Результат |
|---|---|---|
| Український лендинг і чесні межі | Live AX і візуальний перегляд; статус навчальних даних, local-only, майбутніх GPT/інтеграцій | PASS |
| Чотири вкладки й клавіатура | Попередній desktop evidence: 4 tabs, ArrowRight/End/Home/ArrowLeft; mobile 390 px — усі 4 selected/text/href | PASS, відповідний код незмінений |
| Робочий приклад продукту | SO-101 → MO-101 → PO-FAST: 50 потрібно, 10 зарезервовано, 40 заплановано; 60/80 кріплення і закупівля 20; запуск заблокований нестачею | PASS read-only |
| Доступ до демо і повернення | CTA → /demo/ та модуль; мобільне меню → фінанси/налаштування; back link → лендинг | PASS, повернення повторено на v3 |
| Мобільна версія | 390×844 scrollWidth=375; 320×740 scrollWidth=305; візуальний перегляд і навігація, v3 heading виправлено | PASS без горизонтального переповнення сторінки |
| Старі URL | На v3 live hashchange orders/procurement/production/finance; початкова /#orders/SO-101 → /demo/#orders/SO-101 | PASS; збереження suffix, не автоматичне відкриття запису |
| Нові section anchors | #product лишається на лендингу; контрольований test перевіряє також #main/#approach та unknown | PASS |
| Збережена модель демо | domain test: 20 committed operations в ізольованій пам’яті; незмінені model.js/seed.js | PASS, не browser/backend E2E |

Додатково простежено завершені SO-090 → INV-SO-090 → SHP-SO-090 та посилання оплати: 12 одиниць, 1440 EUR сплачено, залишок 0. Для INV-SO-091 відкрито preview оплати 100 EUR: дебіторка 1600→1500, оплати 2040→2140. Натиснуто «Скасувати»; після reload суми не змінились. У браузері не підтверджували запис операцій і не скидали навчальні дані.

Мобільний пошук на v3 відкриває форму; налаштування показують нейтральний опис доступу. Тимчасовий viewport скинуто; вкладку залишено на лендингу.

## Збірка та контроль регресії

Тест hashchange спочатку дав очікуваний RED, після виправлення — GREEN: initial hash, same-document hash, suffix, усі 14 модулів і anchors. `node build.cjs`, domain test, syntax checks і diff whitespace пройшли. Build script створив dist з поточного source до успішного push.

Стандартна обгортка package-site.mjs не змогла запустити відсутній Bash. Для Windows застосовано її офіційний prepare-site-build.cjs та системний tar. Перевірено дві HTML точки входу, assets і manifest, жодного source tree в архіві. Локальний gzip SHA-256 `9d44db6827f3ddcd4366f5a6ee46a403399afcc794661d33d5eae56e49921edc`; Sites нормалізував tar і підтвердив 12 файлів, власний content_hash наведено в receipt. Version збережено з повним SHA, прочитаним після успішного push, та опубліковано штатним Sites deploy.

## Відкриті межі

Повний transactional browser E2E не виконаний; модель перевірена окремим domain test, а live перевірка включала читання й preview/cancel. Backend/PG/full-suite/E2E повтори не запускалися; історичні обмеження A09/A10/A11 залишені.

У журналі браузера є шість повідомлень asynchronous listener/message-channel (два після v3). Їх походження однозначно не встановлено; помилок пройдених UI-дій не спостерігали. «Чиста консоль» не заявляється. Це відкрите діагностичне спостереження, не доказ серверної готовності.

## Відтворювані докази й review

Receipt: `evidence/batch04/landing-v3-20260920.json`. 24 точних CUA text output із кодом дій: `evidence/batch04/browser-v3-observations-20260920.json`, SHA-256 `57768c11c3f82e5ab8a60531aaaa3f084c593a3195799551f4ce93217191e9d5`. Image bytes не архівовані; screenshots переглянуті під час QA. Первинні командні outputs: `evidence/batch04/site-v3-checks-20260920.json`. Інвентар інших вкладок, credentials і bootstrap виключені.

Раніше мобільна перевірка зупинилася через CUA timeout; після відновлення браузера блокер усунуто. Попередні partial receipt/12 observations залишені без зміни як історія v2. Старі DEPLOYMENT.json і LANDING_CHECKS.json також збережені; їх private URL не описує поточний доступ.

Незалежний reviewer прийняв вузькі source fixes (hash routing, підписи/aria, generated bundle, heading spacing) як ACCEPT_SCOPED. Фінальна звірка цього evidence: ACCEPT_SCOPED.
