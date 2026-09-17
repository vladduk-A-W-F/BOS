"""A07 real CLI regression: missing referenced media produces a refusal report.

The sole fixture is freshly migrated/populated in a subprocess. No installation
database or external evidence directory is used as input to this permanent test.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4


PROJECT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PreflightMissingMediaTests(unittest.TestCase):
    def test_missing_referenced_file_is_a_written_refusal_without_source_changes(self):
        self.assertTrue((PROJECT / 'scripts' / 'preflight_data.py').is_file())
        if str(PROJECT) not in sys.path:
            sys.path.insert(0, str(PROJECT))
        from scripts.check_data_transfer import run_child
        from scripts.reconcile_data import make_snapshot

        with tempfile.TemporaryDirectory(prefix='a07_missing_media_cli_') as raw:
            work = Path(raw).resolve()
            source = work / ('check_' + uuid4().hex + '.sqlite3')
            media = work / 'source-media'
            media.mkdir()
            expected_file = work / 'expected.json'
            run_child('seed', source, media, work, backend='sqlite', expected=expected_file)
            expected = json.loads(expected_file.read_text(encoding='utf-8'))
            self.assertGreater(expected['chat']['content']['size'], 0)
            source_before = sha(source)
            snapshot = work / ('check_' + uuid4().hex + '.sqlite3')
            make_snapshot(source, snapshot)
            snapshot_before = sha(snapshot)
            incomplete_media = work / 'incomplete-media'
            shutil.copytree(media, incomplete_media)
            missing_file = incomplete_media / expected['chat']['relative_path']
            self.assertTrue(missing_file.resolve().is_relative_to(incomplete_media))
            self.assertTrue(missing_file.is_file())
            missing_file.unlink()

            output = work / 'refusal.json'
            env = dict(os.environ, BOS_VERIFY_DB='sqlite', BOS_TEST_DB_NAME=':memory:',
                       BOS_TEST_MEDIA=str(incomplete_media), PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
            result = subprocess.run([sys.executable, '-B', str(PROJECT / 'scripts' / 'preflight_data.py'),
                '--snapshot', str(snapshot), '--media', str(incomplete_media), '--output', str(output)],
                cwd=PROJECT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)

            # These assertions also run when CLI fails to produce its report.
            self.assertEqual(sha(source), source_before)
            self.assertEqual(sha(snapshot), snapshot_before)
            self.assertTrue((media / expected['chat']['relative_path']).is_file())
            self.assertFalse(missing_file.exists(), 'preflight must not create a placeholder')
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(output.is_file(), 'CLI omitted refusal report: ' + result.stderr)
            report = json.loads(output.read_text(encoding='utf-8'))
            self.assertFalse(report['can_migrate'])
            self.assertTrue(report['source_unchanged'])
            self.assertEqual(report['source_sha256'], snapshot_before)
            self.assertIn('FILE_ACCESS_CONFLICT', [finding['code'] for finding in report['findings']])
            summary = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertFalse(summary['can_migrate'])
            self.assertGreater(summary['findings'], 0)
            self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
