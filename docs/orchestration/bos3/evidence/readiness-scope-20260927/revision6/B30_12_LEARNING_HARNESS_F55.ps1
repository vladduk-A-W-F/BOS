# REVIEWED-TO-BE ONLY. Do not run this file until an exact owner exception and
# independent review have approved both the protected bootstrap and one learning run.
[CmdletBinding()]
param(
    [switch]$ExecuteAuthorized,
    [Parameter(Mandatory=$false)][string]$OwnerExceptionId,
    [Parameter(Mandatory=$false)][string]$ApprovedManifest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Immutable e710 execution source with f55 origin pins. This script deliberately contains no password,
# token or owner credential. A protected environment provider supplies secrets
# at execution time; command arguments and artefact logs must never contain them.
$candidate = 'e710eb568717dfe3ede945feb899f030bd5ad1ab'
$originCandidate = 'f55a15de4006d10c0d7c65f8a2ca8499fbb99819'
$runRoot = 'D:\3\BOSDev\qa-runs\b30-12-learning-f55-r1'
$dbPath = Join-Path $runRoot 'data\bos3-fasteners-f55-r1.sqlite3'
$mediaPath = Join-Path $runRoot 'media'
$evidencePath = Join-Path $runRoot 'evidence'
$markerPath = Join-Path $runRoot 'RUN_MANIFEST.json'
$fixtureId = 'bos3-fasteners-uk-v1'

if (-not $ExecuteAuthorized) {
    throw 'PREPARATION_ONLY: no filesystem, database, HTTP, test, browser, migration, seed, or credential action is authorized.'
}
if ([string]::IsNullOrWhiteSpace($OwnerExceptionId) -or -not (Test-Path -LiteralPath $ApprovedManifest -PathType Leaf)) {
    throw 'AUTHORIZATION_MISSING: exact owner exception ID and independently approved manifest are required.'
}

# Future preflight requirements, executed only after explicit authorization:
# 1. Verify source HEAD is e710 and every oracle blob equals its recorded f55
#    origin pin; refuse any other runtime unless a new static applicability
#    review has passed.
# 2. Verify runRoot, dbPath, mediaPath, evidencePath and markerPath are absent;
#    dbPath basename must contain "bos3-fasteners", and dbPath parent is data/.
# 3. Require protected environment values: BOS3_LOCAL_SOURCE, BOS3_LOCAL_ROOT,
#    BOS3_LOCAL_DB, BOS3_LOCAL_MEDIA, BOS3_LOCAL_SECRET,
#    BOS3_TRAINING_ENABLED=1, BOS3_TRAINING_PROFILE=isolated-synthetic,
#    BOS3_TRAINING_DB_MARKER=bos3-fasteners-uk-v1,
#    BOS3_TRAINING_OWNER_USERNAME and BOS3_TRAINING_INSTALLATION_ID.
#    Do not echo the secret or authentication password.
# 4. Bootstrap is its own approved phase: migrate isolated SQLite; create exactly
#    one active named owner; add group ceo; confirm normal protected login and a
#    fresh protected relogin. seed_bos3_fasteners requires that owner and an
#    empty business target; it must run once only.
# 5. Write RUN_MANIFEST.json before any learning mutation with candidate, pins,
#    root/db/media/evidence absolute paths, exception ID, allowlists, and no-retry.
# 6. Derive all business IDs from Configuration['bos3_fixture'].source_map.
#    Execute only the oracle's ordered POST preview/confirm calls: ERP actions
#    through /api/erp/preview/, task/CRM actions through /api/operations/preview/,
#    every confirmation through /api/operations/confirm/.
# 7. Capture redacted raw request/response metadata, proposals, receipts, the
#    completed-step and same-owner relogin state, plus before/after DB/media
#    SHA-256 manifests. Stop at first mismatch and preserve all artefacts.

throw 'HARNESS_REVIEW_GATE: execution implementation is intentionally blocked until the approved manifest and exact bootstrap/run authorization are independently verified.'
