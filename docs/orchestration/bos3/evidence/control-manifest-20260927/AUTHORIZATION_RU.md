# B30-CONTROL-MANIFEST: focused synthetic QA

27.09.2026. New state-selected manifest schema regression in read-only CLI,
not application/fixture/progress/browser/full/lifecycle QA. Author bos3_fixture_impl;
independent code+oracle reviewer start_overview_review. Pre-run missing-file
fixture defect corrected before any execution, original preserved in review-v1.

Root authorizes QA bos3_crm_impl exactly one focused attempt1/3 after
ACCEPTED_FOR_ONE_FOCUSED_SYNTHETIC_QA. Exact tool97758b5982866952de2d5bb5a7b88a59b09e5697dc2e5725cc803f72f5853222,
test690e4659d489e409c3e0bfef74106f9278a50329a9bf3aa4a142e713a20ab0f9,
reportda99672b1797c2ca0d6241faeb6ca72ee9aa7ddbe08ea51651ce882fb89c26b2.

Workdir D:/3/BOSDev/qa-scratch/bos3-control-manifest-20260927.
D:/3/BOSDev/venv/Scripts/python.exe -B -m unittest, only these Bos3ControlTest methods:
test_state_selected_alternate_manifest_is_used,
test_missing_selected_manifest_fails,
test_unsafe_selected_manifest_fails_without_reading_it,
test_selected_manifest_pin_mismatch_fails.

Capture new run1 raw stdout/stderr, native exit, exact argv and hashes.
Only synthetic temporary control JSON, no DB/app/browser/network/runtime.
No automatic retry. Independent raw-result review before integration.
Historical CLI initial15tests+focusedrepair and app attempt caps remain unchanged.
