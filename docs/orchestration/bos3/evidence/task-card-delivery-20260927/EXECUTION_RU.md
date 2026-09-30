# B30-UXD03-DELIVERY: exact ordinary local update

Root is the sole executor. Prepared 2026-09-27, before the 2026-10-04 cutoff.
Classification: NEW_REVIEWED_CANDIDATE_ORDINARY_LOCAL_UPDATE_UNDER_STANDING_OWNER_POLICY.
Owner policy: ordinary independently reviewed updates are authorized; this is
not a repeated dev3 entry window or a new lesson/fixture exception.

From installed e710eb568717dfe3ede945feb899f030bd5ad1ab (dev4), to immutable
3d1eabe3b8f54ebc6c6d6bf0241beba219d1fc3c (dev5).
Manifest: docs/orchestration/bos3/TASK_CARD_DEV5_CANDIDATE.json;
SHA-256 5d7e4dd7d77fa09f66677bc8c1e4b372b4a2d2fac8f5fe46051223f3d1ca60ad.

One capture, one official stop, one apply, one official start, one post-start
HTML verification. The official start retains its existing bounded CSRF
readiness polling; the distinct post-start verifier makes exactly one GET /.
No browser, login, lessons, API business mutations, init/seed/migrate/reset,
access change, external exposure or automatic retry. Database, media, access
and progress preserved and aggregate checked against a fresh capture.

Runtime source: C:/Users/user/.codex/worktrees/bos3-local-runtime/repo.
Instance: D:/3/BOSDev/local-bos3/owner. Python: D:/3/BOSDev/venv/Scripts/python.exe.
Official lifecycle: scripts/bos3_local.py stop/start --source SOURCE --root ROOT.
New archive: maintenance-B30-UXD03-DELIVERY-3d1eabe.
Capture/apply arguments use exact source, root, baseline and target above.
All stdout/stderr/native exit codes retained in run1; no secrets copied.

Final pin-delta review by start_overview_review is mandatory before execution.
At preparation: executions 0, installed runtime remains dev4. Keep runtime
running after successful delivery. A failed step stops this one-shot sequence;
record actual state and do not retry or roll back without applicable authority.
