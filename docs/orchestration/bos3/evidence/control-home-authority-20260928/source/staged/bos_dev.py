#!/usr/bin/env python3
"""Local BOS task coordination. No model calls, Git writes, or automatic retries.

Paths in allowlists are repository-relative literal files/directories, not globs.
Claims are advisory: execute Git and tests in the lane's separate worktree.
Stale or blocked ownership requires an explicit, reasoned release by its owner.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid

ACTIVE = {"in_progress", "review", "blocked"}
LEGACY_CONTROL_HOME = Path(r"C:\Users\user\AppData\Local\BOSDev")
CONTROL_HOME = Path(r"D:\3\BOSDev\control-home")
AUTHORITY_ANCHOR = Path(r"D:\3\BOSDev\control-home-authority.json")
EVIDENCE_ROOT = Path(r"D:\3\BOSDev\evidence\bos3-control-home-install-20260928")
AUTHORITY_SCHEMA = "bos3.control-home-authority/v1"
_ANCHOR_FIELDS = {"schema", "generation", "phase", "home", "legacy_alias", "source_archive",
                  "root_identity", "lock_identity", "prepared_receipt", "migration_acceptance", "activated_at_utc"}
_SOURCE_ARCHIVE = Path(r"C:\Users\user\AppData\Local\BOSDev.pre-D-20260928")
_STATE_FILES = ("config.json", "queue.json", "observer.json", "codex-channel-delivery.json", ".queue.lock")


class CoordinationError(Exception):
    pass


class ControlHomeError(CoordinationError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def require(condition, message):
    if not condition:
        raise CoordinationError(message)


def _lexical_path(value):
    raw = str(value).replace("/", "\\")
    if (not re.fullmatch(r"[A-Za-z]:\\[^:]*", raw) or raw.startswith("\\\\")
            or any(part in (".", "..") or part.endswith((".", " "))
                   for part in raw.split("\\") if part)):
        raise ControlHomeError("Control home must be one approved absolute drive path.")
    return ntpath.normcase(ntpath.normpath(raw))


def _no_reparse_parents(path, *, allow_leaf_junction=False):
    if os.name != "nt":
        raise ControlHomeError("Native Windows file identity is required.")
    chain = list(reversed((path, *path.parents)))
    for part in chain:
        try:
            info = part.lstat()
        except OSError as exc:
            raise ControlHomeError(f"Required path is unavailable: {part}") from exc
        reparse = bool(getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        if reparse and not (allow_leaf_junction and part == path and _reparse_tag(part) == 0xA0000003):
            raise ControlHomeError(f"Unexpected reparse point: {part}")


def _reparse_tag(path):
    handle = _open_native(path, follow=False)
    try:
        kernel = ctypes.windll.kernel32
        kernel.DeviceIoControl.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID,
                                           wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                           ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID)
        kernel.DeviceIoControl.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        output = ctypes.create_string_buffer(16384)
        returned = wintypes.DWORD()
        if not kernel.DeviceIoControl(handle, 0x000900A8, None, 0,
                                      output, len(output), ctypes.byref(returned), None):
            raise ControlHomeError(f"Cannot inspect reparse tag: {path}")
        return int.from_bytes(output.raw[:4], "little")
    finally:
        kernel.CloseHandle(handle)


def _open_native(path, *, follow=True):
    kernel = ctypes.windll.kernel32
    kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    kernel.CreateFileW.restype = wintypes.HANDLE
    flags = 0x02000000 | (0 if follow else 0x00200000)
    handle = kernel.CreateFileW(str(path), 0, 0x00000007, None, 3, flags, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ControlHomeError(f"Cannot inspect native file identity: {path}")
    return handle


class _FileTime(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]


class _NativeInfo(ctypes.Structure):
    _fields_ = [("attributes", wintypes.DWORD), ("created", _FileTime), ("accessed", _FileTime),
                ("written", _FileTime), ("volume", wintypes.DWORD), ("size_high", wintypes.DWORD),
                ("size_low", wintypes.DWORD), ("links", wintypes.DWORD),
                ("index_high", wintypes.DWORD), ("index_low", wintypes.DWORD)]


def _identity(path=None, *, handle=None):
    kernel = ctypes.windll.kernel32
    kernel.GetFileInformationByHandle.argtypes = (wintypes.HANDLE, ctypes.POINTER(_NativeInfo))
    kernel.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    owned = handle is None
    native = _open_native(path) if owned else handle
    try:
        info = _NativeInfo()
        if not kernel.GetFileInformationByHandle(native, ctypes.byref(info)):
            raise ControlHomeError("Cannot read native file identity.")
        return ({"volume_id": f"{info.volume:08x}",
                 "file_id": f"{((info.index_high << 32) | info.index_low):016x}"}, info.links)
    finally:
        if owned:
            kernel.CloseHandle(native)


def _regular_file(path):
    _no_reparse_parents(path)
    try:
        info = path.lstat()
    except OSError as exc:
        raise ControlHomeError(f"Required file is unavailable: {path}") from exc
    if not stat.S_ISREG(info.st_mode) or _identity(path)[1] != 1:
        raise ControlHomeError(f"Required file is not a single-link regular file: {path}")


def _read_required_json(path):
    _regular_file(path)
    try:
        result = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ControlHomeError(f"Invalid required JSON: {path}") from exc
    if not isinstance(result, dict):
        raise ControlHomeError(f"Required JSON is not an object: {path}")
    return result


def _receipt(entry):
    if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
        raise ControlHomeError("Authority receipt reference is invalid.")
    name = _lexical_path(entry["path"])
    root = _lexical_path(EVIDENCE_ROOT)
    try:
        within_root = ntpath.commonpath((name, root)) == root
    except ValueError as exc:
        raise ControlHomeError("Authority receipt is on another drive.") from exc
    if not within_root or name == root:
        raise ControlHomeError("Authority receipt is outside the fixed evidence root.")
    if not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
        raise ControlHomeError("Authority receipt digest is invalid.")
    path = Path(name)
    _regular_file(path)
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ControlHomeError("Authority receipt became unreadable.") from exc
    if digest != entry["sha256"]:
        raise ControlHomeError("Authority receipt digest changed.")
    return path


def _authority():
    anchor = _read_required_json(AUTHORITY_ANCHOR)
    if set(anchor) != _ANCHOR_FIELDS or anchor["schema"] != AUTHORITY_SCHEMA or anchor["phase"] != "ACTIVE":
        raise ControlHomeError("Control home authority is absent or inactive.")
    try:
        generation = uuid.UUID(anchor["generation"])
    except (TypeError, ValueError, AttributeError) as exc:
        raise ControlHomeError("Authority generation is invalid.") from exc
    if str(generation) != anchor["generation"].lower():
        raise ControlHomeError("Authority generation is invalid.")
    for field, expected in (("home", CONTROL_HOME), ("legacy_alias", LEGACY_CONTROL_HOME),
                            ("source_archive", _SOURCE_ARCHIVE)):
        if not isinstance(anchor[field], str) or _lexical_path(anchor[field]) != _lexical_path(expected):
            raise ControlHomeError(f"Authority {field} changed.")
    stamp = anchor["activated_at_utc"]
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ControlHomeError("Authority activation timestamp is invalid.") from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ControlHomeError("Authority activation timestamp must be UTC.")
    _receipt(anchor["prepared_receipt"])
    accepted = _read_required_json(_receipt(anchor["migration_acceptance"]))
    if (accepted.get("verdict") != "ACCEPT_MIGRATION_COMMIT" or
            accepted.get("generation") != anchor["generation"] or
            accepted.get("prepared_receipt_sha256") != anchor["prepared_receipt"]["sha256"]):
        raise ControlHomeError("Migration acceptance does not bind this authority.")
    _no_reparse_parents(CONTROL_HOME)
    _no_reparse_parents(LEGACY_CONTROL_HOME, allow_leaf_junction=True)
    try:
        alias_target = LEGACY_CONTROL_HOME.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ControlHomeError("Legacy junction target is unavailable.") from exc
    if _reparse_tag(LEGACY_CONTROL_HOME) != 0xA0000003 or alias_target != CONTROL_HOME:
        raise ControlHomeError("Legacy address is not the exact target junction.")
    root_id, _ = _identity(CONTROL_HOME)
    alias_id, _ = _identity(LEGACY_CONTROL_HOME)
    if root_id != alias_id or root_id != anchor["root_identity"]:
        raise ControlHomeError("Control home root identity changed.")
    lock = CONTROL_HOME / ".queue.lock"
    _regular_file(lock)
    try:
        lock_size = lock.stat().st_size
    except OSError as exc:
        raise ControlHomeError("Control home lock became unavailable.") from exc
    if lock_size < 1 or _identity(lock)[0] != anchor["lock_identity"]:
        raise ControlHomeError("Control home lock identity changed.")
    if _identity(LEGACY_CONTROL_HOME / ".queue.lock")[0] != anchor["lock_identity"]:
        raise ControlHomeError("Legacy and target lock identities differ.")
    state = {}
    for name in _STATE_FILES[:-1]:
        state[name] = _read_required_json(CONTROL_HOME / name)
    if (state["config.json"].get("version") != 1 or
            not isinstance(state["config.json"].get("lanes"), dict) or
            state["queue.json"].get("version") != 1 or
            not isinstance(state["queue.json"].get("tasks"), dict) or
            state["codex-channel-delivery.json"].get("schema") != 1 or
            not isinstance(state["codex-channel-delivery.json"].get("messages"), dict)):
        raise ControlHomeError("Required control state format is invalid.")
    return anchor


def resolve_control_home(value=None):
    """Validate the ACTIVE physical authority and return its one D home."""
    requested = _lexical_path(CONTROL_HOME if value is None else value)
    if requested not in (_lexical_path(CONTROL_HOME), _lexical_path(LEGACY_CONTROL_HOME)):
        raise ControlHomeError("Only the fixed D home and exact C alias are accepted.")
    _authority()
    return CONTROL_HOME


@contextmanager
def state_lock(home, timeout=10):
    """Lock one persistent byte; never delete the file backing the OS lock."""
    home = resolve_control_home(home)
    before = _authority()
    try:
        handle = (home / ".queue.lock").open("r+b")
    except OSError as exc:
        raise ControlHomeError("Existing control home lock cannot be opened.") from exc
    with handle:
        import msvcrt
        try:
            native = msvcrt.get_osfhandle(handle.fileno())
        except OSError as exc:
            raise ControlHomeError("Opened lock handle is invalid.") from exc
        if _identity(handle=native)[0] != before["lock_identity"]:
            raise ControlHomeError("Opened lock identity differs from authority.")
        started = time.monotonic()
        while True:
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() - started >= timeout:
                    raise ControlHomeError("Timed out waiting for queue lock")
                time.sleep(0.05)
        try:
            after = _authority()
            if after != before or _identity(handle=native)[0] != after["lock_identity"]:
                raise ControlHomeError("Authority changed while acquiring the state lock.")
            yield
        finally:
            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError as exc:
                raise ControlHomeError("Control home lock could not be released.") from exc


def read_json(path):
    require(path.is_file(), f"Missing {path}; run init first")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        raise CoordinationError(f"Cannot read {path}: {exc}") from exc


def atomic_json(path, value):
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as handle:
            name = handle.name
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        name = None
    finally:
        if name is not None:
            Path(name).unlink(missing_ok=True)


def canonical_path(value):
    value = value.replace("\\", "/").strip()
    require(value and not value.startswith("/") and ":" not in value,
            "Allowlist paths must be repository-relative")
    require(not any(c in value for c in "*?[]"), "Use literal allowlist files/directories, not globs")
    parts = [p for p in value.split("/") if p and p != "."]
    require(".." not in parts, "Allowlist paths cannot escape the repository")
    return "/".join(parts).casefold() or "."


def overlaps(left, right):
    return left == "." or right == "." or left == right or left.startswith(right + "/") or right.startswith(left + "/")


def task_at(queue, task_id):
    require(task_id in queue["tasks"], f"Unknown task: {task_id}")
    return queue["tasks"][task_id]


def event(task, action, actor, **details):
    task["updated_at"] = utc_now()
    task["history"].append({"at": task["updated_at"], "action": action, "actor": actor, **details})


def owner_check(task, owner):
    require(task["status"] in ACTIVE, "Task has no active claim")
    require(task.get("owner") == owner, "Only the current owner can perform this action")


def evidence_path(value):
    path = Path(value).expanduser().resolve()
    require(path.is_file(), f"Evidence file does not exist: {path}")
    return str(path)


def initialize(home):
    home = resolve_control_home(home)
    _authority()
    return {"created": [], "home": str(home)}


def run(args):
    home = resolve_control_home(args.home)
    with state_lock(home, args.lock_timeout):
        if args.command == "init":
            return initialize(home)
        config = read_json(home / "config.json")
        queue = read_json(home / "queue.json")
        require(isinstance(config.get("lanes"), dict), "config.lanes must be an object")
        require(queue.get("version") == 1 and isinstance(queue.get("tasks"), dict),
                "Unsupported queue format")
        if args.command == "status":
            now = datetime.now(timezone.utc)
            stale_after = config.get("stale_after_seconds", 3600)
            tasks = []
            for original in queue["tasks"].values():
                task = dict(original)
                task["stale_claim"] = False
                if task["status"] in ACTIVE:
                    last = datetime.fromisoformat(task["heartbeat_at"])
                    task["seconds_since_heartbeat"] = max(0, int((now - last).total_seconds()))
                    task["stale_claim"] = task["seconds_since_heartbeat"] >= stale_after
                tasks.append(task)
            return {"home": str(home), "lanes": config["lanes"], "tasks": tasks,
                    "external_owners": config.get("external_owners", []),
                    "stale_policy": "Inspect worktree and process state; never automatically release a stale claim."}
        if args.command == "add":
            require(not config.get("require_base_sha") or args.base_sha,
                    "This coordinator requires an explicit source base SHA")
            require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", args.task) is not None,
                    "Task ID must use 1-100 letters, digits, dots, hyphens or underscores")
            require(args.task not in queue["tasks"], "Task ID already exists")
            require(args.lane in config["lanes"], f"Unknown lane: {args.lane}")
            for dependency in args.depends:
                require(dependency in queue["tasks"], f"Dependency must already exist: {dependency}")
            if args.base_sha:
                require(re.fullmatch(r"[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", args.base_sha) is not None,
                        "Base SHA must be a full 40- or 64-character Git commit ID")
            task = {"id": args.task, "title": args.title, "lane": args.lane,
                    "allowlist": sorted(set(canonical_path(p) for p in args.allowlist)),
                    "dependencies": sorted(set(args.depends)), "status": "pending", "owner": None,
                    "created_at": utc_now(), "history": [], "progress": ""}
            if args.base_sha:
                task["base_sha"] = args.base_sha.lower()
            event(task, "add", "orchestrator")
            queue["tasks"][args.task] = task
        else:
            task = task_at(queue, args.task)
            if args.command == "claim":
                require(task["status"] == "pending", f"Task is {task['status']}, not pending")
                require(args.owner.strip(), "Owner cannot be empty")
                incomplete = [d for d in task["dependencies"] if task_at(queue, d)["status"] != "accepted"]
                require(not incomplete, f"Incomplete dependencies: {', '.join(incomplete)}")
                for external in config.get("external_owners", []):
                    if external.get("status") not in ACTIVE:
                        continue
                    conflicts = [(a, b) for a in task["allowlist"]
                                 for b in external.get("allowlist", []) if overlaps(a, canonical_path(b))]
                    require(not conflicts,
                            f"Allowlist overlaps external owner {external['id']}: {conflicts}")
                if config.get("require_base_sha"):
                    require(task.get("base_sha"), "Task has no source base SHA")
                    worktree = config["lanes"][task["lane"]]["worktree"]
                    result = subprocess.run([config.get("git_executable", "git"), "rev-parse", "HEAD"],
                                            cwd=worktree, capture_output=True, text=True, timeout=20)
                    require(result.returncode == 0, "Cannot resolve lane HEAD; synchronize before claiming")
                    require(result.stdout.strip().lower() == task["base_sha"].lower(),
                            "Lane HEAD differs from task base SHA; synchronize before claiming")
                for other in queue["tasks"].values():
                    if other["id"] == task["id"] or other["status"] not in ACTIVE:
                        continue
                    require(other["lane"] != task["lane"], f"Lane already occupied by {other['id']}")
                    conflicts = [(a, b) for a in task["allowlist"] for b in other["allowlist"] if overlaps(a, b)]
                    require(not conflicts, f"Allowlist overlaps active task {other['id']}: {conflicts}")
                task.update(status="in_progress", owner=args.owner, heartbeat_at=utc_now(),
                            worktree=config["lanes"][task["lane"]].get("worktree"))
                task.pop("block_reason", None)
                task.pop("submission_evidence", None)
                event(task, "claim", args.owner)
            elif args.command in {"heartbeat", "progress"}:
                owner_check(task, args.owner)
                task["heartbeat_at"] = utc_now()
                if args.message is not None:
                    task["progress"] = args.message
                event(task, args.command, args.owner, message=args.message)
            elif args.command == "submit":
                owner_check(task, args.owner)
                require(task["status"] == "in_progress", "Only in-progress tasks can be submitted")
                evidence = evidence_path(args.evidence)
                task.update(status="review", submission_evidence=evidence, heartbeat_at=utc_now())
                event(task, "submit", args.owner, evidence=evidence)
            elif args.command == "accept":
                require(task["status"] == "review", "Only submitted tasks can be accepted")
                require(args.reviewer.strip(), "Reviewer cannot be empty")
                require(args.reviewer.strip().casefold() != task["owner"].strip().casefold(),
                        "Author cannot approve their own result")
                evidence_path(task["submission_evidence"])
                evidence = evidence_path(args.evidence)
                task.update(status="accepted", reviewer=args.reviewer, review_evidence=evidence,
                            accepted_at=utc_now())
                event(task, "accept", args.reviewer, evidence=evidence)
            elif args.command == "block":
                owner_check(task, args.owner)
                require(args.reason.strip(), "Blocking reason cannot be empty")
                task.update(status="blocked", block_reason=args.reason, heartbeat_at=utc_now())
                event(task, "block", args.owner, reason=args.reason)
            elif args.command == "release":
                owner_check(task, args.owner)
                require(args.reason.strip(), "Release reason cannot be empty")
                event(task, "release", args.owner, reason=args.reason)
                task.update(status="pending", last_owner=task["owner"], owner=None)
                task.pop("block_reason", None)
        atomic_json(home / "queue.json", queue)
        return {"task": task}


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--home", default=str(CONTROL_HOME), help="Authoritative D control home or exact C alias")
    root.add_argument("--lock-timeout", type=float, default=10, help="Seconds to wait for the process lock")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create config and queue only if absent; never reset state")
    commands.add_parser("status", help="Read tasks and report stale claims without changing state")
    add = commands.add_parser("add", help="Add a pending task; all dependencies must already exist")
    add.add_argument("task")
    add.add_argument("--title", required=True)
    add.add_argument("--lane", required=True)
    add.add_argument("--allowlist", required=True, nargs="+", help="Literal repo-relative files/directories; '.' claims whole repo")
    add.add_argument("--depends", nargs="*", default=[])
    add.add_argument("--base-sha", help="Full source commit ID for traceable review")
    for command, help_text in {
        "claim": "Claim a task atomically after dependency/lane/path checks",
        "heartbeat": "Refresh ownership heartbeat (does not unblock a task)",
        "progress": "Record current progress and refresh heartbeat",
        "submit": "Submit existing evidence for independent review; retain lane ownership",
        "block": "Record a blocker; retain ownership until an explicit release",
        "release": "Explicitly return a claim to pending after inspecting its worktree",
    }.items():
        sub = commands.add_parser(command, help=help_text)
        sub.add_argument("task")
        sub.add_argument("--owner", required=True)
        if command in {"heartbeat", "progress"}:
            sub.add_argument("--message", required=command == "progress")
        elif command == "submit":
            sub.add_argument("--evidence", required=True)
        elif command in {"block", "release"}:
            sub.add_argument("--reason", required=True)
    accept = commands.add_parser("accept", help="Record acceptance by a reviewer other than the author")
    accept.add_argument("task")
    accept.add_argument("--reviewer", required=True)
    accept.add_argument("--evidence", required=True)
    return root


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        result = run(parser().parse_args())
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        return 0
    except (CoordinationError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
