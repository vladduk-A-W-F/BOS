# BoS 3.0 Integration Cards

Date: 2026-09-27. Integrator: root. Baseline: a445ac0584c79c2939269b37ec814b22691711c7.
These cards compose independently reviewed worker outputs. They do not reset
any historical execution limit or alter the frozen readiness gates.

## B30-02A: Verified Fixture Identity

Problem: the first fixture harness substituted a path string instead of
proving the actual isolated database binding; the installed organization also
needed to use the same canonical company as the lesson registry.
Allowlist: `erp/test_bos3_fasteners_seed.py`,
`erp/management/commands/seed_bos3_fasteners.py`.
Root adds the organization and explicit refusal for an existing organization.
Independent static reviewer: start_overview_implementation, ACCEPT_SCOPED_STATIC.
The final fixture run is limited to this class, attempt 3/3 for the new card.
Result: native exit 1, zero methods executed. The class-level settings override
masked SETTINGS_MODULE. The later B30-QH01A commit uses the repository's existing
profile-unwrapping pattern and received independent ACCEPT_SCOPED_STATIC, with
no rerun. The fixture QA limit remains exhausted and the dynamic gate stays open.

## B30-I01: Server-Owned Learning and CRM Composition

Problem: lessons, authenticated identity, source evidence and the CRM command
boundary must refer to one fixture/session contract in an executable candidate.
Allowlist: `training/**`, `crm/**`, `frontend/bos3_content.json`,
`demo_settings.py`, `boss_project/{urls,auth_views,identity,policy,refinement_views}.py`,
`operations/{middleware,service,projections,views}.py`,
`docs/learning/{BOS3_CRM_CONTRACT,BOS3_TRAINING_REVIEW}.md`,
`scripts/build_bos3_brochure.py`, `docs/BoS_3_0_Start_UA.*` and scoped QA evidence.
The registry and authenticated PDF are included, not left as missing runtime
dependencies. Authors: root training/artifact, bos3_crm_impl CRM,
start_overview_implementation content. Independent review and targeted QA:
start_overview_review; independent training tests: bos3_crm_impl.
The integration combines B30-05/07/08/09 contracts, not a claim that all their
release gates or B30-03 reset work are complete.

## B30-I02: Frontend Composition

Problem: the previous local-only lesson/export must be replaced by the reviewed
server-owned lesson and real preview/confirm CRM flow.
Allowlist: `frontend/boss_app_source.html`, `scripts/build_frontend.cjs`,
`frontend/boss_app_html.html`, `assets/app.js`.
Author: start_overview_implementation. Independent reviewer: bos3_crm_impl,
ACCEPT_SCOPED_STATIC. Root build returned exit 0 once. Browser acceptance is
not implied by compilation or static review.

## B30-11: Owner-Local Runtime

Problem: the user needs a separate persistent localhost installation with
personal access, isolated synthetic data, and identity-verified lifecycle.
Allowlist: `bos3_local_settings.py`, `scripts/bos3_local.py`,
`scripts/bos3-local.ps1`, `docs/learning/BOS3_LOCAL_SERVER.md`.
Author: bos3_fixture_impl. Independent reviewer: start_overview_review.
Execution is held until final review acceptance; no production/public hosting.
Initial static verdict: ACCEPT_SCOPED_STATIC. A subsequent read-only Windows
runtime probe proved the venv redirector and actual Python executable differ;
B30-11A must reconcile the actual child identity before any server start.

## B30-R01: Candidate Identity and Evidence

Allowlist: version, README files, this integration ledger and BoS 3.0 control/
delivery evidence. Version: 0.3.0-dev.1. This is a development review candidate,
not the final prerelease or release. Main, frozen v18 and readiness stay unchanged.
