"""Scoped ERP adjustment behavior through the actual CSRF HTTP routes."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal as D
import hashlib
import os
from pathlib import Path
import re

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.db import connection, transaction
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from boss_project.policy import Policy
from employees.models import Employee
from finance.models import Counterparty
from operations.models import ActionProposal, Configuration, Document
from scripts.check_support import login_test_client
from .models import Event, Item, Location, Lot, Movement, Reservation, SalesLine, SalesOrder
from . import service


class AdjustmentProposalTests(TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('DJANGO_SETTINGS_MODULE'), 'verification_settings')
        name = str(connection.settings_dict['NAME'])
        with connection.cursor() as cursor:
            if connection.vendor == 'sqlite':
                self.assertTrue(Path(name).name.startswith('check_'))
                cursor.execute('PRAGMA database_list')
                self.assertEqual(Path(next(row[2] for row in cursor.fetchall() if row[1]=='main')).resolve(), Path(name).resolve())
            else:
                self.assertEqual(connection.vendor, 'postgresql')
                self.assertRegex(name, r'^test_bos_verify_[0-9a-f]{16}$')
                cursor.execute('SELECT current_database()')
                self.assertEqual(cursor.fetchone()[0], name)
        self.a = Client(enforce_csrf_checks=True)
        self.b = Client(enforce_csrf_checks=True)
        self.user_a = login_test_client(self.a)
        self.user_b = login_test_client(self.b)
        self.item = Item.objects.create(code='N2-ITEM', name='Synthetic N2 item')
        self.location = Location.objects.create(code='N2-LOC', name='Synthetic warehouse')
        self.lot_a = self.lot('N2-A')
        self.lot_b = self.lot('N2-B')
        Configuration.objects.get_or_create(key='erp_write', defaults={'value': {'revision': 0}})

    def lot(self, code):
        lot = service.newlot(code, self.item, self.location, D('10'), D('2'), 'EUR',
                             'A', {}, 'opening', code)
        lot.quality = 'approved'
        lot.save(update_fields=['quality'])
        return lot

    def payload(self, lot=None, delta='-1'):
        return {'action': 'erp_adjust', 'lot_id': (lot or self.lot_a).pk,
                'delta': delta, 'reason': 'Synthetic inventory count'}

    def post(self, client, url, payload):
        return client.post(url, payload, content_type='application/json',
                           HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)

    def preview(self, client=None, lot=None, delta='-1', generic=False):
        response = self.post(client or self.a,
                             '/api/operations/preview/' if generic else '/api/erp/preview/',
                             self.payload(lot, delta))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def confirm(self, proposal, client=None):
        return self.post(client or self.a, '/api/operations/confirm/',
                         {'proposal_id': proposal['id'], 'confirmed': True})

    def business(self):
        return {'lots': list(Lot.objects.order_by('pk').values()),
                'movements': list(Movement.objects.order_by('pk').values()),
                'events': list(Event.objects.order_by('pk').values()),
                'reservations': list(Reservation.objects.order_by('pk').values()),
                'mutex': Configuration.objects.get(key='erp_write').value}

    def assert_refused_unchanged(self, proposal, status=409, client=None):
        before = self.business()
        response = self.confirm(proposal, client)
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(self.business(), before)
        self.assertIsNone(ActionProposal.objects.get(pk=proposal['id']).receipt)

    def reservation(self, lot=None, quantity='1'):
        owner = Employee.objects.create(full_name='Synthetic N2 owner')
        customer = Counterparty.objects.create(name='Synthetic N2 customer', type='customer')
        order = SalesOrder.objects.create(code='N2-ORDER', customer=customer, owner=owner,
                                          due_date='2026-12-01', status='confirmed')
        line = SalesLine.objects.create(order=order, item=self.item, revision='A', quantity=10, price=2)
        return Reservation.objects.create(lot=lot or self.lot_a, line=line, quantity=quantity)

    def document(self, *, code='N2-DOC', revision='A', data=b'synthetic certificate'):
        return Document.objects.create(code=code, revision=revision, title='Synthetic certificate',
                                       text=data.decode(), content=data, status='approved',
                                       checksum=hashlib.sha256(data).hexdigest())

    def bind_document(self, document):
        self.item.required_documents = ['certificate']
        self.item.save(update_fields=['required_documents'])
        self.lot_a.documents = {'certificate': document.pk}
        self.lot_a.save(update_fields=['documents'])

    def test_independent_users_keep_original_effect_after_other_lot_confirmation(self):
        before = self.business()
        pa = self.preview()
        pb = self.preview(self.b, self.lot_b, '-2')
        self.assertEqual(self.business(), before, 'Preview simulations leave no business writes')
        self.assertNotEqual(self.user_a.pk, self.user_b.pk)
        self.assertNotEqual(self.a.session.session_key, self.b.session.session_key)
        rb = self.confirm(pb, self.b)
        self.assertEqual(rb.status_code, 200, rb.content)
        ra = self.confirm(pa)
        self.assertEqual(ra.status_code, 200, ra.content)
        self.assertEqual(ra.json()['impact'], pa['impact'])
        self.assertEqual(rb.json()['impact'], pb['impact'])
        self.assertEqual(Movement.objects.filter(kind='adjustment').count(), 2)
        self.assertEqual(Event.objects.count(), 2)
        self.lot_a.refresh_from_db(); self.lot_b.refresh_from_db()
        self.assertEqual((self.lot_a.quantity, self.lot_b.quantity), (D('9'), D('8')))

    def test_same_lot_conflicts_without_any_second_effect(self):
        pa = self.preview(); pb = self.preview(self.b, self.lot_a, '-2')
        self.assertEqual(self.confirm(pb, self.b).status_code, 200)
        self.assert_refused_unchanged(pa)

    def test_context_keeps_initial_global_fingerprint_and_not_client_fields(self):
        initial = service.fingerprint()
        proposal = self.preview()
        row = ActionProposal.objects.get(pk=proposal['id'])
        self.assertEqual(row.fingerprint, initial)
        self.assertEqual(row.payload, self.payload())
        self.assertEqual(row.dependency_context['mode'], 'erp_adjust')
        self.assertEqual(row.dependency_context['version'], 1)
        self.assertNotIn('dependency_context', proposal)
        response = self.post(self.a, '/api/erp/preview/', {**self.payload(), 'dependency_context': row.dependency_context})
        self.assertEqual(response.status_code, 422)

    def test_legacy_generic_and_null_context_still_use_original_global_token(self):
        for generic in (True, False):
            with self.subTest(generic=generic), transaction.atomic():
                proposal = self.preview(generic=generic)
                if not generic:
                    ActionProposal.objects.filter(pk=proposal['id']).update(dependency_context=None)
                else:
                    self.assertIsNone(ActionProposal.objects.get(pk=proposal['id']).dependency_context)
                other = self.preview(self.b, self.lot_b)
                self.assertEqual(self.confirm(other, self.b).status_code, 200)
                self.assert_refused_unchanged(proposal)
                transaction.set_rollback(True)

    def test_malformed_future_and_wrong_action_contexts_fail_closed(self):
        initial = self.preview()
        context = ActionProposal.objects.get(pk=initial['id']).dependency_context
        cases = [[], {}, {**context, 'version': 2}, {**context, 'version': True},
                 {**context, 'mode': 'erp_ship'}, {**context, 'dependency_sha256': 'invalid'},
                 {key: value for key, value in context.items() if key != 'impact_sha256'}]
        for value in cases:
            with self.subTest(context=value):
                ActionProposal.objects.filter(pk=initial['id']).update(dependency_context=value)
                self.assert_refused_unchanged(initial)

    def test_payload_tampering_fails_closed(self):
        proposal = self.preview()
        ActionProposal.objects.filter(pk=proposal['id']).update(payload=self.payload(delta='-2'))
        self.assert_refused_unchanged(proposal)

    def test_target_lot_item_and_location_changes_invalidate(self):
        mutations = [
            (Lot, self.lot_a.pk, {'unit_cost': D('3')}),
            (Lot, self.lot_a.pk, {'quality': 'blocked'}),
            (Lot, self.lot_a.pk, {'revision': 'B'}),
            (Lot, self.lot_a.pk, {'code': 'N2-A-RENAMED'}),
            (Lot, self.lot_a.pk, {'quantity': D('11')}),
            (Item, self.item.pk, {'required_documents': ['inspection']}),
            (Location, self.location.pk, {'name': 'Changed warehouse'}),
        ]
        for model, identity, values in mutations:
            with self.subTest(model=model.__name__, fields=values), transaction.atomic():
                proposal = self.preview()
                model.objects.filter(pk=identity).update(**values)
                self.assert_refused_unchanged(proposal)
                transaction.set_rollback(True)

    def test_reservation_creation_edit_deletion_and_same_sum_membership_invalidate(self):
        reserve = self.reservation()
        for mutation in ('insert', 'update', 'delete', 'same_sum'):
            with self.subTest(mutation=mutation), transaction.atomic():
                proposal = self.preview()
                if mutation == 'insert':
                    Reservation.objects.create(lot=self.lot_a, line=reserve.line, quantity='1')
                elif mutation == 'update':
                    Reservation.objects.filter(pk=reserve.pk).update(quantity='2')
                elif mutation == 'delete':
                    Reservation.objects.filter(pk=reserve.pk).delete()
                else:
                    Reservation.objects.filter(pk=reserve.pk).update(quantity='0')
                    Reservation.objects.create(lot=self.lot_a, line=reserve.line, quantity='1')
                self.assert_refused_unchanged(proposal)
                transaction.set_rollback(True)

    def test_target_movement_membership_invalidate_even_without_quantity_change(self):
        proposal = self.preview()
        Movement.objects.create(lot=self.lot_a, quantity=0, kind='adjustment', reference='N2-ZERO')
        self.assert_refused_unchanged(proposal)

    def test_unrelated_reservation_does_not_invalidate(self):
        proposal = self.preview()
        self.reservation(self.lot_b)
        response = self.confirm(proposal)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['impact'], proposal['impact'])

    def test_document_versions_metadata_and_real_source_bytes_invalidate(self):
        document = self.document(); self.bind_document(document)
        for mutation in ('new_version', 'status', 'access', 'bytes', 'checksum'):
            with self.subTest(mutation=mutation), transaction.atomic():
                proposal = self.preview()
                self.assertIsNotNone(ActionProposal.objects.get(pk=proposal['id']).dependency_context)
                if mutation == 'new_version':self.document(revision='B')
                elif mutation == 'status':Document.objects.filter(pk=document.pk).update(status='needs_review')
                elif mutation == 'access':Document.objects.filter(pk=document.pk).update(access_level='operational')
                elif mutation == 'bytes':Document.objects.filter(pk=document.pk).update(content=b'corrupted source')
                else:Document.objects.filter(pk=document.pk).update(checksum='0' * 64)
                self.assert_refused_unchanged(proposal)
                transaction.set_rollback(True)

    def test_missing_document_becoming_present_invalidates(self):
        self.item.required_documents=['certificate']; self.item.save(update_fields=['required_documents'])
        self.lot_a.documents={'certificate': 900001}; self.lot_a.save(update_fields=['documents'])
        proposal = self.preview()
        Document.objects.create(pk=900001, code='N2-MISSING', revision='A', title='New source',
                                content=b'present', checksum=hashlib.sha256(b'present').hexdigest(), status='approved')
        self.assert_refused_unchanged(proposal)

    def test_invalid_initial_source_remains_explicit_legacy_mode(self):
        document = self.document(); self.bind_document(document)
        Document.objects.filter(pk=document.pk).update(content=b'broken')
        proposal = self.preview()
        self.assertIsNone(ActionProposal.objects.get(pk=proposal['id']).dependency_context)

    def test_expiry_other_session_role_permission_and_archive_refuse(self):
        proposal = self.preview()
        self.assert_refused_unchanged(proposal, 403, self.b)
        cases = ('expiry', 'role', 'permission', 'archive')
        for mutation in cases:
            with self.subTest(mutation=mutation), transaction.atomic():
                proposal = self.preview()
                expected = 409
                if mutation == 'expiry':
                    ActionProposal.objects.filter(pk=proposal['id']).update(expires_at=timezone.now()-timedelta(seconds=1))
                elif mutation == 'role':
                    self.user_a.groups.set([Group.objects.get_or_create(name='manager')[0]]); expected=403
                elif mutation == 'permission':
                    self.user_a.user_permissions.add(Permission.objects.get(content_type__app_label='operations', codename='view_document'))
                else:
                    employee=Employee.objects.create(full_name='Archived N2 actor', user=self.user_a)
                    employee.delete(actor=self.user_b); expected=403
                self.assert_refused_unchanged(proposal, expected)
                transaction.set_rollback(True)

    def test_replay_after_changes_keeps_one_receipt_and_current_policy(self):
        proposal = self.preview()
        response = self.confirm(proposal)
        self.assertEqual(response.status_code, 200, response.content)
        receipt = response.json()
        service.dispatch(self.payload(self.lot_b, '-2'), 'ceo')
        service.dispatch(self.payload(self.lot_a, '-1'), 'ceo')
        before = self.business()
        repeated = self.confirm(proposal)
        self.assertEqual(repeated.status_code, 200, repeated.content)
        self.assertEqual(repeated.json(), receipt)
        after = self.business()
        # Existing replay holds the mutex and advances its revision, but no business effect.
        before.pop('mutex'); after.pop('mutex')
        self.assertEqual(after, before)
        self.user_a.groups.set([Group.objects.get_or_create(name='manager')[0]])
        self.assertEqual(self.confirm(proposal).status_code, 403)

    def test_frozen_expected_effect_and_impact_mismatch_roll_back_all_writes(self):
        for key in ('effect_sha256', 'impact_sha256'):
            with self.subTest(key=key):
                proposal = self.preview()
                row = ActionProposal.objects.get(pk=proposal['id'])
                context = deepcopy(row.dependency_context); context[key] = '0' * 64
                ActionProposal.objects.filter(pk=row.pk).update(dependency_context=context)
                self.assert_refused_unchanged(proposal)

    def test_erp_lock_precedes_dependency_reads_and_fresh_policy_after_wait(self):
        with CaptureQueriesContext(connection) as captured:
            proposal = self.preview()
        sql = [row['sql'].lower() for row in captured.captured_queries]
        first_write = next(i for i, row in enumerate(sql) if row.startswith('update "operations_configuration"'))
        first_read = next(i for i, row in enumerate(sql) if row.startswith('select') and '"erp_' in row)
        self.assertLess(first_write, first_read)
        original = service.write_lock
        def revoke_after_lock():
            original()
            self.user_a.groups.set([Group.objects.get_or_create(name='manager')[0]])
        with patch('erp.service.write_lock', side_effect=revoke_after_lock):
            self.assert_refused_unchanged(proposal, 403)

    def test_access_change_during_preview_does_not_issue_scoped_proposal(self):
        from . import adjustment_proposals
        original = adjustment_proposals.snapshot
        calls = 0
        def change_access(payload, policy):
            nonlocal calls
            calls += 1
            result = original(payload, policy)
            if calls == 2:
                self.user_a.user_permissions.add(Permission.objects.get(content_type__app_label='operations', codename='view_document'))
            return result
        before = self.business()
        with patch('erp.adjustment_proposals.snapshot', side_effect=change_access):
            response = self.post(self.a, '/api/erp/preview/', self.payload())
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(self.business(), before)
        self.assertEqual(ActionProposal.objects.count(), 0)

    def test_lot_only_impact_matches_complete_snapshot_for_displayed_effects(self):
        from . import adjustment_proposals, experience, queries
        reserve = self.reservation(quantity='2')
        for state, delta in (('approved', '-1'), ('blocked', '-1'), ('missing', '-1'), ('approved', '0')):
            with self.subTest(state=state, delta=delta), transaction.atomic():
                Lot.objects.filter(pk=self.lot_a.pk).update(quality='blocked' if state=='blocked' else 'approved')
                Item.objects.filter(pk=self.item.pk).update(required_documents=['certificate'] if state=='missing' else [])
                request = self.a.get('/api/erp/snapshot/').wsgi_request
                payload = self.payload(delta=delta)
                policy = Policy(request)
                full_before = queries.snapshot(policy)
                scoped_before = adjustment_proposals.snapshot(payload, policy)
                service.dispatch(payload, 'ceo', log=False)
                full_after = queries.snapshot(Policy(request))
                scoped_after = adjustment_proposals.snapshot(payload, Policy(request))
                self.assertEqual(experience.impact(full_before, full_after), experience.impact(scoped_before, scoped_after))
                transaction.set_rollback(True)

    def test_private_file_bytes_change_with_unchanged_document_row_refuses(self):
        response = self.a.post('/api/operations/documents/upload/',
                               {'code': 'N2-PRIVATE', 'revision': 'A', 'title': 'Synthetic private source',
                                'file': SimpleUploadedFile('n2.txt', b'Synthetic private certificate', content_type='text/plain')},
                               HTTP_X_CSRFTOKEN=self.a.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 201, response.content)
        document = Document.objects.get(pk=response.json()['id'])
        reviewed = self.post(self.a, f'/api/operations/documents/{document.pk}/review/', {'checksum': document.checksum})
        self.assertEqual(reviewed.status_code, 200, reviewed.content)
        self.bind_document(document)
        proposal = self.preview()
        self.assertIsNotNone(ActionProposal.objects.get(pk=proposal['id']).dependency_context)
        before_document = Document.objects.filter(pk=document.pk).values().get()
        filename = Path(settings.MEDIA_ROOT) / document.original_file.name
        self.assertTrue(filename.is_file())
        filename.write_bytes(b'Substituted private certificate')
        self.assertEqual(Document.objects.filter(pk=document.pk).values().get(), before_document)
        self.assert_refused_unchanged(proposal)

    def test_access_change_after_dispatch_rolls_back_before_commit(self):
        proposal = self.preview()
        original = service.dispatch
        def alter_access(*args, **kwargs):
            result = original(*args, **kwargs)
            self.user_a.user_permissions.add(Permission.objects.get(content_type__app_label='operations', codename='view_document'))
            return result
        with patch('erp.service.dispatch', side_effect=alter_access):
            self.assert_refused_unchanged(proposal)


from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time
from django.db import connections
from django.test import TransactionTestCase


class AdjustmentProposalPostgresConcurrencyTests(TransactionTestCase):
    """Three bounded PG16 races; SQL observers forward real statements once.

    Run explicitly on the issued PostgreSQL test database. SQLite behavior is
    not a substitute and this class deliberately refuses that backend.
    """
    lot = AdjustmentProposalTests.lot
    payload = AdjustmentProposalTests.payload
    post = AdjustmentProposalTests.post
    preview = AdjustmentProposalTests.preview
    confirm = AdjustmentProposalTests.confirm

    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'This evidence requires PostgreSQL16')
        AdjustmentProposalTests.setUp(self)
        with connection.cursor() as cursor:
            cursor.execute('SHOW server_version')
            self.pg_version = str(cursor.fetchone()[0])
        self.assertEqual(self.pg_version.split('.')[0], '16')

    def race(self, kind):
        proposal_a = self.preview()
        if kind == 'replay':
            proposal_b = proposal_a
            cookie_b = deepcopy(self.a.cookies)
        else:
            proposal_b = self.preview(self.b, self.lot_b if kind == 'independent' else self.lot_a, '-2')
            cookie_b = deepcopy(self.b.cookies)
        locked = threading.Event()
        attempted = threading.Event()
        release_first = threading.Event()
        backend_pids = {}
        trace = []
        trace_lock = threading.Lock()

        def worker(name, cookies, proposal):
            connections.close_all()
            conn = connections['default']
            try:
                with conn.cursor() as cursor:
                    cursor.execute('SET statement_timeout = 10000')
                    cursor.execute('SELECT pg_backend_pid(), current_database()')
                    backend_pid, database_name = cursor.fetchone()
                self.assertRegex(database_name, r'^test_bos_verify_[0-9a-f]{16}$')
                with trace_lock:backend_pids[name] = backend_pid
                saw_lock = False
                def observe(execute, sql, params, many, context):
                    nonlocal saw_lock
                    is_first_lock = (not saw_lock and sql.lower().startswith('update "operations_configuration"'))
                    if is_first_lock:
                        saw_lock = True
                        self.assertTrue(context['connection'].in_atomic_block)
                        with trace_lock:
                            trace.append({'worker': name, 'stage': 'mutex_attempt', 'time': time.monotonic()})
                        if name == 'B':attempted.set()
                    result = execute(sql, params, many, context)
                    if is_first_lock:
                        with trace_lock:
                            trace.append({'worker': name, 'stage': 'mutex_acquired', 'time': time.monotonic()})
                        if name == 'A':
                            locked.set()
                            if not release_first.wait(12):raise AssertionError('Monitor never proved the PostgreSQL mutex wait')
                    return result
                client = Client(enforce_csrf_checks=True)
                client.cookies = deepcopy(cookies)
                with conn.execute_wrapper(observe):
                    response = self.confirm(proposal, client)
                self.assertTrue(saw_lock)
                return {'worker': name, 'status': response.status_code, 'body': response.json(),
                        'backend_pid': backend_pid, 'database': database_name}
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(worker, 'A', deepcopy(self.a.cookies), proposal_a)
            self.assertTrue(locked.wait(5), 'First request did not acquire the actual ERP mutex')
            second = pool.submit(worker, 'B', cookie_b, proposal_b)
            blocked = False
            monitor_pid = None
            try:
                self.assertTrue(attempted.wait(5), 'Second request never attempted the mutex')
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    monitor_pid = cursor.fetchone()[0]
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        cursor.execute('SELECT pg_blocking_pids(%s), (SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s)',
                                       [backend_pids['B'], backend_pids['B']])
                        blockers, wait_type = cursor.fetchone()
                        if backend_pids['A'] in blockers and wait_type == 'Lock':
                            blocked = True
                            with trace_lock:
                                trace.append({'worker': 'monitor', 'stage': 'blocking_proven',
                                              'time': time.monotonic(), 'waiting_pid': backend_pids['B'],
                                              'blocking_pids': blockers, 'wait_event_type': wait_type})
                            break
                        time.sleep(0.02)
                self.assertTrue(blocked, 'PostgreSQL did not report B waiting on the lock held by A')
            finally:
                release_first.set()
            a = first.result(timeout=20)
            b = second.result(timeout=20)
        self.assertEqual(len({a['backend_pid'], b['backend_pid'], monitor_pid}), 3)
        self.assertNotEqual(a['backend_pid'], b['backend_pid'])
        self.assertEqual(a['status'], 200, a)
        self.assertEqual(b['status'], 409 if kind == 'same' else 200, b)
        stages = [(row['worker'], row['stage']) for row in trace]
        self.assertLess(stages.index(('A', 'mutex_acquired')), stages.index(('B', 'mutex_attempt')))
        self.assertLess(stages.index(('B', 'mutex_attempt')), stages.index(('monitor', 'blocking_proven')))
        self.assertLess(stages.index(('monitor', 'blocking_proven')), stages.index(('B', 'mutex_acquired')))
        self.assertEqual(Movement.objects.filter(kind='adjustment').count(), 2 if kind == 'independent' else 1)
        self.assertEqual(Event.objects.count(), 2 if kind == 'independent' else 1)
        self.lot_a.refresh_from_db(); self.lot_b.refresh_from_db()
        self.assertEqual(self.lot_a.quantity, D('9'))
        self.assertEqual(self.lot_b.quantity, D('8') if kind == 'independent' else D('10'))
        self.assertEqual(a['body']['impact'], proposal_a['impact'])
        if kind == 'independent':self.assertEqual(b['body']['impact'], proposal_b['impact'])
        if kind == 'same':self.assertIsNone(ActionProposal.objects.get(pk=proposal_b['id']).receipt)
        if kind == 'replay':self.assertEqual(a['body'], b['body'])
        print('N2_POSTGRES_CONCURRENCY ' + json.dumps({'kind': kind, 'version': self.pg_version,
              'results': [a, b], 'monitor_pid': monitor_pid, 'mutex_trace': trace}, ensure_ascii=False))

    def test_distinct_users_independent_lots_confirm_after_real_mutex_wait(self):
        self.race('independent')

    def test_distinct_users_same_lot_conflict_after_real_mutex_wait(self):
        self.race('same')

    def test_same_proposal_replay_after_real_mutex_wait_creates_one_effect(self):
        self.race('replay')
