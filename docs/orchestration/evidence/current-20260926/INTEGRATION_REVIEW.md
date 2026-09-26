# FINAL-CURRENT-20260926: integration record

Owner instruction: consolidate the latest version and commit histories into main, improve column text, and freeze the resulting current baseline. GitHub issue #5 is a finalization instruction, not a pull request. Production activation and historical test-attempt limits remain excluded.

## History integration

| Commit | Parents | Scope | Independent review |
|---|---|---|---|
| 0cb8fdb36de69f30b74708d9f50a03e1dbfcc769 | a3c0596ab611290ba5ad199f55309812093f908b, abb8845f6563bafa806029ddc1e7c2cace09907c | Network genealogy, missing evidence and branch-restricted CI; retain newer v17 runtime | plan_review: ACCEPT_SCOPED |
| 49adfceb6fbbe234103ce065741d4acd778e4fc8 | 0cb8fdb36de69f30b74708d9f50a03e1dbfcc769, ce7f82995c90ca49a40004b75e77df13ada3ad3c, a1564c1dbdb86aabbab81a5900c36d97addf404d | Main/tracking/daily-review history and 15 source files | plan_review: ACCEPT_SCOPED |

First merge conflict resolution deliberately retained v17 for assets/app.js, boss_project/policy.py, erp/{migrations/0006_network_operations.py,models.py,network.py,queries.py,service.py,urls.py}, frontend/{boss_app_html.html,boss_app_source.html}, operations/projections.py, and current orchestration PLAN/QUEUE/STATE. No runtime change remained. Of 102 imported paths, 101 matched the network source blobs exactly; DECISIONS combined both dated histories. An extra trailing blank line was removed before the final whitespace check (exit 0).

The second merge retained the source STATE blob b020b0a1ef358bc867243be87a66db13832a9c4d and existing main workflow blob 01502b13e19cf0e0a38e7168405fc4a28e65338e. Standard whitespace check returned exit 2 on three CRLF lines. The command-local check `git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol diff --cached --check` returned exit 0. No persistent Git setting or historical source bytes were changed to conceal this difference.

After both merges, each of the 100 SHAs in consolidation-20260926/INVENTORY.json, plus plan commit a3c0596, passed `git merge-base --is-ancestor <sha> HEAD`. This proves genealogy, not independent acceptance of every historical feature. No source branch was force-pushed, rewritten, deleted or separately merged back into an older runtime.

## CI boundary

The retained main workflow blank.yml only performs checkout and echo. It is not a product-test gate. The imported network workflow only accepts pushes to the historical network branch with its own ref/token/attempt guards. Other bounded workflows remain restricted to their original refs or manual dispatch. No manual workflow dispatch or exhausted suite retry is authorized by this integration.

## Product review boundary

UI-COLUMN-CONTENT-01 is separately implemented by columns_implementation in an isolated checkout, checked by columns_qa and reviewed by plan_review. The first new focused-check failure and subsequent corrections are retained in columns evidence. A review finding required keeping different semantic fields even when their displayed strings match. Only repetition of the heading field itself may be omitted.

Historical evidence files retain their original candidate identity and limits. A main merge, snapshot tag or successful frontend build does not change TECHNICAL_READY=false, PILOT_ALLOWED=false or MVP=false.

## Inherited lexical diagnostic

QA ran check_frontend.cjs once and recorded exit 1 for unresolved getComputedStyle. Independent reviewer traced the unchanged call at frontend/boss_app_source.html:754 to commit 37fb57ff. It is present in product 207c742, plan a3c0596 and the current candidate. The checker global allowlist at scripts/check_frontend.cjs:6 omits that name; its blob is unchanged across those versions (ad10d371dfdad327f493eb54085430f2e2ec0004). This static provenance check is not an additional baseline test run. The diagnostic remains FAIL_LEGACY_LEXICAL_CHECK; no checker relaxation or product edit was used to manufacture a pass.
