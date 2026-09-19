"""One P06-F01 regression, with actual PostgreSQL red/green; not a full gate."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = 'b11aa8ce8f5855c34fa197e35b8fe77a850e9df0'
BASE_SOURCE = 'c324a157493fb9681ba0d55bfcfdbf70e402d07cae5c48338481fb975ab2e0d8'
TEST = 'operations.test_seed_demo_sequence.DemoTaskSequenceTests'
RED_TEST = TEST + '.test_new_task_after_seed_preserves_all_eight_demo_tasks'
REGRESSION = Path('operations/test_seed_demo_sequence.py')
SEED = Path('operations/management/commands/seed_bos_demo.py')


def verifier(root):
    spec = importlib.util.spec_from_file_location('p10_verifier', root / 'scripts/verify.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = dict(task='P10-002', origin='P06-F01', scope='focused regression only',
                  started_at=datetime.now(timezone.utc).isoformat(),
                  python=platform.python_version(), system=platform.system(),
                  commit=git(ROOT, 'rev-parse', 'HEAD'),
                  source_sha256=verifier(ROOT).source_digest(),
                  regression_sha256=sha(ROOT / REGRESSION), seed_sha256=sha(ROOT / SEED),
                  run_id=os.environ.get('GITHUB_RUN_ID'),
                  run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),
                  checks=[], accepted=False, technical_ready=False, pilot_allowed=False,
                  full_run=False, full_status='NOT_RUN: existing attempt restrictions',
                  errors=[])
    source_dbs = {p.relative_to(ROOT).as_posix(): sha(p) for p in ROOT.rglob('*.sqlite3')}
    try:
        if report['commit'] != os.environ['GITHUB_SHA']:
            raise ValueError('Unexpected candidate checkout')
        if sys.version_info[:2] != (3, 12):
            raise ValueError('Python 3.12 required')
        baseline = args.baseline.resolve()
        if git(baseline, 'rev-parse', 'HEAD') != BASE:
            raise ValueError('Unexpected baseline checkout')
        original_source = verifier(baseline).source_digest()
        if original_source != BASE_SOURCE:
            raise ValueError('Baseline source changed')
        report['baseline'] = dict(commit=BASE, source_sha256=original_source,
                                  seed_sha256=sha(baseline / SEED))
        # Only add the identical behavioral test to an isolated historical checkout.
        shutil.copy2(ROOT / REGRESSION, baseline / REGRESSION)
        report['baseline']['source_with_regression_sha256'] = verifier(baseline).source_digest()
        import psycopg
        with psycopg.connect(dbname='postgres', host=os.environ['BOS_PGHOST'],
                             port=os.environ['BOS_PGPORT'], user=os.environ['BOS_PGUSER'],
                             password=os.environ['BOS_PGPASSWORD'], connect_timeout=5) as db:
            report['postgres_version_num'] = int(db.execute('SHOW server_version_num').fetchone()[0])
            report['postgres_version'] = db.execute('SELECT version()').fetchone()[0]
        if not 160000 <= report['postgres_version_num'] < 170000:
            raise ValueError('PostgreSQL 16 required')

        for label, root, backend, test in (
                ('postgres-before', baseline, 'postgres', RED_TEST),
                ('postgres-after', ROOT, 'postgres', TEST),
                ('sqlite-after', ROOT, 'sqlite', TEST)):
            v = verifier(root)
            with tempfile.TemporaryDirectory(prefix='bos-p10-002-') as directory:
                with v.database(backend, Path(directory)) as env:
                    env.pop('GITHUB_TOKEN', None)
                    result, receipt = v.execute(
                        [sys.executable, '-B', 'manage.py', 'test', test, '--noinput',
                         '--settings=verification_settings', '--verbosity=2'],
                        root, env, output / (label + '.log'))
                raw = (output / (label + '.log')).read_text(encoding='utf-8')
                if label == 'postgres-before':
                    accepted = (result.returncode == 1 and not receipt.get('timed_out')
                                and 'duplicate key value violates unique constraint "tasks_task_pkey"' in raw
                                and 'Key (id)=(1) already exists.' in raw
                                and 'Ran 1 test in' in raw and 'FAILED (errors=1)' in raw)
                    outcome = 'EXPECTED_PK_COLLISION' if accepted else 'UNEXPECTED_RESULT'
                else:
                    accepted = result.returncode == 0 and 'Ran 6 tests in' in raw and '\nOK\n' in raw
                    outcome = 'PASS' if accepted else 'FAIL'
                report['checks'].append(dict(label=label, backend=backend, accepted=accepted,
                                             outcome=outcome, **receipt))
                print(json.dumps(report['checks'][-1], ensure_ascii=False), flush=True)
        report['accepted'] = len(report['checks']) == 3 and all(c['accepted'] for c in report['checks'])
    except Exception as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
        report['accepted'] = False
    finally:
        report['source_database_count'] = len(source_dbs)
        report['source_databases_unchanged'] = source_dbs == {
            p.relative_to(ROOT).as_posix(): sha(p) for p in ROOT.rglob('*.sqlite3')}
        report['source_unchanged'] = report['source_sha256'] == verifier(ROOT).source_digest()
        report['accepted'] = report['accepted'] and report['source_databases_unchanged'] and report['source_unchanged']
        report['completed_at'] = datetime.now(timezone.utc).isoformat()
        report['files'] = {p.name: sha(p) for p in output.iterdir() if p.is_file()}
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if report['accepted'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    sys.exit(run(parser.parse_args()))
