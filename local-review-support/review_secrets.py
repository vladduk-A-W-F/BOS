"""Current Windows user's DPAPI encryption; no plaintext secret file."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent
DEFAULT_RUNTIME_ROOT = Path('D:/3/Codex/2026-09-20/bos-execution/work/continuation-review-demo-20260920')


def runtime_root(value=None):
    path = Path(value or os.environ.get('BOS_REVIEW_ROOT') or DEFAULT_RUNTIME_ROOT)
    if not path.is_absolute():
        raise ValueError('Review runtime root must be an explicit absolute path.')
    path = path.resolve()
    if path.is_relative_to(CODE_ROOT.parent) or CODE_ROOT.parent.is_relative_to(path):
        raise ValueError('Review runtime must be outside the support checkout and its ancestors.')
    return path


ROOT = runtime_root()


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def transform(value, *, decrypt=False):
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    library = ctypes.WinDLL('crypt32', use_last_error=True)
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        free = ctypes.WinDLL('kernel32', use_last_error=True).LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(target.data)


def read_secrets(root=None):
    return json.loads(transform(((root or ROOT) / 'private/user-secrets.dpapi').read_bytes(), decrypt=True))


def write_secrets(value, root=None):
    path = (root or ROOT) / 'private/user-secrets.dpapi'
    path.parent.mkdir(exist_ok=True)
    with path.open('xb') as stream:
        stream.write(transform(json.dumps(value).encode('utf-8')))
