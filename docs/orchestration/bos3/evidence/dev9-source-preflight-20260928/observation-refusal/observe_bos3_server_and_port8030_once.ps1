param()

$ErrorActionPreference = 'Stop'
$Workspace = 'D:\3\BOSDev\qa-scratch\bos3-atomic-receipt-recovery-20260928\observation-diagnosis'
$ObservationDirectory = Join-Path $Workspace 'observation1'
$RootObservationGo = 'ROOT_ONE_READ_ONLY_OBSERVATION_20260928'

function Require-RootGo {
    if ($RootObservationGo.StartsWith('PENDING_')) { throw 'ROOT_READ_ONLY_OBSERVATION_GO_PENDING' }
}

function Assert-OrdinaryDirectory([string]$Path, [string]$Boundary) {
    $full = [IO.Path]::GetFullPath($Path)
    $boundaryFull = [IO.Path]::GetFullPath($Boundary)
    if ($full -cne $boundaryFull -and -not $full.StartsWith($boundaryFull + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'PATH_OUTSIDE_FIXED_OBSERVATION_WORKSPACE'
    }
    $cursor = $full
    while ($true) {
        $item = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
        if (-not $item.PSIsContainer -or (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw 'OBSERVATION_PATH_NOT_ORDINARY_DIRECTORY'
        }
        if ($cursor -ceq $boundaryFull) { break }
        $parent = [IO.Directory]::GetParent($cursor)
        if ($null -eq $parent) { throw 'OBSERVATION_BOUNDARY_UNREACHABLE' }
        $cursor = $parent.FullName
    }
}

function Write-CreateNewUtf8([string]$Path, [string]$Value) {
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Value)
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) }
    finally { $stream.Dispose() }
}

Require-RootGo
Assert-OrdinaryDirectory -Path $Workspace -Boundary $Workspace
if (Test-Path -LiteralPath $ObservationDirectory) { throw 'OBSERVATION1_EVIDENCE_ALREADY_EXISTS_NO_RETRY' }
New-Item -ItemType Directory -Path $ObservationDirectory -ErrorAction Stop | Out-Null
Assert-OrdinaryDirectory -Path $ObservationDirectory -Boundary $Workspace

$environment = @{}
Get-ChildItem Env: | ForEach-Object { $environment[$_.Name.ToUpperInvariant()] = $_.Value }
$systemRoot = [IO.Path]::GetFullPath($environment['SYSTEMROOT'])
$nativePowerShell = Join-Path $systemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$nativeModules = Join-Path $systemRoot 'System32\WindowsPowerShell\v1.0\Modules'
if (-not (Test-Path -LiteralPath $nativePowerShell -PathType Leaf) -or -not (Test-Path -LiteralPath $nativeModules -PathType Container)) {
    throw 'NATIVE_POWERSHELL_OR_MODULES_UNAVAILABLE'
}
$environment['PSMODULEPATH'] = $nativeModules

# The child emits no raw command line. It emits matching BoS process identity
# and every listener on 8030 with a Boolean-only BoS command classification.
$child = @'
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
function Identity([object]$Process, [bool]$BoSMatch) {
    [ordered]@{
        pid = [int]$Process.ProcessId
        created_utc = if ($null -eq $Process.CreationDate) { $null } else { $Process.CreationDate.ToUniversalTime().ToString('o') }
        executable_path = [string]$Process.ExecutablePath
        bos_command_match = $BoSMatch
    }
}
$candidates = @(Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%internal-serve%'" -ErrorAction Stop)
$matching = @($candidates | Where-Object {
    $null -ne $_.CommandLine -and $_.CommandLine -like '*bos3*' -and $_.CommandLine -like '*internal-serve*'
} | ForEach-Object { Identity $_ $true })
$listeners = @()
foreach ($listener in @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -eq 8030 })) {
    $process = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + [int]$listener.OwningProcess) -ErrorAction Stop
    $match = $null -ne $process.CommandLine -and $process.CommandLine -like '*bos3*' -and $process.CommandLine -like '*internal-serve*'
    $row = Identity $process $match
    $row.local_address = [string]$listener.LocalAddress
    $row.local_port = [int]$listener.LocalPort
    $listeners += $row
}
[ordered]@{
    schema = 'bos3.recovery.observation/v1'
    matching_bos_servers = $matching
    port8030_listeners = $listeners
    command_lines_recorded = $false
    network_requests = 0
    socket_binds = 0
    lifecycle_actions = 0
} | ConvertTo-Json -Depth 5 -Compress
'@
$encodedChild = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($child))
$psi = [Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $nativePowerShell
$psi.Arguments = '-NoProfile -NonInteractive -EncodedCommand ' + $encodedChild
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
foreach ($key in $environment.Keys) { $psi.EnvironmentVariables[$key] = $environment[$key] }
$childProcess = [Diagnostics.Process]::new()
$childProcess.StartInfo = $psi
if (-not $childProcess.Start()) { throw 'NATIVE_OBSERVATION_CHILD_DID_NOT_START' }
$stdoutTask = $childProcess.StandardOutput.ReadToEndAsync()
$stderrTask = $childProcess.StandardError.ReadToEndAsync()
$receiptPath = Join-Path $ObservationDirectory 'native-observation-receipt.json'
if (-not $childProcess.WaitForExit(30000)) {
    # Do not kill a diagnostic child. Its exit and streams are unknown, and the
    # created observation directory blocks a retry under this one-shot recipe.
    Write-CreateNewUtf8 -Path $receiptPath -Value (([ordered]@{
        schema = 'bos3.recovery.observation-native-exit/v1'
        status = 'CHILD_TIMEOUT_NO_KILL_RAW_STREAMS_UNAVAILABLE'
        child_pid = $childProcess.Id
        child_native_exit = $null
        child_wait_timeout_ms = 30000
        stdout_raw_captured = $false
        stderr_raw_captured = $false
        command_lines_recorded = $false
        maximum_invocations = 1
        diagnostic_only = $true
        cannot_replace_preflight = $true
    }) | ConvertTo-Json -Depth 5)
    exit 3
}
if (-not $stdoutTask.Wait(5000) -or -not $stderrTask.Wait(5000)) {
    Write-CreateNewUtf8 -Path $receiptPath -Value (([ordered]@{
        schema = 'bos3.recovery.observation-native-exit/v1'
        status = 'STREAM_DRAIN_TIMEOUT_AFTER_CHILD_EXIT_RAW_STREAMS_UNAVAILABLE'
        child_pid = $childProcess.Id
        child_native_exit = $childProcess.ExitCode
        stream_drain_timeout_ms = 5000
        stdout_raw_captured = $false
        stderr_raw_captured = $false
        command_lines_recorded = $false
        maximum_invocations = 1
        diagnostic_only = $true
        cannot_replace_preflight = $true
    }) | ConvertTo-Json -Depth 5)
    exit 4
}
$stdout = $stdoutTask.Result
$stderr = $stderrTask.Result
$stdoutPath = Join-Path $ObservationDirectory 'native-child.stdout.raw.txt'
$stderrPath = Join-Path $ObservationDirectory 'native-child.stderr.raw.txt'
Write-CreateNewUtf8 -Path $stdoutPath -Value $stdout
Write-CreateNewUtf8 -Path $stderrPath -Value $stderr
$receipt = [ordered]@{
    schema = 'bos3.recovery.observation-native-exit/v1'
    status = if ($childProcess.ExitCode -eq 0) { 'NATIVE_EXIT_CAPTURED' } else { 'NATIVE_EXIT_NONZERO_CAPTURED' }
    child_native_exit = $childProcess.ExitCode
    native_powershell = $nativePowerShell
    native_modules = $nativeModules
    stdout_raw_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $stdoutPath).Hash.ToLowerInvariant()
    stderr_raw_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $stderrPath).Hash.ToLowerInvariant()
    child_wait_timeout_ms = 30000
    stream_drain_timeout_ms = 5000
    stdout_raw_captured = $true
    stderr_raw_captured = $true
    command_lines_recorded = $false
    maximum_invocations = 1
    diagnostic_only = $true
    cannot_replace_preflight = $true
}
Write-CreateNewUtf8 -Path $receiptPath -Value ($receipt | ConvertTo-Json -Depth 5)
exit $childProcess.ExitCode
