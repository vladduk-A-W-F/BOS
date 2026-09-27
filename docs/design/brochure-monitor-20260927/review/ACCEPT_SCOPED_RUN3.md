# ACCEPT_SCOPED — brochure and monitor, run 3

Independent review accepts the final targeted **offline visual** evidence for the new interactive brochure and authenticated global monitor. This is not backend, database, release, hosting, or full-product acceptance.

## Accepted evidence

- Harness: `brochure-monitor-qa.cjs`, SHA-256 `8416F44CF43293E977546B9C28178C1CA553E7CB41F77007A66BE04783918EF6`.
- Output: `artifacts-run3/` only: eight PNG captures, `brochure-monitor-report.json`, and `run3.log` with `exit_code: 0`.
- Fully intercepted origin: `https://bos3.qa`. All files and fixtures are local; mutations return 405, unknown API GETs fail the run, and no server or database is started.
- The report records no unknown GET, no console/page errors, and no document or relevant-surface horizontal overflow in all eight captures.

The eight accepted capture labels are `brochure-desktop-cover`, `brochure-desktop-keyboard`, `brochure-mobile-reduced-motion`, `brochure-deeplink-signin`, `monitor-desktop-fresh`, `monitor-desktop-stale-hidden`, `monitor-desktop-persistent-crm`, and `monitor-mobile-observer`.

The report further verifies one successful visible focused sign-in input before and after its capture; fresh/stale monitor behaviour; finance hiding for the observer; monitor persistence through ERP to CRM; valid empty zeroes; and clear-to-public-entry behaviour for snapshot 401, 403, and access-revision mismatch. The latter is the actual product lifecycle: the global fetch wrapper ends the session, so the monitor unmounts and no previous value remains.

## Frozen build identity

The report hashes match the reviewed build1 files:

| File | SHA-256 |
| --- | --- |
| `frontend/boss_app_source.html` | `0FE2A86C6FE4CDA53F83507F9EAFE4BE1A066BE193C133CF5B9F2A45D63884E8` |
| `frontend/boss_app_html.html` | `33A8372FB84A83F6C4D3E51CBB6AC3524B74AC5D47FF9B85D9BB808C988A69F5` |
| `frontend/bos_design.css` | `79FC5209BB5C781B3AE052B6AA920E5171D405CC9AA6A6E8C2B6DAA99AED4977` |
| `assets/app.js` | `E193D08B31E16B3C2100FA14414AA87A4C8F5946DA7396081503FA353920F8D9` |
| `frontend/bos3_content.json` | `1BCE859370537437C157893065AF499C9EDD0FEFEA90B30C2F3384B2B04B1390` |

The monitor deliberately owns an independent guarded snapshot reader. It is not a shared store with the existing Today/Helicopter screens, and those screens can therefore issue another snapshot GET with a different read time.

## Delivery-document consistency

The product handoff at `docs/design/BROCHURE_MONITOR_20260927_RU.md` is consistent with this acceptance: it reports run3's eight clean captures and four state checks, distinguishes ordinary stale-read dashes from 401/403/revision-mismatch session end into public entry, states the independent-reader limitation, and records that swipe is implemented but was not tested as a physical-device gesture. Its stated three-attempt history is accurate: runs 1 and 2 were stopped by harness defects and are not accepted visual evidence.

## Packaging boundary

Only `artifacts-run3/` can be presented as successful visual evidence. `artifacts-run1/` and `artifacts-run2/` are failed partial harness attempts and must remain failure provenance outside the PASS gallery and successful-report count. The accepted scope is the eight new brochure/monitor surfaces only; it does not reopen prior capped visual, backend, PG, network, payment, progress, or release checks.

The packager must verify that the delivery document's gallery, QA-report, and manifest links resolve to the run3-only package and that the package manifest preserves the five frozen-build hashes above.
