"""Isolated Windows authority checks; execution requires a separate QA decision."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.dont_write_bytecode = True
STAGED = Path(__file__).resolve().parent
SCRATCH = Path(r"D:\3\BOSDev\qa-scratch\bos3-control-home-install-20260928")
if STAGED != SCRATCH / "source" / "staged":
    raise RuntimeError("Authority test must run from its exact staged scratch source.")
def staged_module(name):
    path = STAGED / (name + ".py")
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Required staged source is absent or linked.")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve() != path:
        raise RuntimeError("Authority test loaded a foreign module.")
    return module


core = staged_module("bos_dev")
channel = staged_module("codex_channel")


class FakeTransport:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        return {"status": "queued"}


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        if os.name != "nt":
            self.skipTest("native Windows junction and file identity required")
        qa = SCRATCH / "qa"
        core._no_reparse_parents(SCRATCH)
        if not qa.exists():
            qa.mkdir()
        core._no_reparse_parents(qa)
        self.assertTrue(qa.is_dir())
        self.base = Path(tempfile.mkdtemp(dir=qa, prefix="authority-"))
        core._no_reparse_parents(self.base)
        self.assertEqual(self.base.parent, qa)
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
        try:
            core._no_reparse_parents(SCRATCH / "qa")
            core._no_reparse_parents(self.base)
            if self.alias.exists():
                if core._reparse_tag(self.alias) != 0xA0000003 or self.alias.resolve(strict=True) != self.home:
                    raise AssertionError("Unexpected QA alias; preserve fixture for inspection.")
                os.rmdir(self.alias)
            self._assert_no_reparse_tree(self.base)
            shutil.rmtree(self.base)
        finally:
            for item in reversed(self.patches):
                item.stop()

    def _assert_no_reparse_tree(self, directory):
        for item in directory.iterdir():
            if getattr(item.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise AssertionError("Unexpected QA reparse point; preserve fixture for inspection.")
            if item.is_dir():
                self._assert_no_reparse_tree(item)

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
                       {**self.active, "phase": "SUSPENDED"},
                       {**self.active, "schema": "unknown"},
                       {**self.active, "generation": str(uuid.uuid4())}):
            if anchor is None:
                self.anchor.unlink()
            else:
                self._write(self.anchor, anchor)
            with self.assertRaises(core.ControlHomeError):
                core.resolve_control_home()
        self.assertEqual(json.loads((self.home / "queue.json").read_text())["tasks"], {})

    def test_missing_tampered_and_cross_drive_receipts_refuse(self):
        prepared = Path(self.active["prepared_receipt"]["path"])
        prepared.write_text("tampered", encoding="utf-8")
        with self.assertRaises(core.ControlHomeError):
            core.resolve_control_home()
        prepared.unlink()
        with self.assertRaises(core.ControlHomeError):
            core.resolve_control_home()
        self.active["prepared_receipt"] = {"path": r"C:\other\receipt.json", "sha256": "0" * 64}
        self._write(self.anchor, self.active)
        with self.assertRaises(core.ControlHomeError):
            core.resolve_control_home()

    def test_receipt_acceptance_must_bind_generation_and_hash(self):
        accepted = Path(self.active["migration_acceptance"]["path"])
        self.active["migration_acceptance"] = self._write(accepted, {
            "verdict": "ACCEPT_MIGRATION_COMMIT", "generation": str(uuid.uuid4()),
            "prepared_receipt_sha256": self.active["prepared_receipt"]["sha256"],
        })
        self._write(self.anchor, self.active)
        with self.assertRaises(core.ControlHomeError):
            core.resolve_control_home()

    def test_missing_or_tampered_acceptance_refuses(self):
        accepted = Path(self.active["migration_acceptance"]["path"])
        accepted.write_text("tampered", encoding="utf-8")
        with self.assertRaises(core.ControlHomeError):
            core.resolve_control_home()
        accepted.unlink()
        with self.assertRaises(core.ControlHomeError):
            core.resolve_control_home()

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

    def test_replaced_lock_identity_refuses(self):
        lock = self.home / ".queue.lock"
        lock.rename(self.base / "retired-lock")
        lock.write_bytes(b"\0")
        with self.assertRaises(core.ControlHomeError):
            with core.state_lock(self.home):
                self.fail("Replacement lock was accepted")

    def test_generation_change_after_byte_acquisition_releases_lock(self):
        changed = {**self.active, "generation": str(uuid.uuid4())}
        with patch.object(core, "_authority", side_effect=[self.active, self.active, changed]):
            with self.assertRaises(core.ControlHomeError):
                with core.state_lock(self.home):
                    self.fail("Changed generation was accepted")
        with core.state_lock(self.home):
            pass

    def test_hardlink_state_and_reparse_root_refuse(self):
        observer = self.home / "observer.json"
        observer.unlink()
        os.link(self.home / "config.json", observer)
        with self.assertRaises(core.ControlHomeError):
            core.resolve_control_home()
        observer.unlink()
        self._write(observer, {"cursor": "preserved"})
        real = self.base / "real-home"
        self.home.rename(real)
        try:
            created = subprocess.run(["cmd", "/c", "mklink", "/J", str(self.home), str(real)],
                                     capture_output=True, text=True, timeout=10)
            self.assertEqual(created.returncode, 0, created.stderr)
            with self.assertRaises(core.ControlHomeError):
                core.resolve_control_home()
        finally:
            if self.home.exists() and core._reparse_tag(self.home) == 0xA0000003:
                os.rmdir(self.home)
            real.rename(self.home)

    def test_transferred_delivery_and_opaque_record_are_preserved(self):
        target = channel.TARGETS["main"]
        digest = hashlib.sha256(b"one").hexdigest()
        opaque = {"legacy_extension": ["unchanged", 7]}
        for status in ("ACKNOWLEDGED", "UNCONFIRMED", "SENDING"):
            ledger = self.home / "codex-channel-delivery.json"
            self._write(ledger, {"schema": 1, "messages": {
                "old-id": {"target": target, "sha256": digest, "status": status},
                "opaque-id": opaque,
            }})
            before = ledger.read_bytes()
            fake = FakeTransport()
            with patch.dict(os.environ, {"CODEX_THREAD_ID": channel.TARGETS["observer"]}):
                with patch.object(channel, "AppTools", return_value=fake):
                    if status == "ACKNOWLEDGED":
                        result = channel.deliver(target, "one", "old-id", self.home)
                        self.assertTrue(result["duplicate_suppressed"])
                    else:
                        with self.assertRaises(channel.ChannelError):
                            channel.deliver(target, "one", "old-id", self.home)
            self.assertEqual(fake.calls, [])
            self.assertEqual(ledger.read_bytes(), before)
            self.assertEqual(json.loads(ledger.read_text())["messages"]["opaque-id"], opaque)

    def test_incomplete_relevant_record_refuses_without_send(self):
        target = channel.TARGETS["main"]
        self._write(self.home / "codex-channel-delivery.json", {"schema": 1, "messages": {
            "other-id": {"target": target, "status": "UNCONFIRMED"},
            "opaque-id": {"legacy_extension": "unrelated"},
        }})
        fake = FakeTransport()
        with patch.dict(os.environ, {"CODEX_THREAD_ID": channel.TARGETS["observer"]}):
            with patch.object(channel, "AppTools", return_value=fake):
                with self.assertRaises(channel.ChannelError):
                    channel.deliver(target, "new prompt", "new-id", self.home)
        self.assertEqual(fake.calls, [])

    def test_two_processes_compete_for_one_byte_lock(self):
        child = """import importlib.util
import sys
from pathlib import Path
sys.dont_write_bytecode = True
provider = Path(sys.argv[1]).resolve(strict=True)
spec = importlib.util.spec_from_file_location('bos_dev', provider)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
c.CONTROL_HOME, c.LEGACY_CONTROL_HOME, c.AUTHORITY_ANCHOR, c.EVIDENCE_ROOT, c._SOURCE_ARCHIVE = map(Path, sys.argv[2:])
with c.state_lock(c.LEGACY_CONTROL_HOME, timeout=0.3):
    pass
"""
        paths = [self.home, self.alias, self.anchor, self.evidence, self.archive]
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        provider = STAGED / "bos_dev.py"
        self.assertEqual(Path(core.__file__).resolve(), provider)
        with core.state_lock(self.home):
            blocked = subprocess.run([sys.executable, "-B", "-c", child, str(provider), *map(str, paths)],
                                     cwd=STAGED, env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("Timed out waiting for queue lock", blocked.stderr)
        acquired = subprocess.run([sys.executable, "-B", "-c", child, str(provider), *map(str, paths)],
                                  cwd=STAGED, env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(acquired.returncode, 0, acquired.stderr)


if __name__ == "__main__":
    unittest.main()
