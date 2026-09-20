# PLAN-N1-SHIP · scoped інтеграція

ship додано до наявної metadata-валідації Movement: raw100 і бізнес-правило stripped60, без обрізання. Red: 24 failures; green: 2/2 методи, 27 позитивних комбінацій + 36 відмов, service/2 preview/stored confirm/replay. PG16 ще не перевірено. Незалежний reviewer ACCEPT_SCOPED.

Runtime SHA256: `b9722ed16722cee83de6d7b30d9cac7077488237bd5f3020c60709e851ab859d`.

Raw outputs і SHA256 наведені в RECEIPT.json. Абсолютні шляхи в первинних логах описують ізольовану копію на час запуску; файли з тими самими іменами збережені поруч. Повний suite/E2E не повторювався; P06 BLOCKED, TECHNICAL_READY=false, PILOT_ALLOWED=false.
