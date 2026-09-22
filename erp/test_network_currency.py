"""NETWORK-PLAN-CURRENCY: advice-to-writer regressions on synthetic UAH jobs."""
from decimal import Decimal as D

from django.test import Client, TestCase, override_settings

from employees.models import Employee
from finance.models import Counterparty
from operations.models import Configuration
from scripts.check_support import login_test_client
from . import service
from .models import Item, Location, Lot, Production, Purchase, Reservation, SalesLine, SalesOrder


@override_settings(BOS_DATA_MODE='working', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class NetworkProductionCurrencyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = Employee.objects.create(full_name='Synthetic currency operator')
        cls.customer = Counterparty.objects.create(name='Synthetic currency buyer', type='customer')
        cls.supplier = Counterparty.objects.create(name='Synthetic currency supplier', type='supplier')
        cls.workshop = Location.objects.create(code='CUR-WORK', name='Synthetic workshop', kind='production')
        cls.warehouse = Location.objects.create(code='CUR-WH', name='Synthetic warehouse', kind='warehouse')
        cls.material = Item.objects.create(code='CUR-MAT', name='Synthetic material', kind='material', currency='UAH')
        cls.product = Item.objects.create(code='CUR-PROD', name='Synthetic product', method='make', currency='UAH',
            bom=[{'item_id': cls.material.pk, 'quantity': '2'}])
        cls.order = SalesOrder.objects.create(code='CUR-SO', customer=cls.customer, owner=cls.owner,
            due_date='2026-10-01', currency='UAH', status='confirmed', fulfillment_location=cls.warehouse)
        cls.line = SalesLine.objects.create(order=cls.order, item=cls.product, revision='A', quantity=D('2'), price=D('100'))
        cls.job = Production.objects.create(code='CUR-JOB', item=cls.product, line=cls.line, quantity=D('2'),
            revision='A', bom=cls.product.bom, location=cls.workshop, owner=cls.owner, due_date='2026-10-01', currency='UAH')
        Configuration.objects.get_or_create(key='erp_write', defaults={'value': {'revision': 0}})

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        login_test_client(self.client)

    def lot(self, code, currency='UAH', *, location=None, quality='approved', quantity='4'):
        return Lot.objects.create(code=code, item=self.material, location=location or self.workshop,
            revision='A', quantity=D(quantity), unit_cost=D('3.25'), currency=currency, quality=quality)

    def purchase(self, code, currency='UAH', *, destination=None):
        return Purchase.objects.create(code=code, item=self.material, supplier=self.supplier,
            quantity=D('4'), price=D('3.25'), currency=currency, due_date='2026-10-01', original_due='2026-10-01',
            revision='A', production=self.job, destination=destination)

    def advice(self):
        before = service.fingerprint()
        response = self.client.get(f'/api/erp/orders/{self.order.pk}/next/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(before, service.fingerprint(), 'Suggestion must not mutate business history')
        return response.json()

    def execute(self, payload):
        self.assertIsNotNone(payload)
        before = service.fingerprint()
        kwargs = {'content_type': 'application/json', 'HTTP_X_CSRFTOKEN': self.client.cookies['csrftoken'].value}
        response = self.client.post('/api/erp/preview/', payload, **kwargs)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(before, service.fingerprint(), 'Preview must not write business rows')
        response = self.client.post('/api/operations/confirm/', {'proposal_id': response.json()['id'], 'confirmed': True}, **kwargs)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_local_compatible_reserve_start_finish_keeps_foreign_stock_unchanged(self):
        foreign = self.lot('CUR-EUR-FIRST', 'EUR')
        compatible = self.lot('CUR-UAH-SECOND')
        payload = self.advice()['payload']
        self.assertEqual((payload['action'], payload['lot_id']), ('erp_reserve', compatible.pk))
        self.execute(payload)
        payload = self.advice()['payload']; self.assertEqual(payload['action'], 'erp_start'); self.execute(payload)
        payload = self.advice()['payload']; self.assertEqual(payload['action'], 'erp_finish'); receipt = self.execute(payload)
        result = Lot.objects.get(pk=receipt['lot_id'])
        self.assertEqual((result.currency, result.location_id, result.quantity), ('UAH', self.warehouse.pk, D('2')))
        foreign.refresh_from_db(); compatible.refresh_from_db()
        self.assertEqual((foreign.currency, foreign.quantity, compatible.quantity), ('EUR', D('4'), D('0')))

    def test_quality_suggestion_ignores_foreign_pending_material(self):
        self.lot('CUR-EUR-PENDING', 'EUR', quality='pending')
        compatible = self.lot('CUR-UAH-PENDING', quality='pending')
        payload = self.advice()['payload']
        self.assertEqual((payload['action'], payload['lot_id']), ('erp_quality', compatible.pk))
        self.execute(payload)
        self.assertEqual(self.advice()['payload']['lot_id'], compatible.pk)

    def test_transfer_suggestion_uses_compatible_currency_and_job_location(self):
        foreign = self.lot('CUR-EUR-OFFSITE', 'EUR', location=self.warehouse)
        compatible = self.lot('CUR-UAH-OFFSITE', location=self.warehouse)
        payload = self.advice()['payload']
        self.assertEqual((payload['action'], payload['lot_id'], payload['location_id']),
                         ('erp_transfer', compatible.pk, self.workshop.pk))
        receipt = self.execute(payload)
        transferred = Lot.objects.get(pk=receipt['lot_id'])
        self.assertEqual((transferred.currency, transferred.location_id), ('UAH', self.workshop.pk))
        self.execute(self.advice()['payload'])
        foreign.refresh_from_db(); self.assertEqual(foreign.quantity, D('4'))

    def test_foreign_stock_alone_does_not_cover_uah_material_requirement(self):
        self.lot('CUR-ONLY-EUR', 'EUR')
        row = self.advice()
        self.assertIsNone(row['payload'])
        self.assertIn('UAH', row['why'])

    def test_foreign_positive_reservation_requires_reconciliation_without_start(self):
        foreign = self.lot('CUR-EUR-HELD', 'EUR')
        held = Reservation.objects.create(production=self.job, lot=foreign, quantity=D('4'))
        self.lot('CUR-UAH-FREE')
        row = self.advice()
        self.assertIsNone(row['payload'])
        self.assertIn('валют', row['why'].lower())
        held.refresh_from_db(); self.assertEqual(held.quantity, D('4'))

    def test_wrong_location_reservation_does_not_start_production(self):
        wrong = self.lot('CUR-WRONG-POINT', location=self.warehouse)
        Reservation.objects.create(production=self.job, lot=wrong, quantity=D('4'))
        self.assertIsNone(self.advice()['payload'])
        self.job.refresh_from_db(); self.assertEqual(self.job.status, 'planned')

    def test_zero_foreign_reservation_explains_legacy_writer_conflict_before_finish(self):
        foreign = self.lot('CUR-EUR-ZERO', 'EUR')
        Reservation.objects.create(production=self.job, lot=foreign, quantity=D('0'))
        compatible = self.lot('CUR-UAH-HELD')
        Reservation.objects.create(production=self.job, lot=compatible, quantity=D('4'))
        self.job.status = 'running'; self.job.save(update_fields=['status'])
        row = self.advice()
        self.assertIsNone(row['payload'])
        self.assertIn('валют', row['why'].lower())

    def test_receive_selects_compatible_purchase_and_respects_explicit_destination(self):
        foreign = self.purchase('CUR-PO-EUR', 'EUR')
        compatible = self.purchase('CUR-PO-UAH', destination=self.warehouse)
        payload = self.advice()['payload']
        self.assertEqual((payload['action'], payload['purchase_id'], payload['location_id']),
                         ('erp_receive', compatible.pk, self.warehouse.pk))
        receipt = self.execute(payload)
        received = Lot.objects.get(pk=receipt['lot_id'])
        self.assertEqual((received.currency, received.location_id), ('UAH', self.warehouse.pk))
        foreign.refresh_from_db(); self.assertEqual(foreign.received, D('0'))

    def test_foreign_purchase_alone_does_not_cover_uah_requirement(self):
        self.purchase('CUR-PO-ONLY-EUR', 'EUR')
        row = self.advice()
        self.assertIsNone(row['payload'])
        self.assertIn('UAH', row['why'])

    def test_foreign_linked_job_does_not_progress_as_uah_sales_supply(self):
        self.job.currency = 'EUR'; self.job.save(update_fields=['currency'])
        self.lot('CUR-FOR-EUR-JOB', 'EUR')
        row = self.advice()
        self.assertIsNone(row['payload'])
        self.assertIn('валют', row['why'].lower())
        self.job.refresh_from_db(); self.assertEqual(self.job.currency, 'EUR')

    def test_compatible_job_is_selected_when_foreign_job_exists_first(self):
        self.job.currency = 'EUR'; self.job.quantity = D('1'); self.job.save(update_fields=['currency', 'quantity'])
        compatible = Production.objects.create(code='CUR-JOB-UAH-SECOND', item=self.product, line=self.line,
            quantity=D('1'), revision='A', bom=self.product.bom, location=self.workshop,
            owner=self.owner, due_date='2026-10-01', currency='UAH')
        stock = self.lot('CUR-STOCK-UAH')
        payload = self.advice()['payload']
        self.assertEqual((payload['action'], payload['production_id'], payload['lot_id']),
                         ('erp_reserve', compatible.pk, stock.pk))
        self.execute(payload)

    def test_compatible_partial_reservation_preserves_remaining_need(self):
        held = self.lot('CUR-HELD-ONE', quantity='1')
        Reservation.objects.create(production=self.job, lot=held, quantity=D('1'))
        self.lot('CUR-EUR-FREE-FIRST', 'EUR', quantity='9')
        compatible = self.lot('CUR-UAH-FREE-SECOND', quantity='9')
        payload = self.advice()['payload']
        self.assertEqual((payload['lot_id'], D(payload['quantity'])), (compatible.pk, D('3')))
        self.execute(payload)
        self.assertEqual(sum(self.job.reservations.values_list('quantity', flat=True)), D('4'))
