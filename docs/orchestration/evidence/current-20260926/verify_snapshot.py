"""Static provenance receipt. Does not start the app, suites or CI."""
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


def main():
    inventory = json.loads((ROOT / "docs/orchestration/consolidation-20260926/INVENTORY.json").read_text(encoding="utf-8"))
    head = git("rev-parse", "HEAD")
    if head.returncode:
        raise RuntimeError(head.stderr)
    sources = [entry["sha"] for entry in inventory["commits"]]
    sources.append("a3c0596ab611290ba5ad199f55309812093f908b")
    ancestry = []
    for sha in sources:
        result = git("merge-base", "--is-ancestor", sha, "HEAD")
        ancestry.append({"sha": sha, "exit_code": result.returncode, "stderr": result.stderr.strip()})
    digest = runpy.run_path(str(ROOT / "scripts/verify.py"))["source_digest"]()
    identity_paths = [
        "frontend/boss_app_source.html", "frontend/boss_app_html.html", "assets/app.js",
        "erp/module_registry.py", "scripts/checks/module_column_content.cjs",
        *[f"scripts/checks/fixtures/module_catalog/{role}.json" for role in ("ceo", "manager", "observer")],
    ]
    identity = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in identity_paths}
    receipt = {
        "scope": "Git ancestry and filesystem source identity only; no product test execution",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "head": head.stdout.strip(), "inventory_commit_count": len(inventory["commits"]),
        "checked_ancestors": len(ancestry), "all_ancestors_present": all(row["exit_code"] == 0 for row in ancestry),
        "runtime_source_sha256": digest, "file_sha256": identity, "ancestry": ancestry,
    }
    (HERE / "SNAPSHOT_CHECK.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in receipt.items() if key != "ancestry"}, indent=2))
    return 0 if receipt["all_ancestors_present"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
