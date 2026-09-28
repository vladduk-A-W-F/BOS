"""Source-bound one-shot QA guard. An independently reviewed admission is required."""
import datetime as dt
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

ROOT = Path(r"D:\3\BOSDev\qa-scratch\bos3-control-home-install-20260928")
ADMISSION = ROOT / "QA_ADMISSION.json"
OUTPUT = ROOT / "qa-attempt1"
PYTHON = Path(r"D:\3\BOSDev\venv\Scripts\python.exe")
CUTOFF = dt.datetime(2026, 10, 4, 21, 59, tzinfo=dt.timezone.utc)
GROUPS = {
    "source/staged/test-control-home-authority.py": [
        "AuthorityTests.test_active_default_alias_and_target_share_identity",
        "AuthorityTests.test_missing_prepared_and_invalid_authority_refuse",
        "AuthorityTests.test_missing_tampered_and_cross_drive_receipts_refuse",
        "AuthorityTests.test_receipt_acceptance_must_bind_generation_and_hash",
        "AuthorityTests.test_missing_or_tampered_acceptance_refuses",
        "AuthorityTests.test_unlisted_and_escaping_names_refuse",
        "AuthorityTests.test_missing_ledger_or_lock_refuses_before_transport",
        "AuthorityTests.test_invalid_ledger_refuses_before_transport",
        "AuthorityTests.test_existing_lock_is_not_recreated_by_init",
        "AuthorityTests.test_replaced_lock_identity_refuses",
        "AuthorityTests.test_generation_change_after_byte_acquisition_releases_lock",
        "AuthorityTests.test_hardlink_state_and_reparse_root_refuse",
        "AuthorityTests.test_transferred_delivery_and_opaque_record_are_preserved",
        "AuthorityTests.test_incomplete_relevant_record_refuses_without_send",
        "AuthorityTests.test_two_processes_compete_for_one_byte_lock",
    ],
    "consumers/staged/test-control-home-consumers.py": [
        "ConsumerAuthorityTests.test_exact_scratch_origin",
        "ConsumerAuthorityTests.test_missing_provider_never_uses_setup_fallback",
        "ConsumerAuthorityTests.test_missing_channel_never_uses_setup_fallback",
        "ConsumerAuthorityTests.test_foreign_cached_provider_refused",
        "ConsumerAuthorityTests.test_hardlinked_provider_refused",
        "ConsumerAuthorityTests.test_reparse_provider_refused_when_fixture_available",
        "ConsumerAuthorityTests.test_second_authority_failure_has_no_health_output",
        "ConsumerAuthorityTests.test_flow_refusal_precedes_explicit_fake_transport",
        "ConsumerAuthorityTests.test_local_flow_selected_home_output_refusal",
    ],
}


def checked_path(path, *, file=False):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise RuntimeError("Only ordinary absolute paths are allowed")
    for part in reversed((path, *path.parents)):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Reparse path refused: " + str(part))
    info = path.stat()
    if file and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
        raise RuntimeError("Expected a regular single-link file: " + str(path))
    return path


def digest(path):
    return hashlib.sha256(checked_path(path, file=True).read_bytes()).hexdigest()


def create_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as out:
        json.dump(value, out, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())


def contain_test_children():
    class BasicLimits(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t),
                    ("maximum", ctypes.c_size_t), ("active_limit", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in
                    ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("basic", BasicLimits), ("io", IoCounters),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000  # Kill only this guard and its descendants when the process closes the job handle.
    if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        error = ctypes.get_last_error()
        kernel.CloseHandle(job)
        raise ctypes.WinError(error)
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        error = ctypes.get_last_error()
        kernel.CloseHandle(job)
        raise ctypes.WinError(error)
    # Keep the non-inheritable handle open until OS process teardown. No existing process is assigned.
    return job


def main():
    if os.name != "nt" or dt.datetime.now(dt.timezone.utc) >= CUTOFF:
        raise RuntimeError("Windows and unexpired cutoff required")
    checked_path(ROOT)
    checked_path(PYTHON, file=True)
    checked_path(Path(__file__), file=True)
    admission = json.loads(checked_path(ADMISSION, file=True).read_text(encoding="utf-8"))
    if (admission.get("schema") != "bos3.control-home-focused-qa-admission/v1"
            or admission.get("operator") != "root"
            or admission.get("maximum_invocations") != 1
            or admission.get("groups") != GROUPS
            or admission.get("runner_sha256") != digest(__file__)):
        raise RuntimeError("Admission does not match this exact runner/scope")
    review = admission["independent_review"]
    review_path = ROOT / review["relative_path"]
    if not review_path.is_relative_to(ROOT) or ".." in review_path.parts:
        raise RuntimeError("Review path outside scratch")
    if digest(review_path) != review["sha256"]:
        raise RuntimeError("Independent execution review digest mismatch")
    pins = admission["pins"]
    required = set(GROUPS) | {"source/staged/bos_dev.py", "source/staged/codex_channel.py",
                             "consumers/staged/bos_flow.py", "consumers/staged/local_flow.py",
                             "consumers/staged/repo_health.py"}
    if not required.issubset(pins):
        raise RuntimeError("Missing execution dependency pins")
    for name, expected in pins.items():
        path = ROOT / name
        if not path.is_relative_to(ROOT) or ".." in path.parts or digest(path) != expected:
            raise RuntimeError("Input mismatch: " + name)
    if OUTPUT.exists():
        raise RuntimeError("Attempt directory already exists; automatic retry refused")
    OUTPUT.mkdir()
    create_json(OUTPUT / "INVOKED.json", {
        "admission_sha256": digest(ADMISSION), "runner_sha256": digest(__file__),
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "maximum_invocations": 1, "automatic_retry": False, "pins": pins,
    })
    result = {"groups": [], "status": "INCOMPLETE", "application_checks": 0,
              "installation": False, "phase_fault_qa": "NOT_RUN", "automatic_retry": False}
    started = time.monotonic()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"}
    env.pop("PYTHONPATH", None)
    try:
        job_handle = contain_test_children()
        result["test_descendants_contained"] = bool(job_handle)
        for index, (name, methods) in enumerate(GROUPS.items(), 1):
            if dt.datetime.now(dt.timezone.utc) >= CUTOFF:
                raise RuntimeError("Cutoff reached before next group")
            remaining = 60 - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("Shared 60-second test budget exhausted")
            args = [str(PYTHON), "-I", "-S", "-B", str(ROOT / name), *methods, "-v"]
            entry = {"file": name, "methods": methods, "args": args, "native_exit": None}
            result["groups"].append(entry)
            try:
                run = subprocess.run(args, cwd=ROOT, env=env, capture_output=True,
                                     timeout=remaining, check=False)
                out, err = run.stdout, run.stderr
                entry["native_exit"] = run.returncode
            except subprocess.TimeoutExpired as exc:
                out, err = exc.stdout or b"", exc.stderr or b""
                entry["status"] = "TIMEOUT_NATIVE_EXIT_UNCONFIRMED"
            for suffix, data in (("stdout", out), ("stderr", err)):
                with (OUTPUT / (str(index) + "-" + suffix + ".bin")).open("xb") as log:
                    log.write(data)
            if entry["native_exit"] != 0:
                result["status"] = "FAILED_OR_INCOMPLETE_STOPPED"
                break
        else:
            result["status"] = "NATIVE_ZERO_REQUIRES_INDEPENDENT_OUTPUT_REVIEW"
        result["input_hashes_unchanged"] = all(digest(ROOT / n) == h for n, h in pins.items())
        if not result["input_hashes_unchanged"]:
            result["status"] = "INPUT_CHANGED_NOT_ACCEPTABLE"
    except Exception as exc:
        result["status"] = "GUARD_OR_EXECUTION_ERROR"
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        result["elapsed_seconds"] = time.monotonic() - started
        create_json(OUTPUT / "RESULT.json", result)
    print(json.dumps({"status": result["status"], "receipt": str(OUTPUT / "RESULT.json")}))
    return 0 if result["status"] == "NATIVE_ZERO_REQUIRES_INDEPENDENT_OUTPUT_REVIEW" else 2


if __name__ == "__main__":
    sys.exit(main())
