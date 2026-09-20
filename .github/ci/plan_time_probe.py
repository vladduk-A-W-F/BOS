"""Two bounded diagnostic samples, never a full suite or gate-3 acceptance."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'ce495b29214f21a80b8efd5bf41f6f219b5cb182b0453a7c43dac8899bc06ed5'
SOURCE_BASE = '87b679888c18ed1920f4735aa945dacad514bcaa'
CI_PATHS = {'.github/ci/plan_time_probe.py', '.github/ci/plan_time_django.py',
            '.github/ci/plan_time_replay.py', '.github/workflows/bos-plan-time-targeted.yml'}
SPEC = importlib.util.spec_from_file_location('plan_time_existing_helpers', ROOT / '.github/ci/batch_01_targeted.py')
h = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(h)


def remaining(deadline):
    value = deadline - time.monotonic()
    if value < 1:
        raise TimeoutError('Insufficient diagnostic controller deadline; no operation started')
    return value


def control_connection(env, name, deadline):
    """Timeouts apply only to allocation/observation/cleanup, never app queries."""
    import psycopg
    budget = remaining(deadline)
    return psycopg.connect(dbname=name, host=env['BOS_PGHOST'], port=env['BOS_PGPORT'],
        user=env['BOS_PGUSER'], password=env['BOS_PGPASSWORD'],
        connect_timeout=min(5, int(budget)), autocommit=True,
        options='-c statement_timeout=' + str(min(5000, int(budget * 1000))))


def control_query(db, deadline, statement, params=None):
    milliseconds = min(5000, int(remaining(deadline) * 1000))
    db.execute("SELECT set_config('statement_timeout', %s, false)", (str(milliseconds),))
    remaining(deadline)
    return db.execute(statement, params)


@contextmanager
def issued_database(work, deadline, result):
    import psycopg.sql
    env = os.environ.copy()
    if env.get('BOS_PG_DISPOSABLE') != '1' or not all(env.get(k) for k in ('BOS_PGHOST', 'BOS_PGUSER', 'BOS_PGPASSWORD')):
        raise RuntimeError('Explicit disposable PostgreSQL environment required')
    issued = 'bos_verify_' + uuid.uuid4().hex[:16]
    env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', BOS_DATA_MODE='demo',
               BOS_VERIFY_DB='postgres', BOS_TEST_DB_NAME=issued, BOS_TEST_MEDIA=str(work / 'media'),
               BOS_PROJECT_ROOT=str(work / 'source'), BOS_PGPORT=env.get('BOS_PGPORT', '5432'))
    created = False
    try:
        with control_connection(env, 'postgres', deadline) as db:
            actual, version = control_query(db, deadline,
                "SELECT current_database(), current_setting('server_version_num')").fetchone()
            if actual != 'postgres' or not 160000 <= int(version) < 170000:
                raise RuntimeError('Controller requires PostgreSQL 16 before allocation')
            control_query(db, deadline, psycopg.sql.SQL('CREATE DATABASE {}').format(psycopg.sql.Identifier(issued)))
            created = True
        yield env
    finally:
        if created:
            cleanup_deadline = time.monotonic() + 10
            with control_connection(env, 'postgres', cleanup_deadline) as db:
                control_query(db, cleanup_deadline, psycopg.sql.SQL('DROP DATABASE {} WITH (FORCE)').format(psycopg.sql.Identifier(issued)))
                result['issued_database_cleanup_verified'] = not bool(control_query(db, cleanup_deadline,
                    'SELECT 1 FROM pg_database WHERE datname=%s', (issued,)).fetchone())


def source_canary(env, deadline, create=False):
    issued = env['BOS_TEST_DB_NAME']
    if not re.fullmatch(r'bos_verify_[a-f0-9]{16}', issued) or env.get('BOS_PG_DISPOSABLE') != '1':
        raise RuntimeError('Refuse unissued canary database')
    with control_connection(env, issued, deadline) as db:
        actual, version = control_query(db, deadline,
            "SELECT current_database(), current_setting('server_version_num')").fetchone()
        if actual != issued or not 160000 <= int(version) < 170000:
            raise RuntimeError('Canary database identity mismatch')
        if create:
            control_query(db, deadline, 'CREATE TABLE bos_time_source_canary (id integer PRIMARY KEY, payload text NOT NULL)')
            control_query(db, deadline, 'INSERT INTO bos_time_source_canary VALUES (1,%s)', ('Synthetic diagnostic canary',))
        tables = control_query(db, deadline, "SELECT table_schema,table_name,table_type FROM information_schema.tables "
            "WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY table_schema,table_name").fetchall()
        rows = control_query(db, deadline, 'SELECT id,payload FROM bos_time_source_canary ORDER BY id').fetchall()
    return {'database': issued, 'version_num': int(version), 'tables': tables, 'rows': rows}


def valid_worker(mode, value, issued):
    """Completion of a sample does not establish the historical timeout cause."""
    proof = value.get('database', {})
    expected = ('test_' if mode == 'django' else '') + issued
    common = (value.get('complete') is True and value.get('root_cause_proven') is False
              and proof.get('vendor') == 'postgresql' and proof.get('database') == expected
              and 160000 <= proof.get('version_num', 0) < 170000)
    if mode == 'django':
        return common and value.get('tests_run') == 1 and value.get('tests_failed') == 0 and value.get('tests_skipped') == 0
    return common and value.get('sequences') == 1 and value.get('replay_requests') == 4


def wait_sample(env, issued):
    """Observe only this freshly allocated synthetic database and its test DB."""
    with h.pg_connect(env, 'postgres') as db:
        db.execute('SET statement_timeout = 2000')
        rows = db.execute(
            "SELECT pid,datname,state,wait_event_type,wait_event,pg_blocking_pids(pid) "
            "FROM pg_stat_activity WHERE datname = ANY(%s) ORDER BY pid",
            ([issued, 'test_' + issued],)).fetchall()
    return [dict(zip(('pid', 'database', 'state', 'wait_event_type', 'wait_event', 'blocking_pids'), row)) for row in rows]


def process(command, env, root, output, mode, budget, issued, observer=wait_sample):
    out_path, err_path = output / (mode + '.stdout.log'), output / (mode + '.stderr.log')
    receipt = {'command': command, 'timeout_seconds': budget, 'wait_samples': [], 'timed_out': False}
    started = time.monotonic()
    with out_path.open('wb') as stdout, err_path.open('wb') as stderr:
        child = subprocess.Popen(command, cwd=root, env=env, stdout=stdout, stderr=stderr)
        def expire():
            if child.poll() is None:
                receipt['timed_out'] = True
                receipt['kill_requested_seconds'] = round(time.monotonic() - started, 3)
                child.kill()
        # The observer cannot extend the child deadline, even if its connection stalls.
        timer = threading.Timer(max(.001, budget - (time.monotonic() - started)), expire)
        timer.daemon = True
        timer.start()
        try:
            next_sample = 0
            while child.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed >= budget:
                    expire()
                    break
                if elapsed >= next_sample:
                    try:
                        sample = {'elapsed_seconds': round(elapsed, 3), 'rows': observer(env, issued)}
                    except Exception as exc:
                        sample = {'elapsed_seconds': round(elapsed, 3), 'observer_error_type': type(exc).__name__}
                    receipt['wait_samples'].append(sample)
                    next_sample = elapsed + 5
                time.sleep(min(.1, max(.001, budget - (time.monotonic() - started))))
        finally:
            timer.cancel()
            if child.poll() is None:
                child.kill()
            returncode = child.wait(timeout=5)
    receipt.update(exit_code=None if receipt['timed_out'] else returncode,
                   observed_process_exit=returncode, duration_seconds=round(time.monotonic() - started, 3),
                   stdout=out_path.name, stderr=err_path.name,
                   stdout_sha256=h.sha(out_path), stderr_sha256=h.sha(err_path))
    return receipt


def stage(mode, output, report):
    started = time.monotonic()
    deadline = started + 60
    result = {'mode': mode, 'status': 'STARTED', 'complete': False, 'budget_seconds': 60}
    report['samples'].append(result)
    h.write_json(output / 'report.json', report)
    with tempfile.TemporaryDirectory(prefix='bos-time-' + mode + '-') as temporary:
        work = Path(temporary)
        (work / 'media').mkdir()
        (work / 'source').mkdir()
        with issued_database(work, deadline, result) as env:
            issued = env['BOS_TEST_DB_NAME']
            result['issued_database'] = issued
            if mode == 'django':
                result['source_canary_before'] = source_canary(env, deadline, create=True)
                with control_connection(env, 'postgres', deadline) as db:
                    if control_query(db, deadline, 'SELECT 1 FROM pg_database WHERE datname=%s', ('test_' + issued,)).fetchone():
                        raise RuntimeError('Refuse preexisting companion test database; no cleanup authorized')
                result['companion_absent_before_worker'] = True
            env.update(DJANGO_SETTINGS_MODULE='verification_settings', PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
            for secret in ('GITHUB_TOKEN', 'GH_TOKEN', 'BOS_TEST_DEPENDENCIES'):
                env.pop(secret, None)
            worker = ROOT / '.github/ci' / ('plan_time_' + mode + '.py')
            child_report = output / (mode + '.json')
            command = [sys.executable, '-B', str(worker), '--output', str(child_report)]
            result['worker_sha256'] = h.sha(worker)
            try:
                budget = 60 - (time.monotonic() - started)
                if budget <= 0:
                    raise RuntimeError('Bootstrap exhausted sample budget; worker not run')
                env['BOS_PLAN_TIME_STACK_AFTER'] = str(min(45, max(.1, budget - 2)))
                result['stack_dump_after_worker_seconds'] = float(env['BOS_PLAN_TIME_STACK_AFTER'])
                result['process'] = process(command, env, ROOT, output, mode, budget, issued)
                if child_report.is_file():
                    value = json.loads(child_report.read_text(encoding='utf-8'))
                    result['worker_report'] = child_report.name
                    result['worker_report_sha256'] = h.sha(child_report)
                    result['complete'] = (not result['process']['timed_out']
                                          and result['process']['exit_code'] == 0
                                          and valid_worker(mode, value, issued))
            finally:
                if mode == 'django':
                    try:
                        result['source_canary_after'] = source_canary(env, time.monotonic() + 10)
                        result['source_canary_unchanged'] = result['source_canary_before'] == result['source_canary_after']
                        result['complete'] = result['complete'] and result['source_canary_unchanged']
                    finally:
                        # Cleanup also runs if canary verification itself fails.
                        import psycopg.sql
                        cleanup_deadline = time.monotonic() + 10
                        with control_connection(env, 'postgres', cleanup_deadline) as db:
                            control_query(db, cleanup_deadline, psycopg.sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(psycopg.sql.Identifier('test_' + issued)))
                            result['test_database_cleanup_verified'] = not bool(control_query(db, cleanup_deadline,
                                'SELECT 1 FROM pg_database WHERE datname=%s', ('test_' + issued,)).fetchone())
    result['complete'] = result['complete'] and result.get('issued_database_cleanup_verified') is True
    if mode == 'django':
        result['complete'] = result['complete'] and result.get('test_database_cleanup_verified') is True
    result.update(status='SCOPED_DIAGNOSTIC_COMPLETE' if result['complete'] else 'INCOMPLETE_OR_FAILED',
                  total_seconds=round(time.monotonic() - started, 3))
    h.write_json(output / 'report.json', report)
    if not result['complete']:
        raise RuntimeError('Stop after incomplete diagnostic sample; no automatic retry')


def finalize(output):
    if not (output / 'report.json').exists():
        h.write_json(output / 'report.json', {'status': 'BLOCKED_BEFORE_RUNNER', 'complete': False,
            'root_cause_proven': False, 'technical_ready': False, 'pilot_allowed': False})
    h.finalize(output)
    value = json.loads((output / 'sha256-index.json').read_text())
    value['schema'] = 'bos.plan-time.sha256.v1'
    h.write_json(output / 'sha256-index.json', value)


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'runner-started.json').exists():
        raise RuntimeError('Refuse a repeated run in the same evidence directory')
    h.write_json(output / 'runner-started.json', {'started_at': h.now()})
    report = {'schema': 'bos.plan-time.v1', 'card': 'PLAN-TIME-PROBE', 'complete': False,
              'root_cause_proven': False, 'full_suite_run': False, 'gate3_run': False,
              'technical_ready': False, 'pilot_allowed': False, 'historical_p05': '3/3',
              'source_base': SOURCE_BASE, 'run_id': os.environ.get('GITHUB_RUN_ID'),
              'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'samples': [], 'errors': []}
    before = None
    try:
        if not __debug__ or sys.version_info[:2] != (3, 12):
            raise RuntimeError('Python3.12 with active assertions required')
        if (os.environ.get('GITHUB_EVENT_NAME') != 'pull_request' or os.environ.get('GITHUB_HEAD_REF') != h.HEAD_BRANCH
                or os.environ.get('GITHUB_BASE_REF') != h.BASE_BRANCH or os.environ.get('GITHUB_RUN_ATTEMPT') != '1'):
            raise RuntimeError('Only approved PR branches and first attempt allowed')
        head = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())['pull_request']['head']
        actual = h.git(ROOT, 'rev-parse', 'HEAD')
        if head['repo']['full_name'] != os.environ['GITHUB_REPOSITORY'] or actual != head['sha'] or actual != os.environ['BOS_BATCH_CANDIDATE_SHA']:
            raise RuntimeError('Unexpected candidate')
        if h.git(ROOT, 'status', '--porcelain', '--untracked-files=all'):
            raise RuntimeError('Clean checkout required')
        changed = set(h.git(ROOT, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD^', 'HEAD').splitlines())
        if not changed & CI_PATHS:
            raise RuntimeError('Current head does not change the diagnostic CI allowlist')
        before = {'source_sha256': h.verifier(ROOT).source_digest(), 'source_databases': h.source_databases(ROOT)}
        report.update(candidate_commit=actual, source_before=before,
                      dependencies={n: importlib.metadata.version(n) for n in ('Django', 'djangorestframework', 'psycopg')},
                      harness_sha256=h.sha(Path(__file__)), reused_helper_sha256=h.sha(Path(h.__file__)))
        if before['source_sha256'] != SOURCE:
            raise RuntimeError('Runtime differs from reviewed diagnostic candidate')
        for mode in ('django', 'replay'):
            stage(mode, output, report)
        report['complete'] = True
    except Exception as exc:
        if report['samples'] and report['samples'][-1]['status'] == 'STARTED':
            report['samples'][-1].update(status='INCOMPLETE_OR_FAILED', complete=False)
        report['errors'].append(type(exc).__name__ + ': ' + str(exc))
        (output / 'exception.log').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        after = {'source_sha256': h.verifier(ROOT).source_digest(), 'source_databases': h.source_databases(ROOT)}
        report['source_after'] = after
        report['source_unchanged'] = before is not None and before == after
        report['complete'] = report['complete'] and report['source_unchanged'] and not report['errors']
        report['status'] = 'SCOPED_DIAGNOSTIC_COMPLETE' if report['complete'] else 'INCOMPLETE_OR_BLOCKED'
        h.write_json(output / 'report.json', report)
        finalize(output)
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--finalize-only', action='store_true')
    args = parser.parse_args()
    if args.finalize_only:
        args.output.mkdir(parents=True, exist_ok=True)
        finalize(args.output.resolve())
    else:
        raise SystemExit(run(args.output.resolve()))
