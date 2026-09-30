"""Synthetic, standard-library tests for the bounded atomic receipt retry."""

import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock


WORKSPACE = Path(r'D:\3\BOSDev\qa-scratch\bos3-atomic-receipt-repair-20260928')
SOURCE = WORKSPACE / 'scripts' / 'bos3_local.py'
OWNED_ANCESTORS = (
    Path('D:\\'),
    Path(r'D:\3'),
    Path(r'D:\3\BOSDev'),
    Path(r'D:\3\BOSDev\qa-scratch'),
    WORKSPACE,
)


def require_ordinary_owned_workspace():
    reparse_flag = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
    for path in OWNED_ANCESTORS:
        metadata = os.lstat(path)
        if (not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
                or getattr(metadata, 'st_file_attributes', 0) & reparse_flag):
            raise AssertionError('Synthetic fixture ancestor is not an ordinary owned directory: ' + str(path))


def load_target():
    spec = importlib.util.spec_from_file_location('bos3_local_atomic_target', SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def windows_denial(code):
    failure = PermissionError(code, 'synthetic denial')
    failure.winerror = code
    return failure


class AtomicJsonRetryTests(unittest.TestCase):
    def setUp(self):
        require_ordinary_owned_workspace()
        self.target = load_target()
        self.directory = tempfile.TemporaryDirectory(prefix='atomic-', dir=WORKSPACE)
        self.fixture_path = Path(self.directory.name)
        self.assertEqual(self.fixture_path.parent, WORKSPACE)
        self.addCleanup(self.cleanup_exact_fixture)
        self.path = Path(self.directory.name) / 'receipt.json'

    def cleanup_exact_fixture(self):
        self.directory.cleanup()
        self.assertFalse(self.fixture_path.exists())

    def test_success_is_one_replacement_and_exact_json(self):
        original_replace = self.target.os.replace
        with mock.patch.object(self.target.os, 'replace', wraps=original_replace) as replace:
            self.target.atomic_json(self.path, {'status': 'ready'})
        self.assertEqual(replace.call_count, 1)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8')), {'status': 'ready'})

    def assert_one_applicable_denial_reuses_temp_then_succeeds(self, code):
        original_replace = self.target.os.replace
        calls = []

        def replace(temporary, destination):
            calls.append(Path(temporary))
            if len(calls) == 1:
                raise windows_denial(code)
            return original_replace(temporary, destination)

        with mock.patch.object(self.target.os, 'replace', side_effect=replace), \
                mock.patch.object(self.target.time, 'sleep') as sleep:
            self.target.atomic_json(self.path, {'status': 'ready'})
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(sleep.call_args_list, [mock.call(.05)])
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8')), {'status': 'ready'})

    def test_one_winerror5_denial_reuses_temp_then_succeeds(self):
        self.assert_one_applicable_denial_reuses_temp_then_succeeds(5)

    def test_one_winerror33_denial_reuses_temp_then_succeeds(self):
        self.assert_one_applicable_denial_reuses_temp_then_succeeds(33)

    def test_permanent_applicable_denial_stops_at_three_and_keeps_temp(self):
        self.path.write_text('{"old": true}\n', encoding='utf-8')
        calls = []

        def replace(temporary, destination):
            calls.append(Path(temporary))
            raise windows_denial(32)

        with mock.patch.object(self.target.os, 'replace', side_effect=replace), \
                mock.patch.object(self.target.time, 'sleep') as sleep:
            with self.assertRaises(PermissionError):
                self.target.atomic_json(self.path, {'status': 'new'})
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(calls[1], calls[2])
        self.assertTrue(calls[0].exists())
        self.assertEqual(sleep.call_args_list, [mock.call(.05), mock.call(.1)])
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8')), {'old': True})

    def test_unrelated_errors_do_not_retry(self):
        for failure in (OSError('synthetic unrelated failure'), windows_denial(87)):
            with self.subTest(failure=failure):
                calls = []

                def replace(temporary, destination):
                    calls.append(Path(temporary))
                    raise failure

                with mock.patch.object(self.target.os, 'replace', side_effect=replace), \
                        mock.patch.object(self.target.time, 'sleep') as sleep:
                    with self.assertRaises(type(failure)):
                        self.target.atomic_json(self.path, {'status': 'new'})
                self.assertEqual(len(calls), 1)
                self.assertEqual(sleep.call_args_list, [])


if __name__ == '__main__':
    unittest.main()
