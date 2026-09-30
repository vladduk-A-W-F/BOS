param(
    [ValidateSet('backend','frontend','review')][string]$Lane = 'backend',
    [ValidateSet('doctor','check','migrate','test','frontend-check','sync','status')][string]$Action = 'status',
    [string]$TestLabel,
    [Alias('Home')][string]$ControlHomePath
)
$ErrorActionPreference = 'Stop'
$python = 'D:\3\BOSDev\venv\Scripts\python.exe'
$controlHome = if ([string]::IsNullOrWhiteSpace($ControlHomePath)) { 'C:\Users\user\AppData\Local\BOSDev' } else { $ControlHomePath }
$toolsDir = 'C:\Users\user\AppData\Local\BOSDev\tools'
if ($Action -eq 'status') {
    & $python (Join-Path $toolsDir 'bos_dev.py') --home $controlHome status
    exit $LASTEXITCODE
}
$result = 1
try {
    # Fail closed through the shared resolver before PostgreSQL or lab startup.
    & $python (Join-Path $toolsDir 'bos_dev.py') --home $controlHome status
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($Action -notin @('sync','frontend-check')) {
        & 'D:\3\BOSDev\setup\pg-control.ps1' -Action Start
        . 'D:\3\BOSDev\setup\pg-env.ps1' -Lane $Lane
    }
    $env:BOS_DEV_LANE = $Lane
    $env:PYTHONUTF8 = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:TEMP = 'D:\3\BOSDev\tmp'
    $env:TMP = $env:TEMP
    $env:PYTHONPATH = $toolsDir
    $labArgs = @((Join-Path $toolsDir 'bos_lab.py'), $Action, '--lane', $Lane)
    if ($TestLabel) { $labArgs += @('--label', $TestLabel) }
    & $python @labArgs
    $result = $LASTEXITCODE
}
finally { Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue }
exit $result
