# V18 publication: independent review

Reviewer: plan_review (bos_reviewer), independent and read-only. Root transcribed the reviewer findings on 2026-09-26. Verdict: ACCEPT_SCOPED for the owner-authorized Git publication and current records. No product, tests, build or CI were executed by the reviewer.

## Candidate and Merge

Before publication, the reviewer independently confirmed clean HEAD 81ba3a04e74ecf139433ae9196775b7dcc09305c, 100 unique ledger commits in its ancestry with zero missing, and plan a3c0596, accepted code 2520814 and previous main 03fa08f as ancestors. Runtime/core files are identical to accepted code 2520814; only accepted docs/evidence follow it.

After the actual merge, the reviewer read 718b89497da0d338057ab2bd81d5034c68362d79 and its exact parents 03fa08f797503d04d2340ba8aa57e719b275c019 and 81ba3a04e74ecf139433ae9196775b7dcc09305c. Tree a4bb0bed5e6232af04eb657d2e8d1518e88a64c5 matches the reviewed head; git diff returned exit 0. The 100-commit inclusion therefore carries transitively into the merge.

Root's fresh GitHub observation, expected-head merge response and fetched refs are recorded in MAIN_PUBLICATION.json. The explicit owner instruction authorizes main and a new v18 tag; it does not authorize production, real data, rerunning exhausted tests or integration of unaccepted private packages.

## Publication Metadata QA

- Static orchestration passed: 10 roles, 42 tasks, 11 gates, exit 0.
- Runtime digest 44a3a2ee9fb1e8b36917f7c2c5c6aa60e533f1d3236e26de907e64520f94307a, merge parents, old tag and four critical ancestry assertions passed before the later terminating Git-matrix assertion.
- JSON assertion remains FAIL_HARNESS_FIELD_NAME. CURRENT_BASELINE uses product_commit; STATE uses product_candidate_commit. Manual reading confirms both contain 25208141c247ba931fce3a972be45536eafdd1c7 and the correct digest. The JSON file is an OBSERVED_TERMINAL_TRANSCRIPT because the exception preceded creation of the planned stdout receipt, not a rerun or an original redirected stdout file.
- Git matrix remains FAIL_HARNESS_SCOPE, exit 1: it rejected AGENTS.md, README.md and README_UA.md even though those are allowed metadata, not runtime. Independent diff review confirms the intended metadata-only scope.
- Its fresh original-100 loop was NOT_RUN after the terminating assertion. Inclusion is established by the separate independent ancestry and parent review above, not by relabeling the unexecuted loop as PASS.
- Both harness failures are retained without edits or reruns. The QA package is PARTIAL_METADATA_AUDIT_WITH_HARNESS_FINDINGS; no all-checks-PASS claim is made.

## Records and Publication Boundary

The allowed current documents and V18-PUBLISH-20260926 card distinguish confirmed merge from the following atomic main/tag push. Earlier QA and PR-creation receipts remain historical and unchanged. Snapshot links become valid through the planned atomic publication. The old tag is immutable; exact final head/tag observations belong to the external PR closeout after push, avoiding a self-referential commit hash.

Current product readiness remains false, and all unverified business/UI/PG/restart limits remain explicit. The new publication record does not claim an upgrade of the live application or Sites. Final remote verification is root's responsibility after this accepted docs-only commit.
