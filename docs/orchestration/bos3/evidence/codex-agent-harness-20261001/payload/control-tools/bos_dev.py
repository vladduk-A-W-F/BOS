#!/usr/bin/env python3
"""Local BOS task coordination. No model calls, Git writes, or automatic retries.

Paths in allowlists are repository-relative literal files/directories, not globs.
Claims are advisory: execute Git and tests in the lane's separate worktree.
Stale or blocked ownership requires an explicit, reasoned release by its owner.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ACTIVE = {"in_progress", "review", "blocked"}


class CoordinationError(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def require(condition, message):
    if not condition:
        raise CoordinationError(message)


@contextmanager
def state_lock(home, timeout=10):
    """Lock one persistent byte; never delete the file backing the OS lock."""
    home.mkdir(parents=True, exist_ok=True)
    with (home / ".queue.lock").open("a+b") as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
        started = time.monotonic()
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() - started >= timeout:
                    raise CoordinationError("Timed out waiting for queue lock")
                time.sleep(0.05)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
    root = Path("D:/3/BOSDev/worktrees")
    created = []
    config = home / "config.json"
    queue = home / "queue.json"
    if not config.exists():
        atomic_json(config, {"version": 1, "stale_after_seconds": 3600,
                             "lanes": {lane: {"worktree": str(root / lane)}
                                       for lane in ("backend", "frontend", "review")}})
        created.append(str(config))
    if not queue.exists():
        atomic_json(queue, {"version": 1, "tasks": {}})
        created.append(str(queue))
    return {"created": created, "home": str(home)}


def run(args):
    home = Path(args.home).expanduser().resolve()
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
    default_home = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "BOSDev"
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--home", default=str(default_home), help="Coordination directory (default: LOCALAPPDATA/BOSDev)")
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
