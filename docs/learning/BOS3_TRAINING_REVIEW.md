# Independent Static Review: BoS 3.0 Training Sessions

Status update, 2026-09-27: the findings below are the retained initial review,
not the current unresolved list. The manifest hash is now compared with the
committed fixture bytes; the next mutating action persists `needs_recheck`.
The content registry is included in the backend integration candidate.

Independent execution outcome: `ACCEPT_SCOPED_QA`. The first new run returned
native exit 1: eight methods passed, while the observer fixture lacked the
ordinary document-read permission. Only that method was retried after fixing
the fixture. It returned native exit 0 and verifies denial before the grant,
read-only lesson progress after the grant, and continued ERP-write denial.
The eight successful methods were not repeated. See
`../orchestration/bos3/evidence/new-server-qa/` for raw outputs and receipts.
This does not establish browser, PostgreSQL, release or historical-suite PASS.

Scope: root-authored `training/**`, its fixture/access/identity integration, and
the expected CRM completion boundary. This is a static review only. No test,
seed, migration, Django server, browser, network, PostgreSQL, full suite, old
training harness, or historical capped check was executed by this reviewer.

## Findings

### Integration prerequisite: keep the content registry in the atomic candidate

`training.service.catalog()` unconditionally reads
`frontend/bos3_content.json`. The registry is present in the validation copy,
but it must land atomically with the training service and its routing. Until
that composition is complete, `GET /api/training/content/` is not a runnable
candidate. The registry needs fixture ID, case IDs, routes, and texts matching
the server facts.

### P1: Fixture marker hash must be bound to the immutable fixture manifest

`training.access.installation()` currently checks that `marker['hash']` is a
64-character string, but does not compare it with the SHA-256 of the approved
fixture manifest. A database marker altered to another 64-character value can
therefore still pass installation access and start a new session. Bind the
value to the committed fixture manifest (or a separately sealed manifest
receipt) before training access is granted. The targeted marker-hash rejection
test deliberately captures this fail-closed requirement.

### P2: Persist `needs_recheck` on a later mutating lesson action, not on GET

When a saved step stamp no longer matches current source facts,
`session_state()` correctly reports `needs_recheck` without writing on GET; the
read-only behaviour is intentional. A subsequent mutating `navigate` or
`check` action must persist the derived `needs_recheck` state transactionally
when the source is still stale, while preserving the old evidence for
explanation. The reviewed implementation saves `in_progress` before computing
the result, so this later-write case needs the root correction and test.

### Decision recorded: tour is optional and separate from lesson completion

`change(..., action='tour')` may accept `skipped` or `completed` before the
lesson is complete because the free-workspace onboarding tour is optional. The
server must keep this state separate: a tour update must not mark the lesson or
CRM step complete. The added test checks this distinction.

## Boundaries that read correctly in this snapshot

- Identity is derived from the authenticated user and rechecks the active user,
  exactly one BoS role, and the synthetic training installation owner.
- The fixture marker checks its ID, resolved database identity, owner, isolated
  profile and database-name guard before lesson state is served. Its hash needs
  the P1 manifest binding described above.
- Case 03 source reads require CEO. Observer training operation rows are
  converted into answer-only progress; middleware permits only those narrow
  training POSTs for observer.
- A step is completed by a correct answer or verified source fact, not a route
  visit or navigation request. A CRM record is required for the final CRM step.

## Added Independent Tests

`training/test_sessions.py` is intentionally not executed here. It is designed
for the new isolated synthetic fixture and covers:

1. Start, ordered steps, wrong answer refusal and server-owned progress resume.
2. Stale source invalidation: GET stays read-only, while the next mutation must
   durably record `needs_recheck` if the source remains stale.
3. CEO access to the finance lesson; observer answer-only progress and blocked
   ERP mutation.
4. Foreign-user and disabled-marker denial before lesson state disclosure.
5. Case 03 task evidence, CRM draft -> preview -> confirm, final CRM step, and
   a tour that remains independent from lesson completion.
6. Case 01 receipt, quality, material reservations, production routing and
   output quality through ERP preview/confirm only.
7. Case 02 allowed-lot reservation and shipment, blocked-lot preservation,
   CRM creation/replay/no-op/stale-preview behaviour and role/foreign-user
   source privacy.
8. Marker hash and bound database identity rejection before reading a session.

The test is a new narrow training/CRM candidate. It is not permission to rerun
the exhausted historical browser, E2E, PostgreSQL, payment/network, column or
old training-progress checks.
