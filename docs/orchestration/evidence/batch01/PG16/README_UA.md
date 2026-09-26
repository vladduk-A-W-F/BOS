# PG16 · первинні докази

ZIP — точні bytes GitHub artifact10603616377 run35503944302 attempt1. SHA256 `542a3c5975a0a4e1533f0f744bf3ad57e2f0f111afe232f04fb4efaf28185247`, 28579 bytes. Усередині23 entries, з них22 indexed files + sha256-index.json. Індекс адресує шляхи від кореня ZIP, не файли поруч із цим README. Report та індекс додатково винесені поруч для читання; raw stdout/stderr є в ZIP. Job log та metadata отримані незалежно через GitHub connector.
Root і незалежний reviewer перевірили SHA/size, усі indexed bytes, counts/exits, test_database proofs, source canaries та candidate/source. Успішний upload сам по собі не був підставою приймання.
Первісне пряме завантаження signed URL повернуло HTTP403; exact connector file_id успішно матеріалізовано штатним механізмом. Тести не повторювалися. Raw logs містять лише синтетичні fixtures; жодних робочих БД/ключів немає.
26 green methods у PG-stage =16 реальних business/HTTP methods +10 fake-connection guard regressions. Додатково7 artifact/source unit і3 очікувані baseline red methods. Це не full suite, actual E2E, Windows або production readiness.
Docs-only commit b6332434 породив run35504337653: scope PASS, targeted SKIPPED; повторного PG не було.
