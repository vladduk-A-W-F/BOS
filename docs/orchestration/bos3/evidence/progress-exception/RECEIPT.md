# B30-00 Progress QA Exception Receipt

## Authorization and Identity

The owner explicitly authorized one execution of the one-purpose historical
progress oracle. This was not a reset of the preceding three-attempt history.

- Candidate commit: `a445ac0584c79c2939269b37ec814b22691711c7`
- Candidate source: `frontend/boss_app_source.html`
- Source SHA-256: `01a5292fb260f7dd4a6ad1780c3c154291ed421a2874594bfd7c8965315f6cb0`
- Harness: `B30-00-progress-exception.cjs`
- Harness SHA-256: `7c0ebfd681a8b7ba4e8d6566650220073809672163f1fb602967eb4cc17a68cd`
- Execution count: `1 of 1`; no retry is authorized or performed.

## Command and Result

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' `
  'D:\3\BOSDev\qa-scratch\b30-progress-20260927\B30-00-progress-exception.cjs' `
  --root 'C:\Users\user\.codex\worktrees\bos-start-overview\repo'
```

Exit code: `0`.

The controlled JSX/VM/localStorage oracle selected `BOS3-CASE-02`, clicked
its fourth lesson step, and observed in `onNavigate`, before effects were
flushed and while simulating immediate unmount:

- route: `erp` / `quality`;
- storage key: `bos:demo:17:ceo:bos.training.v3`;
- storage value: `{"caseId":"BOS3-CASE-02","step":3}`;
- executed React effects: `0`.

This proves only the repaired synchronous save-before-navigation behavior for
that exact frozen candidate. It does not reclassify prior harness failures,
accept the whole learning path, or establish browser, server, database, CRM,
production, pilot, or 11-GATES readiness.

## Scope Exclusions

No browser, DOM, HTTP/TCP, Django, database, external CRM, server refresh,
product write, old training harness, full suite, PostgreSQL, E2E, A09, A10, or
A11 check was run. The raw stdout is preserved unchanged in
`B30-00-progress-exception.raw.json`.
