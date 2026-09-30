# BoS 3 · offline visual QA, build4

Classification: **NEW visual styling validation**. This is offline rendering of
the compiled candidate with synthetic, read-only responses. It is not functional
acceptance for progress, payments, network, E2E/browser, PostgreSQL, full-suite,
or historical column workflows.

## Candidate and static evidence

- Build command: `node scripts/build_frontend.cjs`
- Raw build output: [`build4.log`](oracle/build4.log) — exit `0`.
- Static design wiring: [`static-build4.log`](oracle/static-build4.log) — `33/33`, no
  failures. This is the saved raw result from the build4 static check; it
  confirms current `bos_design.css` is embedded before `assets/app.js`.
- Design CSS SHA-256:
  `256f0f2907594db99703098fe68927109fe0a5edef8157457407407b8d8ff499`
- Compiled HTML SHA-256:
  `2f70ce8a27f6372b4e75a4bbcd3ada34ba815f3e44ca1603a9b55160ef321c7a`
- Compiled app SHA-256:
  `bcf12c8b614cb600327c43aa132c58d11b158c83c3bf46c4534cdae87f634f6d`
- Learning content SHA-256:
  `1bce859370537437c157893065af499c9edd0fefea90b30c2f3384b2b04b1390`

## Render evidence

The Playwright harness loads the actual compiled HTML, React and application
bundle from disk through an intercepted `https://bos3.qa` origin. It starts no
server and all non-GET API requests receive in-memory `405`; unknown GET routes
are recorded and fail the run. The secure routed origin only lets the existing
client-side `crypto.subtle` recovery guard execute. It makes no external
connection.

`artifacts-run2` in the original QA staging contains the first successful portion: 12 desktop captures
(three entry cases with hero/handoff/login, runner, ERP sales table and original
InitialImportDialog). The run stopped before CRM because the harness had not
closed the native dialog. Its report has the same build4 hashes, no unknown GET,
no errors and no measured overflow.

`artifacts-run3` in the original QA staging is the reviewed targeted continuation: it first proves the
run2 hashes and diagnostics match build4, then captures only the two missing desktop CRM/HR surfaces
and all 14 mobile surfaces. Its report explicitly records the
reused run2 labels and source hashes.

Together the two directories contain **28 screenshots**:

- 12 reused desktop captures in [`screens`](screens)
- 2 targeted desktop and 14 mobile continuation captures in [`screens`](screens)
- Combined raw diagnostics and continuation lineage:
  [`artifacts-run3/visual-qa-report.json`](artifacts-run3/visual-qa-report.json)

The package relocates the validated screenshots into [`screens`](screens) while
preserving their exact names and bytes. The two raw run reports stay in their
named `artifacts-run*` directories; the original staging directories remain
unchanged outside this evidence package.

Both reports show zero document/main overflow, zero unexpected console errors,
zero page errors and zero unknown GET fixtures. Six guest-entry contexts received
the exact expected synthetic `/api/auth/me/` 401 that leaves the real AuthGate in
the logged-out entry state; that narrowly accounted condition is recorded per
capture and no other errors are suppressed.

The required anchors were present: three entry selectors and lower handoff/login
surfaces, original training runner, non-empty Sales order `SO-OFFLINE-001`, the
actual initial-import form, selected CRM detail/form, and two task cards. The
runner did not submit a form; CRM and task forms were viewed without preview or
write actions.

## Visual review

The entry screens render the light hierarchy, green actions, short case labels,
and selected-card treatment coherently at both widths. Desktop rail, runner,
Sales table, CRM form and task cards remain readable. Mobile changes the global
navigation to the select surface and stacks entry/runner controls without a
measured horizontal overflow. The modal remains centered and usable at 390 px.
The original-resolution ERP mobile capture also shows the complete `Продажі`
header followed by `ERP · Продажі`; no title clipping was found.

## Earlier harness-only outcomes

- [`artifacts/visual-qa-report.json`](artifacts/visual-qa-report.json) preserves the run1 history. It used a pre-build4 candidate and stopped
  at an incomplete synthetic InitialImportDialog snapshot (`data.employees` was
  absent). It is a fixture failure, not product evidence.
- The native-dialog continuation issue in run2 was corrected only in
  `visual-qa.cjs` by using the original dialog's scoped visible `Закрити`
  control and asserting closure before navigation. It did not modify product
  code.
