# V18 Start Overview Focused QA Results

Observed after the product worker completed the allowed UI, PDF, and route
changes. Candidate base HEAD was `d88624da95f034647a8bb031f25f7549d1cd0348`
with the V18 start-overview worktree changes present.

## Commands

```powershell
& 'D:\3\BOSDev\venv\Scripts\python.exe' 'D:\3\BOSDev\online-review\v18-local-20260926\start-overview-qa\check_start_guide.py' --root 'C:\Users\user\.codex\worktrees\bos-start-overview\repo'
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' 'D:\3\BOSDev\online-review\v18-local-20260926\start-overview-qa\check_start_overview_ui.cjs' --root 'C:\Users\user\.codex\worktrees\bos-start-overview\repo'
```

Both commands completed once with exit code `0`.

## Backend Result

`PASS` (`bos.v18.start-guide-focused.v1`):

- demo plus loopback returns the exact fixed PDF bytes as an attachment with
  `application/pdf`;
- non-demo returns `404`;
- a non-loopback address returns `404`;
- a missing fixed file returns `404`;
- `POST` returns `405` and allows only `GET`.

The observed PDF SHA-256 was
`7d981b0897764f20d62d0e36c27f1793510cf97fb6f1b8277ee41eb19fe160e9`.
The Django `Method Not Allowed (POST)` diagnostic is the expected output for
the deliberate `405` case, not a failed command.

## Frontend Result

`PASS` (`bos.v18.start-overview-ui-focused.v1`):

- demo `AuthGate` renders the brochure and retains the username/password form
  and passwordless local demo entry;
- working-mode `AuthGate` keeps normal credentials and does not link the
  demo-only PDF endpoint;
- navigation labels and route props distinguish `Вертоліт` from `Сьогодні`;
- the read-only helicopter render has metrics but no `NextAction`, recovery
  entry, operational workpoint panel, or submit dialog;
- the daily render remains the operational counterpart;
- the existing snapshot identity and permission guard expressions are present.

## Boundaries

No database, HTTP server, TCP, browser, E2E, PostgreSQL, or historical column
suite was run. Neither focused harness writes into the candidate source tree.

Harness SHA-256:

- `check_start_guide.py`: `185fc465aa93987eb0a39850251cf9c18658feea4d9692a6f6f4b33326ad72e6`
- `check_start_overview_ui.cjs`: `446f72586d6d75e7e5c890c5ed31033e2eae7092df181699349f86dbfa563163`

## Additional Regression Harness

The first execution of `check_start_overview_regressions.cjs` stopped before a
product result because its initial assertion incorrectly searched for the
overdue-list filter inside `BoSHome`; the actual filter belongs to the adjacent
inspector component. The raw failure is preserved in the task log. The harness
was corrected to inspect the actual component that owns the filter, without
weakening the product assertion, before its one necessary retry.

The second execution confirmed that overdue-list regression and then stopped
on another harness-only assumption: the final implementation intentionally
uses the shared `.bos-auth-form` selector instead of nesting the grid rule
under the demo-only disclosure. The assertion was updated to require that
shared selector and the disclosure-specific spacing rule before the third and
final permitted attempt.

The third attempt completed with exit code `0`:

- overdue KPI configuration retains `overdue: true`, and the inspector filters
  only `is_overdue === true` tasks for that selection;
- the one shared credential form has `.bos-auth-form`, including its universal
  grid layout and the disclosure-specific margin;
- both overview modes expose the selected currency control, while the daily
  invoice list filters by that same `cur` value;
- `heli-overview` and `today-work` are distinct route component keys, preventing
  hidden overview state from following navigation between modes.

`check_start_overview_regressions.cjs` SHA-256:
`617fe84ab7bad661cf46f049038060c4c5b29b07c2fc2c31e47a6bba0ce968c9`.
