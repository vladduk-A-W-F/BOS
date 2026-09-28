"""Synthetic control-channel checks. No real messages or model runs."""
import json
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import atexit
from contextlib import nullcontext
from unittest.mock import patch

CORE_STAGED = Path(__file__).resolve().parents[2] / "source" / "staged"
_guard_path = Path(__file__).with_name('test-control-home-consumers.py')
_guard_spec = importlib.util.spec_from_file_location('consumer_cleanup_guard', _guard_path)
_guard_module = importlib.util.module_from_spec(_guard_spec)
_guard_spec.loader.exec_module(_guard_module)
cleanup_boundary = _guard_module.cleanup_boundary
guarded_cleanup = _guard_module.guarded_cleanup
SCRATCH_PARENT = CORE_STAGED.parents[1]
for _parent in (SCRATCH_PARENT, *SCRATCH_PARENT.parents):
    if _parent == _parent.parent:
        break
    _info = _parent.lstat()
    if not stat.S_ISDIR(_info.st_mode) or getattr(_info, 'st_file_attributes', 0) & 0x400:
        raise RuntimeError('Unsafe scratch parent')
_TEST_ROOT = tempfile.TemporaryDirectory(dir=SCRATCH_PARENT, prefix="channel-source-scratch-")
_root_cleanup = cleanup_boundary(_TEST_ROOT, SCRATCH_PARENT, 'channel-source-scratch-')
atexit.register(guarded_cleanup, _root_cleanup)
SCRATCH = Path(_TEST_ROOT.name)
HOME = SCRATCH / "control-home"
TOOLS = HOME / "tools"
TOOLS.mkdir(parents=True)
_replacements = {
    'LEGACY_CONTROL_HOME = Path(r"C:\\Users\\user\\AppData\\Local\\BOSDev")':
        'LEGACY_CONTROL_HOME = Path(' + repr(str(SCRATCH / 'legacy')) + ')',
    'CONTROL_HOME = Path(r"D:\\3\\BOSDev\\control-home")':
        'CONTROL_HOME = Path(' + repr(str(HOME)) + ')',
    'AUTHORITY_ANCHOR = Path(r"D:\\3\\BOSDev\\control-home-authority.json")':
        'AUTHORITY_ANCHOR = Path(' + repr(str(SCRATCH / 'anchor.json')) + ')',
    'EVIDENCE_ROOT = Path(r"D:\\3\\BOSDev\\evidence\\bos3-control-home-install-20260928")':
        'EVIDENCE_ROOT = Path(' + repr(str(SCRATCH / 'evidence')) + ')',
    '_SOURCE_ARCHIVE = Path(r"C:\\Users\\user\\AppData\\Local\\BOSDev.pre-D-20260928")':
        '_SOURCE_ARCHIVE = Path(' + repr(str(SCRATCH / 'archive')) + ')',
}
raw = (CORE_STAGED / 'bos_dev.py').read_bytes()
text = raw.decode('utf-8-sig')
for before, after in _replacements.items():
    if text.count(before) != 1:
        raise RuntimeError('Unexpected core source literal count')
    text = text.replace(before, after, 1)
copied = text.encode('utf-8')
(TOOLS / 'bos_dev.py').write_bytes(copied)
_source_hashes = {'bos_dev': (hashlib.sha256(raw).hexdigest(), hashlib.sha256(copied).hexdigest())}
for name in ('bos_dev', 'codex_channel'):
    if name == 'codex_channel':
        raw_channel = (CORE_STAGED / 'codex_channel.py').read_bytes()
        (TOOLS / 'codex_channel.py').write_bytes(raw_channel)
        _source_hashes[name] = (hashlib.sha256(raw_channel).hexdigest(), hashlib.sha256(raw_channel).hexdigest())
    path = TOOLS / (name + '.py')
    if hashlib.sha256(path.read_bytes()).hexdigest() != _source_hashes[name][1]:
        raise RuntimeError('Scratch test dependency copy changed')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if name in sys.modules:
        raise RuntimeError('Foreign cached test dependency')
    sys.modules[name] = module
    spec.loader.exec_module(module)
    if Path(module.__file__) != path:
        raise RuntimeError('Scratch test dependency origin changed')
channel = sys.modules['codex_channel']
ControlHomeError = sys.modules['bos_dev'].ControlHomeError


class FakeClient:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def call(self, tool, args):
        self.calls.append((tool, args))
        if self.fail:
            raise channel.ChannelError("synthetic timeout")
        return {"status": "queued", "threadId": args["threadId"]}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=SCRATCH, prefix="channel-unit-")
        self.cleanup = cleanup_boundary(self.tmp, SCRATCH, 'channel-unit-')
        self.home = Path(self.tmp.name)
        (self.home / "codex-channel-delivery.json").write_text(
            json.dumps({"schema": 1, "messages": {}}), encoding="utf-8")
        self.client = FakeClient()
        self.env = patch.dict(os.environ, {"CODEX_THREAD_ID": channel.TARGETS["observer"]})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        guarded_cleanup(self.cleanup)

    def deliver(self, target, prompt, message_id):
        """Keep ledger assertions synthetic while exercising public argument order."""
        with patch.object(channel, "resolve_control_home", return_value=self.home):
            with patch.object(channel, "state_lock", return_value=nullcontext()):
                with patch.object(channel, "AppTools", return_value=self.client):
                    return channel.deliver(target, prompt, message_id, self.home)

    def test_duplicate_id_does_not_send_twice(self):
        self.deliver(channel.TARGETS["main"], "one", "test-1")
        r = self.deliver(channel.TARGETS["main"], "one", "test-1")
        self.assertTrue(r["duplicate_suppressed"])
        self.assertEqual(len(self.client.calls), 1)

    def test_changed_content_cannot_reuse_id(self):
        self.deliver(channel.TARGETS["main"], "one", "test-1")
        with self.assertRaises(channel.ChannelError):
            self.deliver(channel.TARGETS["main"], "changed", "test-1")
        self.assertEqual(len(self.client.calls), 1)

    def test_new_id_cannot_repeat_identical_message(self):
        self.deliver(channel.TARGETS["main"], "one", "test-1")
        with self.assertRaises(channel.ChannelError):
            self.deliver(channel.TARGETS["main"], "one", "test-2")
        self.assertEqual(len(self.client.calls), 1)

    def test_integrator_exact_target_and_duplicate_suppression(self):
        first = self.deliver(channel.TARGETS["integrator"], "current BoS 3 report", "integrator-report-1")
        duplicate = self.deliver(channel.TARGETS["integrator"], "current BoS 3 report", "integrator-report-1")
        self.assertFalse(first["duplicate_suppressed"])
        self.assertTrue(duplicate["duplicate_suppressed"])
        self.assertEqual(self.client.calls, [("send_message_to_thread", {
            "threadId": "01a0dd56-ca2d-79c0-b159-bde80074a026", "hostId": "local", "prompt": "current BoS 3 report",
        })])
        with self.assertRaises(channel.ChannelError):
            self.deliver(channel.TARGETS["integrator"], "current BoS 3 report", "integrator-report-2")
        self.assertEqual(len(self.client.calls), 1)

    def test_uncertain_write_is_not_repeated(self):
        self.client.fail = True
        with self.assertRaises(channel.ChannelError):
            self.deliver(channel.TARGETS["integrator"], "one", "test-1")
        ledger = json.loads((self.home / "codex-channel-delivery.json").read_text())
        self.assertEqual(ledger["messages"]["test-1"]["status"], "UNCONFIRMED")
        with self.assertRaises(channel.ChannelError):
            self.deliver(channel.TARGETS["integrator"], "one", "test-1")
        self.assertEqual(len(self.client.calls), 1)

    def test_outside_target_and_self_are_rejected(self):
        def reject_before_transport(target, message_id):
            with patch.object(channel, "resolve_control_home", return_value=self.home):
                with patch.object(channel, "AppTools") as transport:
                    with self.assertRaises(channel.ChannelError):
                        channel.deliver(target, "one", message_id, channel.HOME_DIR)
            transport.assert_not_called()

        for target in ("other-thread", channel.TARGETS["observer"]):
            reject_before_transport(target, "test-1")
        with patch.dict(os.environ, {"CODEX_THREAD_ID": channel.TARGETS["integrator"]}):
            reject_before_transport(channel.TARGETS["integrator"], "test-integrator-self")
        for target in channel.TARGETS.values():
            with patch.dict(os.environ, {"CODEX_THREAD_ID": target}):
                reject_before_transport(target, "test-2")
        self.assertEqual(self.client.calls, [])

    def test_writer_report_to_observer_is_delivered_once(self):
        with patch.dict(os.environ, {"CODEX_THREAD_ID": channel.TARGETS["writer"]}):
            self.deliver(channel.TARGETS["observer"], "completed report", "writer-report-1")
            result = self.deliver(channel.TARGETS["observer"], "completed report", "writer-report-1")
        self.assertTrue(result["duplicate_suppressed"])
        self.assertEqual(self.client.calls, [("send_message_to_thread", {
            "threadId": channel.TARGETS["observer"], "hostId": "local", "prompt": "completed report",
        })])

    def test_main_can_report_to_observer(self):
        with patch.dict(os.environ, {"CODEX_THREAD_ID": channel.TARGETS["main"]}):
            result = self.deliver(channel.TARGETS["observer"], "allocation report", "main-report-1")
        self.assertEqual(result["delivery"]["status"], "ACKNOWLEDGED")
        self.assertEqual(len(self.client.calls), 1)

    def test_design_reports_and_main_assignments_use_designated_targets(self):
        with patch.dict(os.environ, {"CODEX_THREAD_ID": channel.TARGETS["main"]}):
            self.deliver(channel.TARGETS["design"], "design assignment", "design-assignment-1")
        with patch.dict(os.environ, {"CODEX_THREAD_ID": channel.TARGETS["design"]}):
            self.deliver(channel.TARGETS["observer"], "design result", "design-report-1")
        self.assertEqual([a['threadId'] for _, a in self.client.calls], [channel.TARGETS['design'], channel.TARGETS['observer']])

    def test_nonlegacy_home_is_refused_before_transport(self):
        with patch.object(channel, "AppTools") as transport:
            with self.assertRaises(ControlHomeError):
                channel.deliver(channel.TARGETS["main"], "one", "nonlegacy-home-1", self.home)
        transport.assert_not_called()

    def test_origin_metadata_is_current_task(self):
        c = object.__new__(channel.AppTools)
        c.catalog = {"wait_threads": {}}
        calls = []
        c.rpc = lambda method, params: calls.append((method, params)) or {"content": [{"type": "text", "text": "{\"polls\":[]}"}]}
        self.assertEqual(c.call("wait_threads", {"targets": []}), {"polls": []})
        self.assertEqual(calls[0][1]["_meta"]["codexThreadId"], channel.TARGETS["observer"])

    def test_unavailable_desktop_does_not_start_anything(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(channel.ChannelError):
                channel.installed_runtime()

    def test_protocol_eof_fails_promptly(self):
        with self.assertRaises(channel.ChannelError):
            channel.AppTools(command=[sys.executable, "-c", "pass"], timeout=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
