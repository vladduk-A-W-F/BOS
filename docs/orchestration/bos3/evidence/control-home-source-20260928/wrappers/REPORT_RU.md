# B30 D control home: wrapper source-only preparation

Статус: `INACTIVE_SOURCE_ONLY_STATIC_REVIEW_REQUIRED`. Затронуты только three
staged wrapper copies and static artifacts. No PowerShell/Python helper,
PostgreSQL, app, lab, state, policy, registration or service action was run.

## Shared path and ordering

Wrappers use fixed legacy `C:/Users/user/AppData/Local/BOSDev` only as the
ordinary default, and pass selected `--home` unchanged to the accepted Python
resolver/API. They do not compare paths, recognise a D home, create an
authority marker, establish state or provide a second resolver. Explicit
nonlegacy selection is therefore rejected by the core resolver, not by a
wrapper-local authority rule.

`start-workday.ps1` adds `-Home` and moves its resolver-backed coordinator
status before `pg-control Start`, PostgreSQL status and the app branch. The
existing status result still provides the same task-count report for legacy
startup after that required ordering change.

`bos-flow.ps1` adds `-Home` and passes the selected home through the accepted
flow CLI as `--home <value>` before its action. The final flow-core binding is
`ACCEPT_SCOPED_STATIC_FLOW_CORE_BINDING`, review
`9beb9790de869bed59f665845b3480770d58d39dd384c60bbc6f8409e8ed117b`.

`bos.ps1` uses the fixed tools directory rather than `LOCALAPPDATA`; both
status and every non-status route call `bos_dev.py --home <value> status`
before PostgreSQL environment setup or lab launch. A rejected nonlegacy lab
override therefore stops before it can inherit a presumed D-safe `PYTHONPATH`.

## Boundary

This is no cutover evidence. It does not update Startup/Run registrations,
policy, services, external callers, live authority/state/ledger, quiescence or
runtime readiness. All dynamic validation and nonlegacy authority establishment
remain separately authorised future work. `executions=0`.

## Focused P1 repair

Static review `1d94287c1c899a01d9c1c57d7cd63c33b52eb2abd8ecdcdb47c094711288a409`
found that the pre-existing outer `finally` could launch Codex after an
unsupported selected-home refusal. `start-workday.ps1` now records a positive
`coordinatorStatusConfirmed` fact only after resolver-backed status returns
and its result is accepted. The app branch requires both mutex ownership and
that fact. A refusal therefore records `skipped_coordinator_status_not_confirmed`
without app launch. A later PostgreSQL failure after a successful coordinator
status still enters the app branch, preserving ordinary legacy behavior.

No changes were made to accepted `bos.ps1` or `bos-flow.ps1`. This delta is
source-only; canonical archive context is now
`fa192b3507c343336991adb0229d20d2b6db9e98`, while original card context
`778b364b6dcc0d7fe23e85ebdd0bdf941cf08d51` remains provenance only.

## Parameter identifier P1 repair

The focused app-finally repair did not address the independently confirmed
PowerShell identifier conflict: `[string]$Home` collides case-insensitively
with automatic/read-only `$HOME`. All three wrappers now declare
`[Alias('Home')][string]$ControlHomePath` and use only that identifier.
Existing callers retain `-Home`; each wrapper still forwards the selected value
as Python `--home`. The coordinator-status app gate is unchanged.
