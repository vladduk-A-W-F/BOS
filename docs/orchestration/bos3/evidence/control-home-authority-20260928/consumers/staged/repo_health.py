"""Read-only health report over local and saved GitHub snapshots; no product authority."""
from __future__ import annotations

import argparse
from collections import Counter
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import types

DEFAULT_HOME = Path("D:/3/BOSDev/control-home")
DEFAULT_ROOT = Path("D:/3/BOSDev")
TOOLS = DEFAULT_HOME / "tools"


def load_control_module(name):
    if name != 'bos_dev':
        raise RuntimeError('Unsupported control module')
    path = TOOLS / (name + '.py')
    for parent in (TOOLS, *TOOLS.parents):
        if parent == parent.parent:
            break
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise RuntimeError('Control tools parent is not an ordinary directory')
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or getattr(before, 'st_file_attributes', 0) & 0x400):
        raise RuntimeError('Control module is not a single-link regular file')
    kernel = ctypes.windll.kernel32
    kernel.CreateFileW.argtypes = (ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                   ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p)
    kernel.CreateFileW.restype = ctypes.c_void_p
    handle = kernel.CreateFileW(str(path), 0x80000000, 7, None, 3, 0x00200000, None)
    if handle in (None, ctypes.c_void_p(-1).value):
        raise RuntimeError('Cannot open exact control module')
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(ctypes.c_void_p(handle))
        raise
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or getattr(opened, 'st_file_attributes', 0) & 0x400
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
            raise RuntimeError('Control module changed or redirected during open')
        raw = stream.read()
    digest = hashlib.sha256(raw).hexdigest()
    cached = sys.modules.get(name)
    if cached is not None:
        if (getattr(cached, '__bos_fixed_source__', None) != (str(path), digest)
                or getattr(cached, '__file__', None) != str(path)):
            raise RuntimeError('Foreign cached control module')
        return cached
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__bos_fixed_source__ = (str(path), digest)
    sys.modules[name] = module
    try:
        exec(compile(raw.decode('utf-8-sig'), str(path), 'exec'), module.__dict__)
    except BaseException:
        del sys.modules[name]
        raise
    return module


_provider = load_control_module('bos_dev')
resolve_control_home = _provider.resolve_control_home
state_lock = _provider.state_lock
REMOTE_MAX_AGE = 90 * 60
PENDING = {"queued", "pending", "requested", "waiting", "in_progress"}
BAD_CONCLUSIONS = {"failure", "cancelled", "timed_out", "action_required"}


def parse_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
    except ValueError:
        return None


def read_json_once(path):
    raw = Path(path).read_bytes()
    parsed = json.loads(raw.decode("utf-8-sig"))
    return parsed, hashlib.sha256(raw).hexdigest()


def tasks_shape(queue):
    if not isinstance(queue, dict) or "tasks" not in queue:
        return [], "tasks_missing_or_queue_not_object"
    data = queue["tasks"]
    if isinstance(data, dict):
        pairs = [(str(key), value) for key, value in data.items()]
    elif isinstance(data, list):
        pairs = [(str(item.get("id", "")), item) if isinstance(item, dict) else ("", item) for item in data]
    else:
        return [], "tasks_not_list_or_object"
    if not pairs:
        return [], "tasks_empty"
    if any(not isinstance(item, dict) for _, item in pairs):
        return pairs, "task_entry_not_object"
    return pairs, None


def check_queue(queue):
    pairs, malformed = tasks_shape(queue)
    original_count = len(pairs)
    pairs = [(key, task) for key, task in pairs if isinstance(task, dict)]
    ids, errors = [], []
    for key, task in pairs:
        ident = task.get("id") or (key if key else None)
        if not isinstance(ident, str) or not ident.strip():
            errors.append("task_id_missing")
            continue
        ids.append(ident)
        if not task.get("owner") or not task.get("status"):
            errors.append(ident + ":owner_or_status_missing")
        deps = task.get("depends_on", task.get("dependencies", []))
        if not isinstance(deps, list) or any(not isinstance(x, str) or not x for x in deps):
            errors.append(ident + ":dependencies_malformed")
    known = set(ids)
    duplicates = sorted(x for x, count in Counter(ids).items() if count > 1)
    missing, graph = [], {}
    for key, task in pairs:
        if not isinstance(task, dict):
            continue
        ident = task.get("id") or (key if key else None)
        deps = task.get("depends_on", task.get("dependencies", []))
        if not isinstance(deps, list):
            continue
        for dep in deps:
            if isinstance(dep, str) and dep not in known:
                missing.append(f"{ident or '?'}->{dep}")
        if ident:
            graph[str(ident)] = [d for d in deps if isinstance(d, str) and d in known]
    visiting, done, cyclic = set(), set(), set()

    def visit(node, trail):
        if node in visiting:
            cyclic.update(trail[trail.index(node):] if node in trail else [node])
            return
        if node in done:
            return
        visiting.add(node)
        for child in graph.get(node, []):
            visit(child, trail + [child])
        visiting.remove(node)
        done.add(node)

    for node in graph:
        visit(node, [node])
    return {"task_count": original_count, "malformed": malformed,
        "duplicate_ids": duplicates, "missing_dependency_ids": sorted(set(missing)),
        "cycle_members": sorted(cyclic), "field_errors": sorted(set(errors))}


def safe_ref(snapshot, value):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError("reference_not_absolute")
    target = Path(value).resolve()
    if target.parent != Path(snapshot).resolve().parent:
        raise ValueError("reference_outside_snapshot_directory")
    return target


def read_git(executable, path):
    try:
        def run(*args):
            return subprocess.run([str(executable), "--no-optional-locks", "-C", str(path), *args],
                check=True, capture_output=True, text=True, timeout=20).stdout
        return {"path": str(path), "head": run("rev-parse", "HEAD").strip(),
                "dirty": bool(run("status", "--porcelain", "-z")), "error": None}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"path": str(path), "head": None, "dirty": None, "error": type(exc).__name__}


def actor_summary(config, observer, index, now, stale_after):
    channel = observer.get("control_channel") or {}
    if not isinstance(channel, dict):
        channel = {}
    indexed = index.get("actors") if isinstance(index.get("actors"), dict) else {}
    expected = {"main": config.get("orchestrator_thread_id") or observer.get("main_thread_id"),
        "writer": config.get("canonical_writer_thread_id"),
        "design": observer.get("design_thread_id"),
        "quality": observer.get("quality_thread_id")}
    result = {}
    for role, thread_id in expected.items():
        snap = channel.get(role + "_snapshot")
        if not isinstance(snap, dict):
            snap = indexed.get(role) if isinstance(indexed.get(role), dict) else {}
        checked = parse_time(snap.get("checked_at_utc"))
        age = (now - checked).total_seconds() if checked else None
        fresh = age is not None and 0 <= age <= stale_after
        errors = any(snap.get(k) not in (None, "", False, [], {}) for k in
                     ("fresh_status_error", "turn_error", "errors", "error"))
        matches = bool(thread_id and snap.get("thread_id") == thread_id)
        status, turn = snap.get("status"), snap.get("turn_status")
        idle = fresh and not errors and matches and status == "idle" and turn == "completed"
        busy = fresh and not errors and matches and status == "active" and turn in ("inProgress", "in_progress")
        result[role] = {"thread_id": snap.get("thread_id"), "expected_thread_id": thread_id,
            "checked_at_utc": snap.get("checked_at_utc"), "status": status or "unknown",
            "turn_status": turn or "unknown", "fresh": fresh, "errors_present": errors,
            "thread_matches": matches,
            "availability": ("reported_idle" if idle else "reported_busy" if busy
                             else "not_free_or_unknown")}
    return result


def ci_check(github, now, add):
    if not isinstance(github, dict):
        add("github_malformed", "incomplete", "GitHub snapshot is not an object.")
        return {"runs_count": 0, "mismatches": [], "incomplete": [], "nonpassing": [], "skipped": []}
    checked = parse_time(github.get("checked_at_utc"))
    if checked is None or (now - checked).total_seconds() > REMOTE_MAX_AGE:
        add("github_needs_refresh", "needs_refresh", "Snapshot time missing or older than 90 minutes.")
    runs = github.get("runs")
    if github.get("runs_complete") is not True or not isinstance(runs, list):
        add("runs_incomplete", "incomplete", "runs_complete must be true and runs must be an array.")
        runs = runs if isinstance(runs, list) else []
    if not runs:
        add("runs_empty", "incomplete", "No workflow runs were supplied.")
    pr = github.get("pr")
    expected = pr.get("head_sha") if isinstance(pr, dict) else None
    mismatch, incomplete, nonpassing, skipped = [], [], [], []
    for i, run in enumerate(runs):
        if not isinstance(run, dict):
            incomplete.append(f"run[{i}]:malformed")
            continue
        rid = str(run.get("id", i))
        if not expected or run.get("head_sha") != expected:
            mismatch.append("run:" + rid)
        conclusion, run_status = run.get("conclusion"), run.get("status")
        if run_status != "completed" or conclusion != "success":
            nonpassing.append("run:" + rid + ":" + str(run_status) + "/" + str(conclusion))
        jobs = run.get("jobs")
        if run.get("jobs_complete") is not True or not isinstance(jobs, list) or not jobs:
            incomplete.append(rid + ":jobs_missing_empty_or_incomplete")
            continue
        for j, job in enumerate(jobs):
            if not isinstance(job, dict):
                incomplete.append(f"{rid}:job[{j}]:malformed")
                continue
            name = str(job.get("name", j))
            if not expected or job.get("head_sha") != expected:
                mismatch.append(f"job:{rid}/{name}")
            status, conclusion = job.get("status"), job.get("conclusion")
            if conclusion == "skipped":
                skipped.append(rid + "/" + name)
            elif status != "completed" or conclusion != "success":
                nonpassing.append(f"job:{rid}/{name}:{status}/{conclusion}")
    if mismatch:
        add("github_head_mismatch", "review_required", str(mismatch))
    if incomplete:
        add("github_jobs_incomplete", "incomplete", str(incomplete))
    if nonpassing:
        add("github_nonpassing_run_or_job", "review_required", str(nonpassing))
    if skipped:
        add("github_skipped_not_passed", "review_required", str(skipped))
    return {"runs_count": len(runs), "mismatches": mismatch,
        "incomplete": incomplete, "nonpassing": nonpassing, "skipped": skipped}


def build_report(index, config, observer, github, state, queue, hashes, live, now=None):
    now = now or datetime.now(timezone.utc)
    findings = []
    def add(code, severity, detail):
        findings.append({"code": code, "severity": severity, "detail": detail})
    required = {"index": index, "config": config, "observer": observer,
                "github": github, "state": state, "queue": queue}
    missing = [name for name, value in required.items() if not isinstance(value, dict) or not value]
    for name in missing:
        add("input_missing_" + name, "incomplete", "Required input missing or malformed.")
    index = index if isinstance(index, dict) else {}
    config = config if isinstance(config, dict) else {}
    observer = observer if isinstance(observer, dict) else {}
    github = github if isinstance(github, dict) else {}
    state = state if isinstance(state, dict) else {}
    queue = queue if isinstance(queue, dict) else {}
    hashes = hashes if isinstance(hashes, dict) else {}
    if index.get("schema") != "bos.local-flow.v1":
        add("local_index_schema", "incomplete", "Expected bos.local-flow.v1.")
    if github.get("schema") != "bos.github-snapshot.v1":
        add("github_schema", "incomplete", "Expected bos.github-snapshot.v1.")
    fresh = int(config.get("stale_after_seconds") or 3600)
    generated, observed = parse_time(index.get("generated_at_utc")), parse_time(observer.get("last_observed_at"))
    if generated is None or (observed and generated < observed):
        add("local_index_stale", "needs_refresh", "Index timestamp missing or behind observer.")
    elif (now - generated).total_seconds() > fresh:
        add("local_index_stale", "needs_refresh", "Index exceeds configured freshness window.")

    pin = config.get("sync_source") or {}
    pin = pin if isinstance(pin, dict) else {}
    ident_input = index.get("identities") if isinstance(index.get("identities"), dict) else {}
    indexed_pin = ident_input.get("sync_source") or {}
    indexed_pin = indexed_pin if isinstance(indexed_pin, dict) else {}
    if not pin.get("path") or not pin.get("commit"):
        add("source_pin_missing", "incomplete", "Configured sync source path/commit missing.")
    elif (indexed_pin.get("path"), indexed_pin.get("commit")) != (pin.get("path"), pin.get("commit")):
        add("source_pin_index_mismatch", "needs_refresh", "CURRENT and config exact pins differ.")
    if not live or live.get("error") or not live.get("head"):
        add("live_git_unknown", "incomplete", "Pinned checkout could not be read.")
    elif live.get("head") != pin.get("commit") or live.get("dirty") is not False:
        add("live_source_drift_or_dirty", "needs_refresh", "Pinned HEAD or clean state differs.")
    indexed_live = index.get("sync_source_live") or {}
    indexed_live = indexed_live if isinstance(indexed_live, dict) else {}
    if indexed_live.get("head") != live.get("head") or indexed_live.get("dirty") != live.get("dirty"):
        add("indexed_live_source_stale", "needs_refresh", "Recorded Git state differs from live read.")

    gates = state.get("continuation_acceptance_gates")
    gate_ids = [g.get("id") for g in gates] if isinstance(gates, list) and all(isinstance(g, dict) for g in gates) else []
    if (len(gate_ids) != 11 or any(type(value) is not int for value in gate_ids)
            or set(gate_ids) != set(range(1, 12))):
        add("gate_ids_invalid", "review_required", "Gate ids must be the unique integer set 1..11.")
    if state.get("technical_ready") is not False or state.get("pilot_allowed") is not False:
        add("readiness_flags_changed", "review_required", "Expected technical_ready=false and pilot_allowed=false.")

    qc = check_queue(queue)
    if qc["malformed"] or qc["field_errors"]:
        add("queue_malformed", "incomplete", str(qc["malformed"] or qc["field_errors"]))
    if qc["duplicate_ids"] or qc["missing_dependency_ids"] or qc["cycle_members"]:
        add("queue_graph_invalid", "review_required", str({
            "duplicates": qc["duplicate_ids"], "missing": qc["missing_dependency_ids"],
            "cycles": qc["cycle_members"]}))

    for label, actual in (("state", hashes.get("state")), ("queue", hashes.get("queue"))):
        expected = github.get(label + "_sha256")
        if not expected or not actual:
            add(label + "_hash_missing", "incomplete", "Exact bytes/hash unavailable.")
        elif expected != actual:
            add(label + "_hash_mismatch", "needs_refresh", "Referenced file bytes differ from SHA.")

    ci = ci_check(github, now, add)
    actors = actor_summary(config, observer, index, now, fresh)
    for role, actor in actors.items():
        if actor["availability"] != "reported_idle":
            if actor["availability"] == "not_free_or_unknown":
                add("actor_snapshot_untrusted", "review_required",
                    f"{role}: exact thread/fresh checked status/errors do not prove a current state.")

    # Deliberate identity differences are retained; no equality is assumed among these fields.
    ident = index.get("identities") or {}
    ident = ident if isinstance(ident, dict) else {}
    pr = github.get("pr")
    pr = pr if isinstance(pr, dict) else {}
    identities = {"published": ident.get("published_commit"),
        "local_canonical": ident.get("local_canonical_commit"),
        "last_accepted_runtime": ident.get("last_accepted_runtime_commit"),
        "working_candidate": ident.get("working_candidate"),
        "lab_sync_pin": {"path": pin.get("path"), "commit": pin.get("commit")},
        "lab_sync_live": live, "github_pr_head": pr.get("head_sha"),
        "state_product_candidate": state.get("product_candidate_commit")}
    if findings:
        severities = {f["severity"] for f in findings}
        status = ("INCOMPLETE" if "incomplete" in severities else
                  "NEEDS_REFRESH" if "needs_refresh" in severities else "REVIEW_REQUIRED")
    else:
        status = "COMPLETE"
    return {"schema": "bos.repo-health.v2", "generated_at_utc": now.isoformat(),
        "status": status, "product_authorization": False, "identities": identities,
        "queue_checks": qc, "state_checks": {"technical_ready": state.get("technical_ready"),
            "pilot_allowed": state.get("pilot_allowed"), "gate_count": len(gates) if isinstance(gates, list) else 0,
            "gate_ids": gate_ids},
        "github_checks": ci, "actors": actors, "hashes": hashes, "findings": findings[:20]}


def locked_inputs(home, root):
    home = resolve_control_home(home)
    with state_lock(home):
        config, _ = read_json_once(home / "config.json")
        observer, _ = read_json_once(home / "observer.json")
        index, _ = read_json_once(root / "reports" / "local_flow" / "CURRENT.json")
    return config, observer, index


def collect(home, root, github_path, prepared=None):
    home = resolve_control_home(home)
    missing, hashes, state, queue, live = [], {}, {}, {}, {}
    config, observer, index = locked_inputs(home, root)
    config = config if isinstance(config, dict) else {}
    if prepared is not None:
        github, state, queue, hashes, input_errors = prepared
        missing.extend(input_errors)
        if not isinstance(github, dict):
            github = {}
            missing.append("github_snapshot_not_object")
    else:
        try:
            github, _ = read_json_once(github_path)
            if not isinstance(github, dict):
                raise ValueError("github_snapshot_not_object")
            state_path = safe_ref(github_path, github.get("state_path"))
            queue_path = safe_ref(github_path, github.get("queue_path"))
            state, hashes["state"] = read_json_once(state_path)
            queue, hashes["queue"] = read_json_once(queue_path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            github = {}
            missing.append("github_state_queue:" + type(exc).__name__)
    pin = config.get("sync_source") or {}
    if pin.get("path") and config.get("git_executable"):
        live = read_git(config["git_executable"], pin["path"])
    report = build_report(index, config, observer, github, state, queue, hashes, live)
    if missing:
        report["status"] = "INCOMPLETE"
        report["findings"] = ([{"code": "required_input_missing", "severity": "incomplete", "detail": x}
                               for x in missing] + report["findings"])[:20]
    return report


def validate_output(outdir, root, protected):
    canonical_root = Path(root).resolve()
    base = (canonical_root / "reports" / "repo_health").resolve()
    if canonical_root not in base.parents:
        raise ValueError("output_base_resolves_outside_root")
    target = Path(outdir).resolve()
    if target != base and base not in target.parents:
        raise ValueError("output_dir_outside_root_reports_repo_health")
    outputs = {(target / name).resolve() for name in ("CURRENT.json", "CURRENT_RU.md")}
    protected = {Path(item).resolve() for item in protected if item}
    if outputs & protected:
        raise ValueError("output_aliases_an_input")
    return target


def render(report):
    lines = ["# BoS repository health v2", "", f"Status: {report['status']}",
             "Product authorization: false.", "", "## Source identities", ""]
    lines += [f"- {key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}"
              for key, value in report.get("identities", {}).items()]
    lines += ["", "## Findings", ""]
    lines += [f"- [{item['severity']}] {item['code']}: {item['detail']}"
              for item in report.get("findings", [])]
    if not report.get("findings"):
        lines.append("No findings in the supplied snapshots.")
    lines += ["", "- Skipped CI jobs are not passed.", ""]
    return "\n".join(lines)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        Path(temp).replace(path)
    finally:
        if Path(temp).exists():
            Path(temp).unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github", required=True, type=Path)
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    if not args.github.is_absolute() or not args.output_dir.is_absolute():
        parser.error("--github and --output-dir must be absolute.")
    home = resolve_control_home(args.home)
    gh, state, queue, hashes, input_errors = {}, {}, {}, {}, []
    refs = []
    try:
        gh, _ = read_json_once(args.github)
        if not isinstance(gh, dict):
            raise ValueError("github_snapshot_not_object")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        input_errors.append("github_snapshot:" + type(exc).__name__)
        gh = {}
    for field, label in (("state_path", "state"), ("queue_path", "queue")):
        try:
            ref = safe_ref(args.github, gh.get(field))
            refs.append(ref)
            value, hashes[label] = read_json_once(ref)
            if label == "state":
                state = value
            else:
                queue = value
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            input_errors.append(label + "_ref:" + type(exc).__name__)
    protected = [args.github, *refs, home / "config.json", home / "observer.json",
        args.root / "reports" / "local_flow" / "CURRENT.json"]
    try:
        outdir = validate_output(args.output_dir, args.root, protected)
    except ValueError as exc:
        parser.error("unsafe output path: " + str(exc))
    report = collect(home, args.root, args.github,
        prepared=(gh, state, queue, hashes, input_errors))
    outdir.mkdir(parents=True, exist_ok=True)
    write(outdir / "CURRENT.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write(outdir / "CURRENT_RU.md", render(report))
    print(json.dumps({"schema": report["schema"], "status": report["status"],
        "findings": len(report["findings"]), "output_dir": str(outdir)}, ensure_ascii=False))
    return 0 if report["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())


