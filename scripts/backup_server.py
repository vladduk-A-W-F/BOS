"""Native SQLite + complete media backup under a live owned maintenance lease.

New private destinations only. Source schema is inspected by its own version's
Python/code. No restore, activation, public export or database repair is implied.
"""
from pathlib import Path
import hashlib
import json
import os
import stat
import subprocess
import time

FORMAT = 'BoS-private-backup-1'


class BackupRefused(ValueError):
    pass


def refuse(code):
    raise BackupRefused('Резервну копію не прийнято: ' + code)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8') + b'\n'


def checksum(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def inventory(installer, root):
    root = installer.safe_path(root, must_exist=True)
    result = {'directories': ['.'], 'files': {}}
    for path in sorted(root.rglob('*')):
        installer.safe_path(path, must_exist=True)
        rel = path.relative_to(root).as_posix()
        st = path.lstat()
        if stat.S_ISDIR(st.st_mode):
            result['directories'].append(rel)
        elif stat.S_ISREG(st.st_mode) and st.st_nlink == 1:
            result['files'][rel] = {'bytes': st.st_size, 'sha256': checksum(path)}
        else:
            refuse('NONREGULAR_OR_SHARED_SOURCE')
    return result


def copy_file(installer, source, destination):
    installer.safe_path(source, must_exist=True)
    before = source.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        refuse('SOURCE_NOT_OWNED_REGULAR_FILE')
    read_fd = os.open(source, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    write_fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(read_fd, 'rb') as reader, os.fdopen(write_fd, 'wb') as writer:
        observed = os.fstat(reader.fileno())
        if (observed.st_dev, observed.st_ino) != (before.st_dev, before.st_ino):
            refuse('SOURCE_REPLACED')
        for chunk in iter(lambda: reader.read(1024 * 1024), b''):
            writer.write(chunk)
        writer.flush()
        os.fsync(writer.fileno())
        after = os.fstat(reader.fileno())
    attrs = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if attrs(before) != attrs(after) or attrs(after) != attrs(source.lstat()):
        refuse('SOURCE_CHANGED_DURING_COPY')


def copy_tree(installer, source, destination, guard):
    before = inventory(installer, source)
    destination.mkdir(mode=0o700)
    for rel in before['directories']:
        if rel != '.':
            (destination / rel).mkdir(mode=0o700)
    for rel in before['files']:
        guard()
        copy_file(installer, source / rel, destination / rel)
    guard()
    if inventory(installer, source) != before or inventory(installer, destination) != before:
        refuse('TREE_CHANGED_DURING_COPY')
    return before


# This subprocess uses the active generation's code and exact Python. It never
# imports the coordinator's Django models when the source is an older version.
WORKER = r'''
import django,json,sys
from pathlib import Path
django.setup()
from scripts.reconcile_data import make_snapshot, source_files
from scripts.data_transfer import validate_snapshot
from scripts.schema_preflight import inspect_schema
source,media,snapshot=map(Path,sys.argv[1:4])
fact=make_snapshot(source,snapshot)
snapshot.chmod(0o600)
after=validate_snapshot(snapshot,media,inspect_schema=inspect_schema)
if not fact['source_files_unchanged'] or source_files(source)!=fact['source_files_before']:
    raise ValueError('SOURCE_BYTES_CHANGED')
print(json.dumps({'snapshot':fact,'logical':after},sort_keys=True,ensure_ascii=False))
'''


def capture_backup(*, ledger, lease, destination):
    from scripts.generation_ledger import GenerationLedger
    from scripts.maintenance_control import QuiescenceLease
    if type(ledger) is not GenerationLedger or type(lease) is not QuiescenceLease:
        refuse('ISSUED_LEDGER_AND_LIVE_LEASE_REQUIRED')
    with lease.fenced_for(ledger.installation_id, ledger.target, lease.operation_id):
        return _capture_fenced(ledger=ledger, lease=lease, destination=destination)


def _capture_fenced(*, ledger, lease, destination):
    installer = ledger.installer
    active = ledger.current_owned()

    def guard():
        # The live owner fence remains held across the whole capture. File
        # copies independently validate paths/inodes before and after reads.
        # Re-scan full immutable code/runtime at phase boundaries, not per file.
        lease.assert_for(active.installation_id, active.target, lease.operation_id)

    active.assert_owned()
    guard()
    destination = installer.safe_path(destination)
    if destination.exists():
        refuse('DESTINATION_MUST_BE_NEW')
    for protected in (active.target, ledger.registry, active.code_root):
        if destination == protected or destination in protected.parents or protected in destination.parents:
            refuse('BACKUP_PATH_OVERLAPS_INSTALLATION')
    installer.safe_path(destination.parent, must_exist=True)
    started = time.monotonic()
    destination.mkdir(mode=0o700)
    # A partial directory never carries COMPLETE and is never silently reused.
    installer.new_file(destination / 'STARTED.json', canonical({
        'format': FORMAT, 'installation_id': active.installation_id,
        'operation_id': lease.operation_id, 'generation_hash': active.generation_hash,
        'backup_identity': installer.identity(destination)}))
    guard()
    code = copy_tree(installer, active.code_root, destination / 'code', guard)
    config_dir = destination / 'config'
    config_dir.mkdir(mode=0o700)
    copy_file(installer, active.config_path, config_dir / 'server.json')
    media = copy_tree(installer, active.media_root, destination / 'private', guard)
    static = copy_tree(installer, active.static_root, destination / 'static', guard)
    config = json.loads(active.config_path.read_bytes())
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('BOS_', 'PIP_', 'OPENAI', 'ANTHROPIC'))
           and key not in ('PYTHONPATH', 'PYTHONHOME', 'DJANGO_SETTINGS_MODULE')}
    env.update(config)
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
    guard()
    result = subprocess.run([str(active.python_path), '-B', '-c', WORKER,
        str(active.database_path), str(active.media_root), str(destination / 'database.sqlite3')],
        cwd=active.code_root, env=env, text=True, capture_output=True, timeout=120)
    if result.returncode:
        # Never put private row data, raw SQL errors or a secret in public logs.
        refuse('VERSIONED_SNAPSHOT_WORKER_FAILED')
    try:
        proof = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        refuse('INVALID_SNAPSHOT_PROOF')
    guard()
    if inventory(installer, active.media_root) != media or inventory(installer, active.static_root) != static:
        refuse('FILES_CHANGED_DURING_SNAPSHOT')
    if inventory(installer, active.code_root) != code or active.config_path.read_bytes() != (config_dir/'server.json').read_bytes():
        refuse('CODE_OR_CONFIG_CHANGED')
    active.assert_owned()
    payload = inventory(installer, destination)
    manifest = {'format': FORMAT, 'installation_id': active.installation_id,
        'operation_id': lease.operation_id, 'generation_hash': active.generation_hash,
        'version': active.version, 'code_source': installer.source_identity(destination/'code'),
        'payload': payload, 'proof': proof,
        'scope': 'native SQLite, exact code/config/static and all private files under live lease',
        'not_checked': ['clean_restore', 'post_restore_http', 'upgrade', 'rollback', 'PostgreSQL', 'Windows']}
    installer.new_file(destination/'MANIFEST.json', canonical(manifest))
    guard()
    if inventory(installer, active.media_root) != media:
        refuse('MEDIA_CHANGED_BEFORE_COMPLETE')
    result = {'complete': True, 'scope': 'capture_only', 'installation_id': active.installation_id,
        'operation_id': lease.operation_id, 'version': active.version,
        'manifest_sha256': checksum(destination/'MANIFEST.json'),
        'database_sha256': checksum(destination/'database.sqlite3'),
        'private_files': len(media['files']), 'elapsed_seconds': round(time.monotonic()-started, 3),
        'lease_retained': True, 'restore_verified': False}
    _seal_complete(installer, destination, {'format': FORMAT,
        'manifest_sha256': result['manifest_sha256']})
    return result


def _seal_complete(installer, destination, value):
    """Publish only our fsynced marker; remove only its own inode on failure."""
    parent_identity = installer.identity(destination)
    pending, final = destination/'PENDING_COMPLETE', destination/'COMPLETE'
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    owned = [os.fstat(fd).st_dev, os.fstat(fd).st_ino]
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        if installer.identity(destination) != parent_identity or final.exists():
            refuse('BACKUP_SEAL_DESTINATION_CHANGED')
        os.rename(pending, final)
        directory_fd = os.open(destination, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        if installer.identity(destination) == parent_identity:
            for path in (pending, final):
                if path.exists() and not path.is_symlink() and installer.identity(path) == owned:
                    path.unlink()
        raise



def inspect_backup(*, installer, source):
    """Read-only completeness/hash check. Does not authorize a restore target."""
    source = installer.safe_path(source, must_exist=True)
    installer.private_directory(source)
    for name in ('MANIFEST.json', 'COMPLETE', 'STARTED.json'):
        installer.private_regular(source/name)
    try:
        manifest = json.loads((source/'MANIFEST.json').read_bytes())
        complete = json.loads((source/'COMPLETE').read_bytes())
    except (ValueError, UnicodeError):
        refuse('INVALID_BACKUP_METADATA')
    if (manifest.get('format') != FORMAT or complete != {'format': FORMAT,
            'manifest_sha256': checksum(source/'MANIFEST.json')}
            or (source/'MANIFEST.json').read_bytes() != canonical(manifest)
            or (source/'COMPLETE').read_bytes() != canonical(complete)):
        refuse('INCOMPLETE_OR_CHANGED_BACKUP')
    actual = inventory(installer, source)
    for name in ('MANIFEST.json', 'COMPLETE'):
        actual['files'].pop(name)
    if actual != manifest.get('payload'):
        refuse('CHANGED_BACKUP_PAYLOAD')
    if installer.source_identity(source/'code') != manifest.get('code_source'):
        refuse('BACKUP_CODE_CHANGED')
    return manifest
