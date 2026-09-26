"""Targeted synthetic seed checks; no production DB, no network, no accounts seeded."""
from decimal import Decimal as D
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
import json

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
from django.test import TransactionTestCase, override_settings

from branches.models import Branch
from employees.models import Employee
from finance.models import Counterparty
from operations.models import Configuration, Document, Invoice, ProcurementRequest, SupplierQuote
from operations.private_storage import verified_document_bytes, private_document_storage
from operations.service import as_of
from boss_project.policy import Policy
from .balances import invoice_settlement
from .models import (
    Item, Location, Lot, SalesOrder, SalesLine, Purchase, Production,
    Movement, Reservation, InvoiceLink, OperatorEntry, Event, StockTransfer, PaymentRetention,
)
from .network_demo import seed_network_demo, MARKER
from .service import dispatch


@override_settings(BOS_DATA_MODE='demo')
class NetworkDemoTests(TransactionTestCase):
    def setUp(self):
        self.folder = TemporaryDirectory(prefix='bos-network-demo-test-')
        self.addCleanup(self.folder.cleanup)
        self.media = Path(self.folder.name) / 'media'
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def snapshot(self):
        return {m._meta.label: list(m._base_manager.order_by('pk').values()) for m in apps.get_models()
            if m._meta.app_label in {'erp', 'operations', 'finance', 'tasks', 'employees', 'branches'}}

    def command(self, dataset='workday'):
        output = StringIO()
        call_command('seed_network_demo', dataset=dataset, stdout=output)
        return json.loads(output.getvalue())

    def assert_stock_trace(self):
        for lot in Lot.objects.all():
            self.assertEqual(lot.quantity, lot.movements.aggregate(n=Sum('quantity'))['n'])
            self.assertLessEqual(lot.reservations.aggregate(n=Sum('quantity'))['n'] or D(0), lot.quantity)
        opening = Movement.objects.filter(kind='opening').aggregate(n=Sum('cost'))['n']
        shipped = Movement.objects.filter(kind='shipment').aggregate(n=Sum('cost'))['n']
        received = Movement.objects.filter(kind='receipt').aggregate(n=Sum('cost'))['n'] or D(0)
        physical = sum((lot.quantity * lot.unit_cost for lot in Lot.objects.all()), D(0))
        transit = sum((row.total_cost for row in StockTransfer.objects.filter(status='in_transit')), D(0))
        self.assertEqual(opening + received - shipped, physical + transit)

    def test_workday_is_linked_erp_ua_hryvnia_and_reversible_collection_is_real(self):
        user = get_user_model().objects.create(username='existing-technical-account', is_active=False)
        user.set_unusable_password()
        user.save(update_fields=['password'])
        user_before = list(get_user_model().objects.values())
        receipt = self.command()
        self.assertTrue(receipt['created'])
        expected = {'branch': 7, 'location': 14, 'employee': 14, 'item': 5, 'lot': 84,
            'salesorder': 33, 'salesline': 33, 'purchase': 11, 'production': 2,
            'invoice': 21, 'invoicelink': 21, 'stocktransfer': 7, 'paymentretention': 7, 'document': 28, 'procurementrequest': 13, 'supplierquote': 12}
        for name, count in expected.items():
            self.assertEqual(receipt['counts'][name], count, name)
        self.assertEqual(list(get_user_model().objects.values()), user_before)
        self.assertFalse(Employee.objects.filter(user__isnull=False).exists())
        self.assertEqual(Location.objects.filter(branch__isnull=True).count(), 0)
        self.assertEqual(Purchase.objects.filter(request__isnull=False, quote__isnull=False).count(), 11)
        self.assertEqual(set(ProcurementRequest.objects.values_list('currency', flat=True)), {'UAH'})
        self.assertEqual({q.terms['currency'] for q in SupplierQuote.objects.all()}, {'UAH'})
        self.assertEqual(Purchase.objects.get(code='NET-PO-KYI').received, D(8))
        self.assertEqual(Purchase.objects.get(code='NET-PO-LVI').received, D(22))
        for purchase in Purchase.objects.all():
            self.assertEqual(purchase.approval_snapshot['source'], 'quote')
            self.assertEqual(purchase.approval_snapshot['request_id'], purchase.request_id)
            self.assertEqual(purchase.approval_snapshot['quote_id'], purchase.quote_id)
        self.assertEqual(Location.objects.filter(kind='production').count(), 7)
        self.assertEqual(StockTransfer.objects.filter(status='in_transit').count(), 2)
        self.assertEqual(Purchase.objects.exclude(origin_country='UA').count(), 4)
        self.assertEqual(SalesOrder.objects.exclude(destination_country='').count(), 3)
        for model in (Item, Lot, SalesOrder, Purchase, Production, Invoice, StockTransfer, PaymentRetention):
            self.assertEqual(set(model.objects.values_list('currency', flat=True)), {'UAH'})
        self.assertEqual(Configuration.objects.get(key='cash').value['currency'], 'UAH')
        for doc in Document.objects.all():
            self.assertTrue(doc.original_file.name)
            self.assertEqual(bytes(doc.content), b'')
            self.assertEqual(verified_document_bytes(doc), doc.text.encode())
        self.assert_stock_trace()
        reader = get_user_model().objects.create_user(username='synthetic-workflow-reader')
        reader.groups.add(Group.objects.get_or_create(name='ceo')[0])
        from .network_workflow import build
        flow = build(Policy(SimpleNamespace(user=reader, session={})), {'currency': 'UAH'})['workflow']
        self.assertEqual(flow['metrics']['request_count'], 13)
        self.assertEqual({r['stage'] for r in flow['requests']}, {'sourcing', 'quoted', 'ordered', 'receiving', 'received'})
        self.assertTrue(flow['synthetic'])
        self.assertFalse(flow['comparison']['available'])
        self.assertIsNone(flow['comparison']['change_percent'])
        self.assertIn('Синтетичний', flow['comparison']['reason'])
        retained = PaymentRetention.objects.order_by('pk').first()
        invoice = retained.invoice
        settlement = invoice_settlement(invoice)
        before = settlement['receivable']
        available = before - retained.amount
        with self.assertRaises(ValueError):
            dispatch({'action': 'erp_payment', 'invoice_id': invoice.pk,
                'amount': str(available + D('.01')), 'reference': 'NET-TEST-EXCESS'}, 'ceo')
        dispatch({'action': 'erp_payment', 'invoice_id': invoice.pk,
            'amount': str(available), 'reference': 'NET-TEST-COLLECTIBLE'}, 'ceo')
        invoice.refresh_from_db()
        self.assertEqual(invoice_settlement(invoice)['receivable'], retained.amount)
        dispatch({'action': 'erp_release_payment', 'retention_id': retained.pk,
            'reason': 'Навчальне приймання комплекту документів завершено'}, 'ceo')
        invoice.refresh_from_db()
        self.assertEqual(invoice_settlement(invoice)['receivable'], retained.amount)
        dispatch({'action': 'erp_payment', 'invoice_id': invoice.pk,
            'amount': str(retained.amount), 'reference': 'NET-TEST-RELEASED'}, 'ceo')
        invoice.refresh_from_db()
        self.assertEqual(invoice_settlement(invoice)['receivable'], D('0'))

    def test_disruption_contains_overdue_supply_and_blocked_production(self):
        receipt = self.command('disruption')
        self.assertEqual(receipt['counts']['lot'], 83)
        self.assertEqual(Purchase.objects.filter(due_date__lt=as_of()).count(), 11)
        self.assertEqual(StockTransfer.objects.filter(status='in_transit').count(), 3)
        self.assertEqual(Lot.objects.filter(quality='blocked').count(), 8)
        job = Production.objects.get(code='NET-MO-DNI')
        self.assertEqual(job.status, 'planned')
        with self.assertRaises(ValueError):
            dispatch({'action': 'erp_start', 'production_id': job.pk}, 'ceo')
        self.assertEqual(OperatorEntry.objects.count(), 0)
        self.assert_stock_trace()

    def test_collections_profile_and_rerun_preserve_later_work(self):
        receipt = self.command('collections')
        self.assertEqual(Invoice.objects.filter(due_date__lt=as_of()).count(), 21)
        self.assertEqual(Event.objects.filter(action='erp_payment').count(), 14)
        invoice = Invoice.objects.get(code='NET-INV-KYI-2')
        dispatch({'action': 'erp_payment', 'invoice_id': invoice.pk,
            'amount': '1.00', 'reference': 'NET-AFTER-SEED'}, 'ceo')
        before = self.snapshot()
        files = {str(p): p.read_bytes() for p in self.media.rglob('*') if p.is_file()}
        again = self.command('collections')
        self.assertFalse(again['created'])
        self.assertEqual(again['counts'], receipt['counts'])  # Receipt counts are the initial seed counts.
        self.assertEqual(before, self.snapshot())
        self.assertEqual(files, {str(p): p.read_bytes() for p in self.media.rglob('*') if p.is_file()})
        with self.assertRaises(CommandError):
            self.command('workday')
        self.assertEqual(before, self.snapshot())

    def test_working_mode_and_foreign_business_rows_are_never_mixed(self):
        with override_settings(BOS_DATA_MODE='working'), self.assertNumQueries(0):
            with self.assertRaises(CommandError):
                seed_network_demo()
        counterparty = Counterparty.objects.create(name='Existing synthetic business row', type='customer')
        before = self.snapshot()
        with self.assertRaises(CommandError):
            self.command()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(Counterparty.objects.get(pk=counterparty.pk).name, 'Existing synthetic business row')
        self.assertFalse(self.media.exists())

    def test_mid_seed_failure_rolls_back_rows_and_owned_files(self):
        before = self.snapshot()
        def fail_at_invoice(payload, *args, **kwargs):
            if payload['action'] == 'erp_invoice':
                raise ValueError('Injected synthetic failure before first invoice')
            return dispatch(payload, *args, **kwargs)
        with patch('erp.network_demo.dispatch', side_effect=fail_at_invoice):
            with self.assertRaises(CommandError):
                self.command()
        self.assertEqual(before, self.snapshot())
        self.assertFalse(any(p.is_file() for p in self.media.rglob('*')))
        self.assertFalse(Configuration.objects.filter(key=MARKER).exists())

    def test_unknown_profile_and_unknown_existing_receipt_refuse_without_changes(self):
        with self.assertRaises(CommandError):
            seed_network_demo('other')
        Configuration.objects.create(key=MARKER, value={'synthetic': True, 'version': 'unknown', 'dataset': 'workday'})
        before = self.snapshot()
        with self.assertRaises(CommandError):
            seed_network_demo()
        self.assertEqual(before, self.snapshot())
