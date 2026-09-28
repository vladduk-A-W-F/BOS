"""One-GET recovery proof, separately authorized after an official start."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

import recovery_source_prepare_template as recovery


FAILED_PROTECTED_BASELINE_SHA256 = "dfcbaefab3f5a63e929b49f11d2f5425019834c9bad6e66b0a3e4fd3a938efa1"
FAILED_BASELINE_ARCHIVE = "maintenance-INVOICE-DEV8-D-20260928-window1"
RUNTIME_IMAGE = "c:/users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"


class VerificationError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


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
        if not self.kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
            raise VerificationError("READY_PROCESS_TIMES_UNAVAILABLE")
        size = wintypes.DWORD(32768)
        image = ctypes.create_unicode_buffer(size.value)
        if not self.kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            raise VerificationError("READY_PROCESS_IMAGE_UNAVAILABLE")
        return {"pid": pid, "created_ticks": (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime,
                "image": str(Path(image.value).resolve()).replace("\\", "/").lower()}

    def close(self, handle):
        if handle:
            self.kernel.CloseHandle(handle)


def normalized_newlines(value):
    return value.replace("\r\n", "\n").replace("\r", "\n")


def command_line(pid):
    powershell, environment = recovery.native_powershell_environment()
    command = ('$p=Get-CimInstance Win32_Process -Filter "ProcessId = ' + str(pid)
               + '"; if ($null -ne $p) {[Console]::Out.Write($p.CommandLine)}')
    result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", command], env=environment,
                            capture_output=True, text=True, encoding="utf-8", timeout=15)
    if result.returncode:
        raise VerificationError("READY_PROCESS_COMMAND_UNAVAILABLE")
    return result.stdout


def listener_pid(port):
    powershell, environment = recovery.native_powershell_environment()
    command = ('$listeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -eq '
               + str(port) + " }); if ($listeners.Count -eq 1 -and ($listeners[0].LocalAddress -eq '127.0.0.1' "
               + "-or $listeners[0].LocalAddress -eq '::1')) {[Console]::Out.Write($listeners[0].OwningProcess)} "
               + 'elseif ($listeners.Count -gt 0) { exit 2 }')
    result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", command], env=environment,
                            capture_output=True, text=True, encoding="utf-8", timeout=15)
    if result.returncode or not result.stdout.strip().isdigit():
        raise VerificationError("READY_LISTENER_IDENTITY_UNAVAILABLE")
    return int(result.stdout.strip())


def require_ready_receipt(items, source, digest):
    recovery.ordinary(items["process"], items["root"], False)
    receipt = recovery.read_json(items["process"])
    record = receipt.get("process")
    tokens = receipt.get("required_tokens")
    if (receipt.get("status") != "ready" or receipt.get("source") != str(source)
            or receipt.get("source_sha256") != digest or receipt.get("port") != recovery.RUNTIME_PORT
            or receipt.get("runtime_image") != RUNTIME_IMAGE or not isinstance(record, dict)
            or not isinstance(record.get("pid"), int) or not isinstance(tokens, list)):
        raise VerificationError("READY_RECEIPT_BINDING_MISMATCH")
    operations = WindowsProcess()
    handle = operations.open(record["pid"])
    if handle is None:
        raise VerificationError("READY_PROCESS_NOT_OPENABLE")
    try:
        if operations.identity(handle, record["pid"]) != record or record.get("image") != RUNTIME_IMAGE:
            raise VerificationError("READY_PROCESS_IDENTITY_MISMATCH")
    finally:
        operations.close(handle)
    if any(not isinstance(token, str) or token not in command_line(record["pid"]) for token in tokens):
        raise VerificationError("READY_PROCESS_COMMAND_MISMATCH")
    if listener_pid(recovery.RUNTIME_PORT) != record["pid"]:
        raise VerificationError("READY_LISTENER_PID_MISMATCH")
    return receipt


def one_exact_get():
    url = "http://127.0.0.1:" + str(recovery.RUNTIME_PORT) + "/"
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(Request(url, headers={"Accept": "text/html"}), timeout=5) as response:
            if response.status != 200 or response.geturl() != url:
                raise VerificationError("LOOPBACK_HTTP_NOT_EXACT_200")
            return url, response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError) as error:
        raise VerificationError("ONE_BOUNDED_LOOPBACK_GET_FAILED") from error


def verify(root, repaired_source, recovery_name):
    recovery.require_final_pins()
    # Reject aliases before any owner-root reads, then inspect the fixed root's
    # own components for symlink/reparse indirection.
    if root != recovery.INSTANCE_ROOT or repaired_source != recovery.REPAIRED_SOURCE:
        raise VerificationError("FIXED_OWNER_ROOT_OR_REPAIRED_SOURCE_ALIAS_MISMATCH")
    recovery.ordinary(recovery.INSTANCE_ROOT, recovery.INSTANCE_ROOT, True)
    if not recovery.RECOVERY_NAME.fullmatch(recovery_name):
        raise VerificationError("RECOVERY_NAME_INVALID")
    digest = recovery.require_repaired_source(repaired_source)
    items = recovery.layout(recovery.INSTANCE_ROOT)
    for key in ("state", "prepared", "data", "media", "access", "secrets"):
        recovery.ordinary(items[key], items["root"], key in {"state", "data", "media"})
    recovery_dir = items["state"] / recovery_name
    recovery.ordinary(recovery_dir, items["root"], True)
    failed_baseline_path = items["state"] / FAILED_BASELINE_ARCHIVE / "started-attestation.json"
    recovery.ordinary(failed_baseline_path, items["root"], False)
    failed_baseline = recovery.read_json(failed_baseline_path)
    if failed_baseline.get("protected_payload_sha256") != FAILED_PROTECTED_BASELINE_SHA256:
        raise VerificationError("SAVED_FAILED_BASELINE_RECEIPT_MISMATCH")
    apply_receipt = recovery.read_json(recovery_dir / "recovery-apply-receipt.json")
    native_receipt_path = recovery_dir / "official-start.native-exit.json"
    recovery.ordinary(native_receipt_path, items["root"], False)
    native_receipt = recovery.read_json(native_receipt_path)
    if (apply_receipt.get("repaired_source") != str(repaired_source) or apply_receipt.get("repaired_source_sha256") != digest
            or apply_receipt.get("protected_payload_unchanged") is not True
            or apply_receipt.get("residual_temp_evidence_unchanged") is not True):
        raise VerificationError("RECOVERY_APPLY_RECEIPT_MISMATCH")
    if (native_receipt.get("status") != "NATIVE_EXIT_CAPTURED" or native_receipt.get("native_exit") != 0
            or native_receipt.get("source") != str(repaired_source) or native_receipt.get("root") != str(root)
            or native_receipt.get("expected_commit") != recovery.REPAIRED_COMMIT
            or native_receipt.get("expected_source_sha256") != digest):
        raise VerificationError("OFFICIAL_START_NATIVE_EXIT_RECEIPT_MISMATCH")
    prepared = recovery.read_json(items["prepared"])
    if prepared.get("source") != str(repaired_source) or prepared.get("source_sha256") != digest:
        raise VerificationError("PREPARED_REPAIRED_SOURCE_MISMATCH")
    protected_before = recovery.protected_digest(items)
    residual_before = recovery.residual_metadata(items)
    if (protected_before != FAILED_PROTECTED_BASELINE_SHA256
            or protected_before != apply_receipt.get("protected_payload_sha256")
            or residual_before != apply_receipt.get("residual_temp_metadata")):
        raise VerificationError("FAILED_BASELINE_OR_APPLY_AGGREGATE_MISMATCH")
    ready = require_ready_receipt(items, repaired_source, digest)
    template = (repaired_source / "frontend" / "boss_app_html.html").read_text(encoding="utf-8")
    if template.count("{{ bos_version }}") != 1:
        raise VerificationError("COMMITTED_HTML_VERSION_TOKEN_MISMATCH")
    expected_html = normalized_newlines(template.replace("{{ bos_version }}", recovery.REPAIRED_VERSION))
    url, served_html = one_exact_get()
    normalized_served = normalized_newlines(served_html)
    if normalized_served != expected_html:
        raise VerificationError("ONE_HTTP_RESPONSE_DIFFERS_FROM_COMMITTED_HTML")
    protected_after = recovery.protected_digest(items)
    residual_after = recovery.residual_metadata(items)
    if protected_after != protected_before or residual_after != residual_before:
        raise VerificationError("AGGREGATE_OR_RESIDUAL_EVIDENCE_CHANGED_DURING_ONE_GET")
    print(json.dumps({
        "schema": "bos3.atomic-receipt-recovery.post-start/v2", "url": url, "http_status": 200,
        "source_commit": recovery.REPAIRED_COMMIT, "source_sha256": digest,
        "repaired_version": recovery.REPAIRED_VERSION, "process_identity": ready["process"],
        "official_start_native_exit": 0,
        "protected_algorithm": "data/media path-plus-bytes and owner-access/runtime-secrets path-plus-bytes",
        "failed_protected_baseline_sha256": FAILED_PROTECTED_BASELINE_SHA256,
        "failed_baseline_receipt": str(failed_baseline_path),
        "protected_payload_sha256_before_get": protected_before, "protected_payload_sha256_after_get": protected_after,
        "residual_temp_metadata_matches_apply_before_and_after": True,
        "expected_html_sha256": hashlib.sha256(expected_html.encode("utf-8")).hexdigest(),
        "served_html_sha256": hashlib.sha256(normalized_served.encode("utf-8")).hexdigest(),
        "writes_performed": False, "http_requests": 1, "retries_performed": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--repaired-source", type=Path, required=True)
    parser.add_argument("--recovery-name", required=True)
    try:
        arguments = parser.parse_args()
        verify(arguments.root, arguments.repaired_source, arguments.recovery_name)
    except (recovery.RecoveryError, VerificationError, OSError, subprocess.SubprocessError) as error:
        print("BOS3_ATOMIC_RECEIPT_POST_START_REFUSED: " + str(error), file=sys.stderr)
        raise SystemExit(2)
