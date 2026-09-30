# B30 training focused QA - attempt 1

Date: 2026-09-27

## Scope and isolation

This was the first execution of the new training/CRM candidate test card. The
only executed label was:

```text
training.test_sessions
```

It used the validation checkout at base commit
`a445ac0584c79c2939269b37ec814b22691711c7` plus the uncommitted candidate
files identified below. No browser, network, local server, PostgreSQL, payment,
full-suite, E2E, historical progress, or old capped test was run.

Before setup, the parent, base SQLite path, Django `_django_test` path and
media directory were all absent. The only setup created:

```text
D:\3\BOSDev\qa-scratch\bos3-training-20260927
D:\3\BOSDev\qa-scratch\bos3-training-20260927\media
```

Environment:

```text
DJANGO_SETTINGS_MODULE=verification_settings
BOS_VERIFY_DB=sqlite
BOS_TEST_DB_NAME=D:\3\BOSDev\qa-scratch\bos3-training-20260927\bos3-fasteners-training-qa.sqlite3
BOS_TEST_MEDIA=D:\3\BOSDev\qa-scratch\bos3-training-20260927\media
PYTHONDONTWRITEBYTECODE=1
BOS_DATA_MODE=demo
```

Interpreter:

```text
D:\3\BOSDev\venv\Scripts\python.exe
```

## Result

Native exit was captured immediately after the test process, before inspecting
the log:

```text
NATIVE_EXIT=1
```

Django found nine tests. Eight passed; one failed:

```text
FAIL: test_ceo_finance_case_and_observer_progress_only
training.test_sessions.TrainingSessionContractTests
```

The test changes the fixture owner from `ceo` to `observer`, then expects the
read-only lesson start to succeed. The request instead returned HTTP 404:

```text
POST /api/training/sessions/BOS3-CASE-01/start/
{"error":"Запис не знайдено в поточній базі."}
```

The raw traceback identifies the test expectation at
`training/test_sessions.py:131`. Static source review ties the failure to
`training/service.py:42-50`: training `sources()` resolves marker-bound ERP
references through `policy.queryset(...)`. The observer's ordinary ERP scope
does not contain those records, so the intended read-only lesson cannot start.

This is a product/test failure, not infrastructure. No automatic retry was
performed. The required product decision/fix must preserve ordinary policy
boundaries while giving an observer only the sealed synthetic marker references
needed for the lesson, or else revise the accepted observer lesson contract.

The isolated Django test database was destroyed after the run. Both its base
and `_django_test` paths were absent when checked after execution; the empty
dedicated media directory remains.

## Evidence

```text
Raw log: training-attempt-1.raw.log
SHA-256: DAC1B7ED05B6E3FF2C015A92BC751F48D346CD42B691EFCED11B0FF5ED3642C4

Native-exit receipt: training-attempt-1.native-exit.txt
SHA-256: ED99E2E25075B2E604284BB280498EECF8FCF24193CE73838CF24FC56BE53C97
```

## Candidate source hashes

```text
training/test_sessions.py
04D3CD0E1860A13E63FFFB855C7D8A1D914DF0CF66ED17859F9B5A1E7554CD7F

training/access.py
C1D12118B65543D5EB5EF46F84C7457F57127410E8C7CBA825434C7D45D44A6B

training/service.py
89E07D6CE2F603A7316D1EE1D4E59211E23871048FE898948A9DB29D0A69BEA5

training/views.py
F91391B5C1549800BAA2CE38ECDB7BFA4089017A8F9F47FB383B85F66BA6A466

training/models.py
CC7CF39BDADA46D73A87DC39E18DA3A81336C1EA3881C588DBFBDF227B78383A

boss_project/policy.py
E6D3EA97F11491701096FE001F16C13B1FF56453DFAD3D92DAE2E1047D38EFC1

operations/service.py
73F865CF65914F585FB5F4ECCB9706FDB56C1B20A55545F4DFE047DEADCCB223

erp/management/commands/seed_bos3_fasteners.py
53527FF4C18226957B8C55ED1EB86C0A4C6268300DC8B9DD03C9F2CC6093BF32

erp/seed/bos3_fasteners_uk_v1.json
7BFC91274B26D3D3EA9ADBA51C1A6CC8433AFDE7DCA29A3B7CEC8460081973BA

crm/models.py
0AA48179015824CF558EF213E4D6C98D2C239386776978AADCF30A07CA8D9475

crm/commands.py
7BAC2EE56CE74A1C3763F55F08CB103F69F42D206E1F47934291E26D9ACACB37

crm/projections.py
5E5BA574D0FC9A6A1C35EBB1A69EA58FC032BAEF45F8D6B91B4DD5803D3A198A

verification_settings.py
35D8C2EA87B9EC7F4C871D3D17F606BA5C82B004B39B5F563692AE1E81A46EDA
```
