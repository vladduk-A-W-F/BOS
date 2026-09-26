# BATCH-02 / N2 · erp_adjust: інвентар і контракт реалізації v1

20.09.2026. Власник доручив додати реалізацію та продовжити після рекомендації дозволяти підтвердження за незалежних змін. Це технічний дизайн вузької картки, не дозвіл production або повних історичних повторів. Source runtime SHA256: `31c692c5f3113446452e8d15faf95c29b019f433550bf4d0658c4f0428e54d20`. Статичне читання; тестів поки немає. Повні SHA20 прочитаних файлів у SOURCE_MANIFEST.json.

## Встановлений контракт поточної дії

`erp.views.preview` чистить payload, перевіряє Policy, бере `erp_write`, повторно читає Policy, глобальний fingerprint і повний snapshot, виконує dispatch(log=False), отримує другий snapshot, impact і receipt projection та відкочує симуляцію. Окрема `operations.service.preview` зберігає proposal з початковим token. Generic `/api/operations/preview/` не симулює ефект; для нього v1 лишає global fingerprint. `execute` звіряє session/user/role, бере той самий mutex, перечитує proposal і actor, перевіряє Policy, має окремі statement/correction/task гілки, повертає receipt до expiry/state-check, а для нового ERP виконання робить CAS receipt, dispatch, Event update і persisted receipt в одній транзакції.

`erp_adjust` є CEO-only одночасно в Policy.CEO_ACTIONS і dispatch. Payload має рівно action/lot_id/delta/reason; ID додатний int, reason text до4000, delta finite з abs≤1000000 і точністю≤3, reason.strip() непорожній. Delta може бути нуль. `move` вимагає lot.quantity+delta≥0 і ≥SUM(reservations.quantity), перевіряє Decimal field bounds, змінює лише quantity; cost=abs(delta)*unit_cost з money bounds; створює Movement(kind=adjustment, reference=lot.code, reason, quantity, cost). Dispatch створює Event лише при log=True. Суми currency не конвертуються.

## Повний інвентар прямих dependencies

| Read | Для чого | Захист v1 |
|---|---|---|
| Очищений payload, зокрема reason і delta | Намір, валідація, Movement/Event | Серверний canonical payload hash; клієнт не передає context |
| ActionProposal session/user/role/expiry/receipt | Власність, строк, повтор | Чинні перевірки; context не підміняє їх |
| User active/groups/Employee user-link+archived | actor і CEO-доступ | Fresh actor після mutex; Policy.access_revision до й після застосування |
| User permissions, employee_id, role | Контекст доступу | Свіжий Policy.access_revision у dependency digest |
| Target Lot, повний row | Кількість, cost, код, currency, revision, документи, item/location membership, display | Canonical full row; існування обов’язкове |
| Target Item, повний row | required_documents для usable; ідентичність і консервативний захист source context | Canonical full row |
| Target Location, повний row | Контекст місця target lot; консервативна залежність | Canonical full row |
| Усі Reservation WHERE lot_id=target, повні rows ORDER BY pk | SUM(quantity), членство, вставка/зміна/видалення навіть за незмінної суми | Повний необмежений набір, з порожнім набором включно |
| Усі Movement WHERE lot_id=target, повні rows ORDER BY pk | Консервативна історія/ідентичність target; валідація move історію не читає | Повний необмежений набір, не snapshot[:300] |
| Lot.documents selected IDs плюс Item.document_id; пропущені IDs | Джерела target та відсутність row | Canonical metadata кожного ID або явний missing marker |
| Усі версії Document для code кожного знайденого linked doc, ORDER BY pk | newest(code), вставка нової версії, видалення/заміна | Повний набір metadata за code; metadata включає id/code/revision/status/checksum/access_level/original_file/size/text-hash/content-hash/created_at/contract_id/title/filename/sections |
| Фактичні bytes selected linked documents | usable і джерельна цілісність, навіть якщо checksum у БД незмінний | verified_document_bytes, SHA дійсних bytes; якщо існуючий selected файл не верифікується, новий scoped mode не видається, залишається legacy global preview |
| `erp_write` Configuration revision | Серіалізація | Чинний mutex; revision не входить у адресний digest, інакше незалежна дія знову invalidates |

Canonical JSON: sort_keys, stable separators, Decimal/date через однакове серверне кодування, явні model/field назви; не лише PK, час або SUM. Для залежностей немає mutable кешу між preview і confirm. Немає нових лічильників ревізій, отже `.update`, bulk, import і прямий ORM між двома фазами не пропускаються через відсутній signal. SHA виявляє відмінність поточного стану; не заявляє виявлення будь-якого ABA з побайтово відновленими всіма IDs/значеннями через довільний DBA-доступ. Штатні шляхи не фізично видаляють Lot/Item/Location; FK PROTECT та історія Movement зберігають ідентичність. Непокритий конкурентний довільний SQL поза mutex не стає підтриманим writer.

## Snapshot/показаний вплив: що реально погоджує користувач

Повний `queries.snapshot` читає Item/Location/Lot/Order/Line/Production/Reservation/Purchase/Inspection/Change/OperatorEntry; correction models+source movements; Invoice/InvoiceLink/settlements; Employee/Counterparty/requests/documents; Event; movements[:300]; plans, replenishment, costs, supplier_scores, summary і dataset/as_of. Ці reads потрібні загальному екрану, але весь snapshot не повертається з preview: повертаються payload/effect/impact.

`experience.impact` порівнює тільки явний `FIELDS` whitelist. `erp_adjust` змінює тільки target Lot.quantity і derived Lot.available. Усі інші FIELDS rows незмінні за одну замкнену симуляцію під ERP mutex. Plans, replenishment, summary, supplier_scores, costs, events і movements не є FIELDS і не входять у показану impact-таблицю. Target reserved/quality/documents/missing_documents можуть впливати на calculation, але сама adjust їх не змінює. UI показує payload reason/delta, label lot.code/revision зі snapshot екрану й impact rows; lot full row захищає code/revision. Item/location включаються консервативно.

В v1 shared helper будує snapshot тільки target lot з тими самими quantity/reserved/available/missing_documents правилами, передає його незміненому `experience.impact`. Preview і confirm використовують один helper. Це явне звуження внутрішнього обчислення тільки для scoped adjust, не зміна shown impact. Глобальний dashboard як і раніше перезавантажується після confirm. Не потрібно включати всі SalesLine/Purchase/Production тільки через те, що старий snapshot обчислював довідкові плани, які preview не показував.

Зберігаються expected effect і expected impact hashes початкової симуляції. Перед commit, після справжнього dispatch, receipt effect без нового erp_event_id і новий impact мусять збігтися; інакше вся транзакція відкочується. Права recheck теж до завершення транзакції. Це додатковий захист від розходження effect при неповному inventory/зміні code, а не дозвіл застосувати перерахований ефект мовчки.

## Writers і конкурентна межа

| Dependency | Штатні writers | Lock/межа |
|---|---|---|
| Lot.quantity, Movement | dispatch adjust/transfer/finish/ship; corrections return_supplier; newlot через opening/receive/finish/return/import/correction return_from_shipment | dispatch @atomic + ERP mutex; nested dispatch його зберігає |
| Lot.quality/documents | dispatch quality/attach; newlot callers | Той самий mutex |
| Reservation membership/quantity | reserve create; release; finish consume; ship consume; cancel_remaining через nested release | Той самий mutex; нульові rows лишаються і входять у digest |
| Item/Location | dispatch item/location create; apply_change item revision/document; initial import через dispatch | Той самий mutex; no runtime Item/Location/Lot/Reservation admin registration |
| Document versions/status/storage binding | upload/review; document_migration | Усі беруть ERP mutex; filesystem immutable verified storage. Migration на реальній БД не виконується цією карткою |
| User/groups/permissions/Employee identity | Django technical admin, auth setup/demo, link_bos_user, Employee archive | Власні DB writes/locks, не ERP mutex. Fresh current identity/access_revision після ERP wait і до commit; не заявляємо глобальну серіалізацію identity writers |
| Синтетичні fixtures, offline bootstrap/import tools | Створення контрольованої БД, management setup | Не live writer контракт; new targeted tests можуть ORM-мутувати dependency між preview/confirm, щоб довести reread |

Референс-lock порядок для інших дій не змінюється. No new route, no external API, no frontend framework.

## Зберігання та compatibility

Один nullable `ActionProposal.dependency_context = JSONField(null=True, blank=True)` і additive migration. Обґрунтування: payload лишається користувацьким незмінним наміром, fingerprint64 лишається початковим глобальним SHA, receipt null зберігає CAS/replay. Overload hash або receipt зламав би ці контракти; окрема revision table потребувала б ширшого writer instrumentation. Міграція тільки синтетичної тестової БД.

Context v1: exact keys `mode='erp_adjust'`, `version=1`, `payload_sha256`, `dependency_sha256`, `access_revision`, `effect_sha256`, `impact_sha256`; усі hashes64hex. Зберігається тільки сервером після scoped preview. Клієнтські додаткові context/mode/version поля відхиляються чинним clean.

Null context: повністю чинна global перевірка, включно зі старими proposals і generic operations-preview. Valid v1/erp_adjust: explicit scoped check; початковий global збережений для diagnostics, але незалежна зміна не відхиляє scope. Unknown mode/version, wrong action, malformed values, absent required context keys: 409 новий preview без business writes; не recompute-current-as-original і не мовчки переводити старий proposal в новий mode. API response може містити серверне `consistency` mode/version для evidence без internal hashes; це необов’язково UI не потребує.

Replay лишається перед context/state validation, але після чинних fresh identity/Policy; завершений receipt повертається без нового Movement/Event навіть якщо target або інша lot згодом змінилась. Unknown context не впливає на вже committed receipt replay.

## Allowlist реалізації

1. `erp/adjustment_proposals.py` новий helper залежностей, scoped snapshot і context validation.
2. `erp/views.py`: scoped preview тільки erp_adjust, capture початкових tokens під lock, effect/impact з helper, server-only context передає до approvals.preview.
3. `operations/service.py`: internal keyword context до create, scoped validation і post-dispatch effect check, legacy branch збережено.
4. `operations/models.py`: один nullable JSON field.
5. `operations/migrations/0007_actionproposal_dependency_context.py`: additive migration.
6. `erp/test_adjustment_proposals.py`: нові targeted behavior regressions.
7. Evidence/doc files після review. `erp.service.dispatch/move`, Policy, existing tests, CI та frontend не змінювати цією карткою без окремого finding/review.

## Адресні докази для review (ще не запускались)

1. Два реальні CEO/users+sessions: preview A/B на різних lots, confirm B потім A:200/200; по одному persisted Movement/Event, показаний initial impact==receipt impact. Спільний Item/Location дозволений, якщо їх row не змінено.
2. Same-lot pending proposals: перший200, другий409; no writes/refused receipt.
3. Target Reservation INSERT (включно sum-preserving membership), update/delete; Lot qty/unit_cost/quality/documents/revision/code/item/location; Item required_documents і Location metadata:409. Незалежні lot/reservation changes:200.
4. Document newer revision under same code, status/checksum/access metadata, selected real source bytes changed with DB unchanged:409. Missing→present document dependency; invalid source scoped fallback explicit.
5. Expiry, wrong user/session, role revoke, permission/access revision change, Employee archive; cached request Policy не рятує proposal. Lock precedes scoped reads; після mutex auth reread.
6. Confirm/replay after independent+target changes: один receipt, no duplicate Movement/Event; current role revoked still403/401.
7. Null context old/operations generic proposal: незалежна B як раніше дає409; malformed/future/mismatched context:409 без writes; client-supplied fields422.
8. Frozen effect/impact mismatch intentionally introduced by controlled hook between validation and application: whole transaction rollback; test checks quantity, Movement/Event, receipt, mutex, not only status.
9. Shared lot-only impact versus existing full snapshot on valid usable, reserved, blocked, missing-doc and delta0 fixtures; no omission of shown field. Precision/bounds remain dispatch-owned.
10. Один адресний PostgreSQL16 concurrent distinct/same-lot/receipt check після SQLite proof і review, якщо root видасть конкретну нову CI-картку. Не full suite, не gate3, не E2E, не P05 retry. SQLite proof не є PG concurrency proof.

## Межі / blockers

Немає власницького блокера дизайну: user semantics схвалені. До коду потрібний independent design review; до інтеграції raw scoped tests + independent diff review. No claim runtime performance improvement, F04/F05 closure, technical/pilot readiness або multi-company SaaS. New migration source не означає deployment. Зміна правил action/digest в майбутньому вимагає version bump і нового preview; source binary deployment не перемикає legacy mode.
