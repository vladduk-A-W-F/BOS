param(
    [ValidateSet('full','sqlite','postgres','e2e','ui','windows')][string]$Suite = 'full',
    [string]$Python = 'python',
    [string]$Output = 'evidence/verify/report.json'
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
& $Python (Join-Path $PSScriptRoot 'verify.py') --suite $Suite --output $Output
exit $LASTEXITCODE
