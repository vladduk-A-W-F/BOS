"""Pure synthetic checks for the prepared source update boundary."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import bos3_prepared_update as update


SID = 'S-1-5-21-1000'
SDDL = 'O:S-1-5-21-1000G:S-1-5-21-1000D:(A;;FA;;;S-1-5-21-1000)'
DIGEST = 'a' * 64


class PreparedUpdateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'prepared.json'
        self.original = {'source': 'old', 'source_sha256': 'b' * 64,
                         'installation_id': 'synthetic', 'nested': {'progress': 3}}
        self.path.write_text(json.dumps(self.original), encoding='utf-8')

    def mock_native(self, base_env):
        self.assertEqual(base_env['BOS3_PREPARED_PATH'], str(self.path))
        self.assertEqual(next(value for key, value in base_env.items()
                              if key.upper() == 'PSMODULEPATH'), 'PS7-pollution')
        native_env = {key.upper(): value for key, value in base_env.items()}
        native_env['PSMODULEPATH'] = 'native-only'
        return 'native-powershell', native_env

    def run_boundary(self, *, elevated=False, owner=SID, temp_sddl=SDDL):
        events = []

        def fake_run(command, **kwargs):
            self.assertEqual(command[:3], ['native-powershell', '-NoProfile', '-NonInteractive'])
            self.assertEqual(kwargs['env']['PSMODULEPATH'], 'native-only')
            self.assertNotIn('PSModulePath', kwargs['env'])
            script = command[4]
            if script == update.PREFLIGHT:
                events.append('preflight')
                output = json.dumps({'sid': SID, 'owner_sid': owner,
                                     'elevated': elevated, 'sddl': SDDL})
            elif script == update.COPY_ACL:
                events.append('copy_acl')
                temporary = Path(kwargs['env']['BOS3_PREPARED_TEMP'])
                self.assertTrue(temporary.exists())
                self.assertEqual(temporary.stat().st_size, 0)
                output = ''
            elif script == update.TEMP_SDDL:
                events.append('temp_acl')
                output = temp_sddl
            elif script == update.FILE_SDDL:
                events.append('file_acl')
                output = SDDL
            else:
                self.fail('Unexpected PowerShell command')
            return subprocess.CompletedProcess(command, 0, stdout=output)

        real_replace = os.replace

        def replace(source, destination):
            events.append('replace')
            return real_replace(source, destination)

        with mock.patch.dict(os.environ, {'PSModulePath': 'PS7-pollution'}), \
                mock.patch.object(update, 'native_windows_powershell_environment',
                                  side_effect=self.mock_native), \
                mock.patch.object(update.subprocess, 'run', side_effect=fake_run), \
                mock.patch.object(update.os, 'replace', side_effect=replace):
            if elevated or owner != SID or temp_sddl != SDDL:
                with self.assertRaises(update.PreparedUpdateError):
                    update.update_prepared_source(self.path, 'new', DIGEST)
            else:
                self.assertTrue(update.update_prepared_source(self.path, 'new', DIGEST))
        return events

    def test_elevated_and_other_owner_refuse_before_temp(self):
        for options in ({'elevated': True}, {'owner': 'S-1-5-32-544'}):
            with self.subTest(options=options):
                self.assertEqual(self.run_boundary(**options), ['preflight'])
                self.assertEqual(json.loads(self.path.read_text(encoding='utf-8')), self.original)
                self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_success_uses_native_module_env_and_changes_only_two_fields(self):
        self.assertEqual(self.run_boundary(),
                         ['preflight', 'copy_acl', 'temp_acl', 'file_acl', 'replace', 'file_acl'])
        expected = dict(self.original, source='new', source_sha256=DIGEST)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8')), expected)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_acl_mismatch_leaves_original_and_cleans_empty_temp(self):
        self.assertEqual(self.run_boundary(temp_sddl='different'),
                         ['preflight', 'copy_acl', 'temp_acl'])
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8')), self.original)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


if __name__ == '__main__':
    unittest.main()
