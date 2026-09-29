# B30-D control-home operation source: independent archive review

Reviewer `/root/bos3_guard_review_sol`; requested profile `gpt-6-sol/high`, observed runtime model `UNCONFIRMED`. Reviewed canonical base `3e7c33c2b62bad41768e8c6efee57e0f0ff3f84d` on `codex/bos3-prerelease-20260927`. Scope is archive provenance and four current-document changes; the independent source review is reused by its exact pin without repeating model code review.

## Verdict

`ACCEPT_INACTIVE_ARCHIVE_ONLY` for the staged candidate. `SOURCE_COMPLETE=true` denotes static source acceptance at the pinned bytes. `TESTED=false`, `INSTALLED=false`, `MIGRATED=false`; this verdict does not admit execution, installation, migration or product readiness.

## Package and provenance

- `INTEGRATION_CARD.json` SHA-256 `5adb4e7eb2eb0b0788c722fb1bd6b13a0b7b9596f01d5d0b7e39705f3f849fd1`; `package_manifest.json` `b521a1cc89ee5c1998ed7436cf15b9fee208bb5176a7c91502a8010e39090f6b`; archive `README_RU.md` `5a6cbeed30eec21750d27d4f07f740d60e54cff53a493b80e77501f138b45b8b`.
- Final independent source review `SOURCE_FINAL_DELTA_REVIEW_RU.md` SHA-256 `b42bd8e68d0ce31f0abe73a3774092c2bcba285b5344f96b472640dbbeb20256`. It accepts exact installer `c204737e572de6dadf061bbf3d8a29f6a99938b13f78a03f93664d53ae180a9f`, native helper `743836205bb0f00e592f6c2a6c26a8c242370213cfb16ec3bdd8581fe8d71add`, contract `5fc980c404f9ab50633710e950a79168d6db59774a0897cde14e0b3789966d4c`, and source manifest `b1a4bbdfc4e1fd30424d03df9ca77fe902797440ad3ae9a2e63f3090117fd4a8` for static scope only.
- Parsed package manifest lists 28 unique copied paths. All 28 archive files and all 28 corresponding source-scratch files hash to their declared SHA-256; every staged Git blob of those copies matches its archive worktree byte content. The archive has exactly 32 files: those 28 plus `.gitattributes`, README, integration card and package manifest. Staged blobs of all four metadata files also match. No extra archive file or missing manifest path was found.
- Git staged inventory has 36 files, confined to the 32 archive paths plus `CONTROL_STATE.json`, `ACTIVE_WORK_PLAN_RU.md`, `TEAM_CURRENT_RU.md` and `RELEASE_PLAN_RU.md`. `git rev-parse HEAD` matches the integration card base. `git diff --cached --check` exited `0`; `git diff --exit-code` for the four worktree documents exited `0`, confirming no unstaged change to their staged content. The staged archive `.gitattributes` preserves exact source bytes.

## Operational truthfulness

- Current-document pre-terminal SHA-256: `CONTROL_STATE.json` `5ab19d22bb0ab33950ddb9180a41390855449d81d9992b84f0d070b5c159936b`; `ACTIVE_WORK_PLAN_RU.md` `02e11888e83293a00db419075802bea5177e39e8db2c42ebb1791f71e16ebcce`; `TEAM_CURRENT_RU.md` `838386ac51bcf1a330ec06bb679399fc51b1b013dcb6a16f5c49367b80a14ed9`; `RELEASE_PLAN_RU.md` `c67b12de289a229b16dd14e36f2b0e873fba6baa4bfb1676fb71dd2c6e4eca8d`.
- New top records state `SOURCE_COMPLETE_STATIC_NOT_TESTED_NOT_INSTALLED` and identify the accepted review and source hashes. Older R1/R2 assignments and author `MANIFEST.json` pending/`SOURCE_COMPLETE=false` bytes are retained as dated history; README and current records identify the final independent verdict as the current source status. Neither the archive nor the documents claim tested Windows behavior, installation, migration, app delivery or current quiescence.
- Existing focused QA remains `FAIL_SETUP`, attempt `1/1` spent, zero completed test bodies and 21 methods `NOT_RUN`. C64 and other execution caps remain unchanged. The C admin sync is described as an administrative sync, not a D cutover; new global freeze and snapshot are still required. Product/runtime state is not advanced by these document changes.

## Permitted terminal sync and limits

After this verdict, the integration card allows root to add this exact review report to the archive, set `INTEGRATION_CARD.review_status` to accepted, and set the package-review status plus this report's path/SHA in `CONTROL_STATE`. These are terminal metadata updates only; the 28 copied files, QA facts, source verdict, execution limits, readiness and install/migration booleans must not change. Root should recompute affected hashes, verify staged paths, and rerun the scoped diff check after those updates. The future archive commit SHA belongs in the external operational delta after the commit exists.

Only read-only diffs, SHA-256, Git blob comparison, JSON data parsing and inventory checks were performed. No imports, AST/parser/compile/help, tests, installer/native execution, probes, live state/ledger/config reads, process/network/DB actions, commit, push or runtime operation ran in this review. `executions=0`.
