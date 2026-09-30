# BoS 3.0 dev.8: source-bound packaging note

Candidate passport is prepared for future path
`docs/orchestration/bos3/INVOICE_DEV8_CANDIDATE.json`. Its sole product input is
`411e222c4687b6a029c027518d3f20453c5849db`, tree
`de9357bf9f0555503f1ab58da360ae79629e092f`; installed runtime baseline remains
`d8e121a0b38bb8c98f5719568b6fa87374e2bfb0`.

Against that baseline the exact non-orchestration runtime delta is five paths:
`README.md`, `README_UA.md`, `boss_project/version.py`, `erp/experience.py`,
and `erp/test_home_projection.py`. Other changed paths are orchestration or
evidence and are deliberately not recast as runtime functionality.

Every artifact hash in the passport is `GIT_BLOB_BYTES_SHA256`: SHA-256 over
the exact byte stream returned by Git for `411e222...:<path>`. A checkout file
can differ by line endings or local materialization; neither form proves an
installed server. The passport contains no self-hash and does not guess a
future immutable delivery commit.

The accepted guarded QA is narrow: one run, attempt `1/3`, native exit `0`,
with the pinned `erp/experience.py`, test module and harness. It proves only
invoice-only USD totals and the empty-snapshot EUR fallback in `home(snapshot)`.
It does not prove persistence, payments, HTTP/browser, rights, lessons,
runtime delivery or readiness.

The existing dev.7 `assets/app.js`, PDF and PDF manifest are present at the
same blob hashes cited by the accepted dev.7 passport. They are retained as
unchanged references only: no build, PDF generation, render or browser QA was
repeated for dev.8. `TECHNICAL_READY`, `PILOT_ALLOWED` and `MVP` remain false.
