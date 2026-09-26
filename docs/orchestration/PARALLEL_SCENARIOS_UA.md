# Три паралельні сценарії: поточний контракт інтеграції

20.09.2026. Усі три сценарії продовжуються паралельно відповідно до прямого доручення власника. Попередню вимогу обрати лише один сценарій не застосовувати. Реалізовані UAH/філії/owner та збережені джерела повторно не створюються.

База цього патча: `646d3b80597e087a1ada14221024ec40588996f0`; tree `1b0bf4e03a4e506d76f2d264e173d1bdc23e7fd3`. Frozen runtime: `98b011a583c7803d88c888070a3412789559919ecb5692ef34f5e8ad59b5072a`. На GitHub у збереженому спостереженні залишається `3d979060fe9862119ba8ad6c9d8bd505103796e3`; локальні одинадцять комітів не оголошено опублікованими. Попередню базу530043a, її freeze та невдалу browser-attempt4 збережено окремо.

Єдиний поточний інтегратор Git і спільних файлів — `/root/product_integration_continuation` у задачі головного оркестратора `01a0be90-e790-7351-a8ac-059d523941c4`. Старий `bos-fullgit-20260920` зберігається без змін; зовнішня reservation лишається чинною. Автор не приймає власну картку. Окремі evidence/registry роботи передають тільки патч для послідовного review та застосування інтегратором.

| Сценарій | Уже інтегрована обмежена частина | Що ще не прийнято |
|---|---|---|
| S1: замовлення → резерв → відвантаження → рахунок → часткова оплата/борг | S1 recovery, CEO settlement, GET; фактична оплата12.34UAH через UI preview/confirm і HTTP replay того самого proposal без дубля на646d3b8 | Повний order-to-debt процес та всі потрібні persisted-state/stale/role докази |
| S2: документ постачальника → витяг → зіставлення → приймання/виняток | Pure mock контракт, Policy/оригінальні bytes, read-only GET/UI; ordinary document фактично повернув unsupported_document без запису на646d3b8 | Тільки synthetic one-line/full-PO matching; немає AI/OCR, persistent exception queue, approval, posting або supplier bill. `accept_draft` не є проведенням; `operation_proposal=null` |
| S3: дефіцит → закупівля/переміщення → приймання/якість → запас | Supply read, явний склад; фактичне переміщення1шт. через UI preview/confirm і HTTP replay того самого proposal без дубля на646d3b8 | Повне завершення закупівлі/приймання/якості з узгодженням кінцевого запасу |

Суми та кількості залишаються Decimal strings. Валюти й одиниці не конвертуються неявно. Філія замовлення відокремлена від фізичного складу. PO не обіцяє резерв цьому замовленню. Restricted-ролям не показують приховані глобальні баланси або непрямий дефіцит. GET не пише. Optimistic double-read та write revision не є atomic snapshot.

Первісний S3 finding про відсутність OrderCancellation у fingerprint відкликано: service розширює MODELS моделями corrections. Доданий write_revision — додатковий бар'єр, не виправлення доведеної старої гонки. Settlement P2 про strip raw payment reference був дійсним і виправлений; writer та історія не переписані.

Actual browser-attempt4 на530043a збережено як FAIL exit1: zoom200 PASS, Escape не повернув фокус opener, downstream flows не запускалися. WORKPOINT-DIALOG-FOCUS увійшов окремим комітом646d3b8. Головний незалежно прийняв actual attempt5 на646d3b8/98b011a583c7803d88c888070a3412789559919ecb5692ef34f5e8ad59b5072a: exit0, Gate10 7/7 і окремі bounded flows3/3. Перевірено SHA/довжину26 артефактів; child8084 і launcher12712 завершені, одноразову середу видалено, source/DB незмінні. Жоден із трьох повних сценаріїв або Gate6 цим не оголошено закритим.

Постійний synthetic working-mode стенд http://127.0.0.1:8876/ також незалежно прийнято на646d3b8: звичайний CEO login, nonstaff/nonsuperuser, actual browser1440/390, без помилок. За receipt сервер залишено працювати; root додатково отримав publicHTTP200. Evidence writer не повторював HTTP/browser. Дані й media окремі, AI не налаштовано, DPAPI secret не виводився. Після нових змін/merge ця приємка потребує окремого зіставлення.

Окремий PR2 (`abb8845f6563bafa806029ddc1e7c2cace09907c`, product `b10760b16dfe933511cd880f02a29d840c03dcc1`) має статус RECONCILIATION_PENDING. Network/transfers/retentions/datasets та тести тієї гілки не інтегровані й не зараховуються цьому кандидату. Незалежне порівняння веде browser_evidence_check; merge та дублювання audit відсутні.

Усі 11 початкових критеріїв незмінні. `TECHNICAL_READY=false`, `PILOT_ALLOWED=false`, P06 BLOCKED; P05 3/3 і A09/A10/A11 збережені. Старий access-current-1 не поновлювати з цього доручення. Нових full/PG/E2E/Windows presets, paid API, реальних даних, production чи merge цей пакет не дозволяє. Детальні межі та прив'язки: [продовження](CONTINUATION_20260920_UA.md).
