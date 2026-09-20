# FLOW-READ-UI · джерела забезпечення й розрахунків у картці замовлення

20.09.2026. Ізольована integration branch `codex/continuation-20260920`, база
`3d979060fe9862119ba8ad6c9d8bd505103796e3`. Канонічне дерево й його STATE/QUEUE
не змінені. TECHNICAL_READY=false, PILOT_ALLOWED=false.

## Поведінка

- Додано GET `/api/erp/lines/<pk>/supply-options/` з явно обраним optional
  `target_location_id`; повторні або некоректні query-параметри дають 422.
- Додано CEO-only GET `/api/erp/orders/<pk>/settlement/`. Обидва маршрути
  використовують прийняті Policy/read projections, нейтральні 404/409 та
  чинний identity-denial protocol. GET не проводить операцій.
- У картці замовлення користувач обирає закуповувану позицію та, за потреби,
  місце призначення. Видно придатні/непридатні партії й нерозподілені PO.
  Обмежені ролі не отримують загальної доступності або прихованого дефіциту.
- Кнопки резерву, переміщення, закупівлі та оплати відкривають чинний
  ERPActionDialog з окремими preview і confirm. Постачальник, ціна, дата й
  кількість переміщення не обираються автоматично. Нова закупівля зберігає
  чинну початкову валюту UAH; явні EUR/USD не змінюються.
- Фінансові підсумки розділені за валютою, оплати прив'язані до конкретних
  рахунків і показують джерела та неповну історію. Суми залишаються Decimal
  strings. Немає FX або обчислення фінансового підсумку у JavaScript.
- Зміна даних, доступу, сесії або обраного контексту прибирає старі джерела
  й дії. 409 не запускає автоматичний повтор.

## Межа зміни

`erp/views.py`, `erp/urls.py`, `erp/test_flow_projection_routes.py`;
`frontend/boss_app_source.html` та generated HTML/app.js;
`scripts/access_routes.json`, `scripts/access_fixtures.py`, `scripts/check_access.py`;
`scripts/check_flow_projections.cjs`, `scripts/check_flow_currency.cjs` та ця картка.
Два GET definitions додані до catalogue; всі попередні definitions і required
field tests збережені. Історичний inventory writers85/12 не змінений.

## Перевірка й обмеження

Evidence зберігається поза Git у sibling `continuation-evidence-20260920`.
`flow-ui/manifest.json` фіксує точні hashes. Перша SQLite перевірка дала
6 PASS із 7 tests (два settlement regressions і п'ять нових route tests),
exit1 через помилку нової fixture: shipped=0 без invoiced=0. Виправлено лише
fixture; один попередньо невдалий reserve preview/confirm/replay test
повторено окремо: 1 PASS, exit0. Зелений повний повтор не заявляється.

Вісім controlled JSX cases пройшли після двох помилок тестового tree walker.
Після незалежного finding про порожню валюту додано окрему перевірку
actual supply action → actual ERPActionDialog: видимий selector і payload
для UAH, EUR та USD узгоджені. Build, lexical, Python AST і additive catalogue
checks пройшли. Ці перевірки не є браузерним прийманням.

Historical full PG/E2E/P05, A09/Gate8 і A10 не запускалися. Окремий browser
runner і persistent synthetic review-demo потребують власних accepted hashes,
ownership review та фактичного scoped browser result. Ця картка не заявляє
готовність production/pilot або повного document-to-posting сценарію.
