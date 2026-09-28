# B30 recovery: one native observation diagnostic preparation

Статус: `PREPARATION_ONLY_NO_EXECUTION`. Рецепт предназначен ровно для одного
будущего read-only observation после отдельного решения root. Он не выполнялся
и не является retry preflight или official start.

`observe_bos3_server_and_port8030_once.ps1` сохраняет PENDING root GO до любых
системных reads. После future GO он создаёт единственную `observation1`
evidence directory, отказывается при существующей directory и запускает
только verified native `%SystemRoot%\\System32\\WindowsPowerShell` с
subprocess-local native `PSMODULEPATH`.

Внутренний native command делает только два bounded system observations:
matching BoS `internal-serve` process identities и all port `8030` listeners.
Для каждого выводятся только PID, creation timestamp, executable path и
`bos_command_match`; raw command lines, secrets, owner-instance/DB files,
HTTP, socket bind, app import, tests и lifecycle actions отсутствуют. Parent
не теряет inner failure: child native exit, stdout/stderr raw files и SHA-256
обоих сохраняются CreateNew receipt. Nonzero child exit тоже записывается и
не вызывает automatic retry.

Static correction before any review execution: evidence directory creation
uses supported `New-Item -Path` after preexisting-path refusal and before/after
ordinary no-reparse checks. Child wait is limited to `30000` ms. On timeout
the wrapper does not kill any process, does not wait on asynchronous stream
readers and writes only an honest timeout receipt with the exact owned child
PID and `raw_streams_unavailable`. After a child exit, each stream reader has
at most `5000` ms; a drain timeout likewise writes no raw-output hash and does
not call blocking `GetResult`. The fixed observation1 directory remains the
no-retry marker.

Result never supplies successful preflight/apply input, current readiness,
recovery authorization or attempt reset. Counters remain failed preflight
`1/1`, old window start `1/1`, full problem `2/3`.
