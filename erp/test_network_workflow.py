"""Focused read-scope, real-time and migration regressions; synthetic data only."""
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
import json
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from boss_project.policy import Policy
from branches.models import Branch
from employees.models import Employee
from finance.models import Counterparty
from operations.models import Document, ProcurementRequest, SupplierQuote
from .models import Item, Location, Lot, Movement, Purchase
from .network_workflow import build, _comparison


def guard():
    assert os.environ.get('DJANGO_SETTINGS_MODULE') == 'verification_settings'
    assert connection.vendor != 'sqlite' or Path(str(connection.settings_dict['NAME'])).name.startswith('check_')


@override_settings(BOS_DATA_MODE='working', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class NetworkWorkflowTests(TestCase):
    def setUp(self):
        guard()
        self.owner = Employee.objects.create(full_name='FLOW synthetic owner')
        self.supplier = Counterparty.objects.create(name='FLOW synthetic supplier', type='supplier')
        self.branch = Branch.objects.create(code='FLOW-KYI', name='FLOW Київ')
        self.location = Location.objects.create(code='FLOW-WH', name='FLOW synthetic warehouse', branch=self.branch)
        self.now = timezone.now()
        self.spec = self.document('FLOW-SPEC')
        self.item = Item.objects.create(code='FLOW-ITEM', name='FLOW synthetic item', document=self.spec, currency='UAH', required_documents=['CoC'])
        self.request = self.request_row('FLOW-R', self.spec, self.item.code)
        self.quote_doc = self.document('FLOW-QDOC')
        self.quote = SupplierQuote.objects.create(code='FLOW-Q', request=self.request, supplier=self.supplier,
                                                 document=self.quote_doc, terms={'unit_price':'7.00','currency':'UAH'},
                                                 created_at=self.now-timedelta(hours=48))
        self.purchase = self.purchase_row('FLOW-PO', self.request, self.item, self.quote)

    def document(self, code, access='operational'):
        return Document.objects.create(code=code, revision='A', title=code, status='approved', checksum='a'*64, access_level=access)

    def request_row(self, code, doc, part, currency='UAH'):
        return ProcurementRequest.objects.create(code=code, part=part, revision='A', quantity=10,
            currency=currency, required_by=self.now.date()+timedelta(days=1), owner=self.owner,
            document=doc, created_at=self.now-timedelta(hours=72))

    def purchase_row(self, code, request, item, quote=None):
        return Purchase.objects.create(code=code, request=request, item=item, quote=quote, supplier=self.supplier,
            quantity=10, price=7, currency=request.currency, due_date=request.required_by, original_due=request.required_by,
            revision='A', destination=self.location, created_at=self.now-timedelta(hours=24))

    def policy(self, role, download=False, view=True):
        user = get_user_model().objects.create_user(username=f'flow-{role}-{get_user_model().objects.count()}')
        user.groups.add(Group.objects.get_or_create(name=role)[0])
        for name in (['view_document'] if view else []) + (['download_document'] if download else []):
            user.user_permissions.add(Permission.objects.get(content_type__app_label='operations', codename=name))
        return Policy(SimpleNamespace(user=user, session={}))

    def receive(self, quantity, when):
        lot = Lot.objects.create(code=f'FLOW-LOT-{Lot.objects.count()}', item=self.item, location=self.location,
                                 revision='A', quantity=quantity, currency='UAH', documents={})
        movement = Movement.objects.create(lot=lot, purchase=self.purchase, kind='receipt', reference=self.purchase.code, quantity=quantity)
        Movement.objects.filter(pk=movement.pk).update(created_at=when)
        self.purchase.received += Decimal(quantity)
        self.purchase.save(update_fields=['received'])
        return movement

    def test_observed_movement_and_unknown_history(self):
        self.receive('4', self.now-timedelta(hours=12))
        current = build(self.policy('ceo'), {'currency':'UAH'})['workflow']
        self.assertEqual(current['requests'][0]['stage'], 'receiving')
        self.assertIsNone(current['requests'][0]['processing_hours'])
        self.assertEqual(current['metrics']['median_purchase_to_first_receipt_hours'], 12)
        self.receive('6', self.now-timedelta(hours=6))
        current = build(self.policy('ceo'), {'currency':'UAH'})['workflow']
        self.assertEqual(current['requests'][0]['stage'], 'received')
        self.assertEqual(current['requests'][0]['processing_hours'], 66)
        self.assertEqual(current['metrics']['timed_request_count'], 1)
        self.assertFalse(current['comparison']['available'])
        self.assertIsNone(current['comparison']['change_percent'])
        SupplierQuote.objects.filter(pk=self.quote.pk).update(created_at=self.now-timedelta(hours=12))
        contradictory = build(self.policy('ceo'))['workflow']['requests'][0]
        self.assertIsNone(contradictory['processing_hours'])
        ProcurementRequest.objects.filter(pk=self.request.pk).update(created_at=None)
        current = build(self.policy('ceo'))['workflow']['requests'][0]
        self.assertIsNone(current['age_days'])
        self.assertIsNone(current['processing_hours'])

    def test_hidden_entities_do_not_change_visible_counts_or_document_sets(self):
        manager = self.policy('manager')
        baseline = build(manager, {'currency':'UAH'})
        hidden_doc = self.document('FLOW-HIDDEN', 'ceo')
        hidden_item = Item.objects.create(code='FLOW-HIDDEN-I', name='Secret item', document=hidden_doc)
        hidden_quote = SupplierQuote.objects.create(code='FLOW-HIDDEN-Q', request=self.request, supplier=self.supplier,
                                                   document=hidden_doc, terms={'price':'987654321'})
        self.purchase_row('FLOW-HIDDEN-PO', self.request, hidden_item, hidden_quote)
        # Re-read policy: demonstrate current permissions, not a stale cache.
        result = build(Policy(manager.request), {'currency':'UAH'})
        self.assertEqual(result['documents'], baseline['documents'])
        self.assertEqual(result['workflow']['metrics'], baseline['workflow']['metrics'])
        self.assertEqual(result['workflow']['requests'][0]['quote_count'], 1)
        self.assertEqual(result['workflow']['requests'][0]['purchase_count'], 1)
        self.assertNotIn('FLOW-HIDDEN', json.dumps(result))
        self.assertNotIn('987654321', json.dumps(result))
        self.assertFalse(any(d['can_download'] for d in result['documents']))
        self.assertNotIn('statement_unbound', [r['id'] for r in result['workflow']['reconciliations']])

    def test_no_document_permission_means_no_requests_or_documents(self):
        result = build(self.policy('observer', view=False))
        self.assertEqual(result['documents'], [])
        self.assertEqual(result['workflow']['requests'], [])
        self.assertEqual(result['workflow']['metrics']['request_count'], 0)

    def test_location_currency_filters_and_download_capability(self):
        ceo = self.policy('ceo', download=True)
        result = build(ceo, {'branch_id':str(self.branch.pk), 'location_id':str(self.location.pk), 'currency':'UAH'})
        self.assertEqual(result['workflow']['metrics']['request_count'], 1)
        self.assertTrue(all(d['can_download'] for d in result['documents']))
        self.assertTrue(all(d['groups'] for d in result['documents']))
        self.assertEqual(build(ceo, {'currency':'EUR'})['workflow']['requests'], [])
        other = Location.objects.create(code='FLOW-OTHER', name='FLOW Other')
        self.assertEqual(build(ceo, {'location_id':other.pk})['documents'], [])
        self.assertEqual(build(ceo, {'branch_id':'unassigned'})['workflow']['requests'], [])
        self.assertNotIn('statement_unbound', [r['id'] for r in result['workflow']['reconciliations']])
        actions = {r['id']: r['next_action'] for r in build(ceo)['workflow']['reconciliations']}
        self.assertEqual((actions['document_review']['section'], actions['document_review']['sub']), ('organizer', 'documents'))
        self.assertEqual((actions['statement_unbound']['section'], actions['statement_unbound']['sub']), ('finance', 'bank'))

    def test_equal_windows_require_samples_and_report_observed_reduction_only(self):
        before = [(self.now-timedelta(days=35+i), 72.0) for i in range(3)]
        after = [(self.now-timedelta(days=7+i), 36.0) for i in range(3)]
        result = _comparison(before+after, self.now)
        self.assertTrue(result['available'])
        self.assertEqual(result['change_percent'], 50.0)
        self.assertEqual(result['baseline']['sample_size'], 3)
        self.assertIn('не доказ', result['reason'])
        self.assertFalse(_comparison(before+after[:2], self.now)['available'])
        self.assertFalse(_comparison([(at,0) for at,_ in before]+after, self.now)['available'])


class NetworkTimingMigrationTests(TransactionTestCase):
    def test_historical_rows_remain_null_and_new_rows_get_actual_creation_time(self):
        guard()
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [('erp','0006_network_operations'), ('operations','0008_procurement_currency_default')]
        try:
            executor.migrate(previous)
            apps = executor.loader.project_state(previous).apps
            owner = apps.get_model('employees','Employee').objects.create(full_name='MIG synthetic owner')
            supplier = apps.get_model('finance','Counterparty').objects.create(name='MIG synthetic supplier', type='supplier')
            doc = apps.get_model('operations','Document').objects.create(code='MIG-DOC', revision='A', title='MIG synthetic', checksum='b'*64)
            request = apps.get_model('operations','ProcurementRequest').objects.create(code='MIG-R', part='MIG-I', revision='A', quantity=1, currency='UAH', required_by='2026-10-01', owner=owner, document=doc)
            quote = apps.get_model('operations','SupplierQuote').objects.create(code='MIG-Q', request=request, supplier=supplier, document=doc)
            item = apps.get_model('erp','Item').objects.create(code='MIG-I', name='MIG synthetic')
            purchase = apps.get_model('erp','Purchase').objects.create(code='MIG-PO', item=item, supplier=supplier, quantity=1, price=1, currency='UAH', due_date='2026-10-01', original_due='2026-10-01', revision='A', request=request, quote=quote)
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            self.assertIsNone(ProcurementRequest.objects.get(pk=request.pk).created_at)
            self.assertIsNone(SupplierQuote.objects.get(pk=quote.pk).created_at)
            self.assertIsNone(Purchase.objects.get(pk=purchase.pk).created_at)
            start = timezone.now()
            current = ProcurementRequest.objects.create(code='MIG-NEW', part='MIG-I', revision='A', quantity=1, required_by='2026-10-01', owner_id=owner.pk, document_id=doc.pk)
            self.assertGreaterEqual(current.created_at, start)
            self.assertLessEqual(current.created_at, timezone.now())
        finally:
            MigrationExecutor(connection).migrate(latest)
