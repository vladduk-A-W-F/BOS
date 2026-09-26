# PLAN-F06 · scoped інтеграція

Детальні e2e-report.json зберігаються у output/e2e-{backend}; перевіряються path/schema/backend/digest/completeness. 5/5 artifact-fixture unit tests, exit 0, 8 негативних підсценаріїв для кожного backend. Actual E2E/CI archive не запускались; це не їх PASS. GATES/SUITES/EXTENSIONS незмінні. Незалежний reviewer ACCEPT_SCOPED.

Runtime SHA256: `5b9894d1be6c1a79df8895af902a97b94756f018e8ac8116a2c09536d978f38a`.

Raw outputs і SHA256 наведені в RECEIPT.json. Абсолютні шляхи в первинних логах описують ізольовану копію на час запуску; файли з тими самими іменами збережені поруч. Повний suite/E2E не повторювався; P06 BLOCKED, TECHNICAL_READY=false, PILOT_ALLOWED=false.
