# B01 — незалежний огляд backend закупівель

Дата: 12.09.2026. Рецензент: `/root/a09_server_review`. Джерело: `tmp/b01_candidate/source`, manifest `tmp/b01_candidate/B01_FROZEN_MANIFEST.json`.

**Фінальний висновок: scoped consensus для backend B01. Основний контракт, права, джерела, allocation/replay та збереження історії відповідають перевіреним межам. Знайдені root tax-basis і reverse-migration defects виправлені та мають фактичні докази. Нових блокерів не виявлено.** Checkout не редагували. Нові тести, сервери та SQL не запускали; вихідні БД не відкривали. Огляд не дублює роботу автора reverse guard.

Фінальний manifest SHA256: `8da3ff8ad0b27329bc9f5fa1b852ca728840c85a0a72b535c0a8bd10b902a59c`. Звірено **13/13 source files та 10/10 evidence logs**; усі hashes збігаються. Факти: `tmp/B01_BACKEND_REVIEW_FINAL_HASH_FACTS.json`. Backend consensus прив’язаний до цього manifest; поточний UI і майбутній повний verify не входять до нього.

## Контракт і межі

Прочитано `tmp/B01_READY_PLAN_UA.md`, source diff, реалізацію авторизації/прогнозу/погодження, source tests та наявні logs. Purchase — погоджене зобов’язання з Quote або явною причиною прямої закупівлі. Погодження не створює складського приходу чи оплати; приймання використовує чинний окремий writer.

Поділ вимоги між постачальниками дозволений; немає `UNIQUE(request)`. Допускаються кількості до 0,001 без нав’язування валюти планової собівартості Item як валюти конкретної закупівлі. Підтвердження кількості/дати назване засвідченням менеджера, а не незалежно отриманим підтвердженням постачальника. Розрахунковий lead time не замінює погоджену due date.

## Перевірені властивості реалізації

**Джерело.** Quote має відповідати явно вибраній вимозі й постачальнику. Номенклатура звіряється за явним кодом або документом, одиницею та версією. Валюта, price/extras, чинність, MOQ і комплектність перевіряються на сервері; вихідні numeric terms канонізуються. Due date обмежена as_of/required_by. Документи мають дозволений reviewed status, актуальну версію та перевірені оригінальні bytes/SHA. Для private-file джерела не використовується запасний BLOB, якщо файл змінено.

**Mutex і конкурентність.** Preview/confirm використовують чинний ERP mutex; source validation та сума всіх `Purchase.quantity` за вимогою читаються після lock. Нові writers request_create/quote_create також беруть той самий lock до предметних читань; upload/document_review уже використовують його. У fingerprint додано повні ProcurementRequest і SupplierQuote rows; зміна джерел відхиляє старий proposal. Виконання повторно перевіряє особу, поточні права, source fields і залишок. Подвійне погодження 6+6 при вимозі 10 підтверджене actual HTTP concurrency: один 200, інший 409; рівно один PO/Event, кількість 6.

**Атомарність та історія.** PO, approval_snapshot, Event і receipt записуються в одній транзакції. Фактична помилка SQL trigger на Event відкочує PO/receipt, після зняття збою той самий proposal виконується. Успішний replay повертає збережений receipt без нового запису, за повторної перевірки поточних повноважень. Snapshot містить agreed quantity/date, server-derived costs, original terms, джерельні ID/version/checksum та підставу. Зміна Quote terms або перенесення поточної due date не переписують погоджену історію. Новий Quote FK має PROTECT; snapshots не приймаються з довільного клієнтського payload.

**Права й видимість.** Для PO одночасно перевіряються доступність current request/quote та document IDs зі збереженого approval snapshot. Переприв’язка Quote до нового доступного документа не відкриває PO, якщо історичне джерело стало прихованим. Це поширюється на snapshot/export та повернення історичного receipt. Observer не отримує original terms, prices/extras, supplier attestation або direct reason. Якщо хоча б один PO вимоги недоступний, aggregate allocated/remaining стає `null` з `allocation_visibility=restricted`; часткова сума не видається за повну. Операційний Lot лишається доступним за власними правами; прихований закупівельний snapshot до нього не додається, пов’язаний Movement з прихованим purchase не розкривається.

**Суми за валютами.** Actual proof точно охоплює окремі EUR/USD/UAH: 10 × 12,34 + 5,00 = 128,40; два надходження 4 та 6 з `pending` quality, однаковий receipt при повторі й відмова надлишку. Валюти не підсумовуються разом і не конвертуються. Контракт B01 явно зберігає чинне округлення unit cost; це не доказ збереження кожного довільного landed-cost залишку округлення. Інші правила округлення — окремий грошовий scope, не нова непогоджена зміна цього review.

## Фактичні докази початкового freeze

- `red-1.log`: 11 методів, 13 failures (з урахуванням subtests); реальні відсутні B01 властивості.
- `after-2.log`: 17 методів, усі пройдено, без skip. Прочитано самі assertions: позитивні записи/суми/права, негативні side effects, concurrence та native migrations, а не лише лічильник завершення.
- `tax-basis-red.log`: відтворено 422 для існуючого `tax_basis=excluding_VAT` через старий exact-set. Candidate дозволяє тільки цей відомий додатковий ключ/значення; тест підтверджує збереження в snapshot та відмову `including_VAT`.
- Compatibility: **operations 48 + ERP 49 = 97 перевірок із набору 151**, плюс один існуючий concurrent-purchase метод для EUR/USD/UAH. Це не повний 151/full verify; дані ERP seed/assistant contract та fixture прямої закупівлі доповнено явною причиною за новим контрактом.
- `after-1.log` з чотирма failures збережено як історичний проміжний результат; він не замінює фінальний green. Корекції fixture не видаються за продуктове red → green.

Сім hash evidence початкового manifest звірено; незмінні 12 source файлів збіглися. Test файл почав змінюватися під час повідомленого reverse-fix, тому старий source manifest не приймався за фінальний refreeze. Факти цього проміжного читання збережено в `tmp/B01_BACKEND_REVIEW_HASH_FACTS.json`; остаточний refreeze звірено повністю окремо.

## Блокер зворотної міграції — закрито

Root виявив, що reverse міграції 0003 видаляв уже заповнені Quote FK та approval_snapshot. Прочитано actual `reverse-source-red.log`: після реального HTTP approved PO rollback не відмовив і змінив columns/constraints/rows/migrations. Це втрата погодженої історії; одного sequence-preserving AddField недостатньо.

Прочитано мінімальний fix автора: reverse RunPython guard як остання forward operation, тому на reverse він виконується до видалення колонок. Guard використовує історичну модель і конкретний database alias, відмовляє за **будь-якого** non-null quote або approval_snapshot (OR, не AND). Історичні PO із двома null залишаються сумісними з forwards/backwards; `_preserve_sqlite_sequence` зберігає deleted-row high-water, не лише MAX(id).

Фінальні змінені SHA:

- `erp/migrations/0003_purchase_source.py`: `a81774d834ed82a5e68beb9ef745bdaff2b99d01c6173d246a988f4f8ee27e18`.
- `erp/test_procurement_bridge.py`: `16bf2a9bcf23c08b8793c2f79cfc4baa71e0d41c38724e28d675ceebe3abefed`.

`reverse-source-green.log`: **2/2**, actual approved PO rollback відхилено, `changed=[]` для columns/constraints/rows/migrations/sequence; окремий legacy-null test з forwards/backwards і deleted high-water також пройшов. `final-18.log`: **18/18** за 4,303 с, без skip; разом повторно підтверджено concurrency 200/409 та reverse refusal без змін. Це не доведений downgrade populated B01: правильно прийнята саме відмова від втрати історії.

## Неприйняті межі

B01 frontend/browser path, PostgreSQL execution, інтегрований full verify та повний master criterion 6 цим оглядом не прийняті. Відкриті критерії A10/A11, activation/upgrade/rollback та загальна відсутність MVP readiness залишаються явними; вони не забороняють продовжувати B01. Final refreeze прийнято в наведених backend межах. Наступне приймання належить конкретному інтегрованому коду/UI та його фактичному full verify; рецензент нових необов’язкових прогонів не виконував.
