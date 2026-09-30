param(
    [ValidateSet('init', 'start', 'status', 'stop')][string]$Action,
    [string]$RuntimeRoot = 'D:/3/BOSDev/local-bos3/owner',
    [string]$PythonPath,
    [switch]$InternalLaunch,
    [string]$LaunchSpec
)
$ErrorActionPreference = 'Stop'

if ($InternalLaunch) {
    $decoded = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($LaunchSpec))
    $spec = $decoded | ConvertFrom-Json
    $process = Start-Process -FilePath $spec.python -WorkingDirectory $spec.cwd -ArgumentList $spec.argument_line -RedirectStandardOutput $spec.stdout -RedirectStandardError $spec.stderr -WindowStyle Hidden -PassThru
    [Console]::Out.Write($process.Id)
    exit 0
}

if (-not $PythonPath) {
    $documentedPython = 'D:/3/BOSDev/venv/Scripts/python.exe'
    if (Test-Path -LiteralPath $documentedPython -PathType Leaf) {
        $PythonPath = $documentedPython
    }
}
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw 'Provide an existing interpreter with -PythonPath; no arbitrary PATH Python is selected.'
}
& $PythonPath -X utf8 -B (Join-Path $PSScriptRoot 'bos3_local.py') $Action --root $RuntimeRoot
if ($LASTEXITCODE -ne 0) { throw 'BoS 3.0 local lifecycle command failed; protected state was retained.' }
