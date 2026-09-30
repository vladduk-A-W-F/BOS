# B30-11 final evidence review

Date: 2026-09-27
Reviewer: independent read-only reviewer
Scope: owner-local synthetic runtime evidence only. No test, HTTP request,
browser action, server action, seed, migration, or application write was run
for this review.

## Verdict

ACCEPT_SCOPED_OWNER_LOCAL

The verdict covers an authenticated, loopback-only owner-local runtime at
`http://127.0.0.1:8030/`, its controlled restart, and the recorded HTTP read
receipt. It is not a production, public hosting, invited-tester, browser,
fixture-QA, reset, or readiness acceptance.

## Reconciled evidence

- Runtime source metadata: clean `33d7d387aa582c04339a91ae94361948ea67904c`
  and source digest
  `e29b09975f32c0c5edb89eeabcc7c16c901b943adeefcf502becc861315eb4dc`.
- Protected non-secret prepared/process metadata matched that digest, loopback
  port 8030, Waitress, and the documented ready receipt identity.
- `http-first.receipt.txt` SHA-256:
  `6f386c886b554cdddc5ea1116af9ced5bace3524e1875af8208c6f63f34c772`.
- `http-resumed.receipt.txt` SHA-256:
  `b7d4d91483650f4d0bc3466594577b779962ca31d5c57cdbe61607e76998c0d6`.
  The receipts show the expected three case IDs, 11 training areas, CEO
  authentication/session resume, empty CRM, anonymous training/PDF denial,
  and matching brochure PDF SHA-256
  `b0068311bfcf57b69d2439646b626a4b2a20d3b544a57b0bacf770e5e0c68daa`.
- `database-restart-hashes.json` supplies original-command provenance for
  pre-stop and post-restart SHA-256
  `89ED2ED46AA051BC966238DDE2E2FF6E89EB354B726EE7EBAB0EC351A274251B`.
  Its cited tool chunks exited 0. This review did not reproduce the command.
- `maintenance-receipt.json` records the reviewed c1b6d67 to 33d7d387
  stopped-instance source rebind with data/media/credential preservation and
  no init/seed/migrate.

## Boundaries retained

- Fixture QA remains 3/3 exhausted; its final harness correction is static
  only.
- Training QA is accepted only in its recorded focused scope.
- Controlled reset is not implemented or accepted.
- Browser acceptance is false. The listener is local only; there is no public
  or invited tester access, Windows auto-start, production release, or changed
  readiness status.
