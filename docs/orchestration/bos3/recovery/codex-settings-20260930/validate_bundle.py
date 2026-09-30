"""Read-only, deterministic validation of this portable text bundle."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "SHA256SUMS.json"
EXPECTED_TOP = {"README_RU.md", "STATE_RU.md", "PROVENANCE.json", "SHA256SUMS.json", "validate_bundle.py"}
EXPECTED_ROLES = {
    "bos_architect", "bos_diagnostician", "bos_evidence", "bos_implementer",
    "bos_pilot_pack", "bos_readiness_auditor", "bos_release_packager",
    "bos_reviewer", "bos_test_ci", "bos_ux",
}
FORBIDDEN_NAMES = {
    "auth.json", "config.toml", "default.rules", "state_5.sqlite", "thread_history_1.sqlite",
    "logs_2.sqlite", "session_index.jsonl", ".env", "cookies.sqlite", "build_once.py",
}
SENSITIVE = [
    ("credential assignment", re.compile(r"(?im)^\s*(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\s*[:=]\s*(?!<)[\"']?[^\s\"']{8,}")),
    ("bearer header", re.compile(r"(?i)authorization\s*[:=]\s*bearer\s+\S+")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ("user home path", re.compile(r"(?i)(?:[a-z]:[/\\]users[/\\][^/\\\s]+|/home/[^/\s]+)")),
    ("chat UUID", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)),
]


def fail(message: str) -> None:
    raise ValueError(message)


def main() -> None:
    files = sorted(p for p in ROOT.rglob("*") if p.is_file())
    relative = {p.relative_to(ROOT).as_posix(): p for p in files}
    if {p.name for p in ROOT.iterdir() if p.is_file()} != EXPECTED_TOP:
        fail("Unexpected top-level file set")
    if any(p.is_symlink() for p in ROOT.rglob("*")):
        fail("Symlink present")
    if any(p.name.lower() in FORBIDDEN_NAMES or p.suffix.lower() in {".sqlite", ".wal", ".log", ".db"} for p in files):
        fail("Forbidden file class present")
    if any(p.stat().st_size > 100_000 for p in files):
        fail("Oversized file present")
    role_paths = {f"templates/agents/{role}.toml" for role in EXPECTED_ROLES}
    required = EXPECTED_TOP | role_paths | {
        "templates/AGENTS.global.md", "templates/AGENTS.project.md",
        "templates/config.project.toml", "templates/model-routing.json",
    }
    if set(relative) != required:
        fail(f"Unexpected inventory: missing={sorted(required - set(relative))}, extra={sorted(set(relative) - required)}")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema") != "bos.recovery-sha256.v1":
        fail("Manifest schema")
    expected_hashes = manifest.get("files")
    if not isinstance(expected_hashes, dict) or set(expected_hashes) != set(relative) - {"SHA256SUMS.json"}:
        fail("Manifest inventory")
    for name, expected in expected_hashes.items():
        actual = hashlib.sha256(relative[name].read_bytes()).hexdigest()
        if actual != expected:
            fail(f"SHA256 mismatch: {name}")

    for name, path in relative.items():
        if name in {"SHA256SUMS.json", "validate_bundle.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        for label, pattern in SENSITIVE:
            if pattern.search(text):
                fail(f"Potential {label} in {name}")
    for name in ("templates/config.project.toml", *sorted(role_paths)):
        tomllib.loads(relative[name].read_text(encoding="utf-8"))
    policy = json.loads(relative["templates/model-routing.json"].read_text(encoding="utf-8"))
    if policy.get("project_root") != "<PROJECT_ROOT>" or policy.get("control_home") != "<CONTROL_HOME>":
        fail("Portable placeholders missing")
    config = tomllib.loads(relative["templates/config.project.toml"].read_text(encoding="utf-8"))
    if set(config["agents"]) - {"enabled", "max_concurrent_threads_per_session", "default_subagent_model", "default_subagent_reasoning_effort"} != EXPECTED_ROLES:
        fail("Role registry mismatch")
    for role in EXPECTED_ROLES:
        if config["agents"][role]["config_file"] != f"agents/{role}.toml":
            fail(f"Role path mismatch: {role}")
        data = tomllib.loads(relative[f"templates/agents/{role}.toml"].read_text(encoding="utf-8"))
        if data["name"] != role:
            fail(f"Role name mismatch: {role}")
    print(f"PASS: {len(files)} files, {len(expected_hashes)} SHA256 entries, {len(EXPECTED_ROLES)} roles; no live paths accessed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
