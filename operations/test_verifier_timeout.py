"""Real subprocess regressions for verifier evidence, using only temporary fixtures."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    'bos_verifier_timeout_tests', Path(__file__).resolve().parents[1] / 'scripts' / 'verify.py')
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


class VerifierTimeoutTests(unittest.TestCase):
    timeout = 1.0

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='bos-timeout-test-')
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.source = self.work / 'source'
        (self.source / 'scripts').mkdir(parents=True)
        self.output = self.work / 'logs'

    def execute(self, code, name='child.log'):
        env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
        return verify.execute([sys.executable, '-B', '-c', code], self.source,
                              env, self.output / name, timeout=self.timeout)

    def assert_timeout(self, result, receipt):
        self.assertIsNone(result.returncode)
        self.assertIsNone(receipt['returncode'])
        self.assertIs(receipt['timed_out'], True)
        self.assertEqual(receipt['timeout_seconds'], self.timeout)
        self.assertIn('TimeoutExpired', receipt['reason'])
        self.assertEqual(receipt['command'], result.args)
        return Path(receipt['log']).read_text(encoding='utf-8')

    def fixture_pipeline(self, *, hang_at=None, django_hangs=False):
        # These are diagnostic fixtures, not substitutes for the app acceptance checks.
        for filename, count in verify.LEGACY.items():
            code = (
                'import json, os, sqlite3, time\n'
                'from pathlib import Path\n'
                f'Path({filename!r} + ".started").write_text("fixture", encoding="utf-8")\n'
            )
            if filename == 'check_launcher.py':
                code += 'print("5 launcher checks passed; diagnostic fixture", flush=True)\n'
            else:
                code += (
                    'with sqlite3.connect(os.environ["BOS_TEST_DB_NAME"]) as db:\n'
                    '    db.execute("CREATE TABLE diagnostic_fixture (value INTEGER)")\n'
                    'print("BOS_DATABASE " + json.dumps({"vendor": "sqlite"}), flush=True)\n'
                    f'print(json.dumps({{"passed": {count}, "checks": list(range({count}))}}), flush=True)\n'
                )
            if filename == hang_at:
                code += 'time.sleep(60)\n'
            (self.source / 'scripts' / filename).write_text(code, encoding='utf-8')
        manager = (
            'import sys, time\nfrom pathlib import Path\n'
            'Path("django.started").write_text("fixture", encoding="utf-8")\n'
            'print("Django fixture: початок", flush=True)\n'
            'print("Незавершена перевірка", file=sys.stderr, flush=True)\n'
        )
        if django_hangs:
            manager += 'time.sleep(60)\n'
        (self.source / 'manage.py').write_text(manager, encoding='utf-8')

    def test_timeout_keeps_partial_utf8_stdout_and_stderr(self):
        result, receipt = self.execute(
            'import os, time; '
            'os.write(1, "Частковий результат\\n".encode("utf-8") + b"\\xff"); '
            'os.write(2, "Діагностика\\n".encode("utf-8")); time.sleep(60)')
        log = self.assert_timeout(result, receipt)
        self.assertEqual(result.stdout, 'Частковий результат\n\ufffd')
        self.assertEqual(result.stderr, 'Діагностика\n')
        self.assertEqual(log, result.stdout + '\n--- STDERR ---\n' + result.stderr)

    def test_silent_timeout_still_creates_log_and_failed_receipt(self):
        result, receipt = self.execute('import time; time.sleep(60)')
        self.assertEqual(self.assert_timeout(result, receipt), '\n--- STDERR ---\n')
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, '')

    def test_normal_success_and_failure_keep_actual_exit_codes(self):
        for code in (0, 7):
            with self.subTest(code=code):
                result, receipt = self.execute(
                    f'import sys; print("out"); print("err", file=sys.stderr); sys.exit({code})',
                    name=f'exit-{code}.log')
                self.assertEqual(result.returncode, code)
                self.assertEqual(receipt['returncode'], code)
                self.assertNotIn('timed_out', receipt)
                self.assertEqual(Path(receipt['log']).read_text(), 'out\n\n--- STDERR ---\nerr\n')

    def test_django_timeout_keeps_all_completed_legacy_receipts(self):
        self.fixture_pipeline(django_hangs=True)
        report = verify.functional('sqlite', self.work, self.output, timeout=self.timeout)
        self.assertEqual(report['status'], verify.FAIL)
        self.assertEqual(report['backend'], 'sqlite')
        self.assertEqual(len(report['parts']), 6)
        self.assertEqual([part['filename'] for part in report['parts'][:5]], list(verify.LEGACY))
        for part in report['parts'][:5]:
            self.assertEqual(part['status'], verify.PASS)
            self.assertEqual(part['returncode'], 0)
            self.assertEqual(part['checks'], part['expected'])
            self.assertTrue(Path(part['log']).is_file())
        last = report['parts'][-1]
        self.assertEqual(last['status'], verify.FAIL)
        self.assertIsNone(last['returncode'])
        self.assertTrue(last['timed_out'])
        self.assertIn('Django fixture: початок', Path(last['log']).read_text(encoding='utf-8'))
        self.assertIn('Незавершена перевірка', Path(last['log']).read_text(encoding='utf-8'))
        self.assertEqual(json.loads(json.dumps(report, ensure_ascii=False)), report)

    def test_legacy_timeout_with_pass_shaped_output_fails_and_stops_pipeline(self):
        self.fixture_pipeline(hang_at='check_operations.py')
        report = verify.functional('sqlite', self.work, self.output, timeout=self.timeout)
        self.assertEqual(report['status'], verify.FAIL)
        self.assertEqual(len(report['parts']), 3)
        self.assertEqual([p['status'] for p in report['parts']], [verify.PASS, verify.PASS, verify.FAIL])
        last = report['parts'][-1]
        self.assertIsNone(last['checks'])
        self.assertFalse(last['engine_verified'])
        self.assertIsNone(last['returncode'])
        self.assertTrue(last['timed_out'])
        self.assertTrue(Path(last['log']).is_file())
        for name in ('check_original.py.started', 'check_launcher.py.started', 'django.started'):
            self.assertFalse((self.source / name).exists(), name)

    def test_spawn_error_is_not_converted_to_success(self):
        with self.assertRaises(FileNotFoundError):
            verify.execute([str(self.work / 'nonexistent-python')], self.source, os.environ.copy(),
                           self.output / 'spawn.log', timeout=self.timeout)

    def test_truncated_legacy_database_marker_keeps_prior_receipts(self):
        self.fixture_pipeline()
        (self.source / 'scripts' / 'check_operations.py').write_text(
            'import time\nprint(\'BOS_DATABASE {"vendor":\', flush=True)\ntime.sleep(60)\n',
            encoding='utf-8')
        report = verify.functional('sqlite', self.work, self.output, timeout=self.timeout)
        self.assertEqual(report['status'], verify.FAIL)
        self.assertEqual(len(report['parts']), 3)
        self.assertEqual([p['status'] for p in report['parts']], [verify.PASS, verify.PASS, verify.FAIL])
        last = report['parts'][-1]
        self.assertTrue(last['timed_out'])
        self.assertIsNone(last['returncode'])
        self.assertIn('BOS_DATABASE {"vendor":', Path(last['log']).read_text())
        self.assertFalse((self.source / 'django.started').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
