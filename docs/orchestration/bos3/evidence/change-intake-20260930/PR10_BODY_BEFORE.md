## 2026-09-30: Portable Settings Preserved

Published accepted 19-file portable text bundle in `docs/orchestration/bos3/recovery/codex-settings-20260930/`, manifest SHA256 `253c012e8fcecbd9cfc347427faa6f0681d63a5d8643e20141fda5f7767e4f7d`, independent review `dd7d50c8`. Separate commit `ea699ffa44319a3e02804509855e6039734bb437` follows CRM evidence commit `c7ad513`. Byte copies are unchanged; review and publication metadata are outside the manifest root. This is not a full backup, reinstall test, active configuration install, migration, or product readiness evidence. Existing runtime and execution limits are unchanged.

## 2026-09-30: Reviewed Inactive CRM Source Package

Published `c7ad513e03604283d984bfcc4d9fbd119013f186` after independent source and package review. CRM R2 `fc82733a` closes the stale detail and delayed preview/confirm selection races in source only; rejected R1 and both verdicts are retained under `docs/orchestration/bos3/evidence/crm-stale-source-20260930/`. All 23 archive files match committed raw blobs. Five current records preserve the full S1/S2/S3, UXD01-08 and 11-gate scope. UXD04 proposal accepted with pre-execution refinements, not admission.

No executable frontend/generated assets or immutable dev9 changes. Build, app QA, browser and runtime delivery NOT_RUN; dev9 NOT_DELIVERED, availability UNCONFIRMED; TECHNICAL_READY/PILOT_ALLOWED/MVP remain false. Docs-only checks passed. Full raw archive whitespace check flags preserved CRLF and unified-patch context spaces; accepted bytes were not reformatted. No main merge or production activation.

## 29.09.2026: Current Stage and UXD04 Source Trace

Published documentation-only commit `c9053d6cdb206dbfc28e69dfb52b8d913c5fb119` reconciles the current stage after the owner's instruction to continue the plan. `CURRENT_STAGE_20260929_RU.md` covers S1/S2/S3, UXD01-08, all 11 gates, learning/login, complete D migration and exact-version delivery. Historical E710 evidence and all attempt limits are preserved.

The independent verdict is `ACCEPT_SCOPED_SOURCE_EVIDENCE_AND_CURRENT_RECORDS` (`ec0d3adc6fe3f56c7f7e062e6599ab1e7ffd394b2d751348d8be53d9e8f5151a`). UXD04's actual handoff/preview/confirm/Task/AuditEvent/history path is traced against 17 pinned dev9 source files. No concrete product defect was established. One documentary P2 about sessionStorage identifiers was corrected by its author; original evidence is retained. Thirteen B30-12 manifest Git objects match dev9, but the old template's pending owner exception/E710 pin is not execution admission for dev9.

The installer source archive is already published at `9638dce`; its work is not assigned again. Invoice fixes are already packaged through dev9, not awaiting repack. Product `6b3aab22b3f8254d5f65846f54ceeed7049e1ddf` and immutable candidate `aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975` are unchanged. Dev9 delivery and current runtime availability remain unconfirmed; `TECHNICAL_READY/PILOT_ALLOWED/MVP=false`.

Checks: JSON-as-data and Git/diff/hash checks only; 7/7 copied author/review files match, 13/13 archive Git blobs preserve bytes, `git diff --check` exit 0. New app tests, imports, builds, browser/HTTP, DB/media, lifecycle and probes: `NOT_RUN`, executions 0. Generic CI is not app acceptance. No main merge, no runtime stop/restart, no repeated owner question. The next cross-role evidence step remains gated by a separate valid exact admission.

---

## 29.09.2026: Finished Installer Source, Not Installed

Published commit `9638dce228070cef6384eebe96e3f86be237faf0` completes the source of the existing B30-D-CONTROL-HOME-OPERATION-SOURCE card. The five separate phases are implemented: snapshot, prepare, alias, activate and verify.

Independent critical review: **SOURCE_COMPLETE_STATIC_NOT_TESTED_NOT_INSTALLED**, review SHA-256 `b42bd8e68d0ce31f0abe73a3774092c2bcba285b5344f96b472640dbbeb20256`. NATIVE-FLUSH-1 and OPS-1 through OPS-5 are closed statically. Independent package review: **ACCEPT_INACTIVE_ARCHIVE_ONLY**, SHA-256 `621aa11d309aaf17755be35d1e00bd5de641a8c5770d7f862e871dfda3b66255`.

- Exact installer SHA-256: `c204737e572de6dadf061bbf3d8a29f6a99938b13f78a03f93664d53ae180a9f`.
- Native helper: `743836205bb0f00e592f6c2a6c26a8c242370213cfb16ec3bdd8581fe8d71add`.
- Source manifest: `b1a4bbdfc4e1fd30424d03df9ca77fe902797440ad3ae9a2e63f3090117fd4a8`.
- Inactive archive: `docs/orchestration/bos3/evidence/control-home-installer-source-20260929/`. All 28 frozen source/history copies match scratch and staged blobs. Final commit has 33 archive files and four orchestration documents. Scoped diff check exit 0.
- `SOURCE_COMPLETE=true` only in static source scope. `TESTED=false`, `INSTALLED=false`, `MIGRATED=false`. Imports, compile, help, tests, native probes and installer execution were **NOT_RUN**.
- Historical focused QA remains **FAIL_SETUP, 1/1 spent**, zero completed test bodies, 21 other methods NOT_RUN. C64 and all historical execution gates remain unchanged.
- No working-state copy, config/ACL/alias/anchor switch, runtime delivery, application stop or product readiness change. Dev9 candidate and last runtime receipt are unchanged; current app availability remains UNCONFIRMED. Generic CI is not migration or application QA.

Earlier records below are preserved as history. This publication does not complete the weekly BoS scope or authorize installation.

---

## D Control-Home: Inactive Source And Failed Focused QA

Documentation/archive head: `3e7c33c2b62bad41768e8c6efee57e0f0ff3f84d`. The owner-authorized D control-home transfer is **not installed**. Core and consumer source received independent static review; cleanup and exact child-process isolation were separately reviewed before one bounded synthetic invocation.

- Exact once-only admission `3f47365b`, independent admission review `9b495097`.
- Guard native exit **2**, authority group **1**. First case failed in `setUp` when scratch `mklink` returned a syntax error. Completed test bodies **0**; remaining **12 authority + 9 consumer NOT_RUN**. Scoped attempt **1/1 spent**, no automatic retry.
- Independent raw-result review `05f1d094`: FAIL_SETUP, not a demonstrated product regression. Source-only diagnosis is inconclusive; no corrective source change or replay followed.
- Archive review `8c8ebb8b` accepts inactive publication only. **84/84** copied artifacts matched hashes; two review metadata files are retained separately. Full whitespace check exit1 is preserved for original/raw CRLF/EOF bytes; scoped current docs/metadata check exit0, not an overall PASS.
- Evidence: `docs/orchestration/bos3/evidence/control-home-authority-20260928/`. Source/runner files are inactive and not an alternative execution location.
- Ledger-transition QA, operation phase-fault QA, global quiescence and migration receipts remain open. Any additional fixture diagnostic execution needs a separately valid exact scope; a new ID does not reset1/1. C64 remains independent and unanswered.
- No live control-state/tools/config/scheduler/app change, app delivery, HTTP or browser check. Product `6b3aab22` and immutable dev9 candidate `aa6a4ca4` are unchanged; current runtime availability **UNCONFIRMED**, readiness flags false. Observer send was not attempted while C writes remain frozen; D operational records are not a delivery receipt.

## Current Checkpoint: Dev9 Source Prepared, Recovery Blocked

- Branch/documentation head: `3e7c33c2b62bad41768e8c6efee57e0f0ff3f84d`; sole branch `codex/bos3-prerelease-20260927`.
- Product: `6b3aab22b3f8254d5f65846f54ceeed7049e1ddf`, dev9. Immutable source remains `aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975`, not the later documentation head.
- Exactly one source-only clone and checkout each exited0. D runtime source digest: `e7046ad6e0374d36de33716ffa0152e31330dbf82fab3e24184bf3d573abebe0`. This is not installed-runtime evidence.
- One no-write recovery preflight exited2 before apply; its generic guard discarded the inner system error. An occupied port or server is not established.
- A separately reviewed diagnostic invocation exited1 because Windows execution policy refused to load the PowerShell script before its body. CIM and listener observations were NOT_RUN. No execution-policy change, bypass, inline/encoded/alternate replay, app kill or retry was performed.
- **Owner decision required:** sanctioned script execution and a fresh explicitly bounded diagnostic scope. This alone will not authorize recovery. Preflight1/1, observation1/1, old-window start1/1 remain spent; global problem2/3 unchanged. Recovery apply/start/GET0.
- Current application availability **UNCONFIRMED**. Dev9 is not delivered. Historical dev7 receipt is not current proof; owner instance was last prepared on failed Ddev8/60f.
- Independently accepted source/refusal package32/32 and observation package11/11 preserve raw records and both historical/recent reviews under distinct names. Evidence: `docs/orchestration/bos3/evidence/dev9-source-preflight-20260928/`. Tool-error text is labelled transcription, not a native stderr byte capture.
- Draft/unmerged; main, production, rights, secrets, real data, 85/12 and11gates unchanged.

### Narrow Pointer Correction
`778b364` repairs only the observation-package review SHA256 pointer (63 to64 characters), independently accepted by review `e796343e`. The referenced review bytes and all runtime/cap/readiness facts are unchanged; no evidence or diagnostic reruns.

### Actual Delivery Result
One reviewed window: capture, official stop and apply each native exit0; official D start native exit1. Windows denied `os.replace` of the temporary process receipt into `process.json` at `scripts/bos3_local.py:570`. No automatic repeat, recovery, rollback, post-start QA or root HTML GET was performed.

Apply changed only `prepared.source` and `prepared.source_sha256`. Protected data/media/credentials/progress aggregate matched capture: `dfcbaefab3f5a63e929b49f11d2f5425019834c9bad6e66b0a3e4fd3a938efa1`. This is apply-time preservation, not a later replayed check. Saved failure cleanup reports the identity-verified child was stopped; it is not a fresh liveness measurement. The historical denial/lock holder is unconfirmed.

Independent result verdict: **PARTIAL_WINDOW_FAILED_AT_OFFICIAL_START_NATIVE_EXIT_1**. A separate reviewer accepted the 33 nonsecret artifacts and truthful control record, not delivery. Evidence: `docs/orchestration/bos3/evidence/invoice-delivery-20260928/`. Root integrates only accepted content; copied raw bytes are preserved with scoped attributes.

### Product Changes
Invoice-only currencies now appear in the finance projection without changing formulas, empty EUR fallback, policies or APIs. Integration `c00c60aad0c4f8e70251da3c7174ed105089198b` matches accepted author9f7/evidence906. Existing guarded QA run1/3 on906: 2/2 SimpleTestCase methods, native0, independently accepted; not repeated and not DB/payment/browser/lesson proof.

Dev8 package411 updates version/readmes. Five non-orchestration Git-blob deltas and three retained dev7 references are bound by the passport. Existing UI/PDF were not rebuilt or relabelled as newly tested.

### Current Assignment
Atomic receipt handling is integrated at81ca067 and packaged at6b3aab2. One prior synthetic5/5native0 verifies bounded same-temp replacement error handling only; no repeat. Source preparation and saved-evidence packaging are complete; their workers are released. Sole next recovery dependency is the owner decision above, not an unfinished implementation or permission for ordinary updates.

Sole integrator: `D:/3/BOSDev/workspaces/bos3-canonical/repo`. Preserve shared Git object dependencies and old C work. Documentation publication does not recreate the immutable runtime source or restart the application.

### Historical Evidence And Limits
Dev7 productd346/source d8 had scoped delivery acceptance with **official start native exit UNCONFIRMED_WRAPPER_WAIT**, not five exit0 phases. Its one historical HTML GET200 and unchanged aggregate are not carried forward as current dev8 proof. Old local address `http://127.0.0.1:8030/` is owner-only and is not newly verified here.

Legacy all16 storage relocation remains separately blocked: inventory3/3; last observation719MiB versus chosen2048MiB. The bounded parser-only infrastructure check failed before target parsing and consumed its sole invocation; no repeat or product syntax-failure claim.

No dev8 browser/JS/login/lesson/ERP/CRM-write/progress acceptance. **TECHNICAL_READY/PILOT_ALLOWED/MVP=false**. Fixture3/3 and Node progress exception1/1 remain exhausted. B30-12 exact exception and UXD03 waiting disclosure remain owner decisions; questions are not repeated.

Existing scheduler only. Cutoff **04.10.2026 23:59 Europe/Berlin**; no project changes after it without new owner instruction.


### Inactive Control-Home Core Preparation
`fa192b3507c343336991adb0229d20d2b6db9e98` archives reviewed source-only core and evidence under `docs/orchestration/bos3/evidence/control-home-source-20260928/core/`. One canonical resolver rejects every unestablished nonlegacy home before transport/state/ledger creation. Independent core delta b7186966 and archive/control integration 1020420c accepted scoped static preparation. Original live tools are unchanged; imports/tests/execution/cutover are NOT_RUN. Flow archival integration is separately published at `fdaff796f15fc81dfec3f58d49372a71a7940cf6`, accepted by package review fe28c437 with exact final core binding9beb9790. Wrappers with both static repairs (finally ordering and PowerShell automatic-variable parameter collision) are archived at `2d8ce0910c0cc4fc18572b55d5028707750bd7b2`, final static review99d43fb7 and independent archive review6b679619. No live wrapper was replaced or executed. Channel test API adaptation is independently accepted as inactive source and archived at `00607be24a608e481efa4437408e7b338fcafe93`, not run. Product/runtime pins and the owner diagnostic decision remain unchanged.


### Task Model Routing
`86334504ff6d56f2a8442141b3d2a36b435ebb89` applies exactly the independently accepted nine-file candidate-v2 configuration (manifest954f2887, reviewcce0be6a), after all current source hashes matched. Default new subagent Sol/medium, bounded review Sol/high, small preparation Luna/medium; architect/full-readiness auditor remain Astra/high; concurrency cap3. Root model, active task settings, sandbox/instructions/permissions and attempt gates unchanged. Nine applied working-file SHA256s match the accepted bytes. No Codex restart, app/helper/test execution or measured savings claim. Requested configuration is not observed runtime model evidence.

Source-only test review found a public target guard ordering P1. The same author completed one continuation after fresh native availability, preserving its partial work; no reset credit or duplicate worker. Exact public API repair371a02a4 was independently accepted static by Sol/high reviewer6ab166a6 and archived at e7b3fbf. CLI send ordering remains outside this acceptance. The separate Sol/medium test-source rebind is complete. Independent Sol/high review0710a5ab closed the missing exception-name P1 and accepted exact test source3cdcbd99 for a subsequent execution gate. No test was run. All helper candidates remain inactive; the immutable runtime candidate is unchanged.

Configuration manifest, independent review and exact applied receipt are retained under `docs/orchestration/bos3/evidence/model-routing-20260928/` at e902e4c; deterministic copies matched, unchanged reviews were not repeated.


### Final Inactive Test-Source Archive
`00607be24a608e481efa4437408e7b338fcafe93` retains the exact accepted test source, manifest/report, original draft and all three reviews under `evidence/control-home-source-20260928/channel-test/`. Ten copied artifacts matched byte hashes. Public outside/self/nonlegacy refusal assertions remain, including no AppTools construction. Full staged whitespace check reported only the original review's Markdown hard-break spaces; those accepted bytes were preserved, and other staged paths passed. No helper/test/import/AST/parser/compile/transport/runtime execution, live tool replacement or state/ledger migration occurred. All source-only workers are released. Static preparation is complete only within each card's pins; previous flow/wrapper acceptance is not automatically extended to later public-guard bytes. Separate exact-pin execution admission, caller compatibility, authoritative state and cutover remain open. Root retains the existing C64 owner dependency without repeating the question or diagnostic.


## Уточнення обсягу 30.09: d4715a0

Незалежно прийняті поточні документи виключають скасоване власником повне перенесення даних на D з умов продукту. Перенесення не позначено виконаним чи PASS; S1/S2/S3, UXD01-08, 11 gates, навчання, персональний вхід, exact-version доставка та всі історичні ліміти збережені.

- Документальний review: `ACCEPT_SCOPED_CURRENT_SCOPE_CORRECTION`, SHA256 `786d387561a35e7b34655807faf1194cdf558ef08bd0bde43490891096fb9dc7`.
- Exact вхід, raw diff і verdict збережені в `docs/orchestration/bos3/evidence/scope-clarification-20260930/`; усі 4 архівні blobs збігаються з вихідними байтами.
- Перевірка diff поточних документів та метаданих: exit 0. Перевірка разом із незмінним raw patch: exit 2, лише 10 порожніх context-рядків unified diff; raw evidence не переформатовано.
- Product/runtime не змінено, нових app/QA/build/browser запусків 0. `TECHNICAL_READY=false`, `PILOT_ALLOWED=false`, `MVP=false`; це не runtime-доставка.

