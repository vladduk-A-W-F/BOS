"""A07 admission regressions using actual migrated SQLite and the real CLI.

Destination: erp/test_data_preflight.py.  No configured runner database is
opened: subprocesses create two synthetic templates and per-test copies.
"""
from contextlib import closing
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from uuid import uuid4

from django.test import SimpleTestCase
import scripts.preflight_data as preflight_data


MAKE_TEMPLATE = r'''
from pathlib import Path
import hashlib, json, os, sqlite3, sys
source = Path(os.environ['BOS_TEST_DB_NAME'])
assert source.is_absolute() and source.parent.is_dir() and not source.exists()
assert source.name in ('base_latest.sqlite3', 'base_historical.sqlite3')
import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
executor = MigrationExecutor(connection)
profile = sys.argv[1]
assert profile in ('latest', 'historical')
targets = executor.loader.graph.leaf_nodes() if profile == 'latest' else [('finance', '0003_transaction_branch')]
executor.migrate(targets)
receipt = {'backend': 'sqlite', 'version': sqlite3.sqlite_version, 'profile': profile, 'targets': targets}
if profile == 'latest':
    from finance.commands import save_transaction
    from finance.models import FinancialIntent
    from operations.models import Document
    from ai_assistant.models import ChatMessage, ChatFile
    tx = save_transaction(changes={'direction':'out','amount':'123.45','currency':'EUR',
        'date':'2026-09-11','description':'Синтетична закупівля A07','category':'supplier'},
        operation_id='a07-preflight-completed')
    raw = bytes(range(256)) + 'Незмінні джерельні байти A07'.encode('utf-8')
    relative = 'chat_files/a07-source.bin'
    media = Path(os.environ['BOS_TEST_MEDIA'])
    physical = media / relative
    physical.parent.mkdir(parents=True, exist_ok=True)
    physical.write_bytes(raw)
    document = Document.objects.create(code='A07-PREFLIGHT',revision='A',title='Синтетичний документ',
        filename='a07-source.bin',content=raw,text='Синтетичний текст',sections=[],status='approved',
        checksum=hashlib.sha256(raw).hexdigest(),access_level='operational')
    message = ChatMessage.objects.create(role='user',content='Синтетичне джерело A07')
    attached = ChatFile.objects.create(chat_message=message,original_name='Технічні дані.bin',
        file=relative,mime_type='application/octet-stream',size=len(raw),parsed_text='')
    message.delete()
    receipt.update(transaction_id=tx.pk,intent_key=FinancialIntent.objects.get(transaction=tx).pk,
        document_id=document.pk,chat_file_id=attached.pk,media_relative=relative,
        bytes_sha256=hashlib.sha256(raw).hexdigest(),bytes_size=len(raw))
connection.close()
print(json.dumps(receipt, ensure_ascii=False))
'''


ADD_SCENARIO = r'''
from pathlib import Path
import json, os, sys
source = Path(os.environ['BOS_TEST_DB_NAME'])
assert source.is_absolute() and source.is_file() and source.name.startswith('test_')
import django
django.setup()
from django.db import connection, transaction
from finance.commands import save_transaction
from finance.models import FinancialIntent
scenario = sys.argv[1]
if scenario == 'orphan':
    with transaction.atomic():
        item = FinancialIntent.objects.create(key='f'*64,payload_hash='e'*64)
    # The atomic block has committed, so this is not an in-flight claim.
    receipt = {'key':item.pk,'sources':[item.transaction_id,item.salary_id]}
elif scenario == 'candidates':
    ids = []
    for index in (1, 2):
        tx = save_transaction(changes={'direction':'out','amount':'100.25','currency':'UAH',
            'date':'2026-09-11','description':'Окремий синтетичний факт '+str(index),'category':'salary'},
            operation_id='a07-separate-fact-'+str(index))
        ids.append(tx.pk)
    receipt = {'transaction_ids':ids}
else:
    raise RuntimeError('Unknown synthetic case')
connection.close()
print(json.dumps(receipt))
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def media_bytes(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(Path(root).rglob('*')) if path.is_file()}


class DataPreflightAdmissionTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.checkout = Path(preflight_data.__file__).resolve().parents[1]
        cls.storage = tempfile.TemporaryDirectory(prefix='bos_verify_data_preflight_')
        cls.addClassCleanup(cls.storage.cleanup)
        cls.root = Path(cls.storage.name)
        cls.base_media = cls.root / 'base_media'
        cls.base_media.mkdir()
        cls.receipts = {}
        for profile in ('latest', 'historical'):
            path = cls.root / ('base_' + profile + '.sqlite3')
            env = cls.environment(path, cls.base_media)
            process = subprocess.run([sys.executable, '-B', '-c', MAKE_TEMPLATE, profile],
                cwd=cls.checkout, env=env, capture_output=True, text=True, timeout=90)
            if process.returncode:
                raise AssertionError('Synthetic source creation failed:\n' + process.stdout + process.stderr)
            cls.receipts[profile] = json.loads(process.stdout.strip().splitlines()[-1])
            if cls.receipts[profile]['backend'] != 'sqlite':
                raise AssertionError('This source must be an actual SQLite database')
        cls.template_sha = {profile: sha(cls.root / ('base_' + profile + '.sqlite3'))
                            for profile in cls.receipts}
        cls.template_media = media_bytes(cls.base_media)

    @classmethod
    def environment(cls, path, media):
        return dict(os.environ, DJANGO_SETTINGS_MODULE='verification_settings',
            BOS_VERIFY_DB='sqlite', BOS_TEST_DB_NAME=str(path), BOS_TEST_MEDIA=str(media),
            BOS_DATA_MODE='working', PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(cls.checkout))

    def setUp(self):
        self.snapshot = self.root / (self._testMethodName + '.sqlite3')
        shutil.copyfile(self.root / 'base_latest.sqlite3', self.snapshot)
        self.media = self.root / (self._testMethodName + '_media')
        shutil.copytree(self.base_media, self.media)

    def scenario(self, name):
        process = subprocess.run([sys.executable, '-B', '-c', ADD_SCENARIO, name],
            cwd=self.checkout, env=self.environment(self.snapshot, self.media),
            capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        return json.loads(process.stdout.strip().splitlines()[-1])

    def rows(self, table, columns='*'):
        # Only fixed test identifiers reach this helper; values never build SQL.
        allowed = {'finance_financialintent', 'finance_transaction', 'operations_document',
                   'ai_assistant_chatfile', 'sqlite_master'}
        self.assertIn(table, allowed)
        with closing(sqlite3.connect(self.snapshot.as_uri() + '?mode=ro&immutable=1', uri=True)) as connection:
            connection.execute('PRAGMA query_only=ON')
            return connection.execute('SELECT ' + columns + ' FROM ' + table).fetchall()

    def inspect_cli(self):
        before = sha(self.snapshot)
        physical = media_bytes(self.media)
        output = self.root / ('report_' + uuid4().hex + '.json')
        process = subprocess.run([sys.executable, '-B', str(self.checkout / 'scripts' / 'preflight_data.py'),
            '--snapshot', str(self.snapshot), '--media', str(self.media), '--output', str(output)],
            cwd=self.checkout, env=self.environment(self.snapshot, self.media),
            capture_output=True, text=True, timeout=60)
        self.assertIn(process.returncode, (0, 1), process.stdout + process.stderr)
        self.assertTrue(output.is_file(), process.stdout + process.stderr)
        report = json.loads(output.read_text())
        self.assertEqual(process.returncode, 0 if report['can_migrate'] else 1)
        self.assertTrue(report['source_unchanged'], report)
        self.assertEqual(report['source_sha256'], before)
        self.assertEqual(sha(self.snapshot), before)
        self.assertEqual(media_bytes(self.media), physical)
        self.assertFalse(any(Path(str(self.snapshot) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')))
        for profile, value in self.template_sha.items():
            self.assertEqual(sha(self.root / ('base_' + profile + '.sqlite3')), value)
        self.assertEqual(media_bytes(self.base_media), self.template_media)
        self.assertIn('target_database', report['not_checked'])
        self.assertIn('production_cutover', report['not_checked'])
        return report

    def test_complete_intent_document_and_archived_file_are_accepted_without_changing_bytes(self):
        fixture = self.receipts['latest']
        before_intents = self.rows('finance_financialintent')
        before_documents = self.rows('operations_document')
        before_files = self.rows('ai_assistant_chatfile')
        for _ in range(2):
            report = self.inspect_cli()
            self.assertTrue(report['can_migrate'], report['findings'])
            self.assertEqual(report['findings'], [])
            self.assertTrue(report['schema']['complete'])
            self.assertTrue(report['accounting']['complete'])
            self.assertEqual(report['manifest']['tables']['finance_financialintent']['count'], 1)
            self.assertEqual(report['manifest']['tables']['finance_transaction']['decimal_totals']['amount'], {'EUR':'123.45'})
            self.assertEqual(report['manifest']['media'], [{'path':fixture['media_relative'],
                'bytes':fixture['bytes_size'], 'sha256':fixture['bytes_sha256']}])
            self.assertEqual(self.rows('finance_financialintent'), before_intents)
            self.assertEqual(self.rows('operations_document'), before_documents)
            self.assertEqual(self.rows('ai_assistant_chatfile'), before_files)

    def test_committed_financial_intent_without_source_is_refused_without_repair(self):
        fixture = self.scenario('orphan')
        self.assertEqual(fixture['sources'], [None, None])
        before = self.rows('finance_financialintent')
        self.assertEqual(len(before), 2, 'One completed receipt and one committed empty claim are required')
        for _ in range(2):
            report = self.inspect_cli()
            self.assertTrue(report['schema']['complete'], report['schema']['findings'])
            self.assertFalse(report['can_migrate'])
            findings = [row for row in report['findings'] if row.get('code') == 'FINANCIAL_INTENT_WITHOUT_SOURCE']
            self.assertEqual(findings, [{'code':'FINANCIAL_INTENT_WITHOUT_SOURCE',
                'table':'finance_financialintent', 'pk':fixture['key']}])
            self.assertEqual(self.rows('finance_financialintent'), before)
            self.assertEqual(report['manifest']['tables']['finance_financialintent']['count'], 2)
            self.assertFalse(report['accounting']['stop_required'])

    def test_equal_amount_date_expenses_remain_candidates_and_keep_distinct_ids(self):
        fixture = self.scenario('candidates')
        expected = fixture['transaction_ids']
        self.assertEqual(len(set(expected)), 2)
        before = self.rows('finance_transaction')
        self.assertEqual(len(before), 3)
        for _ in range(2):
            report = self.inspect_cli()
            self.assertTrue(report['can_migrate'], report['findings'])
            self.assertEqual(report['findings'], [])
            candidates = [row for row in report['warnings'] if row.get('code') == 'SIMILAR_SALARY_EXPENSES']
            self.assertEqual(len(candidates), 1, report['warnings'])
            self.assertEqual(candidates[0]['classification'], 'candidate')
            facts = candidates[0]['facts']
            self.assertEqual(facts['transaction_ids'], expected)
            self.assertEqual(facts['unlinked_ids'], expected)
            self.assertFalse(facts['confirmed_duplicate'])
            self.assertEqual(Decimal(facts['amount_each']), Decimal('100.25'))
            self.assertEqual((facts['currency'], facts['date']), ('UAH','2026-09-11'))
            self.assertFalse(report['accounting']['stop_required'])
            self.assertEqual(report['manifest']['tables']['finance_transaction']['count'], 3)
            self.assertEqual(report['manifest']['tables']['finance_transaction']['decimal_totals']['amount'],
                             {'EUR':'123.45', 'UAH':'200.5'})
            self.assertEqual(self.rows('finance_transaction'), before)

    def test_known_incomplete_historical_schema_is_explicitly_refused_without_new_tables(self):
        shutil.copyfile(self.root / 'base_historical.sqlite3', self.snapshot)
        tables_before = self.rows('sqlite_master', 'type,name,tbl_name,sql')
        self.assertFalse(any(row[1].startswith('erp_') for row in tables_before))
        report = self.inspect_cli()
        self.assertTrue(report['schema']['known_migrations'])
        self.assertEqual(report['schema']['profile'], 'historical')
        self.assertTrue(report['schema']['complete'], report['schema']['findings'])
        self.assertFalse(report['can_migrate'])
        self.assertFalse(report['accounting']['complete'])
        codes = {finding['code'] for finding in report['findings']}
        self.assertIn('SCHEMA_MISSING', codes)
        self.assertIn('SOURCE_RECONCILIATION_INCOMPLETE', codes)
        self.assertEqual(self.rows('sqlite_master', 'type,name,tbl_name,sql'), tables_before)
