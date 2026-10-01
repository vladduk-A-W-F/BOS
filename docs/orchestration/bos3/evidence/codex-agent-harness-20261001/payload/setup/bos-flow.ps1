[CmdletBinding()]
param(
    [Parameter(Position=0)][ValidateSet('status','refresh','next','models','handoff')][string]$Action = 'status',
    [string]$Packet,
    [switch]$Execute
)
$ErrorActionPreference = 'Stop'
$bosPython = 'D:\3\BOSDev\venv\Scripts\python.exe'
$bosFlowScript = Join-Path $PSScriptRoot 'bos_flow.py'
$bosFlowArgs = @('-B', $bosFlowScript, $Action)
if ($Packet) { $bosFlowArgs += @('--packet', $Packet) }
if ($Execute) { $bosFlowArgs += '--execute' }
& $bosPython @bosFlowArgs
exit $LASTEXITCODE
