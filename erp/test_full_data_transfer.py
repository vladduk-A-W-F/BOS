"""Actual full-model A07 rehearsal on the selected verification backend."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from django.test import SimpleTestCase
from scripts import check_data_transfer as runner
from fixtures.synthetic.table_inventory import C03_TABLES


class FullDataTransferTests(SimpleTestCase):
    def test_full_model_transfer_preserves_money_stock_files_ids_and_replays(self):
        backend = os.environ.get('BOS_VERIFY_DB', 'sqlite')
        with tempfile.TemporaryDirectory(prefix='bos-a07-full-transfer-') as folder:
            output = Path(folder) / 'rehearsal'
            completed = subprocess.run([sys.executable, '-B', str(Path(runner.__file__).resolve()),
                '--backend', backend, '--output-dir', str(output)], cwd=runner.ROOT,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), capture_output=True,
                text=True, encoding='utf-8', timeout=180)
            failure = completed.stdout + '\n' + completed.stderr
            if completed.returncode:
                failure += '\n'.join(p.read_text(encoding='utf-8')
                    for p in sorted(output.glob('child-*.log')))
            self.assertEqual(completed.returncode, 0, failure)
            report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
            self.assertTrue(report['complete'])
            self.assertEqual(report['backend'], backend)
            self.assertTrue(report['source_unchanged'])
            self.assertEqual(report['table_count'], 56)
            self.assertEqual(set(report['tables']), C03_TABLES)
            self.assertEqual(report['business_before']['facts'], report['business_after']['facts'])
            self.assertTrue(report['files_preserved'])
            self.assertTrue(report['sequences_preserved'])
            self.assertTrue(report['target_unchanged_by_proof'])
            self.assertTrue(report['rollback_source_verified'])
            self.assertEqual(report['sequence_proof']['next_ids'], [90002, 90003])
            self.assertTrue(report['sequence_proof']['replay']['http_receipt_equal'])
            for currency in ('EUR', 'USD', 'UAH'):
                self.assertTrue(report['sequence_proof']['replay']['financial_replays'][currency]['same_sources'])
            print('BOS_A07_TRANSFER ' + json.dumps({
                'backend': backend, 'complete': True, 'table_count': report['table_count'],
                'source_sha256': report['source_sha256'],
                'source_unchanged': report['source_unchanged'],
                'accounting_totals': report['accounting_totals'],
                'next_ids': report['sequence_proof']['next_ids'],
                'http_receipt_equal': report['sequence_proof']['replay']['http_receipt_equal'],
                'not_checked': report['not_checked']}, ensure_ascii=False))
