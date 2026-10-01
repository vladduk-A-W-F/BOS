# Реалізація маршруту BoS 3.0 — прийняття контексту

Картка `B30-SOLUTIONS-JOURNEY-SOURCE-20260930`; авторський чат `01a0bffa-3fc7-7bc2-9868-86164c6e0315`. Фактична робоча копія: `D:/3/BOSDev/qa-scratch/bos3-brochure-crm-journey-20260930`. Це часткова копія трьох frontend-файлів без `.git`, assets, залежностей, БД і media; не runtime-інсталяція.

До першої source-правки звірено: admission SHA-256 `7106925d62789fa15063890f73c17294ddb332e175808a616ad5b90712d54a4e`; seed receipt `9cb423c59115b70e24c94881d2757316cad3a8512b554559d3a3ebec699d387e`; source card `a032dc63cd570b8ab59769927d3d43fdf6c74e8b7a63db654a9216530bc9df1e`. Seed `frontend/boss_app_source.html` SHA-256 `fc82733a97c3532cd8ea45ec9dfbfbd96d9274054c83d512b7fa8d40f8772384` (921706 bytes), `frontend/bos3_content.json` `1bce859370537437c157893065af499c9edd0fefea90b30c2f3384b2b04b1390` (17408 bytes), `frontend/bos_design.css` `30e1db301539b97080705c463c0fec14ae6370de577f824318484c42d159fd54` (61963 bytes). Шлях та hashes збігаються. CRM R2 є базою HTML; він не застосований тут до canonical/runtime.

Прийнято точний allowlist: змінювати лише `frontend/boss_app_source.html`; evidence — `SOURCE_DELTA.patch`, цей файл і `RESULT_MANIFEST.json`. Реєстр/CSS та зовнішні дерева залишаються read-only. На момент прийняття source edits 0, продуктові запуски 0, QA NOT_RUN. Запитана модель Sol/medium; фактична модель не підтверджена.
## Реалізована обмежена дельта

- **UI-01 / D1.** Перша сторінка чинної шестисторінкової брошури показує лозунг «BoS — рішення під ваш бізнес» і рівно три дії з read-only реєстру `supply`, `quality`, `payment`: «Забезпечити замовлення», «Відвантажити дозволену партію», «Узгодити залишок оплати». Кожна кнопка викликає наявний `onExplore(slug)`; ручне гортання, клавіші/свайп і CSS reduced-motion не змінено. Вторинна дія «Переглянути можливості» відкриває наступну сторінку. Вхід лишається персональним.
- **UI-02 / D2–D3.** Під час відкриття CRM навчальний компонент передає лише чинні `case_id`, `slug` і отриману від сервера `session_id`. У `App` origin `{case_id, slug, session_id, scope}` зберігається окремо від тимчасової `crmHandoff`-чернетки. URL містить тільки чинний `training` slug; нових PK, fixture-ID, localStorage чи API немає. Закриття чернетки, відкриття наявної угоди й підтвердження не очищують origin.
- **UI-03 / D3–D4.** Явна кнопка «Повернутися до сценарію» видима у CRM лише за наявності origin. До переходу звіряються чинний scope та slug. Після переходу навчальний компонент читає сесію через наявний GET-path і порівнює `case_id`, `slug`, публічний session UUID та scope до показу стану. За розбіжності або відмови показує український стан `context_changed`/`denied` і не підміняє його іншим кейсом. Повернення не викликає start/check/preview/confirm; воно не скасовує вже підтверджену серверну дію. Звичайна CRM без origin не отримує нової кнопки. Після успішного повернення або виходу до інших розділів origin очищується.
- **UI-04 / D5.** Нові елементи мають українські написи, `type="button"`, явні назви задач, помилки зміни контексту/доступу та пояснення, що навчальний приклад і план не є підтвердженою дією. CTA кейсу названо «Підготувати передачу до CRM». Наявний порядок залишається: CTA → серверна чернетка → preview → явне підтвердження → квитанція. Інші тексти CRM R2 й модулі застосунку не перекладалися в цій дельті.

## Статична матриця контексту (не виконання)

| Origin | Вхід у CRM | Повернення | Статус доказу |
| --- | --- | --- | --- |
| `supply` / `BOS3-CASE-01` | Серверна public session UUID, без виведення PK зі slug | Читання того самого case/session та перевірка scope | Статичний шлях, live NOT_RUN |
| `quality` / `BOS3-CASE-02` | Те саме | Те саме; hold не змінюється переходом | Статичний шлях, live NOT_RUN |
| `payment` / `BOS3-CASE-03` | Те саме | Те саме; контакт не змінює 6 400 грн залишку | Статичний шлях, live NOT_RUN |
| Origin відсутній | Звичайний CRM-маршрут | Кнопки повернення немає | Статичний шлях, live NOT_RUN |
| Slug, session UUID або scope змінився | Чернетка не є доказом безперервності | `context_changed` або `denied`, чужа сесія не показується як та сама | Статичний шлях, live NOT_RUN |
| Draft закрито / existing / confirm | Origin зберігається окремо | Доступне повернення до того самого case/session, якщо сервер і доступ це підтвердили | Статичний шлях, live NOT_RUN |

## Exact перевірки та межі

Baseline HTML — прийнятий CRM R2 SHA-256 `fc82733a97c3532cd8ea45ec9dfbfbd96d9274054c83d512b7fa8d40f8772384`. Результат і patch зазначені в `RESULT_MANIFEST.json`. `git diff --no-index --no-ext-diff --no-textconv` дав exit `1` як ознаку наявної дельти; raw stdout збережено в `SOURCE_DELTA.patch`. `git diff --no-index --check --no-ext-diff --no-textconv` дав exit `1` без stdout/stderr-діагностик пробілів; це не product PASS. Детерміноване порівняння фрагмента `CRMProposal` та блоку `detailOwner`–`owners` між baseline/result: `True` і `True`. JSON реєстру прочитано: рівно три slug `supply, quality, payment`. CSS та реєстр збігаються з seed SHA-256. У папці лише три seed-файли й три дозволені evidence outputs.

App, Node/JS, збірки, тести, browser, HTTP, БД, runtime та media не запускалися; продуктові executions `0`, QA `NOT_RUN`. Адаптивність, доступність у браузері, фактична CRM-тотожність і доставка не прийняті. **AUTHOR_COMPLETE_UNREVIEWED**: незалежний quality ще має перевірити exact source diff, а root окремо вирішує інтеграцію та публікацію. `TECHNICAL_READY=false`, `PILOT_ALLOWED=false`, `MVP=false`.