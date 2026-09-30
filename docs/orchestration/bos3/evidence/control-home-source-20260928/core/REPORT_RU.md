# B30 D control home: core source-only preparation

Статус: `INACTIVE_SOURCE_ONLY_STATIC_REVIEW_REQUIRED`. Изменены только staged
copies `bos_dev.py` and `codex_channel.py` plus static artifacts in this
scratch. Original C tools, canonical source, live control state, ledger,
config, queue, observer, locks and transport were not read, executed or
changed.

## Resolver and authority boundary

`bos_dev.resolve_control_home(value=None)` is the sole canonical-home API.
The only legacy authority is the fixed canonical path
`C:/Users/user/AppData/Local/BOSDev`; it is not derived from `LOCALAPPDATA`.
Equivalent legacy input resolves to that exact `Path`. Any other selectable
home raises `ControlHomeError` before a state path, directory creation or lock.

The refusal is intentional: C64V2 provides no separately authorised schema or
marker for establishing a coherent nonlegacy config/queue/observer/ledger/lock
state set. This code neither creates such a marker nor treats a missing home,
empty delivery ledger, delivery fallback, config, observer, queue or lock as
authority.

## Propagation

`run`, `initialize` and public `state_lock` resolve their direct input before
state mutation or locking; canonical `Path` values pass through unchanged.
Channel `deliver` resolves before constructing its ledger path or entering a
lock. CLI `--home` resolves/refuses before `AppTools` startup whenever supplied
or required for `status`/`send`; `status` reads observer under that resolved
home and `send` passes the same Path to `deliver`. Existing Codex App Tools
transport and selected-ledger idempotency are otherwise unchanged.

`INTERFACE.json` was published to separate flow owner before this implementation
was frozen. It requires future `bos_flow` work to resolve once before its first
control-state path/lock and pass the exact Path onward. Flow integration remains
outside this card.

## Direct channel API repair

Initial static review `13f9595d` found that former public
`deliver(client, ...)` could receive a transport already created by an external
caller. The public API is now `deliver(target, prompt, message_id, home=...)`:
it resolves/refuses selected home before constructing `AppTools`. The former
client-accepting body is private `_deliver_resolved` and is used by CLI only
after CLI has already resolved home before its one client startup.

This is an intentional source compatibility boundary. It cannot stop an
unrelated external caller that has already constructed its own `AppTools`; such
callers must migrate under a separate exact review scope and must not call the
private helper. This card does not claim to govern them. The updated interface
was sent to the separate flow owner so its accepted dependency pins can rebind.

## Verification boundary

No import, `--help`, execution, compile/AST, test, state read, send or runtime
action occurred. Dynamic authority establishment, flow integration, a complete
cutover and all tests remain open for separate cards and independent review.
