param(
    [Parameter(Mandatory = $true)][ValidateSet('stop', 'start')][string]$Action,
    [Parameter(Mandatory = $true)][string]$ArchiveName
)

$ErrorActionPreference = 'Stop'
$RuntimePython = 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$FromCSource = 'C:\Users\user\.codex\worktrees\bos3-local-runtime\repo'
$ToDSource = 'D:\3\BOSDev\workspaces\bos3-runtime-dev8\repo'
$InstanceRoot = 'D:\3\BOSDev\local-bos3\owner'
$StateRoot = Join-Path $InstanceRoot 'state'
$ExpectedDev8Commit = '60f1e31fca6056711ea52d7aade6b65e0b14afff'
$ExpectedManifestSha256 = '9286497d1aa88177fca6580b1ddcfabcd7345de9bb6eac19b4c7f170d3bacbb2'
$ExpectedFinalReviewSha256 = '9711804f35b04a5a6228fc31bcb84e5316f2ea12ddf77d0470a153482f5a63db'
$ReservedRootGoToken = 'ROOT_DEV8_D_OWNER_LOCAL_20260928_WINDOW1'
$ExpectedRootTechnicalGo = 'ROOT_DEV8_D_OWNER_LOCAL_20260928_WINDOW1'

function Require-FinalPins {
    foreach ($value in @($ExpectedDev8Commit, $ExpectedManifestSha256, $ExpectedFinalReviewSha256, $ExpectedRootTechnicalGo)) {
        if ($value.StartsWith('PENDING_')) { throw 'FINAL_PIN_REVIEW_AND_ROOT_GO_PENDING' }
    }
    if ($ExpectedDev8Commit -notmatch '^[0-9a-f]{40}$' -or $ExpectedManifestSha256 -notmatch '^[0-9a-f]{64}$' -or $ExpectedFinalReviewSha256 -notmatch '^[0-9a-f]{64}$') {
        throw 'FINAL_PIN_FORMAT_INVALID'
    }
}

function Assert-OrdinaryDescendant([string]$Path, [string]$Boundary, [bool]$RequireDirectory) {
    $full = [IO.Path]::GetFullPath($Path)
    $boundaryFull = [IO.Path]::GetFullPath($Boundary)
    if ($full -cne $boundaryFull -and -not $full.StartsWith($boundaryFull + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'PATH_OUTSIDE_FIXED_OWNER_STATE'
    }
    $cursor = $full
    while ($true) {
        $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'REPARSE_PATH_UNSUPPORTED' }
        if ($cursor -ceq $full -and ($RequireDirectory -ne [bool]$item.PSIsContainer)) { throw 'PATH_TYPE_UNEXPECTED' }
        if ($cursor -ceq $boundaryFull) { break }
        $parent = [IO.Directory]::GetParent($cursor)
        if ($null -eq $parent) { throw 'PATH_BOUNDARY_UNREACHABLE' }
        $cursor = $parent.FullName
    }
}

function Write-CreateNewJson([string]$Path, $Value) {
    $json = $Value | ConvertTo-Json -Depth 8
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json)
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) }
    finally { $stream.Dispose() }
}

Require-FinalPins
if ($ArchiveName -notmatch '^maintenance-INVOICE-DEV8-D-[A-Za-z0-9._-]+$') { throw 'ARCHIVE_NAME_INVALID' }
Assert-OrdinaryDescendant -Path $StateRoot -Boundary $StateRoot -RequireDirectory $true
$Archive = Join-Path $StateRoot $ArchiveName
Assert-OrdinaryDescendant -Path $Archive -Boundary $StateRoot -RequireDirectory $true
$RequiredReceipt = Join-Path $Archive $(if ($Action -eq 'stop') { 'started-attestation.json' } else { 'maintenance-receipt.json' })
Assert-OrdinaryDescendant -Path $RequiredReceipt -Boundary $StateRoot -RequireDirectory $false
if (-not (Test-Path -LiteralPath $RuntimePython -PathType Leaf)) { throw 'RUNTIME_PYTHON_MISSING' }
if (-not (Test-Path -LiteralPath $ToDSource -PathType Container)) { throw 'D_RUNTIME_SOURCE_MISSING' }
if (-not (Test-Path -LiteralPath $InstanceRoot -PathType Container)) { throw 'INSTANCE_ROOT_MISSING' }

$stdout = Join-Path $Archive ('official-' + $Action + '.stdout.raw.txt')
$stderr = Join-Path $Archive ('official-' + $Action + '.stderr.raw.txt')
$native = Join-Path $Archive ('official-' + $Action + '.native-exit.json')
if ((Test-Path -LiteralPath $stdout) -or (Test-Path -LiteralPath $stderr) -or (Test-Path -LiteralPath $native)) { throw 'LIFECYCLE_EVIDENCE_ALREADY_EXISTS' }

$source = if ($Action -eq 'stop') { $FromCSource } else { $ToDSource }
$arguments = @('-X', 'utf8', '-B', (Join-Path $source 'scripts\bos3_local.py'), $Action, '--root', $InstanceRoot)
$process = Start-Process -FilePath $RuntimePython -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
if (-not $process.WaitForExit(60000)) {
    Write-CreateNewJson -Path $native -Value ([ordered]@{
        schema = 'bos.invoice-dev8-d.lifecycle-native-exit/v2'; action = $Action; outer_pid = $process.Id
        status = 'OUTER_WRAPPER_TIMEOUT_UNKNOWN'; source = $source; root = $InstanceRoot; archive = $Archive
        expected_dev8_commit = $ExpectedDev8Commit
    })
    exit 3
}
Write-CreateNewJson -Path $native -Value ([ordered]@{
    schema = 'bos.invoice-dev8-d.lifecycle-native-exit/v2'; action = $Action; outer_pid = $process.Id
    status = 'NATIVE_EXIT_CAPTURED'; native_exit = $process.ExitCode; source = $source; root = $InstanceRoot; archive = $Archive
    expected_dev8_commit = $ExpectedDev8Commit; manifest_sha256 = $ExpectedManifestSha256
})
exit $process.ExitCode
