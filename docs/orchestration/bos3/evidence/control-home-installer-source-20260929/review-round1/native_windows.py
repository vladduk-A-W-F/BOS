"""Windows primitives for the one-shot control-home migration."""

from __future__ import annotations

import ctypes
import hashlib
import os
import stat
from ctypes import wintypes
from pathlib import Path


class NativeError(RuntimeError):
    pass


KERNEL = ctypes.WinDLL("kernel32", use_last_error=True)
ADVAPI = ctypes.WinDLL("advapi32", use_last_error=True)
INVALID_HANDLE = ctypes.c_void_p(-1).value
READ_CONTROL = 0x00020000
WRITE_DAC = 0x00040000
WRITE_OWNER = 0x00080000
FILE_READ_ATTRIBUTES = 0x80
FILE_SHARE_ALL = 7
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
SE_FILE_OBJECT = 1
OWNER_SECURITY_INFORMATION = 1
GROUP_SECURITY_INFORMATION = 2
DACL_SECURITY_INFORMATION = 4
PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
UNPROTECTED_DACL_SECURITY_INFORMATION = 0x20000000
SE_DACL_PROTECTED = 0x1000
FSCTL_SET_REPARSE_POINT = 0x000900A4
FSCTL_GET_REPARSE_POINT = 0x000900A8
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
FILE_ATTRIBUTE_COMPRESSED = 0x800
FILE_ATTRIBUTE_ENCRYPTED = 0x4000
FILE_ATTRIBUTE_SPARSE_FILE = 0x200


class FileTime(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]


class FileInformation(ctypes.Structure):
    _fields_ = [
        ("attributes", wintypes.DWORD), ("created", FileTime),
        ("accessed", FileTime), ("written", FileTime),
        ("volume", wintypes.DWORD), ("size_high", wintypes.DWORD),
        ("size_low", wintypes.DWORD), ("links", wintypes.DWORD),
        ("file_index_high", wintypes.DWORD), ("file_index_low", wintypes.DWORD),
    ]


class StreamData(ctypes.Structure):
    _fields_ = [("size", ctypes.c_int64), ("name", wintypes.WCHAR * 296)]


KERNEL.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                               wintypes.HANDLE]
KERNEL.CreateFileW.restype = wintypes.HANDLE
KERNEL.CloseHandle.argtypes = [wintypes.HANDLE]
KERNEL.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInformation)]
KERNEL.MoveFileExW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
KERNEL.LocalFree.argtypes = [ctypes.c_void_p]
KERNEL.CreateDirectoryW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p]
KERNEL.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p,
                                   wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                   ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
KERNEL.FindFirstStreamW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                    ctypes.POINTER(StreamData), wintypes.DWORD]
KERNEL.FindFirstStreamW.restype = wintypes.HANDLE
KERNEL.FindNextStreamW.argtypes = [wintypes.HANDLE, ctypes.POINTER(StreamData)]
KERNEL.FindClose.argtypes = [wintypes.HANDLE]
KERNEL.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD,
                                          ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                          wintypes.LPWSTR, wintypes.DWORD]
KERNEL.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
KERNEL.GetFileAttributesW.restype = wintypes.DWORD
KERNEL.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
ADVAPI.GetSecurityInfo.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
                                   ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
                                   ctypes.POINTER(ctypes.c_void_p)]
ADVAPI.SetSecurityInfo.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
ADVAPI.GetSecurityDescriptorControl.argtypes = [ctypes.c_void_p,
                                                ctypes.POINTER(wintypes.WORD),
                                                ctypes.POINTER(wintypes.DWORD)]
ADVAPI.GetLengthSid.argtypes = [ctypes.c_void_p]
ADVAPI.GetLengthSid.restype = wintypes.DWORD
ADVAPI.GetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
                                            ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL)]


def _winerror(label: str) -> NativeError:
    return NativeError(f"{label}: Windows error {ctypes.get_last_error()}")


def _open(path: Path, access: int, *, follow: bool = False) -> int:
    handle = KERNEL.CreateFileW(str(path), access, FILE_SHARE_ALL, None, OPEN_EXISTING,
                                FILE_FLAG_BACKUP_SEMANTICS | (0 if follow else FILE_FLAG_OPEN_REPARSE_POINT), None)
    if handle == INVALID_HANDLE:
        raise _winerror("CreateFileW")
    return handle


def _close(handle: int) -> None:
    if not KERNEL.CloseHandle(handle):
        raise _winerror("CloseHandle")


def _identity(handle: int, *, single_link: bool = True) -> dict:
    info = FileInformation()
    if not KERNEL.GetFileInformationByHandle(handle, ctypes.byref(info)):
        raise _winerror("GetFileInformationByHandle")
    if single_link and info.links != 1:
        raise NativeError("hardlink or unexpected link count refused")
    return {"volume_id": f"{info.volume:08x}",
            "file_id": f"{((info.file_index_high << 32) | info.file_index_low):016x}"}


def inspect(path: Path, *, directory: bool | None = None) -> dict:
    """Refuse links/reparse and return core-compatible native identity."""
    item = os.lstat(path)
    is_dir = stat.S_ISDIR(item.st_mode)
    if item.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise NativeError("reparse point refused")
    if item.st_file_attributes & (FILE_ATTRIBUTE_COMPRESSED | FILE_ATTRIBUTE_ENCRYPTED | FILE_ATTRIBUTE_SPARSE_FILE):
        raise NativeError("compressed, encrypted or sparse object refused")
    if directory is True and not stat.S_ISDIR(item.st_mode):
        raise NativeError("directory required")
    if directory is False and not stat.S_ISREG(item.st_mode):
        raise NativeError("regular file required")
    handle = _open(path, FILE_READ_ATTRIBUTES)
    try:
        info = FileInformation()
        if not KERNEL.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise _winerror("GetFileInformationByHandle")
        if info.attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise NativeError("reparse point refused")
        return _identity(handle, single_link=not is_dir)
    finally:
        _close(handle)


def require_local_ntfs(path: Path) -> None:
    drive = path.drive
    if not drive or not drive.endswith(":"):
        raise NativeError("local drive path required")
    filesystem = ctypes.create_unicode_buffer(64)
    if not KERNEL.GetVolumeInformationW(drive + "\\", None, 0, None, None, None,
                                         filesystem, len(filesystem)):
        raise _winerror("GetVolumeInformationW")
    if filesystem.value != "NTFS":
        raise NativeError("only local NTFS is supported by 64-bit core identity")


def require_ordinary_ancestors(path: Path) -> None:
    if (not path.is_absolute() or ".." in path.parts or not path.drive.endswith(":")
            or any(":" in part for part in path.parts[1:])):
        raise NativeError("ordinary absolute drive path required")
    for ancestor in path.parents:
        if ancestor == Path(path.drive + "\\"):
            break
        if os.lstat(ancestor).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise NativeError("ancestor reparse point refused")


def require_single_stream(path: Path, *, directory: bool = False) -> None:
    data = StreamData()
    handle = KERNEL.FindFirstStreamW(str(path), 0, ctypes.byref(data), 0)
    if handle == INVALID_HANDLE:
        if directory and ctypes.get_last_error() == 38:
            return
        raise _winerror("FindFirstStreamW")
    try:
        allowed_base = {"::$INDEX_ALLOCATION", "::$DATA"} if directory else {"::$DATA"}
        if data.name not in allowed_base:
            raise NativeError("alternate or unexpected data stream refused")
        if KERNEL.FindNextStreamW(handle, ctypes.byref(data)):
            raise NativeError("alternate data stream refused")
        if ctypes.get_last_error() != 38:
            raise _winerror("FindNextStreamW")
    finally:
        if not KERNEL.FindClose(handle):
            raise _winerror("FindClose")


def copy_attributes(source: Path, target: Path) -> None:
    before = KERNEL.GetFileAttributesW(str(source))
    if before == 0xFFFFFFFF:
        raise _winerror("GetFileAttributesW")
    unsupported = before & ~(0x10 | 0x20 | 0x1 | 0x2 | 0x4 | 0x80)
    if unsupported:
        raise NativeError(f"unsupported file attributes: {unsupported:x}")
    requested = before & ~0x10
    if not KERNEL.SetFileAttributesW(str(target), requested or 0x80):
        raise _winerror("SetFileAttributesW")
    if KERNEL.GetFileAttributesW(str(target)) != before:
        raise NativeError("file attributes readback mismatch")


def identity_follow(path: Path) -> dict:
    handle = _open(path, FILE_READ_ATTRIBUTES, follow=True)
    try:
        return _identity(handle, single_link=not path.is_dir())
    finally:
        _close(handle)


def _security(handle: int) -> tuple[int, int, int, int, bool]:
    owner = ctypes.c_void_p()
    group = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    rc = ADVAPI.GetSecurityInfo(handle, SE_FILE_OBJECT,
                                OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
                                ctypes.byref(owner), ctypes.byref(group), ctypes.byref(dacl), None,
                                ctypes.byref(descriptor))
    if rc:
        raise NativeError(f"GetSecurityInfo: Windows error {rc}")
    if not owner.value or not group.value or not dacl.value:
        KERNEL.LocalFree(descriptor)
        raise NativeError("null owner, group or DACL refused")
    present = wintypes.BOOL()
    actual_dacl = ctypes.c_void_p()
    defaulted = wintypes.BOOL()
    if not ADVAPI.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present),
                                             ctypes.byref(actual_dacl), ctypes.byref(defaulted)):
        KERNEL.LocalFree(descriptor)
        raise _winerror("GetSecurityDescriptorDacl")
    if not present.value or actual_dacl.value != dacl.value:
        KERNEL.LocalFree(descriptor)
        raise NativeError("DACL absent or inconsistent")
    control = wintypes.WORD()
    revision = wintypes.DWORD()
    if not ADVAPI.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)):
        KERNEL.LocalFree(descriptor)
        raise _winerror("GetSecurityDescriptorControl")
    return descriptor.value, owner.value, group.value, dacl.value, control.value & 0x150c


def _security_fingerprint(parts: tuple[int, int, int, int, bool]) -> str:
    _, owner, group, dacl, control = parts
    acl_size = int.from_bytes(ctypes.string_at(dacl + 2, 2), "little")
    if acl_size < 8:
        raise NativeError("invalid DACL size")
    sha = hashlib.sha256()
    for sid in (owner, group):
        size = ADVAPI.GetLengthSid(sid)
        if size <= 0:
            raise NativeError("invalid SID")
        sha.update(size.to_bytes(4, "little"))
        sha.update(ctypes.string_at(sid, size))
    sha.update(acl_size.to_bytes(4, "little"))
    sha.update(ctypes.string_at(dacl, acl_size))
    sha.update(control.to_bytes(2, "little"))
    return sha.hexdigest()


def acl_fingerprint(path: Path) -> str:
    inspect(path)
    handle = _open(path, READ_CONTROL)
    try:
        parts = _security(handle)
        try:
            return _security_fingerprint(parts)
        finally:
            KERNEL.LocalFree(parts[0])
    finally:
        _close(handle)


def copy_acl(source: Path, target: Path) -> str:
    inspect(source)
    inspect(target)
    src = _open(source, READ_CONTROL)
    dst = _open(target, READ_CONTROL | WRITE_DAC | WRITE_OWNER)
    try:
        parts = _security(src)
        try:
            expected = _security_fingerprint(parts)
            _, owner, group, dacl, control = parts
            flags = OWNER_SECURITY_INFORMATION | GROUP_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION
            flags |= PROTECTED_DACL_SECURITY_INFORMATION if control & SE_DACL_PROTECTED else UNPROTECTED_DACL_SECURITY_INFORMATION
            rc = ADVAPI.SetSecurityInfo(dst, SE_FILE_OBJECT, flags, owner, group, dacl, None)
            if rc:
                raise NativeError(f"SetSecurityInfo: Windows error {rc}")
            actual_parts = _security(dst)
            try:
                if _security_fingerprint(actual_parts) != expected:
                    raise NativeError("owner/group/DACL readback mismatch")
            finally:
                KERNEL.LocalFree(actual_parts[0])
            return expected
        finally:
            KERNEL.LocalFree(parts[0])
    finally:
        _close(dst)
        _close(src)


def rename_same_volume(source: Path, target: Path) -> None:
    if source.parent != target.parent or present(target):
        raise NativeError("same-parent absent target required")
    before = inspect(source, directory=True)
    if before["volume_id"] != inspect(source.parent, directory=True)["volume_id"]:
        raise NativeError("source and parent volume differ")
    if not KERNEL.MoveFileExW(str(source), str(target), 0):
        raise _winerror("MoveFileExW")
    if inspect(target, directory=True) != before:
        raise NativeError("archive identity readback mismatch")


def create_junction(link: Path, target: Path, acl_source: Path) -> None:
    if present(link) or not target.is_dir():
        raise NativeError("junction preconditions failed")
    target_identity = inspect(target, directory=True)
    if not KERNEL.CreateDirectoryW(str(link), None):
        raise _winerror("CreateDirectoryW junction placeholder")
    copy_acl(acl_source, link)
    if acl_fingerprint(link) != acl_fingerprint(acl_source):
        raise NativeError("junction placeholder ACL mismatch")
    payload = _junction_payload(target)
    handle = _open(link, 0x40000000)
    try:
        returned = wintypes.DWORD()
        buffer = ctypes.create_string_buffer(payload)
        if not KERNEL.DeviceIoControl(handle, FSCTL_SET_REPARSE_POINT, buffer, len(payload),
                                       None, 0, ctypes.byref(returned), None):
            raise _winerror("FSCTL_SET_REPARSE_POINT")
    finally:
        _close(handle)
    validate_junction(link, target)
    if identity_follow(link) != target_identity:
        raise NativeError("junction target identity mismatch")


def _junction_payload(target: Path) -> bytes:
    substitute = ("\\??\\" + str(target)).encode("utf-16-le")
    printed = str(target).encode("utf-16-le")
    path_bytes = substitute + b"\x00\x00" + printed + b"\x00\x00"
    header = (
        IO_REPARSE_TAG_MOUNT_POINT.to_bytes(4, "little")
        + (8 + len(path_bytes)).to_bytes(2, "little") + b"\x00\x00"
        + (0).to_bytes(2, "little") + len(substitute).to_bytes(2, "little")
        + (len(substitute) + 2).to_bytes(2, "little") + len(printed).to_bytes(2, "little")
    )
    payload = header + path_bytes
    if len(payload) > 16384 or len(path_bytes) + 8 > 0xFFFF:
        raise NativeError("junction reparse buffer too long")
    return payload


def validate_junction(link: Path, target: Path) -> None:
    leaf = os.lstat(link)
    if not stat.S_ISDIR(leaf.st_mode) or not leaf.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise NativeError("exact directory junction required")
    payload = _junction_payload(target)
    handle = _open(link, FILE_READ_ATTRIBUTES)
    try:
        returned = wintypes.DWORD()
        readback = ctypes.create_string_buffer(16384)
        if not KERNEL.DeviceIoControl(handle, FSCTL_GET_REPARSE_POINT, None, 0,
                                       readback, len(readback), ctypes.byref(returned), None):
            raise _winerror("FSCTL_GET_REPARSE_POINT")
        if returned.value != len(payload) or readback.raw[:len(payload)] != payload:
            raise NativeError("junction reparse readback mismatch")
    finally:
        _close(handle)


def present(path: Path) -> bool:
    try:
        os.lstat(path)
        return True
    except FileNotFoundError:
        return False
