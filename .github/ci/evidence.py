"""GitHub provenance for the existing verifier; never replaces its eleven gates."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
SUITES = {'sqlite': {1, 2, 3, 5}, 'postgres': {1, 2, 3, 5},
          'e2e': {6}, 'windows': {1, 2, 3, 6}, 'ui': {10}, 'full': set(range(1, 12))}
CHILDREN = ('sqlite', 'postgres', 'e2e', 'windows', 'ui')
PASS = 'ПРОЙДЕНО'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_sha():
    digest = hashlib.sha256()
    for path in sorted((ROOT / '.github').rglob('*'), key=lambda p: p.as_posix()):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            digest.update(path.relative_to(ROOT).as_posix().encode() + b'\0')
            digest.update(path.read_bytes().replace(b'\r\n', b'\n') + b'\0')
    return digest.hexdigest()


def context():
    spec = importlib.util.spec_from_file_location('bos_verify', ROOT / 'scripts/verify.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)  # __main__ is not entered; no app or DB operation.
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    expected = os.environ['GITHUB_SHA']
    if commit != expected:
        raise ValueError('checkout commit != GITHUB_SHA')
    return dict(repository=os.environ['GITHUB_REPOSITORY'], commit=commit,
                source_sha256=verifier.source_digest(), ci_sha256=config_sha(),
                run_id=os.environ['GITHUB_RUN_ID'], run_attempt=os.environ['GITHUB_RUN_ATTEMPT'])


def pipeline(ctx):
    return f"{ctx['repository']}/{ctx['run_id']}/{ctx['run_attempt']}"


def job_url(ctx, job):
    # Query this attempt, not the latest attempt or a job key masquerading as a job ID.
    url = (f"https://api.github.com/repos/{ctx['repository']}/actions/runs/"
           f"{ctx['run_id']}/attempts/{ctx['run_attempt']}/jobs?per_page=100")
    request = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
        'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.urlopen(request, timeout=30) as response:
        jobs = json.load(response)['jobs']
    matches = [x['html_url'] for x in jobs if x['name'] == job]
    if len(matches) != 1:
        raise ValueError(f'Cannot identify actual job URL: {job}')
    return matches[0]


def database_versions(suite):
    versions = {'sqlite': sqlite3.sqlite_version}
    if suite in ('postgres', 'e2e', 'windows', 'full'):
        import psycopg
        with psycopg.connect(host=os.environ['BOS_PGHOST'], port=os.environ['BOS_PGPORT'],
                             user=os.environ['BOS_PGUSER'], password=os.environ['BOS_PGPASSWORD'],
                             dbname='postgres', connect_timeout=15) as connection:
            with connection.cursor() as cursor:
                cursor.execute('SHOW server_version_num')
                version_num = int(cursor.fetchone()[0])
                cursor.execute('SELECT version()')
                versions['postgresql'] = cursor.fetchone()[0]
                versions['postgresql_version_num'] = version_num
        if not 160000 <= version_num < 170000:
            raise ValueError(f'PostgreSQL 16 required, found {version_num}')
    return versions


def report_errors(report, suite, ctx, actual_job_url):
    errors = []
    if report.get('suite') != suite or report.get('complete') is not True:
        errors.append('suite/complete')
    if report.get('source_databases_unchanged') is not True:
        errors.append('source databases changed or not proven')
    if report.get('source_sha256') != ctx['source_sha256']:
        errors.append('source_sha256')
    ci = report.get('ci', {})
    if ci.get('commit') != ctx['commit'] or ci.get('pipeline_id') != pipeline(ctx):
        errors.append('commit/run/attempt')
    if not actual_job_url or ci.get('job_url') != actual_job_url:
        errors.append('job_url')
    if not re.fullmatch(r'https://github\.com/' + re.escape(ctx['repository']) +
                        r'/actions/runs/' + re.escape(ctx['run_id']) + r'/job/\d+', actual_job_url or ''):
        errors.append('job URL does not belong to this run')
    gates = report.get('gates', [])
    if (len(gates) != len(SUITES[suite]) or
            {g.get('id') for g in gates} != SUITES[suite] or
            any(g.get('status') != PASS for g in gates)):
        errors.append('gates')
    env = report.get('environment', {})
    if env.get('python_minor') != [3, 12]:
        errors.append('Python 3.12')
    if env.get('system') != ('Windows' if suite == 'windows' else 'Linux'):
        errors.append('OS')
    return errors


def file_map(directory):
    return {p.relative_to(directory).as_posix(): sha(p) for p in sorted(directory.rglob('*'))
            if p.is_file() and p.name != 'ci-receipt.json'}


def upstream_errors(directory, ctx, needs):
    errors = []
    if set(needs) != set(CHILDREN):
        errors.append('Expected all five prerequisite job results')
    for suite in CHILDREN:
        if needs.get(suite, {}).get('result') != 'success':
            errors.append(f'{suite}: job did not succeed')
        folder = directory / f"bos-{ctx['run_id']}-{ctx['run_attempt']}-{suite}"
        try:
            receipt = json.loads((folder / 'ci-receipt.json').read_text(encoding='utf-8'))
            report = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
            if any(receipt.get(key) != value for key, value in ctx.items()):
                errors.append(f'{suite}: stale source/config/commit/run/attempt')
            if (receipt.get('schema') != 1 or receipt.get('suite') != suite or
                    receipt.get('job') != suite or receipt.get('state') != 'passed' or
                    receipt.get('verify_exit_code') != 0 or receipt.get('errors')):
                errors.append(f'{suite}: incomplete receipt')
            if receipt.get('files') != file_map(folder) or 'verify-console.log' not in receipt.get('files', {}):
                errors.append(f'{suite}: missing or altered raw evidence')
            if suite in ('postgres', 'e2e', 'windows') and not (
                    160000 <= receipt.get('databases', {}).get('postgresql_version_num', 0) < 170000):
                errors.append(f'{suite}: PostgreSQL 16 not proven')
            errors += [f'{suite}: {e}' for e in report_errors(report, suite, ctx, receipt.get('job_url'))]
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
            errors.append(f'{suite}: unreadable evidence ({type(exc).__name__})')
    return errors


def execute(command, log_path, env):
    with log_path.open('w', encoding='utf-8') as log:
        child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        with child.stdout:
            for line in child.stdout:
                log.write(line)
                log.flush()
                print(line, end='', flush=True)
        return child.wait()


def run(suite, output, upstream):
    if (output / 'report.json').exists() or (output / 'ci-receipt.json').exists():
        raise ValueError('Refusing to reuse prior verification output')
    output.mkdir(parents=True, exist_ok=True)
    receipt = dict(schema=1, suite=suite, job=os.environ['GITHUB_JOB'], state='not_run',
                   verify_exit_code=None, errors=[], databases={},
                   runner={'system': platform.system(), 'python': platform.python_version()})
    exit_code = 1
    try:
        ctx = context()
        receipt.update(ctx)
        if platform.python_version_tuple()[:2] != ('3', '12'):
            raise ValueError('CI requires actual Python 3.12')
        receipt['job_url'] = job_url(ctx, receipt['job'])
        receipt['databases'] = database_versions(suite)
        env = dict(os.environ, CI_PIPELINE_ID=pipeline(ctx), CI_COMMIT_SHA=ctx['commit'],
                   CI_JOB_URL=receipt['job_url'], PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
        env.pop('GITHUB_TOKEN', None)  # metadata API credential is not needed by application tests
        if suite == 'full':
            needs = json.loads(os.environ['BOS_NEEDS_JSON'])
            receipt['errors'] += upstream_errors(upstream, ctx, needs)
            env['BOS_WINDOWS_REPORT'] = str(upstream / f"bos-{ctx['run_id']}-{ctx['run_attempt']}-windows/report.json")
            # A10 denied activation/upgrade/rollback must never be retried through this workflow.
            if (ROOT / 'scripts/check_upgrade.py').exists():
                raise ValueError('A10 stop condition: upgrade execution is not authorized by P04')
        code = execute([sys.executable, 'scripts/verify.py', '--suite', suite,
                        '--output', str(output / 'report.json')], output / 'verify-console.log', env)
        receipt['verify_exit_code'] = code
        exit_code = code if code != 0 else 1
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
        receipt['errors'] += report_errors(report, suite, ctx, receipt['job_url'])
        receipt['state'] = 'passed' if code == 0 and not receipt['errors'] else 'failed'
        exit_code = code if code != 0 else (0 if receipt['state'] == 'passed' else 1)
    except Exception as exc:
        receipt['errors'].append(f'{type(exc).__name__}: {exc}')
    finally:
        receipt['files'] = file_map(output)
        (output / 'ci-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'suite': suite, 'state': receipt['state'], 'errors': receipt['errors']}, ensure_ascii=False))
    return exit_code


def finish(suite, output):
    # Runs after dependency/setup failure too; this is explicitly not a verifier report.
    if not (output / 'ci-receipt.json').exists():
        output.mkdir(parents=True, exist_ok=True)
        receipt = dict(schema=1, suite=suite, state='not_run', verify_exit_code=None,
                       errors=['Verification step was not completed; inspect GitHub job logs.'],
                       setup_steps=json.loads(os.environ.get('BOS_STEPS_JSON', '{}')),
                       files=file_map(output))
        try:
            receipt.update(context(), job=os.environ['GITHUB_JOB'])
            receipt['job_url'] = job_url(receipt, receipt['job'])
        except Exception as exc:
            receipt['errors'].append(type(exc).__name__)
        (output / 'ci-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    receipt = json.loads((output / 'ci-receipt.json').read_text(encoding='utf-8'))
    receipt['setup_steps'] = json.loads(os.environ.get('BOS_STEPS_JSON', '{}'))
    if any(s.get('outcome') in ('failure', 'cancelled') for s in receipt['setup_steps'].values()):
        receipt['errors'].append('A job step failed or was cancelled; inspect setup_steps.')
        if receipt.get('state') == 'passed':
            receipt['state'] = 'failed'
    receipt['files'] = file_map(output)
    (output / 'ci-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0 if receipt.get('state') == 'passed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('run', 'finish'))
    parser.add_argument('--suite', choices=SUITES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--upstream', type=Path, default=Path('_no_upstream_'))
    args = parser.parse_args()
    sys.exit(run(args.suite, args.output, args.upstream) if args.command == 'run' else finish(args.suite, args.output))
