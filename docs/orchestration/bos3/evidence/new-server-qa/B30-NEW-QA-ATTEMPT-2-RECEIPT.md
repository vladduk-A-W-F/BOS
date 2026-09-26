# B30 new focused QA - attempt 2

Date: 2026-09-27

## Authorization and scope

This is the second of at most three attempts for the new B30 fixture/CRM QA
card. The first attempt stopped before migrations/tests because the requested
isolated parent directory did not exist. Root explicitly authorized this one
retry after a filesystem-only preflight.

Only the following labels were executed once:

```text
erp.test_bos3_fasteners_seed crm.test_contract
```

No browser, network, server, PostgreSQL, payment, full-suite, E2E, historical
progress, or training test was run.

## Isolation preflight

Before the run, the parent directory, base SQLite path, Django test-database
path, and media directory were absent. The permitted setup created only:

```text
D:\3\BOSDev\qa-scratch\bos3-new-20260927
D:\3\BOSDev\qa-scratch\bos3-new-20260927\media
```

Environment:

```text
DJANGO_SETTINGS_MODULE=verification_settings
BOS_VERIFY_DB=sqlite
BOS_TEST_DB_NAME=D:\3\BOSDev\qa-scratch\bos3-new-20260927\bos3-fasteners-qa.sqlite3
BOS_TEST_MEDIA=D:\3\BOSDev\qa-scratch\bos3-new-20260927\media
PYTHONDONTWRITEBYTECODE=1
BOS_DATA_MODE=demo
```

Interpreter:

```text
D:\3\BOSDev\venv\Scripts\python.exe
```

Validation checkout HEAD: `a445ac0584c79c2939269b37ec814b22691711c7`.
The checkout also contained the reviewed, uncommitted BoS 3.0 candidate files;
this receipt identifies the precise files hashed below rather than claiming a
committed integrated candidate.

## Observed test result

The raw log records Django creating and then destroying the isolated
`bos3-fasteners-qa.sqlite3_django_test` database, applying migrations including
`training.0001_initial` and `crm.0001_initial`, finding seven tests, and all
seven completing `ok`:

```text
Ran 7 tests in 2.068s
OK
System check identified no issues (0 silenced).
```

After the native test process had completed, the PowerShell receipt wrapper
failed while trying to append `NATIVE_EXIT` with an incompatible `Tee-Object`
parameter combination. Therefore the raw log is valid evidence of the observed
Django `OK` result, but it does **not** contain a separately captured native
process exit code. No rerun is authorized merely to repair that receipt field.

The raw log SHA-256 is:

```text
D30E8004E74DF65528C5DEC2074490BF7B90F7273D71C4ED6951CDBA89A38524
```

Raw log: `attempt-2.raw.log`.

## Source hashes used by the focused test

```text
erp/seed/bos3_fasteners_uk_v1.json
7BFC91274B26D3D3EA9ADBA51C1A6CC8433AFDE7DCA29A3B7CEC8460081973BA

erp/management/commands/seed_bos3_fasteners.py
53527FF4C18226957B8C55ED1EB86C0A4C6268300DC8B9DD03C9F2CC6093BF32

erp/test_bos3_fasteners_seed.py
CF73F424DD3D6DF82ADC88251D4AB977FA8AD90B26A169FA84211BC2E579184B

crm/test_contract.py
B9BECA9C53EE372505FA9C5247FB9CB3EEA7E1AC9B0D38C582E84AF1BF2C8CE1

crm/models.py
0AA48179015824CF558EF213E4D6C98D2C239386776978AADCF30A07CA8D9475

crm/views.py
76FB8D160BD27C5E7B26C4E70A44FE423EA699B1EF3B9A9C9FF757AE9F54F1B9

crm/urls.py
19CA5DCDE740EE2377BE4840C43D34FBF1709C4A16580D8F7C1CC8044685585B

training/access.py
76CCE4233549361B89E28EEF7AA060A65A39B6BD599BAF335339D43E8DD0045B

verification_settings.py
35D8C2EA87B9EC7F4C871D3D17F606BA5C82B004B39B5F563692AE1E81A46EDA
```

## Post-run state

After the run, neither the base SQLite path nor the `_django_test` path
existed. The empty dedicated media directory remained. This focused result is
not evidence of PostgreSQL behavior, browser workflow, public hosting, or
overall technical/pilot/product readiness.
