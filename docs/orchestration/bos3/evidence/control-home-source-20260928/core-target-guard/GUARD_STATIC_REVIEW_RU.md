# B30-D-CONTROL-HOME-PUBLIC-TARGET-GUARD: independent static review

Reviewer: `/root/bos3_guard_review_sol`. Routing requested `gpt-6-sol/high`; observed runtime model is unconfirmed. The frozen author manifest's planned reviewer field is provenance, not this reviewer's identity.

## Verdict

`ACCEPT_STATIC_SOURCE_DELTA_FOR_SCOPED_TEST_REBIND`. The inactive proposed source fixes the stated public `deliver` ordering defect. This is static acceptance of the exact source bytes, not test acceptance, runtime activation, cutover, or product readiness.

## Evidence and findings

- Old `core/staged/codex_channel.py` SHA-256: `3f1c4318a3693a47b088ca75742decbce84dda18942f97f039d424d392108a55`.
- Proposed `core-target-guard/staged/codex_channel.py` SHA-256: `371a02a413477de65186adcb53cfdf7d99c428b1c4dea81eef77494fe76f9235`.
- Frozen `staged/bos_dev.py` SHA-256: `9953e621190dbf70b65955afee473f46969347a292cd2bf63f929bcf3e3d7c53`. `core/INTERFACE.json`: `9537061eca16d000b2632bc4a1ab235ae527c9f0cd56edb6d812f32889f91497`.
- Author manifest SHA-256: `af147a25e2d88388602f99b442c6be8883729252d216ca7ff1d6b82faa20f26b`; author report: `5bce9c9b6354b8e6c771a794337347a319b005d26222cbe7aab33ca7f727a46f`. Prior channel-test review: `0ed0aaf9edd57e710bedd362aa33089c1a60f1add04f813d67c77a0f97de096b`.
- Exact source diff only extracts the six designated-target and caller-self checks into `require_delivery_target` (lines 220-224), invokes it from `_deliver_resolved` (line 229), and adds its public call after `resolve_control_home` and before `with AppTools()` (lines 275-280). There is no changed send payload, host, prompt/message-ID validation, model preflight, ledger transition, duplicate suppression, or receipt code in this delta.
- The frozen resolver refuses a nonlegacy home (bos_dev.py lines 46-57). In the public path, this refusal precedes the target guard and AppTools construction. The target guard precedes AppTools construction for outside and self targets. The private path retains the same defense after client creation.
- No new source finding in this narrow diff. A separate CLI `main()` send path still creates `AppTools` before `_deliver_resolved`; the card expressly scopes the public `deliver` API and excludes a CLI rewrite. CLI self-target constructor ordering is therefore outside this acceptance and must not be inferred fixed.

## Limits and next step

No imports, helper execution, parser/AST/compile, tests, AppTools, network, process, database, runtime, or live state/ledger/config/queue/policy operations were performed. `executions=0`. The prior test source and any consumer bound to the old `3f1...` bytes are not accepted for the new source by this review. Next permitted step is a separate scoped channel-test rebind to `371a...` with a constructor-not-called assertion for outside/self targets, followed by its independent review. Historical limits and owner gates remain unchanged.
