"""Synthetic check of the local PowerShell launch boundary."""

import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

from scripts import bos3_local


class LaunchPolicyTests(unittest.TestCase):
    def test_native_launch_preserves_spec_without_policy_override_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            logs = Path(temporary)
            paths = {'logs': logs}
            cwd = Path('D:/synthetic/source')
            env = {'SYNTHETIC': 'input'}
            native_env = {'SYNTHETIC': 'native'}
            args = ['-X', 'utf8', '-B', 'synthetic script.py']
            with mock.patch.object(bos3_local, 'native_windows_powershell_environment',
                    return_value=('powershell.exe', native_env)) as native, \
                    mock.patch.object(bos3_local.subprocess, 'run',
                    return_value=subprocess.CompletedProcess([], 0)) as run:
                bos3_local.launch_via_powershell(args, cwd, env, paths)

            native.assert_called_once_with(env)
            command = run.call_args.args[0]
            self.assertEqual(command[:4],
                ['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand'])
            self.assertEqual(len(command), 5)
            script = base64.b64decode(command[4]).decode('utf-16-le')
            self.assertNotIn('Bypass', script)
            self.assertNotIn('ExecutionPolicy', script)
            self.assertIn('Start-Process', script)
            self.assertIn('-WindowStyle Hidden -PassThru', script)
            embedded = re.search(r"FromBase64String\('([A-Za-z0-9+/=]+)'\)", script).group(1)
            spec = json.loads(base64.b64decode(embedded).decode('utf-8'))
            self.assertEqual(spec, {
                'python': str(Path(bos3_local.sys.executable).resolve()),
                'cwd': str(cwd),
                'argument_line': subprocess.list2cmdline(args),
                'stdout': str(logs / 'server.stdout.log'),
                'stderr': str(logs / 'server.stderr.log'),
            })
            self.assertEqual(run.call_args.kwargs['env'], native_env)
            self.assertEqual(run.call_args.kwargs['stdin'], subprocess.DEVNULL)
            self.assertEqual(run.call_args.kwargs['stdout'], subprocess.DEVNULL)
            self.assertEqual(run.call_args.kwargs['stderr'].name,
                str(logs / 'server-launch.stderr.log'))
            self.assertEqual(run.call_args.kwargs['timeout'], 30)
            with mock.patch.object(bos3_local, 'native_windows_powershell_environment',
                    return_value=('powershell.exe', native_env)), \
                    mock.patch.object(bos3_local.subprocess, 'run',
                    return_value=subprocess.CompletedProcess([], 1)):
                with self.assertRaisesRegex(bos3_local.LocalError,
                        'Hidden local server process could not be created'):
                    bos3_local.launch_via_powershell(args, cwd, env, paths)


class ConnectorReadingTests(unittest.TestCase):
    def test_the_served_process_starts_its_own_connector_reader_before_serving(self):
        # Synthetic stand-ins: no Django, no socket, no gate files. Only the order inside internal_serve.
        order = []
        reader = types.ModuleType('connectors.periodic')
        reader.start = lambda: order.append('reader')
        waitress = types.ModuleType('waitress')
        waitress.serve = lambda application, **options: order.append(('serve', options['host'], options['port']))
        wsgi = types.ModuleType('boss_project.wsgi')
        wsgi.application = object()
        with mock.patch.object(bos3_local, 'wait_for_child_gate'), \
                mock.patch.object(bos3_local, 'digest_source', return_value='synthetic-digest'), \
                mock.patch.object(bos3_local, 'read_json',
                                  return_value={'launch_id': 'synthetic-launch', 'source_sha256': 'synthetic-digest'}), \
                mock.patch.dict(os.environ, {'BOS3_LOCAL_SOURCE_DIGEST': 'synthetic-digest'}), \
                mock.patch.dict(sys.modules, {'connectors.periodic': reader, 'waitress': waitress,
                                              'boss_project.wsgi': wsgi}), \
                mock.patch.object(sys, 'path', list(sys.path)):
            sys.modules.pop('connectors', None)
            bos3_local.internal_serve({'process': Path('synthetic-receipt.json')}, Path('synthetic-source'),
                                      'waitress', 'synthetic-launch')
        self.assertEqual(order, ['reader', ('serve', '127.0.0.1', bos3_local.PORT)])


if __name__ == '__main__':
    unittest.main()
