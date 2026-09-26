# TEST-INFRA-LEXICAL-01

## Cause

The inherited JSX reference checker reports the standard browser global getComputedStyle as unresolved. The call in frontend/boss_app_source.html:754 and checker both predate the current consolidation. Previous actual failure is preserved in evidence/current-20260926/columns/check_frontend.*. This card repairs that testing defect, not product behavior or old exhausted suites.

## Allowed changes

- scripts/check_frontend.cjs: allow this one browser global; expose the existing analyzer only as needed for direct canary testing, preserve CLI behavior.
- scripts/checks/frontend_lexical_checker.cjs: new synthetic self-test of the checker, including unknown function/component/typo rejection and syntax failure.
- This card, its review and the four named checker receipts in evidence/v18-20260926/.

No frontend JSX, business logic, permissions, fixtures, databases, dependencies or generated application assets change. A negative canary must still fail for a genuinely unknown identifier. Never suppress arbitrary unresolved references.

Author: columns_implementation in isolated bos-column-content checkout. QA: columns_qa. Reviewer: plan_review. Canonical integrator: root. Author does not run tests or accept their own implementation.

## Verification

One initial invocation of the new checker self-test, and one post-repair real JSX lexical invocation, each with raw output and exit code. At most three attempts for any newly exposed defect; the inherited failure remains in history. No UI-COLUMN-CONTENT-01, module_views, build, full/PG/E2E or browser rerun. A pass proves only analyzer correctness and resolved references under its static model, not working UI or full product readiness.
