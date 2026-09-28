# B30-INVOICE-DEV8 runtime source preparation: result review

Дата: 2026-09-28

## Проверенный scope

Проверены только saved `PREBIND.json`, `SOURCE_RECEIPT.json`, clone/checkout native-result JSON и их raw outputs. Новые Git commands, clone/checkout, test, runtime, delivery и filesystem action не выполнялись.

## Подтверждённое

- Repaired prebind attempt `2` записан как `PASS_METADATA_PREBIND_ONLY`; prior attempt1 failure сохранён. Baseline path/blob/raw text/SHA соответствует принятой repair квитанции. До clone counters были zero.
- Clone был ровно один, `--shared --no-checkout`, native exit `0`; checkout был ровно один, `--detach 60f1e31fca6056711ea52d7aade6b65e0b14afff`, native exit `0`. Их saved stdout/stderr SHA-256 совпадают с declared result JSON.
- Saved receipt `A3240982628B5C17528A9BEF250E34A0858F942E34286AACB77DCB1FD6D63C86` фиксирует detached HEAD `60f1…`, expected `symbolic-ref` exit `1`, clean porcelain, exact D source-local remote, ordinary recorded components, empty hooks/attributes controls, unchanged pre/post alternates and dependency chain только в D.
- Все five invoice candidate files в receipt имеют declared Git blob SHA-256/bytes и `matches_git_blob_manifest=true`; saved metadata raw output hashes также совпадают с receipt.
- `runtime_actions=0`, `C_writes=0`, `protected_data_writes=0`; source checkout не выдан за standalone backup или runtime delivery.

## Finding

### P1: отсутствует доказательство process-level `GIT_ATTR_NOSYSTEM=1`

Approved `SOURCE_PREPARATION_PLAN.json` включает `GIT_ATTR_NOSYSTEM=1` в exact Git controls. Однако `CLONE_NATIVE_RESULT.json`, `CHECKOUT_NATIVE_RESULT.json` и `SOURCE_RECEIPT.json` перечисляют Git `-c` controls, но не сохраняют process environment или отдельную raw квитанцию для этой переменной. Поэтому нельзя подтвердить, что этот контроль применился именно к уже выполненным clone/checkout; `core.attributesFile` не заменяет evidence требуемой environment binding.

Не выполнять повторный clone/checkout: оба maxima уже израсходованы. Допустима только documentary provenance correction из уже существующего raw process/runner evidence, если такая неизменяемая квитанция существует; иначе оставить source preparation control status unconfirmed и не использовать checkout для runtime/delivery admission.

## Verdict

`REVISE_SOURCE_RECEIPT_ENVIRONMENT_PROVENANCE_NO_RERUN`.

Фактический source-only checkout существует с проверенными ограниченными receipts, но его нельзя принять как полностью conforming approved source preparation до закрытия P1 без повторного Git действия. Это не runtime GO, delivery acceptance или readiness verdict.
