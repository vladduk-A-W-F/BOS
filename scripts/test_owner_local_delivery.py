"""Owner-local delivery steps on a synthetic installation: no Windows, no server, no owner data.

The installation is migrated by the real manage.py through bos3_local, at the state of the installed 9748b86
(connectors without 0003). PowerShell-only parts (ACL, prepared.json replacement) are replaced by stand-ins.
"""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

from scripts import bos3_local as local
from scripts import owner_local_delivery as delivery

DIGEST = 'f' * 64
SECRET = 'synthetic-' + 'x' * 60
PASSWORD = 'pbkdf2_sha256$synthetic-hash'


def fake_update(path, source, source_sha256):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    data.update(source=source, source_sha256=source_sha256)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


class OwnerLocalDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = Path(tempfile.mkdtemp(prefix='bos-delivery-template-'))
        root = cls.template / 'owner'
        for name in ('data', 'media/docs', 'state', 'logs'):
            (root / name).mkdir(parents=True)
        (root / 'state/prepared.json').write_text(json.dumps({
            'source': str(cls.template / 'installed-source'), 'source_sha256': 'a' * 64, 'dataset': 'bos4',
            'fixture_id': 'bos4-demo-v1.0', 'installation_id': 'synthetic', 'owner_username': 'synthetic-owner',
        }, indent=2) + '\n', encoding='utf-8')
        (root / 'state/runtime-secrets.json').write_text(json.dumps({'django_secret': SECRET}), encoding='utf-8')
        (root / 'state/owner-access.json').write_text(json.dumps({'note': 'synthetic'}), encoding='utf-8')
        (root / 'media/docs/photo.txt').write_text('synthetic media', encoding='utf-8')
        paths = local.instance_paths(root)
        with mock.patch.object(local, 'digest_source', return_value=DIGEST):
            env = local.environment(paths, delivery.SOURCE, SECRET)
            local.managed(['migrate', '--noinput'], env, paths)
            local.managed(['migrate', 'connectors', '0002', '--noinput'], env, paths)
        database = sqlite3.connect(paths['database'])
        database.execute(
            'INSERT INTO auth_user (password, last_login, is_superuser, username, first_name, last_name, email, '
            "is_staff, is_active, date_joined) VALUES (?, NULL, 0, 'synthetic-owner', '', '', '', 0, 1, "
            "'2026-10-01 00:00:00')", (PASSWORD,))
        database.commit()
        database.close()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.template, ignore_errors=True)

    def setUp(self):
        folder = Path(tempfile.mkdtemp(prefix='bos-delivery-'))
        self.addCleanup(shutil.rmtree, folder, True)
        shutil.copytree(self.template / 'owner', folder / 'owner')
        self.paths = local.instance_paths(folder / 'owner')
        for patcher in (mock.patch.object(local, 'digest_source', return_value=DIGEST),
                        mock.patch.object(local, 'localhost_port_is_free', return_value=None)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_sql(self, statement, *values):
        database = sqlite3.connect(self.paths['database'])
        database.execute(statement, values)
        database.commit()
        database.close()

    def test_backup_copies_database_media_and_state_and_refuses_a_running_install(self):
        saved = Path(delivery.backup(self.paths)['backup'])
        self.assertEqual(sorted(p.name for p in saved.iterdir()), sorted([
            'DELIVERY.json', 'FINGERPRINTS.json', 'MANIFEST.json', 'bos3-fasteners.sqlite3', 'media',
            'owner-access.json', 'prepared.json', 'runtime-secrets.json']))
        self.assertIn('media/docs/photo.txt', json.loads((saved / 'MANIFEST.json').read_text(encoding='utf-8')))
        self.assertEqual(delivery.fingerprints(saved / 'bos3-fasteners.sqlite3'),
                         delivery.fingerprints(self.paths['database']))
        self.paths['process'].write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(delivery.DeliveryError, 'process receipt'):
            delivery.backup(self.paths)

    def test_migrate_applies_only_the_allowed_state_migration_and_keeps_data(self):
        saved = delivery.backup(self.paths)['backup']
        with mock.patch.object(delivery, 'ALLOWED_MIGRATIONS', frozenset()):
            with self.assertRaisesRegex(delivery.DeliveryError, 'connectors.0003_connector_url_kind'):
                delivery.migrate(self.paths, saved)
        self.assertNotIn('connectors.0003_connector_url_kind', delivery._applied(self.paths['database']),
                         'a refused plan applies nothing')
        result = delivery.migrate(self.paths, saved)
        self.assertEqual((result['applied'], result['integrity']), (['connectors.0003_connector_url_kind'], 'ok'))
        self.assertIn('connectors.0003_connector_url_kind', delivery._applied(self.paths['database']))
        self.assertEqual(delivery.migrate(self.paths, saved)['applied'], [], 'a repeated step has nothing to do')

    def test_bind_changes_only_the_source_pin(self):
        saved = delivery.backup(self.paths)['backup']
        with mock.patch('scripts.bos3_prepared_update.update_prepared_source', side_effect=fake_update) as update:
            self.assertEqual(delivery.bind(self.paths, saved), {'source': str(delivery.SOURCE), 'source_sha256': DIGEST})
        update.assert_called_once_with(self.paths['prepared'], str(delivery.SOURCE), DIGEST)

        def wider(path, source, source_sha256):
            fake_update(path, source, source_sha256)
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            Path(path).write_text(json.dumps({**data, 'dataset': 'bos3'}), encoding='utf-8')
        with mock.patch('scripts.bos3_prepared_update.update_prepared_source', side_effect=wider), \
                self.assertRaisesRegex(delivery.DeliveryError, 'dataset'):
            delivery.bind(self.paths, saved)

    def test_verify_passes_after_a_sign_in_and_fails_on_a_changed_password(self):
        saved = delivery.backup(self.paths)['backup']
        delivery.migrate(self.paths, saved)
        self.paths['process'].write_text(json.dumps(
            {'status': 'ready', 'source': str(delivery.SOURCE), 'source_sha256': DIGEST}), encoding='utf-8')
        pages = {'/': (200, f'<title>BoS · {delivery._version()} — помічник керівника</title>'),
                 '/api/auth/csrf/': (200, ''), '/mcp/': (404, '')}
        with mock.patch.object(delivery, '_get', side_effect=lambda path: pages[path]):
            self.assertEqual(delivery.verify(self.paths, saved)['result'], 'PASS')
            self.run_sql("UPDATE auth_user SET last_login = '2026-10-10 08:00:00'")
            self.run_sql("INSERT INTO django_session VALUES ('synthetic', 'synthetic', '2026-11-01 00:00:00')")
            self.assertEqual(delivery.verify(self.paths, saved)['result'], 'PASS', 'a sign-in is not a data change')
            self.run_sql("UPDATE auth_user SET password = 'pbkdf2_sha256$changed'")
            result = delivery.verify(self.paths, saved)
        self.assertEqual(result['result'], 'FAIL')
        self.assertFalse(result['checks']['owner_password_unchanged'])
        self.assertIn('auth_user: content differs (1 -> 1 rows)', result['problems'])

    def test_rollback_restores_database_media_and_the_installed_pin(self):
        saved = Path(delivery.backup(self.paths)['backup'])
        delivery.migrate(self.paths, saved)
        with mock.patch('scripts.bos3_prepared_update.update_prepared_source', side_effect=fake_update):
            delivery.bind(self.paths, saved)
            self.run_sql('DELETE FROM auth_user')
            (self.paths['media'] / 'docs' / 'after-backup.txt').write_text('new', encoding='utf-8')
            self.paths['process'].write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(delivery.DeliveryError, 'process receipt'):
                delivery.rollback(self.paths, saved)
            self.paths['process'].unlink()
            result = delivery.rollback(self.paths, saved)
        self.assertEqual(result['result'], 'PASS', result)
        self.assertEqual(delivery.fingerprints(self.paths['database']),
                         json.loads((saved / 'FINGERPRINTS.json').read_text(encoding='utf-8')))
        self.assertNotIn('connectors.0003_connector_url_kind', delivery._applied(self.paths['database']))
        self.assertFalse((self.paths['media'] / 'docs' / 'after-backup.txt').exists())
        self.assertTrue((Path(result['replaced_media_kept_in']) / 'docs' / 'after-backup.txt').exists())
        self.assertEqual(json.loads(self.paths['prepared'].read_text(encoding='utf-8')),
                         json.loads((saved / 'prepared.json').read_text(encoding='utf-8')))
        journal = json.loads((saved / 'DELIVERY.json').read_text(encoding='utf-8'))
        self.assertEqual([entry['step'] for entry in journal], ['backup', 'migrate', 'bind', 'rollback'])

    def test_the_command_line_needs_the_backup_and_never_prints_secrets(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            delivery.main(['migrate', '--root', str(self.paths['root'])])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(delivery.main(['backup', '--root', str(self.paths['root'])]), 0)
            saved = json.loads(out.getvalue())['backup']
            self.assertEqual(delivery.main(['migrate', '--root', str(self.paths['root']), '--backup', saved]), 0)
            self.assertEqual(delivery.main(['inspect', '--root', str(self.paths['root'])]), 0)
        printed = out.getvalue()
        self.assertNotIn(SECRET, printed)
        self.assertNotIn(PASSWORD, printed)
        self.assertIn(delivery._version(), printed)


if __name__ == '__main__':
    unittest.main()
