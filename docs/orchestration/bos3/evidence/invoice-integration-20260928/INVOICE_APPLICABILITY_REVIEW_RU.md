# B30-INVOICE-CURRENCY-INTEGRATION · incremental applicability review

**Reviewer:** `/root/bos3_candidate_review`  
**Режим:** Git/evidence read-only review; code edits, tests, imports, builds,
network, runtime actions and C writes were not performed.  
**Вердикт:** `ACCEPT_SCOPED_ATOMIC_FOUR_BLOB_INTEGRATION_APPLICABILITY`

## Сверенные факты

- D canonical is clean at `1051ae668ccb17f3c028dc8a586e85c6ed287bf3` on
  `codex/bos3-prerelease-20260927`.
- `d8e121a0b38bb8c98f5719568b6fa87374e2bfb0` is an ancestor of `1051...`.
- Author code `9f7d50cc39c6d1fdfe19025e1789d54a2176535d` has parent `d8...`;
  final evidence commit `906f678a4c8f045deb03489f6566af66086e9120` has parent
  `9f7...`.
- `erp/experience.py` is unchanged between d8 and D1051: both trees reference
  Git blob `181a45a66071858eb723d3d65e5facf488348b9c`.
- `d8..1051` contains only orchestration/control and prior delivery evidence;
  it contains no `erp/` change and no conflicting invoice-currency path.

## Exact eligible integration set

The final four blobs at `906...` are:

| Path | Git blob |
|---|---|
| `erp/experience.py` | `21d330fd9df677255350fa080198ad04476287af` |
| `erp/test_home_projection.py` | `9ccf5c9b58bef8f84652163611d66441c705dfca` |
| `docs/orchestration/bos3/evidence/invoice-currency-20260927/AUTHOR_REPORT_RU.md` | `c905fa8e8a9c5698ca6f550aa8f0807c004fef3a` |
| `docs/orchestration/bos3/evidence/invoice-currency-20260927/MANIFEST.json` | `58b015b3f252e4f003dffce65a58771dc9f19892` |

This exact set matches the integration card allowlist. It preserves the
accepted guarded QA provenance: run1 `2/2`, native exit `0`, attempt `1/3`,
with no rerun. The D path change alone neither invalidates that source
applicability nor authorizes repeating the test.

## Boundary and next allowed action

Root may apply only these four blobs atomically to D1051 and create one
non-amended integration commit. The next required evidence is an independent
post-integration staged/final blob-equality and control-delta review. This
verdict does not accept runtime, database behavior, payment flows, browser,
delivery, readiness or any extra invoice scope.
