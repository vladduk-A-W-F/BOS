# B30-D-CONTROL-HOME-CHANNEL-TEST-SOURCE: final static review

Reviewer: `/root/bos3_guard_review_sol` (requested `gpt-6-sol/high`; observed runtime model unconfirmed). Static source inspection only; `executions=0`.

## Verdict

`REVISE_BEFORE_STATIC_TEST_SOURCE_ACCEPTANCE`. The focused outside/self transport-constructor repair is present, but the separate nonlegacy test refers to an exception name absent from the staged channel module. This is a source-level failure in a required refusal case, so the test package is not accepted as a whole.

## Exact pins and preserved coverage

- Final test `staged/test-codex-channel.py`: SHA-256 `77c37be60b2a71c71c245f75fbfeb6b23e537eafe56cdb2d904c56d18efb7e92`; initial draft `history/INITIAL_TEST_SOURCE.py`: `c1b6f8ddc695dad2b56f27ad1540e89791793f8b95e97d546f83558a2f91809c`.
- Final manifest: `275c8a20f0ec218d68b096284525027a6e9779d5e1872192f793b40106349271`; author report: `0366cb326248b5d4c12cfea1b500bca7e67036078ee85db7187de2bffb730094`; initial independent test review: `0ed0aaf9edd57e710bedd362aa33089c1a60f1add04f813d67c77a0f97de096b`.
- Bound channel `../core-target-guard/staged/codex_channel.py`: `371a02a413477de65186adcb53cfdf7d99c428b1c4dea81eef77494fe76f9235`; frozen provider `bos_dev.py`: `9953e621190dbf70b65955afee473f46969347a292cd2bf63f929bcf3e3d7c53`; independent guard review: `6ab166a62c57ffaf7ca8a0092402451b795a8dfe35bfa13685d4a820771ac203`.
- The exact draft-to-final diff changes only the sibling staged import path and the outside/self case. The new case calls public `deliver(..., channel.HOME_DIR)` without patching `resolve_control_home`, mocks `AppTools`, and asserts the constructor was not called for an outside target and each designated self target. The legacy home constant hits the resolver's Path-equality return; no home file read is required by that branch.
- Synthetic ledger cases still patch resolver, lock, and constructor, with a temporary ledger path and context-manager `FakeClient`. Duplicate ID, changed content, repeated content under a new ID, exact target/`hostId`/prompt, UNCONFIRMED no-resend, and designated routing assertions remain. The protocol-EOF case is textually unchanged from the original source. These are source observations, not executed results.

## Blocking finding

**P1, `staged/test-codex-channel.py:133`:** `with self.assertRaises(channel.ControlHomeError)` evaluates `channel.ControlHomeError` before entering the context. The pinned channel imports `LEGACY_CONTROL_HOME`, `atomic_json`, `read_json`, `resolve_control_home`, and `state_lock` from `bos_dev` (channel line 21), but does not import or define `ControlHomeError`. Consequently, this test would raise `AttributeError` at the assertion expression rather than call public `deliver` and verify the nonlegacy-home refusal. This defect predates the focused draft-to-final diff, but it blocks acceptance of the required nonlegacy case. Import the exception explicitly into the test from the staged `bos_dev` module and assert that type; keep the real resolver and `AppTools.assert_not_called()`.

## Boundary

No test, import, helper, parser/AST/compile, AppTools, process, network, database, live state/ledger/home/lock, or policy action ran. No exit code or dynamic PASS exists. The exact revised test needs another static review after the narrow exception-reference repair; only then can an authorized synthetic execution gate be considered. This review does not change the archived guard, canonical product, runtime, authority, or owner gates.
