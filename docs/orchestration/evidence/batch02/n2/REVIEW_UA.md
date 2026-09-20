# BATCH-02 · незалежний review N2 erp_adjust

20.09.2026. Reviewer `/root/bos_batch02_review`, не автор. **ACCEPT_SCOPED_IMPLEMENTATION** для інтеграції і окремої нової PG16 CI-картки. Product behavior на PostgreSQL ще не доведено. Reviewer не виконував app tests, міграції, GitHub writes чи deploy.

Design спочатку прийнято як ACCEPT_SCOPED_DESIGN після actual reads операції adjust/move, locks/Policy/identity, preview/snapshot/impact і private documents. Потім прочитано повний helper, production diff, nullable migration, усі portable та PG-only тести, raw baseline red і обидва candidate runs. SHA шести змінених source files і одинадцяти evidence artifacts звірено.

Перевірені гарантії реалізації:

- Тільки серверний ERP preview `erp_adjust` видає version1 context; role CEO та старий dispatch/move збережено.
- Під первісним mutex знімаються global fingerprint і digest повних Lot/Item/Location, необмежених Reservation/Movement sets, відсутніх і наявних selected documents, same-code version membership, actual verified bytes та access revision.
- Payload/fingerprint/receipt не перевантажено. Additive nullable dependency_context; null старі/generic proposals лишаються global. Некоректний чи невідомий context відмовляє без бізнес-запису.
- Previously scoped byte-integrity failure не переходить у global. Початковий невалідний файл не видає scoped mode, зберігаючи попередню legacy поведінку.
- Лише target-lot impact computation звужено. Чинний FIELDS показує, що adjust змінює лише target quantity/available. Portable parity tests порівнюють full і scoped impact у чотирьох станах.
- Confirm зберігає session/actor/role, mutex і post-wait reread, Policy, expiry, CAS та атомарність. Expected effect/impact і актуальні права перевіряються після dispatch до commit; невідповідність відкочує quantity/Movement/Event/receipt/mutex.
- Receipt replay лишається після свіжих прав і до state/expiry checks; не створює повторний бізнес-ефект.

Докази: baseline red1 має саме 409!=200 після незалежної lot зміни. Candidate attempt1 має18 PASS та одну fixture ERROR серед19 methods: старий ArchiveModel правильно відхилив створення одразу archived Employee. Виправлено тільки нову fixture через create→штатний archive, умову refusal не послаблено. Targeted2: цей метод плюс actual private-file bytes з незмінним DB row та post-dispatch access change, 3/3 PASS. Разом21 різний portable method має PASS у збережених runs; це не один чистий21/21 run. Product source між ними не змінено.

Окремий finding до authored PG-тестів виправлено до запуску: signal перед B.execute не доводив фактичне блокування в PostgreSQL. Фінальний test тримає A, доки третій monitor connection не побачить `pg_blocking_pids(B)` із PID A і `wait_event_type=Lock`. Після цього відпускає A. Три різні PID, bounded waits, actual SQL forwarding once, same-lot/independent/replay результати та бізнес-кількості перевіряються. Ці три PG-only tests ще НЕ ВИКОНАНІ; на SQLite відмовляють, не skip.

Блокувальних product findings у цьому scope не виявлено. Patch SHA256 `f5e73f33df69b5fd9ab01ca9bc23404f2f8f5d3eef3a0c2087c8e751e51dcf6d`. Helper SHA `0eaf7a62baa91b7a7f58ed7684993328b343c7bedc4102cd8af8b94ba1d32f94`. Final test SHA `960573c1e573758f3d81b4f512ca970ed817a3f1b39dd9addb749efbd00e8217`. Інші SHA в CHANGED_SHA256.json/EVIDENCE_SHA256.json.

Межі: state digests, не persistent revision counters і не захист від довільного DBA/ABA поза підтриманими writer контрактами. Не заявлено прискорення, масштабування чи причину F04/F05; global SHA при preview все ще обчислюється. Немає production migration/activation, інших scoped ERP actions, full/gate3/E2E повтору або закриття readiness. P05 3/3, A09/A10/A11 незмінні; TECHNICAL_READY=false, PILOT_ALLOWED=false.
