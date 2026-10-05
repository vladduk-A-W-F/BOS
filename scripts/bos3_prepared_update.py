"""Atomic prepared.json source update after caller-owned backup, quiet and source-pin checks."""

import json
import os
from pathlib import Path
import secrets
import stat
import subprocess

from scripts.bos3_local import native_windows_powershell_environment


class PreparedUpdateError(RuntimeError):
    pass


PREFLIGHT = r'''
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [System.Security.Principal.WindowsPrincipal]::new($identity)
$acl = Get-Acl -LiteralPath $env:BOS3_PREPARED_PATH -ErrorAction Stop
[pscustomobject]@{
  sid = $identity.User.Value
  owner_sid = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
  elevated = $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
  sddl = $acl.Sddl
} | ConvertTo-Json -Compress
'''
COPY_ACL = r'''
$acl = Get-Acl -LiteralPath $env:BOS3_PREPARED_PATH -ErrorAction Stop
Set-Acl -LiteralPath $env:BOS3_PREPARED_TEMP -AclObject $acl -ErrorAction Stop
'''
TEMP_SDDL = '(Get-Acl -LiteralPath $env:BOS3_PREPARED_TEMP -ErrorAction Stop).Sddl'
FILE_SDDL = '(Get-Acl -LiteralPath $env:BOS3_PREPARED_PATH -ErrorAction Stop).Sddl'


def _ordinary_file(path):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_nlink != 1 or (
            getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
        raise PreparedUpdateError('Prepared path must be an ordinary unlinked file')


def _powershell(script, path, temporary=None, *, timeout=15):
    base_env = os.environ.copy()
    base_env['BOS3_PREPARED_PATH'] = str(path)
    if temporary is not None:
        base_env['BOS3_PREPARED_TEMP'] = str(temporary)
    powershell, native_env = native_windows_powershell_environment(base_env)
    result = subprocess.run([powershell, '-NoProfile', '-NonInteractive', '-Command', script],
                            env=native_env, capture_output=True, text=True, encoding='utf-8', timeout=timeout)
    if result.returncode:
        raise PreparedUpdateError('Native PowerShell ACL preflight failed')
    return result.stdout.strip()


def update_prepared_source(path, source, source_sha256):
    """Caller must verify backup, quiet runtime and accepted source pin before this call.

    The existing prepared owner must be the current ordinary (not elevated) user.
    Only source and source_sha256 may change; failures after replacement need caller review.
    """
    path = Path(path).absolute()
    _ordinary_file(path)
    if not isinstance(source, str) or not source or not isinstance(source_sha256, str) or (
            len(source_sha256) != 64 or any(char not in '0123456789abcdef' for char in source_sha256)):
        raise PreparedUpdateError('Source and SHA-256 are required')
    _powershell('$null', path, timeout=60)
    preflight = json.loads(_powershell(PREFLIGHT, path, timeout=60))
    if preflight.get('elevated') is not False or not preflight.get('sid') or (
            preflight['sid'] != preflight.get('owner_sid')) or not preflight.get('sddl'):
        raise PreparedUpdateError('Prepared owner must match a non-elevated current user')
    original = path.read_bytes()
    prepared = json.loads(original)
    if not isinstance(prepared, dict) or not all(key in prepared for key in ('source', 'source_sha256')):
        raise PreparedUpdateError('Prepared source fields are missing')
    updated = dict(prepared, source=source, source_sha256=source_sha256)
    payload = (json.dumps(updated, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        with temporary.open('xb'):
            pass
        _powershell(COPY_ACL, path, temporary)
        if _powershell(TEMP_SDDL, path, temporary) != preflight['sddl']:
            raise PreparedUpdateError('Temporary ACL differs from prepared ACL')
        if path.read_bytes() != original or _powershell(FILE_SDDL, path) != preflight['sddl']:
            raise PreparedUpdateError('Prepared file changed during preflight')
        with temporary.open('wb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if path.read_bytes() != payload or _powershell(FILE_SDDL, path) != preflight['sddl']:
            raise PreparedUpdateError('Prepared replacement verification failed')
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)
    return True
