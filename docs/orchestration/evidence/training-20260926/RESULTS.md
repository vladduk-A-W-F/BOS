# BOS3-TRAINING-01 Focused QA Receipt

## Scope and Candidate

- Candidate inspected: `C:\Users\user\.codex\worktrees\bos-start-overview\repo`
- QA base supplied for this card: `4a2e5a5`
- Harness: `check_bos3_training.cjs`
- Intended execution: a Babel parse and controlled component rendering only.
  No browser, HTTP/TCP, Django, database, PostgreSQL, E2E, full suite, or
  external CRM access was used.

## Result

**Focused harness final status: FAIL / incomplete.** The three-attempt cap was
reached. It must not be reported as a full PASS, and it is not rerun after the
subsequent product correction.

The completed assertions, which remained successful before the halted
persistence assertion, provide limited positive evidence:

1. The three distinct training cases were present with owner role, next action,
   and the reviewed in-product destinations.
2. Their rendered navigation calls used the real `NAV` section/subsection
   model, including the corrected procurement and stock targets; the human
   CRM-preview labels were present.
3. The exported preview was JSON with the reviewed fictional contract:
   `schema: "bos.training.crm-handoff.v1"`, `synthetic: true`, and
   `crm_record_created: false`. No transfer or real CRM write was invoked.

Those are subordinate PASS observations only. They do not make the entire
focused harness a PASS.

## Attempt Record

| Attempt | Outcome | Evidence boundary |
| --- | --- | --- |
| 1 | Stopped after the case/navigation assertion block passed. | Harness mock omitted `bosCan`; this was a harness setup omission, not a product verdict. |
| 2 | Stopped after the case/navigation, label/destination, and JSON-export blocks passed. | Harness mock omitted the role context used by `bosStorageKey`; this was a harness setup omission, not a product verdict. |
| 3 | The same three preceding blocks passed; the progress assertion did not complete. | Controlled rendering observed that the new progress value was not yet in role-keyed local storage before effects could flush. This exposed a potential real navigation/persistence defect. |

Independent source review by the integrator confirmed the third finding as a
real P2 behavior: `openStep` scheduled state, called `onNavigate`, and could
unmount the guide before the shared `useLocalState` effect wrote the new step.
The incoming product correction synchronously persists the role-keyed progress
before navigation. Under the card-wide three-attempt cap, QA did **not** rerun
this harness or claim execution evidence for that correction; its boundary is
static review only.

## Deliberate Non-Checks

- No repeated full, PostgreSQL, browser, E2E, legacy column, or endpoint suites.
- No availability request was made. `check_local_availability.py` remains
  prepared and is restricted to a later explicit GO after commit and preview
  refresh, where it may issue exactly four approved local GET requests.
- This receipt makes no production-readiness, deployment, or live-data claim.

## Follow-up Gate

The focused training card needs an independently authorized new validation
allocation if execution proof of the synchronous persistence correction is
required. The exhausted harness must not be silently reclassified or weakened.
