"""Lifecycle controller for one isolated, loopback-only BoS 3.0 training instance."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener


SOURCE = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = Path('D:/3/BOSDev/local-bos3/owner')
PORT = 8030
FIXTURE_ID = 'bos3-fasteners-uk-v1'
DATASET_FIXTURES = {'bos3': FIXTURE_ID, 'bos4': 'bos4-demo-v1.0'}


class LocalError(RuntimeError):
    pass


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    for delay in (None, .05, .1):
        if delay is not None:
            time.sleep(delay)
        try:
            os.replace(temporary, path)
            return
        except PermissionError as failure:
            if getattr(failure, 'winerror', None) not in (5, 32, 33) or delay == .1:
                raise


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def dataset_profile(prepared):
    if not isinstance(prepared, dict):
        raise LocalError('Local dataset receipt must be an object.')
    dataset = prepared.get('dataset', 'bos3')
    if not isinstance(dataset, str) or dataset not in DATASET_FIXTURES:
        raise LocalError('Unknown local dataset profile; automatic switching is forbidden.')
    if ('fixture_id' in prepared and prepared['fixture_id'] != DATASET_FIXTURES[dataset]):
        raise LocalError('Local dataset profile and fixture receipt differ.')
    return dataset


def digest_source(source):
    status = subprocess.run(['git', '-C', str(source), 'status', '--porcelain'],
        capture_output=True, text=True, encoding='utf-8')
    if status.returncode or status.stdout:
        raise LocalError('Accepted source must be a clean Git checkout before local initialization or start.')
    listed = subprocess.run(['git', '-C', str(source), 'ls-files', '-z'], capture_output=True)
    if listed.returncode:
        raise LocalError('Accepted source cannot provide its tracked-file manifest.')
    tracked = [Path(value.decode('utf-8')) for value in listed.stdout.split(b'\0') if value]
    if not tracked:
        raise LocalError('Accepted source has no tracked files.')
    digest = hashlib.sha256()
    for relative in tracked:
        path = source / relative
        if not path.is_file():
            raise LocalError('Tracked source file is missing: ' + str(relative))
        digest.update(str(relative).replace('\\', '/').encode('utf-8') + b'\0' + path.read_bytes())
    return digest.hexdigest()


def localhost_port_is_free():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(('127.0.0.1', PORT))


def normalized(path):
    return str(Path(path).resolve()).replace('\\', '/').lower()


def instance_paths(root):
    root = Path(root).resolve()
    return {
        'root': root,
        'database': root / 'data' / 'bos3-fasteners.sqlite3',
        'media': root / 'media',
        'static': root / 'static',
        'logs': root / 'logs',
        'state': root / 'state',
        'prepared': root / 'state' / 'prepared.json',
        'process': root / 'state' / 'process.json',
        'owner_access': root / 'state' / 'owner-access.json',
        'runtime_secrets': root / 'state' / 'runtime-secrets.json',
    }


def launch_candidate_path(paths, launch_id):
    return paths['state'] / ('launch-' + launch_id + '.json')


def validate_root(source, paths):
    root = paths['root']
    if not root.is_absolute() or root == source or root in source.parents or source in root.parents:
        raise LocalError('Instance root and source must be separate, non-nested absolute paths.')
    key = normalized(root)
    source_key = normalized(source)
    if 'online-review' in key or 'online-review' in source_key:
        raise LocalError('Review and source roots are forbidden for this local training instance.')
    if paths['database'].name != 'bos3-fasteners.sqlite3':
        raise LocalError('Local training database filename differs from the fixed isolated contract.')
    forbidden = {normalized(source / name) for name in ('BoS_Demo.sqlite3', 'BoS_Working.sqlite3', 'db.sqlite3')}
    if normalized(paths['database']) in forbidden:
        raise LocalError('A source default database cannot become the local training database.')


def native_windows_powershell_environment(base_env=None):
    """Use only the native Windows PowerShell module catalog for system probes."""
    source_env = os.environ if base_env is None else base_env
    native_env = {key.upper(): value for key, value in source_env.items()}
    system_root = Path(native_env.get('SYSTEMROOT', ''))
    executable = system_root / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    modules = system_root / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'Modules'
    if not system_root.is_absolute() or not executable.is_file() or not modules.is_dir():
        raise LocalError('Native Windows PowerShell executable or module catalog is unavailable.')
    native_env['PSMODULEPATH'] = str(modules)
    return str(executable), native_env


def current_user_sid():
    powershell, native_env = native_windows_powershell_environment()
    result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command',
        '[Console]::Out.Write([System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value)'],
        env=native_env, capture_output=True, text=True, encoding='utf-8', timeout=15)
    sid = result.stdout.strip()
    if result.returncode or not sid.startswith('S-1-'):
        raise LocalError('Current Windows user identity cannot be verified for local instance ACL.')
    return sid


def protect_path(path, *, directory):
    """Restrict a new instance path to current user and SYSTEM before private writes."""
    if os.name != 'nt':
        raise LocalError('The local BoS 3.0 lifecycle requires Windows ACL verification.')
    sid = current_user_sid()
    suffix = ':(OI)(CI)F' if directory else ':F'
    result = subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', '*' + sid + suffix,
        '/grant:r', '*S-1-5-18' + suffix], capture_output=True)
    if result.returncode:
        raise LocalError('Local instance ACL could not be applied.')
    verify = r'''
$path = $env:BOS3_ACL_VERIFY_PATH
if (-not $path) { exit 1 }
$acl = Get-Acl -LiteralPath $path
$current = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$allowed = @($current, 'S-1-5-18')
if (-not $acl.AreAccessRulesProtected) { exit 2 }
$seen = @{}
foreach ($rule in $acl.Access) {
  try { $sid = $rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value } catch { exit 3 }
  if ($sid -notin $allowed) { exit 4 }
  if ($rule.IsInherited) { exit 8 }
  if ($rule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) { exit 5 }
  if (($rule.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::FullControl) -ne [System.Security.AccessControl.FileSystemRights]::FullControl) { exit 6 }
  $seen[$sid] = $true
}
if (-not $seen[$current] -or -not $seen['S-1-5-18']) { exit 7 }
'''
    verify_env = os.environ.copy()
    verify_env['BOS3_ACL_VERIFY_PATH'] = str(path)
    powershell, native_env = native_windows_powershell_environment(verify_env)
    checked = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command', verify], env=native_env,
        capture_output=True, text=True, encoding='utf-8', timeout=15)
    if checked.returncode:
        raise LocalError('Effective local instance ACL could not be verified.')


def environment(paths, source, secret):
    prepared = read_json(paths['prepared'])
    dataset = dataset_profile(prepared)
    env = os.environ.copy()
    for key in ('BOS_TEST_DB_NAME', 'BOS_TEST_MEDIA', 'BOS_VERIFY_DB', 'BOS_REVIEW_ROOT',
                'BOS_REVIEW_SEED_MODE', 'BOS_DATABASE_PATH', 'BOS_MEDIA_ROOT'):
        env.pop(key, None)
    env.update({
        'PYTHONUTF8': '1',
        'PYTHONDONTWRITEBYTECODE': '1',
        'DJANGO_SETTINGS_MODULE': 'bos3_local_settings',
        'BOS_DATA_MODE': 'demo',
        'BOS3_LOCAL_ROOT': str(paths['root']),
        'BOS3_LOCAL_SOURCE': str(source),
        'BOS3_LOCAL_DB': str(paths['database']),
        'BOS3_LOCAL_MEDIA': str(paths['media']),
        'BOS3_LOCAL_SECRET': secret,
        'BOS3_LOCAL_DATASET': dataset,
        'BOS3_TRAINING_ENABLED': '1' if dataset == 'bos3' else '0',
        'BOS3_TRAINING_PROFILE': 'isolated-synthetic',
        'BOS3_TRAINING_DB_MARKER': DATASET_FIXTURES[dataset],
        'BOS3_TRAINING_INSTALLATION_ID': prepared['installation_id'],
        'BOS3_TRAINING_OWNER_USERNAME': prepared['owner_username'],
        'BOS3_LOCAL_PORT': str(PORT),
        'BOS3_LOCAL_SOURCE_DIGEST': digest_source(source),
    })
    return env


def private_write(path, value):
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.close(descriptor)
        protect_path(path, directory=False)
        with Path(path).open('wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            Path(path).unlink()
        except OSError:
            pass
        raise


def managed(command, env, paths, *, secret_input=None):
    result = subprocess.run([sys.executable, '-X', 'utf8', '-B', 'manage.py', *command], cwd=SOURCE,
        env=env, input=secret_input, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', timeout=180)
    (paths['logs'] / (command[0] + '.log')).write_text(result.stdout, encoding='utf-8')
    if result.returncode:
        raise LocalError('Initialization command failed; inspect the private local log for its command name.')


OWNER_BOOTSTRAP = r'''
import os
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import transaction
username = os.environ['BOS3_LOCAL_OWNER_USERNAME']
password = os.environ['BOS3_LOCAL_OWNER_PASSWORD']
with transaction.atomic():
    User = get_user_model()
    if User.objects.filter(username=username).exists():
        raise RuntimeError('owner already exists')
    user = User(username=username, is_active=True, is_staff=False, is_superuser=False)
    user.set_password(password)
    user.save(force_insert=True)
    user.groups.add(Group.objects.get_or_create(name='ceo')[0])
    permissions = Permission.objects.filter(content_type__app_label='operations', content_type__model='document',
        codename__in=('view_document', 'download_document', 'export_workspace'))
    if permissions.count() != 3:
        raise RuntimeError('required document permissions are unavailable')
    user.user_permissions.add(*permissions)
'''


def initialize(paths, source, dataset='bos3'):
    dataset_profile({'dataset': dataset})
    if os.name != 'nt':
        raise LocalError('The local BoS 3.0 lifecycle requires Windows.')
    validate_root(source, paths)
    if paths['root'].exists():
        raise LocalError('Instance root already exists; init requires a fresh absent root and never overwrites it.')
    localhost_port_is_free()
    paths['root'].mkdir(parents=True, exist_ok=False)
    protect_path(paths['root'], directory=True)
    for name in ('data', 'media', 'static', 'logs', 'state'):
        (paths['root'] / name).mkdir()
        protect_path(paths['root'] / name, directory=True)
    owner_username = 'bos3-owner-' + secrets.token_hex(6)
    owner_password = secrets.token_urlsafe(24)
    installation_id = secrets.token_urlsafe(24)
    django_secret = secrets.token_urlsafe(48)
    owner_access = {'url': 'http://127.0.0.1:' + str(PORT) + '/', 'username': owner_username,
        'password': owner_password}
    runtime_secrets = {'django_secret': django_secret}
    private_write(paths['runtime_secrets'], runtime_secrets)
    private_write(paths['owner_access'], owner_access)
    prepared = {'schema': 1, 'scope': 'isolated local synthetic BoS instance', 'dataset': dataset,
        'source': str(source), 'source_sha256': digest_source(source), 'database': str(paths['database']),
        'media': str(paths['media']), 'port': PORT, 'owner_username': owner_username,
        'installation_id': installation_id, 'owner_access_file': str(paths['owner_access']),
        'runtime_secrets_file': str(paths['runtime_secrets']),
        'owner_is_staff': False, 'owner_is_superuser': False,
        'prepared_at': datetime.now(timezone.utc).isoformat()}
    atomic_json(paths['prepared'], prepared)
    env = environment(paths, source, django_secret)
    env.update(BOS3_LOCAL_OWNER_USERNAME=owner_username, BOS3_LOCAL_OWNER_PASSWORD=owner_password)
    managed(['migrate', '--noinput'], env, paths)
    managed(['shell', '-c', OWNER_BOOTSTRAP], env, paths)
    seed_command = (['seed_bos3_fasteners', '--owner-username', owner_username]
                    if dataset == 'bos3' else ['seed_bos4_demo'])
    managed(seed_command, env, paths)
    del env['BOS3_LOCAL_OWNER_PASSWORD']
    prepared['fixture_id'] = DATASET_FIXTURES[dataset]
    prepared['initialized_at'] = datetime.now(timezone.utc).isoformat()
    atomic_json(paths['prepared'], prepared)
    print('Local BoS 3.0 synthetic instance initialized. Credentials remain only in its private file.')


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
        self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.TerminateProcess.restype = wintypes.BOOL
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD

    def open(self, pid, terminate=False):
        access = 0x1000 | 0x100000 | (1 if terminate else 0)
        handle = self.kernel.OpenProcess(access, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:  # ERROR_INVALID_PARAMETER: PID has exited.
                return None
            raise LocalError('Owned process cannot be opened; receipt retained.')
        return handle

    def identity(self, handle, pid):
        times = [wintypes.FILETIME() for _ in range(4)]
        if not self.kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
            raise LocalError('Process creation time cannot be verified.')
        size = wintypes.DWORD(32768)
        image = ctypes.create_unicode_buffer(size.value)
        if not self.kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            raise LocalError('Process executable cannot be verified.')
        return {'pid': pid, 'created_ticks': (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
                'image': normalized(image.value)}

    def close(self, handle):
        if handle:
            self.kernel.CloseHandle(handle)

    def exited(self, handle, timeout=0):
        result = self.kernel.WaitForSingleObject(handle, timeout)
        if result not in (0, 258):
            raise LocalError('Owned process wait failed; receipt retained.')
        return result == 0


def expected_runtime_image():
    """Bind venv launchers to their verified underlying interpreter image."""
    return normalized(getattr(sys, '_base_executable', None) or sys.executable)


def verify_current_runtime_image():
    ops = WindowsProcess()
    handle = ops.open(os.getpid())
    if handle is None:
        raise LocalError('Local controller process disappeared during image verification.')
    try:
        record = ops.identity(handle, os.getpid())
        if record['image'] != expected_runtime_image():
            raise LocalError('Local controller image differs from its verified base interpreter.')
        return record
    finally:
        ops.close(handle)


def process_command_line(pid):
    if not isinstance(pid, int) or pid <= 0:
        raise LocalError('Process receipt PID is malformed.')
    command = ('$p=Get-CimInstance Win32_Process -Filter "ProcessId = ' + str(pid)
        + '"; if ($null -ne $p) {[Console]::Out.Write($p.CommandLine)}')
    powershell, native_env = native_windows_powershell_environment()
    result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command', command], env=native_env,
        capture_output=True, text=True, encoding='utf-8', timeout=15)
    if result.returncode:
        raise LocalError('Process command line cannot be verified.')
    return result.stdout


def child_tokens(source, paths, runtime, launch_id):
    return [str(SOURCE / 'scripts' / 'bos3_local.py'), 'internal-serve', '--root', str(paths['root']),
        '--source', str(source), '--runtime', runtime, '--launch-id', launch_id]


def child_spec(source, paths, runtime, launch_id):
    tokens = child_tokens(source, paths, runtime, launch_id)
    return ['-X', 'utf8', '-B', *tokens], tokens


def choose_runtime(env):
    result = subprocess.run([sys.executable, '-c', 'import waitress'], env=env, capture_output=True)
    return 'waitress' if result.returncode == 0 else 'runserver'


def launch_via_powershell(args, cwd, env, paths):
    spec = {'python': str(Path(sys.executable).resolve()), 'cwd': str(cwd),
        'argument_line': subprocess.list2cmdline(args),
        'stdout': str(paths['logs'] / 'server.stdout.log'),
        'stderr': str(paths['logs'] / 'server.stderr.log')}
    encoded = __import__('base64').b64encode(json.dumps(spec).encode('utf-8')).decode('ascii')
    # Inline command, not -File: ExecutionPolicy governs script files only, so no Bypass is needed.
    script = ("$ErrorActionPreference = 'Stop'; "
        f"$s = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}')) | ConvertFrom-Json; "
        "$p = Start-Process -FilePath $s.python -WorkingDirectory $s.cwd -ArgumentList $s.argument_line "
        "-RedirectStandardOutput $s.stdout -RedirectStandardError $s.stderr -WindowStyle Hidden -PassThru; "
        "[Console]::Out.Write($p.Id); exit 0")
    command = __import__('base64').b64encode(script.encode('utf-16-le')).decode('ascii')
    powershell, native_env = native_windows_powershell_environment(env)
    launch_stderr = paths['logs'] / 'server-launch.stderr.log'
    with launch_stderr.open('ab') as error_log:
        result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-EncodedCommand', command],
            env=native_env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=error_log, timeout=30)
    if result.returncode:
        raise LocalError('Hidden local server process could not be created.')


def wait_for_child_gate(paths, source, runtime, launch_id):
    """Do not initialize Django until parent has atomically recorded this exact child."""
    if os.environ.get('BOS3_LOCAL_LAUNCH_ID') != launch_id:
        raise LocalError('Internal local-server launch nonce is absent or mismatched.')
    source_digest = os.environ.get('BOS3_LOCAL_SOURCE_DIGEST')
    if not source_digest:
        raise LocalError('Internal local-server source digest is absent before launch gate.')
    validate_root(source, paths)
    own_tokens = child_tokens(source, paths, runtime, launch_id)
    ops = WindowsProcess()
    handle = ops.open(os.getpid())
    if handle is None:
        raise LocalError('Internal local-server process disappeared before launch gate.')
    try:
        own_record = ops.identity(handle, os.getpid())
        if own_record['image'] != expected_runtime_image():
            raise LocalError('Internal local-server image differs before launch gate.')
        command = process_command_line(os.getpid())
        if any(token not in command for token in own_tokens):
            raise LocalError('Internal local-server source arguments differ before launch gate.')
        candidate = {'schema': 1, 'launch_id': launch_id, 'source': str(source),
            'source_sha256': source_digest, 'runtime': runtime,
            'runtime_image': expected_runtime_image(), 'required_tokens': own_tokens,
            'process': own_record}
        candidate_path = launch_candidate_path(paths, launch_id)
        atomic_json(candidate_path, candidate)
        deadline = time.monotonic() + 15
        try:
            while time.monotonic() < deadline:
                try:
                    receipt = read_json(paths['process'])
                except (OSError, ValueError):
                    time.sleep(.1)
                    continue
                matches_identity = (receipt.get('launch_id') == launch_id and receipt.get('source') == str(source)
                        and receipt.get('source_sha256') == source_digest
                        and receipt.get('runtime') == runtime
                        and receipt.get('runtime_image') == expected_runtime_image()
                        and receipt.get('required_tokens') == own_tokens
                        and receipt.get('process') == own_record)
                if matches_identity and receipt.get('status') in ('identity_recorded', 'starting', 'ready'):
                    return
                if matches_identity and receipt.get('status') == 'start_failed':
                    raise LocalError('Parent recorded a failed launch before this local server opened a listener.')
                time.sleep(.1)
        finally:
            try:
                candidate_path.unlink()
            except OSError:
                pass
    finally:
        ops.close(handle)
    raise LocalError('Parent did not record this local-server identity before launch-gate timeout.')


def internal_serve(paths, source, runtime, launch_id):
    if not launch_id:
        raise LocalError('Internal local-server launch id is required.')
    wait_for_child_gate(paths, source, runtime, launch_id)
    expected_digest = os.environ.get('BOS3_LOCAL_SOURCE_DIGEST')
    receipt = read_json(paths['process'])
    if (not expected_digest or digest_source(source) != expected_digest
            or receipt.get('launch_id') != launch_id
            or receipt.get('source_sha256') != expected_digest):
        raise LocalError('Local source changed or gate receipt differs before Django startup.')
    sys.path.insert(0, str(source))
    if runtime == 'waitress':
        from waitress import serve
        from boss_project.wsgi import application
        serve(application, host='127.0.0.1', port=PORT, threads=4)
        return
    from django.core.management import execute_from_command_line
    execute_from_command_line([str(source / 'manage.py'), 'runserver', '127.0.0.1:' + str(PORT), '--noreload'])


def verify_process(record, expected_tokens, *, terminate=False):
    if not isinstance(record, dict) or set(record) != {'pid', 'created_ticks', 'image'}:
        raise LocalError('Local process receipt is malformed; no process will be touched.')
    ops = WindowsProcess()
    handle = ops.open(record['pid'], terminate=terminate)
    if handle is None:
        return None, ops
    try:
        if ops.identity(handle, record['pid']) != record or record['image'] != expected_runtime_image():
            raise LocalError('PID identity differs; no unrelated process will be touched.')
        command = process_command_line(record['pid'])
        if any(token not in command for token in expected_tokens):
            raise LocalError('Process source arguments differ; no unrelated process will be touched.')
        return handle, ops
    except BaseException:
        ops.close(handle)
        raise


def cleanup_verified_start(paths, state):
    """Stop only a process that passes the same identity and command checks as stop."""
    handle, ops = verify_process(state.get('process'), state.get('required_tokens', []), terminate=True)
    if handle is None:
        return {'already_exited': True}
    try:
        if not ops.kernel.TerminateProcess(handle, 0) or not ops.exited(handle, 10000):
            raise LocalError('Verified startup process did not stop; safe receipt retained.')
        return {'stopped_after_start_failure': True}
    finally:
        ops.close(handle)


def wait_for_child_announcement(paths, state):
    """Accept only a live internal child that independently announces this launch."""
    candidate_path = launch_candidate_path(paths, state['launch_id'])
    expected = ('schema', 'launch_id', 'source', 'source_sha256', 'runtime', 'runtime_image', 'required_tokens')
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            candidate = read_json(candidate_path)
        except (OSError, ValueError):
            time.sleep(.1)
            continue
        if not isinstance(candidate, dict) or any(candidate.get(key) != state[key] for key in expected):
            raise LocalError('Internal local-server announcement differs from the requested launch.')
        record = candidate.get('process')
        handle, child_ops = verify_process(record, state['required_tokens'])
        if handle is None:
            raise LocalError('Announced local-server child exited before identity confirmation.')
        child_ops.close(handle)
        return record
    raise LocalError('Internal local-server did not announce a verifiable child before timeout.')


def start(paths, source):
    prepared = read_json(paths['prepared'])
    dataset_profile(prepared)
    if prepared.get('source') != str(source) or prepared.get('source_sha256') != digest_source(source):
        raise LocalError('Prepared source changed or differs; start is refused.')
    if paths['process'].exists():
        raise LocalError('A local process receipt exists; use status or stop before start.')
    localhost_port_is_free()
    runtime_secrets = read_json(paths['runtime_secrets'])
    secret = runtime_secrets.get('django_secret')
    if secret is None:
        raise LocalError('Private runtime secrets do not contain the local Django secret.')
    env = environment(paths, source, secret)
    runtime = choose_runtime(env)
    launch_id = secrets.token_urlsafe(18)
    env['BOS3_LOCAL_LAUNCH_ID'] = launch_id
    args, tokens = child_spec(source, paths, runtime, launch_id)
    verify_current_runtime_image()
    ops = WindowsProcess()
    state = {'schema': 1, 'status': 'launch_requested', 'process': None, 'runtime': runtime,
        'port': PORT, 'source_sha256': prepared['source_sha256'], 'source': str(source),
        'launch_id': launch_id, 'runtime_image': expected_runtime_image(), 'required_tokens': tokens,
        'started_at': datetime.now(timezone.utc).isoformat()}
    receipt_written = False
    ownership_verified = False
    handle = None
    try:
        # Durable intent exists before the hidden child can be created.
        atomic_json(paths['process'], state)
        receipt_written = True
        launch_via_powershell(args, source, env, paths)
        record = wait_for_child_announcement(paths, state)
        handle = ops.open(record['pid'])
        if handle is None:
            raise LocalError('Hidden local server exited before its identity could be recorded.')
        if ops.identity(handle, record['pid']) != record or record['image'] != expected_runtime_image():
            raise LocalError('Hidden local server executable differs.')
        command = process_command_line(record['pid'])
        if any(token not in command for token in tokens):
            raise LocalError('Hidden local server source arguments differ.')
        state['process'] = record
        state['status'] = 'identity_recorded'
        atomic_json(paths['process'], state)
        ownership_verified = True
        state['status'] = 'starting'
        atomic_json(paths['process'], state)
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if ops.exited(handle):
                raise LocalError('Owned local server exited before readiness.')
            try:
                with opener.open('http://127.0.0.1:' + str(PORT) + '/api/auth/csrf/', timeout=1) as response:
                    if response.status == 200:
                        state['status'] = 'ready'
                        state['ready_at'] = datetime.now(timezone.utc).isoformat()
                        atomic_json(paths['process'], state)
                        print('Local BoS 3.0 ready at http://127.0.0.1:8030/')
                        return
            except OSError:
                time.sleep(.2)
        raise LocalError('Local server readiness timed out; process receipt retained for safe stop.')
    except BaseException as failure:
        state['status'] = 'start_failed'
        state['failure_type'] = type(failure).__name__
        try:
            atomic_json(paths['process'], state)
            receipt_written = True
        except OSError:
            receipt_written = paths['process'].exists()
        if ownership_verified:
            try:
                outcome = cleanup_verified_start(paths, state)
                try:
                    atomic_json(paths['state'] / 'last-start-failure.json', {
                        'failed_at': datetime.now(timezone.utc).isoformat(), 'process': state['process'],
                        'source_sha256': state['source_sha256'], 'cleanup': outcome})
                except OSError:
                    # The verified child is already gone. Retain the primary
                    # receipt if the secondary diagnostic record cannot persist.
                    pass
                if paths['process'].exists():
                    try:
                        paths['process'].unlink()
                    except OSError:
                        # The verified child is already gone; preserving a stale
                        # receipt is safer than falling back to PID-only handling.
                        pass
            except LocalError:
                # Keep the durable receipt for a later explicit status/stop; never
                # substitute a PID-only cleanup attempt.
                pass
        if not receipt_written:
            raise LocalError('Hidden launch state could not be recorded; no PID-only cleanup was attempted.') from failure
        raise
    finally:
        ops.close(handle)


def status_or_stop(paths, stop):
    state = read_json(paths['process']) if paths['process'].exists() else None
    if state is None:
        print(json.dumps({'owned_process': False, 'state': 'absent'}))
        return
    if state.get('process') is None:
        print(json.dumps({'owned_process': False, 'state': state.get('status'), 'recovery_pending': True}))
        return
    handle, ops = verify_process(state.get('process'), state.get('required_tokens', []), terminate=stop)
    if handle is None:
        paths['process'].unlink()
        print(json.dumps({'owned_process': False, 'state': 'exited'}))
        return
    try:
        if not stop:
            print(json.dumps({'owned_process': True, 'state': state.get('status'), 'runtime': state.get('runtime'), 'port': PORT}))
            return
        if not ops.kernel.TerminateProcess(handle, 0) or not ops.exited(handle, 10000):
            raise LocalError('Verified local process did not stop; receipt retained.')
        paths['process'].unlink()
        atomic_json(paths['state'] / 'last-stop.json', {'stopped_at': datetime.now(timezone.utc).isoformat(),
            'process': state['process'], 'source_sha256': state['source_sha256'], 'verified': True})
        print(json.dumps({'stopped': True, 'persistent_data_retained': True}))
    finally:
        ops.close(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'start', 'status', 'stop', 'internal-serve'))
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--runtime', choices=('waitress', 'runserver'))
    parser.add_argument('--launch-id')
    parser.add_argument('--dataset', choices=('bos3', 'bos4'),
                        help='Synthetic dataset for a fresh init only (default: bos3).')
    args = parser.parse_args()
    if args.dataset is not None and args.action != 'init':
        raise LocalError('--dataset is allowed only for a fresh init; existing profiles cannot be switched.')
    source = args.source.resolve()
    if source != SOURCE.resolve():
        raise LocalError('Use the launcher from the exact accepted source directory.')
    paths = instance_paths(args.root)
    if args.action == 'init':
        initialize(paths, source, args.dataset or 'bos3')
    elif args.action == 'start':
        start(paths, source)
    elif args.action == 'internal-serve':
        if not args.runtime:
            raise LocalError('Internal local-server runtime is required.')
        internal_serve(paths, source, args.runtime, args.launch_id)
    else:
        status_or_stop(paths, args.action == 'stop')


if __name__ == '__main__':
    try:
        main()
    except LocalError as error:
        print('BOS3_LOCAL_REFUSED: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
