"""Next-step titles name the material, supplier and product in plain words; payloads stay unchanged.

Synthetic: a demo company plus one synthetic material, product, order, job and purchase, driven through the
ordinary ERP commands so each changed branch of experience.next_step is reached for real.
"""
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TransactionTestCase, override_settings

from finance.models import Counterparty
from . import bos4_demo_data as data
from .bos4_demo import seed_bos4_demo
from .models import Location, Reservation, SalesOrder
from .service import dispatch


def act(action, **payload):
    return dispatch({'action': 'erp_' + action, **payload}, 'ceo')


@override_settings(BOS_DATA_MODE='demo', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class NextStepNameTests(TransactionTestCase):
    def setUp(self):
        folder = TemporaryDirectory(prefix='bos4-next-step-test-')
        self.addCleanup(folder.cleanup)
        override = override_settings(MEDIA_ROOT=Path(folder.name) / 'media')
        override.enable()
        self.addCleanup(override.disable)
        seed_bos4_demo()
        self.shop = Location.objects.get(code='KM-ZHY-SHOP')
        self.store = Location.objects.get(code='KM-ZHY-METAL')
        self.supplier = Counterparty.objects.get(name='Металопрокат Центр')
        self.material = act('item', code='T-MAT-1', name='Синтетичний профіль 25×25', unit='шт.', kind='material',
            method='buy', revision='A', currency='UAH', planned_cost='100.00', minimum='1', lead_days=1,
            required_documents=[])['item_id']
        self.product = act('item', code='T-PRD-1', name='Синтетичний стелаж Т-1', unit='шт.', kind='product',
            method='make', revision='A', currency='UAH', planned_cost='500.00', minimum='1', lead_days=1,
            required_documents=[], bom=[{'item_id': self.material, 'quantity': '2'}],
            routing=[{'name': n, 'instruction': i, 'days': d} for n, i, d in data.ROUTE])['item_id']
        customer = Counterparty.objects.create(name='ТОВ «Синтетичний клієнт»', type='customer')
        out = act('order', code='ZM-T-1', customer_id=customer.pk, owner_id=data_owner(), due_date='2026-12-01', currency='UAH',
            fulfillment_location_id=Location.objects.get(code='KM-ZHY-FG').pk,
            lines=[{'item_id': self.product, 'quantity': '3', 'price': '900.00'}])
        act('confirm_order', order_id=out['order_id'])
        self.order = SalesOrder.objects.get(pk=out['order_id'])
        line = self.order.lines.get()
        self.job = act('job', code='VZ-T-1', item_id=self.product, quantity='3', location_id=self.shop.pk,
            owner_id=data_owner(), due_date='2026-11-20', line_id=line.pk)['production_id']
        self.users = {}

    def next(self, role='ceo'):
        if role not in self.users:
            user = get_user_model().objects.create_user(username='synthetic-' + role, password='synthetic-pass')
            Group.objects.get_or_create(name=role)[0].user_set.add(user)
            self.users[role] = user
        self.client.force_login(self.users[role])
        response = self.client.get(f'/api/erp/orders/{self.order.pk}/next/')
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def assert_no_codes(self, title):
        for code in ('T-MAT-1', 'T-PRD-1', 'VZ-T-1', 'ZK-T-1', 'ZM-T-1'):
            self.assertNotIn(code, title)

    def test_supply_receive_reserve_start_and_finish_name_the_things(self):
        step = self.next()
        self.assertEqual(step['title'], 'Потрібно забезпечити «Синтетичний профіль 25×25»')
        self.assertIsNone(step['payload'])

        po = act('purchase', code='ZK-T-1', item_id=self.material, supplier_id=self.supplier.pk, quantity='6',
            price='100.00', currency='UAH', due_date='2026-11-01', revision='A', production_id=self.job,
            destination_id=self.shop.pk, origin_country='UA', direct_reason='Синтетична закупівля під VZ-T-1')['purchase_id']
        step = self.next()
        self.assertEqual(step['title'], 'Прийняти поставку «Синтетичний профіль 25×25» від Металопрокат Центр')
        self.assertEqual((step['payload']['action'], step['payload']['purchase_id'], step['payload']['quantity']),
                         ('erp_receive', po, '6.000'))
        self.assert_no_codes(step['title'])
        # The observer reads the same plain title but gets no executable payload.
        observer = self.next('observer')
        self.assertEqual((observer['title'], observer['payload']), (step['title'], None))

        lot = act('receive', purchase_id=po, code='T-L-1', location_id=self.shop.pk, quantity='6', documents={})['lot_id']
        act('quality', lot_id=lot, result='approved', inspector_id=data_owner(), note='Синтетична перевірка')
        step = self.next()
        self.assertEqual(step['title'], 'Зарезервувати «Синтетичний профіль 25×25»')
        self.assertEqual((step['payload']['action'], step['payload']['lot_id'], step['payload']['production_id']),
                         ('erp_reserve', lot, self.job))

        act('reserve', lot_id=lot, quantity='6', production_id=self.job)
        step = self.next()
        self.assertEqual(step['title'], 'Розпочати виробництво «Синтетичний стелаж Т-1»')
        self.assertEqual(step['payload'], {'action': 'erp_start', 'production_id': self.job})

        act('start', production_id=self.job)
        for name, _, _ in data.ROUTE:
            act('operator', production_id=self.job, operation=name, operator_id=data_owner(), result='done',
                minutes=30, defects='0', note='Синтетична операція')
        step = self.next()
        self.assertEqual(step['title'], 'Випустити продукцію «Синтетичний стелаж Т-1»')
        self.assertEqual((step['payload']['action'], step['payload']['production_id'], step['payload']['quantity']),
                         ('erp_finish', self.job, '3.000'))
        self.assert_no_codes(step['title'])

    def test_transfer_and_reservation_guards_name_the_things(self):
        lot = act('opening', code='T-L-2', item_id=self.material, location_id=self.store.pk, quantity='10',
            unit_cost='100.00', currency='UAH', revision='A', documents={}, reason='Синтетичний залишок')['lot_id']
        act('quality', lot_id=lot, result='approved', inspector_id=data_owner(), note='Синтетична перевірка')
        step = self.next()
        self.assertEqual(step['title'], 'Передати «Синтетичний профіль 25×25» до місця виконання')
        self.assertEqual((step['payload']['action'], step['payload']['lot_id'], step['payload']['location_id']),
                         ('erp_transfer', lot, self.shop.pk))
        # A reservation held outside the job's place is a guard, not an action; it names the product.
        Reservation.objects.create(lot_id=lot, production_id=self.job, quantity='1')
        step = self.next()
        self.assertEqual(step['title'], 'Звірити місце резервів: виробництво «Синтетичний стелаж Т-1»')
        self.assertIsNone(step['payload'])
        self.assert_no_codes(step['title'])


def data_owner():
    from employees.models import Employee
    return Employee.objects.get(full_name='Наталія Ткаченко').pk
