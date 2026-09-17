# C03 core checkpoint 1: незалежний проміжний review

12.09.2026. Читання стабільної копії, без тестів/серверів/БД/змін checkout. Це перелік конкретних меж до фінального freeze, не прийняття C03.

CORE_CHECKPOINT_1.json SHA-256 `86be441eca09e2bea33420fda70b2d97261a77c345ac13e9646fd1f2d4f772ed`; source package `e4d6e0adbb507018a8f0973f287a3994b54536edd141be1637b6346cdc6107b2`. Незалежно звірено всі20 source SHA та6 evidence SHA, розбіжностей немає. Actual core-eight-2.log — 8/8 методів, 1.207с, OK; не називаємо це повним C03, конкурентним PostgreSQL proof або лише8HTTP.

Прочитано statements writer/parser/reads/routes, source upload, financial guard, shared payment helper, policy та proposal integration. У цьому checkpoint підтверджено потрібний напрям lock: ERP mutex → фактичний no-op Transaction UPDATE → fresh fingerprint/джерела. Finance reverse-link validator не бере ERP mutex. Нова Transaction викликає save_transaction з серверним actor та stmt-tx:LineUUID; Line OneToOne і global allocation key відокремлюють cross-actor identity від actor-scoped FinancialIntent. Новий payment та existing Event мають різні delta; cap використовує B03 settlement. Стан/Audit/Event/receipt пишеться всередині confirm atomic; preview не пише домен. Stored receipt повертається перед перевіркою stale, після чинного actor/source gate.

Source marker містить text/source, тож попередній суміжний search-risk врахований. Не-CEO document policy виключає statement code за marker та фактичним StatementImport; транзакції з reverse StatementLine не видаються менеджеру. Нова міграція додає3 ledger і ставить reverse guard останнім forward operation, тобто перед reverse DDL. Майбутні поглиблені fault/identity/concurrency/preservation докази автор ще готує.

## Конкретні відкриті зауваження checkpoint 1

1. **Після create_transaction не можна додати allocation через existing_transaction того самого bound ID.** Literal transaction_intent comparison відхиляє409 режим, який контракт допускає і UI вибирає для вже прив’язаного рядка. Автор підтвердив прогалину свого попереднього тесту. Потрібна actual create → existing sameID + new key regression; первісний binding_snapshot не переписувати.
2. **Status filter summary не приймається.** UI/wire надсилають status до lines та summary, а statement_reads.summary.params його забороняє400; Promise.all не застосовує навіть успішний список. Потрібен один і той самий derived status scope у підсумках та рядках.
3. **Current summary імпорту не узгоджений з UI.** Import detail і exact-byte no_change повертають тільки `{lines:[...]}`; C03StatementTotals очікує currencies. Потрібен погоджений явний shape для поточних підсумків саме refs цього імпорту, окремо від незмінних source_totals.
4. **Export не містить обіцяних refs/statuses.** Нині лише первісні8 CSV columns; UI/wire обіцяють джерела й поточні статуси. Додати явні колонки з ідентифікаторами та поточним станом, зберегти formula-safe текст, не змінювати original bytes/SHA.
5. **Два allocation_key можуть посилатися на один existing payment Event у тому самому preview.** Обидві перевірки StatementAllocation.exists() бачать відсутність запису; при достатній сумі Line preview видає proposal. Confirm потім відкочується на OneToOne другого запису, тобто подвійного committed paid немає, але попереднє погодження хибне. Відмовити цьому явному дублю до proposal, зберігши DB uniqueness та rollback.

Усі п’ять передано автору. Нових власних тестів не запускалося, дублювання авторських advanced regressions не потрібне. Фінальний verdict — після фактичних red→green цих меж, named atomic/source/replay доказів і нового SHA freeze. UI review має окремі response-identity/non-JSON-denial зауваження; помилкову гіпотезу про manager Bank знято після перевірки незмінного App guard.
