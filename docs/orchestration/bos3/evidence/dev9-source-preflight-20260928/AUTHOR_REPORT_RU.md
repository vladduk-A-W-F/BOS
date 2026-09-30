# B30 atomic receipt: fail-closed recovery preparation

Статус: `PREPARATION_ONLY_NO_EXECUTION`. Создан отдельный scratch package;
canonical `D:/3/BOSDev/workspaces/bos3-canonical/repo`, protected owner
instance и существующий runtime source не изменялись. Не выполнялись imports,
parser, tests, process/HTTP/app probes, start/stop/kill, ACL, Git mutation,
data/media/secret reads or writes.

## Фактическая исходная точка

Это не повтор window1. Исторически сохранены только следующие факты: failed
dev8 prepared source был D runtime-dev8 на `60f1e31...`; old stop вернул
native exit `0`; saved cleanup зафиксировал PID `55564` с
`stopped_after_start_failure=true`. Последнее не является current liveness
proof. Current availability остаётся `UNCONFIRMED` до отдельного будущего
preflight.

## Future procedure

`recovery_source_prepare_template.py` отказывает ещё до любого owner/runtime
access, пока repaired commit, source digest, version, review и root GO имеют
`PENDING_*`. После final fill его отдельная команда `preflight` остаётся
no-write: проверяет fixed paths, prepared binding к failed D/60f, сохранённый
cleanup outcome, отсутствие process receipt, любых matching server процессов
и listener на `8030`. Любое расхождение, server или occupied port прекращает
операцию без kill.

Только после отдельно сохранённого и reviewed successful preflight команда
`apply` может создать новую recovery evidence directory и заменить ровно
`prepared.source` и `prepared.source_sha256` на immutable repaired D source.
До и после этого она сравнивает aggregate data/media plus owner access/runtime
secret bytes by digest and exact metadata двух residual `process.json.*.tmp`.
Нет init/seed/migrate/reset/rollback/manual ACL/overwrite, capture или stop.

`recovery_official_start_native_exit_template.ps1` предназначен только для
одного будущего official start: он проверяет PENDING gate и recovery apply
receipt, сохраняет raw stdout/stderr и честный native exit/outer timeout
receipt. `recovery_post_start_template.py` отдельно от start и apply делает
ровно один direct loopback HTTP GET, если и только если final pins заполнены;
он печатает receipt с HTTP 200, exact repaired pin/digest и protected/residual
aggregate binding. Его запуск требует отдельной авторизации.

## Risks and boundary

Final repaired immutable candidate отсутствует, поэтому все templates сейчас
обязаны refuse. Preflight cannot reconstruct historical WinError 5 cause and
не заявляет его transient. It also cannot transfer old ready evidence into a
new candidate. Same problem уже `2/3`, window1 start `1/1`; данный package не
сбрасывает счётчики, не authorizes remaining execution и не authorizes a
second window.

## Static repair disposition

Review `afca406381cfea759f20e7fa91fa21e289795ab2e4634e4a9f73e235faeb4371`
found no execution issue, but required three source/evidence bindings. The
template now checks actual failed source clean Git HEAD `60f1e31...` and disk
digest `06a4...`, rather than trusting prepared metadata alone. Its bounded
no-write system observation uses only verified
`%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe` with a
subprocess-local native `PSMODULEPATH`; absence of either refuses with no
ambient fallback.

Future `apply` now requires a direct-child JSON preflight receipt below fixed
scratch `preflight-receipts`, whose exact SHA-256 is another final PENDING pin
and whose complete content must equal a fresh preflight observation. Thus a
separately reviewed historical receipt and current state both bind the apply;
neither one alone is sufficient. The accepted repaired source remains PENDING.

`IMMUTABLE_DEV9_SOURCE_PLAN_RU.md` is a source-only plan for future D dev9
immutable checkout. It uses a full PENDING 40-hex target, treats `81ca067` as
context only, and does not create a checkout or authorize runtime work.

## Post-start P1 repair

Delta review `ff8c31a8e1b788c0418632723116bba39846ec2dab401dc0f46168a74ad6a004`
closed the earlier source/preflight findings but rejected the former minimal
post-start `200` proof. Only `recovery_post_start_template.py` was expanded.
Before any owner-root reads it rejects lexical root/source aliases and validates
the fixed owner root as ordinary/non-reparse. It then requires the saved
official native-exit `0` receipt, exact ready `process.json`, current Windows
process identity, command tokens and the sole loopback listener PID to agree.

The one permitted GET remains exactly one no-proxy/no-redirect request. Its
normalized body must equal the committed repaired source root HTML after the
single `{{ bos_version }}` replacement; expected and served hashes enter the
receipt. The protected algorithm is explicitly the same path-plus-bytes scope
used by recovery preflight/apply: data/media traversal plus owner-access and
runtime-secrets bytes. It must equal failed-window baseline
`dfcbaefab3f5a63e929b49f11d2f5425019834c9bad6e66b0a3e4fd3a938efa1` and the
saved `maintenance-INVOICE-DEV8-D-20260928-window1/started-attestation.json`
receipt before the GET, then be recomputed with residual temp metadata after
that same GET. No second GET, DB query, bootstrap, lifecycle or execution was
introduced.
