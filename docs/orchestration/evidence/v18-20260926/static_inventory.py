"""Parse reviewed Python and JSON source without importing BoS modules."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys


PYTHON_DIRS = ("ai_assistant", "branches", "boss_project", "employees", "erp", "finance",
               "operations", "scripts", "tasks", "tests")
PYTHON_TOP = ("manage.py", "demo_settings.py", "server_settings.py", "verification_settings.py")
JSON_DIRS = ("ai_assistant", "branches", "boss_project", "employees", "erp", "finance",
             "operations", "scripts", "tasks", "frontend")
JSON_TOP = ("package.json", "package-lock.json")
JSON_CURRENT_POINTERS = ("docs/tracker/activity.json", "docs/orchestration/CURRENT_BASELINE.json",
                         "docs/orchestration/STATE.json", "docs/orchestration/QUEUE.json")


def files(root: Path, directories: tuple[str, ...], suffix: str, top: tuple[str, ...] = ()) -> list[Path]:
    selected: set[Path] = set()
    for directory in directories:
        path = root / directory
        if path.is_dir():
            selected.update(item for item in path.rglob("*" + suffix) if item.is_file())
    selected.update(root / name for name in top if (root / name).is_file())
    return sorted(selected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.project_root.resolve()
    if not (root / "manage.py").is_file():
        parser.error("--project-root must be the reviewed candidate")
    python_files = files(root, PYTHON_DIRS, ".py", PYTHON_TOP)
    json_files = files(root, JSON_DIRS, ".json", JSON_TOP)
    json_files = sorted(set(json_files).union(root / name for name in JSON_CURRENT_POINTERS
                                               if (root / name).is_file()))
    errors: list[dict[str, str]] = []
    for file in python_files:
        try:
            ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except (OSError, SyntaxError, UnicodeError) as error:
            errors.append({"kind": "python_ast", "file": file.relative_to(root).as_posix(), "error": str(error)})
    for file in json_files:
        try:
            json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError) as error:
            errors.append({"kind": "json", "file": file.relative_to(root).as_posix(), "error": str(error)})
    print(json.dumps({"scope": {"python_dirs": PYTHON_DIRS, "python_top": PYTHON_TOP,
                                "json_dirs": JSON_DIRS, "json_top": JSON_TOP,
                                "json_current_pointers": JSON_CURRENT_POINTERS},
                      "counts": {"python_ast": len(python_files), "runtime_json": len(json_files)},
                      "errors": errors}, ensure_ascii=False, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
