# WORKPOINT-DIALOG-FOCUS

20.09.2026. Actual scoped browser attempt 4 stopped at the first 390 px dialog: Escape closed the native dialog, but keyboard focus did not return to its opener. Native 200% zoom passed; subsequent Gate 10 and flow checks were not reached. Cleanup proved browser, owned launcher/server, and disposable runtime removal. This failure remains evidence; it is not a passing browser run.

WorkpointsPanel disables controls while it reads current facts before opening an action. The previously focused opener can lose focus during that await, before showModal records its native return target. Capture the original element before setting busy and retain it only in component state. On dialog close, restore it only while the access scope is unchanged and the element is connected and enabled. No business write, permission, recovery, or runner assertion changes.

Allowlist: frontend/boss_app_source.html; generated frontend/boss_app_html.html and assets/app.js; scripts/check_workpoint_focus.cjs; this card. One independent review and atomic commit are required before a new frozen browser run. Historical full-suite retry limits remain unchanged.

Validation: the new controlled actual JSX regression fails before the fix and passes four cases after it (original element, disconnected element, disabled element, changed identity scope). The 22 existing confirmation recovery controls pass after the same parent lifecycle changed. Frontend build passes. These controlled checks do not establish native browser acceptance. Preserve both the failed browser report and the new browser result separately.

Technical readiness and pilot approval remain false.
