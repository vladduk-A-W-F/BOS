"""Guarded future C/d8 to D/dev8 owner-runtime delivery template.

Preparation only: every immutable dev8 pin is deliberately PENDING. The
configuration gate runs before any filesystem, Git, process, or data access.
After final pin review and root GO, capture and apply form the only permitted
metadata transition; this module never creates a database, seeds, migrates,
resets, changes access, or starts/stops a server.
"""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


CARD_ID = "B30-INVOICE-DEV8-D-DELIVERY-PREP"
FROM_C_SOURCE = Path(r"C:\Users\user\.codex\worktrees\bos3-local-runtime\repo")
FROM_C_COMMIT = "d8e121a0b38bb8c98f5719568b6fa87374e2bfb0"
TO_D_SOURCE = Path(r"D:\3\BOSDev\workspaces\bos3-runtime-dev8\repo")
TO_D_SOURCE_CONTEXT_COMMIT = "c00c60aad0c4f8e70251da3c7174ed105089198b"
INSTANCE_ROOT = Path(r"D:\3\BOSDev\local-bos3\owner")
RUNTIME_PORT = 8030
ARCHIVE_NAME = re.compile(r"^maintenance-INVOICE-DEV8-D-[A-Za-z0-9._-]+$")
PASSPORT_PRODUCT_COMMIT = "411e222c4687b6a029c027518d3f20453c5849db"
PASSPORT_HASH_KIND = "GIT_BLOB_BYTES_SHA256"
PASSPORT_RUNTIME_DELTA = (
    ("README.md", "3d1703d502b2c080a5dda89d2adf5506a4f00b9186c6d9e473ffd78ff8b6503b", 5056),
    ("README_UA.md", "e0a2c4ed82e1c5839b5ca06f8c0adac966fb3d1154d424c153fd800e3fc53d9c", 15547),
    ("boss_project/version.py", "ba7a3a9f2cf5b7b1661165ee661a500f53ac05920ab2af5b27d5c32d61f57520", 24),
    ("erp/experience.py", "db613bacaecd2b60c3656042d52016a6c692865115176e0cc473a24c66a2702b", 23073),
    ("erp/test_home_projection.py", "cc2bf7f029e10c2277e3f902d7171d0e1eda5c6011ec448a794e559c0587a1e2", 1523),
)
UNCHANGED_DEV7_ASSETS_NOT_RERUN = (
    ("assets/app.js", "51732f2f359ac0155a9ff0e0d041ed2b6941bf23329c02adf72855b2628fd59e", 1272362),
    ("docs/BoS_3_0_Start_UA.pdf", "048d8488798ab0151fa2c787106f46e4aba8fc25cc754ab44d65ce505b142e8c", 96140),
    ("docs/BoS_3_0_Start_UA.manifest.json", "9d13ceef684c8f4eb97108e6fdad1e3a31cfd542a87a52971ac6987beeafd111", 259),
)

# These values are intentionally the sole final-fill surface. Do not execute
# this template until one immutable package and independent review fill all.
DEV8_COMMIT = "60f1e31fca6056711ea52d7aade6b65e0b14afff"
DEV8_VERSION = "0.3.0-dev.8"
DEV8_MANIFEST_PATH = "docs/orchestration/bos3/INVOICE_DEV8_CANDIDATE.json"
DEV8_MANIFEST_SHA256 = "9286497d1aa88177fca6580b1ddcfabcd7345de9bb6eac19b4c7f170d3bacbb2"
DELIVERY_FILES = frozenset(path for path, _, _ in PASSPORT_RUNTIME_DELTA)
DELIVERY_ALLOWLIST_SHA256 = "20d30eea700251e87825097e7fbfee8d94e6e70dd68584a066fceee03934b5b4"
FINAL_REVIEW_SHA256 = "9711804f35b04a5a6228fc31bcb84e5316f2ea12ddf77d0470a153482f5a63db"
RESERVED_ROOT_GO_TOKEN = "ROOT_DEV8_D_OWNER_LOCAL_20260928_WINDOW1"
ROOT_TECHNICAL_GO = "ROOT_DEV8_D_OWNER_LOCAL_20260928_WINDOW1"


class DeliveryError(RuntimeError):
    pass


def git(source, *args, check=True):
    result = subprocess.run(
        ["git", "-C", str(source), *args], capture_output=True, text=True, encoding="utf-8"
    )
    if check and result.returncode:
        raise DeliveryError("Git precondition failed: " + " ".join(args))
    return result


def git_blob(source, revision, relative):
    result = subprocess.run(["git", "-C", str(source), "show", revision + ":" + relative], capture_output=True)
    if result.returncode:
        raise DeliveryError("Immutable candidate blob is unavailable.")
    return result.stdout


def require_passport_entries(entries, expected, label):
    if not isinstance(entries, list) or len(entries) != len(expected):
        raise DeliveryError(label + " shape differs from the reviewed passport.")
    observed = tuple((row.get("path"), row.get("sha256"), row.get("bytes")) if isinstance(row, dict) else None
                     for row in entries)
    if observed != expected:
        raise DeliveryError(label + " differs from the reviewed passport.")


def require_passport(source, manifest_bytes):
    try:
        passport = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DeliveryError("Immutable dev8 passport is not valid JSON.") from error
    if (passport.get("schema") != 1 or passport.get("product_commit") != PASSPORT_PRODUCT_COMMIT
            or passport.get("baseline_runtime_commit") != FROM_C_COMMIT
            or passport.get("hash_kind") != PASSPORT_HASH_KIND):
        raise DeliveryError("Immutable dev8 passport identity differs.")
    require_passport_entries(passport.get("non_orchestration_runtime_delta"), PASSPORT_RUNTIME_DELTA,
                             "Runtime delta")
    require_passport_entries(passport.get("unchanged_dev7_assets_not_rerun"), UNCHANGED_DEV7_ASSETS_NOT_RERUN,
                             "Unchanged dev7 assets")
    for path, expected_hash, expected_bytes in PASSPORT_RUNTIME_DELTA + UNCHANGED_DEV7_ASSETS_NOT_RERUN:
        blob = git_blob(source, PASSPORT_PRODUCT_COMMIT, path)
        if len(blob) != expected_bytes or hashlib.sha256(blob).hexdigest() != expected_hash:
            raise DeliveryError("Git blob bytes differ from passport for " + path)
    return passport


def require_candidate_runtime_delta(source):
    verified = []
    for path, expected_hash, expected_bytes in PASSPORT_RUNTIME_DELTA:
        blob = git_blob(source, DEV8_COMMIT, path)
        actual_hash = hashlib.sha256(blob).hexdigest()
        if len(blob) != expected_bytes or actual_hash != expected_hash:
            raise DeliveryError("Final dev8 candidate blob differs from passport for " + path)
        verified.append({"path": path, "sha256": actual_hash, "bytes": len(blob)})
    return verified


def source_digest(source):
    if git(source, "status", "--porcelain").stdout:
        raise DeliveryError("Source checkout is not clean.")
    listed_result = subprocess.run(["git", "-C", str(source), "ls-files", "-z"], capture_output=True)
    if listed_result.returncode:
        raise DeliveryError("Tracked source manifest is unavailable.")
    digest = hashlib.sha256()
    for raw in listed_result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = Path(raw.decode("utf-8"))
        path = source / relative
        if not path.is_file():
            raise DeliveryError("Tracked source file is missing.")
        digest.update(str(relative).replace("\\", "/").encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def allowlist_digest(paths):
    return hashlib.sha256(("\n".join(sorted(paths)) + "\n").encode("utf-8")).hexdigest()


def require_final_pins():
    values = {
        "dev8_commit": DEV8_COMMIT,
        "dev8_version": DEV8_VERSION,
        "manifest_path": DEV8_MANIFEST_PATH,
        "manifest_sha256": DEV8_MANIFEST_SHA256,
        "allowlist_sha256": DELIVERY_ALLOWLIST_SHA256,
        "final_review_sha256": FINAL_REVIEW_SHA256,
        "root_technical_go": ROOT_TECHNICAL_GO,
    }
    if any(value.startswith("PENDING_") for value in values.values()):
        raise DeliveryError("FINAL_PIN_REVIEW_AND_ROOT_GO_PENDING")
    if not re.fullmatch(r"[0-9a-f]{40}", DEV8_COMMIT):
        raise DeliveryError("Immutable dev8 commit is malformed.")
    if not re.fullmatch(r"[0-9a-f]{64}", DEV8_MANIFEST_SHA256):
        raise DeliveryError("Immutable manifest SHA-256 is malformed.")
    if not re.fullmatch(r"[0-9a-f]{64}", DELIVERY_ALLOWLIST_SHA256):
        raise DeliveryError("Delivery allowlist SHA-256 is malformed.")
    if not re.fullmatch(r"[0-9a-f]{64}", FINAL_REVIEW_SHA256):
        raise DeliveryError("Final review SHA-256 is malformed.")
    if not DELIVERY_FILES or any(not isinstance(path, str) or not path or path.startswith("/")
                                or ".." in path.split("/") for path in DELIVERY_FILES):
        raise DeliveryError("Exact reviewed delivery allowlist is unavailable.")
    if allowlist_digest(DELIVERY_FILES) != DELIVERY_ALLOWLIST_SHA256:
        raise DeliveryError("Reviewed delivery allowlist hash differs.")
    if not isinstance(DEV8_MANIFEST_PATH, str) or not DEV8_MANIFEST_PATH or DEV8_MANIFEST_PATH.startswith("/"):
        raise DeliveryError("Immutable manifest path is malformed.")
    return values


def require_fixed_paths(from_source, to_source, root):
    if from_source.resolve() != FROM_C_SOURCE.resolve():
        raise DeliveryError("Only the recorded C/d8 source may be captured or stopped.")
    if to_source.resolve() != TO_D_SOURCE.resolve():
        raise DeliveryError("Only the fixed D runtime-dev8 source path is allowed.")
    if root.resolve() != INSTANCE_ROOT.resolve():
        raise DeliveryError("Only the recorded owner instance root is allowed.")
    if not str(to_source.resolve()).lower().startswith("d:\\"):
        raise DeliveryError("Future runtime source must be on D.")


def atomic_json(path, value, owner_root):
    require_ordinary_write_subpath(path, owner_root)
    temporary = path.with_name(path.name + ".tmp")
    require_ordinary_write_subpath(temporary, owner_root)
    if temporary.exists():
        raise DeliveryError("Existing temporary delivery file blocks atomic write.")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DeliveryError("Required delivery metadata is unavailable.") from error


def paths(root):
    return {
        "root": root,
        "data": root / "data",
        "media": root / "media",
        "state": root / "state",
        "prepared": root / "state" / "prepared.json",
        "process": root / "state" / "process.json",
        "owner_access": root / "state" / "owner-access.json",
        "runtime_secrets": root / "state" / "runtime-secrets.json",
    }


def protected_payload_digest(layout):
    owner_root = layout["root"]
    if owner_root.resolve() != INSTANCE_ROOT.resolve():
        raise DeliveryError("Protected payload root differs from the fixed owner root.")
    require_ordinary_contained(owner_root, owner_root, require_directory=True)
    digest = hashlib.sha256()
    for directory in (layout["data"], layout["media"]):
        require_ordinary_contained(directory, owner_root, require_directory=True)
        for current, directories, files in os.walk(directory, topdown=True, followlinks=False):
            current_path = Path(current)
            require_ordinary_contained(current_path, owner_root, require_directory=True)
            for name in directories:
                require_ordinary_contained(current_path / name, owner_root, require_directory=True)
            for name in files:
                path = current_path / name
                require_ordinary_contained(path, owner_root, require_directory=False)
                digest.update(str(path.relative_to(owner_root)).replace("\\", "/").encode("utf-8") + b"\0")
                digest.update(path.read_bytes())
    for key in ("owner_access", "runtime_secrets"):
        path = layout[key]
        require_ordinary_contained(path, owner_root, require_directory=False)
        digest.update(str(path.relative_to(owner_root)).replace("\\", "/").encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def require_ordinary_contained(path, owner_root, require_directory):
    try:
        path.relative_to(owner_root)
        root_resolved = owner_root.resolve(strict=True)
    except (OSError, ValueError) as error:
        raise DeliveryError("Protected path is outside the fixed owner root.") from error
    cursor = path
    while True:
        try:
            metadata = cursor.lstat()
        except OSError as error:
            raise DeliveryError("Protected path is unavailable.") from error
        attributes = getattr(metadata, "st_file_attributes", 0)
        if stat.S_ISLNK(metadata.st_mode) or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise DeliveryError("Protected payload reparse entry is unsupported.")
        if cursor == owner_root:
            break
        cursor = cursor.parent
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (OSError, ValueError) as error:
        raise DeliveryError("Protected path resolves outside the fixed owner root.") from error
    if require_directory != path.is_dir():
        raise DeliveryError("Protected path type differs from the expected contract.")
    return resolved


def require_ordinary_write_subpath(path, owner_root):
    try:
        path.relative_to(owner_root)
        root_resolved = owner_root.resolve(strict=True)
    except (OSError, ValueError) as error:
        raise DeliveryError("Write path is outside the fixed owner root.") from error
    cursor = path.parent
    while True:
        try:
            metadata = cursor.lstat()
        except OSError as error:
            raise DeliveryError("Write path parent is unavailable.") from error
        attributes = getattr(metadata, "st_file_attributes", 0)
        if stat.S_ISLNK(metadata.st_mode) or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise DeliveryError("Write path reparse parent is unsupported.")
        if not cursor.is_dir():
            raise DeliveryError("Write path parent is not a directory.")
        try:
            cursor.resolve(strict=True).relative_to(root_resolved)
        except (OSError, ValueError) as error:
            raise DeliveryError("Write path parent resolves outside the fixed owner root.") from error
        if cursor == owner_root:
            break
        cursor = cursor.parent
    if path.exists():
        require_ordinary_contained(path, owner_root, require_directory=False)


def require_from_source(source, layout):
    if git(source, "rev-parse", "HEAD").stdout.strip() != FROM_C_COMMIT:
        raise DeliveryError("C source is not the recorded d8 runtime.")
    digest = source_digest(source)
    prepared = read_json(layout["prepared"])
    expected_database = layout["data"] / "bos3-fasteners.sqlite3"
    if (prepared.get("source") != str(source) or prepared.get("source_sha256") != digest
            or prepared.get("database") != str(expected_database) or prepared.get("port") != RUNTIME_PORT
            or not prepared.get("initialized_at") or not expected_database.is_file()):
        raise DeliveryError("Prepared runtime metadata does not bind the C/d8 source.")
    return prepared, digest


def require_d_target(source):
    pins = require_final_pins()
    if git(source, "rev-parse", "HEAD").stdout.strip() != DEV8_COMMIT:
        raise DeliveryError("D runtime checkout is not the immutable dev8 pin.")
    if git(source, "merge-base", "--is-ancestor", FROM_C_COMMIT, DEV8_COMMIT, check=False).returncode:
        raise DeliveryError("Immutable dev8 candidate does not descend from d8.")
    if git(source, "merge-base", "--is-ancestor", PASSPORT_PRODUCT_COMMIT, DEV8_COMMIT, check=False).returncode:
        raise DeliveryError("Immutable dev8 candidate does not contain the reviewed invoice product commit.")
    if git(source, "config", "--get", "core.autocrlf", check=False).stdout.strip().lower() != "false":
        raise DeliveryError("D runtime checkout must set core.autocrlf=false for separate blob/disk proof.")
    manifest = git_blob(source, DEV8_COMMIT, DEV8_MANIFEST_PATH)
    if hashlib.sha256(manifest).hexdigest() != DEV8_MANIFEST_SHA256:
        raise DeliveryError("Immutable manifest hash differs from the approved pin.")
    require_passport(source, manifest)
    changed = [path for path in git(source, "diff", "--name-only", FROM_C_COMMIT, DEV8_COMMIT).stdout.splitlines() if path]
    product_paths = [path for path in changed if not path.startswith("docs/orchestration/")]
    if set(product_paths) != DELIVERY_FILES or len(product_paths) != len(DELIVERY_FILES):
        raise DeliveryError("Final dev8 candidate product path set differs from the exact passport delta.")
    return pins, source_digest(source), product_paths, require_candidate_runtime_delta(source)


def native_powershell_environment():
    env = {key.upper(): value for key, value in os.environ.items()}
    system_root = Path(env.get("SYSTEMROOT", ""))
    executable = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    modules = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "Modules"
    if not system_root.is_absolute() or not executable.is_file() or not modules.is_dir():
        raise DeliveryError("Native Windows PowerShell is unavailable.")
    env["PSMODULEPATH"] = str(modules)
    return str(executable), env


class WindowsProcess:
    def __init__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        self.kernel.GetProcessTimes.restype = wintypes.BOOL
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
            wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL

    def open(self, pid):
        return self.kernel.OpenProcess(0x1000, False, pid) or None

    def identity(self, handle, pid):
        times = [wintypes.FILETIME() for _ in range(4)]
        if not self.kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
            raise DeliveryError("Cannot verify receipt creation time.")
        size = wintypes.DWORD(32768)
        image = ctypes.create_unicode_buffer(size.value)
        if not self.kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            raise DeliveryError("Cannot verify receipt executable path.")
        return {"pid": pid, "created_ticks": (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
                "image": str(Path(image.value).resolve()).replace("\\", "/").lower()}

    def close(self, handle):
        if handle:
            self.kernel.CloseHandle(handle)


def command_line(pid):
    powershell, env = native_powershell_environment()
    command = ('$p=Get-CimInstance Win32_Process -Filter "ProcessId = ' + str(pid)
               + '"; if ($null -ne $p) {[Console]::Out.Write($p.CommandLine)}')
    result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", command],
                            env=env, capture_output=True, text=True, encoding="utf-8", timeout=15)
    if result.returncode:
        raise DeliveryError("Cannot verify receipt command line.")
    return result.stdout


def listener_pid(port):
    powershell, env = native_powershell_environment()
    command = ('$listeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | '
               'Where-Object { $_.LocalPort -eq ' + str(port) + ' }); '
               "if ($listeners.Count -eq 1 -and ($listeners[0].LocalAddress -eq '127.0.0.1' "
               "-or $listeners[0].LocalAddress -eq '::1')) {[Console]::Out.Write($listeners[0].OwningProcess)} "
               'elseif ($listeners.Count -gt 0) { exit 2 }')
    result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", command],
                            env=env, capture_output=True, text=True, encoding="utf-8", timeout=15)
    if result.returncode:
        raise DeliveryError("Cannot determine loopback listener identity.")
    return int(result.stdout) if result.stdout.strip().isdigit() else None


def require_ready_receipt(layout, source, digest):
    receipt = read_json(layout["process"])
    record = receipt.get("process")
    tokens = receipt.get("required_tokens")
    if receipt.get("status") != "ready" or not isinstance(record, dict) or not isinstance(tokens, list):
        raise DeliveryError("Ready identity-bound process receipt is required.")
    if receipt.get("source") != str(source) or receipt.get("source_sha256") != digest:
        raise DeliveryError("Ready receipt is not bound to the expected source.")
    if set(record) != {"pid", "created_ticks", "image"} or not isinstance(record["pid"], int):
        raise DeliveryError("Ready process receipt is malformed.")
    process = WindowsProcess()
    handle = process.open(record["pid"])
    if handle is None:
        raise DeliveryError("Receipt process has already exited.")
    try:
        if process.identity(handle, record["pid"]) != record:
            raise DeliveryError("Live process differs from protected receipt identity.")
    finally:
        process.close(handle)
    if any(token not in command_line(record["pid"]) for token in tokens):
        raise DeliveryError("Live process command differs from protected receipt identity.")
    if listener_pid(RUNTIME_PORT) != record["pid"]:
        raise DeliveryError("Ready receipt PID is not the sole runtime listener.")
    return receipt


def require_stopped(source):
    powershell, env = native_powershell_environment()
    env["BOS3_FROM_SOURCE"] = str(source)
    env["BOS3_PORT"] = str(RUNTIME_PORT)
    command = r'''
$processes = @(Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -like ('*' + $env:BOS3_FROM_SOURCE + '*internal-serve*')
})
$listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object {
  $_.LocalPort -eq [int]$env:BOS3_PORT
})
if ($processes.Count -ne 0 -or $listeners.Count -ne 0) { exit 2 }
'''
    result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", command],
                            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=15)
    if result.returncode:
        raise DeliveryError("Instance is not proven stopped by the official lifecycle action.")


def archive_directory(layout, name):
    if not ARCHIVE_NAME.fullmatch(name):
        raise DeliveryError("Archive name is not an allowed delivery identifier.")
    require_ordinary_contained(layout["root"], layout["root"], require_directory=True)
    require_ordinary_contained(layout["state"], layout["root"], require_directory=True)
    archive = layout["state"] / name
    require_ordinary_write_subpath(archive, layout["root"])
    if archive.exists():
        raise DeliveryError("Delivery archive already exists.")
    archive.mkdir()
    require_ordinary_contained(archive, layout["root"], require_directory=True)
    return archive


def capture(args):
    require_final_pins()
    from_source, to_source, root = args.from_source.resolve(), args.to_source.resolve(), args.root.resolve()
    require_fixed_paths(from_source, to_source, root)
    layout = paths(root)
    prepared, from_digest = require_from_source(from_source, layout)
    pins, to_digest, product_paths, candidate_blobs = require_d_target(to_source)
    ready = require_ready_receipt(layout, from_source, from_digest)
    archive = archive_directory(layout, args.archive_name)
    original_prepared = layout["prepared"].read_bytes()
    prepared_before_stop = archive / "prepared.before-stop.json"
    require_ordinary_write_subpath(prepared_before_stop, layout["root"])
    prepared_before_stop.write_bytes(original_prepared)
    atomic_json(archive / "started-attestation.json", {
        "schema": "bos3.invoice-dev8-d.started-attestation/v1", "at": datetime.now(timezone.utc).isoformat(),
        "card": CARD_ID, "from_source": str(from_source), "from_commit": FROM_C_COMMIT,
        "from_source_sha256": from_digest, "to_source": str(to_source), "to_commit": DEV8_COMMIT,
        "to_source_sha256": to_digest, "version": DEV8_VERSION, "manifest_path": DEV8_MANIFEST_PATH,
        "manifest_sha256": pins["manifest_sha256"], "allowlist_sha256": pins["allowlist_sha256"],
        "final_review_sha256": pins["final_review_sha256"], "root_technical_go": pins["root_technical_go"],
        "product_paths": product_paths, "verified_candidate_blobs": candidate_blobs,
        "prepared_sha256": hashlib.sha256(original_prepared).hexdigest(),
        "protected_payload_sha256": protected_payload_digest(layout), "process_identity": ready["process"],
        "archive": str(archive),
    }, layout["root"])
    print(json.dumps({"captured": True, "archive": str(archive), "from": FROM_C_COMMIT, "to": DEV8_COMMIT}, sort_keys=True))


def apply(args):
    require_final_pins()
    from_source, to_source, root = args.from_source.resolve(), args.to_source.resolve(), args.root.resolve()
    require_fixed_paths(from_source, to_source, root)
    layout = paths(root)
    prepared, from_digest = require_from_source(from_source, layout)
    pins, to_digest, product_paths, candidate_blobs = require_d_target(to_source)
    attestation_path = args.attestation if args.attestation.is_absolute() else args.attestation.absolute()
    try:
        attestation_path.relative_to(layout["state"])
    except ValueError as error:
        raise DeliveryError("Capture attestation must remain below instance state.") from error
    require_ordinary_contained(attestation_path, layout["root"], require_directory=False)
    attestation_path = attestation_path.resolve()
    attestation = read_json(attestation_path)
    expected = {
        "schema": "bos3.invoice-dev8-d.started-attestation/v1", "card": CARD_ID,
        "from_source": str(from_source), "from_commit": FROM_C_COMMIT, "from_source_sha256": from_digest,
        "to_source": str(to_source), "to_commit": DEV8_COMMIT, "to_source_sha256": to_digest,
        "manifest_path": DEV8_MANIFEST_PATH, "manifest_sha256": pins["manifest_sha256"],
        "allowlist_sha256": pins["allowlist_sha256"], "final_review_sha256": pins["final_review_sha256"],
        "root_technical_go": pins["root_technical_go"], "version": DEV8_VERSION,
    }
    if any(attestation.get(key) != value for key, value in expected.items()):
        raise DeliveryError("Capture attestation does not bind this exact delivery.")
    if attestation.get("verified_candidate_blobs") != candidate_blobs:
        raise DeliveryError("Capture attestation lacks the exact final dev8 blob proof.")
    before = protected_payload_digest(layout)
    if attestation.get("protected_payload_sha256") != before:
        raise DeliveryError("Protected payload differs from fresh capture attestation.")
    if layout["process"].exists():
        raise DeliveryError("Official stop did not clear the process receipt.")
    require_stopped(from_source)
    if attestation.get("prepared_sha256") != hashlib.sha256(layout["prepared"].read_bytes()).hexdigest():
        raise DeliveryError("Prepared metadata changed after capture.")
    updated = {**prepared, "source": str(to_source), "source_sha256": to_digest}
    atomic_json(layout["prepared"], updated, layout["root"])
    after = read_json(layout["prepared"])
    if (after.get("source") != str(to_source) or after.get("source_sha256") != to_digest
            or any(after.get(key) != value for key, value in prepared.items()
                   if key not in {"source", "source_sha256"})):
        raise DeliveryError("Prepared metadata changed outside the two allowed source fields.")
    if protected_payload_digest(layout) != before:
        raise DeliveryError("Protected payload changed during source metadata rebind.")
    archive = attestation_path.parent
    atomic_json(archive / "maintenance-receipt.json", {
        "schema": "bos3.invoice-dev8-d.maintenance-receipt/v1", "at": datetime.now(timezone.utc).isoformat(),
        "card": CARD_ID, "from_commit": FROM_C_COMMIT, "to_commit": DEV8_COMMIT,
        "from_source_sha256": from_digest, "to_source_sha256": to_digest,
        "manifest_path": DEV8_MANIFEST_PATH, "manifest_sha256": pins["manifest_sha256"],
        "product_paths": product_paths, "verified_candidate_blobs": candidate_blobs,
        "protected_payload_unchanged": True,
        "prepared_fields_changed": ["source", "source_sha256"],
        "never_called": ["clone", "checkout", "init", "seed", "migrate", "reset", "start", "stop"],
    }, layout["root"])
    print(json.dumps({"updated": True, "from": FROM_C_COMMIT, "to": DEV8_COMMIT}, sort_keys=True))


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("capture", "apply"):
        command = commands.add_parser(name)
        command.add_argument("--from-source", type=Path, required=True)
        command.add_argument("--to-source", type=Path, required=True)
        command.add_argument("--root", type=Path, required=True)
    commands.choices["capture"].add_argument("--archive-name", required=True)
    commands.choices["apply"].add_argument("--attestation", type=Path, required=True)
    return result


if __name__ == "__main__":
    try:
        arguments = parser().parse_args()
        if arguments.command == "capture":
            capture(arguments)
        else:
            apply(arguments)
    except (DeliveryError, OSError, subprocess.SubprocessError) as error:
        print("BOS3_DEV8_D_DELIVERY_REFUSED: " + str(error), file=sys.stderr)
        raise SystemExit(2)
