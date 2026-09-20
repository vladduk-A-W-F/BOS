"""Portable pre-application handshake; Windows identity is self-reported and handle-verified."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import time

IS_WINDOWS = os.name == 'nt'


def image_name(value):
    return os.path.normcase(str(Path(value).resolve()))


def expected_child_image():
    return image_name(getattr(sys, '_base_executable', sys.executable) if IS_WINDOWS else sys.executable)


def kernel_api():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    signatures = {
        'GetCurrentProcess': ([], wintypes.HANDLE),
        'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        'GetProcessTimes': ([wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4, wintypes.BOOL),
        'QueryFullProcessImageNameW': ([wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                       ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        'WaitForSingleObject': ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        'TerminateProcess': ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (args, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
    return kernel


def process_identity(kernel, handle, pid):
    times = [wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
        raise ctypes.WinError(ctypes.get_last_error())
    size = wintypes.DWORD(32768)
    name = ctypes.create_unicode_buffer(size.value)
    if not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {'pid': pid, 'created_ticks': (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
            'image': image_name(name.value)}


def current_identity():
    if IS_WINDOWS:
        kernel = kernel_api()
        return process_identity(kernel, kernel.GetCurrentProcess(), os.getpid())
    return {'pid': os.getpid(), 'created_ticks': None, 'image': image_name(sys.executable)}


def validate_identity(value, nonce, *, expected_image=None, expected_pid=None, windows=None):
    windows = IS_WINDOWS if windows is None else windows
    expected_image = expected_image or expected_child_image()
    if (not isinstance(value, dict) or value.get('nonce') != nonce
            or type(value.get('pid')) is not int or value['pid'] <= 0
            or not isinstance(value.get('image'), str)
            or image_name(value['image']) != image_name(expected_image)
            or (windows and (type(value.get('created_ticks')) is not int or value['created_ticks'] <= 0))
            or (not windows and value.get('created_ticks') is not None)
            or (expected_pid is not None and value['pid'] != expected_pid)):
        raise RuntimeError('Child handshake nonce/PID/creation time/executable differs.')
    return {key: value[key] for key in ('pid', 'created_ticks', 'image')}


def open_verified_windows(identity):
    """Return only a verified held handle. Mismatch never reaches caller cleanup."""
    kernel = kernel_api()
    handle = kernel.OpenProcess(0x1000 | 0x100000 | 1, False, identity['pid'])
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if process_identity(kernel, handle, identity['pid']) != identity:
            raise RuntimeError('Child PID was reused or self-reported identity differs.')
        return kernel, handle
    except BaseException:
        kernel.CloseHandle(handle)
        raise


def exited(kernel, handle, timeout=0):
    result = kernel.WaitForSingleObject(handle, timeout)
    if result not in (0, 258):
        raise ctypes.WinError(ctypes.get_last_error())
    return result == 0


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.tmp')  # one child/parent writer per distinct owned file
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def child_handshake(timeout=15):
    """Report identity first, then await parent release; never import Django before release."""
    identity_path = Path(os.environ['BOS_UI_SERVER_IDENTITY'])
    nonce = os.environ['BOS_UI_SERVER_NONCE']
    parent = json.loads(os.environ['BOS_UI_SERVER_PARENT'])
    proof = {**current_identity(), 'nonce': nonce}
    atomic_json(identity_path, proof)
    parent_kernel = parent_handle = None
    try:
        if IS_WINDOWS:
            # Parent came from the controller's own held/pseudo handle, not a later PID sample.
            parent_kernel, parent_handle = open_verified_windows(parent)
        elif os.getppid() != parent['pid']:
            raise RuntimeError('Direct POSIX controller exited before child handshake.')
        release = identity_path.with_name(identity_path.stem + '-release.json')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if ((IS_WINDOWS and exited(parent_kernel, parent_handle))
                    or (not IS_WINDOWS and os.getppid() != parent['pid'])):
                raise RuntimeError('Controller exited before releasing the owned child.')
            if release.exists():
                if json.loads(release.read_text(encoding='utf-8')) != proof:
                    raise RuntimeError('Ownership release differs from actual child identity.')
                return proof
            time.sleep(.05)
        raise RuntimeError('Ownership release timed out; application was not imported.')
    finally:
        if parent_handle is not None:
            parent_kernel.CloseHandle(parent_handle)
