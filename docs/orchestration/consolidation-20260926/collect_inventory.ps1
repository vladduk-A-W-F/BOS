param([string]$Repository = (Resolve-Path "$PSScriptRoot/../../..").Path)
$ErrorActionPreference = 'Stop'
function Read-Git {
    param([string[]]$GitArguments)
    $result = @(& git -C $Repository @GitArguments)
    if ($LASTEXITCODE -ne 0) { throw "git failed: $GitArguments" }
    return $result
}
$base = 'c4a68d494a91d3bc9ac5259f6a7b351e5cf6efb0'
$remoteLines = Read-Git @('ls-remote', '--heads', '--tags', 'origin')
$refs = @($remoteLines | ForEach-Object {
    $fields = $_ -split '\s+', 2
    [ordered]@{ sha = $fields[0]; ref = $fields[1] }
})
$sourceRefs = @($refs | Where-Object { $_.ref -notlike 'refs/heads/codex/bos-consolidation-*' })
$tips = @($sourceRefs | ForEach-Object { $_.sha } | Select-Object -Unique)
$raw = Read-Git (@('log', '--topo-order', '--format=%H%x09%P%x09%aI%x09%s') + $tips)
$commits = @($raw | ForEach-Object {
    $fields = $_ -split "`t", 4
    [ordered]@{ sha=$fields[0]; parents=@($fields[1] -split ' ' | Where-Object { $_ }); authored_at=$fields[2]; subject=$fields[3] }
})
$comparisons = @($sourceRefs | ForEach-Object {
    $tip = $_.sha
    $counts = (Read-Git @('rev-list', '--left-right', '--count', "$base...$tip")) -split '\s+'
    [ordered]@{ ref=$_.ref; sha=$tip; merge_base=[string](Read-Git @('merge-base', $base, $tip)); base_only=[int]$counts[0]; source_only=[int]$counts[1]; source_unique_commits=@(Read-Git @('rev-list', '--reverse', "$base..$tip")) }
})
$inventory = [ordered]@{
    schema='bos.consolidation.inventory.v1'; observed_at_utc=[DateTime]::UtcNow.ToString('o')
    repository='vladduk-A-W-F/BOS'; base=$base; product='207c7426bcd057cc1a5cfcf172d4c040b05221e9'
    scope='All commits reachable from the observed remote source heads and tags; local uncommitted files and separate Sites repository excluded.'
    remote_refs=$refs; comparisons=$comparisons; commit_count=$commits.Count; commits=$commits
    technical_ready=$false; pilot_allowed=$false; mvp=$false
}
$json = ($inventory | ConvertTo-Json -Depth 10).Replace("`r`n", "`n") + "`n"
[IO.File]::WriteAllText("$PSScriptRoot/INVENTORY.json", $json, [Text.UTF8Encoding]::new($false))
$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('# BoS: complete observed remote commit ledger')
$lines.Add('')
$lines.Add("Snapshot UTC: $($inventory.observed_at_utc). Commits: $($commits.Count).")
$lines.Add('')
$lines.Add('This is a provenance ledger, not a statement that every branch change is integrated or accepted. Local private patches and the separate Sites history require separate admission. The plan-only commit containing this ledger is identified by its enclosing Git commit and PR.')
$lines.Add('')
$lines.Add('| SHA | Date | Subject |')
$lines.Add('|---|---|---|')
foreach ($commit in $commits) {
    $subject = $commit.subject.Replace('|', '\|')
    $lines.Add("| [$($commit.sha)](https://github.com/vladduk-A-W-F/BOS/commit/$($commit.sha)) | $($commit.authored_at) | $subject |")
}
[IO.File]::WriteAllText("$PSScriptRoot/COMMITS.md", ($lines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
Write-Output "PASS inventory: $($refs.Count) refs, $($commits.Count) commits"
Write-Output ($comparisons | ConvertTo-Json -Depth 5)
