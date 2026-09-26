"""A held HTTP writer for maintenance tests, confined to one NEW test directory.

This is synthetic WSGI, not a BoS installation or a backup acceptance fixture.
It executes the canonical drain runner; no copied or injectable product module.
"""
import argparse
from importlib import metadata
from pathlib import Path
import sqlite3
import time

from scripts.start_server import run_application


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--timeout', type=float, required=True)
    args = parser.parse_args()
    work = args.work
    if not work.is_absolute() or work.is_symlink() or not work.is_dir() or any(work.iterdir()):
        raise RuntimeError('The synthetic worker requires an empty owned directory')
    runtime_version = metadata.version('waitress')
    if runtime_version != '3.0.2':
        raise RuntimeError('These real subprocess tests require pinned Waitress 3.0.2')
    db = work / 'ledger.sqlite3'
    with sqlite3.connect(db) as connection:
        connection.execute('CREATE TABLE writes (id TEXT PRIMARY KEY, value TEXT NOT NULL)')
    db.chmod(0o600)

    def application(environ, start_response):
        key = environ['PATH_INFO'].strip('/')
        if key == 'health':
            body = b'synthetic-waitress-ready'
        else:
            if not key.isascii() or not key.isdigit():
                raise ValueError('Only synthetic numeric request identifiers are accepted')
            (work / ('entered-' + key)).write_text('entered', encoding='utf-8')
            deadline = time.monotonic() + 30
            while not (work / 'release').exists():
                if time.monotonic() > deadline:
                    raise RuntimeError('The synthetic fixture release is missing')
                time.sleep(.01)
            with sqlite3.connect(db, timeout=5) as connection:
                connection.execute('INSERT INTO writes VALUES (?, ?)', (key, 'committed'))
            (work / ('committed-' + key)).write_text('committed', encoding='utf-8')
            body = ('completed:' + key).encode()
        start_response('200 OK', [('Content-Type', 'text/plain'), ('Content-Length', str(len(body)))])
        return [body]

    return run_application(application, port=0, version='0.2.9-test',
                           runtime_version=runtime_version, drain_timeout=args.timeout)


if __name__ == '__main__':
    raise SystemExit(main())
