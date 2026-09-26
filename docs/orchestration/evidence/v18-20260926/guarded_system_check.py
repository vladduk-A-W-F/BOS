"""One-shot, opt-in guarded Django system-check harness for VERIFY-V18-BOUNDED.

This helper is intentionally not an application command.  It must be invoked
only after review, with an existing disposable media directory outside the
candidate checkout.  The child installs its audit hook before Django or project
imports and refuses database connections, sockets, subprocesses, and every
filesystem mutation.  Its parent captures child output without making files.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap


CHILD = r'''
import json
import os
from pathlib import Path
import sys

attempts = {"sqlite_connect": 0, "socket": 0, "subprocess": 0,
            "write_open": 0, "filesystem_mutation": 0}
mutations = {"os.chdir", "os.chmod", "os.chown", "os.link", "os.mkdir",
             "os.remove", "os.rename", "os.replace", "os.rmdir",
             "os.symlink", "os.truncate", "os.utime"}
write_flags = (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC)

def blocked(kind, event):
    attempts[kind] += 1
    raise RuntimeError("AUDIT_GUARD_BLOCKED:" + kind + ":" + event)

def audit(event, args):
    if event == "sqlite3.connect":
        blocked("sqlite_connect", event)
    if event.startswith("socket."):
        blocked("socket", event)
    if event == "subprocess.Popen" or event == "os.system":
        blocked("subprocess", event)
    if event in mutations:
        blocked("filesystem_mutation", event)
    if event == "open":
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
        if (isinstance(mode, str) and any(flag in mode for flag in ("w", "a", "x", "+"))) or flags & write_flags:
            blocked("write_open", event)

sys.addaudithook(audit)
if not sys.dont_write_bytecode:
    raise RuntimeError("AUDIT_GUARD_BLOCKED:bytecode:python-not-started-with-B")

expected_media = Path(os.environ["BOS_TEST_MEDIA"]).resolve()
print(json.dumps({"guard": "installed-before-django-import", "python": sys.version,
                  "settings_module": os.environ.get("DJANGO_SETTINGS_MODULE"),
                  "verify_db": os.environ.get("BOS_VERIFY_DB"),
                  "database_name": os.environ.get("BOS_TEST_DB_NAME"),
                  "media": str(expected_media)}, ensure_ascii=False, sort_keys=True))

import django
django.setup()
from django.conf import settings
from django.core.management import call_command

database = settings.DATABASES
if set(database) != {"default"}:
    raise RuntimeError("AUDIT_GUARD_BLOCKED:database-aliases:" + repr(sorted(database)))
default = database["default"]
if default.get("ENGINE") != "django.db.backends.sqlite3" or str(default.get("NAME")) != ":memory:":
    raise RuntimeError("AUDIT_GUARD_BLOCKED:database-config:" + repr(default))
if Path(settings.MEDIA_ROOT).resolve() != expected_media:
    raise RuntimeError("AUDIT_GUARD_BLOCKED:media-config:" + str(settings.MEDIA_ROOT))

print(json.dumps({"guard": "precheck-assertions-passed", "django": django.get_version(),
                  "database": {"aliases": sorted(database), "engine": default.get("ENGINE"),
                               "name": str(default.get("NAME"))},
                  "media": str(Path(settings.MEDIA_ROOT).resolve()), "attempts": attempts},
                 ensure_ascii=False, sort_keys=True))
call_command("check", tags=["models", "urls", "security"], verbosity=1)
if any(attempts.values()):
    raise RuntimeError("AUDIT_GUARD_BLOCKED:intercepted-event:" + repr(attempts))
print(json.dumps({"guard": "check-finished", "attempts": attempts}, ensure_ascii=False, sort_keys=True))
'''


def outside(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return True
    return False


def output_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--media", type=Path, required=True,
                        help="existing disposable directory outside project-root")
    args = parser.parse_args()
    root, media = args.project_root.resolve(), args.media.resolve()
    if not root.is_dir() or not (root / "verification_settings.py").is_file():
        parser.error("--project-root must be the reviewed BoS candidate")
    if not media.is_dir() or not outside(media, root):
        parser.error("--media must already exist outside project-root")
    environment = dict(os.environ)
    environment.update(DJANGO_SETTINGS_MODULE="verification_settings", BOS_VERIFY_DB="sqlite",
                       BOS_TEST_DB_NAME=":memory:", BOS_TEST_MEDIA=str(media),
                       BOS_DATA_MODE="demo", PYTHONDONTWRITEBYTECODE="1")
    try:
        result = subprocess.run([sys.executable, "-B", "-c", textwrap.dedent(CHILD)], cwd=root,
                                env=environment, capture_output=True, text=True, encoding="utf-8", timeout=60)
    except subprocess.TimeoutExpired as error:
        print(json.dumps({"parent": "guarded-system-check", "project_root": str(root),
                          "media": str(media), "child_exit": 124, "result": "TIMEOUT"},
                         ensure_ascii=False, sort_keys=True))
        timeout_stdout, timeout_stderr = output_text(error.stdout), output_text(error.stderr)
        if timeout_stdout:
            print(timeout_stdout, end="" if timeout_stdout.endswith("\n") else "\n")
        if timeout_stderr:
            print(timeout_stderr, file=sys.stderr, end="" if timeout_stderr.endswith("\n") else "\n")
        return 124
    print(json.dumps({"parent": "guarded-system-check", "project_root": str(root),
                      "media": str(media), "child_exit": result.returncode},
                     ensure_ascii=False, sort_keys=True))
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
