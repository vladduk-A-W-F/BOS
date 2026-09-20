# P06-F02 independent read-only review

Reviewed 2026-09-20. PR https://github.com/vladduk-A-W-F/BOS/pull/1
Exact reviewed head: 82beca6c14e097a31200068d72b15334c5bed319
PR base: 7d46dced3bcf06d44755cf53366c9e16bd465582

Verdict: ACCEPT_SCOPED for the isolation guard; no actionable code defect found within P06-F02. Do not reimplement P10-003. No repository or external discussion writes, app tests, DB connections, or CI runs were performed by this review.

## Static assessment
- erp/test_initial_import.py:23-65 validates both environment and loaded verification profile, delegates issued source restrictions to database_config(), rejects backend mismatch, requires exact test_ + issued PostgreSQL source name and queries current_database(). The query precedes fixture writes at setUp:69-74.
- An unchanged source NAME, unrelated/custom TEST.NAME, mismatched backend, unknown profile or actual live source connection fails closed. PostgreSQL TEST settings are not an escape hatch: accepted NAME is derived from the verified source rather than TEST.NAME, and independently checked against the live connection.
- SQLite requires an absolute issued check path, a separate exact Django test pathname and samefile/resolve rejection of source aliases; in-memory SQLite is checked against Django memory name and PRAGMA database_list.
- This guard protects fixture writes. It does not claim to protect arbitrary Django test-runner setup/migrations before setUp or arbitrary adversarial modification of settings/environment. The approved verification allocator/harness supplies that outer lifecycle boundary.

## Live evidence independently checked
GitHub run 35503944302: completed success, attempt 1, exact head aecf8ee1f556b60f3fa34b66a001372e332d02ab. Live targeted job 106060472541 logs corroborate checkout and stage counts. PostgreSQL 16.15, Python 3.12.14, Django 6.0.5.
Artifact 10603616377: live digest SHA256 542a3c5975a0a4e1533f0f744bf3ad57e2f0f111afe232f04fb4efaf28185247, 28579 bytes. The ZIP fetched from current Git matches both hash and size. All 22 indexed members independently match sizes/SHA256; ZIP has exactly 23 entries including index. Both relevant raw log hashes match report.json.
Baseline red: one method, exit 1, old startswith(check_) assertion failure, actual test_bos_verify_728358a257fe4959 / server_version_num 160015.
Candidate green: 15 methods, exit 0, OK: 1 actual three-currency business import + 4 actual PostgreSQL import/concurrency methods + 10 fake-connection guard methods. Actual DB test_bos_verify_8bca77408fd742bc / 160015. Source canaries match before and after. Negative guard cases are fake-connection checks, not real attempts to write a working DB.

## Correspondence to current head
The following files are byte-identical between the tested aecf8ee1 commit and reviewed 82beca6 head, confirmed by connector content and Git blob IDs:
- erp/test_initial_import.py: 4046c788062fef0cc6167824f833146e873d95f9
- erp/test_initial_import_isolation.py: c07bbdb7ca89fa620df8d3fa890f9fdf77b97c7f
- scripts/check_support.py: ea446b6a178cdb8bd987f8e77393d3e829fc80b8
- verification_settings.py: 7c51467d32e77d07c7b8d800a9a83676c57c0578
- demo_settings.py: 60f390a5e2abc3cafe98d8323970ba4ca87d7767
- .github/ci/batch_01_targeted.py: 27b7346044276495e239e962eba3a2b5f308fd2c
Tested overall source SHA256 was 31c692c5f3113446452e8d15faf95c29b019f433550bf4d0658c4f0428e54d20. Product runtime changed after that commit; this review does not turn that old overall digest into a current-head full-suite PASS.

## Documentation drift to resolve separately
Current docs/orchestration/cards/P10-003.md:3 remains IN_PROGRESS and line 7 says no runtime reproduction; line 12 also retains an old after-pause phrase. Current P10-003/RECEIPT.json is a historical local-stage receipt with postgres16 PENDING. Canonical current state/report should clearly supersede these with scoped PG evidence without editing the historical receipt. Recommended bounded work: reconcile card status/current narrative with immutable historical receipt and PG16 summary.

Limits: no full suite, no new runtime validation on 82beca6, no production/historical database invariance claim, no readiness/pilot change. P06 BLOCKED and TECHNICAL_READY/PILOT_ALLOWED remain false.
