# BATCH-02 · PLAN-UX · джерела виконання замовлення

20.09.2026. Реалізація в ізольованій копії; canonical/GitHub не змінено цим виконавцем. Незалежний review очікується. Результат не є прийманням UI gate чи запуском продукту.

## Зміни

У чинний `BoSInspector` замовлення після «Позиції й виконання» додано «Джерела виконання». Контракт `bos.order-trace.v1` погоджено безпосередньо з виконавцем `PLAN-LINKS-READ`; `erp/order_trace.py` прочитано для остаточних типів. `task.deadline=null` є допустимим. Значення кількості лишаються серверними Decimal-рядками; `null` має знак «—» та текст про обмежений доступ, нуль зберігається точно.

Блок показує дані перевірки, власника замовлення, позиції, джерела скасування/резерву/відвантаження, доведене походження партій, дозволені роботи/доручення/реквізити рахунків. Не виводить очікувані закупівлі як призначені замовленню, не обчислює обіцяну дату та не додає фінансові суми. Немає нових mutation API, preview/confirm, зовнішнього GPT чи автоматичних повторів GET.

Loading, 409, denied, network/server error очищують неприйняті факти. Зміна ID/actor/access context, session-ended і відомий data-changed відкидають пізню відповідь через sequence, контекст і AbortController. Після data-changed показано потребу ручного оновлення. Перевіряються schema/order/scope/access_revision та типи спожитих вкладених полів; помилки не показують сирий серверний payload.

Відкриття джерела є явною дією. За окремим погодженням root розширено лише callbacks цього ж файла в `ERPWorkspace` і `BoSHome`: чинний snapshot GET повторно перевіряє доступ до початкового order та до джерела, після чого оновлює єдиний parent data і selection. Pending parent refresh не перезаписує цей свіжий результат. Немає fallback до старих cached деталей. Для інших callers inspector переходи вимкнені з поясненням. Доручення відкривається у чинному HR списку з видимим ID для пошуку; точного task deep link не оголошено.

## Allowlist та збірка

- `frontend/boss_app_source.html`: scoped CSS, read-only component, одна вставка в order, два вузькі parent callbacks.
- `frontend/boss_app_html.html`, `assets/app.js`: лише похідні від чинного `scripts/build_frontend.cjs` із локальним `assets/babel.js`.
- Скрипт збірки, backend, DB, Policy, моделі, CI, джерела gates та readiness не змінювалися.

Patch: `UX.patch`. SHA до/після: `manifest.json`. Копія: `source/`.

## Перевірка

`verification.json` містить точні команди, exit codes, час і SHA raw logs.

1. Штатна локальна Babel-збірка: exit 0.
2. `node --check` згенерованого `assets/app.js`: exit 0.
3. `test_trace_behavior.cjs`: 18/18 PASS, exit 0. Перевіряється фактичний JSX компонента зі штучним планувальником hooks та керованим fetch. Сценарії: великі Decimal та 0/null; неправильний order; закриття/перемикання під час відповіді; session/data clearing; 409 без повтору; свіжа наявність order/source перед переходом; double click; зміна header/body access revision; malformed nested DTO; network failure; nullable task deadline і HR list.

Це unit-перевірка поведінки компонента, не React DOM, браузерний E2E чи візуальна перевірка. Попередні 17-case candidate та докази збережено в `before-origin-check/`; наступний крок додав окрему перевірку відкликання доступу саме до початкового order при збереженому доступі до source.

## Межі та наступна UX-перевірка

Збережено існуючий inspector та його selection semantics. Локальна history, повернення до замовлення зі збереженням фокусу та загальний focus management не входили в цю картку й не оголошені виконаними. CSS додає 44px touch actions, wrap і видимий focus; фактичні viewport 390/768/1440, zoom200%, клавіатура, screen-reader та повернення фокусу мають окрему браузерну перевірку за доступним дозволеним профілем. A11 не обходили; мережеві CDN не використовували.

До інтеграції потрібен незалежний review та погоджена інтеграція backend route/catalogue. Браузерний прохід має перевірити відкриття через «Продажі»/«Сьогодні», джерела всіх підтриманих типів, blocked caller, швидке перемикання, role change, 409, partial>100 та довгі українські коди. Full suite/E2E не повторювались. `TECHNICAL_READY=false`, `PILOT_ALLOWED=false`.
