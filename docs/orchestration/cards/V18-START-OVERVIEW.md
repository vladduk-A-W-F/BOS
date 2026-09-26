# V18-START-OVERVIEW

## Request

26.09.2026: owner requested access instructions and a starter brochure, then explicitly placed the brochure on the start page. The owner also requested removing duplication between the helicopter/daily/start views and keeping the helicopter informational with metrics.

## Scope

- Base: d88624da95f034647a8bb031f25f7549d1cd0348, BoS v18.
- Show the starter brochure within AuthGate and explain the existing passwordless local CEO demo entry. Keep the normal credential form available; do not provision or elevate accounts.
- Separate the existing heli and dash routes: helicopter for read-only metrics and source inspection, daily workspace for operational actions. Retain the hardened ERP snapshot reader and role checks.
- Serve one fixed public brochure PDF only in local demo mode. Never expose the docs directory, private media or arbitrary paths.
- No schema, policy, business-service, seed or real-data changes. Do not restore the old generated-data helicopter component.

## Allowlist

frontend/boss_app_source.html; generated frontend/boss_app_html.html and assets/app.js; boss_project/refinement_views.py; boss_project/urls.py; docs/BoS_v18_Start_UA.pdf; this card and scoped evidence under docs/orchestration/evidence/start-overview-20260926/.

## Verification Budget

New focused static/component and fixed-file endpoint checks only, with at most three attempts for a specific new defect. One frontend build and narrow lexical check. Independent review must inspect the actual diff and raw results. No full, PostgreSQL, E2E, browser or historical column suite reruns. PDF rendering is document QA, not a product browser run.

After acceptance, refresh the local-only preview using the existing synthetic review.sqlite3 and media, preserving both and the prior v18 receipt. No migrations, seeding or production activation. A bounded local HTTP check may read the root, changed app asset, brochure and runtime status; it must not conduct business operations or bypass denied routes.

## Acceptance Limits

This is a scoped usability follow-up, not a new acceptance of all BoS workflows. TECHNICAL_READY=false, PILOT_ALLOWED=false and MVP=false remain unchanged. The published bos-v18-current-2026-09-26 tag remains immutable.
