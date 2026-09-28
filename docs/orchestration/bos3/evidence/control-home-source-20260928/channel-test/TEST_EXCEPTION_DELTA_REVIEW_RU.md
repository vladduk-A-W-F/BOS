# B30-D-CONTROL-HOME-CHANNEL-TEST-SOURCE: exception delta review

Reviewer: `/root/bos3_guard_review_sol`. Requested review profile `gpt-6-sol/high`; observed runtime model `UNCONFIRMED`. This is a focused static closure review of the prior P1 finding, not a test execution.

## Verdict

`ACCEPT_STATIC_TEST_SOURCE_FOR_SUBSEQUENT_EXECUTION_GATE` for the exact inactive source SHA-256 `3cdcbd99aaa2133f6283c73b51bc80fcc1add3b9a992c3fa83e567931a25b1b1`. The previous undefined `channel.ControlHomeError` assertion is repaired. No dynamic PASS, runtime activation, or cutover is inferred.

## Evidence

- Updated test `staged/test-codex-channel.py`: `3cdcbd99aaa2133f6283c73b51bc80fcc1add3b9a992c3fa83e567931a25b1b1`; manifest: `c63daf5c9923a03789b938e724a7310ae957502848db6f185986f2568b725327`; author report: `5a271e14d44b42cc7a4d54832e561520f6a60c5aeecf4d8398abe5f11d9f0c64`. Hashes were computed from the current files.
- Previous focused review: `a8db7ea5c6e2074b2a27decfd54008268ddd8b6b251feb21e7439e8888ad6ebb`; prior focused test pin: `77c37be60b2a71c71c245f75fbfeb6b23e537eafe56cdb2d904c56d18efb7e92` (from preserved review/manifest). Initial draft: `c1b6f8ddc695dad2b56f27ad1540e89791793f8b95e97d546f83558a2f91809c`.
- The test's `CORE_STAGED` points to sibling `core-target-guard/staged` (line 11), is placed on `sys.path` before imports (line 12), and imports `ControlHomeError` directly from `bos_dev` (line 14). The pinned sibling `bos_dev.py` declares that class at line 33. `codex_channel.py` imports its resolver from that same top-level `bos_dev` module. These source references close the missing-name finding without changing product code.
- In `test_nonlegacy_home_is_refused_before_transport`, lines 133-136 now assert `ControlHomeError` around public `channel.deliver(..., self.home)` and retain `transport.assert_not_called()`. This refusal case does not patch `resolve_control_home`; `self.home` is the synthetic temporary path. The outside/self case still calls public `deliver(..., channel.HOME_DIR)` with the real resolver and asserts `AppTools` was not constructed (lines 95-108).
- The diff against the preserved initial draft shows the staged import rebinding, the outside/self constructor assertions, and this exception reference. Prior independent reviews covered the unchanged test behavior; this closure review found no new issue in the exception repair.
- Dependency pins recomputed: channel `371a02a413477de65186adcb53cfdf7d99c428b1c4dea81eef77494fe76f9235`; provider `9953e621190dbf70b65955afee473f46969347a292cd2bf63f929bcf3e3d7c53`.

## Limits

No import, helper, test, parser/AST/compile, `--help`, AppTools, process, network, database, live home/state/ledger/lock, or runtime operation ran. `executions=0`; exit codes and dynamic results are absent. Any later synthetic execution requires its separate authorization and exact dependency pins. Historical limits and owner gates remain unchanged.
