from scripts.check_support import login_test_client
"""Synthetic A01 regressions through the actual HTTP/ORM paths."""
from decimal import Decimal as D
from django.db import connection
from django.db.models import Sum
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from employees.models import Employee
from operations.models import Configuration
from .models import Item, Location, Lot, Production, Movement, Event
from . import service


class FinishIntegrityTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        login_test_client(self.client)
        self.client.get('/api/operations/status/')
        self.owner = Employee.objects.create(full_name='Синтетичний оператор A01')
        self.location = Location.objects.create(code='A01-W', name='Тестова дільниця', kind='production')
        self.raw = Item.objects.create(code='A01-M', name='Тестовий матеріал', kind='material')
        self.product = Item.objects.create(code='A01-P', name='Тестовий виріб', method='make')
        self.job = Production.objects.create(code='A01-J', item=self.product, quantity=10,
            revision='A', bom=[{'item_id': self.raw.id, 'quantity': '1'}], routing=[],
            location=self.location, owner=self.owner, due_date='2026-09-30', status='running')
        Configuration.objects.get_or_create(key='erp_write', defaults={'value': {'revision': 0}})

    def post(self, url, data):
        return self.client.post(url, data, content_type='application/json',
                                HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)

    def lot(self, code, quantity, cost='2.00'):
        lot = service.newlot(code, self.raw, self.location, D(quantity), D(cost), 'EUR',
                             'A', {}, 'opening', code)
        lot.quality = 'approved'; lot.save(update_fields=['quality'])
        return lot

    def reserve(self, lot, quantity):
        return service.dispatch({'action': 'erp_reserve', 'lot_id': lot.id,
            'production_id': self.job.id, 'quantity': str(quantity)})

    def payload(self, quantity=10, code='A01-OUT'):
        return {'action': 'erp_finish', 'production_id': self.job.id, 'quantity': str(quantity),
                'code': code, 'location_id': self.location.id, 'labor_cost': '0'}

    def confirm(self, proposal_id):
        response = self.post('/api/operations/confirm/', {'proposal_id': proposal_id, 'confirmed': True})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def finish(self, quantity=10, code='A01-OUT'):
        before = service.fingerprint()
        response = self.post('/api/erp/preview/', self.payload(quantity, code))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(service.fingerprint(), before, 'Перегляд не змінює бізнес-дані')
        proposal = response.json()['id']
        return proposal, self.confirm(proposal)

    def assert_balance(self, lot, expected):
        lot.refresh_from_db()
        total = lot.movements.aggregate(n=Sum('quantity'))['n'] or D(0)
        self.assertEqual(lot.quantity, D(expected))
        self.assertEqual(lot.quantity, total, 'Залишок = сума всіх рухів партії')
        self.assertLessEqual(service.reserved(lot), lot.quantity)

    def test_two_reservations_consume_one_current_lot_and_replay_is_identical(self):
        lot = self.lot('A01-L', '10')
        self.reserve(lot, 5); self.reserve(lot, 5)
        self.assertEqual(self.job.reservations.count(), 2)
        proposal, receipt = self.finish()
        self.assert_balance(lot, '0')
        self.assertEqual(Movement.objects.filter(kind='production').count(), 1)
        before = service.fingerprint(), Event.objects.count()
        self.assertEqual(self.confirm(proposal), receipt)
        self.assertEqual((service.fingerprint(), Event.objects.count()), before)
        self.assertEqual(D(receipt['cost']), D('20.00'))

    def test_partial_six_then_four_keeps_reservations_and_balance(self):
        lot = self.lot('A01-L', '10')
        self.reserve(lot, 5); self.reserve(lot, 5)
        self.finish(6, 'A01-OUT-6'); self.assert_balance(lot, '4')
        self.job.refresh_from_db()
        self.assertEqual((self.job.produced, self.job.status), (D('6'), 'running'))
        self.assertEqual(service.reserved(lot), D('4'))
        self.finish(4, 'A01-OUT-4'); self.assert_balance(lot, '0')
        self.job.refresh_from_db()
        self.assertEqual((self.job.produced, self.job.status), (D('10'), 'done'))

    def test_different_lots_keep_separate_quantities_and_costs(self):
        a = self.lot('A01-LA', '5', '2.00'); b = self.lot('A01-LB', '5', '3.00')
        self.reserve(a, 2); self.reserve(a, 3); self.reserve(b, 1); self.reserve(b, 4)
        _, receipt = self.finish()
        self.assert_balance(a, '0'); self.assert_balance(b, '0')
        self.assertEqual(D(receipt['cost']), D('25.00'))

    def assert_lock_precedes_business_reads(self, queries):
        sql = [q['sql'].lower() for q in queries]
        locks = [i for i, q in enumerate(sql) if q.startswith('update "operations_configuration"')]
        reads = [i for i, q in enumerate(sql) if q.startswith('select') and '"erp_' in q]
        self.assertTrue(locks, 'Запис блокує спільний ERP mutex')
        self.assertTrue(reads, 'Запит справді читає бізнес-дані')
        self.assertLess(min(locks), min(reads), 'Блокування потрібне до fingerprint та знімка «Було»')

    def test_preview_and_confirm_lock_before_fingerprint_and_snapshot(self):
        lot = self.lot('A01-L', '10'); self.reserve(lot, 10)
        with CaptureQueriesContext(connection) as preview:
            response = self.post('/api/erp/preview/', self.payload())
        self.assertEqual(response.status_code, 200, response.content)
        self.assert_lock_precedes_business_reads(preview.captured_queries)
        with CaptureQueriesContext(connection) as confirm:
            self.confirm(response.json()['id'])
        self.assert_lock_precedes_business_reads(confirm.captured_queries)

    def test_generic_proposal_locks_before_erp_fingerprint(self):
        lot = self.lot('A01-L', '10'); self.reserve(lot, 10)
        with CaptureQueriesContext(connection) as preview:
            response = self.post('/api/operations/preview/', self.payload())
        self.assertEqual(response.status_code, 200, response.content)
        self.assert_lock_precedes_business_reads(preview.captured_queries)

    def test_overproduction_rejected_without_partial_write(self):
        lot = self.lot('A01-L', '10'); self.reserve(lot, 5); self.reserve(lot, 5)
        self.finish(6, 'A01-OUT-6')
        before = service.fingerprint(), Event.objects.count()
        response = self.post('/api/erp/preview/', self.payload(5, 'A01-TOO-MUCH'))
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual((service.fingerprint(), Event.objects.count()), before)
