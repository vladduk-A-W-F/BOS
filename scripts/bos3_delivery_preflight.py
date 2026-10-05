"""Read-only Windows checks before a separately reviewed owner-local delivery."""

import argparse
import ctypes
import json
from pathlib import Path
import subprocess
import sys

from scripts import bos3_local as local
from scripts import bos3_prepared_update as prepared_update


class PreflightError(RuntimeError):
    pass


def _argv(command):
    """Parse the actual Windows command line into complete arguments."""
    shell = ctypes.windll.shell32
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    ctypes.windll.kernel32.LocalFree.restype = ctypes.c_void_p
    count = ctypes.c_int()
    pointer = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not pointer:
        raise PreflightError('CIM command line cannot be parsed.')
    try:
        return [pointer[index] for index in range(count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(pointer, ctypes.c_void_p))


def check(root, source, source_sha256):
    paths = local.instance_paths(root)
    source = Path(source).resolve()
    if not source.is_absolute() or not isinstance(source_sha256, str) or len(source_sha256) != 64 or any(
            char not in '0123456789abcdef' for char in source_sha256):
        raise PreflightError('An exact accepted source and SHA-256 are required.')
    local.validate_root(source, paths)
    prepared_update._ordinary_file(paths['prepared'])
    prepared_update._ordinary_file(paths['process'])
    original = {key: paths[key].read_bytes() for key in ('prepared', 'process')}
    prepared = json.loads(original['prepared'])
    receipt = json.loads(original['process'])
    if (not isinstance(prepared, dict) or not isinstance(receipt, dict)
            or prepared.get('source') != str(source) or receipt.get('source') != str(source)
            or prepared.get('source_sha256') != source_sha256
            or receipt.get('source_sha256') != source_sha256
            or local.digest_source(source) != source_sha256):
        raise PreflightError('Prepared, receipt and accepted source pins differ.')
    launch_id = receipt.get('launch_id')
    if (receipt.get('schema') != 1 or receipt.get('status') != 'ready'
            or receipt.get('runtime') != 'waitress' or receipt.get('port') != local.PORT
            or not isinstance(launch_id, str) or not launch_id):
        raise PreflightError('Ready waitress receipt is missing or malformed.')
    tokens = [str(source / 'scripts' / 'bos3_local.py'), 'internal-serve', '--root',
              str(paths['root']), '--source', str(source), '--runtime', 'waitress',
              '--launch-id', launch_id]
    if receipt.get('required_tokens') != tokens:
        raise PreflightError('Receipt launch arguments differ from the accepted source.')
    record = receipt.get('process')
    if (not isinstance(record, dict) or set(record) != {'pid', 'created_ticks', 'image'}
            or type(record['pid']) is not int or record['pid'] <= 0
            or type(record['created_ticks']) is not int or record['created_ticks'] <= 0
            or not isinstance(record['image'], str) or not record['image']
            or receipt.get('runtime_image') != record['image']
            or record['image'] != local.expected_runtime_image()):
        raise PreflightError('Process identity receipt is malformed or mismatched.')

    # Warm up native Windows PowerShell once before the bounded ACL and CIM reads.
    prepared_update._powershell('$null', paths['prepared'], timeout=60)
    acl = json.loads(prepared_update._powershell(
        prepared_update.PREFLIGHT, paths['prepared'], timeout=60))
    if (not isinstance(acl, dict) or acl.get('elevated') is not False
            or not isinstance(acl.get('sid'), str) or not acl['sid'].startswith('S-1-')
            or acl.get('owner_sid') != acl['sid']
            or not isinstance(acl.get('sddl'), str) or not acl['sddl']):
        raise PreflightError('Prepared owner must match the ordinary current user.')
    ops = local.WindowsProcess()
    handle = ops.open(record['pid'])
    if handle is None:
        raise PreflightError('Owned waitress process is no longer running.')
    try:
        if ops.identity(handle, record['pid']) != record or ops.exited(handle):
            raise PreflightError('Owned waitress process identity changed or exited.')
        command = local.process_command_line(record['pid'], timeout=60)
        if not command or _argv(command)[1:] != ['-X', 'utf8', '-B', *tokens]:
            raise PreflightError('Live waitress command arguments differ.')
        if ops.identity(handle, record['pid']) != record or ops.exited(handle):
            raise PreflightError('Owned waitress process changed during preflight.')
        for key, value in original.items():
            prepared_update._ordinary_file(paths[key])
            if paths[key].read_bytes() != value:
                raise PreflightError('Prepared or process receipt changed during preflight.')
    finally:
        ops.close(handle)
    return {'preflight': 'PASS', 'source_sha256': source_sha256,
            'owned_waitress_pid': record['pid']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.root, args.source, args.source_sha256)))


if __name__ == '__main__':
    try:
        main()
    except (PreflightError, local.LocalError, prepared_update.PreparedUpdateError,
            OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as error:
        print('BOS3_DELIVERY_PREFLIGHT_REFUSED: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
