"""Bounded new-card checks only; no full verifier or application server."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'owner-copy'
PYTHON = ROOT / 'venv/Scripts/python.exe'
FILES = ['operations/management/commands/bootstrap_bos_owner.py',
         'operations/test_bootstrap_owner.py', 'docs/FIRST_OWNER_UA.md']


def hashes():
    return {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() for name in FILES}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', choices=['sqlite', 'postgres'], required=True)
    args = parser.parse_args()
    stage = 'sqlite-warning' if args.backend == 'sqlite' else 'pg17'
    out = ROOT / 'owner-evidence' / stage
    out.mkdir()
    (out / 'media').mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(('BOS_', 'DJANGO_'))}
    env.update(BOS_VERIFY_DB=args.backend, BOS_TEST_MEDIA=str(out / 'media'),
               BOS_DATA_MODE='demo', PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    before = hashes()
    report = {'backend': args.backend, 'source_before': before, 'complete': False,
              'full_suite': False, 'installer_run': False}
    control, name = None, None
    if args.backend == 'postgres':
        import psycopg
        from psycopg import sql
        env.update(json.loads((ROOT / 'pg-secrets/runner-env.json').read_text()))
        control = psycopg.connect(host=env['BOS_PGHOST'], port=env['BOS_PGPORT'],
            dbname='postgres', user=env['BOS_PGUSER'], password=env['BOS_PGPASSWORD'],
            connect_timeout=5, autocommit=True)
        version = int(control.execute('SHOW server_version_num').fetchone()[0])
        assert version // 10000 == 16
        name = 'bos_verify_' + uuid.uuid4().hex[:16]
        report.update(issued_database=name, version_num=version)
        control.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        env['BOS_TEST_DB_NAME'] = name
        with psycopg.connect(host=env['BOS_PGHOST'], port=env['BOS_PGPORT'], dbname=name,
                user=env['BOS_PGUSER'], password=env['BOS_PGPASSWORD'], connect_timeout=5) as source:
            actual = source.execute('SELECT current_database()').fetchone()[0]
            assert actual == name
            assert source.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0] == 0
            report['source_database_before'] = {'database': actual, 'public_tables': 0}
    else:
        env['BOS_TEST_DB_NAME'] = str(out / 'source.sqlite3')
    test = ('operations.test_bootstrap_owner.FirstOwnerTests.test_getpass_warning_never_falls_back_to_echo_or_writes'
            if args.backend == 'sqlite' else 'operations.test_bootstrap_owner')
    command = [str(PYTHON), '-X', 'utf8', '-B', 'manage.py', 'test', test,
               '--settings=verification_settings', '--verbosity=2', '--noinput']
    report['command'] = command
    started = time.monotonic()
    try:
        with (out / 'raw.log').open('wb') as raw:
            result = subprocess.run(command, cwd=SOURCE, env=env, stdout=raw,
                                    stderr=subprocess.STDOUT, timeout=120)
        report['exit_code'] = result.returncode
        if control:
            with psycopg.connect(host=env['BOS_PGHOST'], port=env['BOS_PGPORT'], dbname=name,
                    user=env['BOS_PGUSER'], password=env['BOS_PGPASSWORD'], connect_timeout=5) as source:
                report['source_database_after'] = {
                    'database': source.execute('SELECT current_database()').fetchone()[0],
                    'public_tables': source.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]}
            assert report['source_database_after'] == report['source_database_before']
        report['source_after'] = hashes()
        assert report['source_after'] == before
        report['complete'] = result.returncode == 0
    except subprocess.TimeoutExpired:
        report.update(timed_out=True, exit_code=None)
    finally:
        report['elapsed_seconds'] = round(time.monotonic() - started, 3)
        if control:
            for owned in ('test_' + name, name):
                control.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(owned)))
            report['cleanup'] = not control.execute(
                'SELECT 1 FROM pg_database WHERE datname = ANY(%s)', [[name, 'test_' + name]]).fetchall()
            control.close()
        report['raw_sha256'] = hashlib.sha256((out / 'raw.log').read_bytes()).hexdigest()
        (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
