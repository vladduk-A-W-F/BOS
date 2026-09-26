"""One bounded PostgreSQL 16 check of the reviewed BATCH-02 additions."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
CI_PATHS = {'.github/ci/batch_02_targeted.py', '.github/workflows/bos-batch02-targeted.yml'}
# Frozen after sequential integration and independent review, before CI publication.
CANDIDATE_SOURCE = 'ce495b29214f21a80b8efd5bf41f6f219b5cb182b0453a7c43dac8899bc06ed5'

spec = importlib.util.spec_from_file_location('batch01_helpers', ROOT / '.github/ci/batch_01_targeted.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def finalize(output):
    if not (output / 'report.json').exists():
        h.write_json(output / 'report.json', dict(batch='BATCH-02', status='BLOCKED_BEFORE_RUNNER',
            accepted_scoped=False, technical_ready=False, pilot_allowed=False, full_run=False,
            business_e2e_run=False))
    h.finalize(output)
    index = json.loads((output / 'sha256-index.json').read_text())
    index['schema'] = 'bos.batch02.sha256.v1'
    h.write_json(output / 'sha256-index.json', index)


def plan():
    return [dict(label=name, source='candidate', labels=labels, expected_tests=count,
                 expected_red=None, timeout_seconds=180, mode='postgres16', status='NOT_RUN', accepted=False)
            for name, labels, count in (
                ('postgres-order-trace', ['erp.test_order_trace.OrderTraceTests'], 18),
                ('postgres-adjust-dependencies', ['erp.test_adjustment_proposals'], 24),
            )]


def run(output):
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'runner-started.json').exists():
        raise ValueError('Refuse repeat execution in existing evidence directory')
    h.write_json(output / 'runner-started.json', {'started_at': h.now()})
    report = dict(batch='BATCH-02', scope='new-card focused regressions only',
        started_at=h.now(), accepted_scoped=False, technical_ready=False, pilot_allowed=False,
        full_run=False, business_e2e_run=False, historical_p05_used=3, historical_p05_limit=3,
        A09_retried=False, A10_retried=False, A11_retried=False, candidate_commit=None,
        run_id=os.environ.get('GITHUB_RUN_ID'), run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),
        python=platform.python_version(), checks=plan(), errors=[], runner_timeout_seconds=600,
        harness_sha256=h.sha(Path(__file__)), reused_helper_sha256=h.sha(Path(h.__file__)))
    before = None
    try:
        if (os.environ.get('GITHUB_EVENT_NAME') != 'pull_request'
                or os.environ.get('GITHUB_HEAD_REF') != h.HEAD_BRANCH
                or os.environ.get('GITHUB_BASE_REF') != h.BASE_BRANCH
                or os.environ.get('GITHUB_RUN_ATTEMPT') != '1'):
            raise ValueError('Only approved branches and first attempt allowed')
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        head = event['pull_request']['head']
        report['candidate_commit'] = h.git(ROOT, 'rev-parse', 'HEAD')
        if (head['repo']['full_name'] != os.environ['GITHUB_REPOSITORY']
                or head['sha'] != report['candidate_commit']
                or head['sha'] != os.environ['BOS_BATCH_CANDIDATE_SHA']
                or sys.version_info[:2] != (3, 12)):
            raise ValueError('Unexpected candidate or Python version')
        changed = set(h.git(ROOT, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'HEAD^', 'HEAD').splitlines())
        report['head_changed_ci_paths'] = sorted(changed & CI_PATHS)
        if not report['head_changed_ci_paths'] or h.git(ROOT, 'status', '--porcelain', '--untracked-files=all'):
            raise ValueError('CI change and clean checkout required')
        before = dict(source_sha256=h.verifier(ROOT).source_digest(), source_databases=h.source_databases(ROOT))
        report['source_before'] = before
        if before['source_sha256'] != CANDIDATE_SOURCE:
            raise ValueError('Candidate differs from reviewed source')
        report['dependencies'] = {name: h.importlib.metadata.version(name) for name in ('Django', 'djangorestframework', 'psycopg')}
        with h.pg_connect(os.environ, 'postgres') as db:
            report['postgres_version_num'] = int(db.execute('SHOW server_version_num').fetchone()[0])
        if not 160000 <= report['postgres_version_num'] < 170000:
            raise ValueError('PostgreSQL 16 required')
        for stage in report['checks']:
            remaining = 600 - (time.monotonic() - started)
            if remaining < 30:
                raise RuntimeError('Runner budget exhausted; remaining stages not run')
            stage['effective_timeout_seconds'] = min(180, int(remaining))
            h.run_stage(stage, ROOT, output, report)
            if stage.get('infrastructure_error') or stage.get('timed_out'):
                raise RuntimeError('Stopped after infrastructure blocker/timeout; no retry')
        report['accepted_scoped'] = all(s['accepted'] for s in report['checks'])
    except Exception as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
        (output / 'runner.exception.log').write_text(traceback.format_exc())
    finally:
        after = dict(source_sha256=h.verifier(ROOT).source_digest(), source_databases=h.source_databases(ROOT))
        report['source_unchanged'] = before is not None and before == after
        report['accepted_scoped'] = bool(report['accepted_scoped'] and report['source_unchanged'] and not report['errors'])
        report.update(completed_at=h.now(), status='PASS_SCOPED' if report['accepted_scoped'] else 'FAIL_OR_BLOCKED')
        h.write_json(output / 'report.json', report)
        finalize(output)
    return 0 if report['accepted_scoped'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--finalize-only', action='store_true')
    args = parser.parse_args()
    if args.finalize_only:
        args.output.mkdir(parents=True, exist_ok=True)
        finalize(args.output.resolve())
    else:
        sys.exit(run(args.output.resolve()))
