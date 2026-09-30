"""Isolated Windows authority checks; execution requires a separate QA decision."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bos_dev as core
import codex_channel as channel


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        if os.name != "nt":
            self.skipTest("native Windows junction and file identity required")
        qa = Path(__file__).resolve().parents[1] / "qa"
        qa.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=qa, prefix="authority-")
        self.base = Path(self.temp.name)
        self.home = self.base / "D-home"
        self.alias = self.base / "C-alias"
        self.anchor = self.base / "authority.json"
        self.evidence = self.base / "evidence"
        self.archive = self.base / "C-archive"
        self.home.mkdir()
        self.evidence.mkdir()
        self.patches = [patch.object(core, key, value) for key, value in {
            "CONTROL_HOME": self.home, "LEGACY_CONTROL_HOME": self.alias,
            "AUTHORITY_ANCHOR": self.anchor, "EVIDENCE_ROOT": self.evidence,
            "_SOURCE_ARCHIVE": self.archive,
        }.items()]
        for item in self.patches:
            item.start()
        self.addCleanup(self._cleanup)
        self._write(self.home / "config.json", {"version": 1, "lanes": {}})
        self._write(self.home / "queue.json", {"version": 1, "tasks": {}})
        self._write(self.home / "observer.json", {"cursor": "preserved"})
        self._write(self.home / "codex-channel-delivery.json", {"schema": 1, "messages": {}})
        (self.home / ".queue.lock").write_bytes(b"\0")
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(self.alias), str(self.home)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.generation = str(uuid.uuid4())
        prepared = self._write(self.evidence / "prepared.json", {"generation": self.generation})
        accepted = self._write(self.evidence / "accepted.json", {
            "verdict": "ACCEPT_MIGRATION_COMMIT", "generation": self.generation,
            "prepared_receipt_sha256": prepared["sha256"],
        })
        self.active = {
            "schema": core.AUTHORITY_SCHEMA, "generation": self.generation, "phase": "ACTIVE",
            "home": str(self.home), "legacy_alias": str(self.alias),
            "source_archive": str(self.archive), "root_identity": core._identity(self.home)[0],
            "lock_identity": core._identity(self.home / ".queue.lock")[0],
            "prepared_receipt": prepared, "migration_acceptance": accepted,
            "activated_at_utc": "2026-09-28T07:00:00Z",
        }
        self._write(self.anchor, self.active)

    def _cleanup(self):
        if self.alias.exists() and core._reparse_tag(self.alias) == 0xA0000003:
            os.rmdir(self.alias)
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def _write(self, path, value):
        data = (json.dumps(value) + "\n").encode("utf-8")
        path.write_bytes(data)
        return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}

    def test_active_default_alias_and_target_share_identity(self):
        self.assertEqual(core.resolve_control_home(), self.home)
        self.assertEqual(core.resolve_control_home(self.alias), self.home)
        self.assertEqual(core.resolve_control_home(self.home), self.home)
        self.assertEqual(core._identity(self.alias)[0], core._identity(self.home)[0])
        self.assertEqual(core._identity(self.alias / ".queue.lock")[0], core._identity(self.home / ".queue.lock")[0])
        self.assertEqual(json.loads((self.home / "observer.json").read_text())["cursor"], "preserved")

    def test_missing_prepared_and_invalid_authority_refuse(self):
        for anchor in (None, {**self.active, "phase": "PREPARED"},
                       {**self.active, "schema": "unknown"},
                       {**self.active, "generation": str(uuid.uuid4())}):
            if anchor is None:
                self.anchor.unlink()
            else:
                self._write(self.anchor, anchor)
            with self.assertRaises(core.ControlHomeError):
                core.resolve_control_home()
        self.assertEqual(json.loads((self.home / "queue.json").read_text())["tasks"], {})

    def test_unlisted_and_escaping_names_refuse(self):
        for name in (self.base, str(self.home) + "\\..\\D-home", "relative", "\\\\server\\share",
                     str(self.home) + ":stream", str(self.archive)):
            with self.assertRaises(core.ControlHomeError):
                core.resolve_control_home(name)

    def test_missing_ledger_or_lock_refuses_before_transport(self):
        for name in ("codex-channel-delivery.json", ".queue.lock"):
            path = self.home / name
            backup = path.read_bytes()
            path.unlink()
            try:
                with patch.object(channel, "AppTools") as transport:
                    with self.assertRaises(core.ControlHomeError):
                        channel.deliver(channel.TARGETS["main"], "one", "authority-1", self.home)
                transport.assert_not_called()
            finally:
                path.write_bytes(backup)
                if name == ".queue.lock":
                    self.active["lock_identity"] = core._identity(path)[0]
                    self._write(self.anchor, self.active)

    def test_invalid_ledger_refuses_before_transport(self):
        ledger = self.home / "codex-channel-delivery.json"
        self._write(ledger, {"schema": 1, "messages": []})
        with patch.object(channel, "AppTools") as transport:
            with self.assertRaises(core.ControlHomeError):
                channel.deliver(channel.TARGETS["main"], "one", "authority-invalid-ledger", self.home)
        transport.assert_not_called()

    def test_cli_self_refuses_before_transport(self):
        message = self.base / "message.txt"
        message.write_text("one", encoding="utf-8")
        argv = ["channel", "send", "--home", str(self.home), "--target", "observer",
                "--message-file", str(message), "--message-id", "self-1"]
        with patch.dict(os.environ, {"CODEX_THREAD_ID": channel.TARGETS["observer"]}):
            with patch.object(sys, "argv", argv), patch.object(channel, "AppTools") as transport:
                with self.assertRaises(channel.ChannelError):
                    channel.main()
        transport.assert_not_called()

    def test_existing_lock_is_not_recreated_by_init(self):
        before = (self.home / ".queue.lock").read_bytes()
        self.assertEqual(core.initialize(self.home)["created"], [])
        self.assertEqual((self.home / ".queue.lock").read_bytes(), before)

    def test_two_processes_compete_for_one_byte_lock(self):
        child = """import sys
from pathlib import Path
import bos_dev as c
c.CONTROL_HOME, c.LEGACY_CONTROL_HOME, c.AUTHORITY_ANCHOR, c.EVIDENCE_ROOT, c._SOURCE_ARCHIVE = map(Path, sys.argv[1:])
with c.state_lock(c.LEGACY_CONTROL_HOME, timeout=0.3):
    pass
"""
        paths = [self.home, self.alias, self.anchor, self.evidence, self.archive]
        env = {**os.environ, "PYTHONPATH": str(Path(core.__file__).resolve().parent)}
        with core.state_lock(self.home):
            blocked = subprocess.run([sys.executable, "-c", child, *map(str, paths)],
                                     env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("Timed out waiting for queue lock", blocked.stderr)
        acquired = subprocess.run([sys.executable, "-c", child, *map(str, paths)],
                                  env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(acquired.returncode, 0, acquired.stderr)


if __name__ == "__main__":
    unittest.main()
