"""Gate 8: actual new offline install, Waitress/Caddy TLS, identity and lifecycle.

Creates only its own temporary synthetic installation. Runtime prerequisites are
explicit; unavailable binaries/wheels give nonzero, never a substitute server.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import queue
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.package_server import package
from scripts.server_http_checks import exercise_https


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    if not __debug__:
        print('Assert вимкнено: приймання заборонено.'); return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheelhouse', default=os.environ.get('BOS_SERVER_WHEELHOUSE'))
    parser.add_argument('--caddy', default=os.environ.get('BOS_CADDY_BIN'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = {'gate': 8, 'date': datetime.now(timezone.utc).isoformat(), 'complete': False,
              'platform': sys.platform, 'checks': [], 'commands': []}
    missing = [name for name, value in (('BOS_SERVER_WHEELHOUSE', args.wheelhouse),
               ('BOS_CADDY_BIN', args.caddy), ('openssl', shutil.which('openssl'))) if not value]
    if missing:
        report.update(status='НЕ ЗАПУЩЕНО', reason='Відсутні явні prerequisites: ' + ', '.join(missing))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(report, ensure_ascii=False)); return 2
    work = Path(tempfile.mkdtemp(prefix='bos-install-check-'))
    work.chmod(0o700)
    report['synthetic_work'] = str(work)
    children, threads, canaries = [], [], []
    base_env = {k: v for k, v in os.environ.items() if not k.startswith(('BOS_', 'PIP_', 'ANTHROPIC', 'OPENAI'))
                and k not in ('PYTHONPATH', 'PYTHONHOME', 'DJANGO_SETTINGS_MODULE')}
    base_env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONUTF8='1')
    stage = 'package'

    def execute(label, command, *, cwd=ROOT, env=None, payload=None, timeout=120):
        result = subprocess.run(list(map(str, command)), cwd=cwd, env=env or base_env,
                                input=payload, capture_output=True, text=True, timeout=timeout)
        for stream, content in (('stdout', result.stdout), ('stderr', result.stderr)):
            (work / (label + '.' + stream + '.log')).write_text(content)
        report['commands'].append({'step': label, 'returncode': result.returncode,
            'stdout_sha256': hashlib.sha256(result.stdout.encode()).hexdigest(),
            'stderr_sha256': hashlib.sha256(result.stderr.encode()).hexdigest()})
        return result

    def launch(label, command):
        # All process ownership comes from our own Popen objects, never a PID file.
        process = subprocess.Popen(list(map(str, command)), cwd=ROOT, env=base_env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        children.append(process)
        events = queue.Queue()
        def collect(stream, name):
            with (work / (label + '.' + name + '.log')).open('w') as log:
                for line in stream:
                    log.write(line); log.flush()
                    if name == 'stdout':
                        try: events.put(json.loads(line))
                        except ValueError: events.put({'event': 'unstructured'})
        for stream, name in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
            thread = threading.Thread(target=collect, args=(stream, name), daemon=True)
            thread.start(); threads.append(thread)
        deadline = time.monotonic() + 30
        while True:
            event = events.get(timeout=max(.1, deadline - time.monotonic()))
            if event.get('event') == 'bos.bundle.ready':
                assert event['health'] == {'live': 200, 'ready': 200}, 'healthy startup required'
                assert event['source_sha256'] == report['package']['source_sha256'], 'startup source identity'
                return process, events, event
            assert event.get('event') != 'bos.bundle.refused', 'genuine supervisor refused startup'

    def stop(process, events):
        process.terminate()
        code = process.wait(timeout=20)
        assert code == 0, 'graceful supervisor termination'
        deadline = time.monotonic() + 3
        while True:
            event = events.get(timeout=max(.1, deadline - time.monotonic()))
            if event.get('event') == 'bos.bundle.stopped':
                assert event['children'] and all(not item['forced'] and item['exit_code'] == 0
                                                for item in event['children']), 'graceful owned children'
                return event

    try:
        https_port, http_port = port(), port()
        assert https_port != http_port, 'distinct test ports'
        origin = f'https://localhost:{https_port}'
        source, target, registry = work / 'package', work / 'company', work / 'registry'
        report['package'] = package(ROOT, source)
        stage = 'real_install_cli'
        install = execute('install', [sys.executable, source / 'scripts/install_server.py',
            '--target', target, '--registry', registry, '--source-root', source,
            '--origin', origin, '--wheelhouse', Path(args.wheelhouse).absolute()], timeout=240)
        assert install.returncode == 2, 'provision CLI must explicitly report startup still pending'
        result = json.loads(install.stdout)
        assert result['application_provisioned'] is True and result['complete'] is False
        report['installation'] = result
        report['checks'].append({'case': 'fresh_venv_pins_migrations_static_empty_business', 'passed': True})
        config = json.loads((target / 'config/server.json').read_text())
        canaries.append(config['BOS_SECRET_KEY'])
        python = target / 'venv/bin/python'
        release = target / 'releases' / result['source_sha256']
        stage = 'synthetic_identity'
        password = 'BoS_private_password_' + secrets.token_urlsafe(24)
        canaries.append(password)
        seed = '''import json,sys,django;django.setup()
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group,Permission
from django.apps import apps
assert not get_user_model().objects.exists()
assert not any(m.objects.exists() for m in apps.get_models() if m._meta.app_label in {'operations','erp','finance','employees','branches','tasks','ai_assistant'})
p=json.load(sys.stdin)['password']
u=get_user_model().objects.create_user(username='tls-ceo',password=p)
u.groups.add(Group.objects.get_or_create(name='ceo')[0])
u.user_permissions.add(*Permission.objects.filter(content_type__app_label='operations',codename__in=['view_document','download_document','export_workspace']))
get_user_model().objects.create_superuser(username='tls-admin',email='tls@example.invalid',password=p)
print('two synthetic principals created in this new installation')
'''
        seeded = execute('synthetic-seed', [python, '-B', '-c', seed], cwd=release,
                         env={**base_env, **config}, payload=json.dumps({'password': password}))
        assert seeded.returncode == 0, 'new synthetic identity setup'
        cert, key = work / 'localhost.crt', work / 'localhost.key'
        generated = execute('test-certificate', ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
            '-keyout', key, '-out', cert, '-days', '2', '-subj', '/CN=localhost',
            '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'])
        assert generated.returncode == 0, 'own test certificate'
        key.chmod(0o600)
        command = [sys.executable, release / 'scripts/lifecycle_server.py', '--target', target,
                   '--registry', registry, '--installation-id', result['installation_id'],
                   '--caddy', Path(args.caddy).absolute(), '--certificate', cert, '--private-key', key,
                   '--ca-certificate', cert, '--http-port', str(http_port)]
        stage = 'launch_https'
        process, events, bound = launch('first-start', command)
        report['startup'] = bound
        context = ssl.create_default_context(cafile=str(cert))
        def private_snapshot():
            media = target / 'state/private'
            return {p.relative_to(media).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in media.rglob('*') if p.is_file()}
        stage = 'actual_https_contract'
        exercise_https(origin=origin, http_port=http_port, context=context,
                                               password=password, canary_values=canaries,
                                               private_snapshot=private_snapshot, checks=report['checks'])
        stage = 'duplicate_instance'
        # A live instance cannot be replaced by a second supervisor.
        duplicate = execute('duplicate', command, timeout=20)
        assert duplicate.returncode == 3, 'second instance must refuse'
        assert json.loads(duplicate.stdout)['event'] == 'bos.bundle.refused'
        report['checks'].append({'case': 'duplicate_instance_refused', 'passed': True})
        stage = 'graceful_stop_restart'
        report['first_stop'] = stop(process, events)
        db = Path(config['BOS_DATABASE_PATH'])
        media = Path(config['BOS_MEDIA_ROOT'])
        before_db = hashlib.sha256(db.read_bytes()).hexdigest()
        before_files = {p.relative_to(media).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in media.rglob('*') if p.is_file()}
        process, events, bound = launch('second-start', command)
        report['second_stop'] = stop(process, events)
        assert hashlib.sha256(db.read_bytes()).hexdigest() == before_db, 'restart must not migrate or seed database'
        after_files = {p.relative_to(media).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in media.rglob('*') if p.is_file()}
        assert after_files == before_files and before_files, 'restart preserves exact private documents'
        report['checks'].append({'case': 'restart_preserves_database_and_private_bytes', 'passed': True})
        stage = 'nonempty_actual_structured_logs'
        report['structured_logs'] = {}
        expected_fields = {'event', 'status', 'version', 'correlation_id'}
        for filename in ('application.stderr.log', 'caddy.stderr.log'):
            paths = list((target / 'runtime-logs').glob('lifecycle-*/' + filename))
            records = [json.loads(line) for path in paths for line in path.read_text().splitlines() if line]
            assert records and all(set(row) == expected_fields for row in records), 'nonempty allowlisted process logs'
            assert all(row['version'] == result['version'] for row in records), 'actual validated log version'
            statuses = {row['status'] for row in records}
            assert {200, 403} <= statuses, 'real accepted and rejected requests must appear in logs'
            report['structured_logs'][filename] = {'records': len(records), 'fields': sorted(expected_fields),
                'statuses': sorted(value for value in statuses if value is not None)}
        report['checks'].append({'case': 'nonempty_application_and_proxy_structured_logs', 'passed': True})
        report['complete'] = all(case.get('passed') is not False for case in report['checks'])
        if not report['complete']:
            report.update(status='ПОМИЛКА', reason='Є непройдений обов’язковий HTTP сценарій; див. checks.')
    except Exception as error:
        detail = str(error)
        for value in canaries:
            detail = detail.replace(value, '[private]')
        report.update(status='ПОМИЛКА', failure={'stage': stage, 'type': type(error).__name__, 'detail': detail})
    finally:
        for process in reversed(children):
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
                    report['complete'] = False
                    report['forced_supervisor_stop'] = True
        for thread in threads: thread.join(timeout=2)
        for process in children:
            process.stdout.close(); process.stderr.close()
        logs = list(work.glob('*.log')) + list((work / 'company').rglob('*.log'))
        private_absent = all(value not in log.read_text(errors='replace') for value in canaries for log in logs)
        report['private_canaries_absent'] = private_absent
        report['log_files_checked'] = len(logs)
        report['complete'] = report['complete'] and private_absent
        if report['complete']: report['status'] = 'ПРОЙДЕНО'
        elif not private_absent: report['status'] = 'ПОМИЛКА'
        encoded = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
        (work / 'report.json').write_text(encoded)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded)
        print(encoded)
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
