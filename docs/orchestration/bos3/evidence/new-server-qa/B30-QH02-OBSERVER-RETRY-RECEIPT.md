# B30-QH02 observer capability correction - focused QA

Date: 2026-09-27

## Authorization and exact scope

The first new `training.test_sessions` execution found eight passing methods and
one failing observer method. Static review identified the failure as a test
fixture capability mismatch: the observer had no `operations.view_document`,
so the existing policy correctly hid the fixture's operational documents and
their dependent ERP rows.

Root authorized one correction and one exact-method retry. The test correction
does not change shared ERP policy or add a training bypass. It verifies both:

1. An observer without `view_document` receives unavailable catalog state and
   HTTP 404 before lesson facts or session state are disclosed.
2. After granting the existing `operations.view_document` permission, the same
   observer can start the operational C1 lesson in `read_only`, save an answer,
   and still receives HTTP 403 for an ERP/task preview mutation.

Only this label was executed once:

```text
training.test_sessions.TrainingSessionContractTests.test_ceo_finance_case_and_observer_progress_only
```

No other eight methods were repeated. No browser, server, network, PostgreSQL,
payment, full-suite, E2E, historical progress, or old capped check was run.

## Result

The base and Django test SQLite paths were absent immediately before the run.
The native test exit was captured before log inspection:

```text
NATIVE_EXIT=0
```

Raw result:

```text
Ran 1 test in 0.298s
OK
System check identified no issues (0 silenced).
```

Django created and destroyed the isolated test database. Both the base and
`_django_test` paths were absent after the run; the dedicated media directory
remained.

## Evidence

```text
Raw log: training-attempt-2-qh02.raw.log
SHA-256: E3089E3FF75360B62F805D43A40AD678B3F25FB4FD5B6D3393DA423716F69F87

Native-exit receipt: training-attempt-2-qh02.native-exit.txt
SHA-256: 50ECF457C4DD72B28211F3B189582BDBD20A9966CA052072D330C6008C9682E0
```

This accepts only the corrected observer-capability boundary. It is not an
overall training, CRM, hosting, PostgreSQL, browser, pilot, production, or
release acceptance.
