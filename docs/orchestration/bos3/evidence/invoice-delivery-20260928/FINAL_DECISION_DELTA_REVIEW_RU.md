# Незалежний review decision-delta: B30-INVOICE-DEV8-D-DELIVERY

Дата: 2026-09-28  
Режим: статичне читання. Жодних lifecycle, runtime, Git, HTTP, parser/import,
тестових або source actions не виконувалось.

## Перевірені bytes

* `ROOT_DELIVERY_DECISION.json` —
  `c31171c399d8f6e5a60a00201a120fbe10bf21a730d3721bd951cae9e5aefdde`;
* current pending maintenance template —
  `219790cbc2eb59cea3a71e16b8ec56a1837d4c1234b8bb27094938b4df8f1bc1`;
* current pending lifecycle template —
  `059d7aa2dc2ea79075f11d6d56e9458c37d5c992eb763bf369baeb12cb71fe07`;
* unchanged post-start template —
  `f6910e49467ff04fb9de7e0cf3a293927c4af741b60c50f27e392133b0e24fff`.

## Closure P1

Обраний варіант 1 реалізовано коректно. У поточних executable templates
`ROOT_TECHNICAL_GO` і `$ExpectedRootTechnicalGo` знову мають
`PENDING_ROOT_FINAL_DECISION`, тому `require_final_pins()` / `Require-FinalPins`
відмовляють до filesystem, Git, process або data access. Це закриває попереднє
передчасне відкриття gate зарезервованим token.

`ROOT_DELIVERY_DECISION.json` фіксує один token, candidate `60f1e31fca6056711ea52d7aade6b65e0b14afff`, product/manifest/allowlist,
fixed C/D/owner paths, archive
`maintenance-INVOICE-DEV8-D-20260928-window1`, exact five phase limits,
заборони та failure rule. Воно також фіксує єдиний post-review edit: замінити
лише два PENDING GO constants на цей id, і очікувані exact script SHA:

* maintenance `dced1900a50e1830f7ba147052c7e69e6f53dddc4a223a82bf8bead332897720`;
* lifecycle `420502cc6a41d4be439d42371ccc57235777237022d18e6c82a49178f464da41`;
* post-start `f6910e49467ff04fb9de7e0cf3a293927c4af741b60c50f27e392133b0e24fff`.

Це саме hashes раніше перевіреного pin-only fill; інші поведінкові зміни не
дозволені. Root зобов'язаний перевірити decision, цей review і всі actual
script hashes перед кожною phase. Provenance addendum явно зберігає limitation
оригінального JSONL lock, не перетворюючи її на доказ delivery/runtime.

## Verdict

`ACCEPT_SCOPED_HASH_BOUND_ROOT_DECISION_DELTA`.

Після exact two-constant fill, який дає рівно перелічені hashes, admissible
лише описане одноразове owner-local window: capture -> accepted official stop
native exit 0 -> accepted apply -> accepted official start -> окремий QA
post-start one GET -> незалежний result review. Це процедурне admission
приймання, не результат delivery: readiness лишається false, а будь-яка
інша зміна bytes, timeout/unknown exit або failure зупиняє послідовність без
retry, rollback чи recovery.
