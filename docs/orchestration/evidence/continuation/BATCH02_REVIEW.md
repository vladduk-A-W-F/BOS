# BATCH02 independent CI evidence audit

Verdict: PASS_SCOPED for integrity and provenance of the existing BATCH02 PostgreSQL evidence. This audit performed no application test rerun, external write, PR comment, merge, or original database access.

## Live candidate and CI
- Observed PR1: open, draft, not merged. Title: BoS: GPT/Codex orchestration, order sources, scoped confirmations and landing delivery.
- PR: https://github.com/vladduk-A-W-F/BOS/pull/1
- Current head: setup/bos-gpt-orchestration-20260920 @ 82beca6c14e097a31200068d72b15334c5bed319.
- Base: fix/p10-002-task-sequence-20260919 @ 7d46dced3bcf06d44755cf53366c9e16bd465582.
- Workflow run: https://github.com/vladduk-A-W-F/BOS/actions/runs/35507888776; attempt 1; completed/success; exact CI commit 8060075455206257d6283c70906facca98f0bc1a.
- Live targeted job 106070687194 completed successfully. Its log shows checkout and BOS_BATCH_CANDIDATE_SHA at the exact CI commit, real postgres:16 service initialization, and artifact upload SHA/size/ID.
- Live compare from CI commit to current head: ahead 3, behind 0, 22 changed paths; every change is docs/orchestration documentation or evidence. scripts/verify.py source_digest includes only named runtime roots, selected root extensions, docs/KNOWLEDGE_UA.md and docs/PARAMETERS_UA.md. All 22 changes are excluded. Runtime source identity therefore carries forward to the current head; this is not a claim that current head was itself tested.

## Artifact and byte verification
- Exact-head tracked archive: docs/orchestration/evidence/batch02/PG16/BoS_BATCH02_PG16_35507888776.zip.
- Git blob SHA1: 6a8f2654c83d2bec0adfe9801ed829395bd417b4, independently recomputed with Git blob header.
- Archive bytes: 11719. Independently computed SHA256: 4908b2ad522fde391d254061a41560fd8e3336c692d3ad5f6819eff7fe97b6ec.
- Live Actions artifact 10604821829, bos-batch02-targeted-35507888776-1, not expired, has exactly that digest and size and CI head. Job upload log independently repeats the same artifact hash, bytes, and ID.
- All 8 indexed raw files match both their recorded SHA256 and byte count. ZIP contains these 8 files plus sha256-index.json. The separately tracked report.json and sha256-index.json at current head byte-match ZIP members.
- Full member results: member-verification.json. Live metadata: live-metadata.json. Live log excerpt: targeted-job-excerpt.log.

## Runtime and harness mapping
- CI runtime source SHA256: ce495b29214f21a80b8efd5bf41f6f219b5cb182b0453a7c43dac8899bc06ed5. Report source_before and both stages agree. Source unchanged after run is true.
- Exact-CI batch_02_targeted.py freezes that candidate digest and verifies actual source_digest before starting tests; a mismatch raises a failure.
- Harness SHA256 recomputed from exact-CI Git bytes: 12aa5083f8ba4baea625617c55555b265d3f07e164f9b03613c4f92dcd0a8371; equals report.
- Reused batch_01_targeted.py helper SHA256 recomputed: 30046f9c933b7a0fefc8e1813e07ca2fbea782bb6ebba9974d74a8dd59a13cfb; equals report.
- Python 3.12.14; reported Django 6.0.5, DRF 3.17.1, psycopg 3.3.6; PostgreSQL server_version_num 160015.
- This audit attests the CI comparator/source mapping. Independent native Windows source_digest reconstruction is owned by parent and is not claimed here.

## Raw PostgreSQL results
- postgres-order-trace: 18 distinct raw method lines ending ok; Ran 18 tests; OK; exit 0; no skips/expected failures/unexpected successes.
- postgres-adjust-dependencies: 24 distinct raw method lines ending ok (21 proposal methods plus 3 real concurrency methods); Ran 24 tests; OK; exit 0; no skips/expected failures/unexpected successes.
- Both stdout logs identify vendor postgresql, version_num 160015 and the issued test_bos_verify_<hex> database; these are distinct from the synthetic source databases.
- Both synthetic source canary before/after structures byte-equate as JSON. This proves preservation of the scoped synthetic canary DB snapshots only, not a scan of any original user database.
- The helper evaluates exact method counts, OK, exit 0, correct vendor/version/test DB name and unchanged source canary; it rejects skips and infrastructure timeouts.

## Three real mutex waits
- independent: A192/B193, monitor191; observer reports B193 blocked by A192 with wait_event_type Lock; statuses 200/200; two distinct effects.
- same resource: A202/B203, monitor194; observer reports B203 blocked by A202 with Lock; statuses 200/409; second proposal has no receipt; one effect.
- replay: A205/B206, monitor204; observer reports B206 blocked by A205 with Lock; statuses 200/200; same ERP event id16 and same response; one effect.
- In all cases the raw trace orders A mutex acquired < B mutex attempt < observer blocking proven < B mutex acquired; all three backend PID values are distinct.
- Inspected exact-CI test source calls real execute once through execute_wrapper, reads pg_blocking_pids via monitor connection, asserts both DB worker connections and PG16, and checks Movement/Event counts and quantities. These are not fake-connection tests.
- Machine-readable raw analysis: raw-proof-analysis.json. Exact-CI source retained as test_adjustment_proposals.py, batch_02_targeted.py, batch_01_targeted.py and verify.py.

## Scope and remaining limits
- Accepted: integrity/provenance of existing bounded PG16 BATCH02 evidence, 42 methods, runtime source identity from CI to current head, and three actual lock waits.
- Not newly performed: Windows application smoke, native Windows source digest, SQLite 39-method run, JSX 18 checks, browser acceptance, full suite, E2E, P06 timeout diagnosis, Windows gate11, installation/upgrade/rollback, or independent re-review of all product changes.
- The source digest is the repository-defined runtime digest, not a hash of every Git path or all environment dependencies.
- P06 remains BLOCKED; TECHNICAL_READY=false; PILOT_ALLOWED=false; historical P05 full-run count remains 3/3. No retry/reset was performed.
- Read AGENTS.md at exact current head; matches local audit copy. Read-only task respects the targeted/full-run distinction.

Observed at 2026-09-20T11:58:03.202Z.
