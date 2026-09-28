# B30-INVOICE-CURRENCY-INTEGRATION · final incremental integration review

**Reviewer:** `/root/bos3_candidate_review`  
**Режим:** Git/evidence read-only verification; no code edit, test rerun,
import, build, network or runtime action.  
**Вердикт:** `ACCEPT_SCOPED_ATOMIC_INTEGRATION`

Commit `c00c60aad0c4f8e70251da3c7174ed105089198b` has exactly one parent:
`1051ae668ccb17f3c028dc8a586e85c6ed287bf3`. Its exact diff contains only the
four allowlisted paths:

| Path | Final blob, equal to `906...` |
|---|---|
| `erp/experience.py` | `21d330fd9df677255350fa080198ad04476287af` |
| `erp/test_home_projection.py` | `9ccf5c9b58bef8f84652163611d66441c705dfca` |
| `docs/orchestration/bos3/evidence/invoice-currency-20260927/AUTHOR_REPORT_RU.md` | `c905fa8e8a9c5698ca6f550aa8f0807c004fef3a` |
| `docs/orchestration/bos3/evidence/invoice-currency-20260927/MANIFEST.json` | `58b015b3f252e4f003dffce65a58771dc9f19892` |

All four final blob IDs equal their `906f678a4c8f045deb03489f6566af66086e9120`
counterparts. D canonical is clean at `c00...` on
`codex/bos3-prerelease-20260927`.

The earlier accepted guarded QA remains applicable to these identical source
blobs: run1 `2/2`, native exit `0`, attempt `1/3`. It was not rerun. This
acceptance is source integration only; installed runtime remains a separate d8
state and no runtime, database, browser, payment, delivery or readiness claim
is established.
