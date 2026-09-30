# B30 control home: public target preflight source repair

Статус: `INACTIVE_SOURCE_ONLY_STATIC_REVIEW_REQUIRED`. Это continuation той же
`TARGET_GUARD_CARD`, не новая attempt или runtime action. Использован
сохранённый staged partial SHA `371a02...`; он сверён до report/manifest и не
перезаписывался.

## Narrow delta

Новая private `require_delivery_target(target)` сохраняет exact designated
target allowlist и self-message refusal. Public
`deliver(target, prompt, message_id, home=...)` сначала вызывает accepted
`resolve_control_home(home)`, затем `require_delivery_target(target)`, и только
после обоих checks может construct `AppTools`. Поэтому unsupported/self target
не запускает public transport constructor; nonlegacy home по-прежнему
refuses first, before target, state, ledger or transport.

`_deliver_resolved` retains the same target guard as internal defense. Message
ID/prompt validation, model preflight, fixed `hostId`, ledger-local duplicate
suppression, SENDING/UNCONFIRMED/ACKNOWLEDGED transitions and receipt behavior
are unchanged.

## Boundary

The prior core archive and consumers of its `3f1...` bytes are not
automatically accepted for this proposed revision. This package does not run
tests, import helpers, construct AppTools, read state/ledger, or make any
runtime/readiness/cutover claim. Independent source review must precede a
separate channel-test dependency rebind.
