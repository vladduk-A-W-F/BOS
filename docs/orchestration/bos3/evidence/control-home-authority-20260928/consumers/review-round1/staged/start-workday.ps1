[CmdletBinding()]
param([switch]$NoAppLaunch, [Alias('Home')][string]$ControlHomePath)
$ErrorActionPreference = 'Stop'
# The Startup shortcut targets this existing PowerShell 7 runtime (RemoteSigned).
# Windows PowerShell 5.1 is Restricted on this host; no execution policy is changed.
$powerShellRuntime = 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe'
$python = 'D:\3\BOSDev\venv\Scripts\python.exe'
$coordinator = 'D:\3\BOSDev\control-home\tools\bos_dev.py'
$controlHome = if ([string]::IsNullOrWhiteSpace($ControlHomePath)) { 'D:\3\BOSDev\control-home' } else { $ControlHomePath }
$pgControl = 'D:\3\BOSDev\setup\pg-control.ps1'
$evidenceDirectory = 'D:\3\BOSDev\evidence'
$evidencePath = Join-Path $evidenceDirectory 'startup-last.json'
$mutex = [Threading.Mutex]::new($false, 'Local\BOSDev.StartWorkday')
$ownsMutex = $false
$coordinatorStatusConfirmed = $false
$exitCode = 1
$stage = 'startup_lock'
$report = [ordered]@{
    version = 1
    startedUtc = [DateTime]::UtcNow.ToString('o')
    completedUtc = $null
    ok = $false
    powerShellRuntime = $powerShellRuntime
    noAppLaunch = [bool]$NoAppLaunch
    controlHome = $controlHome
    postgres = $null
    coordinator = $null
    app = $null
    error = $null
    app_error = $null
    evidence_error = $null
}
function Invoke-CoordinatorStatus([string]$SelectedHome) {
    $processInfo = [Diagnostics.ProcessStartInfo]::new()
    $processInfo.FileName = $python
    $processInfo.ArgumentList.Add($coordinator)
    $processInfo.ArgumentList.Add('--home')
    $processInfo.ArgumentList.Add($SelectedHome)
    $processInfo.ArgumentList.Add('status')
    $processInfo.WorkingDirectory = 'D:\3\BOSDev'
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.StandardOutputEncoding = [Text.UTF8Encoding]::new($false)
    $processInfo.StandardErrorEncoding = [Text.UTF8Encoding]::new($false)
    $processInfo.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $processInfo
    try {
        if (!$process.Start()) { throw 'Could not launch the read-only coordinator status command.' }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (!$process.WaitForExit(30000)) {
            $process.Kill()
            throw 'Read-only coordinator status timed out after 30 seconds.'
        }
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw 'Read-only coordinator status returned a failure code.' }
        return ($stdout | ConvertFrom-Json)
    } finally { $process.Dispose() }
}
try {
    try { $ownsMutex = $mutex.WaitOne([TimeSpan]::FromSeconds(50)) }
    catch [Threading.AbandonedMutexException] { $ownsMutex = $true }
    if (!$ownsMutex) { throw 'Another workday startup is still running.' }
    $stage = 'prerequisites'
    foreach ($requiredPath in @($powerShellRuntime, $python, $coordinator, $pgControl)) {
        if (!(Test-Path -LiteralPath $requiredPath -PathType Leaf)) { throw 'A required local runtime or helper is missing.' }
    }
    # The shared Python resolver must refuse unsupported home selection before
    # any PostgreSQL, app, or other startup side effect is considered.
    $stage = 'coordinator_status'
    $coordStatus = Invoke-CoordinatorStatus -SelectedHome $controlHome
    if (!$coordStatus.ok) { throw 'Coordinator status did not confirm success.' }
    $statusCounts = [ordered]@{}
    foreach ($task in @($coordStatus.tasks)) {
        $statusName = [string]$task.status
        if (!$statusCounts.Contains($statusName)) { $statusCounts[$statusName] = 0 }
        $statusCounts[$statusName]++
    }
    $report.coordinator = [ordered]@{
        ok = $true
        taskCount = @($coordStatus.tasks).Count
        staleClaimCount = @($coordStatus.tasks | Where-Object { $_.stale_claim }).Count
        statusCounts = $statusCounts
    }
    $coordinatorStatusConfirmed = $true
    Remove-Variable coordStatus -ErrorAction SilentlyContinue
    $stage = 'postgres_start'
    $startResult = & $pgControl -Action Start
    $stage = 'postgres_status'
    $pgStatus = & $pgControl -Action Status
    if (!$pgStatus.running -or $pgStatus.host -ne '127.0.0.1' -or $pgStatus.port -ne 55432) { throw 'The owned PostgreSQL cluster is not ready.' }
    $report.postgres = [ordered]@{ running=[bool]$pgStatus.running; host=$pgStatus.host; port=$pgStatus.port; data=$pgStatus.data; version=$pgStatus.version }

    $report.ok = $true
    $exitCode = 0
} catch {
    # Do not persist raw child output or arbitrary exception messages.
    $report.error = [ordered]@{ stage=$stage; type=$_.Exception.GetType().FullName; message='Startup failed at the named stage; inspect that local helper.' }
} finally {
    # Keep the single-startup mutex while attempting the independent app stage.
    # A PG/coordinator failure remains the primary error and failed exit status.
    if ($ownsMutex -and $coordinatorStatusConfirmed) {
        $stage = 'app_start'
        try {
            $existingApp = @(Get-Process -Name ChatGPT -ErrorAction SilentlyContinue)
            if ($NoAppLaunch) {
                $report.app = [ordered]@{ action='skipped_by_option'; processCount=$existingApp.Count }
            } elseif ($existingApp.Count -gt 0) {
                $report.app = [ordered]@{ action='already_running'; processCount=$existingApp.Count }
            } else {
                $appId = 'OpenAI.Codex_2p2nqsd0c76g0!App'
                $registeredApp = Get-StartApps | Where-Object { $_.AppID -eq $appId }
                if (!$registeredApp) { throw 'The verified Codex application ID is no longer registered.' }
                Start-Process -FilePath (Join-Path $env:WINDIR 'explorer.exe') -ArgumentList ('shell:AppsFolder\' + $appId) -WindowStyle Hidden | Out-Null
                # Shell activation is asynchronous; GUI readiness is separate.
                $report.app = [ordered]@{ action='launch_requested'; appId=$appId }
            }
        } catch {
            $report.app_error = [ordered]@{ stage='app_start'; type=$_.Exception.GetType().FullName; message='Codex app startup failed; inspect registration or process availability.' }
            if ($null -eq $report.error) { $report.error = $report.app_error }
            $report.ok = $false
            $exitCode = 1
        }
    } elseif ($ownsMutex) {
        # A selected-home refusal must suppress app launch, while a later PG
        # failure after confirmed coordinator status preserves legacy app flow.
        $report.app = [ordered]@{ action='skipped_coordinator_status_not_confirmed' }
    }
    $report.completedUtc = [DateTime]::UtcNow.ToString('o')
    if ($coordinatorStatusConfirmed) { try {
        New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null
        $temporaryEvidence = Join-Path $evidenceDirectory ('startup-last.' + $PID + '.tmp')
        $json = $report | ConvertTo-Json -Depth 8
        [IO.File]::WriteAllText($temporaryEvidence, $json + "`r`n", [Text.UTF8Encoding]::new($false))
        # This script is launched with the verified PowerShell 7 runtime.
        # The overwrite overload performs a rename on the same filesystem.
        [IO.File]::Move($temporaryEvidence, $evidencePath, $true)
    } catch {
        $exitCode = 1
        $report.ok = $false
        $report.evidence_error = [ordered]@{ stage='evidence_write'; type=$_.Exception.GetType().FullName; message='Could not persist the startup evidence file.' }
        if ($null -eq $report.error) { $report.error = $report.evidence_error }
        [Console]::Error.WriteLine('Could not persist BOS startup evidence.')
    } }
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
$report | ConvertTo-Json -Depth 8
exit $exitCode
