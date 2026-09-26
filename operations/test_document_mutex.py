"""A06: document writers share the ERP admission mutex.

Only synthetic data. Real HTTP and SQL; execute_wrapper forwards each statement
exactly once. The two ordering tests are a portable locking contract, not proof
of a PostgreSQL race. The two interleavings also expose SQLite's coarse lock.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal as D
import hashlib
import json
import os
from pathlib import Path
import threading
import time

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, connections, transaction
from django.db.models import Sum
from django.test import Client, TransactionTestCase, override_settings

from employees.models import Employee
from finance.models import Counterparty
from erp import service
from erp.models import Item, Location, Lot, SalesOrder, SalesLine, Reservation
from erp.models import Movement, Inspection, Event
from operations.models import ActionProposal, Configuration, Document
from scripts.check_support import login_test_client


@override_settings(BOS_DATA_MODE='working', DEBUG=False, ANTHROPIC_API_KEY='',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class A06DocumentMutexTests(TransactionTestCase):
    def setUp(self):
        if os.environ.get('DJANGO_SETTINGS_MODULE') != 'verification_settings':
            self.fail('Run only with synthetic verification_settings')
        if connection.vendor == 'sqlite':
            name = str(connection.settings_dict['NAME'])
            self.assertNotIn('memory', name, 'Concurrency needs a new file-backed SQLite DB')
            self.assertIn('check_', Path(name).name, 'A working database is not accepted')
        self.evidence = {'test': self.id(), 'backend': connection.vendor, 'trace': []}
        with connection.cursor() as cursor:
            cursor.execute('SELECT sqlite_version()' if connection.vendor == 'sqlite'
                           else 'SHOW server_version')
            self.evidence['database_version'] = cursor.fetchone()[0]
        self.addCleanup(self.save_evidence)
        self.client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        login_test_client(self.client, 'ceo')
        self.cookies = deepcopy(self.client.cookies)
        self.mutex, _ = Configuration.objects.get_or_create(
            key='erp_write', defaults={'value': {'revision': 0}})
        self.employee = Employee.objects.create(full_name='Синтетичний оператор A06 documents')
        self.customer = Counterparty.objects.create(name='Синтетичний замовник A06', type='customer')
        self.location = Location.objects.create(code='A06-DOC-W', name='Синтетичний склад')
        self.item = Item.objects.create(code='A06-DOC-M', name='Синтетичний матеріал',
            kind='material', method='buy', revision='A', required_documents=['cert'], currency='EUR')
        data = b'A06 synthetic certificate revision A'
        self.doc = Document.objects.create(code='A06-CERT', revision='A', title='Синтетичний сертифікат',
            filename='a06-cert.txt', text=data.decode(), content=data, status='approved',
            checksum=hashlib.sha256(data).hexdigest(), access_level='operational')
        self.lot = Lot.objects.create(code='A06-DOC-L', item=self.item, location=self.location,
            revision='A', quantity=D('10'), unit_cost=D('2.00'), currency='EUR',
            quality='approved', documents={'cert': self.doc.pk})
        Movement.objects.create(lot=self.lot, quantity=D('10'), kind='opening',
            reference='A06-OPEN', cost=D('20.00'))
        self.order = SalesOrder.objects.create(code='A06-DOC-SO', customer=self.customer,
            owner=self.employee, due_date='2026-10-01', currency='EUR', status='confirmed')
        self.line = SalesLine.objects.create(order=self.order, item=self.item, revision='A',
            quantity=D('10'), price=D('5.00'))
        self.reservation = Reservation.objects.create(lot=self.lot, line=self.line, quantity=D('10'))

    def save_evidence(self):
        directory = os.environ.get('A06_DOCUMENT_EVIDENCE_DIR')
        if directory:
            target = Path(directory)
            target.mkdir(parents=True, exist_ok=True)
            (target / (self._testMethodName + '.json')).write_text(
                json.dumps(self.evidence, ensure_ascii=False, indent=2, default=str) + '\n')

    def cloned_client(self):
        client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        client.cookies = deepcopy(self.cookies)
        return client

    def post(self, client, path, payload):
        return client.post(path, payload, content_type='application/json',
            HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)

    def document_request(self, kind, client):
        if kind == 'upload':
            upload = SimpleUploadedFile('a06-cert-b.txt', b'A06 synthetic certificate revision B',
                                        content_type='text/plain')
            return client.post('/api/operations/documents/upload/',
                {'code': self.doc.code, 'revision': 'B', 'title': 'Синтетичний сертифікат B', 'file': upload},
                HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
        return self.post(client, f'/api/operations/documents/{self.doc.pk}/review/',
                         {'checksum': self.doc.checksum})

    def sql_info(self, sql, params, context, worker):
        normalized = ' '.join(sql.lower().split())
        operation = normalized.split(' ', 1)[0]
        table = next((name for name in ('operations_configuration', 'operations_document',
            'erp_reservation', 'erp_lot', 'erp_movement', 'erp_inspection')
            if '"' + name + '"' in normalized), None)
        lock = (operation == 'update' and table == 'operations_configuration'
                and bool(params) and params[-1] == self.mutex.pk)
        return {'worker': worker, 'operation': operation, 'table': table,
                'erp_mutex': lock, 'atomic': context['connection'].in_atomic_block,
                'sql': normalized, 'completed': False}

    def record_sql(self, worker, control=None):
        def wrapper(execute, sql, params, many, context):
            row = self.sql_info(sql, params, context, worker)
            if row['table']:
                self.evidence['trace'].append(row)
            if control:
                control('before', row)
            # The original SQL is invoked exactly once, without replacement.
            result = execute(sql, params, many, context)
            row['completed'] = True
            if control:
                control('after', row)
            return result
        return wrapper

    def assert_admission_lock_order(self):
        rows = self.evidence['trace']
        locks = [i for i, row in enumerate(rows) if row['erp_mutex'] and row['completed']]
        reads = [i for i, row in enumerate(rows)
                 if row['table'] == 'operations_document' and row['operation'] == 'select']
        writes = [i for i, row in enumerate(rows)
                  if row['table'] == 'operations_document' and row['operation'] in ('insert', 'update')]
        self.assertTrue(reads, 'A real Document decision was read')
        self.assertTrue(writes, 'A real Document write was executed')
        self.assertTrue(locks, 'Document admission writer must acquire the same ERP mutex')
        self.assertLess(min(locks), min(reads), 'Lock must precede the first Document admission read')
        self.assertLess(min(locks), min(writes))
        self.assertTrue(all(rows[i]['atomic'] for i in locks + reads + writes),
                        'Lock, current-document decision and write must share a transaction')

    def test_upload_locks_before_document_admission_reads_and_insert(self):
        with connection.execute_wrapper(self.record_sql('upload')):
            response = self.document_request('upload', self.client)
        self.evidence['http'] = {'status': response.status_code, 'body': response.json()}
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Document.objects.filter(code=self.doc.code).count(), 2)
        self.assertEqual(Movement.objects.count(), 1)
        self.assert_admission_lock_order()

    def test_review_locks_before_document_admission_reads_and_update(self):
        Document.objects.filter(pk=self.doc.pk).update(status='needs_review')
        with connection.execute_wrapper(self.record_sql('review')):
            response = self.document_request('review', self.client)
        self.evidence['http'] = {'status': response.status_code, 'body': response.json()}
        self.assertEqual(response.status_code, 200, response.content)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, 'approved')
        self.assertEqual(Movement.objects.count(), 1)
        self.assert_admission_lock_order()

    def interleave(self, kind):
        if kind == 'review':
            Document.objects.filter(pk=self.doc.pk).update(status='needs_review')
            Lot.objects.filter(pk=self.lot.pk).update(quality='pending')
            payload = {'action': 'erp_quality', 'lot_id': self.lot.pk, 'result': 'approved',
                       'inspector_id': self.employee.pk, 'note': 'Синтетичний контроль A06'}
            # Generic approval creates a real intent. Actual admission must
            # reject the unreviewed certificate during confirmation.
            preview_path = '/api/operations/preview/'
        else:
            payload = {'action': 'erp_ship', 'line_id': self.line.pk, 'lot_id': self.lot.pk,
                       'quantity': '7', 'reference': 'A06-DOC-SHIP'}
            preview_path = '/api/erp/preview/'
        response = self.post(self.client, preview_path, payload)
        self.assertEqual(response.status_code, 200, response.content)
        proposal = response.json()['id']
        ready = threading.Event()
        release = threading.Event()
        document_attempt = threading.Event()
        document_committed = threading.Event()
        active_section = threading.Event()
        erp_locks = 0
        observations = {'document_committed_inside_paused_section': False}

        def erp_control(phase, row):
            nonlocal erp_locks
            if phase == 'after' and row['erp_mutex']:
                erp_locks += 1
            pause = (phase == 'before' and not ready.is_set() and erp_locks >= 2 and
                     ((kind == 'upload' and row['operation'] == 'update' and row['table'] == 'erp_reservation')
                      or (kind == 'review' and row['operation'] == 'select' and row['table'] == 'operations_document')))
            if pause:
                # ERP lock, fresh fingerprint and snapshot have already run.
                active_section.set()
                ready.set()
                if not release.wait(6):
                    raise TimeoutError('Controller did not release the ERP SQL statement')
                active_section.clear()

        def document_control(phase, row):
            document_write = row['table'] == 'operations_document' and row['operation'] in ('insert', 'update')
            if phase == 'before' and (row['erp_mutex'] or document_write):
                document_attempt.set()
            if phase == 'after' and document_write:
                def committed():
                    observations['document_committed_inside_paused_section'] = active_section.is_set()
                    document_committed.set()
                transaction.on_commit(committed)

        def worker(name):
            try:
                client = self.cloned_client()
                control = erp_control if name == 'erp' else document_control
                with connection.execute_wrapper(self.record_sql(name, control)):
                    response = (self.post(client, '/api/operations/confirm/',
                        {'proposal_id': proposal, 'confirmed': True}) if name == 'erp'
                        else self.document_request(kind, client))
                return {'status': response.status_code, 'body': response.json()}
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            erp_future = pool.submit(worker, 'erp')
            try:
                self.assertTrue(ready.wait(5), 'ERP did not reach the observed admission/write boundary')
                doc_future = pool.submit(worker, 'document')
                self.assertTrue(document_attempt.wait(5), 'Document request did not attempt a real SQL write/lock')
                document_committed.wait(0.5)
            finally:
                release.set()
            erp_result = erp_future.result(timeout=8)
            doc_result = doc_future.result(timeout=8)
        self.evidence['interleaving'] = {'kind': kind, 'erp': erp_result, 'document': doc_result,
                                       **observations, 'erp_mutex_updates': erp_locks}
        self.assertFalse(observations['document_committed_inside_paused_section'],
                         'Document committed inside the ERP admission-to-write critical section')
        self.assertEqual(erp_result['status'], 200 if kind == 'upload' else 422, erp_result)
        self.assertIn(doc_result['status'], (201, 409) if kind == 'upload' else (200, 409), doc_result)
        if doc_result['status'] == 409:
            retry = self.document_request(kind, self.client)
            self.evidence['document_retry'] = {'status': retry.status_code, 'body': retry.json()}
            self.assertEqual(retry.status_code, 201 if kind == 'upload' else 200, retry.content)
        self.lot.refresh_from_db()
        self.line.refresh_from_db()
        self.reservation.refresh_from_db()
        total = self.lot.movements.aggregate(n=Sum('quantity'))['n'] or D('0')
        self.assertEqual(self.lot.quantity, total)
        self.assertGreaterEqual(self.reservation.quantity, D('0'))
        self.assertLessEqual(self.reservation.quantity, self.lot.quantity)
        if kind == 'upload':
            self.assertEqual((self.lot.quantity, self.line.shipped, self.reservation.quantity),
                             (D('3'), D('7'), D('3')))
            self.assertEqual(Movement.objects.filter(kind='shipment').count(), 1)
            self.assertEqual(Event.objects.filter(action='erp_ship').count(), 1)
            self.assertEqual(Document.objects.filter(code=self.doc.code).count(), 2)
            self.assertFalse(service.usable(self.lot), 'Old certificate is no longer latest for a new shipment')
            later = self.post(self.client, '/api/erp/preview/', {**payload, 'quantity': '1', 'reference': 'A06-LATER'})
            self.assertEqual(later.status_code, 422, later.content)
            self.assertEqual(Movement.objects.filter(kind='shipment').count(), 1)
        else:
            self.assertEqual((self.lot.quantity, self.lot.quality), (D('10'), 'pending'))
            self.assertEqual(Inspection.objects.count(), 0)
            self.assertEqual(Event.objects.count(), 0)
            self.assertIsNone(ActionProposal.objects.get(pk=proposal).receipt)
            self.doc.refresh_from_db()
            self.assertEqual(self.doc.status, 'approved')
            fresh = self.post(self.client, '/api/erp/preview/', payload)
            self.assertEqual(fresh.status_code, 200, fresh.content)
            confirmed = self.post(self.client, '/api/operations/confirm/',
                {'proposal_id': fresh.json()['id'], 'confirmed': True})
            self.assertEqual(confirmed.status_code, 200, confirmed.content)
            self.lot.refresh_from_db()
            self.assertEqual(self.lot.quality, 'approved')
            self.assertEqual(Inspection.objects.count(), 1)
            self.assertEqual(Movement.objects.count(), 1)

    def test_upload_cannot_commit_inside_shipment_critical_section(self):
        self.interleave('upload')

    def test_review_cannot_commit_inside_quality_critical_section(self):
        self.interleave('review')
