# PLAN-N1-REQUEST · scoped інтеграція

Сирі рядки code/part/revision/unit перевіряються за metadata до write_lock; без strip/truncate. Red: 36 failures у 2 методах. Green: 5/5 разом з чинними invoice boundary і hidden-document regressions, exit 0. PG16 ще не перевірено. Незалежний reviewer ACCEPT_SCOPED.

Runtime SHA256: `853ac1c0473c685961ebb488922fa4f93a981a8ef99115962bf45ee6f2fbe1c5`.

Raw outputs і SHA256 наведені в RECEIPT.json. Абсолютні шляхи в первинних логах описують ізольовану копію на час запуску; файли з тими самими іменами збережені поруч. Повний suite/E2E не повторювався; P06 BLOCKED, TECHNICAL_READY=false, PILOT_ALLOWED=false.
