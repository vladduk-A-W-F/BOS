"""SRV10/11 actual subprocess requests on newly created synthetic SQLite only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

SOURCE = Path(__file__).resolve().parents[1]
CONFIG_DRAFT = None
RUNTIME_DRAFT = None
EVIDENCE = []

URL_SOURCE = '''from django.urls import path
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from boss_project.urls import urlpatterns as original
import importlib.util
import logging

urlpatterns = list(original)
if importlib.util.find_spec('boss_project.server_health') is not None:
    from boss_project.server_health import liveness, readiness
    urlpatterns = [path('health/live/', liveness, name='bos-health-live'),
                   path('health/ready/', readiness, name='bos-health-ready')] + urlpatterns

@csrf_exempt
def echo(request):
    log = logging.getLogger('bos.synthetic')
    log.error('Private body %s and headers %s', request.body, request.headers)
    log.warning('Private query %s', request.META.get('QUERY_STRING'),
                extra={'bos_event': {'untrusted': request.GET.get('token')}, 'status_code': 'private'})
    try:
        raise ValueError('private failure ' + request.body.decode('utf-8', errors='replace'))
    except ValueError:
        log.exception('Private traceback')
    return JsonResponse({'ok': True})

@csrf_exempt
def explode(request):
    raise RuntimeError('private server failure ' + request.body.decode('utf-8', errors='replace'))

def host(request):
    request.get_host()
    return JsonResponse({'ok': True})

urlpatterns = [path('__srv11/echo/', echo), path('__srv11/explode/', explode),
               path('__srv11/host/', host)] + urlpatterns
'''


def snapshot(root):
    result = {}
    for path in sorted(root.rglob('*')):
        relative = str(path.relative_to(root))
        result[relative] = {'mode': path.stat().st_mode & 0o777,
            'bytes': path.stat().st_size if path.is_file() else None,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}
    return result


def worker():
    case = os.environ['A09_RUNTIME_CASE']
    canaries = json.loads(os.environ['A09_RUNTIME_CANARIES'])
    phase = 'setup'
    io = []
    statements = []
    def audit(event, args):
        if event in ('socket.bind', 'socket.connect'):
            io.append({'event': event, 'phase': phase})
            raise RuntimeError('SRV10/11 does not start network services')
        if event == 'sqlite3.connect':
            name = str(args[0])
            if phase == 'requests':
                io.append({'event': event, 'phase': phase, 'read_only': name.endswith('?mode=ro')})
    sys.addaudithook(audit)
    # Observe real SQL only after Connection initialization. The connect/handle
    # audit event fires too early to call set_trace_callback on that handle.
    def profile(frame, event, function):
        if phase == 'requests' and event == 'c_call' and getattr(function, '__name__', '') == 'execute':
            import sqlite3
            handle = getattr(function, '__self__', None)
            if isinstance(handle, sqlite3.Connection):
                handle.set_trace_callback(lambda statement: statements.append(statement.split(None, 1)[0].upper()))
    sys.setprofile(profile)
    result = {'case': case}
    try:
        from boss_project.server_wsgi import application
        from django.conf import settings
        from django.core.management import call_command
        from django.db import connections, connection
        from django.test import Client
        root = Path(os.environ['BOS_INSTALLATION_ROOT'])
        database = Path(os.environ['BOS_DATABASE_PATH'])
        media = Path(os.environ['BOS_MEDIA_ROOT'])
        assert database.is_relative_to(root) and media.is_relative_to(root)
        assert not database.exists()
        if case not in ('live_missing', 'ready_missing', 'ready_empty', 'ready_corrupt', 'configuration_refused'):
            call_command('migrate', verbosity=0, interactive=False)
            if case == 'ready_pending':
                from django.db.migrations.loader import MigrationLoader
                leaf = next(node for node in MigrationLoader(connection).graph.leaf_nodes() if node[0] == 'operations')
                with connection.cursor() as cursor:
                    cursor.execute('DELETE FROM django_migrations WHERE app=%s AND name=%s', leaf)
            connections.close_all()
        elif case == 'ready_empty':
            database.write_bytes(b'')
        elif case == 'ready_corrupt':
            database.write_bytes(canaries['database'].encode())
        if case == 'ready_media_missing':
            media.rmdir()
        elif case == 'ready_media_file':
            media.rmdir()
            media.write_bytes(canaries['filename'].encode())
        elif case == 'ready_media_readonly':
            media.chmod(0o500)
        before = snapshot(root)
        phase = 'requests'
        client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        common = {'REMOTE_ADDR': '127.0.0.1', 'HTTP_X_FORWARDED_FOR': '198.51.100.91',
            'HTTP_X_FORWARDED_PROTO': 'https', 'HTTP_HOST': 'bos.example.test:8443',
            'HTTP_AUTHORIZATION': 'Bearer ' + canaries['authorization'],
            'HTTP_X_BOS_REQUEST_ID': canaries['correlation'], 'HTTP_COOKIE': 'private=' + canaries['cookie']}
        answers = []
        def request(method, path, data=None, **overrides):
            options = {**common, **overrides}
            response = getattr(client, method)(path, data=data or {}, content_type='application/json', **options)
            content = response.content
            try:
                body = json.loads(content)
            except (ValueError, UnicodeError):
                body = None
            answers.append({'method': method, 'status': response.status_code, 'body': body,
                'correlation': response.get('X-BoS-Request-ID'), 'cache_control': response.get('Cache-Control'),
                'allow': response.get('Allow'), 'response_sha256': hashlib.sha256(content).hexdigest()})
        if case.startswith('ready_'):
            request('get', '/health/ready/')
        elif case == 'live_missing':
            request('get', '/health/live/')
        elif case == 'methods':
            for endpoint in ('/health/live/', '/health/ready/'):
                request('post', endpoint, data={'password': canaries['password']})
        elif case == 'logs':
            payload = {'password': canaries['password'], 'body': canaries['body'], 'filename': canaries['filename']}
            query = '?token=' + canaries['query']
            request('post', '/__srv11/echo/' + query, data=payload)
            request('post', '/__srv11/explode/' + query, data=payload)
            request('get', '/' + canaries['filename'] + query)
            request('get', '/__srv11/host/', HTTP_HOST=canaries['host'] + '.invalid')
            request('get', '/health/live/' + query, REMOTE_ADDR='203.0.113.71')
            request('get', '/health/live/' + query, HTTP_X_FORWARDED_PROTO='http')
        result.update(started=callable(application), answers=answers,
            files_unchanged=snapshot(root) == before, io=io, query_verbs=statements)
    except Exception as error:
        result.update(exception=type(error).__name__, io=io, query_verbs=statements)
    print(json.dumps(result, ensure_ascii=False))


class A09HealthAndLoggingTests(unittest.TestCase):
    def invoke(self, case):
        with tempfile.TemporaryDirectory(prefix='bos_a09_runtime_') as temporary:
            work = Path(temporary)
            installation = work / 'installation'
            installation.mkdir(mode=0o700)
            for child in ('data', 'private', 'static'):
                (installation / child).mkdir(mode=0o700)
            overlay = work / 'overlay'
            package = overlay / 'boss_project'
            package.mkdir(parents=True)
            (package / '__init__.py').write_text('__path__.append(' + repr(str(SOURCE / 'boss_project')) + ')\n')
            config = CONFIG_DRAFT or SOURCE
            for relative in ('server_settings.py', 'boss_project/server_config.py', 'boss_project/server_wsgi.py'):
                source = config / relative
                if source.exists():
                    shutil.copyfile(source, overlay / relative)
            if RUNTIME_DRAFT:
                for name in ('server_health.py', 'server_logging.py'):
                    shutil.copyfile(RUNTIME_DRAFT / 'boss_project' / name, package / name)
            # This is test-only routing; no synthetic endpoint enters production.
            (overlay / 'a09_runtime_urls.py').write_text(URL_SOURCE)
            with (overlay / 'server_settings.py').open('a') as settings_file:
                settings_file.write("\nROOT_URLCONF = 'a09_runtime_urls'\n")
            canaries = {key: 'A09_PRIVATE_' + key.upper() + '_' + uuid.uuid4().hex
                for key in ('password', 'body', 'filename', 'query', 'cookie', 'authorization', 'correlation', 'host', 'database')}
            canaries['body'] += '\nFAKE_LOG_RECORD'
            env = {k: v for k, v in os.environ.items() if not k.startswith('BOS_') and k != 'DJANGO_SETTINGS_MODULE'}
            env.update(PYTHONPATH=os.pathsep.join((str(overlay), str(SOURCE))), PYTHONDONTWRITEBYTECODE='1',
                BOS_DATA_MODE='working', BOS_DATABASE_ENGINE='sqlite3', BOS_INSTALLATION_ID=str(uuid.uuid4()),
                BOS_INSTALLATION_ROOT=str(installation), BOS_DATABASE_PATH=str(installation / 'data' / 'bos.sqlite3'),
                BOS_MEDIA_ROOT=str(installation / 'private'), BOS_PUBLIC_ORIGIN='https://bos.example.test:8443',
                BOS_ALLOWED_HOSTS='bos.example.test', BOS_TRUSTED_PROXY_IPS='127.0.0.1',
                BOS_SECRET_KEY=secrets.token_urlsafe(64), A09_RUNTIME_CASE=case,
                A09_RUNTIME_CANARIES=json.dumps(canaries))
            if case == 'configuration_refused':
                env['BOS_SECRET_KEY'] = 'django-insecure-' + canaries['password']
            run = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker'], cwd=SOURCE,
                env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr[-500:])
            result = json.loads(run.stdout)
            result['stderr_lines'] = run.stderr.splitlines()
            for value in (*canaries.values(), env['BOS_SECRET_KEY']):
                self.assertNotIn(value, run.stdout + run.stderr, 'Private synthetic canary leaked')
            self.assertNotIn('FAKE_LOG_RECORD', run.stdout + run.stderr)
            self.assertFalse(any(row['event'].startswith('socket.') for row in result['io']), result)
            if case != 'configuration_refused':
                self.assertNotIn('exception', result, result)
                self.assertTrue(result['files_unchanged'], result)
                self.assertTrue(all(row['read_only'] for row in result['io'] if row['event'] == 'sqlite3.connect'), result)
                self.assertTrue(set(result['query_verbs']) <= {'PRAGMA', 'SELECT'}, result)
            EVIDENCE.append(result)
            print('BOS_A09_HEALTH_LOG ' + json.dumps(result, ensure_ascii=False), flush=True)
            return result

    def test_liveness_without_database_has_no_database_io(self):
        result = self.invoke('live_missing')
        self.assertEqual(result['answers'][0]['status'], 200)
        self.assertEqual(result['answers'][0]['body'], {'status': 'alive'})
        self.assertEqual(result['io'], [])

    def test_readiness_fully_migrated_uses_only_readonly_selects(self):
        result = self.invoke('ready_healthy')
        self.assertEqual(result['answers'][0]['status'], 200)
        self.assertEqual(result['answers'][0]['body'], {'status': 'ready'})
        self.assertTrue(result['io'])
        self.assertIn('SELECT', result['query_verbs'])

    def test_absent_empty_corrupt_and_pending_database_are_unavailable(self):
        for case in ('ready_missing', 'ready_empty', 'ready_corrupt', 'ready_pending'):
            with self.subTest(case=case):
                result = self.invoke(case)
                self.assertEqual(result['answers'][0]['status'], 503)
                self.assertEqual(result['answers'][0]['body'], {'status': 'unavailable'})

    def test_missing_file_and_readonly_media_are_unavailable(self):
        for case in ('ready_media_missing', 'ready_media_file', 'ready_media_readonly'):
            with self.subTest(case=case):
                result = self.invoke(case)
                self.assertEqual(result['answers'][0]['status'], 503)
                self.assertEqual(result['answers'][0]['body'], {'status': 'unavailable'})

    def test_public_health_rejects_post_without_dependency_io(self):
        result = self.invoke('methods')
        self.assertEqual([row['status'] for row in result['answers']], [405, 405])
        self.assertTrue(all(row['allow'] == 'GET' for row in result['answers']))
        self.assertEqual(result['io'], [])

    def test_real_request_error_and_access_logs_never_include_private_canaries(self):
        result = self.invoke('logs')
        self.assertEqual([row['status'] for row in result['answers']], [200, 500, 404, 400, 403, 301])
        self.assertTrue(result['stderr_lines'])
        logs = [json.loads(line) for line in result['stderr_lines']]
        ids = [row['correlation'] for row in result['answers']]
        self.assertEqual(len(set(ids)), len(ids))
        self.assertTrue(all(re.fullmatch('[0-9a-f]{32}', value or '') for value in ids))
        self.assertTrue(all(set(row) == {'event', 'status', 'version', 'correlation_id'} for row in logs))
        self.assertTrue(all(row['correlation_id'] in ids for row in logs), 'Post-response/error logs lost the server-issued request ID')
        requests = [row for row in logs if row['event'] == 'request']
        self.assertEqual([(row['status'], row['correlation_id']) for row in requests],
            [(row['status'], row['correlation']) for row in result['answers']])
        self.assertTrue(any(row['event'] == 'application_error' and row['correlation_id'] == ids[1] for row in logs))

    def test_configuration_refusal_is_sanitized_and_structured_before_io(self):
        result = self.invoke('configuration_refused')
        self.assertEqual(result['exception'], 'ImproperlyConfigured')
        self.assertEqual(result['io'], [])
        logs = [json.loads(line) for line in result['stderr_lines']]
        self.assertTrue(any(row['event'] == 'configuration_refused' and row['status'] == 503 for row in logs))


def main():
    global SOURCE, CONFIG_DRAFT, RUNTIME_DRAFT
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default=str(SOURCE))
    parser.add_argument('--config-draft')
    parser.add_argument('--runtime-draft')
    parser.add_argument('--output', required=True)
    args, rest = parser.parse_known_args()
    SOURCE = Path(args.source).resolve()
    CONFIG_DRAFT = Path(args.config_draft).resolve() if args.config_draft else None
    RUNTIME_DRAFT = Path(args.runtime_draft).resolve() if args.runtime_draft else None
    program = unittest.main(argv=[sys.argv[0], *rest], verbosity=2, exit=False)
    report = {'date': datetime.now(timezone.utc).isoformat(), 'methods': program.result.testsRun,
        'failures': len(program.result.failures), 'errors': len(program.result.errors),
        'success': program.result.wasSuccessful(), 'scenarios': EVIDENCE,
        'scope': 'Actual isolated SQLite and Django requests/log streams; no production HTTP/TLS/network/Windows/PG acceptance'}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return not program.result.wasSuccessful()


if __name__ == '__main__':
    if '--worker' in sys.argv:
        worker()
        raise SystemExit(0)
    raise SystemExit(main())
