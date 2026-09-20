"""Bounded verifier artifact tests; fixture processes never run the business E2E."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import verify


# This subprocess fixture exercises real output placement, console parsing, and
# byte hashes only. It deliberately contains no application or database code.
FIXTURE = r'''import argparse
import hashlib
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path)
args = parser.parse_args()
output = args.output or Path(os.environ['FIXTURE_DEFAULT_OUTPUT'])
mode = os.environ.get('FIXTURE_MODE', 'ok')
vendor = 'postgresql' if os.environ['FIXTURE_BACKEND'] == 'postgres' else 'sqlite'
report = {'schema': 'bos.gate6.actual.v1', 'gate': 6,
          'complete': mode not in ('business_failure', 'incomplete_exit_zero'),
          'environment': {'actual_vendor': vendor},
          'checks': ['fixture output placement only']}
output.parent.mkdir(parents=True, exist_ok=True)
if mode != 'missing':
    output.write_text('not json' if mode == 'invalid_json' else json.dumps(report), encoding='utf-8')
summary = {'gate': 6, 'complete': report['complete'], 'vendor': vendor,
           'report': str(output),
           'report_sha256': hashlib.sha256(output.read_bytes()).hexdigest() if output.exists() else '0' * 64}
if mode == 'wrong_digest':
    summary['report_sha256'] = '0' * 64
if mode == 'wrong_path':
    summary['report'] = str(output.parent / 'elsewhere.json')
if mode == 'wrong_vendor':
    summary['vendor'] = 'sqlite' if vendor == 'postgresql' else 'postgresql'
if mode == 'inconsistent_complete':
    summary['complete'] = False
if mode != 'no_summary':
    print(json.dumps(summary))
raise SystemExit(1 if mode == 'business_failure' else 0)
'''


class VerifyE2EEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bos-evidence-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / 'work'
        self.source = self.work / 'source'
        (self.source / 'scripts').mkdir(parents=True)
        (self.source / 'scripts/e2e_scenario.py').write_text(FIXTURE, encoding='utf-8')
        self.output = self.root / 'artifact'
        self.mode = 'ok'

        @contextmanager
        def synthetic_environment(backend, work):
            yield dict(os.environ, FIXTURE_BACKEND=backend, FIXTURE_MODE=self.mode,
                       FIXTURE_DEFAULT_OUTPUT=str(self.root / ('outside-' + backend + '.json')))

        self.database = mock.patch.object(verify, 'database', synthetic_environment)
        self.database.start()
        self.addCleanup(self.database.stop)

    def run_main(self):
        report_path = self.output / 'report.json'
        with mock.patch.object(verify, 'ROOT', self.source), mock.patch.object(
                verify.sys, 'argv', ['verify.py', '--suite', 'e2e', '--output', str(report_path)]):
            code = verify.main()
        return code, json.loads(report_path.read_text(encoding='utf-8'))

    def test_routes_both_backend_files_inside_artifact_with_matching_hashes(self):
        for backend in ('sqlite', 'postgres'):
            with self.subTest(backend=backend):
                result = verify.extension(6, backend, self.work, self.output)
                detail = self.output / ('e2e-' + backend) / 'e2e-report.json'
                self.assertTrue(detail.is_file())
                self.assertFalse((self.root / ('outside-' + backend + '.json')).exists())
                self.assertEqual(result['status'], verify.PASS)
                self.assertTrue(result['evidence']['complete'])
                self.assertEqual(result['evidence']['report'], str(detail))
                self.assertEqual(result['evidence']['report_sha256'],
                                 hashlib.sha256(detail.read_bytes()).hexdigest())
                log = (self.output / ('gate-06-' + backend + '.log')).read_text(encoding='utf-8')
                summary = next(verify.json_objects(log))
                self.assertEqual(summary['report_sha256'], result['evidence']['report_sha256'])
        self.assertEqual(len(list(self.output.rglob('e2e-report.json'))), 2)

    def test_successful_fixture_with_complete_artifacts_is_accepted(self):
        code, report = self.run_main()
        self.assertEqual(code, 0)
        self.assertTrue(report['complete'])
        self.assertTrue(report['gates'][0]['evidence_complete'])
        for part in report['gates'][0]['parts']:
            self.assertTrue(Path(part['evidence']['report']).is_file())

    def test_exit_zero_cannot_admit_missing_or_inconsistent_evidence(self):
        for mode in ('missing', 'wrong_digest', 'wrong_path', 'invalid_json',
                     'no_summary', 'wrong_vendor', 'inconsistent_complete', 'incomplete_exit_zero'):
            with self.subTest(mode=mode):
                self.mode = mode
                self.output = self.root / ('artifact-' + mode)
                code, report = self.run_main()
                self.assertEqual(code, 1)
                self.assertFalse(report['complete'])
                gate = report['gates'][0]
                # An artifact defect does not rewrite the process exit result.
                self.assertEqual(gate['status'], verify.PASS)
                self.assertFalse(gate['evidence_complete'])
                self.assertTrue(all(p['evidence']['errors'] for p in gate['parts']))

    def test_failed_fixture_preserves_its_detailed_evidence(self):
        self.mode = 'business_failure'
        code, report = self.run_main()
        self.assertEqual(code, 1)
        self.assertFalse(report['complete'])
        self.assertEqual(report['gates'][0]['status'], verify.FAIL)
        self.assertTrue(report['gates'][0]['evidence_complete'])
        for part in report['gates'][0]['parts']:
            detail = json.loads(Path(part['evidence']['report']).read_text(encoding='utf-8'))
            self.assertFalse(detail['complete'])

    def test_other_extensions_keep_their_existing_command(self):
        (self.source / 'scripts/check_concurrency.py').write_text('raise SystemExit(0)\n', encoding='utf-8')
        result = verify.extension(5, 'sqlite', self.work, self.output)
        self.assertEqual(result['status'], verify.PASS)
        self.assertEqual(result['command'], [verify.sys.executable, '-B', 'scripts/check_concurrency.py'])
        self.assertNotIn('evidence', result)


if __name__ == '__main__':
    unittest.main()
