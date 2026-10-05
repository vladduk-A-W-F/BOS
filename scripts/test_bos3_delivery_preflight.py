"""Synthetic checks: preflight never mutates state or controls the process."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import bos3_delivery_preflight as preflight


DIGEST = 'a' * 64
SID = 'S-1-5-21-1000'


class DeliveryPreflightTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / 'owner'
        self.source = Path(directory.name) / 'accepted'
        (self.root / 'state').mkdir(parents=True)
        self.source.mkdir()
        self.paths = preflight.local.instance_paths(self.root)
        self.tokens = [str(self.source / 'scripts' / 'bos3_local.py'), 'internal-serve',
                       '--root', str(self.root), '--source', str(self.source),
                       '--runtime', 'waitress', '--launch-id', 'nonce']
        self.record = {'pid': 123, 'created_ticks': 456, 'image': 'python.exe'}
        self.prepared = {'source': str(self.source), 'source_sha256': DIGEST}
        self.receipt = {'schema': 1, 'status': 'ready', 'source': str(self.source),
                        'source_sha256': DIGEST, 'runtime': 'waitress',
                        'port': preflight.local.PORT, 'launch_id': 'nonce',
                        'runtime_image': 'python.exe', 'required_tokens': self.tokens,
                        'process': self.record}
        self.write_receipts()

    def write_receipts(self):
        self.paths['prepared'].write_text(json.dumps(self.prepared), encoding='utf-8')
        self.paths['process'].write_text(json.dumps(self.receipt), encoding='utf-8')

    def run_check(self, *, ps=None, cim='command', argv=None, external_change=None):
        if ps is None:
            ps = mock.Mock(side_effect=['', json.dumps({
                'sid': SID, 'owner_sid': SID, 'elevated': False, 'sddl': 'acl'})])
        ops = mock.Mock()
        ops.open.return_value = object()
        ops.identity.return_value = self.record
        ops.exited.return_value = False
        before = {p.name: p.read_bytes() for p in self.paths['state'].iterdir()}
        def command_probe(*args, **kwargs):
            if isinstance(cim, BaseException):
                raise cim
            if external_change:
                external_change()
                before.clear()
                before.update({p.name: p.read_bytes() for p in self.paths['state'].iterdir()})
            return cim
        cim_probe = mock.Mock(side_effect=command_probe)
        with mock.patch.object(preflight.local, 'digest_source', return_value=DIGEST), \
                mock.patch.object(preflight.local, 'expected_runtime_image', return_value='python.exe'), \
                mock.patch.object(preflight.local, 'WindowsProcess', return_value=ops), \
                mock.patch.object(preflight.local, 'process_command_line', cim_probe) as get_command, \
                mock.patch.object(preflight.prepared_update, '_powershell', ps), \
                mock.patch.object(preflight, '_argv', return_value=argv or [
                    'python.exe', '-X', 'utf8', '-B', *self.tokens]) as parse:
            try:
                result = preflight.check(self.root, self.source, DIGEST)
            finally:
                self.assertEqual(before, {p.name: p.read_bytes() for p in self.paths['state'].iterdir()})
        return result, ps, ops, get_command, parse

    def test_valid_read_only_identity_and_bounded_probes(self):
        result, ps, ops, get_command, _ = self.run_check()
        self.assertEqual(result['owned_waitress_pid'], 123)
        self.assertEqual(ps.call_args_list, [
            mock.call('$null', self.paths['prepared'], timeout=60),
            mock.call(preflight.prepared_update.PREFLIGHT, self.paths['prepared'], timeout=60)])
        get_command.assert_called_once_with(123, timeout=60)
        ops.open.assert_called_once_with(123)
        ops.close.assert_called_once()
        self.assertEqual(ops.exited.call_count, 2)
        self.assertFalse(ops.kernel.TerminateProcess.called)

    def test_forged_receipt_tokens_fail_before_process_probe(self):
        for tokens in ([], ['internal-serve'], self.tokens[:-1]):
            with self.subTest(tokens=tokens):
                self.receipt['required_tokens'] = tokens
                self.write_receipts()
                with self.assertRaises(preflight.PreflightError):
                    self.run_check()

    def test_empty_cim_and_argument_substring_fail_closed(self):
        with self.assertRaises(preflight.PreflightError):
            self.run_check(cim='')
        with self.assertRaises(preflight.PreflightError):
            self.run_check(argv=['python.exe', '-X', 'utf8', '-B',
                                 'prefix' + self.tokens[0], *self.tokens[1:]])

    def test_acl_and_cim_timeout_leave_receipts_untouched(self):
        timeout = subprocess.TimeoutExpired(['powershell'], 60)
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_check(ps=mock.Mock(side_effect=timeout))
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_check(cim=timeout)

    def test_changed_receipts_during_probe_refuse_stale_success(self):
        for key in ('prepared', 'process'):
            with self.subTest(key=key):
                self.write_receipts()
                def change():
                    value = json.loads(self.paths[key].read_bytes())
                    value['source_sha256'] = 'b' * 64
                    self.paths[key].write_text(json.dumps(value), encoding='utf-8')
                with self.assertRaisesRegex(preflight.PreflightError, 'changed during preflight'):
                    self.run_check(external_change=change)

    def test_subprocess_boundary_retains_defaults_and_propagates_timeout(self):
        with mock.patch.object(preflight.prepared_update, 'native_windows_powershell_environment',
                               return_value=('powershell.exe', {})), \
                mock.patch.object(preflight.local, 'native_windows_powershell_environment',
                                  return_value=('powershell.exe', {})), \
                mock.patch.object(subprocess, 'run', return_value=mock.Mock(returncode=0, stdout='ok')) as run:
            preflight.prepared_update._powershell('read', self.paths['prepared'])
            self.assertEqual(run.call_args.kwargs['timeout'], 15)
            preflight.local.process_command_line(123)
            self.assertEqual(run.call_args.kwargs['timeout'], 15)
            before = {p.name: p.read_bytes() for p in self.paths['state'].iterdir()}
            run.side_effect = subprocess.TimeoutExpired(['powershell'], 60)
            for probe in (lambda: preflight.prepared_update._powershell('read', self.paths['prepared'], timeout=60),
                          lambda: preflight.local.process_command_line(123, timeout=60)):
                with self.assertRaises(subprocess.TimeoutExpired):
                    probe()
                self.assertEqual(run.call_args.kwargs['timeout'], 60)
            self.assertEqual(before, {p.name: p.read_bytes() for p in self.paths['state'].iterdir()})


if __name__ == '__main__':
    unittest.main()
