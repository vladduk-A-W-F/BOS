# B30-ATOMIC-DEV9-RUNTIME-SOURCE-PREP-ONCE: независимый pin review

**Reviewer:** `/root/bos3_candidate_review`  
**Режим:** read-only documentary/source-preparation review. Не запускались
clone, checkout, тесты, import, probes, runtime или recovery.

## Сверенные факты

* `aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975` действительно имеет parent
  `6b3aab22b3f8254d5f65846f54ceeed7049e1ddf`; его diff содержит только
  release/control evidence и immutable Dev9 passport, а не новый product code.
* В этом exact commit manifest имеет SHA-256
  `1d39d2b329c5a5cfc6706caecaa99e674e40eb14c795cc82d8547851b5a37d00`.
  `scripts/bos3_local.py` имеет accepted repair SHA-256
  `6483cc03bb7ea8fbf4e15a4b52c881b14ef0d8005cd0b16bafdf6455fa4c79da`.
* `SOURCE_PREPARATION_DECISION.json` ограничивает будущую операцию одним
  shared/no-checkout clone и одним detached checkout, без retry; destination
  отсутствует, C/runtime/protected writes/legacy inventory исключены. Его
  controls явно содержат process-local `GIT_ATTR_NOSYSTEM=1`,
  `core.autocrlf=false`, empty hooks/attributes, выключенные fsmonitor и
  submodule recursion. Receipt scope корректно ограничен source-only facts.

## Finding

### P1: план не привязан к уже принятому immutable target

`IMMUTABLE_DEV9_SOURCE_PLAN_RU.md` в section **Fixed future contract** и
**Future one-shot conditions** всё ещё обозначает target как
`PENDING_REVIEWED_DEV9_IMMUTABLE_40HEX_COMMIT` / "it is `PENDING` now".
Это противоречит decision, где `source_head` и `target_commit` уже равны
`aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975`, и не позволяет independently
prove that the future detached checkout follows the accepted pin rather than
an unspecified later commit.

**Required narrow correction:** replace the pending target wording in the plan
with exact `aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975`, retain the requirement
to verify its type, manifest blob and repair hash immediately before the one
operation, and leave all clone/checkout caps and no-retry controls unchanged.

## Verdict

**REVISE_BEFORE_SOURCE_PREPARATION**

The decision and source-only boundaries are otherwise appropriately limited,
but the stale `PENDING` target text is a material pin ambiguity. This verdict
does not authorize a clone, checkout, recovery procedure, runtime change or
any acceptance claim.
