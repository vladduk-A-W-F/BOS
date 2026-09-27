# BoS 3.0 Development Candidate 01

Version: **0.3.0-dev.1**. Baseline: `a445ac0` (PR #9), integration branch:
`codex/bos3-prerelease-20260927`. This is an owner-local review candidate,
not release, prerelease acceptance, production activation or permission to invite
external users. Main and frozen v18 are unchanged.

## Implemented Scope

- Interactive start brochure: 11 business areas, three independent synthetic
  fastener-factory cases, realistic company/product/order/lot/invoice facts.
- Server-owned lesson sessions: ordered checks, wrong-answer refusal, source
  evidence, stale-source recheck, pause/resume, optional tour independent of
  lesson completion. ERP operations retain their existing preview/confirm path.
- Minimal real CRM: account/source links, deals, owner/stage/next action,
  activities and activity status; all writes use preview and explicit confirm.
- One authenticated training installation with fixture/owner/database/hash
  binding, no passwordless demo login and no observer ERP mutation.
- Three-page Ukrainian start PDF, built from the same content registry and
  protected by the same owner-scoped training access.
- Windows localhost launcher with separate data/media/secrets/logs, protected
  owner access file, source pinning and identity-verified start/status/stop.

## Evidence Boundaries

| Check | Recorded outcome | Scope |
|---|---|---|
| Frozen a445ac0 progress exception | exit 0, ACCEPT_SCOPED, 1/1 consumed | One Node save-before-navigation check; never repeat |
| New fixture/CRM attempt 1 | Infrastructure failure | Missing scratch parent, no passing assertions |
| New fixture/CRM attempt 2 | Seven tests observed OK | Native exit was not captured; old fixture harness did not prove actual path |
| New fixture final attempt 3 | exit 1, zero methods | Settings-identity guard defect; 3/3 exhausted |
| QH01A correction | ACCEPT_SCOPED_STATIC | Existing profile-unwrapping pattern, no dynamic retry |
| New training attempt 1 | exit 1, eight of nine methods OK | Observer fixture omitted ordinary document-read permission |
| QH02 focused retry | exit 0, one method OK | Only failed observer method rerun; permission/read-only boundary |
| Frontend | ACCEPT_SCOPED_STATIC; one build exit 0 | No browser acceptance implied |
| PDF | Build/render exit 0; all three pages viewed | Layout, Unicode and content manifest checked |
| Local lifecycle | Pending dedicated receipt | No current listener or restart claim from static review |

Raw outputs and receipts are in `evidence/new-server-qa/` and
`evidence/progress-exception/`. Logs describe synthetic isolated databases only.
The corrected fixture harness is not dynamically accepted. The old exhausted
full/PG/E2E/browser/payment-network/column checks are not rerun or relabelled.

## Remaining Work

- Complete and record owner-local lifecycle/HTTP evidence, then give the actual
  URL and protected credential-file link. No Internet tunnel or purchase.
- Obtain the separately requested browser-check scope before browser acceptance.
- Implement and independently verify controlled training reset; currently not
  available and not presented as implemented.
- Continue content/role walkthrough and collect owner feedback; closed tester
  access requires a later migration/access decision.
- Preserve the 2026-10-04 conditional owner-local prerelease target and the
  2026-10-11 conditional release decision after feedback, not automatic release.

TECHNICAL_READY=false. PILOT_ALLOWED=false. MVP=false.
