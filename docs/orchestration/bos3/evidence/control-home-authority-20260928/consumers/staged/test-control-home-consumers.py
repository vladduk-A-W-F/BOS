"""Prepared scratch-only consumer checks; run only after independent admission."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

STAGED = Path(__file__).resolve().parent
SOURCE = STAGED.parents[1] / 'source' / 'staged'
_PRESERVE = set()


def _ordinary_directory(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise RuntimeError('Scratch directory redirected or replaced')
    return info.st_dev, info.st_ino


def cleanup_boundary(temp, parent, prefix):
    temp._finalizer.detach()
    root = Path(temp.name)
    if root.parent != parent or not root.name.startswith(prefix):
        raise RuntimeError('Scratch target outside assigned parent')
    parent_identity = _ordinary_directory(parent)
    root_identity = _ordinary_directory(root)
    return root, parent, prefix, parent_identity, root_identity


def guarded_cleanup(boundary, *, known_symlink_leaf=False):
    root, parent, prefix, parent_identity, root_identity = boundary
    try:
        if any(saved == root or root in saved.parents for saved in _PRESERVE):
            raise RuntimeError('Earlier cleanup refusal preserves this fixture')
        if root.parent != parent or not root.name.startswith(prefix):
            raise RuntimeError('Scratch target path changed')
        for ancestor in (parent, *parent.parents):
            if ancestor == ancestor.parent:
                break
            _ordinary_directory(ancestor)
        if (_ordinary_directory(parent) != parent_identity
                or _ordinary_directory(root) != root_identity
                or os.path.normcase(str(root.resolve(strict=True))) != os.path.normcase(str(root))):
            raise RuntimeError('Scratch target identity or containment changed')
        if known_symlink_leaf:
            home = root / 'control-home'
            tools = home / 'tools'
            _ordinary_directory(home)
            _ordinary_directory(tools)
            leaf = tools / 'bos_dev.py'
            info = leaf.lstat()
            if not stat.S_ISLNK(info.st_mode) or not getattr(info, 'st_file_attributes', 0) & 0x400:
                raise RuntimeError('Known symlink leaf changed')
            leaf.unlink()
        pending = [root]
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    info = entry.stat(follow_symlinks=False)
                    if getattr(info, 'st_file_attributes', 0) & 0x400:
                        raise RuntimeError('Unexpected reparse point in scratch fixture')
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(Path(entry.path))
                    elif not stat.S_ISREG(info.st_mode):
                        raise RuntimeError('Unexpected scratch entry type')
        if (_ordinary_directory(parent) != parent_identity
                or _ordinary_directory(root) != root_identity
                or os.path.normcase(str(root.resolve(strict=True))) != os.path.normcase(str(root))):
            raise RuntimeError('Scratch target changed before recursive cleanup')
        shutil.rmtree(root)
    except BaseException:
        _PRESERVE.add(root)
        raise


class ConsumerAuthorityTests(unittest.TestCase):
    def setUp(self):
        parent = STAGED.parents[1]
        for part in (parent, *parent.parents):
            if part == part.parent:
                break
            info = part.lstat()
            if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise RuntimeError('Unsafe scratch parent')
        self.temp = tempfile.TemporaryDirectory(dir=parent, prefix='bos-consumer-scratch-')
        self.cleanup = cleanup_boundary(self.temp, parent, 'bos-consumer-scratch-')
        self.known_symlink_leaf = False
        self.root = Path(self.temp.name)
        self.home = self.root / 'control-home'
        self.setup = self.root / 'setup'
        self.tools = self.home / 'tools'
        self.setup.mkdir()
        self.tools.mkdir(parents=True)
        self.hashes = {}
        self.stage(SOURCE / 'bos_dev.py', self.tools, {
            'LEGACY_CONTROL_HOME = Path(r"C:\\Users\\user\\AppData\\Local\\BOSDev")':
                'LEGACY_CONTROL_HOME = Path(' + repr(str(self.root / 'legacy')) + ')',
            'CONTROL_HOME = Path(r"D:\\3\\BOSDev\\control-home")':
                'CONTROL_HOME = Path(' + repr(str(self.home)) + ')',
            'AUTHORITY_ANCHOR = Path(r"D:\\3\\BOSDev\\control-home-authority.json")':
                'AUTHORITY_ANCHOR = Path(' + repr(str(self.root / 'anchor.json')) + ')',
            'EVIDENCE_ROOT = Path(r"D:\\3\\BOSDev\\evidence\\bos3-control-home-install-20260928")':
                'EVIDENCE_ROOT = Path(' + repr(str(self.root / 'evidence')) + ')',
            '_SOURCE_ARCHIVE = Path(r"C:\\Users\\user\\AppData\\Local\\BOSDev.pre-D-20260928")':
                '_SOURCE_ARCHIVE = Path(' + repr(str(self.root / 'archive')) + ')',
        })
        self.stage(SOURCE / 'codex_channel.py', self.tools, {})
        self.stage(STAGED / 'local_flow.py', self.setup, {
            "DEFAULT_HOME = Path('D:/3/BOSDev/control-home')":
                'DEFAULT_HOME = Path(' + repr(str(self.home)) + ')',
            "DEFAULT_ROOT = Path('D:/3/BOSDev')":
                'DEFAULT_ROOT = Path(' + repr(str(self.root)) + ')',
        })
        self.stage(STAGED / 'repo_health.py', self.setup, {
            'DEFAULT_HOME = Path("D:/3/BOSDev/control-home")':
                'DEFAULT_HOME = Path(' + repr(str(self.home)) + ')',
            'DEFAULT_ROOT = Path("D:/3/BOSDev")':
                'DEFAULT_ROOT = Path(' + repr(str(self.root)) + ')',
        })
        self.stage(STAGED / 'bos_flow.py', self.setup, {
            "ROOT = Path('D:/3/BOSDev')":
                'ROOT = Path(' + repr(str(self.root)) + ')',
        })

    def tearDown(self):
        for name in ('bos_flow_scratch', 'repo_health_scratch', 'local_flow', 'bos_dev', 'codex_channel'):
            sys.modules.pop(name, None)
        guarded_cleanup(self.cleanup, known_symlink_leaf=self.known_symlink_leaf)

    def stage(self, source, directory, replacements):
        raw = source.read_bytes()
        text = raw.decode('utf-8-sig')
        for old, new in replacements.items():
            self.assertEqual(text.count(old), 1, 'Unexpected literal count: ' + old)
            text = text.replace(old, new, 1)
        copied = text.encode('utf-8')
        target = directory / source.name
        target.write_bytes(copied)
        self.hashes[source.name] = (hashlib.sha256(raw).hexdigest(), hashlib.sha256(copied).hexdigest())
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), self.hashes[source.name][1])

    def load(self, name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        return module

    def flow(self):
        return self.load('bos_flow_scratch', self.setup / 'bos_flow.py')

    def health(self):
        return self.load('repo_health_scratch', self.setup / 'repo_health.py')

    def test_exact_scratch_origin(self):
        flow = self.flow()
        for module, name in ((flow._provider, 'bos_dev.py'), (flow.channel, 'codex_channel.py')):
            path = self.tools / name
            self.assertEqual(module.__file__, str(path))
            self.assertEqual(module.__bos_fixed_source__, (str(path), hashlib.sha256(path.read_bytes()).hexdigest()))
        self.assertEqual(flow.local_flow.__file__, str(self.setup / 'local_flow.py'))

    def test_missing_provider_never_uses_setup_fallback(self):
        (self.tools / 'bos_dev.py').unlink()
        (self.setup / 'bos_dev.py').write_text('raise AssertionError("fallback executed")\n', encoding='utf-8')
        with self.assertRaises((FileNotFoundError, RuntimeError)):
            self.flow()
        self.assertNotIn('bos_dev', sys.modules)

    def test_foreign_cached_provider_refused(self):
        sys.modules['bos_dev'] = types.ModuleType('bos_dev')
        with self.assertRaisesRegex(RuntimeError, 'Foreign cached control module'):
            self.flow()

    def test_missing_channel_never_uses_setup_fallback(self):
        (self.tools / 'codex_channel.py').unlink()
        (self.setup / 'codex_channel.py').write_text('raise AssertionError("fallback executed")\n', encoding='utf-8')
        with self.assertRaises((FileNotFoundError, RuntimeError)):
            self.flow()
        self.assertNotIn('codex_channel', sys.modules)

    def test_hardlinked_provider_refused(self):
        os.link(self.tools / 'bos_dev.py', self.tools / 'other.py')
        with self.assertRaisesRegex(RuntimeError, 'single-link'):
            self.flow()

    def test_reparse_provider_refused_when_fixture_available(self):
        target = self.tools / 'original.py'
        (self.tools / 'bos_dev.py').rename(target)
        try:
            os.symlink(target, self.tools / 'bos_dev.py')
        except OSError as exc:
            self.skipTest('Windows file symlink fixture unavailable: ' + type(exc).__name__)
        self.known_symlink_leaf = True
        with self.assertRaisesRegex(RuntimeError, 'single-link'):
            self.flow()

    def test_second_authority_failure_has_no_health_output(self):
        health = self.health()
        github = self.root / 'github.json'
        github.write_text('{}', encoding='utf-8')
        outdir = self.root / 'reports' / 'repo_health'
        failure = health._provider.ControlHomeError('second-stage-refused')
        with patch.object(health, 'resolve_control_home', side_effect=[self.home, self.home, failure]):
            with patch.object(health, 'write') as output_write:
                with patch.object(sys, 'argv', ['repo_health', '--home', str(self.home), '--root',
                                              str(self.root), '--github', str(github), '--output-dir', str(outdir)]):
                    with self.assertRaises(health._provider.ControlHomeError):
                        health.main()
        output_write.assert_not_called()
        self.assertFalse(outdir.exists())

    def test_flow_refusal_precedes_explicit_fake_transport(self):
        flow = self.flow()
        def forbidden_factory():
            raise AssertionError('Transport constructed')
        with patch.object(flow, 'resolve_control_home', side_effect=flow.ControlHomeError('refused')):
            with patch.object(flow, 'state_lock', side_effect=AssertionError('External state opened')):
                with self.assertRaises(flow.ControlHomeError):
                    flow.refresh(home=self.home, root=self.root, client_factory=forbidden_factory)

    def test_local_flow_selected_home_output_refusal(self):
        flow = self.flow().local_flow
        with patch.object(flow, 'resolve_control_home', side_effect=flow._provider.ControlHomeError('refused')):
            with patch.object(flow, 'atomic_text') as output_write:
                with patch.object(sys, 'argv', ['local_flow', '--home', str(self.home), '--root',
                                              str(self.root), '--output-dir', str(self.root / 'reports' / 'local_flow')]):
                    with self.assertRaises(flow._provider.ControlHomeError):
                        flow.main()
        output_write.assert_not_called()
        self.assertFalse((self.root / 'reports').exists())

    def test_wrapper_home_forwarding_source(self):
        for name in ('bos.ps1', 'bos-flow.ps1', 'start-workday.ps1'):
            text = (STAGED / name).read_text(encoding='utf-8-sig')
            self.assertIn("'D:\\3\\BOSDev\\control-home' } else { $ControlHomePath }", text)
        self.assertIn("'--home', $controlHome", (STAGED / 'bos-flow.ps1').read_text(encoding='utf-8-sig'))
        self.assertIn('--home $controlHome status', (STAGED / 'bos.ps1').read_text(encoding='utf-8-sig'))
        self.assertIn('$processInfo.ArgumentList.Add($SelectedHome)',
                      (STAGED / 'start-workday.ps1').read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
