"""A09 SRV01-03 subprocess contract. Synthetic paths only; never opens a DB/socket.

Run with --source REPO --draft DRAFT for the unintegrated candidate, or omit
--draft to test the actual checkout. The latter is red before A09 is integrated.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid


def worker():
    # Audit instrumentation is a safety observer, not a substituted DB/socket.
    attempts = []
    def audit(event, args):
        if event in ('sqlite3.connect', 'socket.bind', 'socket.connect'):
            attempts.append(event)
            raise RuntimeError('A09 diagnostic refuses DB and socket access')
    sys.addaudithook(audit)
    case = json.loads(os.environ.get('A09_CASE', '{}'))
    result = {'attempts': attempts}
    try:
        if case.get('path_alias'):
            from boss_project.server_config import _locations
            root = Path(os.environ['BOS_INSTALLATION_ROOT'])
            alias = Path('/' + str(root))
            result['source_alias_samefile'] = os.path.samefile(alias, root)
            _locations(alias, alias / 'data' / 'bos.sqlite3', alias / 'private', alias / 'static', root)
            raise AssertionError('Source root alias was admitted')
        if case.get('mutation'):
            import server_settings as configured
            key, value = case['mutation']
            if key == 'permissions':
                configured.REST_FRAMEWORK = {**configured.REST_FRAMEWORK, 'DEFAULT_PERMISSION_CLASSES': value}
            elif key == 'authentication':
                configured.REST_FRAMEWORK = {**configured.REST_FRAMEWORK, 'DEFAULT_AUTHENTICATION_CLASSES': value}
            elif key == 'remove_middleware':
                configured.MIDDLEWARE = [m for m in configured.MIDDLEWARE if m != value]
            else:
                setattr(configured, key, value)
        from boss_project.server_wsgi import application
        from django.conf import settings
        result.update(status='started', callable=callable(application), mode=settings.BOS_DATA_MODE,
                      cookie=settings.SESSION_COOKIE_NAME, secret_sha=hashlib.sha256(settings.SECRET_KEY.encode()).hexdigest(),
                      settings=settings.SETTINGS_MODULE, installed_apps=len(settings.INSTALLED_APPS))
        if case.get('proxy'):
            from django.http import JsonResponse
            from django.test import RequestFactory
            from boss_project.server_config import TrustedProxyMiddleware
            proxy = case['proxy']
            request = RequestFactory().get('/', REMOTE_ADDR=proxy['peer'],
                HTTP_X_FORWARDED_PROTO=proxy.get('proto', 'https'),
                HTTP_X_FORWARDED_FOR=proxy.get('client', '198.51.100.18'),
                HTTP_X_FORWARDED_HOST='hostile.invalid', HTTP_FORWARDED='host=hostile.invalid;proto=https')
            response = TrustedProxyMiddleware(lambda r: JsonResponse({
                'secure': r.is_secure(), 'client': r.META.get('REMOTE_ADDR'),
                'forwarded_host': r.META.get('HTTP_X_FORWARDED_HOST'),
                'forwarded': r.META.get('HTTP_FORWARDED')}))(request)
            result['proxy'] = {'status': response.status_code, 'body': json.loads(response.content)}
        import demo_settings as local
        result['local'] = {'secret_unchanged': local.SECRET_KEY == 'local-demo-only',
                           'guard_unchanged': local.MIDDLEWARE[0] == 'boss_project.demo_middleware.LocalDemoGuard',
                           'permission_unchanged': local.REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES'] == ['rest_framework.permissions.IsAuthenticated']}
    except Exception as error:
        result.update(status='refused', exception=type(error).__name__)
        if type(error).__name__ == 'ImproperlyConfigured':
            result['reason'] = str(error)
    print(json.dumps(result, ensure_ascii=False))


SOURCE = Path(__file__).resolve().parents[1]
DRAFT = None
EVIDENCE = []


class A09ServerConfigurationTests(unittest.TestCase):
    @staticmethod
    def entries(root):
        # Observe our synthetic tree even when the tested owner cannot traverse
        # it. Restore the exact tested mode before running the real subprocess.
        mode = stat.S_IMODE(root.stat().st_mode)
        try:
            root.chmod(mode | 0o500)
            return sorted(str(p.relative_to(root)) for p in root.rglob('*'))
        finally:
            root.chmod(mode)

    def invoke(self, *, env_changes=None, mutation=None, arrange=None, proxy=None, path_alias=False):
        with tempfile.TemporaryDirectory(prefix='a09-config-') as temporary:
            scratch = Path(temporary)
            installation = scratch / 'installation'
            installation.mkdir(mode=0o700)
            env = {k: v for k, v in os.environ.items() if not k.startswith('BOS_') and k != 'DJANGO_SETTINGS_MODULE'}
            env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', BOS_DATA_MODE='working',
                       BOS_INSTALLATION_ROOT=str(installation), BOS_INSTALLATION_ID=str(uuid.uuid4()),
                       BOS_DATABASE_ENGINE='sqlite3', BOS_DATABASE_PATH=str(installation / 'data' / 'bos.sqlite3'),
                       BOS_MEDIA_ROOT=str(installation / 'private'), BOS_PUBLIC_ORIGIN='https://bos.example.test:8443',
                       BOS_ALLOWED_HOSTS='bos.example.test', BOS_TRUSTED_PROXY_IPS='127.0.0.1,::1',
                       BOS_SECRET_KEY=secrets.token_urlsafe(64))
            if arrange:
                arrange(env, installation, scratch)
            for key, value in (env_changes or {}).items():
                if value is None:
                    env.pop(key, None)
                else:
                    env[key] = value
            python_paths = [str(SOURCE)]
            if DRAFT:
                overlay = scratch / 'overlay'
                package = overlay / 'boss_project'
                package.mkdir(parents=True)
                (package / '__init__.py').write_text('__path__.append(' + repr(str(SOURCE / 'boss_project')) + ')\n')
                for source in (DRAFT / 'boss_project').glob('server_*.py'):
                    shutil.copyfile(source, package / source.name)
                shutil.copyfile(DRAFT / 'server_settings.py', overlay / 'server_settings.py')
                python_paths.insert(0, str(overlay))
            env['PYTHONPATH'] = os.pathsep.join(python_paths)
            env['A09_CASE'] = json.dumps({'mutation': mutation, 'proxy': proxy, 'path_alias': path_alias})
            before = self.entries(installation)
            process = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker'],
                                     cwd=SOURCE, env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(process.returncode, 0, process.stderr[-1000:])
            result = json.loads(process.stdout)
            self.assertEqual(result['attempts'], [], result)
            self.assertEqual(self.entries(installation), before,
                             'Configuration/application creation wrote installation files')
            if env.get('BOS_SECRET_KEY'):
                self.assertNotIn(env['BOS_SECRET_KEY'], process.stdout + process.stderr)
            result['case'] = self._testMethodName
            result['mutation'] = mutation[0] if mutation else None
            result['environment_keys_changed'] = sorted((env_changes or {}).keys())
            EVIDENCE.append(result)
            return result

    def refused(self, **kwargs):
        result = self.invoke(**kwargs)
        self.assertEqual(result['status'], 'refused', result)
        self.assertEqual(result['exception'], 'ImproperlyConfigured', result)
        self.assertTrue(result['reason'].startswith('Сервер BoS не запущено:'), result)

    def test_two_clean_explicit_profiles_create_application_without_io(self):
        first = self.invoke()
        second = self.invoke()
        for result in (first, second):
            self.assertEqual(result['status'], 'started', result)
            self.assertEqual(result['settings'], 'server_settings')
            self.assertEqual(result['mode'], 'working')
            self.assertTrue(result['callable'])
            self.assertTrue(all(result['local'].values()))
        self.assertNotEqual(first['cookie'], second['cookie'])
        self.assertNotEqual(first['secret_sha'], second['secret_sha'])

    def test_missing_demo_and_weak_secrets_refused_before_io(self):
        for value in (None, '', 'local-demo-only', 'synthetic-verification-only', 'A' * 80,
                      'django-insecure-' + secrets.token_urlsafe(64)):
            with self.subTest(value_type='absent' if value is None else 'invalid secret'):
                self.refused(env_changes={'BOS_SECRET_KEY': value})

    def test_wrong_entrypoint_modes_and_backend_refused_before_io(self):
        for key, value in (('DJANGO_SETTINGS_MODULE', 'demo_settings'),
                           ('DJANGO_SETTINGS_MODULE', 'verification_settings'),
                           ('DJANGO_SETTINGS_MODULE', 'boss_project.settings'),
                           ('BOS_DATA_MODE', None), ('BOS_DATA_MODE', 'demo'),
                           ('BOS_DATABASE_ENGINE', None), ('BOS_DATABASE_ENGINE', 'postgresql')):
            with self.subTest(key=key, value=value):
                self.refused(env_changes={key: value})

    def test_empty_wildcard_foreign_hosts_and_invalid_origins_refused(self):
        for key, value in (('BOS_ALLOWED_HOSTS', ''), ('BOS_ALLOWED_HOSTS', '*'),
                           ('BOS_ALLOWED_HOSTS', '.example.test'), ('BOS_ALLOWED_HOSTS', 'other.example.test'),
                           ('BOS_PUBLIC_ORIGIN', 'http://bos.example.test:8443'),
                           ('BOS_PUBLIC_ORIGIN', 'https://user:password@bos.example.test'),
                           ('BOS_PUBLIC_ORIGIN', 'https://bos.example.test/path'),
                           ('BOS_PUBLIC_ORIGIN', 'https://bos.example.test?secret=canary')):
            with self.subTest(key=key, value=value):
                self.refused(env_changes={key: value})

    def test_nonisolated_and_aliased_paths_refused(self):
        cases = [
            lambda e, root, temp: e.update(BOS_INSTALLATION_ROOT='relative'),
            lambda e, root, temp: e.update(BOS_INSTALLATION_ROOT=str(SOURCE)),
            lambda e, root, temp: e.update(BOS_DATABASE_PATH=str(SOURCE / 'db.sqlite3')),
            lambda e, root, temp: e.update(BOS_MEDIA_ROOT=str(SOURCE / 'rehearsal-media')),
            lambda e, root, temp: e.update(BOS_MEDIA_ROOT=str(root / 'static' / 'private')),
            lambda e, root, temp: e.update(BOS_DATABASE_PATH=str(root / 'private' / 'bos.sqlite3')),
        ]
        if os.name == 'posix':
            cases.append(lambda e, root, temp: root.chmod(0o755))
            cases.append(lambda e, root, temp: e.update(BOS_INSTALLATION_ROOT='/' + str(SOURCE)))
        def alias(e, root, temp):
            (temp / 'elsewhere').mkdir()
            (root / 'private').symlink_to(temp / 'elsewhere', target_is_directory=True)
        def hardlink(e, root, temp):
            (root / 'data').mkdir()
            (temp / 'synthetic-empty').write_bytes(b'')
            (root / 'data' / 'bos.sqlite3').hardlink_to(temp / 'synthetic-empty')
        def regular_parent(e, root, temp):
            (root / 'data').write_bytes(b'Synthetic non-database file')
        cases.extend((alias, hardlink, regular_parent))
        for index, arrange in enumerate(cases):
            with self.subTest(index=index):
                self.refused(arrange=arrange)

    def test_effective_configuration_is_checked_after_module_import(self):
        for mutation in (
            ('permissions', ['rest_framework.permissions.AllowAny']),
            ('authentication', []), ('BOS_DATA_MODE', 'demo'), ('DEBUG', True),
            ('SESSION_COOKIE_SECURE', False), ('CSRF_COOKIE_SECURE', False),
            ('SECURE_SSL_HOST', 'hostile.invalid'),
            ('SESSION_COOKIE_NAME', 'sessionid'), ('CSRF_COOKIE_NAME', 'different_csrftoken'),
            ('remove_middleware', 'django.middleware.csrf.CsrfViewMiddleware'),
            ('remove_middleware', 'operations.middleware.LocalRoleGuard'),
            ('MIDDLEWARE', ['boss_project.demo_middleware.LocalDemoGuard']),
        ):
            with self.subTest(key=mutation[0]):
                self.refused(mutation=mutation)

    def test_private_media_cannot_descend_from_database_file(self):
        self.refused(arrange=lambda e, root, temp: e.update(
            BOS_DATABASE_PATH=str(root / 'data'), BOS_MEDIA_ROOT=str(root / 'data' / 'private')))

    def test_actual_source_alias_is_refused_independent_of_directory_mode(self):
        self.refused(path_alias=True)

    def test_root_requires_owner_read_and_search(self):
        self.assertEqual(os.name, 'posix', 'Native Windows ACL acceptance is not implemented; it cannot pass as POSIX proof')
        for mode in (0o000, 0o400, 0o200):
            with self.subTest(mode=oct(mode)):
                self.refused(arrange=lambda e, root, temp, mode=mode: root.chmod(mode))

    def test_readonly_root_with_provisioned_children_is_valid(self):
        def arrange(e, root, temp):
            for name in ('data', 'private', 'static'):
                (root / name).mkdir(mode=0o700)
            if os.name == 'posix':
                root.chmod(0o500)
        result = self.invoke(arrange=arrange)
        self.assertEqual(result['status'], 'started', result)

    def test_proxy_config_requires_explicit_exact_peers(self):
        for peers in ('', '*', '0.0.0.0', '::', '127.0.0.0/8', '127.0.0.1,127.0.0.1'):
            with self.subTest(peers=peers):
                self.refused(env_changes={'BOS_TRUSTED_PROXY_IPS': peers})

    def test_forwarded_headers_apply_only_from_defined_peer(self):
        scenarios = [
            ({'peer': '127.0.0.1'}, 200),
            ({'peer': '203.0.113.19'}, 403),
            ({'peer': '127.0.0.1', 'proto': 'https,http'}, 400),
            ({'peer': '127.0.0.1', 'client': '198.51.100.18,198.51.100.19'}, 400),
        ]
        for proxy, status in scenarios:
            with self.subTest(proxy=proxy):
                result = self.invoke(proxy=proxy)
                self.assertEqual(result['status'], 'started', result)
                self.assertEqual(result['proxy']['status'], status)
                if status == 200:
                    self.assertEqual(result['proxy']['body'], {'secure': True, 'client': '198.51.100.18',
                                                              'forwarded_host': None, 'forwarded': None})


def main():
    global SOURCE, DRAFT
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default=str(SOURCE))
    parser.add_argument('--draft')
    parser.add_argument('--output', required=True)
    args, unittest_args = parser.parse_known_args()
    SOURCE = Path(args.source).resolve()
    DRAFT = Path(args.draft).resolve() if args.draft else None
    program = unittest.main(argv=[sys.argv[0], *unittest_args], exit=False, verbosity=2)
    report = {'date': datetime.now(timezone.utc).isoformat(), 'source': str(SOURCE),
              'draft_overlay': str(DRAFT) if DRAFT else None, 'tests_run': program.result.testsRun,
              'failures': len(program.result.failures), 'errors': len(program.result.errors),
              'successful': program.result.wasSuccessful(), 'probes': EVIDENCE,
              'scope': 'Configuration and in-process WSGI/middleware only; no TLS/HTTP server/install/PG/Windows acceptance'}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return not program.result.wasSuccessful()


if __name__ == '__main__':
    if '--worker' in sys.argv:
        worker()
        raise SystemExit(0)
    raise SystemExit(main())
