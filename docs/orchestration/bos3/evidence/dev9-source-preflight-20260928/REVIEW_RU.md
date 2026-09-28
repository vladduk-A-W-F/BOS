# Незалежний static review B30-ATOMIC-RECEIPT-RECOVERY-PREP

Дата: 2026-09-28  
Режим: static read-only. Не виконувалися parser/import, Git/process/ACL/HTTP
probes, lifecycle, DB/data/secret actions або tests.

## Перевірені bytes

* `recovery_source_prepare_template.py` —
  `906e00cc02b4ee920aa1524ac2a686915bf7d51012348ce4f9622bdcac789f29`;
* `recovery_official_start_native_exit_template.ps1` —
  `b78739546e0f2d367ee588494c8eccf93de7e90ed752b4b9d8a249039a110aeb`;
* `recovery_post_start_template.py` —
  `846777b89e812fd4b30a5fadf838461ced522311c18c1cfdfa44dfd63282eb9b`;
* `AUTHOR_REPORT_RU.md` —
  `63b4b2022383170cf4a6195ca7e08b4237e64be34f07a5857bcff21a7a661706`;
* `MANIFEST.json` —
  `8ada39e7b6cad19a241f2939593801e80c1493b15c408efab86d0794c8c67f9d`.

## Позитивні межі

Усі три templates мають `PENDING_*` gate перед owner/runtime access. Current
package не викликає capture/stop/kill/ACL/reset/init/seed/migrate або старий
window replay. Future apply обмежений двома `prepared` source fields,
порівнює protected data/media/access/secrets aggregate та exact residual temp
metadata до і після, а post-start відокремлено в один no-proxy/no-redirect
GET. Historical cleanup і current availability не змішані.

## Findings

**P1 — preflight не зв'язує actual failed checkout з D/60f.**

`preflight()` перевіряє лише `prepared.source` і `prepared.source_sha256`
проти constants, але не перевіряє actual `FAILED_SOURCE` через clean Git HEAD
`FAILED_COMMIT` і disk/tree digest `FAILED_SOURCE_SHA256`. Stale prepared
metadata може пройти при зміненому або іншому checkout на тому ж path. Це
суперечить заявленому preflight «from failed D/60f» і послаблює source/evidence
binding до recovery apply.

Мінімальний repair: після PENDING gate та fixed-path comparison додати
read-only `require_failed_source()` з exact HEAD, clean status і digest,
аналогічно repaired-source guard; `preflight`/`apply` мають відмовлятися при
будь-якому розходженні. Це не є runtime action або retry.

**P1 — process/listener preflight використовує ambient `powershell.exe`.**

`require_no_server_or_listener()` запускає `powershell.exe` через PATH без
absolute native executable і без ізольованого `PSMODULEPATH`. Для operation,
яка заявлена як fail-closed system observation, це не закріплює executable та
module catalog; попередня BoS Windows provenance вже показала важливість цього
розмежування. Мінімальний repair: derive/verify
`%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe` і native
`Modules`, передати тільки subprocess-local normalized env з `PSMODULEPATH`.
Помилка має відмовляти preflight, не fallback.

**P2 — declared separately reviewed preflight не має receipt binding у apply.**

Документація каже, що apply можливий після separately saved/reviewed successful
preflight, але `apply()` просто повторно обчислює `preflight()` і не приймає
fixed preflight receipt/hash. Recheck є корисним safety guard, проте не
реалізує заявлений evidence handoff. Або додати required preflight receipt з
exact failed-source/protected/residual fields та hash, або звузити майбутній
procedure до одного fresh apply-integrated preflight без твердження про
окремо reviewed output.

## Verdict

`NOT_READY_STATIC_P1_FAILED_SOURCE_AND_NATIVE_POWERSHELL_BINDING`.

Package чесно не claim-ить historical lock cause або current liveness, але
P1 блокує future preflight/recovery applicability. Жодних executions не
схвалено. Same problem лишається `2/3`, window1 start `1/1`; static repair не
створює додаткової attempt і не дозволяє start, HTTP, recovery або window 2.
