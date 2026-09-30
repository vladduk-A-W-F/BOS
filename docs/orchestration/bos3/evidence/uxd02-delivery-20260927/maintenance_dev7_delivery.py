"""Two-phase, stopped-instance UXD02 delivery maintenance for frozen BoS 3.0.

This tool never stops or starts the server and never runs Django, migrations,
seeds, resets, or rollback. `capture` records a live, verified baseline; after
the official owner tool has stopped it, `apply` may switch an exact reviewed
dev7 Git commit and atomically rebind the prepared source digest. Until every
pending target pin below is reviewed and filled, this runner is not executable.
"""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


BASELINE_SHA = '8114097b3ddf2c31b709ed945bfb514c404ce4f1'
# Filled together only after independent review of an immutable dev7 candidate.
APPROVED_CANDIDATE_SHA = 'd8e121a0b38bb8c98f5719568b6fa87374e2bfb0'
APPROVED_MANIFEST_PATH = 'docs/orchestration/bos3/DRILLDOWN_DEV7_CANDIDATE.json'
APPROVED_MANIFEST_SHA256 = '823761cbc532b5707e3d3fa990be9c8aba8bcdafdcfbdbc6779d4ce18dc64509'
DELIVERY_FILES = frozenset({
    'README.md',
    'README_UA.md',
    'assets/app.js',
    'boss_project/version.py',
    'docs/BoS_3_0_Start_UA.manifest.json',
    'docs/BoS_3_0_Start_UA.pdf',
    'docs/design/evidence-uxd02-drilldown-20260927/AUTHOR_REPORT_RU.md',
    'docs/design/evidence-uxd02-drilldown-20260927/BUILD.json',
    'docs/design/evidence-uxd02-drilldown-20260927/BUILD.stderr.log',
    'docs/design/evidence-uxd02-drilldown-20260927/BUILD.stdout.log',
    'docs/design/evidence-uxd02-drilldown-20260927/SOURCE_AND_CHANGE_MANIFEST.json',
    'docs/orchestration/bos3/DRILLDOWN_DEV7_CANDIDATE.json',
    'frontend/boss_app_source.html',
    'tools/bos_control.py',
    'tools/test_bos3_control.py',
})
STATIC_PNG = 'assets/bos3-fasteners-entry.png'
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
ARCHIVE_NAME = re.compile(r'^maintenance-UXD02-DELIVERY-[A-Za-z0-9._-]+$')


class DeliveryError(RuntimeError):
    pass


def git(source, *args, check=True):
    result = subprocess.run(['git', '-C', str(source), *args], capture_output=True,
                            text=True, encoding='utf-8')
    if check and result.returncode:
        raise DeliveryError('Git precondition failed: ' + ' '.join(args))
    return result


def git_blob(source, revision, relative):
    result = subprocess.run(['git', '-C', str(source), 'show', revision + ':' + relative],
                            capture_output=True)
    if result.returncode:
        raise DeliveryError('Candidate asset blob is unavailable.')
    return result.stdout


def source_digest(source):
    if git(source, 'status', '--porcelain').stdout:
        raise DeliveryError('Source checkout is not clean.')
    listed_result = subprocess.run(['git', '-C', str(source), 'ls-files', '-z'], capture_output=True)
    if listed_result.returncode:
        raise DeliveryError('Tracked source manifest is unavailable.')
    listed = listed_result.stdout.split(b'\0')
    digest = hashlib.sha256()
    for raw in listed:
        if not raw:
            continue
        relative = Path(raw.decode('utf-8'))
        path = source / relative
        if not path.is_file():
            raise DeliveryError('Tracked source file is missing.')
        digest.update(str(relative).replace('\\', '/').encode('utf-8') + b'\0')
        digest.update(path.read_bytes())
    return digest.hexdigest()


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    if temporary.exists():
        raise DeliveryError('Existing temporary maintenance file blocks atomic write.')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def native_powershell_environment():
    env = {key.upper(): value for key, value in os.environ.items()}
    system_root = Path(env.get('SYSTEMROOT', ''))
    executable = system_root / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    modules = system_root / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'Modules'
    if not system_root.is_absolute() or not executable.is_file() or not modules.is_dir():
        raise DeliveryError('Native Windows PowerShell is unavailable.')
    env['PSMODULEPATH'] = str(modules)
    return str(executable), env


class WindowsProcess:
    def __init__(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.kernel.GetProcessTimes.restype = wintypes.BOOL
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
            wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL

    def open(self, pid):
        handle = self.kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        return handle

    def identity(self, handle, pid):
        times = [wintypes.FILETIME() for _ in range(4)]
        if not self.kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
            raise DeliveryError('Cannot verify receipt creation time.')
        size = wintypes.DWORD(32768)
        image = ctypes.create_unicode_buffer(size.value)
        if not self.kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            raise DeliveryError('Cannot verify receipt executable path.')
        return {'pid': pid,
                'created_ticks': (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
                'image': str(Path(image.value).resolve()).replace('\\', '/').lower()}

    def close(self, handle):
        if handle:
            self.kernel.CloseHandle(handle)


def command_line(pid):
    powershell, env = native_powershell_environment()
    command = ('$p=Get-CimInstance Win32_Process -Filter "ProcessId = ' + str(pid)
               + '"; if ($null -ne $p) {[Console]::Out.Write($p.CommandLine)}')
    result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command', command],
                            env=env, capture_output=True, text=True, encoding='utf-8', timeout=15)
    if result.returncode:
        raise DeliveryError('Cannot verify receipt command line.')
    return result.stdout


def listener_pid(port):
    powershell, env = native_powershell_environment()
    command = ('$listeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | '
               'Where-Object { $_.LocalPort -eq ' + str(port) + ' }); '
               "if ($listeners.Count -eq 1 -and ($listeners[0].LocalAddress -eq '127.0.0.1' "
               "-or $listeners[0].LocalAddress -eq '::1')) {[Console]::Out.Write($listeners[0].OwningProcess)} "
               'elseif ($listeners.Count -gt 0) { exit 2 }')
    result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command', command],
                            env=env, capture_output=True, text=True, encoding='utf-8', timeout=15)
    if result.returncode:
        raise DeliveryError('Cannot determine loopback listener identity.')
    return int(result.stdout) if result.stdout.strip().isdigit() else None


def require_stopped(source, port):
    powershell, env = native_powershell_environment()
    env['BOS3_DELIVERY_SOURCE'] = str(source)
    env['BOS3_DELIVERY_PORT'] = str(port)
    command = r'''
$processes = @(Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -like ('*' + $env:BOS3_DELIVERY_SOURCE + '*internal-serve*')
})
$listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object {
  $_.LocalPort -eq [int]$env:BOS3_DELIVERY_PORT
})
if ($processes.Count -ne 0 -or $listeners.Count -ne 0) { exit 2 }
'''
    result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command', command],
                            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=15)
    if result.returncode:
        raise DeliveryError('Instance is not proven stopped; use the official owner lifecycle tool first.')


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeliveryError('Required maintenance metadata is unavailable.') from exc


def paths(root):
    return {'root': root, 'data': root / 'data', 'media': root / 'media', 'state': root / 'state',
            'prepared': root / 'state' / 'prepared.json', 'process': root / 'state' / 'process.json',
            'owner_access': root / 'state' / 'owner-access.json',
            'runtime_secrets': root / 'state' / 'runtime-secrets.json'}


def protected_payload_digest(layout):
    digest = hashlib.sha256()
    for directory in (layout['data'], layout['media']):
        if not directory.is_dir():
            raise DeliveryError('Protected instance directory is unavailable.')
        for path in sorted(item for item in directory.rglob('*') if item.is_file()):
            digest.update(str(path.relative_to(layout['root'])).replace('\\', '/').encode('utf-8') + b'\0')
            digest.update(path.read_bytes())
    for key in ('owner_access', 'runtime_secrets'):
        path = layout[key]
        if not path.is_file():
            raise DeliveryError('Protected credential file is unavailable.')
        digest.update(str(path.relative_to(layout['root'])).replace('\\', '/').encode('utf-8') + b'\0')
        digest.update(path.read_bytes())
    return digest.hexdigest()


def require_baseline(source, layout, old_sha):
    if old_sha != BASELINE_SHA:
        raise DeliveryError('Only frozen dev6 runtime 8114097 may be maintained by this runner.')
    actual_sha = git(source, 'rev-parse', 'HEAD').stdout.strip()
    if actual_sha != old_sha:
        raise DeliveryError('Source checkout is not the declared frozen runtime.')
    digest = source_digest(source)
    prepared = read_json(layout['prepared'])
    expected_database = layout['data'] / 'bos3-fasteners.sqlite3'
    if (prepared.get('source') != str(source) or prepared.get('source_sha256') != digest
            or prepared.get('database') != str(expected_database)
            or prepared.get('port') != 8030 or not prepared.get('initialized_at')
            or not expected_database.is_file()):
        raise DeliveryError('Prepared runtime metadata does not bind this source and digest.')
    return prepared, digest


def verify_ready_receipt(layout, source, prepared):
    receipt = read_json(layout['process'])
    record = receipt.get('process')
    tokens = receipt.get('required_tokens')
    if receipt.get('status') != 'ready' or not isinstance(record, dict) or not isinstance(tokens, list):
        raise DeliveryError('A ready, identity-bound process receipt is required before manual stop.')
    if not all(isinstance(token, str) and token for token in tokens):
        raise DeliveryError('Process receipt command tokens are malformed.')
    if receipt.get('source') != str(source) or receipt.get('source_sha256') != prepared['source_sha256']:
        raise DeliveryError('Ready receipt is not bound to the frozen source.')
    if set(record) != {'pid', 'created_ticks', 'image'} or not isinstance(record['pid'], int):
        raise DeliveryError('Ready receipt process identity is malformed.')
    ops = WindowsProcess()
    handle = ops.open(record['pid'])
    if handle is None:
        raise DeliveryError('Receipt process has already exited.')
    try:
        if ops.identity(handle, record['pid']) != record:
            raise DeliveryError('Live process differs from protected receipt identity.')
    finally:
        ops.close(handle)
    if any(token not in command_line(record['pid']) for token in tokens):
        raise DeliveryError('Live process command differs from protected receipt identity.')
    if listener_pid(prepared['port']) != record['pid']:
        raise DeliveryError('Ready receipt PID is not the sole runtime listener.')
    return receipt


def archive_directory(layout, name):
    if not ARCHIVE_NAME.fullmatch(name):
        raise DeliveryError('Archive name is not an allowed maintenance identifier.')
    archive = layout['state'] / name
    if archive.exists():
        raise DeliveryError('Maintenance archive already exists.')
    archive.mkdir()
    return archive


def capture(args):
    source, root = args.source.resolve(), args.root.resolve()
    layout = paths(root)
    prepared, digest = require_baseline(source, layout, args.old_sha)
    approved_sha, manifest = require_approved_candidate(source, args.old_sha)
    receipt = verify_ready_receipt(layout, source, prepared)
    archive = archive_directory(layout, args.archive_name)
    shutil.copy2(layout['prepared'], archive / 'prepared.before-stop.json')
    shutil.copy2(layout['process'], archive / 'process.ready.json')
    attestation = {
        'schema': 1, 'kind': 'bos3.uxd02-delivery.started-attestation.v1',
        'at': datetime.now(timezone.utc).isoformat(), 'old_sha': args.old_sha, 'new_sha': approved_sha,
        'manifest_path': manifest['path'], 'manifest_sha256': manifest['sha256'],
        'source': str(source), 'root': str(root), 'source_sha256': digest,
        'prepared_sha256': hashlib.sha256(layout['prepared'].read_bytes()).hexdigest(),
        'protected_payload_sha256': protected_payload_digest(layout),
        'process_identity': receipt['process'], 'archive': str(archive),
    }
    atomic_json(archive / 'started-attestation.json', attestation)
    print(json.dumps({'captured': True, 'archive': str(archive), 'old_sha': args.old_sha}, sort_keys=True))


def require_delivery_assets(source, new_sha, product_paths):
    if STATIC_PNG not in product_paths:
        return
    if not git_blob(source, new_sha, STATIC_PNG).startswith(PNG_SIGNATURE):
        raise DeliveryError('The only permitted static image is not a PNG asset.')


def require_manifest_pin(source, new_sha):
    if (not isinstance(APPROVED_MANIFEST_PATH, str) or not APPROVED_MANIFEST_PATH
            or APPROVED_MANIFEST_PATH.startswith('/')
            or '..' in APPROVED_MANIFEST_PATH.split('/')):
        raise DeliveryError('Reviewed dev7 manifest path is not pinned.')
    if not isinstance(APPROVED_MANIFEST_SHA256, str) or not re.fullmatch(r'[0-9a-f]{64}', APPROVED_MANIFEST_SHA256):
        raise DeliveryError('Reviewed dev7 manifest SHA-256 is not pinned.')
    actual = hashlib.sha256(git_blob(source, new_sha, APPROVED_MANIFEST_PATH)).hexdigest()
    if actual != APPROVED_MANIFEST_SHA256:
        raise DeliveryError('Reviewed dev7 manifest hash differs from the candidate blob.')
    return {'path': APPROVED_MANIFEST_PATH, 'sha256': APPROVED_MANIFEST_SHA256}


def require_approved_candidate(source, old_sha):
    if not isinstance(APPROVED_CANDIDATE_SHA, str) or not re.fullmatch(r'[0-9a-f]{40}', APPROVED_CANDIDATE_SHA):
        raise DeliveryError('Reviewed dev7 candidate SHA is not pinned.')
    if not DELIVERY_FILES or any(not isinstance(path, str) or not path for path in DELIVERY_FILES):
        raise DeliveryError('Reviewed dev7 exact product allowlist is not pinned.')
    if APPROVED_MANIFEST_PATH not in DELIVERY_FILES:
        raise DeliveryError('Reviewed dev7 manifest path is outside the exact product allowlist.')
    manifest = require_manifest_pin(source, APPROVED_CANDIDATE_SHA)
    require_delivery_diff(source, old_sha, APPROVED_CANDIDATE_SHA)
    return APPROVED_CANDIDATE_SHA, manifest


def require_delivery_diff(source, old_sha, new_sha):
    if not re.fullmatch(r'[0-9a-f]{40}', new_sha) or new_sha == old_sha:
        raise DeliveryError('New source SHA must be a different full commit SHA.')
    git(source, 'cat-file', '-e', new_sha + '^{commit}')
    if git(source, 'merge-base', '--is-ancestor', old_sha, new_sha, check=False).returncode:
        raise DeliveryError('New dev7 candidate must descend from frozen dev6 runtime.')
    paths = [row for row in git(source, 'diff', '--name-only', old_sha, new_sha).stdout.splitlines() if row]
    product = [row for row in paths if not row.startswith('docs/orchestration/')]
    if not product or any(row not in DELIVERY_FILES for row in product):
        raise DeliveryError('Candidate changes files outside the exact dev7 delivery allowlist.')
    require_delivery_assets(source, new_sha, product)
    return paths, product


def apply(args):
    source, root = args.source.resolve(), args.root.resolve()
    layout = paths(root)
    approved_sha, manifest = require_approved_candidate(source, args.old_sha)
    if args.new_sha != approved_sha:
        raise DeliveryError('Requested candidate differs from the immutable approved candidate SHA.')
    attestation = read_json(args.attestation.resolve())
    archive = args.attestation.resolve().parent
    try:
        args.attestation.resolve().relative_to(layout['state'])
    except ValueError as exc:
        raise DeliveryError('Started attestation must reside below the protected instance state directory.') from exc
    expected = {'schema': 1, 'kind': 'bos3.uxd02-delivery.started-attestation.v1', 'old_sha': args.old_sha,
                'new_sha': approved_sha,
                'manifest_path': manifest['path'], 'manifest_sha256': manifest['sha256'],
                'source': str(source), 'root': str(root), 'archive': str(archive)}
    if any(attestation.get(key) != value for key, value in expected.items()):
        raise DeliveryError('Started attestation does not belong to this maintenance request.')
    prepared, digest = require_baseline(source, layout, args.old_sha)
    if (attestation.get('source_sha256') != digest
            or attestation.get('prepared_sha256') != hashlib.sha256(layout['prepared'].read_bytes()).hexdigest()):
        raise DeliveryError('Baseline changed after the started attestation.')
    if attestation.get('protected_payload_sha256') != protected_payload_digest(layout):
        raise DeliveryError('Protected data, media, or credential bytes changed after attestation.')
    if layout['process'].exists():
        raise DeliveryError('Official stop did not clear the process receipt.')
    require_stopped(source, prepared['port'])
    diff_paths, product_paths = require_delivery_diff(source, args.old_sha, args.new_sha)
    before = protected_payload_digest(layout)
    atomic_json(archive / 'stopped-preflight.json', {
        'schema': 1, 'old_sha': args.old_sha, 'new_sha': args.new_sha,
        'stopped_verified': True, 'product_paths': product_paths,
        'ignored_orchestration_paths': [row for row in diff_paths if row.startswith('docs/orchestration/')],
    })
    git(source, 'switch', '--detach', args.new_sha)
    if git(source, 'rev-parse', 'HEAD').stdout.strip() != args.new_sha:
        raise DeliveryError('Source switch did not reach the reviewed candidate.')
    new_digest = source_digest(source)
    if protected_payload_digest(layout) != before:
        raise DeliveryError('Protected data, media, or credential bytes changed during source switch.')
    updated = {**prepared, 'source_sha256': new_digest}
    atomic_json(layout['prepared'], updated)
    unchanged = protected_payload_digest(layout) == before
    if not unchanged:
        raise DeliveryError('Protected data, media, or credential bytes changed during prepared update.')
    atomic_json(archive / 'maintenance-receipt.json', {
        'schema': 1, 'card': 'UXD02-DELIVERY-PREP', 'at': datetime.now(timezone.utc).isoformat(),
        'old_sha': args.old_sha, 'new_sha': args.new_sha,
        'manifest_path': manifest['path'], 'manifest_sha256': manifest['sha256'],
        'old_digest': digest, 'new_digest': new_digest,
        'stopped_verified': True, 'product_paths': product_paths,
        'data_media_credentials_unchanged': True,
        'runner_never_called': ['init', 'migrate', 'seed', 'start', 'stop', 'rollback'],
    })
    print(json.dumps({'updated': True, 'old_sha': args.old_sha, 'new_sha': args.new_sha,
                      'product_paths': product_paths}, sort_keys=True))


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest='command', required=True)
    for name in ('capture', 'apply'):
        command = commands.add_parser(name)
        command.add_argument('--source', type=Path, required=True)
        command.add_argument('--root', type=Path, required=True)
        command.add_argument('--old-sha', required=True)
    capture_command = commands.choices['capture']
    capture_command.add_argument('--archive-name', required=True)
    apply_command = commands.choices['apply']
    apply_command.add_argument('--new-sha', required=True)
    apply_command.add_argument('--attestation', type=Path, required=True)
    return result


if __name__ == '__main__':
    try:
        arguments = parser().parse_args()
        if arguments.command == 'capture':
            capture(arguments)
        else:
            apply(arguments)
    except DeliveryError as error:
        print('BOS3_DELIVERY_REFUSED: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
