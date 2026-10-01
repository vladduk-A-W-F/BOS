"""Synthetic check of the local PowerShell launch boundary."""

import base64
import json
from pathlib import Path
import re
import subprocess
import tempfile
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


if __name__ == '__main__':
    unittest.main()
