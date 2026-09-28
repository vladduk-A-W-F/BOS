[CmdletBinding()]
param(
    [Parameter(Position=0)][ValidateSet('status','refresh','next','models','handoff')][string]$Action = 'status',
    [string]$Packet,
    [Alias('Home')][string]$ControlHomePath,
    [switch]$Execute
)
$ErrorActionPreference = 'Stop'
$bosPython = 'D:\3\BOSDev\venv\Scripts\python.exe'
$bosFlowScript = Join-Path $PSScriptRoot 'bos_flow.py'
$legacyControlHome = 'C:\Users\user\AppData\Local\BOSDev'
$controlHome = if ([string]::IsNullOrWhiteSpace($ControlHomePath)) { $legacyControlHome } else { $ControlHomePath }
$bosFlowArgs = @('-B', $bosFlowScript, '--home', $controlHome, $Action)
if ($Packet) { $bosFlowArgs += @('--packet', $Packet) }
if ($Execute) { $bosFlowArgs += '--execute' }
& $bosPython @bosFlowArgs
exit $LASTEXITCODE
