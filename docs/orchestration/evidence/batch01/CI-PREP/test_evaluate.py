"""Artifact-only result parsing tests: no Django, databases, subprocesses, or CI."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest


path = Path(__file__).parent / '.github/ci/batch_01_targeted.py'
spec = importlib.util.spec_from_file_location('batch01_result_evaluation', path)
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class ResultSummaryTests(unittest.TestCase):
    def fixture(self, expected_red=None, mode='postgres16'):
        count = 1 if expected_red else 5
        source = 'bos_verify_0123456789abcdef'
        stage = {'expected_tests': count, 'mode': mode, 'expected_red': expected_red,
                 'exit_code': 1 if expected_red else 0, 'source_database': source}
        stdout = 'BOS_BATCH_TEST_DATABASE ' + json.dumps({
            'vendor': 'postgresql', 'database': 'test_' + source, 'version_num': 160004})
        markers = {
            'guard': "test_initial_import.py\nname.startswith('check_')\nAssertionError: False is not true\n",
            'invoice': 'test_distinct_import_proposals_same_source_have_one_immutable_effect\n'
                       'django.db.utils.DataError: value too long for type character varying(30)\n',
            'request': 'test_raw_overflow_refused_without_trimming_or_partial_writes\n'
                       '500 != 422\nvalue too long for type character varying(30)\n',
        }
        stderr = markers.get(expected_red, '') + f'Ran {count} tests in 0.01s\n\n'
        return stage, stdout, stderr

    def test_exact_expected_red_summaries_are_accepted(self):
        for red, summary in (('guard', 'FAILED (failures=1)'),
                             ('invoice', 'FAILED (errors=3)'),
                             ('request', 'FAILED (failures=36)')):
            with self.subTest(red=red):
                stage, stdout, stderr = self.fixture(red)
                self.assertTrue(harness.evaluate(stage, stdout, stderr + summary + '\n'))

    def test_expected_red_rejects_nonpassing_outcomes(self):
        for red in ('guard', 'invoice', 'request'):
            for outcome in ('skipped=1', 'expected failures=1', 'unexpected successes=1'):
                with self.subTest(red=red, outcome=outcome):
                    stage, stdout, stderr = self.fixture(red)
                    self.assertFalse(harness.evaluate(stage, stdout,
                        stderr + f'FAILED (failures=1, {outcome})\n'))

    def test_exact_green_summaries_are_accepted(self):
        for mode in ('postgres16', 'unit'):
            with self.subTest(mode=mode):
                stage, stdout, stderr = self.fixture(mode=mode)
                self.assertTrue(harness.evaluate(stage, stdout, stderr + 'OK\n'))

    def test_green_rejects_nonpassing_outcomes(self):
        for mode in ('postgres16', 'unit'):
            for outcome in ('skipped=1', 'expected failures=1', 'unexpected successes=1'):
                with self.subTest(mode=mode, outcome=outcome):
                    stage, stdout, stderr = self.fixture(mode=mode)
                    self.assertFalse(harness.evaluate(stage, stdout, stderr + f'OK ({outcome})\n'))

    def test_missing_or_multiple_summaries_are_refused(self):
        for red in (None, 'guard'):
            stage, stdout, stderr = self.fixture(red)
            summaries = ('', 'OK\nOK\n', 'FAILED (failures=1)\nFAILED (failures=1)\n')
            for summary in summaries:
                with self.subTest(red=red, summary=summary):
                    self.assertFalse(harness.evaluate(deepcopy(stage), stdout, stderr + summary))


if __name__ == '__main__':
    unittest.main()
