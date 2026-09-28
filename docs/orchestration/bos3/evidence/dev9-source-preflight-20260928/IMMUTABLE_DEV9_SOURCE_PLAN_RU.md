# Source-only plan: future immutable D dev9 checkout

Статус: `EXACT_PIN_BOUND_PENDING_INDEPENDENT_DELTA_REVIEW`. Это отдельная source preparation
от recovery/runtime window. Root закрепил final target
`aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975` по SOURCE_PREPARATION_DECISION.json;
исторический context `81ca067` не является checkout target. Исполнение допускается
только после независимой проверки этой точной привязки и предоперационных guards.

## Fixed future contract

* source: `D:/3/BOSDev/workspaces/bos3-canonical/repo`;
* destination: `D:/3/BOSDev/workspaces/bos3-runtime-dev9/repo`;
* target: `aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975`, containing accepted
  dev9 manifest SHA256 `1d39d2b329c5a5cfc6706caecaa99e674e40eb14c795cc82d8547851b5a37d00`
  and atomic repair source SHA256 `6483cc03bb7ea8fbf4e15a4b52c881b14ef0d8005cd0b16bafdf6455fa4c79da`;
* maximum: one clone and one detached checkout; no retry, force, reset, move,
  delete, runtime action or protected owner write.

## Future one-shot conditions

Before any command, root must record canonical clean HEAD and approved branch;
verify the target object type is `commit`, the exact manifest blob hash and
the repair source pin. Destination must be absent. Every existing source,
destination-parent and controls component must be ordinary and non-reparse.

Only after final pin review, use the previously reviewed source-only method:
one `git clone --shared --no-checkout --origin source-local` with the exact
empty hooks template, empty attributes control, process-local D TEMP/TMP/cache
and `GIT_ATTR_NOSYSTEM=1`; then one `git checkout --detach TARGET_COMMIT`.
Set `core.autocrlf=false`, fixed hooks/attributes paths, `core.fsmonitor=false`
and `submodule.recurse=false`. No legacy C worktree, old runtime checkout,
owner instance or all16 inventory is touched.

The receipt must capture native argv/exits/raw stream hashes, resolved ordinary
paths, detached HEAD, clean porcelain, source-local URL, alternates bytes/SHA,
control-path facts and declared Git-blob versus LF-disk proof for the reviewed
manifest and declared changed files. It must state the shared-object dependency
on D canonical objects; it is not a standalone backup claim.

No clone or checkout was executed while preparing this plan.
