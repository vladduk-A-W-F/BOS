param([ValidateSet('start','stop')][string]$Action = 'start')
$ErrorActionPreference = 'Stop'
$clusterRoot = Join-Path $env:RUNNER_TEMP "bos-pg16-$($env:GITHUB_RUN_ID)-$($env:GITHUB_RUN_ATTEMPT)"
$clusterData = Join-Path $clusterRoot 'data'
$ownerFile = Join-Path $clusterRoot 'owner.json'
$outputRoot = Join-Path $env:RUNNER_TEMP 'bos-ci/windows'
New-Item -ItemType Directory -Force $outputRoot | Out-Null

function Invoke-NativeChecked([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable exit=$LASTEXITCODE" }
}

try {
    if ($Action -eq 'stop') {
        if (Test-Path $ownerFile) {
            $owner = Get-Content $ownerFile -Raw | ConvertFrom-Json
            if ($owner.run_id -ne $env:GITHUB_RUN_ID -or $owner.run_attempt -ne $env:GITHUB_RUN_ATTEMPT) {
                throw 'Cluster ownership does not match current run/attempt'
            }
            # Never stop the system PostgreSQL service; only our private data directory.
            if (Test-Path (Join-Path $clusterData 'postmaster.pid')) {
                Invoke-NativeChecked (Join-Path $owner.bin 'pg_ctl.exe') @('-D',$clusterData,'stop','-m','fast','-w','-t','60')
            }
        }
        exit 0
    }
    if (Test-Path $clusterRoot) { throw 'Refusing to reuse an existing cluster directory' }
    $postgresBin = $env:BOS_PG16_BIN
    if (-not $postgresBin) { $postgresBin = 'C:\Program Files\PostgreSQL\16\bin' }
    $postgresExe = Join-Path $postgresBin 'postgres.exe'
    if (-not (Test-Path $postgresExe)) { throw 'Native PostgreSQL 16 binaries missing; configure BOS_PG16_BIN in P07' }
    $actualVersion = & $postgresExe --version
    if ($LASTEXITCODE -ne 0 -or $actualVersion -notmatch '^postgres \(PostgreSQL\) 16\.') {
        throw "Expected PostgreSQL 16; actual: $actualVersion"
    }
    New-Item -ItemType Directory $clusterRoot | Out-Null
    @{run_id=$env:GITHUB_RUN_ID;run_attempt=$env:GITHUB_RUN_ATTEMPT;bin=$postgresBin} |
        ConvertTo-Json | Set-Content -Encoding utf8 $ownerFile
    $passwordFile = Join-Path $clusterRoot 'synthetic-password.txt'
    Set-Content -Encoding ascii $passwordFile $env:BOS_PGPASSWORD
    try {
        Invoke-NativeChecked (Join-Path $postgresBin 'initdb.exe') @('-D',$clusterData,'-U',$env:BOS_PGUSER,'--encoding=UTF8','--auth=scram-sha-256',"--pwfile=$passwordFile")
    } finally { Remove-Item $passwordFile -ErrorAction SilentlyContinue }
    @"
listen_addresses = '127.0.0.1'
port = 55432
"@ | Add-Content (Join-Path $clusterData 'postgresql.conf')
    Invoke-NativeChecked (Join-Path $postgresBin 'pg_ctl.exe') @('-D',$clusterData,'-l',(Join-Path $outputRoot 'postgres.log'),'start','-w','-t','60')
    @{state='started';version=$actualVersion;port=55432;run_id=$env:GITHUB_RUN_ID;run_attempt=$env:GITHUB_RUN_ATTEMPT} |
        ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $outputRoot 'pg-setup.json')
    exit 0
} catch {
    @{state='not_run';action=$Action;exit_code=1;reason=$_.Exception.Message} |
        ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $outputRoot "pg-$Action-failure.json")
    Write-Error $_ -ErrorAction Continue
    exit 1
}
