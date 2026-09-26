# V18 bounded QA

## Candidate and boundary

- Canonical candidate HEAD: `25208141c247ba931fce3a972be45536eafdd1c7`.
- Root-provided runtime source digest before the matrix:
  `44a3a2ee9fb1e8b36917f7c2c5c6aa60e533f1d3236e26de907e64520f94307a`.
- `scripts.verify.source_digest()` after the matrix returned the identical hash.
- QA writes are limited to this isolated `evidence/v18-20260926` directory,
  except for two accidental canonical `git_fsck` receipt files disclosed below.

No default settings, Django server, request, migration, DB suite, PostgreSQL,
E2E, browser, build, CI, deployment or old UI check was run.

## Results

| Check | Exit | Result and scope |
| --- | ---: | --- |
| `frontend_lexical_checker.cjs` | 0 | 4 PASS: allowed browser global plus unknown function, JSX typo/component and syntax-error canaries. |
| `check_frontend.cjs` | 0 | Static JSX lexical references passed; previous inherited exit 1 is preserved separately. |
| Guarded Django check | 0 | One approved attempt only. `verification_settings`, SQLite `:memory:`, only alias `default`, external existing `D:\3\BOSDev\test-media`, demo mode, Python `-B`; audit counters all zero before/after. Tagged models/urls/security check reported no issues. |
| `git fsck --full --no-reflogs --no-dangling` | 0 | Git object integrity check passed. |
| Python AST inventory | 0 | 342 `.py` files in runtime/test/script scope parsed without imports or bytecode output. |
| Runtime JSON inventory | 0 | 24 unique JSON files in runtime directories/config parsed, including the four current-pointer files. |
| Current-pointer JSON | 0 | Latest `docs/tracker/activity.json`, `CURRENT_BASELINE.json`, `STATE.json`, `QUEUE.json`: 4/4 re-parsed; this is not four additional unique files. |
| Node syntax inventory | 0 | 14 files: every `scripts/**/*.js` / `*.cjs` plus generated `assets/app.js`, checked with `node --check`; no failures. |
| `tools/bos_control.py validate` | 0 | Static result PASS; roles 10, tasks 41, gates 11; `application_tests_run=false`. |
| `scripts.verify.source_digest()` | 0 | After hash equals root-provided before hash. |

`python tools/bos_control.py source_digest` was attempted once by mistake and
returned exit 2 because that CLI has no `source_digest` subcommand. Its raw
receipt is retained. The allowed correct diagnostic is
`from scripts.verify import source_digest`, which returned the expected hash;
no product verification was repeated.

## Guard receipt

Helper SHA-256 before its only execution:
`68DD23CC1A3C42D8A4E9661BAB5C95A86E697267040CFD19A5ED51F377EC07C0`.

The child installed its audit hook before Django/project imports and rejected
SQLite connections, socket activity, subprocess starts, write opens and listed
filesystem mutations. Effective configuration and counters are printed in
`guarded_system_check.stdout-stderr.txt`; all five counters are zero. This is a
bounded import/system consistency result, not an OS sandbox or functional
acceptance.

## Git and current-state findings

- Local `main` is `ecb8cf7…`; `origin/main` and immutable tag
  `bos-current-2026-09-26` peel to `03fa08f…`.
- Each is an ancestor of candidate HEAD (`merge-base --is-ancestor`, exit 0).
- Candidate HEAD has no tag and is not equal to local/remote `main` or the old
  tag. This confirms v18 has not been published as `main` or newly tagged.
- The original 100-commit ledger is complete relative to candidate HEAD:
  all 100 commit objects exist and all 100 are ancestors of `2520814…`
  (receipt exit 0). Both plan baseline `a3c0596…` and current published
  `03fa08f…` are also ancestors of that candidate.
- The earlier `original_100_ancestry` receipt used `a3c0596…` as its target
  (78 ancestors, 22 non-ancestors). It is retained solely as a wrong-target
  provenance diagnostic and is not a conclusion about the final candidate;
  `original_100_final_candidate_ancestry` is the authoritative audit receipt.
- The canonical worktree is intentionally not clean: root-owned current
  records/trackers and the user-provided `AGENTS.md` are modified; two
  accidental untracked `git_fsck` receipts in canonical were reported to root
  for root-owned resolution. No runtime source file appears in that dirty list.

## Receipts and gaps

Every invoked command has a matching `*.command.txt` and
`*.stdout-stderr.txt` here. `source_after_identity.txt` records final HEAD,
three representative runtime file hashes and canonical status.

The initial fsck receipt was accidentally created in canonical and immediately
copied here; deletion through the execution tool was blocked. Root was notified
with the two exact paths and retains their resolution. This process deviation
affected only those two evidence files, never product code.

Verdict for this QA scope: `ACCEPT_SCOPED_WITH_RECORD_GAPS`. The static and
guarded checks passed, but do not establish full business behavior, browser
layout, PostgreSQL, deployment, 11-gate completion, `TECHNICAL_READY`,
`PILOT_ALLOWED` or `MVP`.
