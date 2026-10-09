"""Owner-local delivery steps for a local Claude session on the owner's Windows PC.

Run every step from the NEW accepted source checkout with the owner-local Python, in any shell:
    <python> -X utf8 -B <New>/scripts/owner_local_delivery.py <step> --root <Root> [--backup <dir>]

Order (docs/strategy/OWNER_LOCAL_DELIVERY_UA.md): inspect -> preflight -> [bos3_local.py stop, old source]
-> backup -> migrate -> bind -> [bos3_local.py start, new source] -> verify. On any mismatch:
[bos3_local.py stop] -> rollback -> [bos3_local.py start, old source].
This tool never starts or stops the server, never runs init, seed, reset or flush, never prints secrets,
password hashes or database rows, and changes nothing in the installation before a verified backup.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))

from scripts import bos3_local as local  # noqa: E402

# Migrations this release may apply by itself: Django state only, no SQL. Anything else needs its own plan.
ALLOWED_MIGRATIONS = frozenset({'connectors.0003_connector_url_kind'})
STATE_FILES = ('prepared.json', 'owner-access.json', 'runtime-secrets.json')
# Tables a sign-in or the running source re-reader may legitimately grow; they must never shrink.
VOLATILE_TABLES = frozenset({'django_session', 'operations_loginattempt', 'connectors_connectorsnapshot'})
# Columns they write in place (connectors.views.sync_connector); every other column must stay as it was.
IGNORED_COLUMNS = {'auth_user': frozenset({'last_login'}),
                   'connectors_connector': frozenset({'status', 'last_error', 'last_sync_at'})}
JOURNAL = 'DELIVERY.json'
PLANNED = re.compile(r'^(\w+)\.(\d{4}\w*)\s*$', re.M)
STAMPED = re.compile(r'^\d{8}-\d{6}Z-')                  # names of this tool's backups


class DeliveryError(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')   # UTC: names sort in time order


def _sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _files(base):
    base = Path(base)
    return {p.relative_to(base).as_posix(): _sha(p) for p in sorted(base.rglob('*')) if p.is_file()}


def _version(source=SOURCE):
    match = re.search(r"VERSION\s*=\s*'([^']+)'", (source / 'boss_project' / 'version.py').read_text(encoding='utf-8'))
    return match.group(1) if match else None


def _git_clean(source):
    result = subprocess.run(['git', '-C', str(source), 'status', '--porcelain'], capture_output=True, text=True)
    return result.returncode == 0 and result.stdout == ''


def _readonly(database):
    return sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)


def fingerprints(database):
    """Row count and content hash per table. Values never leave this function."""
    out = {}
    connection = _readonly(database)
    try:
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for table in tables:
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')
                       if row[1] not in IGNORED_COLUMNS.get(table, ())]
            select = ', '.join(f'"{column}"' for column in columns)
            try:
                rows = connection.execute(f'SELECT {select} FROM "{table}" ORDER BY rowid').fetchall()
            except sqlite3.OperationalError:                     # a WITHOUT ROWID table
                rows = connection.execute(f'SELECT {select} FROM "{table}" ORDER BY {select}').fetchall()
            digest = hashlib.sha256()
            for row in rows:
                digest.update(json.dumps(row, default=bytes.hex, ensure_ascii=False).encode('utf-8') + b'\n')
            out[table] = {'rows': len(rows), 'sha256': digest.hexdigest()}
    finally:
        connection.close()
    return out


def compare(before, after, applied=()):
    """Problems between two fingerprint maps; an empty list means the data is unchanged."""
    problems = []
    for table in sorted(set(before) | set(after)):
        old, new = before.get(table), after.get(table)
        if old is None or new is None:
            problems.append(f'{table}: table {"added" if old is None else "missing"}')
        elif table == 'django_migrations':
            if new['rows'] != old['rows'] + len(applied):
                problems.append(f'django_migrations: {old["rows"]} -> {new["rows"]} rows, expected +{len(applied)}')
        elif table in VOLATILE_TABLES:
            if new['rows'] < old['rows']:
                problems.append(f'{table}: rows decreased {old["rows"]} -> {new["rows"]}')
        elif new != old:
            problems.append(f'{table}: content differs ({old["rows"]} -> {new["rows"]} rows)')
    return problems


def _applied(database):
    connection = _readonly(database)
    try:
        return {f'{app}.{name}' for app, name in connection.execute('SELECT app, name FROM django_migrations')}
    finally:
        connection.close()


def _journal(backup, step, result):
    path = Path(backup) / JOURNAL
    entries = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    entries.append({'step': step, 'at': _now(), **result})
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def _problems(paths, backup, saved):
    """Differences of the live database from the backup beyond allowlisted migrations; empty means unchanged.

    The applied migrations are measured in the two databases, not taken from the journal, so a repeated step
    or a new attempt after a rollback counts exactly what is there.
    """
    applied = sorted(_applied(paths['database']) - _applied(backup / paths['database'].name))
    outside = [f'django_migrations: {name} is outside the allowlist' for name in applied
               if name not in ALLOWED_MIGRATIONS]
    return outside + compare(saved, fingerprints(paths['database']), applied)


def _listening(port=None):
    """Whether a server accepts connections on the local port. A bind probe would also fail on TIME_WAIT."""
    try:
        with socket.create_connection(('127.0.0.1', port or local.PORT), timeout=2):
            return True
    except OSError:
        return False


def _require_stopped(paths):
    if paths['process'].exists():
        raise DeliveryError('A process receipt exists: run bos3_local.py stop (or status) with the installed '
                            'source first; never delete the receipt by hand.')
    if _listening():
        raise DeliveryError(f'Port {local.PORT} answers: another server is running.')


def _require_backup(paths, backup):
    """Only the newest complete backup this tool made for this installation."""
    backup, folder = Path(backup).resolve(), paths['root'] / 'backups'
    if backup.parent != folder or not STAMPED.match(backup.name) or not all((backup / name).is_file() for name in (
            JOURNAL, 'FINGERPRINTS.json', 'MANIFEST.json', 'prepared.json')):
        raise DeliveryError('Not a backup this tool made for this installation: ' + backup.as_posix())
    newer = sorted(p.name for p in folder.iterdir()
                   if STAMPED.match(p.name) and p.name > backup.name and (p / JOURNAL).is_file())
    if newer:
        raise DeliveryError('A newer backup exists (' + ', '.join(newer) + '): use the one printed by the '
                            'last backup step.')
    return backup


def _copy_database(source, target):
    """SQLite backup API copy; returns the integrity check of the target."""
    reader, writer = _readonly(source), sqlite3.connect(target)
    try:
        reader.backup(writer)
        return writer.execute('PRAGMA integrity_check').fetchone()[0]
    finally:
        reader.close()
        writer.close()


def _secret(paths):
    secret = local.read_json(paths['runtime_secrets']).get('django_secret')
    if not secret:
        raise DeliveryError('Private runtime secrets do not contain the local Django secret.')
    return secret


def inspect(paths, backup=None):
    prepared = local.read_json(paths['prepared'])
    receipt = local.read_json(paths['process']) if paths['process'].exists() else None
    clean = _git_clean(SOURCE)
    return {                                               # paths with '/': the same in PowerShell and Git Bash
        'installed_source': Path(prepared['source']).as_posix(),
        'installed_source_sha256': prepared.get('source_sha256'),
        'dataset': prepared.get('dataset', 'bos3'), 'fixture_id': prepared.get('fixture_id'),
        'process_receipt': None if receipt is None else (receipt.get('status') if receipt.get('process')
                                                          else 'recovery_pending'),
        'new_source': SOURCE.as_posix(), 'new_version': _version(), 'new_clean': clean,
        'new_source_sha256': local.digest_source(SOURCE) if clean else None,
    }


def preflight(paths, backup=None):
    """Read-only. A running installation gets the full owned-process preflight; a stopped one, its pins."""
    prepared = local.read_json(paths['prepared'])
    installed, pin = prepared['source'], prepared['source_sha256']
    if paths['process'].exists():
        from scripts import bos3_delivery_preflight
        return {'running': True, **bos3_delivery_preflight.check(paths['root'], installed, pin)}
    if local.digest_source(Path(installed)) != pin:
        raise DeliveryError('The installed source no longer matches its pin.')
    return {'running': False, 'installed_pin': 'OK'}


def backup(paths, backup=None):
    _require_stopped(paths)
    target = paths['root'] / 'backups' / (_stamp() + '-' + (_version() or 'unknown'))
    target.mkdir(parents=True)
    if os.name == 'nt':
        local.protect_path(target, directory=True)       # private to the owner and SYSTEM, verified
    copy = target / paths['database'].name
    if _copy_database(paths['database'], copy) != 'ok':  # live database -> backup copy
        raise DeliveryError('The backup copy failed its integrity check.')
    if paths['media'].exists():
        shutil.copytree(paths['media'], target / 'media')
    else:
        (target / 'media').mkdir()
    for name in STATE_FILES:
        shutil.copy2(paths['state'] / name, target / name)
    if paths['media'].exists() and _files(paths['media']) != _files(target / 'media'):
        raise DeliveryError('The media copy differs from the original.')
    if any(_sha(paths['state'] / name) != _sha(target / name) for name in STATE_FILES):
        raise DeliveryError('A state file copy differs from the original.')
    saved = fingerprints(copy)
    if fingerprints(paths['database']) != saved:
        raise DeliveryError('The database copy differs from the original.')
    (target / 'FINGERPRINTS.json').write_text(json.dumps(saved, indent=2) + '\n', encoding='utf-8')
    manifest = {name: _sha(target / name) for name in (copy.name, *STATE_FILES)}
    manifest.update({'media/' + name: digest for name, digest in _files(target / 'media').items()})
    (target / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return _journal(target, 'backup', {'backup': target.as_posix(), 'files': len(manifest),
                                       'bytes': sum((target / name).stat().st_size for name in manifest),
                                       'tables': len(saved)})


def migrate(paths, backup):
    _require_stopped(paths)
    backup = _require_backup(paths, backup)
    saved = json.loads((backup / 'FINGERPRINTS.json').read_text(encoding='utf-8'))
    env = local.environment(paths, SOURCE, _secret(paths))
    local.managed(['migrate', '--plan'], env, paths)
    planned = ['.'.join(match) for match in PLANNED.findall((paths['logs'] / 'migrate.log').read_text(encoding='utf-8'))]
    unexpected = sorted(set(planned) - ALLOWED_MIGRATIONS)
    if unexpected:
        raise DeliveryError('Migrations outside this release allowlist need their own plan: ' + ', '.join(unexpected))
    if planned:
        local.managed(['migrate', '--noinput'], env, paths)
    missing = sorted(set(planned) - _applied(paths['database']))
    connection = _readonly(paths['database'])
    try:
        integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
    finally:
        connection.close()
    problems = _problems(paths, backup, saved)
    if missing or integrity != 'ok' or problems:
        raise DeliveryError(f'Migration check failed: missing={missing} integrity={integrity} problems={problems}')
    return _journal(backup, 'migrate', {'applied': planned, 'integrity': integrity, 'data_unchanged': True})


def bind(paths, backup):
    _require_stopped(paths)
    backup = _require_backup(paths, backup)
    saved = json.loads((backup / 'prepared.json').read_text(encoding='utf-8'))
    digest = local.digest_source(SOURCE)
    from scripts.bos3_prepared_update import update_prepared_source
    update_prepared_source(paths['prepared'], str(SOURCE), digest)
    prepared = local.read_json(paths['prepared'])
    changed = {key for key in set(saved) | set(prepared) if saved.get(key) != prepared.get(key)}
    if prepared.get('source') != str(SOURCE) or prepared.get('source_sha256') != digest or (
            changed - {'source', 'source_sha256'}):
        raise DeliveryError('prepared.json is not bound to the new source as expected: ' + ', '.join(sorted(changed)))
    return _journal(backup, 'bind', {'source': str(SOURCE), 'source_sha256': digest})


def _get(path):
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(f'http://127.0.0.1:{local.PORT}{path}', timeout=15) as response:
            return response.status, response.read().decode('utf-8', 'replace')
    except HTTPError as error:
        return error.code, ''
    except OSError:
        return None, ''


def _owner_password(database, username):
    connection = _readonly(database)
    try:
        row = connection.execute('SELECT password FROM auth_user WHERE username = ?', (username,)).fetchone()
    finally:
        connection.close()
    return hashlib.sha256(row[0].encode('utf-8')).hexdigest() if row else None


def verify(paths, backup):
    """Right after start and before anyone signs in: the new code serves, the owner's data is unchanged."""
    backup = _require_backup(paths, backup)
    receipt = local.read_json(paths['process']) if paths['process'].exists() else {}
    saved = json.loads((backup / 'FINGERPRINTS.json').read_text(encoding='utf-8'))
    manifest = json.loads((backup / 'MANIFEST.json').read_text(encoding='utf-8'))
    username = local.read_json(paths['prepared']).get('owner_username')
    home_status, home = _get('/')
    title = re.search(r'<title>(.*?)</title>', home, re.S)
    problems = _problems(paths, backup, saved)
    checks = {
        'server_ready_on_new_source': receipt.get('status') == 'ready' and receipt.get('source') == str(SOURCE)
        and receipt.get('source_sha256') == local.digest_source(SOURCE),
        'page_shows_version': home_status == 200 and bool(title) and _version() in title.group(1),
        'csrf_200': _get('/api/auth/csrf/')[0] == 200,
        'mcp_not_open': _get('/mcp/')[0] in (404, 405),   # 404 without keys; 405 (POST with a key only) after a key
        'data_unchanged': not problems,
        'owner_password_unchanged': _owner_password(paths['database'], username) is not None and (
            _owner_password(paths['database'], username) == _owner_password(backup / paths['database'].name, username)),
        'media_unchanged': _files(paths['media']) == {k[6:]: v for k, v in manifest.items() if k.startswith('media/')},
        'private_state_unchanged': all(_sha(paths['state'] / name) == manifest[name]
                                       for name in ('owner-access.json', 'runtime-secrets.json')),
    }
    return _journal(backup, 'verify', {'checks': checks, 'problems': problems,
                                       'result': 'PASS' if all(checks.values()) else 'FAIL'})


def rollback(paths, backup):
    """Backup -> live database, media and pin. Whatever it replaces is kept in <Backup>/replaced-<UTC time>."""
    _require_stopped(paths)
    backup = _require_backup(paths, backup)
    saved_prepared = json.loads((backup / 'prepared.json').read_text(encoding='utf-8'))
    manifest = json.loads((backup / 'MANIFEST.json').read_text(encoding='utf-8'))
    saved = json.loads((backup / 'FINGERPRINTS.json').read_text(encoding='utf-8'))
    copy, media = backup / paths['database'].name, {k[6:]: v for k, v in manifest.items() if k.startswith('media/')}
    if (_sha(copy) != manifest[copy.name] or fingerprints(copy) != saved or _files(backup / 'media') != media
            or _sha(backup / 'prepared.json') != manifest['prepared.json']):
        raise DeliveryError('The backup no longer matches its manifest; nothing was changed.')
    replaced = backup / ('replaced-' + _stamp())
    (replaced / 'data').mkdir(parents=True)
    # the database file with its -journal or -wal file, if any
    live = sorted(p for p in paths['database'].parent.glob(paths['database'].name + '*') if p.is_file())
    for path in live:
        shutil.copy2(path, replaced / 'data' / path.name)
    if _files(replaced / 'data') != {path.name: _sha(path) for path in live}:
        raise DeliveryError('The current database could not be kept; nothing was restored.')
    integrity = _copy_database(copy, paths['database'])  # backup copy -> live database
    if paths['media'].exists():
        shutil.move(str(paths['media']), str(replaced / 'media'))
    shutil.copytree(backup / 'media', paths['media'])
    current = local.read_json(paths['prepared'])
    if (current.get('source'), current.get('source_sha256')) != (saved_prepared['source'], saved_prepared['source_sha256']):
        from scripts.bos3_prepared_update import update_prepared_source
        update_prepared_source(paths['prepared'], saved_prepared['source'], saved_prepared['source_sha256'])
    checks = {
        'database_restored': integrity == 'ok' and fingerprints(paths['database']) == saved,
        'media_restored': _files(paths['media']) == media,
        'prepared_restored': local.read_json(paths['prepared']) == saved_prepared,
        'private_state_unchanged': all(_sha(paths['state'] / name) == manifest[name]
                                       for name in ('owner-access.json', 'runtime-secrets.json')),
    }
    return _journal(backup, 'rollback', {'checks': checks, 'replaced_kept_in': replaced.as_posix(),
                                         'result': 'PASS' if all(checks.values()) else 'FAIL'})


STEPS = {'inspect': inspect, 'preflight': preflight, 'backup': backup, 'migrate': migrate, 'bind': bind,
         'verify': verify, 'rollback': rollback}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('step', choices=tuple(STEPS))
    parser.add_argument('--root', type=Path, default=local.DEFAULT_ROOT)
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args(argv)
    if Path(local.__file__).resolve().parents[1] != SOURCE:
        raise DeliveryError('bos3_local was imported from another source checkout.')
    if args.step in ('migrate', 'bind', 'verify', 'rollback') and not args.backup:
        parser.error('--backup <dir printed by the backup step> is required')
    paths = local.instance_paths(args.root)
    try:
        result = STEPS[args.step](paths, args.backup)
    except Exception as error:
        if args.backup and (Path(args.backup) / JOURNAL).exists():
            _journal(args.backup, args.step, {'result': 'REFUSED', 'error': str(error)})
        raise
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('result', 'PASS') == 'PASS' else 3


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, KeyError, sqlite3.Error, subprocess.TimeoutExpired) as error:
        print('OWNER_LOCAL_DELIVERY_REFUSED: ' + str(error), file=sys.stderr)
        sys.exit(2)
