param(
    [Parameter(Mandatory = $true)][string]$RecoveryName
)

$ErrorActionPreference = 'Stop'
$RuntimePython = 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$RepairedSource = 'D:\3\BOSDev\workspaces\bos3-runtime-dev9\repo'
$InstanceRoot = 'D:\3\BOSDev\local-bos3\owner'
$StateRoot = Join-Path $InstanceRoot 'state'
$ExpectedCommit = 'aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975'
$ExpectedDigest = 'e7046ad6e0374d36de33716ffa0152e31330dbf82fab3e24184bf3d573abebe0'
$ExpectedRootGo = 'ROOT_ATOMIC_DEV9_RECOVERY_20260928_ONCE'

function Require-FinalPins {
    foreach ($value in @($ExpectedCommit, $ExpectedDigest, $ExpectedRootGo)) {
        if ($value.StartsWith('PENDING_')) { throw 'FINAL_REPAIRED_PIN_REVIEW_AND_ROOT_GO_PENDING' }
    }
    if ($ExpectedCommit -notmatch '^[0-9a-f]{40}$' -or $ExpectedDigest -notmatch '^[0-9a-f]{64}$') {
        throw 'FINAL_REPAIRED_PIN_FORMAT_INVALID'
    }
}

function Assert-OrdinaryUnderState([string]$Path, [bool]$Directory) {
    $full = [IO.Path]::GetFullPath($Path)
    $state = [IO.Path]::GetFullPath($StateRoot)
    if ($full -cne $state -and -not $full.StartsWith($state + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'PATH_OUTSIDE_FIXED_STATE'
    }
    $cursor = $full
    while ($true) {
        $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'REPARSE_PATH_UNSUPPORTED' }
        if ($cursor -ceq $full -and ($Directory -ne [bool]$item.PSIsContainer)) { throw 'PATH_TYPE_UNEXPECTED' }
        if ($cursor -ceq $state) { break }
        $parent = [IO.Directory]::GetParent($cursor)
        if ($null -eq $parent) { throw 'STATE_BOUNDARY_UNREACHABLE' }
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
if ($RecoveryName -notmatch '^recovery-INVOICE-DEV8-ATOMIC-[A-Za-z0-9._-]+$') { throw 'RECOVERY_NAME_INVALID' }
$RecoveryDir = Join-Path $StateRoot $RecoveryName
Assert-OrdinaryUnderState -Path $RecoveryDir -Directory $true
$ApplyReceipt = Join-Path $RecoveryDir 'recovery-apply-receipt.json'
Assert-OrdinaryUnderState -Path $ApplyReceipt -Directory $false
$Receipt = Get-Content -LiteralPath $ApplyReceipt -Raw -Encoding utf8 | ConvertFrom-Json
if ($Receipt.repaired_commit -cne $ExpectedCommit -or $Receipt.repaired_source_sha256 -cne $ExpectedDigest -or
    $Receipt.root_recovery_go -cne $ExpectedRootGo -or $Receipt.protected_payload_unchanged -ne $true -or
    $Receipt.residual_temp_evidence_unchanged -ne $true) { throw 'RECOVERY_APPLY_RECEIPT_MISMATCH' }
if (-not (Test-Path -LiteralPath $RuntimePython -PathType Leaf) -or -not (Test-Path -LiteralPath $RepairedSource -PathType Container)) {
    throw 'RUNTIME_OR_REPAIRED_SOURCE_MISSING'
}

$stdout = Join-Path $RecoveryDir 'official-start.stdout.raw.txt'
$stderr = Join-Path $RecoveryDir 'official-start.stderr.raw.txt'
$native = Join-Path $RecoveryDir 'official-start.native-exit.json'
if ((Test-Path -LiteralPath $stdout) -or (Test-Path -LiteralPath $stderr) -or (Test-Path -LiteralPath $native)) {
    throw 'OFFICIAL_START_EVIDENCE_ALREADY_EXISTS'
}

$arguments = @('-X', 'utf8', '-B', (Join-Path $RepairedSource 'scripts\bos3_local.py'), 'start', '--root', $InstanceRoot)
$process = Start-Process -FilePath $RuntimePython -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
if (-not $process.WaitForExit(60000)) {
    Write-CreateNewJson -Path $native -Value ([ordered]@{ schema = 'bos3.atomic-receipt-recovery.native-exit/v1'; action = 'start'; outer_pid = $process.Id
        status = 'OUTER_WRAPPER_TIMEOUT_UNKNOWN'; source = $RepairedSource; root = $InstanceRoot; recovery = $RecoveryDir
        expected_commit = $ExpectedCommit; expected_source_sha256 = $ExpectedDigest })
    exit 3
}
Write-CreateNewJson -Path $native -Value ([ordered]@{ schema = 'bos3.atomic-receipt-recovery.native-exit/v1'; action = 'start'; outer_pid = $process.Id
    status = 'NATIVE_EXIT_CAPTURED'; native_exit = $process.ExitCode; source = $RepairedSource; root = $InstanceRoot; recovery = $RecoveryDir
    expected_commit = $ExpectedCommit; expected_source_sha256 = $ExpectedDigest })
exit $process.ExitCode
