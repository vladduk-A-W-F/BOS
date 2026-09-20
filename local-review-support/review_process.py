"""Windows ownership for a persistent local child; no JobKillOnClose or PID-only stop."""
from contextlib import contextmanager, ExitStack
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import time


class OwnershipError(RuntimeError):
    pass


def image_name(value):
    return os.path.normcase(str(Path(value).resolve()))


def atomic_json(path, value):
    """Flush content before atomic replacement; never truncate a recoverable state."""
    path = Path(path)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def valid_identity(value, expected_image):
    return (isinstance(value, dict) and set(value) == {'pid', 'created_ticks', 'image'}
            and type(value['pid']) is int and value['pid'] > 0
            and type(value['created_ticks']) is int and value['created_ticks'] > 0
            and isinstance(value['image'], str)
            and image_name(value['image']) == image_name(expected_image))


class Windows:
    def __init__(self):
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        declarations = {
            'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
            'GetCurrentProcess': ([], wintypes.HANDLE),
            'GetProcessTimes': ([wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4, wintypes.BOOL),
            'QueryFullProcessImageNameW': ([wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                           ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            'WaitForSingleObject': ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            'TerminateProcess': ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            'CreateMutexW': ([ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            'ReleaseMutex': ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (args, result) in declarations.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = args, result

    @contextmanager
    def lock(self, root):
        suffix = hashlib.sha256(image_name(root).encode('utf-8')).hexdigest()
        handle = self.kernel.CreateMutexW(None, False, 'Local\\BoSReviewLifecycle-' + suffix)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        acquired = False
        try:
            result = self.kernel.WaitForSingleObject(handle, 0)
            if result == 258:
                raise OwnershipError('Another start/stop/status operation owns this instance.')
            if result not in (0, 128):  # acquired, or abandoned by a previous dead controller
                raise ctypes.WinError(ctypes.get_last_error())
            acquired = True
            yield
        finally:
            if acquired:
                self.kernel.ReleaseMutex(handle)
            self.close(handle)

    def identity(self, handle, pid):
        times = [wintypes.FILETIME() for _ in range(4)]
        if not self.kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        size = wintypes.DWORD(32768)
        name = ctypes.create_unicode_buffer(size.value)
        if not self.kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {'pid': pid, 'created_ticks': (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
                'image': image_name(name.value)}

    def current(self):
        return self.identity(self.kernel.GetCurrentProcess(), os.getpid())

    def open_pid(self, pid, terminate=False):
        handle = self.kernel.OpenProcess(0x1000 | 0x100000 | (1 if terminate else 0), False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:  # PID absent; access denied or other errors are never absence
                return None
            raise ctypes.WinError(error)
        return handle

    def open_verified(self, expected, expected_image, terminate=False):
        if not valid_identity(expected, expected_image):
            raise OwnershipError('Missing or unexpected process identity; no PID-only action allowed.')
        handle = self.open_pid(expected['pid'], terminate)
        if handle is None:
            return None
        try:
            if self.identity(handle, expected['pid']) != expected:
                raise OwnershipError('PID was reused or identity differs; process is not owned.')
            return handle
        except BaseException:
            self.close(handle)
            raise

    def wait(self, handle, milliseconds=0):
        if handle is None:
            return True
        result = self.kernel.WaitForSingleObject(handle, milliseconds)
        if result not in (0, 258):
            raise ctypes.WinError(ctypes.get_last_error())
        return result == 0

    def terminate(self, handle):
        if not self.wait(handle) and not self.kernel.TerminateProcess(handle, 0):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self, handle):
        if handle is not None:
            self.kernel.CloseHandle(handle)


class Lifecycle:
    def __init__(self, root, command, expected_child_image, *, windows=None, spawn=None):
        self.root = Path(root).resolve()
        self.command = [str(value) for value in command]
        self.child_image = image_name(expected_child_image)
        self.launcher_image = image_name(self.command[0])
        self.ops = windows or Windows()
        self.spawn = spawn or subprocess.Popen
        self.state_path = self.root / 'process.json'

    def _state(self):
        state = read_json(self.state_path)
        if (state.get('schema') != 2 or state.get('root') != str(self.root)
                or state.get('command') != self.command
                or state.get('expected_child_image') != self.child_image
                or state.get('expected_launcher_image') != self.launcher_image
                or not isinstance(state.get('nonce'), str) or len(state['nonce']) != 48
                or any(c not in '0123456789abcdef' for c in state['nonce'])):
            raise OwnershipError('Pending ownership record differs; no process touched.')
        return state

    def run_dir(self, state):
        return self.root / 'control' / state['nonce']

    def _save(self, state, stage):
        state['stage'] = stage
        atomic_json(self.state_path, state)

    def _handshake(self, state):
        path = self.run_dir(state) / 'child.json'
        if not path.exists():
            return False
        proof = read_json(path)
        if (proof.get('nonce') != state['nonce']
                or not valid_identity(proof.get('child'), self.child_image)
                or not valid_identity(proof.get('launcher'), self.launcher_image)
                or (state.get('launcher') and proof['launcher'] != state['launcher'])):
            raise OwnershipError('Child handshake nonce, identity or executable differs.')
        # Store the child-reported creation time, not an identity inferred later from a bare PID.
        state.update(child=proof['child'], launcher=proof['launcher'])
        self._save(state, 'identified')
        return True

    @contextmanager
    def _handles(self, state, terminate=False):
        with ExitStack() as stack:
            handles = {}
            for name, image in (('child', self.child_image), ('launcher', self.launcher_image)):
                handle = self.ops.open_verified(state.get(name), image, terminate)
                if handle is not None:
                    stack.callback(self.ops.close, handle)
                handles[name] = handle
            yield handles

    def _stop(self, state):
        if not state.get('child'):
            if not self._handshake(state):
                if not state.get('launch_attempted'):
                    self.state_path.unlink()
                    return {'launch_attempted': False, 'processes_stopped': False}
                self._save(state, 'recovery_pending')
                raise OwnershipError('Child handshake not available; pending state retained. Retry stop after the child gate exits or inspect owned logs; no unknown PID touched.')
        with self._handles(state, terminate=True) as handles:
            self._save(state, 'stopping')
            self.ops.terminate(handles['child'])
            if not self.ops.wait(handles['child'], 10000):
                raise OwnershipError('Owned child has not exited; state retained.')
            # The launcher normally follows its child. Only its verified handle may be stopped.
            if not self.ops.wait(handles['launcher'], 2000):
                self.ops.terminate(handles['launcher'])
            if not self.ops.wait(handles['launcher'], 10000):
                raise OwnershipError('Owned launcher has not exited; state retained.')
            receipt = {'child_exit_verified': True, 'launcher_exit_verified': True,
                       'child': state['child'], 'launcher': state['launcher'],
                       'persistent_data_retained': True, 'nonce': state['nonce']}
            atomic_json(self.run_dir(state) / 'stopped.json', receipt)
            self.state_path.unlink()
            return receipt

    def start(self, *, environment, cwd, log, readiness, preflight=lambda: None, handshake_timeout=10):
        with self.ops.lock(self.root):
            if self.state_path.exists():
                raise OwnershipError('Owned pending/process record exists; use status/stop before start.')
            preflight()
            state = {'schema': 2, 'root': str(self.root), 'command': self.command,
                     'expected_child_image': self.child_image, 'expected_launcher_image': self.launcher_image,
                     'nonce': secrets.token_hex(24), 'controller': self.ops.current(),
                     'launcher': None, 'child': None, 'launch_attempted': False}
            self.run_dir(state).mkdir(parents=True)
            self._save(state, 'pending')  # durable before creating any process
            try:
                env = dict(environment, BOS_REVIEW_PROCESS_NONCE=state['nonce'])
                state['launch_attempted'] = True
                self._save(state, 'launching')
                process = self.spawn(self.command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                launcher = self.ops.identity(process._handle, process.pid)
                if not valid_identity(launcher, self.launcher_image):
                    raise OwnershipError('Launcher executable differs; state retained for inspection.')
                state['launcher'] = launcher
                self._save(state, 'launching')
                deadline = time.monotonic() + handshake_timeout
                while not self._handshake(state):
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise OwnershipError('Child handshake did not arrive; pending state retained.')
                    time.sleep(.05)
                with self._handles(state) as handles:
                    if any(self.ops.wait(handle) for handle in handles.values()):
                        raise OwnershipError('Owned process exited before release; startup refused.')
                    # Hold verified handles throughout acknowledgement and readiness.
                    self._save(state, 'owned')
                    atomic_json(self.run_dir(state) / 'release.json',
                                {'nonce': state['nonce'], 'child': state['child'], 'launcher': state['launcher']})
                    def alive():
                        if any(self.ops.wait(handle) for handle in handles.values()):
                            raise OwnershipError('Owned child or launcher exited during readiness.')
                    readiness(alive)
                    alive()
                    self._save(state, 'ready')
                return state  # closing query handles leaves the persistent server running
            except BaseException as failure:
                # Includes Ctrl+C. No error path discards unproved ownership.
                state['failure_type'] = type(failure).__name__
                try:
                    self._save(state, 'start_failed')
                    self._stop(state)
                except BaseException as cleanup_failure:
                    state['cleanup_failure_type'] = type(cleanup_failure).__name__
                    try:
                        self._save(state, 'recovery_pending')
                    except BaseException:
                        pass  # earlier atomic state and child proof still remain on disk
                raise

    def stop(self):
        with self.ops.lock(self.root):
            if not self.state_path.exists():
                return {'no_owned_record': True, 'persistent_data_retained': True}
            return self._stop(self._state())

    def status(self):
        with self.ops.lock(self.root):
            if not self.state_path.exists():
                return {'no_owned_record': True}
            state = self._state()
            if not state.get('child'):
                return {'stage': state['stage'], 'recovery_pending': True}
            with self._handles(state) as handles:
                return {'stage': state['stage'], 'child_running': not self.ops.wait(handles['child']),
                        'launcher_running': not self.ops.wait(handles['launcher'])}


def child_gate(root, *, timeout=20, windows=None):
    """Before importing Django, self-identify and await a held-handle parent acknowledgement."""
    root = Path(root).resolve()
    ops = windows or Windows()
    state = read_json(root / 'process.json')
    nonce = os.environ.get('BOS_REVIEW_PROCESS_NONCE')
    if nonce != state.get('nonce') or state.get('root') != str(root):
        raise OwnershipError('Child has no matching durable parent intent.')
    current = ops.current()
    if not valid_identity(current, state['expected_child_image']):
        raise OwnershipError('Child executable is not the accepted Python runtime.')
    if os.getppid() == state['controller']['pid']:
        launcher = current  # direct Python invocation, without a venv launcher
    else:
        parent = ops.open_pid(os.getppid())
        if parent is None:
            raise OwnershipError('Venv launcher already exited.')
        try:
            launcher = ops.identity(parent, os.getppid())
        finally:
            ops.close(parent)
    if not valid_identity(launcher, state['expected_launcher_image']):
        raise OwnershipError('Child parent is not the expected launcher executable.')
    proof = {'nonce': nonce, 'child': current, 'launcher': launcher}
    run = root / 'control' / nonce
    # A controller can die immediately after CreateProcess. Leave self-identity
    # before checking its liveness, so a later stop can reconcile the pending record.
    atomic_json(run / 'child.json', proof)
    controller = ops.open_verified(state['controller'], state['controller']['image'])
    if controller is None:
        raise OwnershipError('Controller exited before child ownership was established.')
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if ops.wait(controller):
                raise OwnershipError('Controller exited before releasing the owned child.')
            release = run / 'release.json'
            if release.exists():
                if read_json(release) != proof:
                    raise OwnershipError('Controller acknowledgement differs from child identity.')
                return proof
            time.sleep(.05)
        raise OwnershipError('Ownership acknowledgement timed out; application was not imported.')
    finally:
        ops.close(controller)
