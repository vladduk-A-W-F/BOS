"""Ownership boundary tests only; no browser, Django, database, listener or process spawn."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import check_ui
from scripts import ui_process_identity as owner


class ProcessIdentityTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.environ['BOS_RUNNER_TEST_TEMP']).resolve()
        self.base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='identity-unit-', dir=self.base)
        self.root = Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(self.base))
        self.identity = {'pid': 200, 'created_ticks': 987654, 'image': owner.expected_child_image()}

    def tearDown(self):
        self.assertTrue(self.root.is_relative_to(self.base))
        self.temp.cleanup()

    def test_windows_handshake_requires_self_creation_exe_and_nonce(self):
        good = {**self.identity, 'nonce': 'own'}
        self.assertEqual(owner.validate_identity(good, 'own', windows=True), self.identity)
        for delta in ({'created_ticks': None}, {'created_ticks': True}, {'created_ticks': 0},
                      {'image': str(self.root / 'other.exe')}, {'pid': True}, {'nonce': 'stale'}):
            with self.subTest(delta=delta), self.assertRaises(RuntimeError):
                owner.validate_identity({**good, **delta}, 'own', windows=True)

    def test_windows_reused_pid_closes_handle_without_terminating(self):
        kernel = mock.Mock()
        kernel.OpenProcess.return_value = 1234
        with mock.patch.object(owner, 'kernel_api', return_value=kernel), \
                mock.patch.object(owner, 'process_identity', return_value={**self.identity, 'created_ticks': 1}):
            with self.assertRaises(RuntimeError):
                owner.open_verified_windows(self.identity)
        kernel.CloseHandle.assert_called_once_with(1234)
        kernel.TerminateProcess.assert_not_called()

    def test_windows_verified_handle_is_returned_and_not_reopened(self):
        kernel = mock.Mock()
        kernel.OpenProcess.return_value = 1234
        with mock.patch.object(owner, 'kernel_api', return_value=kernel), \
                mock.patch.object(owner, 'process_identity', return_value=self.identity) as identity:
            self.assertEqual(owner.open_verified_windows(self.identity), (kernel, 1234))
        kernel.OpenProcess.assert_called_once()
        identity.assert_called_once_with(kernel, 1234, self.identity['pid'])
        kernel.CloseHandle.assert_not_called()

    def test_posix_requires_direct_popen_pid_and_never_windows_api(self):
        proof = {'pid': 321, 'created_ticks': None, 'image': owner.image_name(check_ui.sys.executable), 'nonce': 'own'}
        with mock.patch.object(owner, 'IS_WINDOWS', False), mock.patch.object(owner, 'kernel_api') as kernel:
            self.assertEqual(owner.validate_identity(proof, 'own', expected_pid=321)['pid'], 321)
            with self.assertRaises(RuntimeError):
                owner.validate_identity(proof, 'own', expected_pid=322)
            current = owner.current_identity()
            self.assertIsNone(current['created_ticks'])
            kernel.assert_not_called()

    def test_child_cannot_return_without_matching_release(self):
        identity_path = self.root / 'identity.json'
        env = {'BOS_UI_SERVER_IDENTITY': str(identity_path), 'BOS_UI_SERVER_NONCE': 'own',
               'BOS_UI_SERVER_PARENT': json.dumps({'pid': 100, 'created_ticks': 12, 'image': self.identity['image']})}
        kernel = mock.Mock()
        with mock.patch.dict(os.environ, env), mock.patch.object(owner, 'current_identity', return_value=self.identity), \
                mock.patch.object(owner, 'IS_WINDOWS', True), \
                mock.patch.object(owner, 'open_verified_windows', return_value=(kernel, 1)), \
                mock.patch.object(owner, 'exited', return_value=False):
            with self.assertRaises(RuntimeError):
                owner.child_handshake(timeout=0)
        self.assertEqual(json.loads(identity_path.read_text()), {**self.identity, 'nonce': 'own'})
        kernel.CloseHandle.assert_called_once_with(1)

    def test_child_rejects_stale_ack_and_keeps_self_proof(self):
        identity_path = self.root / 'identity.json'
        owner.atomic_json(self.root / 'identity-release.json', {**self.identity, 'nonce': 'old'})
        env = {'BOS_UI_SERVER_IDENTITY': str(identity_path), 'BOS_UI_SERVER_NONCE': 'own',
               'BOS_UI_SERVER_PARENT': json.dumps({'pid': 100, 'created_ticks': 12, 'image': self.identity['image']})}
        with mock.patch.dict(os.environ, env), mock.patch.object(owner, 'current_identity', return_value=self.identity), \
                mock.patch.object(owner, 'IS_WINDOWS', True), \
                mock.patch.object(owner, 'open_verified_windows', return_value=(mock.Mock(), 1)), \
                mock.patch.object(owner, 'exited', return_value=False):
            with self.assertRaises(RuntimeError):
                owner.child_handshake(timeout=1)
        self.assertTrue(identity_path.exists())

    def test_interrupt_before_handshake_stops_only_owned_launcher_and_retains_failure(self):
        launcher = mock.Mock(pid=100, _handle=111)
        launcher.poll.return_value = None
        proof = {}
        with mock.patch.object(owner, 'current_identity', return_value=self.identity), \
                mock.patch.object(owner, 'process_identity', return_value=self.identity), \
                mock.patch.object(owner, 'kernel_api', return_value=mock.Mock()), \
                mock.patch.object(check_ui.subprocess, 'Popen', return_value=launcher), \
                mock.patch.object(check_ui.time, 'sleep', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                check_ui.OwnedServer(self.root, {}, 0, None, self.root / 'missing.json', proof)
        self.assertFalse(proof['actual_server_exit_verified'])
        launcher.wait.assert_called()
        self.assertNotIn('ownership_verified_before_application', proof)

    def test_unknown_child_exit_retains_owned_runtime(self):
        report = {'cleanup': {}, 'isolation': {'server_process': {'actual_server_exit_verified': False,
                                                                  'launcher_exit_verified': True}}}
        with mock.patch.object(check_ui.tempfile, 'gettempdir', return_value=str(self.base)), \
                mock.patch.object(check_ui.shutil, 'rmtree') as remove:
            with check_ui.owned_runtime(report) as folder:
                work = Path(folder)
            remove.assert_not_called()
        self.assertTrue(work.exists())
        self.assertIn('runtime_retained_reason', report['cleanup'])
        # Only this test-created empty directory, resolved under its explicit evidence root.
        self.assertEqual(work.resolve().parent, self.base)
        work.rmdir()

    def test_both_exit_proofs_allow_only_exact_owned_runtime_cleanup(self):
        report = {'cleanup': {}, 'isolation': {'server_process': {'actual_server_exit_verified': True,
                                                                  'launcher_exit_verified': True}}}
        with mock.patch.object(check_ui.tempfile, 'gettempdir', return_value=str(self.base)):
            with check_ui.owned_runtime(report) as folder:
                work = Path(folder)
        self.assertFalse(work.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
