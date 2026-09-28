# B30-INVOICE-DEV8 source preparation: environment provenance addendum

Дата: 2026-09-28

Проверена только P1 provenance correction; Git, runtime, test, delivery и повторные clone/checkout не выполнялись.

## Связанные факты

- `CLONE_RAW_PROCESS_EVENT.json` SHA-256 `6F5CDCA7F809BF63AB8E949E6F43E8CE08D5BB5E35B2A10709598F888BB89C75` содержит completed native event `exec-5d96df79-eb9b-467d-a80e-191ad3fbf9b2` at `2026-09-28T01:23:47.169Z`. Его command text устанавливает `$env:GIT_ATTR_NOSYSTEM='1'` непосредственно перед `& git @args`; exact clone argv, native exit `0`, output hashes и timestamps совпадают с saved `CLONE_NATIVE_RESULT.json`.
- `CHECKOUT_RAW_PROCESS_EVENT.json` SHA-256 `F465034209B3F203D0ACB62791E61D252E6F1E78AF41BB88C7D5F269C8969AA1` содержит completed native event `exec-94758fa0-8b13-4023-9895-49311e207629` at `2026-09-28T01:24:13.163Z`. Его command text устанавливает ту же переменную непосредственно перед `& git @argv`; target `60f1…`, native exit `0`, argv, output hashes и timestamps совпадают с `CHECKOUT_NATIVE_RESULT.json`.
- Independent observer record `D:/3/BOSDev/evidence/bos3-readiness-20260927/CONTINUATION54_SOURCE_ENV_COMMAND_RECORDS.json` SHA-256 `68F6058D7467DCDD53C16475F8358E4EFBB69FF6F254F97972A5FFBF1E535F34` independently records both same event IDs, command texts and exits as retrieval from existing native command records. It is corroboration, not a new execution.

## Limitation

Direct byte-for-byte reopening of the original append-only rollout JSONL was unavailable because another process held an exclusive lock. The one failed read was not retried. Thus the D event snapshots and independent observer record support the recorded process environment, while a fresh direct source-file byte comparison is `UNCONFIRMED`.

## Verdict

`ACCEPT_SCOPED_ENVIRONMENT_PROVENANCE_ADDENDUM_WITH_SOURCE_LOCK_LIMITATION`.

This closes the specific missing `GIT_ATTR_NOSYSTEM=1` evidence in `SOURCE_RESULT_REVIEW_RU.md` for the recorded source-only operation. It does not upgrade the checkout into runtime/delivery acceptance and does not permit any further clone, checkout, retry or runtime action.
