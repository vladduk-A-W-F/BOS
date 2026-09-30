$ErrorActionPreference = 'Stop'
$run = 'D:/3/BOSDev/qa-scratch/bos3-uxd02-delivery-20260927/run1'
$out = Join-Path $run 'wrapper-recovery.json'
if (Test-Path -LiteralPath $out) { throw 'Recovery already recorded; no retry' }
$wrapper = Get-CimInstance Win32_Process -Filter 'ProcessId = 47748'
$receipt = Get-Content -LiteralPath 'D:/3/BOSDev/local-bos3/owner/state/process.json' -Raw | ConvertFrom-Json
$server = Get-CimInstance Win32_Process -Filter 'ProcessId = 50544'
$listener = @(Get-NetTCPConnection -LocalPort 8030 -State Listen)
if ($wrapper.Name -ne 'pwsh.exe' -or $wrapper.CreationDate.ToUniversalTime().ToString('o') -ne '2026-09-27T18:27:39.9227310Z' -or
    $wrapper.ExecutablePath -ne 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe' -or
    -not $wrapper.CommandLine.Contains('bos3-uxd02-delivery-20260927/run1') -or
    -not $wrapper.CommandLine.Contains('-WindowStyle Hidden -Wait -PassThru') -or
    -not $wrapper.CommandLine.Contains('bos3_local.py') -or
    -not $wrapper.CommandLine.Contains("'start','--root'")) { throw 'Wrapper identity mismatch' }
if ($receipt.status -ne 'ready' -or $receipt.process.pid -ne 50544 -or $server.ProcessId -ne 50544 -or
    (Get-Process -Id 50544).StartTime.ToUniversalTime().ToFileTimeUtc() -ne $receipt.process.created_ticks -or
    -not $server.CommandLine.Contains('internal-serve') -or
    $listener.Count -ne 1 -or $listener[0].OwningProcess -ne 50544 -or $listener[0].LocalAddress -ne '127.0.0.1') { throw 'Server identity mismatch' }
$before = [ordered]@{wrapper=$wrapper | Select-Object ProcessId,Name,CreationDate,ExecutablePath,CommandLine;server_pid=50544;server_created_ticks=$receipt.process.created_ticks;listener='127.0.0.1:8030'}
$process = [Diagnostics.Process]::GetProcessById(47748)
if ([long][Math]::Floor($process.StartTime.ToUniversalTime().ToFileTimeUtc() / [decimal]10) -ne [long][Math]::Floor($wrapper.CreationDate.ToUniversalTime().ToFileTimeUtc() / [decimal]10)) { throw 'Wrapper PID reused' }
$process.Kill($false)
if (-not $process.WaitForExit(5000)) { throw 'Wrapper did not exit; no retry' }
$afterServer = Get-CimInstance Win32_Process -Filter 'ProcessId = 50544'
$afterListener = @(Get-NetTCPConnection -LocalPort 8030 -State Listen)
$same = (Get-Process -Id 50544).StartTime.ToUniversalTime().ToFileTimeUtc() -eq $receipt.process.created_ticks -and $afterListener.Count -eq 1 -and $afterListener[0].OwningProcess -eq 50544
[ordered]@{schema=1;at_utc=[DateTime]::UtcNow.ToString('o');before=$before;action='Process.Kill(false) wrapper only';wrapper_exit_code=$process.ExitCode;native_start_exit='UNCONFIRMED_WRAPPER_WAIT';server_identity_preserved=$same;restart_performed=$false;http_requests=0} | ConvertTo-Json -Depth 6 | Out-File -LiteralPath $out -Encoding utf8
if (-not $same) { throw 'Server continuity unconfirmed; no restart authorized by recovery' }
Get-Content -LiteralPath $out -Raw
