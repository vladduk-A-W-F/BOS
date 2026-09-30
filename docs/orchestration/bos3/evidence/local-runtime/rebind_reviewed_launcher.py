"""One-time reviewed, stopped-instance launcher maintenance; never seeds data."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

SOURCE = Path('C:/Users/user/.codex/worktrees/bos3-local-runtime/repo')
ROOT = Path('D:/3/BOSDev/local-bos3/owner')
OLD_PREFIX = 'c1b6d67'
OLD_DIGEST = '8da11c5c2b381341f37fa64d4cae1d81c71c420ab1f93a5ab07d13c23c59c0d2'
NEW_SHA = '33d7d387aa582c04339a91ae94361948ea67904c'
sys.path.insert(0, str(SOURCE))
from scripts.bos3_local import atomic_json, digest_source, native_windows_powershell_environment


def git(*args):
    return subprocess.check_output(['git', '-C', str(SOURCE), *args], text=True).strip()


def data_hashes():
    files = list((ROOT / 'data').rglob('*')) + list((ROOT / 'media').rglob('*'))
    files += [ROOT / 'state' / name for name in ('owner-access.json', 'runtime-secrets.json')]
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files if path.is_file()}


old_sha = git('rev-parse', 'HEAD')
assert old_sha.startswith(OLD_PREFIX) and not git('status', '--porcelain')
assert git('diff', '--name-only', old_sha, NEW_SHA).splitlines() == [
    'docs/learning/BOS3_LOCAL_SERVER.md', 'scripts/bos3_local.py']
prepared_path = ROOT / 'state' / 'prepared.json'
process_path = ROOT / 'state' / 'process.json'
prepared = json.loads(prepared_path.read_text(encoding='utf-8'))
process = json.loads(process_path.read_text(encoding='utf-8'))
assert prepared['source'] == str(SOURCE) and prepared['source_sha256'] == OLD_DIGEST
assert digest_source(SOURCE) == OLD_DIGEST
assert process['status'] == 'start_failed' and process['process'] is None
assert prepared['port'] == 8030 and prepared.get('initialized_at')

powershell, env = native_windows_powershell_environment()
env['BOS3_MAINTENANCE_SOURCE'] = str(SOURCE)
probe = r'''
$ErrorActionPreference = 'Stop'
$processes = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like ('*' + $env:BOS3_MAINTENANCE_SOURCE + '*internal-serve*') })
$listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -eq 8030 })
if ($processes.Count -ne 0 -or $listeners.Count -ne 0) { exit 2 }
[Console]::Out.Write('stopped_verified')
'''
result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command', probe],
                        env=env, capture_output=True, text=True, check=True)
assert result.stdout == 'stopped_verified'
before = data_hashes()
archive = ROOT / 'state' / 'maintenance-B30-11D'
archive.mkdir(exist_ok=False)
for path in [prepared_path, process_path, *list((ROOT / 'state').glob('launch-*.json')),
             ROOT / 'logs' / 'server.stderr.log', ROOT / 'logs' / 'server.stdout.log']:
    if path.is_file():
        shutil.copy2(path, archive / path.name)

subprocess.run(['git', '-C', str(SOURCE), 'switch', '--detach', NEW_SHA], check=True)
assert git('rev-parse', 'HEAD') == NEW_SHA and not git('status', '--porcelain')
new_digest = digest_source(SOURCE)
assert data_hashes() == before
updated = {**prepared, 'source_sha256': new_digest}
atomic_json(prepared_path, updated)
assert json.loads(prepared_path.read_text(encoding='utf-8')) == updated
receipt = {'schema': 1, 'card': 'B30-11D', 'at': datetime.now(timezone.utc).isoformat(),
           'reason': 'Reviewed launcher-pipe correction on stopped owner-local instance',
           'old_commit': old_sha, 'new_commit': NEW_SHA, 'old_digest': OLD_DIGEST,
           'new_digest': new_digest, 'stopped_verified': True,
           'data_media_credentials_unchanged': data_hashes() == before,
           'init_seed_migrate_executed': False, 'archived_failed_receipt': str(archive)}
atomic_json(archive / 'maintenance-receipt.json', receipt)
assert receipt['data_media_credentials_unchanged']
assert hashlib.sha256(process_path.read_bytes()).digest() == hashlib.sha256((archive / 'process.json').read_bytes()).digest()
process_path.unlink()
print(json.dumps(receipt, sort_keys=True))
