# BOS3-TRAINING-01 Focused QA Plan

Prepared against candidate base `4a2e5a5`. This plan is not an execution
receipt. The actual source structures must be read after the UI worker signals
READY before assertions or a runnable harness are written.

## Single Planned Command

```powershell
$candidate = 'C:\Users\user\.codex\worktrees\bos-start-overview\repo'
$node = 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
& $node 'D:\3\BOSDev\online-review\v18-local-20260926\training-qa\check_bos3_training.cjs' --root $candidate
```

The command will be a Babel parse plus controlled component rendering only. It
will not start Django, use a database, open HTTP/TCP, invoke a browser, access
external CRM, or modify the candidate tree.

## Deferred Local Availability Check

This is prepared but must not run until the root integrator explicitly signals
GO after committing the reviewed candidate and refreshing the existing local
synthetic preview. It permits exactly four one-pass GET requests and no others:

```powershell
$candidate = 'C:\Users\user\.codex\worktrees\bos-start-overview\repo'
$python = 'D:\3\BOSDev\venv\Scripts\python.exe'
$receipt = 'D:\3\BOSDev\online-review\v18-local-20260926\runtime-start-overview.json'
& $python 'D:\3\BOSDev\online-review\v18-local-20260926\training-qa\check_local_availability.py' --root $candidate --runtime-receipt $receipt
```

It checks the exact `127.0.0.1:8018` root, `assets/app.js`, fixed start-guide
PDF, and runtime endpoint. The runtime assertion uses only the real fields
`version`, `data_mode`, and `ai_configured`; it does not invent legacy field
names. It compares served app/PDF bytes to the candidate and the full
`source_commit` in the refresh receipt to candidate `git HEAD`.

## Required Unique Case Checks

1. Exactly three stable, unique educational case codes are present. Every case
   has a department owner, a next action, and an existing navigation target.
2. Every destination resolves to the actual `NAV` section/subsection model;
   no training route invents a new product screen or bypasses normal routing.
3. CRM handoff preview/export is fictional and structurally valid JSON. It must
   state `synthetic: true` and `crm_record_created: false`, contain no live
   data, and avoid external transfer. If role-isolated local progress exists,
   it must be visibly local-only and cannot be treated as a business action.

## Invariants To Confirm From Actual Source

- The label is `BoS 3.0` only for learning content; existing runtime version
  declarations remain outside the training feature and are not replaced by it.
- The existing start/overview components and navigation remain the destinations
  of learning links rather than being duplicated or rewritten.
- Assertions will use the actual object keys and rendered component props after
  READY, not inferred field names from this plan or from the handbook prose.
