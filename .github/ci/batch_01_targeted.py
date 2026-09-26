"""One branch-scoped BATCH-01 regression run; never a full gate or business E2E."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
BASE = '7d46dced3bcf06d44755cf53366c9e16bd465582'
BASE_SOURCE = '10d86748d682926a898d2d2dfecd43fd7f6962f6ed38602da7ae704e52aca154'
CANDIDATE_SOURCE = '31c692c5f3113446452e8d15faf95c29b019f433550bf4d0658c4f0428e54d20'
HEAD_BRANCH = 'setup/bos-gpt-orchestration-20260920'
BASE_BRANCH = 'fix/p10-002-task-sequence-20260919'
CI_PATHS = {'.github/ci/batch_01_targeted.py', '.github/workflows/bos-batch01-targeted.yml'}
IMPORT = 'erp.test_initial_import.InitialImportTests.test_actual_three_currency_import_preserves_overdue_origin_and_pending_stock'
FINANCE = 'finance.test_statement_concurrency.StatementConcurrencyTests'
REQUEST = 'operations.test_request_lengths.ProcurementRequestLengthTests'
REQUEST_FILE = Path('operations/test_request_lengths.py')
SHIP = 'erp.test_shipping_reference_lengths.ShippingReferenceLengthTests'
ARTIFACT = 'scripts.test_verify_evidence.VerifyE2EEvidenceTests'
SOURCE = 'scripts.test_source_digest.SourceDigestPathOrderTests'

# The probe runs after Django creates/migrates its test DB and before any case.
# It neither changes the test methods nor connects tests to the source database.
DJANGO_RUNNER = r'''
import json, logging, os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'verification_settings'
import django
django.setup()
# Preserve the actual SQL exception behind expected red HTTP 500 responses.
request_logger = logging.getLogger('django.request')
request_logger.setLevel(logging.ERROR)
request_logger.addHandler(logging.StreamHandler())
from django.db import connection
from django.test.runner import DiscoverRunner

class FocusedRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        old_config = super().setup_databases(**kwargs)
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_setting('server_version_num')")
            name, version = cursor.fetchone()
        proof = {'vendor': connection.vendor, 'database': name, 'version_num': int(version)}
        print('BOS_BATCH_TEST_DATABASE ' + json.dumps(proof), flush=True)
        if (proof['vendor'] != 'postgresql' or not 160000 <= proof['version_num'] < 170000
                or name != 'test_' + os.environ['BOS_TEST_DB_NAME']):
            raise RuntimeError('Refuse unexpected test database or PostgreSQL version')
        return old_config

raise SystemExit(bool(FocusedRunner(verbosity=2, interactive=False).run_tests(sys.argv[1:])))
'''


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def verifier(root):
    spec = importlib.util.spec_from_file_location('batch01_verifier_' + root.name,
                                                root / 'scripts/verify.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True, timeout=15).strip()


def source_databases(root):
    return {path.relative_to(root).as_posix(): sha(path)
            for path in sorted(root.rglob('*.sqlite3')) if '.git' not in path.parts}


def finalize(output):
    output.mkdir(parents=True, exist_ok=True)
    if not (output / 'report.json').exists():
        write_json(output / 'report.json', {
            'batch': 'BATCH-01', 'accepted_scoped': False, 'status': 'BLOCKED_BEFORE_RUNNER',
            'technical_ready': False, 'pilot_allowed': False, 'full_run': False,
            'business_e2e_run': False, 'run_id': os.environ.get('GITHUB_RUN_ID'),
            'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'), 'completed_at': now(),
            'reason': 'Runner report absent; inspect retained setup/dependency logs.'})
    index = {'schema': 'bos.batch01.sha256.v1', 'created_at': now(), 'files': {}}
    for path in sorted(output.rglob('*')):
        if path.is_file() and path.name != 'sha256-index.json':
            if path.is_symlink():
                raise ValueError('Refuse symlink in evidence output')
            index['files'][path.relative_to(output).as_posix()] = {
                'sha256': sha(path), 'bytes': path.stat().st_size}
    write_json(output / 'sha256-index.json', index)


def plan(include_ship):
    stages = [
        ('postgres-red-p10-003', 'baseline', [IMPORT], 1, 'guard', 120),
        ('postgres-red-f03', 'baseline',
         [FINANCE + '.test_distinct_import_proposals_same_source_have_one_immutable_effect'],
         1, 'invoice', 120),
        ('postgres-red-n1-request', 'baseline-request',
         [REQUEST + '.test_raw_overflow_refused_without_trimming_or_partial_writes'],
         1, 'request', 120),
        ('postgres-green-import', 'candidate', [IMPORT,
         'erp.test_initial_import_isolation.InitialImportIsolationTests',
         'erp.test_import_concurrency.ERPImportConcurrencyTests'], 15, None, 180),
        ('postgres-green-finance', 'candidate', [FINANCE], 5, None, 240),
        ('postgres-green-request-invoice', 'candidate', [REQUEST,
         'erp.test_value_boundaries.A07BoundaryTests.test_l01_invoice_code_30_ascii_and_unicode_round_trip',
         'erp.test_value_boundaries.A07BoundaryTests.test_l01_invoice_code_31_refused_without_truncation_or_trim'],
         4, None, 240),
    ]
    if include_ship:
        stages.append(('postgres-green-n1-ship', 'candidate', [SHIP], 2, None, 240))
    stages.append(('artifact-unit-f06', 'candidate', [ARTIFACT], 5, None, 90))
    stages.append(('source-unit-digest', 'candidate', [SOURCE], 2, None, 60))
    return [dict(label=label, source=source, labels=labels, expected_tests=count,
                 expected_red=red, timeout_seconds=timeout, status='NOT_RUN', accepted=False,
                 mode='unit' if label in ('artifact-unit-f06', 'source-unit-digest') else 'postgres16')
            for label, source, labels, count, red, timeout in stages]


def pg_connect(env, name):
    import psycopg
    return psycopg.connect(dbname=name, host=env['BOS_PGHOST'], port=env['BOS_PGPORT'],
                          user=env['BOS_PGUSER'], password=env['BOS_PGPASSWORD'],
                          connect_timeout=5, autocommit=True)


def source_canary(env, create=False):
    name = env['BOS_TEST_DB_NAME']
    if not re.fullmatch(r'bos_verify_[a-f0-9]{16}', name) or env.get('BOS_PG_DISPOSABLE') != '1':
        raise ValueError('Refuse unissued source database')
    with pg_connect(env, name) as db:
        actual, version = db.execute(
            "SELECT current_database(), current_setting('server_version_num')").fetchone()
        if actual != name or not 160000 <= int(version) < 170000:
            raise ValueError('Unexpected source database or PostgreSQL version')
        if create:
            db.execute('CREATE TABLE bos_batch_source_canary (id integer PRIMARY KEY, payload text NOT NULL)')
            db.execute('INSERT INTO bos_batch_source_canary VALUES (1, %s)',
                       ('Synthetic BATCH-01 source must remain unchanged',))
        tables = db.execute("SELECT table_schema, table_name, table_type FROM information_schema.tables "
                            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
                            'ORDER BY table_schema, table_name').fetchall()
        rows = db.execute('SELECT id, payload FROM bos_batch_source_canary ORDER BY id').fetchall()
    return {'database': name, 'version_num': int(version), 'tables': tables, 'rows': rows}


def evaluate(stage, stdout, stderr):
    raw = stdout + '\n' + stderr
    counts = re.findall(r'^Ran (\d+) tests? in ', stderr, flags=re.MULTILINE)
    stage['observed_test_counts'] = [int(value) for value in counts]
    summaries = re.findall(r'^(?:OK|FAILED)(?: \([^\n]*\))?$', stderr, flags=re.MULTILINE)
    stage['test_summaries'] = summaries
    stage['disallowed_test_outcomes'] = re.findall(
        r'\b(?:skipped|expected failures|unexpected successes)\s*=\s*\d+', '\n'.join(summaries))
    complete = (counts == [str(stage['expected_tests'])] and not stage.get('timed_out')
                and len(summaries) == 1 and not stage['disallowed_test_outcomes'])
    if stage['mode'] == 'postgres16':
        proofs = [json.loads(line.partition(' ')[2]) for line in stdout.splitlines()
                  if line.startswith('BOS_BATCH_TEST_DATABASE ')]
        stage['test_database_proofs'] = proofs
        complete = complete and len(proofs) == 1 and all(
            proof.get('vendor') == 'postgresql'
            and 160000 <= proof.get('version_num', 0) < 170000
            and proof.get('database') == 'test_' + stage['source_database'] for proof in proofs)
    if stage['expected_red'] is None:
        return complete and stage['exit_code'] == 0 and bool(re.search(r'^OK$', stderr, re.MULTILINE))
    failed = complete and stage['exit_code'] == 1 and 'FAILED (' in stderr
    if stage['expected_red'] == 'guard':
        markers = ('test_initial_import.py', "name.startswith('check_')", 'AssertionError: False is not true')
    elif stage['expected_red'] == 'invoice':
        markers = ('test_distinct_import_proposals_same_source_have_one_immutable_effect',
                   'django.db.utils.DataError: value too long for type character varying(30)')
    else:
        # A raw padded value passes the old strip-length check and reaches SQL.
        # An unrelated assertion failure is not accepted as this reproduction.
        markers = ('test_raw_overflow_refused_without_trimming_or_partial_writes',
                   '500 != 422', 'value too long for type character varying(')
    stage['expected_failure_markers'] = {marker: marker in raw for marker in markers}
    return failed and all(stage['expected_failure_markers'].values())


def run_stage(stage, root, output, report):
    started = time.monotonic()
    stage.update(started_at=now(), status='RUNNING', source_sha256=verifier(root).source_digest(),
                 commit=BASE if stage['source'].startswith('baseline') else report['candidate_commit'])
    write_json(output / 'report.json', report)
    stdout_path = output / (stage['label'] + '.stdout.log')
    stderr_path = output / (stage['label'] + '.stderr.log')
    stage.update(stdout_log=stdout_path.name, stderr_log=stderr_path.name)

    def process(env):
        for key in ('GITHUB_TOKEN', 'GH_TOKEN'):
            env.pop(key, None)
        env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', DJANGO_SETTINGS_MODULE='verification_settings')
        command = ([sys.executable, '-B', '-m', 'unittest', *stage['labels'], '-v']
                   if stage['mode'] == 'unit'
                   else [sys.executable, '-B', '-c', DJANGO_RUNNER, *stage['labels']])
        stage['command'] = command
        with stdout_path.open('w', encoding='utf-8') as out, stderr_path.open('w', encoding='utf-8') as err:
            try:
                result = subprocess.run(command, cwd=root, env=env, stdout=out, stderr=err,
                                        timeout=stage['effective_timeout_seconds'])
                stage['exit_code'] = result.returncode
            except subprocess.TimeoutExpired:
                stage.update(exit_code=None, timed_out=True)

    try:
        if stage['mode'] == 'unit':
            process(dict(os.environ))
        else:
            # The existing allocator owns CREATE/DROP of a new synthetic source.
            with tempfile.TemporaryDirectory(prefix='bos-batch01-db-') as directory:
                work = Path(directory)
                (work / 'media').mkdir()
                (work / 'source').mkdir()
                with verifier(root).database('postgres', work) as env:
                    stage['source_database'] = env['BOS_TEST_DB_NAME']
                    stage['source_canary_before'] = source_canary(env, create=True)
                    try:
                        process(env)
                    finally:
                        stage['source_canary_after'] = source_canary(env)
                        stage['source_database_unchanged'] = (
                            stage['source_canary_before'] == stage['source_canary_after'])
        stage['accepted'] = evaluate(stage, stdout_path.read_text(), stderr_path.read_text())
        if stage['mode'] == 'postgres16':
            stage['accepted'] = stage['accepted'] and stage['source_database_unchanged']
        stage['status'] = ('EXPECTED_RED' if stage['expected_red'] else 'PASS') if stage['accepted'] else 'FAIL'
    except Exception as exc:
        stage.update(status='BLOCKED', accepted=False, infrastructure_error=f'{type(exc).__name__}: {exc}')
        (output / (stage['label'] + '.exception.log')).write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        stage.update(completed_at=now(), duration_seconds=round(time.monotonic() - started, 3))
        for stream, path in (('stdout', stdout_path), ('stderr', stderr_path)):
            if path.exists():
                stage[stream + '_sha256'] = sha(path)
        write_json(output / 'report.json', report)
        print(json.dumps({key: stage.get(key) for key in
              ('label', 'status', 'accepted', 'exit_code', 'observed_test_counts', 'duration_seconds')},
              ensure_ascii=False), flush=True)


def run(args):
    started = time.monotonic()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'runner-started.json').exists():
        raise ValueError('Refuse repeat execution in an existing evidence directory')
    write_json(output / 'runner-started.json', {'started_at': now(), 'run_id': os.environ.get('GITHUB_RUN_ID')})
    report = dict(batch='BATCH-01', scope='new-card focused regressions only', started_at=now(),
                  accepted_scoped=False, technical_ready=False, pilot_allowed=False, full_run=False,
                  business_e2e_run=False, historical_p05_used=3, historical_p05_limit=3,
                  A09_retried=False, A10_retried=False, A11_retried=False,
                  python=platform.python_version(), run_id=os.environ.get('GITHUB_RUN_ID'),
                  run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'), candidate_commit=None,
                  checks=plan(args.include_ship), errors=[], ship_included=args.include_ship,
                  harness_sha256=sha(Path(__file__)), runner_timeout_seconds=900)
    checks_before = {}
    try:
        if (os.environ.get('GITHUB_EVENT_NAME') != 'pull_request'
                or os.environ.get('GITHUB_HEAD_REF') != HEAD_BRANCH
                or os.environ.get('GITHUB_BASE_REF') != BASE_BRANCH
                or os.environ.get('GITHUB_RUN_ATTEMPT') != '1'):
            raise ValueError('Only the approved PR branches and first attempt are allowed')
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        head = event['pull_request']['head']
        if head['repo']['full_name'] != os.environ['GITHUB_REPOSITORY']:
            raise ValueError('Refuse a forked PR candidate')
        if sys.version_info[:2] != (3, 12):
            raise ValueError('Python 3.12 required')
        baseline = args.baseline.resolve()
        if baseline == ROOT or baseline.is_relative_to(ROOT) or ROOT.is_relative_to(baseline):
            raise ValueError('Candidate and baseline must be separate sibling checkouts')
        report['candidate_commit'] = git(ROOT, 'rev-parse', 'HEAD')
        if (report['candidate_commit'] != os.environ['BOS_BATCH_CANDIDATE_SHA']
                or report['candidate_commit'] != head['sha']
                or git(baseline, 'rev-parse', 'HEAD') != BASE):
            raise ValueError('Unexpected candidate or baseline commit')
        changed = set(git(ROOT, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD^', 'HEAD').splitlines())
        report['head_changed_ci_paths'] = sorted(changed & CI_PATHS)
        if not report['head_changed_ci_paths']:
            raise ValueError('Current HEAD does not change the CI allowlist; skip app execution')
        for label, root in (('candidate', ROOT), ('baseline', baseline)):
            if git(root, 'status', '--porcelain', '--untracked-files=all'):
                raise ValueError('Checkout is not clean: ' + label)
            checks_before[label] = dict(source_sha256=verifier(root).source_digest(),
                                       source_databases=source_databases(root))
        report.update(source_before=checks_before, baseline_commit=BASE)
        if checks_before['baseline']['source_sha256'] != BASE_SOURCE:
            raise ValueError('Baseline runtime digest does not match the approved source')
        if checks_before['candidate']['source_sha256'] != CANDIDATE_SOURCE:
            raise ValueError('Candidate runtime digest differs from the frozen reviewed source')
        report['dependencies'] = {name: importlib.metadata.version(name)
                                  for name in ('Django', 'djangorestframework', 'psycopg')}
        with pg_connect(os.environ, 'postgres') as db:
            report['postgres_version_num'] = int(db.execute('SHOW server_version_num').fetchone()[0])
            report['postgres_version'] = db.execute('SELECT version()').fetchone()[0]
        if not 160000 <= report['postgres_version_num'] < 170000:
            raise ValueError('PostgreSQL 16 required')
        with tempfile.TemporaryDirectory(prefix='bos-batch01-baseline-request-') as directory:
            historical = Path(directory) / 'source'
            shutil.copytree(baseline, historical, ignore=shutil.ignore_patterns('.git', '__pycache__'))
            if verifier(historical).source_digest() != BASE_SOURCE:
                raise ValueError('Isolated baseline copy differs from approved runtime')
            if (historical / REQUEST_FILE).exists():
                raise ValueError('The requested new baseline regression already exists')
            shutil.copy2(ROOT / REQUEST_FILE, historical / REQUEST_FILE)
            report['baseline_overlay'] = {'only_added_file': REQUEST_FILE.as_posix(),
                'sha256': sha(ROOT / REQUEST_FILE), 'source_sha256': verifier(historical).source_digest()}
            roots = {'candidate': ROOT, 'baseline': baseline, 'baseline-request': historical}
            for stage in report['checks']:
                remaining = report['runner_timeout_seconds'] - (time.monotonic() - started)
                if remaining < 30:
                    report['errors'].append('Bounded runner budget exhausted; remaining stages NOT_RUN.')
                    break
                stage['effective_timeout_seconds'] = min(stage['timeout_seconds'], int(remaining))
                run_stage(stage, roots[stage['source']], output, report)
                if stage.get('infrastructure_error') or stage.get('timed_out'):
                    report['errors'].append('Stopped after infrastructure blocker/timeout; remaining stages not retried.')
                    break
        report['accepted_scoped'] = all(stage['accepted'] for stage in report['checks'])
    except Exception as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
        (output / 'runner.exception.log').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        report['source_unchanged'] = {}
        for label, before in checks_before.items():
            root = ROOT if label == 'candidate' else args.baseline.resolve()
            try:
                report['source_unchanged'][label] = before == {
                    'source_sha256': verifier(root).source_digest(), 'source_databases': source_databases(root)}
            except Exception as exc:
                report['source_unchanged'][label] = False
                report['errors'].append(f'Source verification {label}: {exc}')
        report['accepted_scoped'] = (report['accepted_scoped'] and not report['errors']
            and len(report['source_unchanged']) == 2 and all(report['source_unchanged'].values()))
        report.update(completed_at=now(), status='PASS_SCOPED' if report['accepted_scoped'] else 'FAIL_OR_BLOCKED')
        write_json(output / 'report.json', report)
        finalize(output)
    return 0 if report['accepted_scoped'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include-ship', action='store_true', help='Include the two reviewed N1-SHIP methods')
    parser.add_argument('--finalize-only', action='store_true', help='Index retained files; never execute tests')
    args = parser.parse_args()
    if args.finalize_only:
        finalize(args.output.resolve())
    else:
        if args.baseline is None:
            parser.error('--baseline is required for execution')
        sys.exit(run(args))
