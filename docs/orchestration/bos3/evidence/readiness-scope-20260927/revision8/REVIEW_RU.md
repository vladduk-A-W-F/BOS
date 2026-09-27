# B30-12 revision8 static delta review

2026-09-27. Independent start_overview_review: REVISE, two narrow findings. Source path, dirty-source rejection, placeholder exception rejection and final-manifest SHA gates are now substantively corrected. C1/C2/C3 per-write numeric, receipt and replay assertions address previous missing checks.

P1: harness line64 calls re.fullmatch but lacks import re; a future execute would fail before setup. P2: oracleline237 retains retired PowerShell -ExecuteAuthorized, while Python requires --execute. Same author assigned only these two corrections plus report/hashes. Existing revision8 exact source remains preserved. No execution/import/compile/test/DB/HTTP; no owner exception question until final static acceptance.

Provenance correction after exact frozen-byte reconciliation: the P1 import statement above was an erroneous static finding, not an observed runtime failure. Frozen revision8 SHA9E6A285F01E39A533E3D19BA9FA40CAC2E91C36171D37AF1BCD1757D18372C46 already contains re in its combined import line. Revision9 only separates that import onto its own line and corrects oracle switch wording. Independent final reviewer confirmed this discrepancy; preserve the original finding as history, retract the missing-import claim. Neither revision was executed.
