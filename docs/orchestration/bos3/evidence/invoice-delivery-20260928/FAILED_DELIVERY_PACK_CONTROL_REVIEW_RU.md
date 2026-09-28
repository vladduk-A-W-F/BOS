# B30-INVOICE-DEV8-D: failed-delivery evidence and control review

Дата: 2026-09-28

## Scope

Проверены saved-artifact package и новая D canonical documentary/control delta. Runtime, instance, app, HTTP, test, browser, recovery и source preparation не выполнялись и не переаудировались.

## Package integrity and boundaries

- `MANIFEST.json` SHA-256 `15D7E83A2EF54A97B6E95C5C4BD03C538D15447824F73209C72C01E59DC438AD` и `REPORT_RU.md` SHA-256 `D384CCC43902B192418568E7036BC79F1DD0E2D251ED29F4524789CC74590C58` совпали с declared pins.
- Manifest lists exactly 33 artifacts; package contains exactly those 33 listed artifacts plus manifest/report. For all 33, target and specified source SHA-256 and byte length matched. `delivery-once` has complete declared `12/12` saved result/stream artifacts.
- Listed paths exclude declared sensitive/payload categories: `owner-access.json`, `runtime-secrets.json`, `prepared.before-stop.json`, databases, media and broad native logs. This review verified allowlisted paths and bytes; it did not inspect owner-state payload contents beyond their file identities.
- Outcome wording is factual: capture/official stop/apply native `0`; official start native `1`; post-start and root HTTP `NOT_RUN`; live child/runtime `UNCONFIRMED`; delivery not accepted; no readiness elevation. Start-failure diagnosis/review are preserved as evidence, not recovery proof.

## Control transcription

- `CONTROL_STATE.json` makes dev8 transition current and failed at official start, with `attempts=1`, no automatic retry, post-start/HTTP not authorised, read-only diagnosis plus a separate recovery decision next. It retains runtime source `d8` and dev.7 receipt as historical.
- `LOCAL_RUNTIME_RECEIPT.json` now expressly identifies itself as the last accepted historical dev7 delivery, not current availability after dev8 failure; its `current_transition` records `UNCONFIRMED` rather than a live service claim.
- Current top sections in ACTIVE/TEAM name `WinError5` at `process.json` replacement, preserve the three earlier successful phases without equating them to accepted delivery, and do not create a duplicate implementation, QA, start, kill, rollback, browser or HTTP operation.

## Verdict

`ACCEPT_SCOPED_FAILED_DELIVERY_EVIDENCE_AND_CONTROL_RECORD`.

The package may be copied to the planned canonical evidence path with these exact byte/provenance limits. This verdict is not runtime acceptance, recovery approval, start retry, post-start/HTTP permission or readiness/release approval.
