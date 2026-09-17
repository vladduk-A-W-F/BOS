"""Permanent A07 migration regression: actual isolated SQLite subprocesses.

Destination: erp/test_constraint_upgrade.py.  This SQLite-specific check also
runs when the surrounding suite uses PostgreSQL; the subprocess explicitly
reports SQLite and never claims to verify PostgreSQL migration behavior.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4

from django.test import SimpleTestCase

import scripts.check_constraint_upgrade as upgrade_probe


class ConstraintUpgradeTests(SimpleTestCase):
    # The probe module is loaded only to resolve its canonical source path.
    # It must expose main(); importing it must not migrate anything.
    def run_probe(self, case):
        script = Path(upgrade_probe.__file__).resolve()
        root = script.parents[1]
        with tempfile.TemporaryDirectory(prefix='bos_a07_upgrade_') as folder:
            base = Path(folder)
            db = base / ('check_' + uuid4().hex + '.sqlite3')
            env = os.environ.copy()
            env.update(BOS_VERIFY_DB='sqlite', BOS_TEST_DB_NAME=str(db),
                BOS_TEST_MEDIA=str(base / 'media'), DJANGO_SETTINGS_MODULE='verification_settings',
                PYTHONDONTWRITEBYTECODE='1')
            env['PYTHONPATH'] = str(root) + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
            completed = subprocess.run([sys.executable, '-B', str(script), case],
                cwd=root, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(completed.returncode, 0, completed.stdout + '\n' + completed.stderr)
            report = json.loads(completed.stdout.strip().splitlines()[-1])
            self.assertEqual((report['case'], report['backend'], report['passed']), (case, 'sqlite', True))
            self.assertTrue(report['database_version'])
            self.assertTrue(report['rows_unchanged'])
            print('BOS_A07_MIGRATION ' + json.dumps(report, ensure_ascii=False, sort_keys=True))
            return report

    def test_invalid_old_rows_refuse_each_migration_without_partial_ddl(self):
        for case in ('finance', 'operations', 'erp'):
            with self.subTest(case=case):
                report = self.run_probe(case)
                self.assertTrue(report['denied'])
                self.assertFalse(report['applied'])
                self.assertTrue(report['ddl_unchanged'])
                self.assertEqual(report['sequence_before'], report['sequence_after'])

    def test_forward_reverse_high_water_and_next_ids_for_sparse_empty_and_larger_current(self):
        for case in ('sequence', 'sequence_empty', 'sequence_current'):
            with self.subTest(case=case):
                report = self.run_probe(case)
                self.assertIsNone(report['denied'])
                self.assertTrue(report['applied'])
                self.assertTrue(report['reverse_rows_unchanged'])
                self.assertGreaterEqual(report['reverse_sequence'],
                    max(report['sequence_before'], report['sequence_after']))
                self.assertGreater(report['next_ids'][0], report['reverse_sequence'])
                self.assertGreater(report['next_ids'][1], report['next_ids'][0])
                self.assertEqual(report['next_ids'], [8, 9] if case == 'sequence_current' else [90002, 90003])

    def test_null_high_water_is_refused_without_repairing_source_metadata(self):
        report = self.run_probe('sequence_null')
        self.assertIn('Invalid SQLite sequence metadata', report['denied'])
        self.assertFalse(report['applied'])
        self.assertTrue(report['ddl_unchanged'])
        self.assertIsNone(report['sequence_before'])
        self.assertIsNone(report['sequence_after'])
