# BOS3-TRAINING-01 independent review

Reviewed 27.09.2026 against parent 4a2e5a5. Independent reviewer: start_overview_review.

Verdict: ACCEPT_SCOPED_STATIC_FIX_WITH_QA_GAP. This candidate is for manual local-preview review only. No remaining P1/P2 was found by the final static source review; full acceptance is not claimed.

The reviewer checked all three fictional cases, current route targets, the factory-nomenclature analogy, department handoffs, human-readable CRM preview and exact synthetic JSON export. Export creates no CRM record, uses no live/private data and sends no network request. The technical runtime version remains 0.2.18-current; BoS 3.0 is the learning-model name only.

Corrections made during review: native case selection replaced incomplete tab semantics; purchase orders point to ERP/purchase, blocked lots to ERP/stock; production appears in the department handoff; inaccessible financial steps are disabled. The learning state is validated and namespaced by existing mode/user/role storage rules.

The focused training harness reached its three-attempt cap and ends FAIL/incomplete. Attempts 1 and 2 had missing harness mocks. The third passed case/navigation, readable-preview and synthetic-export checks before exposing the actual progress persistence defect: the guide could unmount before a shared state hook's effect saved the new step.

The final repair synchronously writes the selected case/step with the same role-scoped storage key before navigation. A failed storage write raises the existing user notice. The independent reviewer traced that final control flow and accepted the source-level correction. The corrected persistence behavior was NOT dynamically retested. The subordinate successful assertions must not be presented as a whole-suite PASS.

Root mechanical builds succeeded before and after the final repair; initial new-code lexical check succeeded; final git diff --check succeeded. These are syntax/build evidence, not execution proof of lesson progress. No full, PostgreSQL, E2E or browser suite was run. A new validation allocation is required before repeating the exhausted training harness.

The prior PDF endpoint and start/overview controls are unchanged from 4a2e5a5 and retain their earlier scoped evidence. Preview refresh and bounded four-GET availability observation occur after the commit and have their own external runtime receipt; this source record does not pretend they had already run.

TECHNICAL_READY=false, PILOT_ALLOWED=false, MVP=false. Real CRM models, activities, deal stages, persistence, migrations and command-path integration are the next product phase described in docs/learning/BOS_3_0_UA.md, not delivered by this teaching export.
