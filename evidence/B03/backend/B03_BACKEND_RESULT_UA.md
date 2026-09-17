# B03 · результат ізольованого backend-кандидата

Кандидат побудовано на коді B02 0.2.12-dev. Канонічний репозиторій, його база та media не змінювались. Це виконаний локальний backend етап; загальне приймання B03 потребує інтеграції root і повного verify.

Реалізовано шість дій через чинні preview/confirm та ERP mutex: скасування невиконаного залишку, повернення конкретного приймання постачальнику, повернення конкретного відвантаження клієнтом, кредитове коригування рахунку, повне сторнування кредиту, окреме підтвердження вимоги постачальнику. Додано шість захищених реєстрів і міграцію 0005. Початкові кількості, виконання, рахунки та старі джерельні події збережені; кошти автоматично не повертаються.

Облікова вартість нового повернення розподіляється з фактичної вартості його руху-джерела накопичувальним HALF_EVEN. Кредитові бюджети обчислюються з первісного InvoiceLink за ordinal, без підміни поточними цінами. Один settlement helper використовується читанням, оплатою та підказками. B02 історичні залишки зберігають свій первинний snapshot і receipt.

Новий GET outcome знаходить завершений намір за точним action+UUID, перевіряє поточну роль і джерела та не створює записів. Unknown/hidden 404 не означає відсутності commit. Повтор повертає перший receipt/Event/actor. Нові читання містять повні доступні джерельні й результатні рухи та лише пов’язані B03 events. Історичний прихований документ блокує повернення, його claim, event, replay та outcome; недоступний агрегат позначено restricted/null.

| Фактична перевірка | Результат і доказ |
|---|---|
| Початкові чотири HTTP сценарії до реалізації | 4 очікувані відмови unknown action; `initial-red.log` |
| Початкові ті ж сценарії після реалізації | 4/4; `first-after.log` |
| Знайдені review дефекти | Історична видимість, prospective source lot, низький Decimal context, cancelled BOM ETA, duplicate events, financial next-step inference: фактичні red, вузькі правки, green; журнали `review-*`, `bom-red`, `projection-*` |
| Основні B03 + B01/B02 сумісність | 55/55, 32.056 с; `compat-green.log` — 18 B03 та збережені попередні сценарії |
| Завершальні source regressions | 3/3, 6.684 с; `final-sources-1.log` — B01 allocation після cancellation, спільна return quantity між двома invoices, чотири real HTTP конфлікти зі старими діями |
| Шість заповнених нових реєстрів | 3/3, 8.946 с; `preservation-1.log` — SQL constraints, PROTECT, reverse refusal до DDL, exact typed copy 53 tables і п’ять receipt replay |
| Історичні typed-transfer тести | Реальні 53≠47 red2/2; після точного додавання шести таблиць green2/2, 12.044 с; `typed-compat-*` |
| Gate 5 final | 99/99 методів, 110/110 фактичних records, 33 actions; `gate5-final.json`, без skip/expected-failure |

Gate 5 зберігає буквальні baseline A06 84/89/26 (SHA db069888…) та B02 88/92/27 (SHA e81e275e…). Додано 11 методів: по EUR/USD/UAH для кожної з шести дій, distinct proposals одного intent, конкуренція різних intents за всі шість source budgets, cancellation/receive, credit/payment та cancellation/ship/reserve і return/transfer/reserve. Усі записи друкуються фактичним потрібним тестом; manifest не генерується під час gate.

Дві історичні міграційні fixture виправлено тільки в setup. B01 спочатку створює справжній HTTP PO на latest і потім переходить до точної 0003 за доведено порожніх пізніших реєстрів. B02 аналогічно фіксує 0004 до запису еталона. Початкові state/assertions, reverse guards і high-water докази збережені; populated snapshot не стирається.

Три restore-файли root скопійовано за frozen SHA з `b03_restore_candidate/FROZEN_MANIFEST.json`: попередні 12 сценаріїв плюс 2 нові, exact B02 47 + B03 6 = 53. Root виконав 14/14 на своєму ізольованому знімку; я не повторював native restore. Остаточний канонічний verify має використати фінальні policy та UI.

Під час підготовки тестів були дві неточності fixture (неправильний `/next-action/` замість `/next/`, quantity замість delta старої adjust) та необхідне ORM refresh у BOM fixture. Їх виправлено без змін бізнес-контракту; початкові журнали збережені й не видаються за окремі продуктові дефекти.

Не заявлено: PostgreSQL, Windows, реальний браузер, клієнтські дані, production/банківські операції, AP, автоматичні cash refunds, атомарна комерційна заміна або завершення всього MVP. Canonical full verify виконує root після незалежного огляду й інтеграції.

Access extension: 54/54 actual HTTP requests (5 roles ×9 methods + manager/no_documents ×9), six real fixture preview/confirm200. Old176 route objects byte-identical, newroute177; all57 required fieldtest IDs unchanged. Access proof uses exact final core SHA. Root native restore proof uses the earlier stated isolated snapshot and is due for canonical full23 rerun.
