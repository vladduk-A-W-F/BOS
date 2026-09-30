"""Fail-closed preparation for one future repaired dev8 recovery window.

No command in this template is authorized now. Final pins deliberately remain
PENDING, and their gate precedes filesystem, Git, process, secret, or data
access. The future preflight command is read-only and must be a separately
reviewed operation before `apply` can be considered.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time


CARD_ID = "B30-ATOMIC-RECEIPT-RECOVERY-PREP"
INSTANCE_ROOT = Path(r"D:\3\BOSDev\local-bos3\owner")
FAILED_SOURCE = Path(r"D:\3\BOSDev\workspaces\bos3-runtime-dev8\repo")
FAILED_COMMIT = "60f1e31fca6056711ea52d7aade6b65e0b14afff"
FAILED_SOURCE_SHA256 = "06a4bf2fa7f681a0a4c83612045d894feebc7908849beb574359792a119f4fc8"
REPAIRED_SOURCE = Path(r"D:\3\BOSDev\workspaces\bos3-runtime-dev9\repo")
RUNTIME_PORT = 8030
RESIDUAL_TEMP_NAMES = (
    "process.json.7ebb63ea7d83910c.tmp",
    "process.json.be6a89a61b41a79a.tmp",
)
RECOVERY_NAME = re.compile(r"^recovery-INVOICE-DEV8-ATOMIC-[A-Za-z0-9._-]+$")

# The sole final-fill surface. All values must be independently pinned and root
# approved before any command can inspect an owner instance.
REPAIRED_COMMIT = "aa6a4ca4c4b50f0c2ba01495eab74e568d0e2975"
REPAIRED_SOURCE_SHA256 = "e7046ad6e0374d36de33716ffa0152e31330dbf82fab3e24184bf3d573abebe0"
REPAIRED_VERSION = "0.3.0-dev.9"
REPAIR_REVIEW_SHA256 = "aae464c3c1a6ee492fc6db107ac7abdb63776e634eee2d7b7c02676a319e6c26"
ROOT_RECOVERY_GO = "ROOT_ATOMIC_DEV9_RECOVERY_20260928_ONCE"
REVIEWED_PREFLIGHT_RECEIPT_SHA256 = "PENDING_REVIEWED_PREFLIGHT_RECEIPT_SHA256"
PREFLIGHT_RECEIPT_ROOT = Path(r"D:\3\BOSDev\qa-scratch\bos3-atomic-receipt-recovery-20260928\preflight-receipts")


class RecoveryError(RuntimeError):
    pass


def require_final_pins():
    values = (REPAIRED_COMMIT, REPAIRED_SOURCE_SHA256, REPAIRED_VERSION,
              REPAIR_REVIEW_SHA256, ROOT_RECOVERY_GO)
    if any(value.startswith("PENDING_") for value in values):
        raise RecoveryError("FINAL_REPAIRED_PIN_REVIEW_AND_ROOT_GO_PENDING")
    if not re.fullmatch(r"[0-9a-f]{40}", REPAIRED_COMMIT):
        raise RecoveryError("REPAIRED_COMMIT_FORMAT_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}", REPAIRED_SOURCE_SHA256):
        raise RecoveryError("REPAIRED_SOURCE_DIGEST_FORMAT_INVALID")


def layout(root):
    return {
        "root": root, "state": root / "state", "data": root / "data", "media": root / "media",
        "prepared": root / "state" / "prepared.json", "process": root / "state" / "process.json",
        "access": root / "state" / "owner-access.json", "secrets": root / "state" / "runtime-secrets.json",
        "failure": root / "state" / "last-start-failure.json",
    }


def ordinary(path, root, directory):
    try:
        path.relative_to(root)
        resolved_root = root.resolve(strict=True)
    except (OSError, ValueError) as error:
        raise RecoveryError("PATH_OUTSIDE_FIXED_OWNER_ROOT") from error
    cursor = path
    while True:
        try:
            metadata = cursor.lstat()
        except OSError as error:
            raise RecoveryError("REQUIRED_PATH_UNAVAILABLE") from error
        attributes = getattr(metadata, "st_file_attributes", 0)
        if stat.S_ISLNK(metadata.st_mode) or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise RecoveryError("REPARSE_PATH_UNSUPPORTED")
        if cursor == root:
            break
        cursor = cursor.parent
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as error:
        raise RecoveryError("PATH_RESOLVES_OUTSIDE_FIXED_OWNER_ROOT") from error
    if path.is_dir() != directory:
        raise RecoveryError("PATH_TYPE_UNEXPECTED")
    return resolved


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RecoveryError("REQUIRED_METADATA_UNAVAILABLE") from error


def source_digest(source):
    result = subprocess.run(["git", "-C", str(source), "status", "--porcelain"],
                            capture_output=True, text=True, encoding="utf-8")
    if result.returncode or result.stdout:
        raise RecoveryError("REPAIRED_SOURCE_NOT_CLEAN")
    listed = subprocess.run(["git", "-C", str(source), "ls-files", "-z"], capture_output=True)
    if listed.returncode:
        raise RecoveryError("REPAIRED_SOURCE_MANIFEST_UNAVAILABLE")
    digest = hashlib.sha256()
    for raw in listed.stdout.split(b"\0"):
        if raw:
            relative = Path(raw.decode("utf-8"))
            file_path = source / relative
            if not file_path.is_file():
                raise RecoveryError("REPAIRED_TRACKED_FILE_MISSING")
            digest.update(str(relative).replace("\\", "/").encode("utf-8") + b"\0")
            digest.update(file_path.read_bytes())
    return digest.hexdigest()


def require_exact_source(source, commit, digest, label):
    head = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True,
                          text=True, encoding="utf-8")
    if head.returncode or head.stdout.strip() != commit:
        raise RecoveryError(label + "_HEAD_MISMATCH")
    if source_digest(source) != digest:
        raise RecoveryError(label + "_SOURCE_DIGEST_MISMATCH")


def native_powershell_environment():
    env = {key.upper(): value for key, value in os.environ.items()}
    system_root = Path(env.get("SYSTEMROOT", ""))
    executable = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    modules = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "Modules"
    if not system_root.is_absolute() or not executable.is_file() or not modules.is_dir():
        raise RecoveryError("NATIVE_WINDOWS_POWERSHELL_UNAVAILABLE")
    env["PSMODULEPATH"] = str(modules)
    return str(executable), env


def protected_digest(items):
    digest = hashlib.sha256()
    root = items["root"]
    for directory in (items["data"], items["media"]):
        ordinary(directory, root, True)
        for current, directories, files in os.walk(directory, topdown=True, followlinks=False):
            current_path = Path(current)
            ordinary(current_path, root, True)
            for name in directories:
                ordinary(current_path / name, root, True)
            for name in files:
                path = current_path / name
                ordinary(path, root, False)
                digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8") + b"\0")
                digest.update(path.read_bytes())
    for key in ("access", "secrets"):
        path = items[key]
        ordinary(path, root, False)
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def residual_metadata(items):
    result = []
    for name in RESIDUAL_TEMP_NAMES:
        path = items["state"] / name
        ordinary(path, items["root"], False)
        item = path.stat()
        result.append({"name": name, "bytes": item.st_size, "mtime_ns": item.st_mtime_ns})
    return result


def require_no_server_or_listener():
    command = ("$server=@(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object { "
               "$_.CommandLine -like '*internal-serve*' -and ($_.CommandLine -like '*bos3-runtime-dev8*') }); "
               "$listeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -eq "
               + str(RUNTIME_PORT) + " }); if ($server.Count -ne 0 -or $listeners.Count -ne 0) { exit 2 }")
    powershell, environment = native_powershell_environment()
    result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", command], env=environment,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=15)
    if result.returncode:
        raise RecoveryError("SERVER_OR_PORT_OCCUPIED_STOP_WITHOUT_KILL")


def preflight(root, failed_source):
    require_final_pins()
    if root.resolve() != INSTANCE_ROOT.resolve() or failed_source.resolve() != FAILED_SOURCE.resolve():
        raise RecoveryError("FIXED_FAILED_INSTANCE_OR_SOURCE_MISMATCH")
    require_exact_source(failed_source, FAILED_COMMIT, FAILED_SOURCE_SHA256, "FAILED_SOURCE")
    items = layout(root)
    for key in ("root", "state", "data", "media"):
        ordinary(items[key], root, True)
    for key in ("prepared", "access", "secrets", "failure"):
        ordinary(items[key], root, False)
    if items["process"].exists():
        raise RecoveryError("PROCESS_RECEIPT_PRESENT_STOP_WITHOUT_KILL")
    prepared_bytes = items["prepared"].read_bytes()
    prepared = read_json(items["prepared"])
    expected_database = items["data"] / "bos3-fasteners.sqlite3"
    if (prepared.get("source") != str(failed_source) or prepared.get("source_sha256") != FAILED_SOURCE_SHA256
            or prepared.get("database") != str(expected_database) or prepared.get("port") != RUNTIME_PORT
            or not prepared.get("initialized_at") or not expected_database.is_file()):
        raise RecoveryError("FAILED_DEV8_PREPARED_STATE_DIVERGES_STOP")
    failure = read_json(items["failure"])
    if (failure.get("source_sha256") != FAILED_SOURCE_SHA256
            or failure.get("cleanup", {}).get("stopped_after_start_failure") is not True):
        raise RecoveryError("SAVED_CLEANUP_RECEIPT_DIVERGES_STOP")
    require_no_server_or_listener()
    return {
        "schema": "bos3.atomic-receipt-recovery.preflight/v1", "card": CARD_ID,
        "failed_source": str(failed_source), "failed_commit": FAILED_COMMIT,
        "failed_source_sha256": FAILED_SOURCE_SHA256,
        "prepared_sha256": hashlib.sha256(prepared_bytes).hexdigest(),
        "protected_payload_sha256": protected_digest(items), "residual_temp_metadata": residual_metadata(items),
        "historical_cleanup": "saved_stopped_after_start_failure_true", "availability_before_preflight": "UNCONFIRMED",
        "preflight_server_and_port": "ABSENT_AT_OBSERVATION", "writes_performed": False,
    }


def require_repaired_source(source):
    if source.resolve() != REPAIRED_SOURCE.resolve() or not str(source.resolve()).lower().startswith("d:\\"):
        raise RecoveryError("FIXED_IMMUTABLE_REPAIRED_D_SOURCE_MISMATCH")
    require_exact_source(source, REPAIRED_COMMIT, REPAIRED_SOURCE_SHA256, "REPAIRED_SOURCE")
    return REPAIRED_SOURCE_SHA256


def require_reviewed_preflight(path, current):
    if REVIEWED_PREFLIGHT_RECEIPT_SHA256.startswith("PENDING_"):
        raise RecoveryError("REVIEWED_PREFLIGHT_RECEIPT_HASH_PENDING")
    if not re.fullmatch(r"[0-9a-f]{64}", REVIEWED_PREFLIGHT_RECEIPT_SHA256):
        raise RecoveryError("REVIEWED_PREFLIGHT_RECEIPT_HASH_FORMAT_INVALID")
    try:
        path.relative_to(PREFLIGHT_RECEIPT_ROOT)
        root = PREFLIGHT_RECEIPT_ROOT.resolve(strict=True)
    except (OSError, ValueError) as error:
        raise RecoveryError("PREFLIGHT_RECEIPT_OUTSIDE_FIXED_SCRATCH_ROOT") from error
    cursor = path
    while True:
        metadata = cursor.lstat()
        attributes = getattr(metadata, "st_file_attributes", 0)
        if stat.S_ISLNK(metadata.st_mode) or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise RecoveryError("PREFLIGHT_RECEIPT_REPARSE_PATH_UNSUPPORTED")
        if cursor == PREFLIGHT_RECEIPT_ROOT:
            break
        cursor = cursor.parent
    if path.resolve(strict=True).parent != root:
        raise RecoveryError("PREFLIGHT_RECEIPT_MUST_BE_DIRECT_CHILD")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != REVIEWED_PREFLIGHT_RECEIPT_SHA256:
        raise RecoveryError("REVIEWED_PREFLIGHT_RECEIPT_HASH_MISMATCH")
    try:
        recorded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RecoveryError("REVIEWED_PREFLIGHT_RECEIPT_INVALID") from error
    if recorded != current:
        raise RecoveryError("REVIEWED_PREFLIGHT_RECEIPT_DOES_NOT_BIND_FRESH_STATE")


def atomic_json(path, value, root):
    parent = path.parent
    ordinary(parent, root, True)
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    for delay in (None, .05, .1):
        if delay is not None:
            time.sleep(delay)
        try:
            os.replace(temporary, path)
            return
        except PermissionError as error:
            if getattr(error, "winerror", None) not in (5, 32, 33) or delay == .1:
                raise


def apply(root, failed_source, repaired_source, recovery_name, preflight_receipt):
    require_final_pins()
    if not RECOVERY_NAME.fullmatch(recovery_name):
        raise RecoveryError("RECOVERY_NAME_INVALID")
    before = preflight(root, failed_source)
    require_reviewed_preflight(preflight_receipt.resolve(), before)
    repaired_digest = require_repaired_source(repaired_source)
    items = layout(root)
    recovery_dir = items["state"] / recovery_name
    if recovery_dir.exists():
        raise RecoveryError("RECOVERY_EVIDENCE_DIRECTORY_ALREADY_EXISTS")
    # Preflight completed without writes. Evidence is created only after every
    # state/source guard has passed, immediately before the two-field rebind.
    recovery_dir.mkdir()
    ordinary(recovery_dir, root, True)
    original = read_json(items["prepared"])
    if hashlib.sha256(items["prepared"].read_bytes()).hexdigest() != before["prepared_sha256"]:
        raise RecoveryError("PREPARED_CHANGED_AFTER_PREFLIGHT_STOP")
    if protected_digest(items) != before["protected_payload_sha256"] or residual_metadata(items) != before["residual_temp_metadata"]:
        raise RecoveryError("PROTECTED_AGGREGATE_OR_RESIDUAL_EVIDENCE_CHANGED_STOP")
    updated = {**original, "source": str(repaired_source), "source_sha256": repaired_digest}
    atomic_json(items["prepared"], updated, root)
    after = read_json(items["prepared"])
    if (after.get("source") != str(repaired_source) or after.get("source_sha256") != repaired_digest
            or any(after.get(key) != value for key, value in original.items() if key not in {"source", "source_sha256"})):
        raise RecoveryError("PREPARED_CHANGED_OUTSIDE_SOURCE_FIELDS")
    if protected_digest(items) != before["protected_payload_sha256"] or residual_metadata(items) != before["residual_temp_metadata"]:
        raise RecoveryError("PROTECTED_AGGREGATE_OR_RESIDUAL_EVIDENCE_CHANGED")
    atomic_json(recovery_dir / "recovery-apply-receipt.json", {
        **before, "schema": "bos3.atomic-receipt-recovery.apply/v1", "at": datetime.now(timezone.utc).isoformat(),
        "repaired_source": str(repaired_source), "repaired_commit": REPAIRED_COMMIT,
        "repaired_source_sha256": repaired_digest, "repaired_version": REPAIRED_VERSION,
        "repair_review_sha256": REPAIR_REVIEW_SHA256, "root_recovery_go": ROOT_RECOVERY_GO,
        "prepared_fields_changed": ["source", "source_sha256"], "protected_payload_unchanged": True,
        "residual_temp_evidence_unchanged": True,
        "never_called": ["init", "seed", "migrate", "reset", "rollback", "acl", "kill", "stop", "start"],
    }, root)
    print(json.dumps({"updated": True, "recovery_dir": str(recovery_dir), "from": FAILED_COMMIT,
                      "to": REPAIRED_COMMIT, "native_lifecycle_calls": 0}, sort_keys=True))


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for command in (commands.add_parser("preflight"), commands.add_parser("apply")):
        command.add_argument("--root", type=Path, required=True)
        command.add_argument("--failed-source", type=Path, required=True)
    apply_command = commands.choices["apply"]
    apply_command.add_argument("--repaired-source", type=Path, required=True)
    apply_command.add_argument("--recovery-name", required=True)
    apply_command.add_argument("--preflight-receipt", type=Path, required=True)
    return result


if __name__ == "__main__":
    try:
        arguments = parser().parse_args()
        if arguments.command == "preflight":
            print(json.dumps(preflight(arguments.root.resolve(), arguments.failed_source.resolve()), sort_keys=True))
        else:
            apply(arguments.root.resolve(), arguments.failed_source.resolve(), arguments.repaired_source.resolve(),
                  arguments.recovery_name, arguments.preflight_receipt.resolve())
    except (RecoveryError, OSError, subprocess.SubprocessError) as error:
        print("BOS3_ATOMIC_RECEIPT_RECOVERY_REFUSED: " + str(error), file=sys.stderr)
        raise SystemExit(2)
