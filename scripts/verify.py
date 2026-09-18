"""Strict eleven-gate verifier. Missing implementation/evidence never passes."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
if os.environ.get('BOS_TEST_DEPENDENCIES'):
    sys.path.append(os.environ['BOS_TEST_DEPENDENCIES'])
PASS = 'ПРОЙДЕНО'
FAIL = 'ПОМИЛКА'
MISSING = 'НЕ РЕАЛІЗОВАНО'
UNRUN = 'НЕ ЗАПУЩЕНО'
GATES = {
    1: 'Міграції на порожніх SQLite і PostgreSQL',
    2: '151 функціональна + 5 launcher + решта тестів на обох СУБД',
    3: 'П’ять інваріантів, мінімум 1000 випадкових прогонів кожний',
    4: 'Права всіх ролей на всіх API/admin та всіх поверхнях даних',
    5: 'Два одночасні виклики кожної грошової та складської дії',
    6: 'Наскрізний процес на чистій базі, звірка до копійки',
    7: 'Backup/restore у чисту установку: кількості, суми, версії, SHA',
    8: 'Чиста виробнича установка: TLS, cookies, proxy, health, logs',
    9: 'Оновлення N → N+1 та відновлення N після rollback',
    10: 'Браузер: 390/768/1440, 200%, клавіатура, Escape, мережа',
    11: 'Чиста Windows / Python 3.12: критерії 1–3 і 6',
}
SUITES = {'full': tuple(GATES), 'sqlite': (1, 2, 3, 5),
          'postgres': (1, 2, 3, 5), 'e2e': (6,), 'ui': (10,),
          'windows': (1, 2, 3, 6)}
LEGACY = {'check_workspace.py': 22, 'check_erp.py': 49,
          'check_operations.py': 48, 'check_original.py': 32,
          'check_launcher.py': 5}
# Future gates must be implemented as real executable acceptance checks.
EXTENSIONS = {3: 'scripts/check_invariants.py', 4: 'scripts/check_access.py',
              5: 'scripts/check_concurrency.py', 6: 'scripts/e2e_scenario.py',
              7: 'scripts/check_restore.py', 8: 'scripts/check_install.py',
              9: 'scripts/check_upgrade.py', 10: 'scripts/check_ui.py'}


def source_digest():
    digest = hashlib.sha256()
    roots = ('scripts', 'tests', 'fixtures', 'frontend', 'assets', 'static', 'deploy',
             'boss_project', 'operations', 'erp', 'finance', 'employees', 'branches',
             'tasks', 'ai_assistant')
    files = [p for name in roots for p in (ROOT / name).rglob('*') if p.is_file()
             and '__pycache__' not in p.parts and p.suffix != '.pyc']
    files += [p for p in ROOT.iterdir() if p.is_file()
              and p.suffix in {'.py', '.txt', '.bat', '.sh', '.ps1', '.yml', '.yaml'}]
    files += [ROOT / 'docs' / n for n in ('KNOWLEDGE_UA.md', 'PARAMETERS_UA.md')
              if (ROOT / 'docs' / n).exists()]
    for path in sorted(set(files)):
        digest.update(str(path.relative_to(ROOT)).replace('\\', '/').encode())
        content = path.read_bytes()
        if path.suffix in {'.py','.js','.cjs','.html','.css','.json','.jsonl','.md','.txt','.sh','.ps1','.bat','.yml','.yaml'}:
            content = content.replace(b'\r\n', b'\n')
        digest.update(b'\0' + content + b'\0')
    return digest.hexdigest()


def outcome(status, reason='', **values):
    return {'status': status, 'reason': reason, **values}


def combine(parts):
    for status in (FAIL, MISSING, UNRUN):
        if any(x['status'] == status for x in parts):
            return outcome(status, 'Усі підперевірки обов’язкові.', parts=parts)
    return outcome(PASS, parts=parts)


class EnvironmentUnavailable(RuntimeError):
    pass


@contextmanager
def database(backend, work):
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', BOS_DATA_MODE='demo',
               BOS_VERIFY_DB=backend, BOS_TEST_MEDIA=str(work / 'media'),
               BOS_PROJECT_ROOT=str(work / 'source'))
    if backend == 'sqlite':
        env['BOS_TEST_DB_NAME'] = str(work / ('check_' + uuid.uuid4().hex + '.sqlite3'))
        yield env
        return
    required = ('BOS_PGHOST', 'BOS_PGUSER', 'BOS_PGPASSWORD')
    if os.environ.get('BOS_PG_DISPOSABLE') != '1' or not all(os.environ.get(k) for k in required):
        raise EnvironmentUnavailable('Немає налаштованого ізольованого PostgreSQL; потрібні BOS_PGHOST/USER/PASSWORD і BOS_PG_DISPOSABLE=1.')
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:
        raise EnvironmentUnavailable('Не встановлено psycopg із requirements-ci.txt.') from exc
    name = 'bos_verify_' + uuid.uuid4().hex[:16]
    env['BOS_TEST_DB_NAME'] = name
    try:
        connection = psycopg.connect(dbname='postgres', host=env['BOS_PGHOST'],
                                     port=env.get('BOS_PGPORT', '5432'), user=env['BOS_PGUSER'],
                                     password=env['BOS_PGPASSWORD'], connect_timeout=5, autocommit=True)
    except psycopg.OperationalError as exc:
        raise EnvironmentUnavailable('Ізольований PostgreSQL недоступний; з’єднання не встановлено.') from exc
    created = False
    try:
        connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        created = True
        yield env
    finally:
        if created:
            connection.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
        connection.close()


def execute(command, cwd, env, log, *, timeout=600):
    log.parent.mkdir(parents=True, exist_ok=True)
    receipt = {'command': command, 'log': str(log)}
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        # TimeoutExpired can contain bytes even with text=True, or None for silence.
        def decoded(value):
            return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else (value or '')
        result = subprocess.CompletedProcess(command, None, decoded(exc.stdout), decoded(exc.stderr))
        receipt.update(timed_out=True, timeout_seconds=timeout,
                       reason=f'TimeoutExpired: перевищено {timeout} с; збережено доступний частковий вивід.')
    # Other exceptions still become failed gates; a timeout has no normal exit code.
    log.write_text(result.stdout + '\n--- STDERR ---\n' + result.stderr, encoding='utf-8')
    return result, {**receipt, 'returncode': result.returncode}


def json_objects(text):
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char == '{':
            try:
                value, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                yield value


def migration(backend, work, output):
    command = [sys.executable, '-c',
               "import os; os.environ['DJANGO_SETTINGS_MODULE']='verification_settings'; "
               "import django; django.setup(); from scripts.check_support import prove_database; "
               "prove_database(); from django.core.management import call_command; call_command('migrate',verbosity=1)"]
    with database(backend, work) as env:
        result, receipt = execute(command, work / 'source', env, output / f'migrations-{backend}.log')
    return outcome(PASS if result.returncode == 0 else FAIL, backend=backend, **receipt)


def functional(backend, work, output, *, timeout=600):
    parts = []
    for filename, expected in LEGACY.items():
        print(f'  {backend}: {filename}', flush=True)
        with database(backend, work) as env:
            result, receipt = execute([sys.executable, '-B', 'scripts/' + filename],
                                      work / 'source', env, output / f'{backend}-{filename}.log', timeout=timeout)
        if receipt.get('timed_out'):
            # Partial output may end inside JSON; retain evidence before parsing it.
            parts.append(outcome(FAIL, filename=filename, checks=None, expected=expected,
                                 engine_verified=False, **receipt))
            return {**combine(parts), 'backend': backend}
        if filename == 'check_launcher.py':
            count = 5 if '5 launcher checks passed;' in result.stdout else 0
            engine_verified = True  # Launcher is DB-independent; never gate 11 evidence.
        else:
            reports = [x for x in json_objects(result.stdout) if 'passed' in x and 'checks' in x]
            count = reports[-1]['passed'] if reports and len(reports[-1]['checks']) == reports[-1]['passed'] else 0
            engine = 'postgresql' if backend == 'postgres' else 'sqlite'
            engine_verified = any(line.startswith('BOS_DATABASE ') and json.loads(line[13:])['vendor'] == engine
                                  for line in result.stdout.splitlines())
        passed = result.returncode == 0 and count == expected and engine_verified
        parts.append(outcome(PASS if passed else FAIL, filename=filename, checks=count,
                             expected=expected, engine_verified=engine_verified, **receipt))
    with database(backend, work) as env:
        result, receipt = execute([sys.executable, '-B', 'manage.py', 'test', '--noinput',
                                   '--settings=verification_settings', '--verbosity=1'],
                                  work / 'source', env, output / f'{backend}-django-tests.log', timeout=timeout)
    receipt.setdefault('reason', 'Решта Django-тестів; не заміняють 151+5.')
    parts.append(outcome(PASS if result.returncode == 0 else FAIL, **receipt))
    return {**combine(parts), 'backend': backend}


def extension(gate, backend, work, output):
    path = EXTENSIONS[gate]
    if not (work / 'source' / path).is_file():
        return outcome(MISSING, 'Потрібна справжня перевірка: ' + path, backend=backend)
    with database(backend, work) as env:
        result, receipt = execute([sys.executable, '-B', path], work / 'source', env,
                                  output / f'gate-{gate:02d}-{backend}.log')
    return outcome(PASS if result.returncode == 0 else FAIL, backend=backend, **receipt)


def windows_evidence(source_sha):
    path = Path(os.environ.get('BOS_WINDOWS_REPORT', 'evidence/ci/windows/report.json'))
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        return outcome(UNRUN, 'Немає результату реального Windows runner.', expected_report=str(path))
    value = json.loads(path.read_text(encoding='utf-8'))
    valid = (value.get('suite') == 'windows' and value.get('complete') is True
             and value.get('source_sha256') == source_sha
             and value.get('environment', {}).get('system') == 'Windows'
             and value.get('environment', {}).get('python_minor') == [3, 12]
             and {r['id'] for r in value.get('gates', [])} == {1, 2, 3, 6}
             and all(r['status'] == PASS for r in value.get('gates', [])))
    if os.environ.get('CI_PIPELINE_ID'):
        valid = valid and value.get('ci', {}).get('pipeline_id') == os.environ['CI_PIPELINE_ID']
    return outcome(PASS if valid else FAIL, 'Перевірено Windows-звіт, ОС, Python, критерії, SHA та поточний pipeline.', report=str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=SUITES, default='full')
    parser.add_argument('--output', default='evidence/verify/report.json')
    parser.add_argument('--list', action='store_true')
    args = parser.parse_args()
    if args.list:
        print(json.dumps(GATES, ensure_ascii=False, indent=2)); return 0
    if not __debug__ or os.environ.get('PYTHONOPTIMIZE', '') not in ('', '0'):
        print('ПОМИЛКА: assert вимкнено; приймання неможливе.', file=sys.stderr); return 2
    output = Path(args.output).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    sha = source_digest()
    report = {'schema': 1, 'suite': args.suite, 'source_sha256': sha,
              'date': datetime.now(timezone.utc).isoformat(), 'complete': False,
              'environment': {'system': platform.system(), 'python': sys.version,
                              'python_minor': list(sys.version_info[:2])},
              'ci': {'pipeline_id': os.environ.get('CI_PIPELINE_ID'),
                     'job_url': os.environ.get('CI_JOB_URL'), 'commit': os.environ.get('CI_COMMIT_SHA')},
              'data': 'Лише нові синтетичні бази та контрольний файл.', 'gates': []}
    live_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.sqlite3')}
    report['source_database_count'] = len(live_hashes)
    with tempfile.TemporaryDirectory(prefix='bos-verify-') as folder:
        work = Path(folder)
        shutil.copytree(ROOT, work / 'source', ignore=shutil.ignore_patterns(
            '.git', '.venv', '.venv-ci', 'venv', '__pycache__', '*.pyc', '*.sqlite*', '*.db', '.env', '.env.*',
            'evidence', 'output', 'upload', 'media', 'rehearsal-media', 'node_modules',
            'DATA_RECONCILIATION_UA.md'))
        with sqlite3.connect(work / 'source' / 'db.sqlite3') as sentinel:
            sentinel.execute('CREATE TABLE synthetic_control (notice TEXT NOT NULL)')
            sentinel.execute('INSERT INTO synthetic_control VALUES (?)', ('BoS: виключно синтетична контрольна база',))
        for gate in SUITES[args.suite]:
            print(f'{gate:02d}. {GATES[gate]}', flush=True)
            backends = [args.suite] if args.suite in ('sqlite', 'postgres') else ['sqlite', 'postgres']
            if gate in (4, 7, 8, 9, 10):
                backends = ['sqlite']
            if args.suite == 'windows' and (platform.system() != 'Windows' or sys.version_info[:2] != (3, 12)):
                value = outcome(UNRUN, 'Цей запуск не є Windows з Python 3.12.')
            elif gate == 11:
                try:
                    value = windows_evidence(sha)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    value = outcome(FAIL, 'Некоректний Windows-артефакт: ' + str(exc))
            else:
                parts = []
                for backend in backends:
                    try:
                        if gate == 1:
                            part = migration(backend, work, output.parent)
                        elif gate == 2:
                            part = functional(backend, work, output.parent)
                        else:
                            part = extension(gate, backend, work, output.parent)
                    except EnvironmentUnavailable as exc:
                        part = outcome(UNRUN, str(exc), backend=backend)
                    except Exception as exc:
                        part = outcome(FAIL, f'{type(exc).__name__}: {exc}', backend=backend)
                    parts.append(part)
                value = combine(parts)
            report['gates'].append({'id': gate, 'name': GATES[gate], **value})
            print('  ' + value['status'], flush=True)
        report['source_databases_unchanged'] = live_hashes == {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('*.sqlite3')}
        report['complete'] = (all(g['status'] == PASS for g in report['gates'])
                              and len(report['gates']) == len(SUITES[args.suite])
                              and report['source_databases_unchanged'])
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(('ПРОЙДЕНО' if report['complete'] else 'НЕ ПРИЙНЯТО') + ': ' + str(output), flush=True)
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
