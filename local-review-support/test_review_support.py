"""Targeted stdlib tests. All process/HTTP boundaries are mocked; no Django or network."""
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import review_control as control
from review_process import Lifecycle, OwnershipError, Windows, atomic_json, child_gate, image_name, read_json
from review_secrets import runtime_root, CODE_ROOT


class FakeWindows:
    def __init__(self, launcher, child):
        self.records = {
            10: {'pid': 10, 'created_ticks': 100, 'image': image_name(child)},
            20: {'pid': 20, 'created_ticks': 200, 'image': image_name(launcher)},
            30: {'pid': 30, 'created_ticks': 300, 'image': image_name(child)},
        }
        self.dead = set()
        self.closed = []
        self.killed = []
        self.busy = False

    @contextmanager
    def lock(self, root):
        if self.busy:
            raise OwnershipError('Concurrent lifecycle operation')
        self.busy = True
        try:
            yield
        finally:
            self.busy = False

    def current(self):
        return dict(self.records[10])

    def identity(self, handle, pid):
        return dict(self.records[handle])

    def open_verified(self, expected, expected_image, terminate=False):
        if not expected or expected['image'] != image_name(expected_image):
            raise OwnershipError('Unknown or wrong executable')
        pid = expected['pid']
        if self.records.get(pid) != expected:
            raise OwnershipError('PID identity changed')
        return pid

    def open_pid(self, pid, terminate=False):
        return pid if pid in self.records else None

    def wait(self, handle, milliseconds=0):
        return handle is None or handle in self.dead

    def terminate(self, handle):
        if not self.wait(handle):
            self.killed.append(handle)
            self.dead.add(handle)

    def close(self, handle):
        self.closed.append(handle)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        owned = Path(os.environ['BOS_SUPPORT_TEST_TEMP']).resolve()
        owned.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='unit-', dir=owned)
        self.root = Path(self.temp.name)
        self.owned_temp = owned
        self.assertTrue(self.root.resolve().is_relative_to(self.owned_temp))
        self.launcher = self.root / 'venv/python.exe'
        self.child = self.root / 'base/python.exe'
        self.ops = FakeWindows(self.launcher, self.child)
        self.mode = 'normal'
        self.spawn_calls = 0
        self.lifecycle = Lifecycle(self.root, [self.launcher, '-B', 'owned.py'], self.child,
                                   windows=self.ops, spawn=self.spawn)
        (self.root / 'data').mkdir()
        (self.root / 'media').mkdir()
        (self.root / 'data/sentinel.txt').write_text('persistent synthetic data')
        (self.root / 'media/sentinel.txt').write_text('persistent synthetic media')

    def tearDown(self):
        # TemporaryDirectory is this test's own exact directory, never a product runtime.
        self.assertTrue(self.root.resolve().is_relative_to(self.owned_temp))
        self.temp.cleanup()

    def proof(self, state):
        return {'nonce': state['nonce'], 'child': dict(self.ops.records[30]),
                'launcher': dict(self.ops.records[20])}

    def spawn(self, command, **kwargs):
        self.spawn_calls += 1
        state = read_json(self.lifecycle.state_path)
        self.assertTrue(state['launch_attempted'])
        self.assertEqual(kwargs['env']['BOS_REVIEW_PROCESS_NONCE'], state['nonce'])
        self.assertFalse((self.lifecycle.run_dir(state) / 'release.json').exists())
        if self.mode == 'interrupt_before_handshake':
            raise KeyboardInterrupt()
        if self.mode == 'error_before_handshake':
            raise OSError('mock CreateProcess/start failure')
        if self.mode != 'no_handshake':
            proof = self.proof(state)
            if self.mode == 'wrong_nonce':
                proof['nonce'] = 'f' * 48
            if self.mode == 'wrong_exe':
                proof['child']['image'] = image_name(self.root / 'other.exe')
            if self.mode == 'reused_pid':
                proof['child']['created_ticks'] -= 1
            atomic_json(self.lifecycle.run_dir(state) / 'child.json', proof)
        return Mock(pid=20, _handle=20, poll=Mock(return_value=None))

    def start(self, readiness=lambda alive: alive()):
        return self.lifecycle.start(environment={}, cwd=self.root, log=io.StringIO(),
                                    readiness=readiness, handshake_timeout=0)

    def assert_persistent(self):
        self.assertEqual((self.root / 'data/sentinel.txt').read_text(), 'persistent synthetic data')
        self.assertEqual((self.root / 'media/sentinel.txt').read_text(), 'persistent synthetic media')

    def test_successful_start_remains_alive_and_owned_stop_verifies_pair(self):
        state = self.start()
        self.assertEqual(state['stage'], 'ready')
        self.assertFalse(self.ops.killed)
        self.assertTrue(self.lifecycle.status()['child_running'])
        self.assertEqual(read_json(self.lifecycle.run_dir(state) / 'release.json'), self.proof(state))
        receipt = self.lifecycle.stop()
        self.assertTrue(receipt['child_exit_verified'] and receipt['launcher_exit_verified'])
        self.assertEqual(self.ops.killed, [30, 20])
        self.assertFalse(self.lifecycle.state_path.exists())
        self.assert_persistent()

    def test_second_start_refused_without_spawn_or_overwrite(self):
        self.start()
        original = self.lifecycle.state_path.read_bytes()
        with self.assertRaises(OwnershipError):
            self.start()
        self.assertEqual(self.spawn_calls, 1)
        self.assertEqual(self.lifecycle.state_path.read_bytes(), original)

    def test_concurrent_start_and_stop_refused_by_same_lock(self):
        with self.ops.lock(self.root):
            with self.assertRaises(OwnershipError):
                self.start()
            with self.assertRaises(OwnershipError):
                self.lifecycle.stop()
        self.assertEqual(self.spawn_calls, 0)

    def test_interrupt_before_handshake_retains_pending_then_stop_recovers(self):
        self.mode = 'interrupt_before_handshake'
        with self.assertRaises(KeyboardInterrupt):
            self.start()
        state = read_json(self.lifecycle.state_path)
        self.assertEqual(state['stage'], 'recovery_pending')
        self.assertFalse(self.ops.killed)
        atomic_json(self.lifecycle.run_dir(state) / 'child.json', self.proof(state))
        self.assertTrue(self.lifecycle.stop()['child_exit_verified'])
        self.assert_persistent()

    def test_error_before_handshake_retains_durable_record(self):
        self.mode = 'error_before_handshake'
        with self.assertRaises(OSError):
            self.start()
        state = read_json(self.lifecycle.state_path)
        self.assertEqual(state['failure_type'], 'OSError')
        self.assertEqual(state['stage'], 'recovery_pending')
        with self.assertRaises(OwnershipError):
            self.lifecycle.stop()
        self.assertTrue(self.lifecycle.state_path.exists())
        self.assertFalse(self.ops.killed)

    def test_child_leaves_recoverable_identity_even_after_controller_exits(self):
        self.mode = 'interrupt_before_handshake'
        with self.assertRaises(KeyboardInterrupt):
            self.start()
        state = read_json(self.lifecycle.state_path)
        self.ops.dead.add(10)
        with patch.dict(os.environ, {'BOS_REVIEW_PROCESS_NONCE': state['nonce']}), \
                patch.object(self.ops, 'current', return_value=dict(self.ops.records[30])), \
                patch('review_process.os.getppid', return_value=20):
            with self.assertRaises(OwnershipError):
                child_gate(self.root, windows=self.ops)
        self.assertEqual(read_json(self.lifecycle.run_dir(state) / 'child.json'), self.proof(state))
        self.assertFalse((self.lifecycle.run_dir(state) / 'release.json').exists())
        self.assertTrue(self.lifecycle.stop()['child_exit_verified'])

    def test_handshake_timeout_never_releases_application(self):
        self.mode = 'no_handshake'
        with self.assertRaises(OwnershipError):
            self.start()
        state = read_json(self.lifecycle.state_path)
        self.assertFalse((self.lifecycle.run_dir(state) / 'release.json').exists())
        self.assertFalse(self.ops.killed)

    def test_wrong_nonce_exe_or_creation_time_never_touches_unknown_process(self):
        for mode in ('wrong_nonce', 'wrong_exe', 'reused_pid'):
            with self.subTest(mode=mode):
                self.mode = mode
                with self.assertRaises(OwnershipError):
                    self.start()
                self.assertFalse(self.ops.killed)
                self.assertTrue(self.lifecycle.state_path.exists())
                # Reset only mocked state in this isolated test root, not a real runtime.
                self.lifecycle.state_path.unlink()

    def test_stop_checks_both_identities_before_terminating_either(self):
        self.start()
        self.ops.records[20]['created_ticks'] += 1
        with self.assertRaises(OwnershipError):
            self.lifecycle.stop()
        self.assertFalse(self.ops.killed)
        self.assertTrue(self.lifecycle.state_path.exists())
        self.assert_persistent()

    def test_readiness_failure_cleans_owned_pair_and_retains_data(self):
        def fail(alive):
            alive()
            raise HTTPError('http://127.0.0.1/forbidden', 401, 'unauthorized', None, None)
        with self.assertRaises(HTTPError):
            self.start(fail)
        self.assertEqual(self.ops.killed, [30, 20])
        self.assertFalse(self.lifecycle.state_path.exists())
        self.assert_persistent()

    def test_ctrl_c_after_handshake_cleans_pair(self):
        def interrupt(alive):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.start(interrupt)
        self.assertEqual(self.ops.killed, [30, 20])
        self.assertFalse(self.lifecycle.state_path.exists())


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='http-unit-', dir=os.environ['BOS_SUPPORT_TEST_TEMP'])
        self.root = Path(self.temp.name)
        self.owned_temp = Path(os.environ['BOS_SUPPORT_TEST_TEMP']).resolve()
        self.assertTrue(self.root.resolve().is_relative_to(self.owned_temp))
        (self.root / 'source/assets').mkdir(parents=True)
        (self.root / 'source/assets/app.js').write_bytes(b'accepted asset')

    def tearDown(self):
        self.assertTrue(self.root.resolve().is_relative_to(self.owned_temp))
        self.temp.cleanup()

    def opener(self, auth=None, asset=b'accepted asset'):
        calls = []
        def open_response(url, **kwargs):
            calls.append(url)
            if url.endswith('/api/runtime/status/'):
                raise HTTPError(url, 401, 'working requires login', None, None)
            if url.endswith('/api/auth/csrf/'):
                data = json.dumps(auth if auth is not None else {'mode': 'working', 'authenticated': False}).encode()
            elif url.endswith('/assets/app.js'):
                data = asset
            else:
                data = b'<script src="/assets/app.js"></script>'
            response = io.BytesIO(data)
            response.status = 200
            return response
        return Mock(open=open_response), calls

    def test_public_csrf_works_while_old_runtime_readiness_would_return_401(self):
        opener, calls = self.opener()
        with self.assertRaises(HTTPError):
            opener.open(control.ORIGIN + '/api/runtime/status/')
        calls.clear()
        with patch.object(control, 'ROOT', self.root):
            result = control.probe_http(opener)
        self.assertEqual(result['public_csrf'], 200)
        self.assertEqual(calls, [control.ORIGIN + '/api/auth/csrf/', control.ORIGIN + '/', control.ORIGIN + '/assets/app.js'])

    def test_demo_authenticated_or_changed_asset_never_ready(self):
        for auth, asset in (({'mode': 'demo', 'authenticated': False}, b'accepted asset'),
                            ({'mode': 'working', 'authenticated': True}, b'accepted asset'),
                            ({'mode': 'working', 'authenticated': False}, b'other asset')):
            with self.subTest(auth=auth, asset=asset):
                opener, _ = self.opener(auth, asset)
                with patch.object(control, 'ROOT', self.root), self.assertRaises(RuntimeError):
                    control.probe_http(opener)

    def test_runtime_source_nesting_refused_before_port_or_copy(self):
        for source, runtime in ((self.root, self.root / 'runtime'), (self.root / 'source', self.root)):
            with patch.object(control, 'ROOT', runtime), patch.object(control, 'unused_port') as probe:
                with self.assertRaises(RuntimeError):
                    control.prepare(source, 'not-used')
                probe.assert_not_called()
        with self.assertRaises(ValueError):
            runtime_root(CODE_ROOT / 'runtime')


class WindowsBoundaryTests(unittest.TestCase):
    def test_held_handle_identity_mismatch_closes_without_termination(self):
        ops = Windows.__new__(Windows)
        ops.kernel = Mock()
        ops.kernel.OpenProcess.return_value = 777
        expected = {'pid': 42, 'created_ticks': 123, 'image': image_name('python.exe')}
        ops.identity = Mock(return_value={**expected, 'created_ticks': 124})
        with self.assertRaises(OwnershipError):
            ops.open_verified(expected, expected['image'], terminate=True)
        ops.kernel.CloseHandle.assert_called_once_with(777)
        ops.kernel.TerminateProcess.assert_not_called()

    def test_windows_mutex_timeout_refuses_and_closes_handle(self):
        ops = Windows.__new__(Windows)
        ops.kernel = Mock()
        ops.kernel.CreateMutexW.return_value = 888
        ops.kernel.WaitForSingleObject.return_value = 258
        with self.assertRaises(OwnershipError):
            with ops.lock(Path.cwd()):
                self.fail('A competing lifecycle owner must not be admitted')
        ops.kernel.CloseHandle.assert_called_once_with(888)
        ops.kernel.ReleaseMutex.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
