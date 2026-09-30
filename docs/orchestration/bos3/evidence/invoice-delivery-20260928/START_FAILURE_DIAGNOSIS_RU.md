# B30 invoice dev8 D start failure: read-only diagnosis

Status: `ATTEMPT1_START_FAILED_NO_RECOVERY_AUTHORIZED`. This is a forensic
reading of saved source and evidence only. No Python/module/parser/app launch,
process query, HTTP, stop/start/kill, data read/write, retry, or post-start QA
was performed.

## Saved attempt boundary

`delivery-once/CAPTURE_NATIVE_RESULT.json` records one capture, native exit
`0`; `APPLY_NATIVE_RESULT.json` records one apply, native exit `0`. Their raw
stdout records capture of archive
`maintenance-INVOICE-DEV8-D-20260928-window1` and a metadata update from d8
to `60f1e31fca6056711ea52d7aade6b65e0b14afff`. Those receipts prove only
their named delivery-template phases, not a running server.

The official lifecycle receipts record C stop native exit `0` and D start
native exit `1`. The D start receipt binds source
`D:\3\BOSDev\workspaces\bos3-runtime-dev8\repo`, owner root, exact candidate,
and manifest hash. It is native-exit evidence, not a ready/live identity
receipt. `official-start.stdout.raw.txt` is empty; stderr records:

```
PermissionError: [WinError 5] ... process.json.be6a89a61b41a79a.tmp -> process.json
```

at `scripts/bos3_local.py:570`.

## Exact write and child ordering

In exact source `60f1e31...`, `atomic_json` creates a unique `process.json.*.tmp`,
flushes/fsyncs it, then calls `os.replace` (lines 28-36). `start` first writes
`process.json` with `launch_requested` (553), starts the hidden child (555),
waits for a verified child announcement (556-560), then successfully writes
`identity_recorded` (565-568). The failed write is the subsequent `starting`
receipt at line 570.

Therefore source plus stderr prove that, at an earlier point in this same start,
the parent had received and identity-checked a child record. They do **not**
prove that this PID remains live now.

The internal child writes only `launch-<id>.json` (421-422); it reads
`process.json` while waiting for matching identity/status (427-440), and only
then may enter `internal_serve` (452-466). No child path in this source writes
`process.json`; all such writes named in this start path are parent writes
(553, 567, 570, 581, 591). Thus there is no source-proven parent/child writer
race. A transient child read at the failed replace moment cannot be excluded
from saved evidence, but neither raw output nor source identifies it as the
WinError 5 holder. External locking, ACL/driver behavior, or another actor are
also not distinguishable under the permitted reads.

## State artifacts and limited inference

The allowed state-name/mtime enumeration at the event shows no `process.json`.
It shows these new temporary files at `2026-09-28 01:43:01 UTC`:

* `process.json.be6a89a61b41a79a.tmp` (998 bytes), named directly in stderr;
* `process.json.7ebb63ea7d83910c.tmp` (1040 bytes).

The existing saved `last-start-failure.json` at `01:43:02 UTC` was read under
the subsequent explicit allowance. It records the historical process identity
(`pid` `55564`, creation ticks and the primary-runtime image), the source
digest, and `cleanup: {"stopped_after_start_failure": true}`. In the exact
source, that result is returned only after `verify_process` accepts the
recorded identity and `TerminateProcess` succeeds and the process exits (lines
491-501). It therefore establishes that failure cleanup historically verified
and stopped the recorded child. It is not a current liveness probe: it does not
establish a current PID, listener, endpoint, runtime identity, or the
holder/cause of the file-system denial.

The source failure path attempts a second `process.json` atomic write with
`start_failed` at 591. The two temp names/timestamps are consistent with the
failed line-570 replacement plus this failure-handler attempt, but file names
are random and the enumeration alone does not assign each temp conclusively.
The missing `process.json` means there is no current persisted receipt that can
be represented as a live identity. Absence of `launch-<id>.json` also proves
nothing: the child source removes that announcement in its `finally` block
(442-446).

## Decision boundary

The established failure is OS replacement denial at `process.json` after
parent-side child identity verification. The actual lock/denial cause and any
current process state remain `UNCONFIRMED` under this read-only scope. This
diagnosis does not authorize a status call, recovery, retry, stop, start, kill,
post-start QA, or metadata edit. Root requires an independent review and a
separate explicit decision before any further operation.
