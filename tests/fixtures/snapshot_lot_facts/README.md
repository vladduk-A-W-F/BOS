# Pinned snapshot reader for new regression comparisons

`queries_030103.py` is the exact, immutable pre-change `erp/queries.py` from
runtime source `030103d52fa076317e13bccf15f476ef63c0a3b412735df92ef9ae436337b2e5`.
Its SHA256 is `40dd86d217e2dec7872bfdb85a134acede07d6b2a95ee41ef3f382b03b8ba098`.
CRLF bytes are preserved. This is project code, copied only as a test oracle.

Only `erp/test_snapshot_lot_facts.py` loads this file, under an `erp` package name
so its original relative imports resolve to the same current models/services.
Production does not import it or choose between parallel reader implementations.
Full output equality is checked on a small unchanged synthetic DB/media fixture;
this does not assert an atomic snapshot during concurrent external changes.

No historical test modules or seed commands are imported. The seven new methods
need a dedicated synthetic test database and owned media/temp on D: on Windows.
The runner must set `BOS_FACTS_TEST_ROOT` to that existing owned temp directory.
There are seven tiny lots, two lines and one BOM component in the base fixture.
Physical storage reads are real; spies delegate to the original reader.
