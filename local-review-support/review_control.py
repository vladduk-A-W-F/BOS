"""Prepare/start/stop the owned synthetic review instance; no automatic deletion."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler
from urllib.error import HTTPError

from review_secrets import ROOT, CODE_ROOT, runtime_root, read_secrets, write_secrets
from review_process import Lifecycle, atomic_json

PYTHON = Path(sys.executable).resolve()
ORIGIN = 'http://127.0.0.1:8876'


def environment():
    result = os.environ.copy()
    for key in ('BOS_TEST_DB_NAME', 'BOS_TEST_MEDIA', 'BOS_VERIFY_DB', 'BOS_REVIEW_SEED_MODE',
                'BOS_DATA_MODE', 'PYTHONOPTIMIZE', 'DJANGO_SETTINGS_MODULE'):
        result.pop(key, None)
    result.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1',
                  DJANGO_SETTINGS_MODULE='review_settings',
                  PYTHONPATH=str(CODE_ROOT) + os.pathsep + str(ROOT / 'source'),
                  BOS_REVIEW_ROOT=str(ROOT),
                  TEMP=str(ROOT / 'temp'), TMP=str(ROOT / 'temp'))
    return result


def source_digest(source):
    result = subprocess.run([str(PYTHON), '-X', 'utf8', '-B', '-c',
                             'from scripts.verify import source_digest; print(source_digest())'],
                            cwd=source, env=environment(), capture_output=True, text=True,
                            encoding='utf-8', timeout=30, check=True)
    return result.stdout.strip()


def unused_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 8876))


def managed(command, mode='working', password=None):
    env = environment()
    env['BOS_REVIEW_SEED_MODE'] = mode
    result = subprocess.run([str(PYTHON), '-X', 'utf8', '-B', 'manage.py', *command],
                            cwd=ROOT / 'source', env=env, input=password,
                            capture_output=True, text=True, encoding='utf-8', timeout=120)
    (ROOT / 'logs' / (command[0] + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Preparation command failed; see logs/' + command[0] + '.log')


def prepare(source, expected):
    source = source.resolve()
    if ROOT.is_relative_to(source) or source.is_relative_to(ROOT):
        raise RuntimeError('Runtime and accepted source must be separate, non-nested directories.')
    if (ROOT / 'prepared.json').exists() or (ROOT / 'source').exists():
        raise RuntimeError('Review instance already exists; refusing to overwrite source or data.')
    if not source.is_dir() or source.resolve() == ROOT:
        raise RuntimeError('Explicit accepted source directory required.')
    unused_port()
    ROOT.mkdir(parents=True, exist_ok=True)
    for name in ('data', 'media', 'logs', 'temp', 'evidence'):
        (ROOT / name).mkdir(exist_ok=True)
    actual = source_digest(source)
    if actual != expected:
        raise RuntimeError('Accepted runtime source SHA differs; no database has been created.')
    shutil.copytree(source, ROOT / 'source', ignore=shutil.ignore_patterns(
        '.git', '.venv', '.venv-ci', 'venv', '__pycache__', '*.pyc', '*.sqlite*', '*.db',
        '.env', '.env.*', 'evidence', 'output', 'upload', 'media', 'rehearsal-media', 'node_modules'))
    if source_digest(ROOT / 'source') != expected or source_digest(source) != expected:
        raise RuntimeError('Copied source differs from accepted snapshot; initialization refused.')
    identity = {'username': 'bos-review-owner', 'password': secrets.token_urlsafe(24),
                'django_secret_key': secrets.token_urlsafe(48)}
    write_secrets(identity, root=ROOT)
    managed(['migrate', '--noinput'])
    managed(['bootstrap_bos_owner', '--username', identity['username'], '--password-stdin',
             '--allow-document-download'], password=identity['password'] + '\n')
    for name in ('seed_bos_demo', 'seed_erp_demo', 'seed_bos_workspace', 'seed_bos_ua'):
        managed([name], mode='demo')
    manifest = {'scope': 'Owned synthetic review instance; not pilot or production readiness',
                'source': str(source.resolve()), 'source_sha256': expected, 'url': ORIGIN,
                'prepared_at': datetime.now(timezone.utc).isoformat(), 'runtime_mode': 'working',
                'database': str(ROOT / 'data/review.sqlite3'), 'media': str(ROOT / 'media'),
                'username': identity['username'], 'password_store': 'private/user-secrets.dpapi',
                'credentials_encryption': 'Windows DPAPI CurrentUser', 'owner_is_staff': False,
                'owner_is_superuser': False, 'grants': ['view_document', 'download_document'],
                'support': support_manifest()}
    atomic_json(ROOT / 'prepared.json', manifest)
    print('Prepared synthetic review source ' + expected)


def lifecycle():
    command = [str(PYTHON), '-X', 'utf8', '-B', str(CODE_ROOT / 'review_server.py')]
    return Lifecycle(ROOT, command, getattr(sys, '_base_executable', PYTHON))


def support_manifest():
    files = ('review_control.py', 'review_process.py', 'review_server.py', 'review_settings.py',
             'review_secrets.py', 'browser_review.py', 'start.ps1', 'stop.ps1', 'show-login.ps1')
    return {name: hashlib.sha256((CODE_ROOT / name).read_bytes()).hexdigest() for name in files}


def probe_http(opener):
    # This endpoint is deliberately public in working mode. Runtime status requires login.
    with opener.open(ORIGIN + '/api/auth/csrf/', timeout=1) as response:
        auth = json.load(response)
        if response.status != 200 or auth.get('mode') != 'working' or auth.get('authenticated') is not False:
            raise RuntimeError('Public CSRF response does not prove anonymous working mode.')
    with opener.open(ORIGIN + '/', timeout=1) as response:
        if response.status != 200 or b'/assets/app.js' not in response.read():
            raise RuntimeError('Application HTML was not served.')
    with opener.open(ORIGIN + '/assets/app.js', timeout=2) as response:
        if (response.status != 200 or hashlib.sha256(response.read()).digest()
                != hashlib.sha256((ROOT / 'source/assets/app.js').read_bytes()).digest()):
            raise RuntimeError('Served application asset differs from accepted source.')
    return {'url': ORIGIN, 'root': 200, 'public_csrf': 200, 'app_js': 200,
            'asset_sha_matches_source': True, 'anonymous_auth': auth,
            'checked_at': datetime.now(timezone.utc).isoformat()}


def http_readiness(alive):
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        alive()
        try:
            receipt = probe_http(opener)
            alive()
            atomic_json(ROOT / 'evidence/http-readiness.json', receipt)
            return
        except HTTPError:
            raise  # auth/configuration errors are not connection-startup retries
        except OSError:
            time.sleep(.2)
    raise RuntimeError('Readiness timeout; owned cleanup or pending recovery will follow.')


def start():
    def preflight():
        prepared = json.loads((ROOT / 'prepared.json').read_text(encoding='utf-8'))
        if source_digest(ROOT / 'source') != prepared['source_sha256']:
            raise RuntimeError('Review source changed after preparation; refusing to start.')
        if support_manifest() != prepared['support']:
            raise RuntimeError('Review support changed after preparation; refusing to start.')
        original_source = Path(prepared['source']).resolve()
        if ROOT.is_relative_to(original_source) or original_source.is_relative_to(ROOT):
            raise RuntimeError('Runtime must remain outside accepted source.')
        unused_port()
    with (ROOT / 'logs/server.log').open('a', encoding='utf-8') as log:
        lifecycle().start(environment=environment(), cwd=ROOT / 'source', log=log,
                          readiness=http_readiness, preflight=preflight)
    print('Own persistent HTTP application ready: ' + ORIGIN)


def status_or_stop(stop=False):
    result = lifecycle().stop() if stop else lifecycle().status()
    print(json.dumps(result))


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'start', 'stop', 'status', 'show-login'])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--expected-source-sha')
    parser.add_argument('--runtime-root', type=Path, default=ROOT)
    args = parser.parse_args()
    ROOT = runtime_root(args.runtime_root)
    os.environ['BOS_REVIEW_ROOT'] = str(ROOT)
    if args.action == 'prepare':
        if not args.source or not args.expected_source_sha:
            parser.error('prepare needs exact --source and --expected-source-sha')
        with lifecycle().ops.lock(ROOT):
            prepare(args.source.resolve(), args.expected_source_sha)
    elif args.action == 'start':
        start()
    elif args.action in ('stop', 'status'):
        status_or_stop(stop=args.action == 'stop')
    else:
        identity = read_secrets(ROOT)
        print('Synthetic review login: ' + identity['username'])
        print('Password: ' + identity['password'])
        print('Use only in the local review browser; do not paste into chat or Git.')


if __name__ == '__main__':
    main()
