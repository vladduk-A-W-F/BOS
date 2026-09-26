# TEST-INFRA-LEXICAL-01: independent acceptance

Reviewer: plan_review. Verdict: ACCEPT_SCOPED after source inspection and raw QA review. Author columns_implementation did not run tests or accept the code; QA columns_qa ran the canaries once and real JSX lexical check once.

Only getComputedStyle was added to the known browser globals. The existing Babel ReferencedIdentifier/hasBinding analysis and CLI nonzero exit for unresolved identifiers remain. Direct canaries use the same exported analyzer, not a replacement: permitted global, unknown function, unknown JSX component/typo, and syntax error.

Results: frontend_lexical_checker exit 0 / 4 PASS; check_frontend_v18 exit 0. The Babel deoptimization message is informational. The previous actual exit 1 remains in evidence/current-20260926/columns/check_frontend.*. New captured text receipts were normalized from CRLF to LF for staging; command output content and exit codes were not changed and no command was repeated for that normalization.

| Source | SHA-256 |
|---|---|
| scripts/check_frontend.cjs | adbdccfcb7e35f918594e9abbde0edea03698327716e4832402297e74cef8119 |
| scripts/checks/frontend_lexical_checker.cjs | a79df89f176290817980db28abcf3743de07dcd1fa4f7bedf38bf0870580e341 |

Frontend source, generated assets, APIs, domain data and permissions are unchanged. This repairs the analyzer defect and proves only its bounded lexical model. It is not a browser, full frontend, PostgreSQL or business-workflow acceptance and does not reset old attempt limits.
