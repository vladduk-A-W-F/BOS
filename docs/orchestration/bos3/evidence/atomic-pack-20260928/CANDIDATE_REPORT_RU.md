# B30-ATOMIC-DEV9-PASSPORT · кандидат dev.9

## Ідентичність кандидата

Паспорт описує інтегрований product commit
`6b3aab22b3f8254d5f65846f54ceeed7049e1ddf` та його tree
`e8e6257d8120cb5960697787d2300733a46c766a`. Базова підготовлена версія,
для якої delivery dev.8 завершився невдачею, —
`60f1e31fca6056711ea52d7aade6b65e0b14afff`; вона досі є підготовленим
джерелом D runtime.

`ATOMIC_DEV9_CANDIDATE.json` фіксує рівно п’ять неоркестраційних Git blob
змін від цієї бази: три metadata-файли та `scripts/bos3_local.py` разом з
його ізольованим тестом. SHA-256 і byte counts обчислені по Git blob bytes,
а не по checkout-файлах чи нормалізованих CRLF.

## Збережені докази й межі

Вказано історичний invoice-only currency QA з його первинними source/test /
harness pins та точним обсягом доказу. Він не запускався повторно.

Окремо вказано прийнятий synthetic atomic receipt QA: один виклик, native
exit `0`, п’ять методів `OK` за `0.447 s`, source/test pins і SHA raw receipt
/ stderr. Це доводить тільки injected-error поведінку bounded atomic
replacement; не доводить реальний Windows lock, lifecycle, delivery або
живу runtime. Консервативний облік проблеми лишається `2/3`; failed official
start window лишається `1/1`.

Три dev.7 assets збережено без змін і без повторного build/PDF/browser QA.
PDF є наявною guide-пам’яткою, а не свідченням dev.9, delivery чи runtime.

## Стан

Delivery має статус `PENDING_AND_UNCONFIRMED`; готовність не змінюється:
`TECHNICAL_READY=false`, `PILOT_ALLOWED=false`, `MVP=false`. Цей паспорт не
проводить тестів, build, import, PDF generation, runtime, мережевих чи
канонічних операцій. Він передається незалежному reviewer, потім root;
самоприймання відсутнє.
