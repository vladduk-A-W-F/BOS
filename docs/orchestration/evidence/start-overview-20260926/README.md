# V18 Start Overview Focused QA

Prepared for `V18-START-OVERVIEW`. These checks are intentionally outside the
candidate source tree and are not yet executed. They must run only after the
product worker declares the allowed files complete and the integrator gives GO.

## Scope

- `check_start_guide.py`: direct, in-process Django view checks for the fixed
  `/help/start.pdf` endpoint. It verifies demo-loopback byte-for-byte PDF
  attachment delivery and the non-demo, remote, missing-file, and POST denial
  cases. It creates only a temporary empty directory for the missing-file case.
- `check_start_overview_ui.cjs`: Babel compilation and controlled-hook renders
  of the actual `AuthGate` and `BoSHome` functions. It checks the demo brochure,
  working-mode denial of the demo-only link, retained credential form, distinct
  `Вертоліт` / `Сьогодні` routes, and a read-only helicopter without actions,
  recovery entry, or action dialog. It also checks the retained snapshot and
  permission guard expressions.

Neither script starts Django, accesses a database, opens TCP, invokes a
browser, runs E2E, runs PostgreSQL, or edits the candidate source tree.

## Approved Commands After GO

```powershell
$candidate = 'C:\Users\user\.codex\worktrees\bos-start-overview\repo'
$python = 'D:\3\BOSDev\venv\Scripts\python.exe'
$node = 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'

& $python 'D:\3\BOSDev\online-review\v18-local-20260926\start-overview-qa\check_start_guide.py' --root $candidate
& $node 'D:\3\BOSDev\online-review\v18-local-20260926\start-overview-qa\check_start_overview_ui.cjs' --root $candidate
& $node 'D:\3\BOSDev\online-review\v18-local-20260926\start-overview-qa\check_start_overview_regressions.cjs' --root $candidate
```

Run each command once. Preserve any failure output as evidence; do not weaken
assertions or substitute a broader suite.
