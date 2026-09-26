param([string]$RuntimeRoot = 'D:/3/Codex/2026-09-20/bos-execution/work/continuation-review-demo-20260920')
$ErrorActionPreference = 'Stop'
& "$PSScriptRoot/../../vertical-ua/venv/Scripts/python.exe" -X utf8 -B "$PSScriptRoot/review_control.py" start --runtime-root $RuntimeRoot
if ($LASTEXITCODE -ne 0) { throw 'Review server start failed; see the retained logs.' }
