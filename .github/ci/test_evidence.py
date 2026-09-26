"""Synthetic tests of CI provenance only; no application, network, DB or browser."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('ci_evidence', Path(__file__).with_name('evidence.py'))
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class EvidenceContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ctx = dict(repository='synthetic/example', commit='a' * 40,
                        source_sha256='b' * 64, ci_sha256='c' * 64, run_id='123', run_attempt='2')
        self.needs = {s: {'result': 'success'} for s in ci.CHILDREN}
        for suite in ci.CHILDREN:
            folder = self.folder(suite)
            folder.mkdir()
            (folder / 'verify-console.log').write_text('Synthetic test fixture, not an actual verifier result.\n')
            report = self.report(suite)
            (folder / 'report.json').write_text(json.dumps(report))
            receipt = dict(self.ctx, schema=1, suite=suite, job=suite, state='passed',
                           verify_exit_code=0, errors=[], databases={'postgresql_version_num': 160015},
                           job_url=self.url(), files=ci.file_map(folder))
            (folder / 'ci-receipt.json').write_text(json.dumps(receipt))

    def folder(self, suite):
        return self.root / f'bos-123-2-{suite}'

    def url(self):
        return 'https://github.com/synthetic/example/actions/runs/123/job/456'

    def report(self, suite):
        return dict(suite=suite, complete=True, source_databases_unchanged=True,
                    source_sha256=self.ctx['source_sha256'],
                    ci=dict(commit=self.ctx['commit'], pipeline_id=ci.pipeline(self.ctx), job_url=self.url()),
                    environment=dict(system='Windows' if suite == 'windows' else 'Linux', python_minor=[3, 12]),
                    gates=[dict(id=g, status=ci.PASS) for g in sorted(ci.SUITES[suite])])

    def mutate_receipt(self, fn, suite='windows'):
        path = self.folder(suite) / 'ci-receipt.json'
        value = json.loads(path.read_text())
        fn(value)
        path.write_text(json.dumps(value))

    def errors(self):
        return ci.upstream_errors(self.root, self.ctx, self.needs)

    def test_complete_synthetic_contract(self):
        self.assertEqual(self.errors(), [])

    def test_missing_report(self):
        (self.folder('windows') / 'report.json').unlink()
        self.assertTrue(self.errors())

    def test_missing_receipt(self):
        (self.folder('windows') / 'ci-receipt.json').unlink()
        self.assertTrue(self.errors())

    def test_stale_identity(self):
        for key in self.ctx:
            with self.subTest(key=key):
                altered = dict(self.ctx, **{key: 'stale'})
                self.assertTrue(ci.upstream_errors(self.root, altered, self.needs))

    def test_failed_cancelled_skipped_missing_job(self):
        for result in ('failure', 'cancelled', 'skipped', None):
            with self.subTest(result=result):
                self.needs['windows']['result'] = result
                self.assertTrue(self.errors())

    def test_missing_prerequisite_result(self):
        del self.needs['ui']
        self.assertTrue(self.errors())

    def test_nonzero_exit(self):
        self.mutate_receipt(lambda r: r.update(verify_exit_code=7))
        self.assertTrue(self.errors())

    def test_setup_not_run(self):
        self.mutate_receipt(lambda r: r.update(state='not_run'))
        self.assertTrue(self.errors())

    def test_wrong_postgres(self):
        self.mutate_receipt(lambda r: r['databases'].update(postgresql_version_num=170011))
        self.assertTrue(self.errors())

    def test_tampered_or_missing_log(self):
        log = self.folder('windows') / 'verify-console.log'
        log.write_text('changed')
        self.assertTrue(self.errors())
        log.unlink()
        self.assertTrue(self.errors())

    def test_malformed_evidence(self):
        (self.folder('windows') / 'ci-receipt.json').write_text('null')
        self.assertTrue(self.errors())

    def test_report_rejects_incomplete_wrong_gate_os_and_python(self):
        mutations = [lambda r: r.update(complete=False),
                     lambda r: r.update(source_databases_unchanged=False),
                     lambda r: r['gates'].pop(),
                     lambda r: r['gates'].append(copy.deepcopy(r['gates'][0])),
                     lambda r: r['gates'][0].update(status='НЕ ЗАПУЩЕНО'),
                     lambda r: r['gates'][0].update(status='НЕ РЕАЛІЗОВАНО'),
                     lambda r: r['environment'].update(system='Linux'),
                     lambda r: r['environment'].update(python_minor=[3, 15]),
                     lambda r: r['ci'].update(commit='stale'),
                     lambda r: r['ci'].update(pipeline_id='old-attempt')]
        for i, mutate in enumerate(mutations):
            with self.subTest(mutation=i):
                report = self.report('windows')
                mutate(report)
                self.assertTrue(ci.report_errors(report, 'windows', self.ctx, self.url()))

    def test_url_must_identify_this_run(self):
        report = self.report('windows')
        bad_url = self.url().replace('/123/', '/122/')
        report['ci']['job_url'] = bad_url
        self.assertTrue(ci.report_errors(report, 'windows', self.ctx, bad_url))

    def test_raw_child_exit_is_preserved(self):
        log = self.root / 'child.log'
        self.assertEqual(ci.execute([sys.executable, '-c', 'print("sentinel"); raise SystemExit(7)'], log, os.environ.copy()), 7)
        self.assertEqual(log.read_text().strip(), 'sentinel')

    def test_run_preserves_exit_and_report_filename(self):
        output = self.root / 'run'
        def child(command, log, env):
            self.assertEqual(Path(command[-1]), output / 'report.json')
            self.assertEqual(env['CI_PIPELINE_ID'], ci.pipeline(self.ctx))
            self.assertNotIn('GITHUB_TOKEN', env)
            log.write_text('synthetic child exit=7')
            (output / 'report.json').write_text(json.dumps(self.report('sqlite')))
            return 7
        with patch.dict(os.environ, GITHUB_JOB='sqlite', GITHUB_TOKEN='synthetic-not-a-token'), patch.object(ci, 'context', return_value=self.ctx), \
             patch.object(ci, 'job_url', return_value=self.url()), patch.object(ci, 'database_versions', return_value={}), \
             patch.object(ci.platform, 'python_version_tuple', return_value=('3', '12', '0')), \
             patch.object(ci, 'execute', side_effect=child):
            self.assertEqual(ci.run('sqlite', output, self.root), 7)
        receipt = json.loads((output / 'ci-receipt.json').read_text())
        self.assertEqual(receipt['verify_exit_code'], 7)
        self.assertEqual(receipt['state'], 'failed')

    def test_setup_failure_gets_not_run_receipt(self):
        output = self.root / 'setup-failure'
        with patch.object(ci, 'context', side_effect=RuntimeError('setup failed')):
            self.assertEqual(ci.finish('sqlite', output), 1)
        self.assertEqual(json.loads((output / 'ci-receipt.json').read_text())['state'], 'not_run')
        self.assertFalse((output / 'report.json').exists())

    def test_cleanup_failure_cannot_be_passed(self):
        folder = self.folder('windows')
        with patch.dict(os.environ, BOS_STEPS_JSON=json.dumps({'cleanup': {'outcome': 'failure'}})):
            self.assertEqual(ci.finish('windows', folder), 1)

    def test_reuse_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Refusing'):
            ci.run('windows', self.folder('windows'), self.root)


if __name__ == '__main__':
    unittest.main(verbosity=2)
