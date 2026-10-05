"""One synthetic profile check; no Django, databases, ACL changes or processes."""
import contextlib
import io
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import bos3_local as local


class LocalProfileTests(unittest.TestCase):
    def test_fresh_init_default_and_bos4_seed_and_environment(self):
        for dataset in ('bos3', 'bos4'):
            with self.subTest(dataset=dataset), tempfile.TemporaryDirectory() as temporary:
                paths = local.instance_paths(Path(temporary) / 'instance')
                with mock.patch.object(local, 'protect_path') as acl, \
                        mock.patch.object(local, 'localhost_port_is_free') as port, \
                        mock.patch.object(local, 'digest_source', return_value='synthetic-digest'), \
                        mock.patch.object(local.secrets, 'token_urlsafe', return_value='x' * 64), \
                        mock.patch.object(local.secrets, 'token_hex', return_value='synthetic'), \
                        mock.patch.object(local.subprocess, 'run',
                            return_value=subprocess.CompletedProcess([], 0, stdout='synthetic')) as run, \
                        contextlib.redirect_stdout(io.StringIO()):
                    if dataset == 'bos3':
                        local.initialize(paths, local.SOURCE)
                    else:
                        local.initialize(paths, local.SOURCE, dataset)
                prepared = local.read_json(paths['prepared'])
                self.assertEqual(prepared['dataset'], dataset)
                self.assertEqual(prepared['fixture_id'], local.DATASET_FIXTURES[dataset])
                self.assertEqual(run.call_count, 3)
                seed = run.call_args.args[0][5:]
                expected = (['seed_bos3_fasteners', '--owner-username', prepared['owner_username']]
                            if dataset == 'bos3' else ['seed_bos4_demo'])
                self.assertEqual(seed, expected)
                env = run.call_args.kwargs['env']
                self.assertEqual(env['BOS3_LOCAL_DATASET'], dataset)
                self.assertEqual(env['BOS3_TRAINING_ENABLED'], '1' if dataset == 'bos3' else '0')
                self.assertEqual(env['BOS3_LOCAL_PORT'], '8030')
                self.assertEqual(paths['database'].name, 'bos3-fasteners.sqlite3')
                self.assertFalse(paths['database'].exists())
                self.assertFalse(prepared['owner_is_staff'])
                self.assertFalse(prepared['owner_is_superuser'])
                port.assert_called_once_with()
                self.assertEqual(acl.call_count, 8)

    def test_legacy_receipt_defaults_and_ambient_profile_cannot_override_it(self):
        prepared = {'fixture_id': local.FIXTURE_ID, 'installation_id': 'synthetic',
                    'owner_username': 'synthetic-owner'}
        with mock.patch.object(local, 'read_json', return_value=prepared), \
                mock.patch.object(local, 'digest_source', return_value='synthetic-digest'), \
                mock.patch.dict(os.environ, {'BOS3_LOCAL_DATASET': 'bos4', 'BOS3_TRAINING_ENABLED': '0'}):
            env = local.environment(local.instance_paths('D:/synthetic/instance'), local.SOURCE, 'x' * 64)
        self.assertEqual(env['BOS3_LOCAL_DATASET'], 'bos3')
        self.assertEqual(env['BOS3_TRAINING_ENABLED'], '1')

    def test_settings_require_persisted_profile_and_matching_environment(self):
        base = types.ModuleType('demo_settings')
        base.BASE_DIR = local.SOURCE
        root = Path('D:/synthetic/instance').resolve()
        env = {'BOS3_LOCAL_ROOT': str(root), 'BOS3_LOCAL_SOURCE': str(local.SOURCE),
               'BOS3_LOCAL_DB': str(root / 'data' / 'bos3-fasteners.sqlite3'),
               'BOS3_LOCAL_MEDIA': str(root / 'media'), 'BOS3_LOCAL_SECRET': 'x' * 64}
        for dataset, prepared in (('bos3', {}), ('bos4', {'dataset': 'bos4'})):
            with self.subTest(dataset=dataset), mock.patch.dict(sys.modules, {'demo_settings': base}), \
                    mock.patch.object(local, 'read_json', return_value=prepared) as read, \
                    mock.patch.dict(os.environ, {**env, 'BOS3_LOCAL_DATASET': dataset,
                        'BOS3_TRAINING_ENABLED': '1' if dataset == 'bos3' else '0'}, clear=True):
                settings = runpy.run_path(str(local.SOURCE / 'bos3_local_settings.py'))
                self.assertEqual(settings['BOS3_LOCAL_DATASET'], dataset)
                self.assertEqual(settings['BOS3_TRAINING_ENABLED'], dataset == 'bos3')
                read.assert_called_once_with(root / 'state' / 'prepared.json')
        with mock.patch.dict(sys.modules, {'demo_settings': base}), \
                mock.patch.object(local, 'read_json', return_value={'dataset': 'bos4'}), \
                mock.patch.dict(os.environ, {**env, 'BOS3_LOCAL_DATASET': 'bos3'}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'persisted profile'):
                runpy.run_path(str(local.SOURCE / 'bos3_local_settings.py'))

    def test_invalid_profile_refuses_before_mutation(self):
        for dataset in ('unknown', None, [], True):
            with self.subTest(dataset=dataset), mock.patch.object(Path, 'mkdir') as mkdir, \
                    mock.patch.object(local, 'protect_path') as acl, \
                    mock.patch.object(local.subprocess, 'run') as run, \
                    mock.patch.object(local, 'localhost_port_is_free') as port:
                with self.assertRaises(local.LocalError):
                    local.initialize(local.instance_paths('D:/synthetic/absent'), local.SOURCE, dataset)
                for untouched in (mkdir, acl, run, port):
                    untouched.assert_not_called()

    def test_inconsistent_receipt_refuses_environment_and_start_before_private_reads(self):
        for prepared in ({'dataset': 'bos4', 'fixture_id': local.FIXTURE_ID},
                         {'fixture_id': local.DATASET_FIXTURES['bos4']}, {'dataset': 'unknown'}):
            with self.subTest(prepared=prepared), \
                    mock.patch.object(local, 'read_json', return_value=prepared) as read, \
                    mock.patch.object(local, 'digest_source') as digest, \
                    mock.patch.object(local, 'localhost_port_is_free') as port, \
                    mock.patch.object(local.subprocess, 'run') as run:
                paths = local.instance_paths('D:/synthetic/instance')
                with self.assertRaises(local.LocalError):
                    local.start(paths, local.SOURCE)
                read.assert_called_once_with(paths['prepared'])
                read.reset_mock()
                with self.assertRaises(local.LocalError):
                    local.environment(paths, local.SOURCE, 'synthetic')
                read.assert_called_once_with(paths['prepared'])
                for untouched in (digest, port, run):
                    untouched.assert_not_called()

    def test_existing_root_is_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = local.instance_paths(temporary)
            sentinel = paths['root'] / 'sentinel.json'
            original = b'{"dataset":"bos3","password":"synthetic","progress":7}\n'
            sentinel.write_bytes(original)
            with mock.patch.object(local, 'protect_path') as acl, \
                    mock.patch.object(local, 'localhost_port_is_free') as port, \
                    mock.patch.object(local.subprocess, 'run') as run:
                with self.assertRaisesRegex(local.LocalError, 'already exists'):
                    local.initialize(paths, local.SOURCE, 'bos4')
                for untouched in (acl, port, run):
                    untouched.assert_not_called()
            self.assertEqual(sentinel.read_bytes(), original)
            self.assertEqual(list(paths['root'].iterdir()), [sentinel])

    def test_dataset_option_cannot_switch_an_existing_instance(self):
        for action in ('start', 'status', 'stop', 'internal-serve'):
            with self.subTest(action=action), mock.patch.object(sys, 'argv',
                    ['bos3_local.py', action, '--dataset', 'bos4']), \
                    mock.patch.object(local, 'instance_paths') as paths:
                with self.assertRaisesRegex(local.LocalError, 'fresh init'):
                    local.main()
                paths.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
