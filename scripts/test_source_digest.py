"""Path-only source identity regressions; no app, database or runner is started."""
import hashlib
from pathlib import PurePosixPath, PureWindowsPath
import unittest
from unittest.mock import patch

from scripts import verify


def synthetic_root(flavour, root, files):
    """Read-only in-memory file inventory with genuine pathlib comparison rules."""
    class SyntheticPath(flavour):
        def is_file(self):
            return self.relative_to(root).as_posix() in files

        def exists(self):
            return self.is_file()

        def read_bytes(self):
            return files[self.relative_to(root).as_posix()]

        def rglob(self, pattern):
            if pattern != '*':
                raise AssertionError(pattern)
            prefix = self.relative_to(root).as_posix() + '/'
            return (type(self)(root) / name for name in files if name.startswith(prefix))

        def iterdir(self):
            return (type(self)(root) / name for name in files if '/' not in name)

    return SyntheticPath(root)


def expected_digest(ordered_entries):
    """Explicit known order, independent of the production sort expression."""
    digest = hashlib.sha256()
    for name, normalized_bytes in ordered_entries:
        digest.update(name.encode() + b'\0' + normalized_bytes + b'\0')
    return digest.hexdigest()


class SourceDigestPathOrderTests(unittest.TestCase):
    FLAVOURS = ((PurePosixPath, '/synthetic/source'),
                (PureWindowsPath, 'C:/synthetic/source'))

    def test_mixed_case_paths_have_same_digest_on_both_path_flavours(self):
        files = {
            'scripts/a.py': b'a = 1\r\n',
            'scripts/_helper.py': b'helper = 1\n',
            'START_DEMO.bat': b'@echo off\r\n',
            'scripts/Z.py': b'z = 1\n',
            'assets/Logo.png': b'\x89PNG\r\n',
        }
        expected = expected_digest([
            ('START_DEMO.bat', b'@echo off\n'),
            ('assets/Logo.png', b'\x89PNG\r\n'),
            ('scripts/Z.py', b'z = 1\n'),
            ('scripts/_helper.py', b'helper = 1\n'),
            ('scripts/a.py', b'a = 1\n'),
        ])
        for flavour, root in self.FLAVOURS:
            for inventory in (files, dict(reversed(tuple(files.items())))):
                with self.subTest(flavour=flavour.__name__, first=next(iter(inventory))):
                    with patch.object(verify, 'ROOT', synthetic_root(flavour, root, inventory)):
                        self.assertEqual(verify.source_digest(), expected)

    def test_directory_prefix_keeps_legacy_posix_component_order(self):
        # Native POSIX Path orders by components: documents/ precedes
        # documents.json. Sorting the whole slash-delimited string reverses it.
        files = {
            'operations/seed/documents.json': b'[]\r\n',
            'operations/seed/documents/D01.md': b'# Document\r\n',
        }
        expected = expected_digest([
            ('operations/seed/documents/D01.md', b'# Document\n'),
            ('operations/seed/documents.json', b'[]\n'),
        ])
        for flavour, root in self.FLAVOURS:
            with self.subTest(flavour=flavour.__name__):
                with patch.object(verify, 'ROOT', synthetic_root(flavour, root, files)):
                    self.assertEqual(verify.source_digest(), expected)


if __name__ == '__main__':
    unittest.main()
