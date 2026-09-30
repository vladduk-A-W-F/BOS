"""One-shot, separately admitted Windows control-home installation phases."""

from __future__ import annotations

import argparse
import hashlib
import json
import msvcrt
import os
import shutil
import stat
import sys
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path

import native_windows as native


class Refused(RuntimeError):
    pass


BASE = Path("D:/3/BOSDev/qa-scratch/bos3-control-home-install-20260928")
WORK = BASE / "operation/source-complete-20260929"
C_HOME = Path("C:/Users/user/AppData/Local/BOSDev")
D_HOME = Path("D:/3/BOSDev/control-home")
C_ARCHIVE = Path("C:/Users/user/AppData/Local/BOSDev.pre-D-20260928")
ANCHOR = Path("D:/3/BOSDev/control-home-authority.json")
EVIDENCE = Path("D:/3/BOSDev/evidence/bos3-control-home-install-20260928")
SETUP = Path("D:/3/BOSDev/setup")
FIXED_PATHS = {"legacy_alias": C_HOME.as_posix(), "target_home": D_HOME.as_posix(),
               "source_archive": C_ARCHIVE.as_posix(), "authority_anchor": ANCHOR.as_posix(),
               "evidence_root": EVIDENCE.as_posix(), "setup": SETUP.as_posix()}
CUTOFF = datetime(2026, 10, 4, 21, 59, tzinfo=timezone.utc)
PHASES = ("snapshot", "prepare", "alias", "activate", "verify")
PINNED = {
    "operation/source-complete-20260929/CARD.json": "acc92026a4bf97f57770337601acc77877caa514f1d8dcc371483a7593c122cd",
    "architecture/INTERFACE.json": "fe0401c9aca5a1f57a5e10b4381d9fc6d53544169ac790ad7ecf6c305e56621d",
    "ROOT_COMMAND_SHEET_RU.md": "7e8e7883ebf331a39ac37a3e6677770dbccea3b44f3171f39d9c634e74820fe5",
    "source/MANIFEST.json": "00997c1323aaf7b8927f7c36ffbd341b422695402fc925012f9a8ff74e03598c",
    "consumers/MANIFEST.json": "3b684264bf6c3ae1825c8bbdd2ce9bd8e28e9618d1cdd04abd900f60a3253ec9",
}
OVERLAYS = (
    ("source", "bos_dev.py", D_HOME / "tools/bos_dev.py"),
    ("source", "codex_channel.py", D_HOME / "tools/codex_channel.py"),
    ("consumers", "bos.ps1", D_HOME / "tools/bos.ps1"),
    ("consumers", "bos_flow.py", SETUP / "bos_flow.py"),
    ("consumers", "local_flow.py", SETUP / "local_flow.py"),
    ("consumers", "repo_health.py", SETUP / "repo_health.py"),
    ("consumers", "bos-flow.ps1", SETUP / "bos-flow.ps1"),
    ("consumers", "start-workday.ps1", SETUP / "start-workday.ps1"),
)
OLD_MCP = b"C:/Users/user/AppData/Local/BOSDev/tools/codex_channel.py"
NEW_MCP = b"D:/3/BOSDev/control-home/tools/codex_channel.py"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path, *, stream=None) -> str:
    sha = hashlib.sha256()
    if stream is not None:
        stream.seek(0)
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
        return sha.hexdigest()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def parse_json(data: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Refused("duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(data.decode("utf-8"), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise Refused("JSON object required")
    return value


def exact_file(path: Path, expected: str) -> bytes:
    native.inspect(path, directory=False)
    native.require_single_stream(path)
    data = path.read_bytes()
    if digest(data) != expected:
        raise Refused(f"digest mismatch: {path}")
    return data


def fixed_ref(ref: dict, *, directory: Path = EVIDENCE) -> tuple[Path, bytes]:
    if set(ref) != {"path", "sha256"} or not isinstance(ref["path"], str):
        raise Refused("exact path/sha256 receipt reference required")
    path = Path(ref["path"])
    if (not path.is_absolute() or path == directory or directory not in path.parents
            or ".." in path.parts or path.drive not in ("C:", "D:")):
        raise Refused("receipt must be inside fixed evidence root")
    for ancestor in path.parents:
        if ancestor == directory.parent:
            break
        if os.lstat(ancestor).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise Refused("receipt ancestor reparse refused")
    sha = ref["sha256"]
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise Refused("invalid receipt SHA256")
    return path, exact_file(path, sha)


def check_pins() -> dict:
    for relative, expected in PINNED.items():
        if file_digest(BASE / relative) != expected:
            raise Refused(f"frozen source changed: {relative}")
    manifests = {}
    for name in ("source", "consumers"):
        manifest = parse_json((BASE / name / "MANIFEST.json").read_bytes())
        field = "outputs" if name == "source" else "result_sha256"
        for staged, sha in manifest[field].items():
            if not staged.startswith("staged/") or ".." in Path(staged).parts:
                raise Refused("invalid staged dependency path")
            exact_file(BASE / name / staged, sha)
        manifests[name] = manifest
    return manifests


def check_time() -> None:
    if datetime.now(timezone.utc) > CUTOFF:
        raise Refused("operation cutoff passed")


def check_plan(path: Path, sha: str) -> dict:
    if path.parent != EVIDENCE or ".." in path.parts:
        raise Refused("plan must be an exact private evidence file")
    plan = parse_json(exact_file(path, sha))
    if plan.get("schema") != "bos3.control-home-operation-plan/v1":
        raise Refused("wrong operation plan schema")
    if plan.get("generation") != str(uuid.UUID(plan.get("generation", ""))):
        raise Refused("canonical generation UUID required")
    if plan.get("paths") != FIXED_PATHS:
        raise Refused("operation paths changed")
    if plan.get("dependency_review_sha256") != "21c32c1a7835002c55e2d14eec9bea269d29c36a02ed73a53f9b4d497868ac67":
        raise Refused("independent dependency review changed")
    if plan.get("global_config") is None or not Path(plan["global_config"]).is_absolute():
        raise Refused("exact global config path required")
    if not isinstance(plan.get("global_config_before_sha256"), str):
        raise Refused("global config before digest required")
    if not isinstance(plan.get("global_config_after_sha256"), str):
        raise Refused("global config after digest required")
    for key in ("global_config_reviewed_after", "global_config_edit"):
        if not isinstance(plan.get(key), dict):
            raise Refused(f"exact reviewed config input required: {key}")
    return plan


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise Refused("UTC timestamp required")
    return parsed.astimezone(timezone.utc)


def phase_admission(path: Path, sha: str, phase: str, generation: str,
                    plan_sha: str, previous_sha: str | None) -> dict:
    if path.parent != EVIDENCE:
        raise Refused("phase admission must be in fixed evidence root")
    receipt = parse_json(exact_file(path, sha))
    if receipt.get("schema") != "bos3.control-home-phase-admission/v1" or receipt.get("verdict") != "ADMIT_CONTROL_HOME_PHASE":
        raise Refused("independent phase admission missing")
    if (receipt.get("operation"), receipt.get("generation"), receipt.get("phase"),
            receipt.get("plan_sha256")) != ("B30-D-CONTROL-HOME-OPERATION-SOURCE", generation, phase, plan_sha):
        raise Refused("phase admission binding mismatch")
    if receipt.get("paths") != FIXED_PATHS or receipt.get("owner_message") != "01a0ee26-9c0e-7bd2-9508-de9e026c5966":
        raise Refused("admission owner/path binding mismatch")
    if receipt.get("scope") != phase or receipt.get("maximum_invocations") != 1 or receipt.get("retry_allowed") is not False:
        raise Refused("one-shot phase scope missing")
    if receipt.get("qa_attempts_spent") != "1/1" or receipt.get("C64_unchanged") is not True:
        raise Refused("historical limits missing")
    if receipt.get("previous_receipt_sha256") != previous_sha:
        raise Refused("previous receipt hash not admitted")
    if receipt.get("deadline") != "2026-10-04T23:59:00+02:00":
        raise Refused("deadline changed")
    code = receipt.get("source_sha256", {})
    if code != {"install_control_home.py": file_digest(WORK / "install_control_home.py"),
                "native_windows.py": file_digest(WORK / "native_windows.py"),
                "OPERATION_CONTRACT.json": file_digest(WORK / "OPERATION_CONTRACT.json")}:
        raise Refused("phase admission source hashes changed")
    for name, verdict in (("source_review", "ACCEPT_SOURCE_FOR_PHASE_REVIEW"),
                          ("qa_acceptance", "ACCEPT_FOCUSED_QA_FOR_OPERATION")):
        ref = receipt.get(name)
        if not isinstance(ref, dict):
            raise Refused(f"independent {name} missing")
        review = parse_json(fixed_ref(ref)[1])
        if (review.get("verdict") != verdict or review.get("card") != "B30-D-CONTROL-HOME-OPERATION-SOURCE"
                or review.get("source_sha256") != code):
            raise Refused(f"independent {name} source binding mismatch")
    qref = receipt.get("quiescence")
    if not isinstance(qref, dict):
        raise Refused("quiescence reference missing")
    q = parse_json(fixed_ref(qref)[1])
    if q.get("schema") != "bos3.control-home-global-quiescence/v1" or q.get("generation") != generation:
        raise Refused("quiescence generation/schema mismatch")
    if q.get("freeze_id") != receipt.get("freeze_id") or not isinstance(q.get("freeze_id"), str):
        raise Refused("freeze identity missing")
    now = datetime.now(timezone.utc)
    if not (_timestamp(q["observed_at_utc"]) <= now < _timestamp(q["expires_at_utc"])):
        raise Refused("quiescence observation stale")
    if q.get("root_sole_operator") is not True or q.get("resumed_since_freeze") is not False:
        raise Refused("operator/freeze status not proven")
    actors = q.get("actors")
    required = {"root", "observer", "workers", "direct_callers", "cached_modules", "registrations", "mcp_worker", "transport", "heartbeat"}
    if not isinstance(actors, dict) or set(actors) != required or any(
        not isinstance(v, dict) or v.get("disposition") not in ("STOPPED", "DRAINED", "PAUSED", "INAPPLICABLE_REVIEWED")
        or not isinstance(v.get("native_receipt"), dict) for v in actors.values()
    ):
        raise Refused("complete reviewed actor map required")
    for actor in actors.values():
        fixed_ref(actor["native_receipt"])
    if actors["heartbeat"]["disposition"] != "PAUSED" or actors["transport"]["disposition"] != "DRAINED":
        raise Refused("heartbeat pause or transport drain missing")
    return receipt


def refresh_gate(plan: dict, args) -> None:
    check_time()
    phase_admission(Path(args.admission), args.admission_sha256, args.phase,
                    plan["generation"], args.plan_sha256, args.previous_sha256)


def _write_new(path: Path, data: bytes, acl_from: Path) -> None:
    if native.present(path):
        raise Refused(f"output exists: {path}")
    with path.open("xb") as output:
        native.copy_acl(acl_from, path)
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    if file_digest(path) != digest(data) or native.acl_fingerprint(path) != native.acl_fingerprint(acl_from):
        raise Refused("written file digest mismatch")


def exclusive_bytes(path: Path, data: bytes, acl_from: Path) -> dict:
    temporary = path.with_name("." + path.name + ".new")
    _write_new(temporary, data, acl_from)
    if native.present(path):
        raise Refused(f"immutable output exists: {path}")
    os.rename(temporary, path)
    if file_digest(path) != digest(data) or native.acl_fingerprint(path) != native.acl_fingerprint(acl_from):
        raise Refused("immutable publication readback mismatch")
    return {"path": str(path), "sha256": digest(data)}


def atomic_bytes(path: Path, data: bytes, acl_from: Path, generation: str, label: str) -> dict:
    temporary = path.with_name(f".{path.name}.{generation}.{label}.tmp")
    _write_new(temporary, data, acl_from)
    if native.acl_fingerprint(temporary) != native.acl_fingerprint(acl_from):
        raise Refused("atomic temp ACL mismatch")
    os.replace(temporary, path)
    if file_digest(path) != digest(data) or native.acl_fingerprint(path) != native.acl_fingerprint(acl_from):
        raise Refused("atomic readback mismatch")
    return {"path": str(path), "sha256": digest(data)}


def generation_dir(plan: dict) -> Path:
    path = EVIDENCE / plan["generation"]
    if path.parent != EVIDENCE:
        raise Refused("invalid generation directory")
    return path


def receipt_ref(plan: dict, phase: str, expected: str | None = None) -> tuple[dict, dict]:
    path = generation_dir(plan) / f"{phase}.receipt.json"
    if not expected:
        raise Refused("exact previous receipt SHA256 required")
    ref = {"path": str(path), "sha256": expected}
    return parse_json(fixed_ref(ref)[1]), ref


def begin_attempt(plan: dict, phase: str, admission_sha: str, previous_sha: str | None) -> None:
    payload = {"schema": "bos3.control-home-phase-attempt/v1", "generation": plan["generation"],
               "phase": phase, "admission_sha256": admission_sha, "previous_sha256": previous_sha,
               "started_at_utc": datetime.now(timezone.utc).isoformat()}
    exclusive_bytes(generation_dir(plan) / f"{phase}.attempt.json", json_bytes(payload), generation_dir(plan))


def finish_phase(plan: dict, phase: str, admission_sha: str, previous_sha: str | None, details: dict) -> dict:
    payload = {"schema": "bos3.control-home-phase-receipt/v1", "generation": plan["generation"],
               "phase": phase, "admission_sha256": admission_sha, "previous_sha256": previous_sha,
               "details": details, "completed_at_utc": datetime.now(timezone.utc).isoformat()}
    return exclusive_bytes(generation_dir(plan) / f"{phase}.receipt.json", json_bytes(payload), generation_dir(plan))


def inventory(root: Path, lock_stream=None) -> dict:
    result = {}
    native.require_local_ntfs(root)
    def visit(path: Path, rel: str) -> None:
        item = os.lstat(path)
        is_dir = stat.S_ISDIR(item.st_mode)
        identity = native.inspect(path, directory=is_dir)
        native.require_single_stream(path, directory=is_dir)
        entry = {"type": "directory" if is_dir else "file", "identity": identity,
                 "acl_sha256": native.acl_fingerprint(path),
                 "attributes": item.st_file_attributes, "mtime_ns": item.st_mtime_ns}
        if is_dir:
            result[rel] = entry
            for child in sorted(os.scandir(path), key=lambda x: x.name):
                visit(Path(child.path), f"{rel}/{child.name}" if rel else child.name)
        else:
            entry.update({"size": item.st_size,
                          "sha256": file_digest(path, stream=lock_stream if rel == ".queue.lock" else None)})
            result[rel] = entry
    visit(root, "")
    return result


def snapshot(plan: dict) -> dict:
    if native.present(D_HOME) or native.present(C_ARCHIVE) or native.present(ANCHOR):
        raise Refused("destination/archive/anchor conflict")
    native.require_local_ntfs(C_HOME)
    native.require_local_ntfs(D_HOME)
    native.inspect(C_HOME, directory=True)
    lock = C_HOME / ".queue.lock"
    native.inspect(lock, directory=False)
    with lock.open("r+b") as stream:
        if os.fstat(stream.fileno()).st_size < 1:
            raise Refused("source lock is empty")
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            contents = inventory(C_HOME, stream)
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    required = ("config.json", "queue.json", "observer.json", "codex-channel-delivery.json", ".queue.lock")
    if any(name not in contents or contents[name]["type"] != "file" for name in required):
        raise Refused("required control state missing")
    payload = {"schema": "bos3.control-home-opaque-snapshot/v1", "generation": plan["generation"],
               "source": str(C_HOME), "entries": contents}
    ref = exclusive_bytes(generation_dir(plan) / "snapshot.manifest.json", json_bytes(payload), generation_dir(plan))
    return {"snapshot_manifest": ref, "entry_count": len(contents),
            "source_root_identity": contents[""]["identity"],
            "source_lock_identity": contents[".queue.lock"]["identity"]}


def load_snapshot(plan: dict, previous: dict) -> dict:
    ref = previous["details"]["snapshot_manifest"]
    manifest = parse_json(fixed_ref(ref)[1])
    if manifest.get("generation") != plan["generation"] or manifest.get("source") != str(C_HOME):
        raise Refused("snapshot manifest binding mismatch")
    return manifest["entries"]


def checked_copy(source: Path, destination: Path, entry: dict) -> None:
    if native.inspect(source, directory=False) != entry["identity"]:
        raise Refused("source identity changed")
    native.require_single_stream(source)
    if file_digest(source) != entry["sha256"] or native.acl_fingerprint(source) != entry["acl_sha256"]:
        raise Refused("source bytes or ACL changed")
    if native.present(destination):
        raise Refused("copy destination exists")
    with source.open("rb") as read, destination.open("xb") as write:
        native.copy_acl(source, destination)
        shutil.copyfileobj(read, write, 1024 * 1024)
        write.flush()
        os.fsync(write.fileno())
    shutil.copystat(source, destination, follow_symlinks=False)
    native.copy_attributes(source, destination)
    if file_digest(destination) != entry["sha256"] or native.acl_fingerprint(destination) != entry["acl_sha256"]:
        raise Refused("copy readback mismatch")


def copy_home(entries: dict) -> dict:
    if native.present(D_HOME):
        raise Refused("target home exists")
    D_HOME.mkdir()
    native.copy_acl(C_HOME, D_HOME)
    native.copy_attributes(C_HOME, D_HOME)
    if native.acl_fingerprint(D_HOME) != entries[""]["acl_sha256"]:
        raise Refused("target root ACL mismatch")
    for rel, entry in sorted(entries.items(), key=lambda pair: (pair[0].count("/"), pair[0])):
        if not rel:
            continue
        source = C_HOME / rel
        destination = D_HOME / rel
        if entry["type"] == "directory":
            if native.inspect(source, directory=True) != entry["identity"]:
                raise Refused("source directory changed")
            native.require_single_stream(source, directory=True)
            destination.mkdir()
            native.copy_acl(source, destination)
            native.copy_attributes(source, destination)
            if native.acl_fingerprint(destination) != entry["acl_sha256"]:
                raise Refused("directory ACL mismatch")
        elif entry["type"] == "file":
            checked_copy(source, destination, entry)
        else:
            raise Refused("unknown snapshot object type")
    for rel, entry in sorted(entries.items(), key=lambda pair: (-pair[0].count("/"), pair[0])):
        if entry["type"] == "directory":
            shutil.copystat(C_HOME / rel, D_HOME / rel, follow_symlinks=False)
            native.copy_attributes(C_HOME / rel, D_HOME / rel)
    for rel, entry in entries.items():
        target = D_HOME / rel
        if native.acl_fingerprint(target) != entry["acl_sha256"]:
            raise Refused("full copy ACL changed after parent updates")
        if entry["type"] == "file" and file_digest(target) != entry["sha256"]:
            raise Refused("full copy digest mismatch")
        if os.lstat(target).st_file_attributes != entry["attributes"]:
            raise Refused("full copy attributes mismatch")
    if native.inspect(D_HOME / ".queue.lock", directory=False) == entries[".queue.lock"]["identity"]:
        raise Refused("D lock identity must be new")
    return {"target_root_identity": native.inspect(D_HOME, directory=True),
            "target_lock_identity": native.inspect(D_HOME / ".queue.lock", directory=False)}


def reviewed_overlay(source: Path, destination: Path, expected_before: str, expected_after: str,
                     backup: Path) -> dict:
    if file_digest(destination) != expected_before:
        raise Refused(f"overlay base changed: {destination}")
    before_acl = native.acl_fingerprint(destination)
    original = destination.read_bytes()
    backup_ref = exclusive_bytes(backup, original, destination)
    if native.acl_fingerprint(backup) != before_acl:
        raise Refused("backup ACL mismatch")
    replacement = exact_file(source, expected_after)
    atomic_bytes(destination, replacement, destination, "overlay", digest(str(destination).encode())[:12])
    if native.acl_fingerprint(destination) != before_acl:
        raise Refused("overlay ACL mismatch")
    return {"destination": str(destination), "before_sha256": expected_before,
            "after_sha256": expected_after, "backup": backup_ref}


def config_overlay(plan: dict) -> dict:
    path = Path(plan["global_config"])
    if path == C_HOME or C_HOME in path.parents or path == D_HOME or D_HOME in path.parents:
        raise Refused("global config must be external to both homes")
    original = exact_file(path, plan["global_config_before_sha256"])
    edit = plan["global_config_edit"]
    if set(edit) != {"offset", "old_text", "new_text", "args_index", "before_size", "after_size"}:
        raise Refused("reviewed config span is incomplete")
    if edit["old_text"] != OLD_MCP.decode() or edit["new_text"] != NEW_MCP.decode():
        raise Refused("reviewed MCP tokens changed")
    offset = edit["offset"]
    if not isinstance(offset, int) or offset < 0 or original[offset:offset + len(OLD_MCP)] != OLD_MCP:
        raise Refused("reviewed MCP byte offset mismatch")
    if edit["before_size"] != len(original):
        raise Refused("reviewed config byte length changed")
    after = original[:offset] + NEW_MCP + original[offset + len(OLD_MCP):]
    if edit["after_size"] != len(after):
        raise Refused("reviewed replacement length mismatch")
    reviewed_after = fixed_ref(plan["global_config_reviewed_after"])[1]
    if after != reviewed_after:
        raise Refused("candidate bytes differ from pre-reviewed config after bytes")
    if digest(after) != plan["global_config_after_sha256"]:
        raise Refused("reviewed config after SHA mismatch")
    before_obj = tomllib.loads(original.decode("utf-8-sig"))
    after_obj = tomllib.loads(after.decode("utf-8-sig"))
    before_args = before_obj["mcp_servers"]["bos_control"]["args"]
    after_args = after_obj["mcp_servers"]["bos_control"]["args"]
    index = edit["args_index"]
    if (not isinstance(before_args, list) or not isinstance(index, int)
            or index < 0 or index >= len(before_args) or before_args[index] != OLD_MCP.decode()):
        raise Refused("MCP argv value not exact")
    expected_args = list(before_args)
    expected_args[index] = NEW_MCP.decode()
    if after_args != expected_args:
        raise Refused("MCP argv semantic edit mismatch")
    before_obj["mcp_servers"]["bos_control"]["args"] = after_args
    if before_obj != after_obj:
        raise Refused("global config semantics changed outside MCP argv")
    backup = generation_dir(plan) / "global-config.before"
    backup_ref = exclusive_bytes(backup, original, path)
    atomic_bytes(path, after, path, plan["generation"], "global-config")
    return {"path": str(path), "before_sha256": digest(original), "after_sha256": digest(after),
            "backup": backup_ref}


def prepare(plan: dict, previous: dict, manifests: dict, args) -> dict:
    entries = load_snapshot(plan, previous)
    if inventory(C_HOME) != entries:
        raise Refused("source changed after snapshot")
    copy_details = copy_home(entries)
    overlays = []
    for group, name, destination in OVERLAYS:
        manifest = manifests[group]
        after = (manifest["outputs"] if group == "source" else manifest["result_sha256"])["staged/" + name]
        source = BASE / group / "staged" / name
        before = (manifests["source"]["inputs"].get(name) if group == "source" else
                  manifests["consumers"]["baseline_sha256"].get(name))
        if not before:
            raise Refused(f"missing overlay baseline: {name}")
        backup = generation_dir(plan) / ("backup-" + group + "-" + name)
        overlays.append(reviewed_overlay(source, destination, before, after, backup))
    refresh_gate(plan, args)
    config = config_overlay(plan)
    refresh_gate(plan, args)
    prepared = {"schema": "bos3.control-home-authority/v1", "generation": plan["generation"],
                "phase": "PREPARED", "home": D_HOME.as_posix(), "legacy_alias": C_HOME.as_posix(),
                "source_archive": C_ARCHIVE.as_posix(), "root_identity": copy_details["target_root_identity"],
                "lock_identity": copy_details["target_lock_identity"], "prepared_receipt": None,
                "migration_acceptance": None, "activated_at_utc": None}
    anchor_ref = atomic_bytes(ANCHOR, json_bytes(prepared), D_HOME, plan["generation"], "prepared")
    return {"copy": copy_details, "overlays": overlays, "global_config": config,
            "snapshot_manifest": previous["details"]["snapshot_manifest"],
            "draft_prepared_anchor": anchor_ref}


def alias(plan: dict, previous: dict, args) -> dict:
    anchor = parse_json(ANCHOR.read_bytes())
    if anchor.get("phase") != "PREPARED" or anchor.get("generation") != plan["generation"]:
        raise Refused("draft PREPARED anchor missing")
    if previous["details"]["draft_prepared_anchor"]["sha256"] != file_digest(ANCHOR):
        raise Refused("draft anchor changed")
    root_identity = native.inspect(D_HOME, directory=True)
    lock_identity = native.inspect(D_HOME / ".queue.lock", directory=False)
    if (root_identity, lock_identity) != (anchor["root_identity"], anchor["lock_identity"]):
        raise Refused("prepared D identities changed")
    snapshot_ref = previous["details"]["snapshot_manifest"]
    entries = parse_json(fixed_ref(snapshot_ref)[1])["entries"]
    if inventory(C_HOME) != entries:
        raise Refused("full C source changed before alias")
    old_root = native.inspect(C_HOME, directory=True)
    old_lock = native.inspect(C_HOME / ".queue.lock", directory=False)
    refresh_gate(plan, args)
    native.rename_same_volume(C_HOME, C_ARCHIVE)
    if native.inspect(C_ARCHIVE, directory=True) != old_root or native.inspect(C_ARCHIVE / ".queue.lock") != old_lock:
        raise Refused("C archive identity changed")
    if inventory(C_ARCHIVE) != entries:
        raise Refused("C archive opaque manifest changed")
    refresh_gate(plan, args)
    native.create_junction(C_HOME, D_HOME, C_ARCHIVE)
    if native.identity_follow(C_HOME) != root_identity or native.identity_follow(C_HOME / ".queue.lock") != lock_identity:
        raise Refused("C/D alias identity mismatch")
    details = {"source_archive": str(C_ARCHIVE), "old_root_identity": old_root,
               "old_lock_identity": old_lock, "target_root_identity": root_identity,
               "target_lock_identity": lock_identity, "alias_root_identity": native.identity_follow(C_HOME),
               "alias_lock_identity": native.identity_follow(C_HOME / ".queue.lock")}
    final = {"schema": "bos3.control-home-prepared-receipt/v1", "generation": plan["generation"],
             "plan_sha256": plan["_sha256"], "snapshot_receipt_sha256": previous["previous_sha256"],
             "prepare_receipt_sha256": plan["_previous_sha256"],
             "alias_admission_sha256": args.admission_sha256,
             "prepare": previous["details"], "alias": details,
             "completed_at_utc": datetime.now(timezone.utc).isoformat()}
    final_ref = exclusive_bytes(generation_dir(plan) / "prepared.final.json", json_bytes(final), generation_dir(plan))
    anchor["prepared_receipt"] = final_ref
    updated = atomic_bytes(ANCHOR, json_bytes(anchor), ANCHOR, plan["generation"], "alias-prepared")
    details.update({"prepared_receipt": final_ref, "prepared_anchor": updated})
    return details


def activate(plan: dict, previous: dict, acceptance_ref: dict, args) -> dict:
    prepared_ref = previous["details"]["prepared_receipt"]
    prepared = parse_json(fixed_ref(prepared_ref)[1])
    if prepared.get("generation") != plan["generation"] or prepared.get("plan_sha256") != plan["_sha256"]:
        raise Refused("final prepared receipt binding mismatch")
    acceptance = parse_json(fixed_ref(acceptance_ref)[1])
    if (acceptance.get("verdict"), acceptance.get("generation"), acceptance.get("prepared_receipt_sha256")) != (
        "ACCEPT_MIGRATION_COMMIT", plan["generation"], prepared_ref["sha256"]):
        raise Refused("independent commit acceptance missing")
    if not acceptance.get("issuer") or not isinstance(acceptance.get("independent_review"), dict):
        raise Refused("independent commit issuer/review missing")
    commit_review = parse_json(fixed_ref(acceptance["independent_review"])[1])
    if commit_review.get("verdict") != "ACCEPT_PREPARED_MIGRATION" or commit_review.get("prepared_receipt_sha256") != prepared_ref["sha256"]:
        raise Refused("independent prepared review mismatch")
    anchor = parse_json(ANCHOR.read_bytes())
    if anchor.get("phase") != "PREPARED" or anchor.get("prepared_receipt") != prepared_ref:
        raise Refused("prepared anchor binding mismatch")
    if previous["details"]["prepared_anchor"]["sha256"] != file_digest(ANCHOR):
        raise Refused("prepared anchor digest changed")
    native.validate_junction(C_HOME, D_HOME)
    if native.identity_follow(C_HOME) != anchor["root_identity"] or native.inspect(D_HOME) != anchor["root_identity"]:
        raise Refused("root alias identity changed")
    if native.identity_follow(C_HOME / ".queue.lock") != anchor["lock_identity"]:
        raise Refused("lock alias identity changed")
    if file_digest(Path(prepared["prepare"]["global_config"]["path"])) != prepared["prepare"]["global_config"]["after_sha256"]:
        raise Refused("prepared global config changed")
    for overlay in prepared["prepare"]["overlays"]:
        if file_digest(Path(overlay["destination"])) != overlay["after_sha256"]:
            raise Refused("prepared overlay changed")
        if digest(fixed_ref(overlay["backup"])[1]) != overlay["before_sha256"]:
            raise Refused("overlay backup changed")
    config = prepared["prepare"]["global_config"]
    if digest(fixed_ref(config["backup"])[1]) != config["before_sha256"]:
        raise Refused("global config backup changed")
    entries = parse_json(fixed_ref(prepared["prepare"]["snapshot_manifest"])[1])["entries"]
    if inventory(C_ARCHIVE) != entries:
        raise Refused("archived source changed before ACTIVE")
    for name in ("config.json", "queue.json", "observer.json", "codex-channel-delivery.json", ".queue.lock"):
        if file_digest(D_HOME / name) != entries[name]["sha256"]:
            raise Refused("preserved state changed before ACTIVE")
    refresh_gate(plan, args)
    anchor["phase"] = "ACTIVE"
    anchor["migration_acceptance"] = acceptance_ref
    anchor["activated_at_utc"] = datetime.now(timezone.utc).isoformat()
    ref = atomic_bytes(ANCHOR, json_bytes(anchor), ANCHOR, plan["generation"], "active")
    if parse_json(exact_file(ANCHOR, ref["sha256"])) != anchor:
        raise Refused("ACTIVE readback mismatch")
    return {"active_anchor": ref, "prepared_receipt": prepared_ref,
            "migration_acceptance": acceptance_ref}


def verify(plan: dict, previous: dict, args) -> dict:
    anchor = parse_json(exact_file(ANCHOR, previous["details"]["active_anchor"]["sha256"]))
    if anchor.get("phase") != "ACTIVE" or anchor.get("generation") != plan["generation"]:
        raise Refused("ACTIVE authority missing")
    root = native.inspect(D_HOME, directory=True)
    lock = native.inspect(D_HOME / ".queue.lock", directory=False)
    if root != anchor["root_identity"] or lock != anchor["lock_identity"]:
        raise Refused("target identity mismatch")
    native.validate_junction(C_HOME, D_HOME)
    if native.identity_follow(C_HOME) != root or native.identity_follow(C_HOME / ".queue.lock") != lock:
        raise Refused("C/D identity mismatch")
    final = parse_json(fixed_ref(anchor["prepared_receipt"])[1])
    if final.get("generation") != plan["generation"]:
        raise Refused("prepared generation mismatch")
    snapshot_ref = final["prepare"]["snapshot_manifest"]
    entries = parse_json(fixed_ref(snapshot_ref)[1])["entries"]
    if inventory(C_ARCHIVE) != entries:
        raise Refused("archived source changed before installed verification")
    preserved = {}
    for name in ("config.json", "queue.json", "observer.json", "codex-channel-delivery.json", ".queue.lock"):
        sha = file_digest(D_HOME / name)
        if sha != entries[name]["sha256"]:
            raise Refused(f"preserved initial state changed before resumption: {name}")
        preserved[name] = sha
    for overlay in final["prepare"]["overlays"]:
        if file_digest(Path(overlay["destination"])) != overlay["after_sha256"]:
            raise Refused("installed overlay changed before resumption")
    config = final["prepare"]["global_config"]
    if file_digest(Path(config["path"])) != config["after_sha256"]:
        raise Refused("installed global config changed")
    coordinator_ref = phase_admission(Path(args.admission), args.admission_sha256,
                                      "verify", plan["generation"], args.plan_sha256,
                                      args.previous_sha256).get("coordinator_readonly_receipt")
    if not isinstance(coordinator_ref, dict):
        raise Refused("read-only coordinator status receipt missing")
    coordinator = parse_json(fixed_ref(coordinator_ref)[1])
    if (coordinator.get("schema"), coordinator.get("generation"), coordinator.get("active_anchor_sha256"),
            coordinator.get("read_only")) != ("bos3.control-home-coordinator-status/v1", plan["generation"],
                                             previous["details"]["active_anchor"]["sha256"], True):
        raise Refused("coordinator read-only status binding mismatch")
    return {"root_identity": root, "lock_identity": lock, "preserved_state_sha256": preserved,
            "coordinator_status": coordinator_ref,
            "installed_acceptance": "PENDING_INDEPENDENT_REVIEW"}


def run(args) -> dict:
    check_time()
    manifests = check_pins()
    plan = check_plan(Path(args.plan), args.plan_sha256)
    plan["_sha256"] = args.plan_sha256
    for path in (C_HOME, D_HOME, C_ARCHIVE, ANCHOR, EVIDENCE, SETUP, Path(plan["global_config"])):
        native.require_ordinary_ancestors(path)
        native.require_local_ntfs(path)
    phase = args.phase
    refresh_gate(plan, args)
    if phase == "snapshot":
        if args.previous_sha256:
            raise Refused("snapshot has no previous receipt")
        if generation_dir(plan).exists():
            raise Refused("generation already exists")
        generation_dir(plan).mkdir(parents=False)
        native.copy_acl(C_HOME, generation_dir(plan))
        previous = None
    else:
        index = PHASES.index(phase)
        previous, _ = receipt_ref(plan, PHASES[index - 1], args.previous_sha256)
        if previous.get("generation") != plan["generation"] or previous.get("phase") != PHASES[index - 1]:
            raise Refused("previous phase receipt mismatch")
    acceptance_ref = None
    if phase == "activate":
        if not args.acceptance or not args.acceptance_sha256:
            raise Refused("independent acceptance path and SHA required")
        acceptance_ref = {"path": args.acceptance, "sha256": args.acceptance_sha256}
    elif args.acceptance or args.acceptance_sha256:
        raise Refused("acceptance only applies to activate")
    begin_attempt(plan, phase, args.admission_sha256, args.previous_sha256)
    try:
        if phase == "snapshot":
            details = snapshot(plan)
        elif phase == "prepare":
            details = prepare(plan, previous, manifests, args)
        elif phase == "alias":
            plan["_previous_sha256"] = args.previous_sha256
            details = alias(plan, previous, args)
        elif phase == "activate":
            details = activate(plan, previous, acceptance_ref, args)
        else:
            details = verify(plan, previous, args)
        refresh_gate(plan, args)
        return finish_phase(plan, phase, args.admission_sha256, args.previous_sha256, details)
    except Exception as exc:
        failure = {"schema": "bos3.control-home-phase-failure/v1", "generation": plan["generation"],
                   "phase": phase, "outcome": "UNCERTAIN_REQUIRES_REVIEW",
                   "exception_type": type(exc).__name__, "reason": str(exc),
                   "recorded_at_utc": datetime.now(timezone.utc).isoformat()}
        try:
            exclusive_bytes(generation_dir(plan) / f"{phase}.failure.json", json_bytes(failure), generation_dir(plan))
        except Exception as record_error:
            raise Refused(f"phase failed ({type(exc).__name__}: {exc}); failure receipt also failed ({record_error})") from exc
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=PHASES)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--admission", required=True)
    parser.add_argument("--admission-sha256", required=True)
    parser.add_argument("--previous-sha256")
    parser.add_argument("--acceptance")
    parser.add_argument("--acceptance-sha256")
    args = parser.parse_args()
    try:
        result = run(args)
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError,
            native.NativeError, Refused) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
