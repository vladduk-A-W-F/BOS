# PLAN-LINKS-READ · рішення щодо closed-world каталогу

20.09.2026. Статичне уточнення після незалежного review. Маршрут не реалізований; каталоги та тести канонічного дерева не змінено і не запущено.

## Рішення

Новий **GET** можна додати як окреме additive розширення поточного API-каталогу в межах погодженого C2. Він не додає writer, не змінює заморожену історичну базу 85 шляхів запису / 12 дефектних місць і не перенумеровує її. Підстава — master §1.8 описує саме базу writer inventory; `docs/WRITE_PATHS_UA.md` відносить read-only getters/snapshot/search/export до матриці прав A04. Нове доручення власника дозволяє роботу за C2, але не послаблення приймальних умов.

Водночас додати URL без catalogue/coverage було б неповним патчем: master §2.4 вимагає обходу **всіх** маршрутів. `scripts/check_access.py` точно порівнює live resolver з `scripts/access_routes.json` через Counter(signature). Невідомий доданий route дає `unknown_route_definition`; відсутній oracle — `missing_route_policy`. Історичний writer inventory і чинний closed-world URL catalogue — різні реєстри.

Статично прочитаний поточний manifest має **190 patterns, 57 required_field_tests**. При додаванні лише одного маршруту очікується 191 pattern; перед фактичною інтеграцією треба звірити базовий SHA і врахувати незалежні additive зміни. Це не підстава жорстко замінити чи обрізати актуальний manifest до числа 191.

## Точні файли та зміни наступної картки

| Файл | Обов’язкова зміна |
|---|---|
| `erp/urls.py` | Додати `orders/<int:pk>/trace/` з name `bos-order-trace`; не змінювати next/draft |
| `scripts/access_routes.json` | Додати одну definition нижче. Зберегти кожну поточну definition, callback, converters, multiplicity і всі 57 старих field-test IDs. До `source` дописати датовану additive примітку, не замінюючи походження |
| `scripts/check_access.py` | Додати `/api/erp/orders/{pk}/trace/` в `RAW_GET`; окремий явний branch `contract()` для точних очікувань нижче. Додати `erp.test_order_trace` до default `--field-tests`, зберігши всі шість чинних modules. Не знижувати thresholds57 і не вилучати жодних tests |
| `scripts/access_fixtures.py` | `route_values()` уже зіставляє `api/erp/orders/` із `self.seed.order.pk`; не замінювати на pk=1. Додати positive anchors `bos.order-trace.v1`, фактичний order_id і `A04-SO-OPEN`; додати canaries/контрольні джерела для hidden reservation, недозволеного InvoiceLink та задачі з hidden historical ref |
| `erp/test_order_trace.py` — новий | Named tests для всіх нових role/field-boundaries; їхні точні ID додати до required_field_tests після створення і звірки discovery. Не оголошувати нестворені тести вже наявними |
| `docs/ACCESS_UA.md` | Additive опис дозволених полів і джерел trace без розширення фінансових прав |
| `docs/orchestration/evidence/PLAN_LINKS_READ_ROUTE_DELTA.json` — новий | Базовий/новий manifest SHA, додана definition, додані required field IDs, збережені counts/пороги, explicit `historical_write_inventory_85_12_unchanged=true`, scope перевірок і фактичний review verdict |

Пропонована definition:

```json
{
  "pattern": "api/erp/orders/<int:pk>/trace/",
  "name": "bos-order-trace",
  "callback": "erp.views.order_trace",
  "actions": null,
  "model": null,
  "converters": {"pk": "IntConverter"}
}
```

Назви й callback — контракт наступної реалізації, зараз їх немає. Нового DRF format alias не потрібно; не додавати неіснуючі `.json` маршрути за припущенням. `catalogue()` вже рекурсивно обходить resolver, тому його механізм не змінюється. Поточний `canonical()` уже перетворює числовий ID у `{pk}`.

## Явний oracle нового маршруту

Для стабільної синтетичної fixture; за валідного CSRF там, де middleware його вимагає:

| Контекст | GET | HEAD / OPTIONS | POST / PUT / PATCH / DELETE / TRACE / CONNECT |
|---|---|---|---|
| anonymous | 401 | 401 | 401 |
| technical_admin без business role | 403 | 403 | 403 |
| ceo | 200, непорожній дозволений trace | 405 | 405 |
| manager, full | 200, операційний allowlist | 405 | 405 |
| observer, full | 200, allowlist спостерігача | 405 | 403 |
| manager/observer, no_documents для fixture order з документом | 404 без реквізитів order | 405 | manager 405 / observer 403 |

CEO/no_documents лишається 200 за чинною Policy; варіанти no_download/no_export не забороняють звичайне читання trace, але не надають файлів/експорту. Для невідомого та недоступного order — однакова нейтральна 404. Відкликана identity, detected change під час читання і невірні HTTP methods перевіряються окремими named tests, а не широкою множиною «200 або 409 або 404» у стабільному sweep oracle.

`read_state_changed` — 409 без business payload лише у спеціальній перевірці змін під час читання. Вона не дозволяє прийняти 409 як звичайний успіх GET у стабільній role fixture. GET не створює audit/proposal/configuration, зовнішніх викликів немає; state digest до/після read-case незмінний.

Семантичні access-тести щонайменше перевіряють hidden reservation → null/restricted, invoice тільки через дозволений InvoiceLink, tasks тільки через `Policy.tasks()` з historical refs, current-role refresh, відсутність raw payload/цін/собівартості у недозволених відповідях і непорожній позитивний trace. Їх додають до наявного обов’язкового набору, а не замінюють ним старі 57.

## Межі доказу

Цей документ підтверджує рішення щодо allowlist та catalogue wiring на рівні статичного читання. Немає нового PASS gate4, запуску `check_access --catalogue-only`, full suite або PostgreSQL. `--catalogue-only` у чинному коді навмисно завершується incomplete/exit1 і сам не є прийманням. Ліміти повторів і C1-блокери зберігаються; потрібний дозволений адресний proof та незалежний review майбутнього diff.
