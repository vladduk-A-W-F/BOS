"""Restore a verified private backup into an installation created by THIS call.

Never opens an existing target for replacement. Runtime is marked unprovisioned
before restoring data, and becomes launchable only after exact native/typed
verification. A new installation receives a new UUID/secret/cookie namespace.
"""
from pathlib import Path
import json
import os
import subprocess
import time


RESTORE_WORKER = r'''
import hashlib,json,os,sqlite3,sys
from pathlib import Path
import django
django.setup()
from django.apps import apps
from django.conf import settings
from scripts.data_transfer import validate_snapshot
from scripts.schema_preflight import inspect_schema
from scripts.reconcile_data import connect_readonly
source,target,media=map(Path,sys.argv[1:4])
if Path(settings.DATABASES['default']['NAME'])!=target:
    raise ValueError('RESTORE_TARGET_CONFIG_MISMATCH')
labels={'operations','erp','finance','employees','branches','tasks','ai_assistant'}
if any(m.objects.exists() for m in apps.get_models() if m._meta.app_label in labels):
    raise ValueError('RESTORE_TARGET_NOT_EMPTY')
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
if get_user_model().objects.exists() or Group.objects.exists() or Session.objects.exists():
    raise ValueError('RESTORE_TARGET_ALREADY_HAS_IDENTITIES')
from django.db import connections
connections.close_all()
if any(Path(str(target)+s).exists() for s in ('-wal','-shm','-journal')):
    raise ValueError('RESTORE_TARGET_HAS_ACTIVE_SIDECARS')
original=target.stat(); source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
# Only this freshly provisioned, empty, exclusively locked target is writable.
# A byte copy preserves the sealed SQLite header as well as rows and sequences.
reader_fd=os.open(source,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
writer_fd=os.open(target,os.O_WRONLY|getattr(os,'O_NOFOLLOW',0))
with os.fdopen(reader_fd,'rb') as reader, os.fdopen(writer_fd,'r+b') as writer:
    current=os.fstat(writer.fileno())
    if (current.st_dev,current.st_ino)!=(original.st_dev,original.st_ino) or current.st_nlink!=1:
        raise ValueError('RESTORE_TARGET_INODE_CHANGED')
    writer.truncate(0)
    for chunk in iter(lambda:reader.read(1024*1024),b''):
        writer.write(chunk)
    writer.flush();os.fsync(writer.fileno())
if (target.stat().st_dev,target.stat().st_ino)!=(original.st_dev,original.st_ino):
    raise ValueError('RESTORE_TARGET_INODE_CHANGED')
proof=validate_snapshot(target,media,inspect_schema=inspect_schema)
if hashlib.sha256(source.read_bytes()).hexdigest()!=source_hash:
    raise ValueError('BACKUP_SOURCE_CHANGED')
print(json.dumps({'logical':proof,'database_sha256':hashlib.sha256(target.read_bytes()).hexdigest()},sort_keys=True))
'''


def restore_new(*, installer, source, target, registry, origin, wheelhouse):
    from scripts.backup_server import inspect_backup, inventory, copy_file, checksum, canonical, refuse
    from scripts.provision_runtime import provision_install
    from scripts.lifecycle_server import load_owned, instance_lock, child_environment
    source = installer.safe_path(source, must_exist=True)
    target = installer.safe_path(target)
    registry = installer.safe_path(registry)
    if target.exists():
        refuse('RESTORE_REQUIRES_ABSENT_TARGET')
    for left, right in ((source,target),(source,registry),(target,registry)):
        if left == right or left in right.parents or right in left.parents:
            refuse('RESTORE_PATH_OVERLAP')
    manifest = inspect_backup(installer=installer, source=source)
    original_inventory = inventory(installer, source)
    started = time.monotonic()
    # No resume parameter exists: only a target created in this very call.
    installed = provision_install(installer=installer,target=target,registry=registry,
        source_root=source/'code',origin=origin,wheelhouse=wheelhouse)
    installation_id = installed['installation_id']
    record,release,python,config = load_owned(installer,target=target,registry=registry,
        installation_id=installation_id)
    owner = installer.InstallerRegistry(registry)
    with instance_lock(installer,target):
        # Fail closed across crashes. Immutable identity/source/config stay as
        # issued; this runtime readiness field was explicitly mutable in A09.
        with owner.lock():
            record = owner.get(installation_id)
            record['runtime']['application_provisioned'] = False
            record['runtime']['restore'] = {'complete':False,'source_manifest_sha256':checksum(source/'MANIFEST.json'),
                'source_installation_id':manifest['installation_id']}
            owner.update(record)
        database = target/'state/data/bos.sqlite3'
        database_identity = installer.identity(database)
        media = target/'state/private'
        if inventory(installer,media) != {'directories':['.'],'files':{}}:
            refuse('RESTORE_PRIVATE_TARGET_NOT_EMPTY')
        source_media = inventory(installer,source/'private')
        for relative in source_media['directories']:
            if relative != '.':
                (media/relative).mkdir(mode=0o700)
        for relative in source_media['files']:
            copy_file(installer,source/'private'/relative,media/relative)
        if inventory(installer,media) != source_media:
            refuse('RESTORED_PRIVATE_BYTES_DIFFER')
        result = subprocess.run([str(python),'-B','-c',RESTORE_WORKER,
                str(source/'database.sqlite3'),str(database),str(media)],
            cwd=release,env=child_environment(config),text=True,capture_output=True,timeout=120)
        if result.returncode:
            refuse('NEW_TARGET_RESTORE_WORKER_FAILED')
        try:
            proof=json.loads(result.stdout)
        except (ValueError,UnicodeError):
            refuse('INVALID_RESTORE_PROOF')
        expected=manifest['proof']['logical']
        for key in ('sqlite_schema_hash','logical_schema_hash','migration_state','tables','sequences','media','media_references'):
            if proof['logical'][key] != expected[key]:
                refuse('RESTORE_TYPED_MANIFEST_DIFFERS')
        # Native sealed file must remain byte-for-byte exact on clean restore.
        exact_database = checksum(database)==checksum(source/'database.sqlite3')
        if not exact_database:
            refuse('RESTORE_NATIVE_DATABASE_BYTES_DIFFER')
        if installer.identity(database)!=database_identity:
            refuse('RESTORE_TARGET_REPLACED')
        if inventory(installer,source)!=original_inventory:
            refuse('BACKUP_CHANGED_DURING_RESTORE')
        if installer.source_identity(release)!=manifest['code_source']:
            refuse('RESTORE_CODE_VERSION_DIFFERS')
        # Exact static payload, too: a different collection result is explicit.
        if inventory(installer,target/'state/static')!=inventory(installer,source/'static'):
            refuse('RESTORE_STATIC_BYTES_DIFFER')
        with owner.lock():
            record=owner.get(installation_id)
            if record['runtime'].get('application_provisioned') or record['runtime']['restore']['complete']:
                refuse('RESTORE_RUNTIME_CHANGED')
            record['runtime']['restore'].update(complete=True,typed_manifest_verified=True,
                native_database_sha256=proof['database_sha256'],
                identity_policy='new UUID/secret/cookie namespace; exact stored users, roles and session rows')
            record['runtime']['application_provisioned']=True
            owner.update(record)
        try:
            load_owned(installer,target=target,registry=registry,installation_id=installation_id)
        except BaseException:
            # The lifetime instance lock is still held; no managed server can
            # start between publication and this final admission. Revoke before
            # releasing that lock on any late failure.
            with owner.lock():
                record=owner.get(installation_id)
                record['runtime']['application_provisioned']=False
                record['runtime']['restore']['complete']=False
                record['runtime']['restore']['late_admission_failed']=True
                owner.update(record)
            raise
    return {'complete':True,'scope':'clean_restore_data_and_code_only','installation_id':installation_id,
        'source_installation_id':manifest['installation_id'],'version':manifest['version'],
        'database_sha256':proof['database_sha256'],'private_files':len(source_media['files']),
        'tables':len(expected['tables']),'elapsed_seconds':round(time.monotonic()-started,3),
        'backup_unchanged':True,'post_restore_http_verified':False,
        'identity_policy':'new installation UUID, secret and cookie namespace; stored identities/history unchanged'}
