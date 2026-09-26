"""Real loopback Waitress requests, synthetic settings, no database access."""
import argparse
import atexit
import http.client
import json
import os
from pathlib import Path
import queue
import runpy
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid


def worker(runner, extra):
    attempts = []
    def audit(event, arguments):
        if event == 'sqlite3.connect':
            attempts.append({'event': event})
            raise RuntimeError('Synthetic HTTP probe refuses every database access')
        if event == 'socket.bind':
            address = arguments[1]
            attempts.append({'event': event, 'address': address})
            if not isinstance(address, tuple) or address[0] != '127.0.0.1':
                raise RuntimeError('Synthetic HTTP probe refuses non-loopback bind')
    sys.addaudithook(audit)
    atexit.register(lambda: print(json.dumps({'event': 'a09.audit', 'attempts': attempts}), flush=True))
    sys.argv = [runner, *extra]
    try:
        runpy.run_path(runner, run_name='__main__')
    except Exception as error:
        print(json.dumps({'event': 'a09.failure', 'exception': type(error).__name__}), flush=True)
        raise SystemExit(1)


SOURCE = Path(__file__).resolve().parents[1]
DRAFT = None
DEPS = None
EVIDENCE = []


class A09WaitressTests(unittest.TestCase):
    def environment(self, base):
        instance = base / 'state'
        instance.mkdir(mode=0o700)
        python_paths = [str(SOURCE)]
        if DRAFT:
            overlay = base / 'source-overlay'
            package = overlay / 'boss_project'
            package.mkdir(parents=True)
            (package / '__init__.py').write_text('__path__.append(' + repr(str(SOURCE / 'boss_project')) + ')\n')
            for source in (DRAFT / 'boss_project').glob('server_*.py'):
                shutil.copyfile(source, package / source.name)
            shutil.copyfile(DRAFT / 'server_settings.py', overlay / 'server_settings.py')
            python_paths.insert(0, str(overlay))
        if DEPS:
            python_paths.append(str(DEPS))
        env = {k: v for k, v in os.environ.items() if not k.startswith('BOS_') and k != 'DJANGO_SETTINGS_MODULE'}
        env.update(PYTHONPATH=os.pathsep.join(python_paths),
                   PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', BOS_DATA_MODE='working',
                   BOS_INSTALLATION_ROOT=str(instance), BOS_INSTALLATION_ID=str(uuid.uuid4()),
                   BOS_DATABASE_ENGINE='sqlite3', BOS_DATABASE_PATH=str(instance / 'data' / 'bos.sqlite3'),
                   BOS_MEDIA_ROOT=str(instance / 'private'), BOS_PUBLIC_ORIGIN='https://bos.example.test:8443',
                   BOS_ALLOWED_HOSTS='bos.example.test', BOS_TRUSTED_PROXY_IPS='127.0.0.1',
                   BOS_SECRET_KEY=secrets.token_urlsafe(64))
        return env, instance

    def command(self):
        return [sys.executable, str(Path(__file__).resolve()), '--worker',
                str((DRAFT or SOURCE) / 'scripts' / 'start_server.py'), '--port', '0']

    def test_invalid_configuration_refuses_before_bind_or_database(self):
        with tempfile.TemporaryDirectory(prefix='a09-wsgi-invalid-') as folder:
            env, instance = self.environment(Path(folder))
            env['BOS_SECRET_KEY'] = 'local-demo-only'
            process = subprocess.run(self.command(), cwd=SOURCE, env=env, capture_output=True, text=True, timeout=15)
            records = [json.loads(line) for line in process.stdout.splitlines() if line.startswith('{')]
            EVIDENCE.append({'case': self._testMethodName, 'returncode': process.returncode, 'records': records})
            self.assertNotEqual(process.returncode, 0)
            refused = [r for r in records if r.get('event') == 'bos.server.refused']
            self.assertEqual(len(refused), 1)
            self.assertIn('BOS_SECRET_KEY', refused[0]['reason'])
            log_records = [json.loads(line) for line in process.stderr.splitlines()]
            self.assertTrue(log_records)
            self.assertTrue(all(set(line) == {'event', 'status', 'version', 'correlation_id'} for line in log_records))
            self.assertNotIn('local-demo-only', process.stdout + process.stderr)
            self.assertEqual([r['attempts'] for r in records if r.get('event') == 'a09.audit'], [[]])
            self.assertEqual(list(instance.rglob('*')), [])

    def test_real_http_keeps_actual_peer_and_checks_forwarded_headers(self):
        with tempfile.TemporaryDirectory(prefix='a09-wsgi-http-') as folder:
            base = Path(folder)
            env, instance = self.environment(base)
            lines = []
            messages = queue.Queue()
            with (base / 'stderr.log').open('w+') as stderr:
                process = subprocess.Popen(self.command(), cwd=SOURCE, env=env,
                                           stdout=subprocess.PIPE, stderr=stderr, text=True, bufsize=1)
                def collect():
                    for line in process.stdout:
                        lines.append(line.rstrip())
                        try:
                            messages.put(json.loads(line))
                        except ValueError:
                            messages.put({'event': 'unstructured-output'})
                reader = threading.Thread(target=collect, daemon=True)
                reader.start()
                responses = []
                try:
                    ready = None
                    deadline = time.monotonic() + 8
                    while time.monotonic() < deadline:
                        try:
                            event = messages.get(timeout=0.2)
                        except queue.Empty:
                            if process.poll() is not None:
                                break
                            continue
                        if event.get('event') == 'bos.server.bound':
                            ready = event
                            break
                        if event.get('event') == 'a09.failure':
                            break
                    self.assertIsNotNone(ready, 'Supported Waitress runner did not bind: ' + repr(lines))
                    self.assertEqual(ready['host'], '127.0.0.1')
                    self.assertEqual(ready['runtime_version'], '3.0.2')
                    port = ready['port']
                    base_headers = {'Host': 'bos.example.test:8443', 'X-Forwarded-Proto': 'https',
                                    'X-Forwarded-For': '198.51.100.18'}
                    scenarios = [
                        ('valid', '127.0.0.1', base_headers, 200),
                        ('forged-actual-peer', '127.0.0.2', {**base_headers, 'X-Forwarded-For': '127.0.0.1'}, 403),
                        ('no-proxy-headers', '127.0.0.1', {'Host': 'bos.example.test:8443'}, 400),
                        ('ambiguous-proto', '127.0.0.1', {**base_headers, 'X-Forwarded-Proto': 'https,http'}, 400),
                        ('wrong-host', '127.0.0.1', {**base_headers, 'Host': 'hostile.invalid'}, 400),
                        ('ignored-forwarded-host', '127.0.0.1', {**base_headers, 'X-Forwarded-Host': 'hostile.invalid',
                                                                  'Forwarded': 'host=hostile.invalid;proto=http'}, 200),
                        ('http-redirect', '127.0.0.1', {**base_headers, 'X-Forwarded-Proto': 'http'}, 301),
                    ]
                    for label, source, headers, expected in scenarios:
                        with self.subTest(case=label):
                            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5, source_address=(source, 0))
                            try:
                                connection.request('GET', '/api/auth/csrf/', headers=headers)
                                response = connection.getresponse()
                                body = response.read()
                                response_headers = dict(response.getheaders())
                            finally:
                                connection.close()
                            responses.append({'case': label, 'source_address': source, 'status': response.status,
                                              'expected': expected, 'secure_cookie': 'Secure' in response_headers.get('Set-Cookie', '')})
                            self.assertEqual(response.status, expected, body[:200])
                            if expected == 200:
                                self.assertEqual(json.loads(body), {'mode': 'working', 'authenticated': False})
                                self.assertIn('Secure', response_headers.get('Set-Cookie', ''))
                                self.assertEqual(response_headers.get('X-Frame-Options'), 'DENY')
                            if label == 'http-redirect':
                                self.assertEqual(response_headers.get('Location'), 'https://bos.example.test:8443/api/auth/csrf/')
                finally:
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                    reader.join(timeout=2)
                    process.stdout.close()
                    stderr.seek(0)
                    errors = stderr.read()
                    records = [json.loads(line) for line in lines if line.startswith('{')]
                    EVIDENCE.append({'case': self._testMethodName, 'returncode': process.returncode,
                                     'records': records, 'responses': responses, 'stderr': errors})
                self.assertEqual(process.returncode, 0, errors)
                attempts = [r['attempts'] for r in records if r.get('event') == 'a09.audit']
                self.assertEqual(len(attempts), 1)
                self.assertEqual([a for a in attempts[0] if a['event'] == 'sqlite3.connect'], [])
                self.assertTrue(attempts[0])
                self.assertTrue(all(a['address'][0] == '127.0.0.1' for a in attempts[0]))
                self.assertEqual(list(instance.rglob('*')), [])


def main():
    global SOURCE, DRAFT, DEPS
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default=str(SOURCE))
    parser.add_argument('--draft')
    parser.add_argument('--deps')
    parser.add_argument('--output', required=True)
    args, rest = parser.parse_known_args()
    SOURCE = Path(args.source).resolve()
    DRAFT = Path(args.draft).resolve() if args.draft else None
    DEPS = Path(args.deps).resolve() if args.deps else None
    program = unittest.main(argv=[sys.argv[0], *rest], exit=False, verbosity=2)
    Path(args.output).write_text(json.dumps({'tests_run': program.result.testsRun,
        'failures': len(program.result.failures), 'errors': len(program.result.errors),
        'successful': program.result.wasSuccessful(), 'evidence': EVIDENCE,
        'scope': 'Real Waitress 3.0.2 loopback HTTP only; no TLS/production data/Windows/install acceptance'}, ensure_ascii=False, indent=2) + '\n')
    return not program.result.wasSuccessful()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        worker(sys.argv[2], sys.argv[3:])
    else:
        raise SystemExit(main())
