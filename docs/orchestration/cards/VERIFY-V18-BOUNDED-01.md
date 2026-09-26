# VERIFY-V18-BOUNDED-01

Owner request: check commit/merge integrity and code after naming and documenting the v18 intermediate baseline. This is a bounded verification card, not a new identity for an exhausted full suite.

## Scope

QA may prepare helpers and raw outputs only in an isolated evidence/v18-20260926 directory. Root is the sole writer of the canonical checkout and integrates the reviewed evidence. The final static audit runs after root signals FINAL_RECORDS_READY and records file identity before and after execution.

- Git fsck (read-only), source/ref ancestry, main/tag equality and clean-source checks.
- Python AST parsing without imports or bytecode output; Node syntax checks without executing scripts; runtime JSON/config parsing. Historical archives and intentionally broken archived examples are not application code.
- Static bos_control validation and source digest. No scripts/verify gates execute.
- One guarded Django system/import check on the exact candidate: models, urls and security tags only; no server, request, migration or database test.

## Guarded system check

Default boss_project.settings is forbidden: it selects SQLite files in the checkout and ignores verification database variables. Use verification_settings explicitly, BOS_VERIFY_DB=sqlite, BOS_TEST_DB_NAME=:memory:, BOS_TEST_MEDIA pointing to an existing isolated disposable directory, BOS_DATA_MODE=demo and Python -B. Assert effective settings before the check. No real secrets or credentials are used.

An independently reviewed Python audit hook must reject SQLite connection attempts, socket activity, subprocess starts, file write opens and filesystem mutations. Set the hook before Django/project imports. Capture output outside the guarded child. Record attempted forbidden events; if blocked, stop and retain the failure, never relax the guard to get a pass. The audit mechanism is not an OS sandbox or proof of all possible native behavior.

One initial system-check attempt, at most three for a newly identified harness defect after independent review. These are not attempts at the old P05/PG/E2E/browser problems. No old UI-column, module_views, build or live endpoint rerun. No installation, production, real data or GitHub workflow dispatch.

QA authors/runs the harness; plan_review independently reviews its implementation before use and the raw results afterwards. Root only integrates exact reviewed artifacts. A successful check proves import/model/URL consistency under the specified synthetic settings, not business transactions, role flows, restart behavior, visual layout or any of the 11 complete acceptance gates.
