"""BoS 4 demo company: synthetic, linked through ordinary ERP commands, no accounts seeded."""
from decimal import Decimal as D
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
from django.test import TransactionTestCase, override_settings

from branches.models import Branch
from employees.models import Employee
from operations.models import Configuration, Document, Invoice
from operations.private_storage import verified_document_bytes
from operations.service import as_of
from tasks.models import Task
from .balances import invoice_settlement
from .models import Item, Location, Lot, SalesOrder, Purchase, Production, Movement, StockTransfer, OperatorEntry, DocumentLink
from .service import dispatch


@override_settings(BOS_DATA_MODE='demo')
class Bos4DemoTests(TransactionTestCase):
    def setUp(self):
        self.folder = TemporaryDirectory(prefix='bos4-demo-test-')
        self.addCleanup(self.folder.cleanup)
        self.override = override_settings(MEDIA_ROOT=Path(self.folder.name) / 'media')
        self.override.enable()
        self.addCleanup(self.override.disable)

    def command(self):
        output = StringIO()
        call_command('seed_bos4_demo', stdout=output)
        return json.loads(output.getvalue())

    def test_company_is_linked_branches_in_hryvnia_without_accounts(self):
        receipt = self.command()
        self.assertTrue(receipt['created'])
        self.assertEqual(receipt['cases'], ['Комплектуючі для партії меблів',
            'Відвантаження лише допущеної партії', 'Рахунок, оплата й нагадування'])
        self.assertEqual(Branch.objects.count(), 4)
        self.assertEqual(Branch.objects.filter(parent__code='KM-KYI').count(), 3)
        # Only suppliers' own points are outside the company's branches.
        self.assertEqual(set(Location.objects.filter(branch__isnull=True).values_list('kind', flat=True)), {'supplier'})
        self.assertEqual(Location.objects.filter(kind='supplier', lat__isnull=False).count(), 3)
        self.assertEqual(Item.objects.filter(kind='product').count(), 8)
        self.assertEqual(Item.objects.filter(kind='material').count(), 16)
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(Employee.objects.filter(user__isnull=False).exists())
        for model in (Item, Lot, SalesOrder, Purchase, Production, Invoice, StockTransfer):
            self.assertEqual(set(model.objects.values_list('currency', flat=True)), {'UAH'})
        self.assertEqual(str(as_of()), '2026-10-05')
        for doc in Document.objects.all():
            self.assertTrue(doc.text.startswith('ДЕМО-ДАНІ.'))
            self.assertEqual(verified_document_bytes(doc), doc.text.encode())
        # Every lot balance is the sum of its movements; reservations never exceed stock.
        for lot in Lot.objects.all():
            self.assertEqual(lot.quantity, lot.movements.aggregate(n=Sum('quantity'))['n'])
            self.assertLessEqual(lot.reservations.aggregate(n=Sum('quantity'))['n'] or D(0), lot.quantity)
        self.assertEqual(StockTransfer.objects.filter(status='in_transit').count(), 1)
        cases = Configuration.objects.get(key='demo_cases').value['cases']
        self.assertEqual([c['title'] for c in cases], receipt['cases'])

    def test_case_components_completes_a_produced_and_shipped_batch(self):
        self.command()
        order = SalesOrder.objects.get(code='ZM-0141')
        self.assertEqual(sum(l.quantity * l.price for l in order.lines.all()), D('1922800'))
        po = Purchase.objects.get(code='ZK-0311')
        self.assertEqual((po.quantity, po.received, po.status), (D(300), D(300), 'received'))
        self.assertEqual(list(Movement.objects.filter(purchase=po, kind='receipt').order_by('id')
                              .values_list('quantity', flat=True)), [D(200), D(100)])
        job = Production.objects.get(code='VZ-0141-1')
        self.assertEqual((job.quantity, job.produced, job.status), (D(120), D(120), 'done'))
        self.assertEqual(list(OperatorEntry.objects.filter(production=job).order_by('id')
                              .values_list('operation', 'result')), [(step['name'], 'done') for step in job.routing])
        for material in job.bom:
            consumed = Movement.objects.filter(production=job, kind='consume', lot__item_id=material['item_id'])
            self.assertEqual(-consumed.aggregate(n=Sum('quantity'))['n'], D(material['quantity']) * D(120))
        self.assertEqual(job.reservations.aggregate(n=Sum('quantity'))['n'], D(0))
        produced = Lot.objects.get(code='KM-L-SM-1800-VZ0141')
        ready = Lot.objects.get(code='KM-T-SM-1800-VZ0141')
        passport = Document.objects.get(code='KM-PASS-VZ-0141-1')
        self.assertEqual((produced.quality, ready.quality), ('approved', 'approved'))
        self.assertEqual(produced.documents, {'passport': passport.pk})
        self.assertEqual(ready.documents, produced.documents)
        self.assertEqual(ready.location_id, order.fulfillment_location_id)
        self.assertEqual((produced.quantity, ready.quantity), (D(0), D(0)))
        line = order.lines.get(item__code='SM-1800')
        self.assertEqual((line.quantity, line.shipped), (D(120), D(120)))
        shipment = Movement.objects.get(line=line, kind='shipment')
        self.assertEqual((shipment.lot_id, shipment.quantity, shipment.reference), (ready.pk, D(-120), 'VN-0141-1'))
        self.assertEqual(sum(l.quantity - l.shipped for l in order.lines.all()), D(134))
        self.assertEqual(Production.objects.get(code='VZ-0141-2').status, 'planned')
        self.assertEqual(Lot.objects.get(code='KM-L-MA-7075-ZK0311-REST').quantity, D(80))
        self.assertEqual(set(DocumentLink.objects.filter(order=order).values_list('document__code', flat=True)),
                         {'KM-ZM-0141', 'KM-VN-0141-1'})
        case = Configuration.objects.get(key='demo_cases').value['cases'][0]
        self.assertEqual(case['result'], {'label': 'Виготовлено й відвантажено', 'value': '120 стелажів СМ-1800'})
        self.assertEqual(case['steps'][-1]['shipment'], shipment.reference)
        for step in case['steps']:
            self.assertTrue(Document.objects.filter(code=step['document']).exists())
        self.assertTrue(Purchase.objects.filter(code='ZK-0309', due_date__lt=as_of(), received=0).exists())

    def test_network_purchases_start_at_the_supplier_point(self):
        from types import SimpleNamespace
        from django.contrib.auth.models import Group
        from boss_project.policy import Policy
        from .network import build
        self.command()
        reader = get_user_model().objects.create_user(username='synthetic-network-reader')
        reader.groups.add(Group.objects.get_or_create(name='ceo')[0])
        rows = build(Policy(SimpleNamespace(user=reader, session={})), {'currency': 'UAH'})['rows']
        metal = Location.objects.get(code='KM-SUP-METAL')
        po = next(r for r in rows['purchases'] if r['code'] == 'ZK-0311')
        self.assertEqual(po['origin_location_id'], metal.pk)
        point = next(p for p in rows['points'] if p['id'] == metal.pk)
        self.assertEqual(point['branch_name'], metal.supplier.name)

    def test_case_quality_ships_only_approved_batch(self):
        self.command()
        line = SalesOrder.objects.get(code='ZM-0144').lines.get(item__code='SHM-2')
        self.assertEqual((line.quantity, line.shipped), (D(50), D(40)))
        blocked = Lot.objects.get(code='KM-L-SHM-2-0918')
        self.assertEqual((blocked.quality, blocked.quantity), ('blocked', D(25)))
        with self.assertRaises(ValueError):
            dispatch({'action': 'erp_reserve', 'lot_id': blocked.pk, 'quantity': '10', 'line_id': line.pk}, 'ceo')
        self.assertFalse(Movement.objects.filter(lot=blocked, kind='shipment').exists())
        self.assertEqual(Invoice.objects.get(code='RF-0144').amount, D('777700'))

    def test_case_payment_leaves_reminder_for_remaining_debt(self):
        self.command()
        invoice = Invoice.objects.get(code='RF-0137')
        self.assertEqual((invoice.amount, invoice.paid), (D('420000'), D('252000')))
        self.assertEqual(invoice_settlement(invoice)['receivable'], D('168000'))
        task = Task.objects.get(title__contains='RF-0137')
        self.assertEqual((task.assignee, task.priority, task.sales_order.code), ('Дмитро Савченко', 'high', 'ZM-0137'))
        school = Invoice.objects.get(code='RF-0139')
        self.assertEqual(invoice_settlement(school)['receivable'], D('0'))

    def test_repeat_is_receipt_and_non_empty_database_is_refused(self):
        first = self.command()
        lots = Lot.objects.count()
        again = self.command()
        self.assertFalse(again['created'])
        self.assertEqual(again['company'], first['company'])
        self.assertEqual(Lot.objects.count(), lots)

    def test_refuses_outside_demo_mode_and_on_foreign_data(self):
        with override_settings(BOS_DATA_MODE='production'):
            with self.assertRaises(CommandError):
                self.command()
        Branch.objects.create(code='REAL', name='Наявна філія')
        with self.assertRaises(CommandError):
            self.command()
        self.assertFalse(Configuration.objects.filter(key='bos4_demo_seed').exists())

    def test_refuses_database_with_connected_sources(self):
        from connectors.models import Connector
        owner = get_user_model().objects.create(username='synthetic-owner')
        Connector.objects.create(kind='csv', name='Наявні замовлення', dataset='orders', created_by=owner)
        before = (Configuration.objects.count(), Item.objects.count(), Branch.objects.count())
        with self.assertRaisesRegex(CommandError, 'підключені джерела'):
            self.command()
        self.assertEqual((Configuration.objects.count(), Item.objects.count(), Branch.objects.count()), before)
        self.assertEqual(Connector.objects.count(), 1)
