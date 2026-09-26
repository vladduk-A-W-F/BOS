"""Additive Ukrainian operational fixtures; never migrate or convert old money."""
import hashlib
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from branches.models import Branch
from employees.models import Employee
from finance.models import Counterparty
from operations.models import Configuration, Document, Invoice
from operations.service import as_of
from erp.models import Item, Location, Lot, Purchase, SalesOrder, SalesLine
from erp.service import dispatch, write_lock


class Command(BaseCommand):
    help = 'Додає синтетичні філії Києва, Львова й Дніпра та пов’язані операції UAH без зміни старих даних.'

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.BOS_DATA_MODE != 'demo':
            raise CommandError('Український приклад дозволено лише в навчальній базі.')
        if not Configuration.objects.filter(key='dataset').exists():
            raise CommandError('Спочатку створіть окрему навчальну компанію: seed_bos_demo.')
        if Configuration.objects.filter(key='ua_workpoints_dataset').exists():
            self.stdout.write('Український приклад уже існує. Наявні записи збережено.')
            return
        write_lock()
        if Configuration.objects.filter(key='ua_workpoints_dataset').exists():
            transaction.set_rollback(True)
            self.stdout.write('Український приклад уже існує. Наявні записи збережено.')
            return
        for model in (Branch, Item, Location, Lot, Purchase, SalesOrder, Document, Invoice):
            if model.objects.filter(code__startswith='UA-DEMO-').exists():
                raise CommandError('Префікс UA-DEMO- зайнятий. Автоматичне перезаписування заборонене.')

        def act(action, **data):
            return dispatch({'action': 'erp_' + action, **data}, 'ceo')

        def doc(code, title, text):
            content = text.encode('utf-8')
            return Document.objects.create(code=code, revision='A', title=title,
                access_level='operational', status='approved', filename=code + '.txt',
                content=content, text=text, sections=[{'source': 'Розділ 1', 'text': text}],
                checksum=hashlib.sha256(content).hexdigest())

        spec = doc('UA-DEMO-SPEC', 'Навчальна специфікація монтажного вузла',
            'Синтетичний монтажний вузол, версія A, одиниця шт. Ціни навчальні, без перерахунку валют. Не для реального виробництва.')
        cert = doc('UA-DEMO-CERT', 'Навчальне підтвердження комплектності',
            'Синтетичне підтвердження комплектності партії. Не є сертифікатом виробника.')
        customer = Counterparty.objects.create(name='Український навчальний покупець · синтетичні дані', type='customer')
        supplier = Counterparty.objects.create(name='Український навчальний постачальник · синтетичні дані', type='supplier')
        item = act('item', code='UA-DEMO-PRODUCT', name='Навчальний монтажний вузол', unit='шт.',
            kind='product', method='buy', revision='A', currency='UAH', planned_cost='1100.00',
            document_id=spec.pk, required_documents=['certificate'])['item_id']
        kilogram = act('item', code='UA-DEMO-MATERIAL', name='Навчальний матеріал', unit='кг',
            kind='material', method='buy', revision='A', currency='UAH', planned_cost='80.00')['item_id']
        due = str(as_of() + timedelta(days=21))
        result = []
        for code, city, lat, lng, qty in (
                ('KY', 'Київ', 50.4501, 30.5234, '5'),
                ('LV', 'Львів', 49.8397, 24.0297, '4'),
                ('DN', 'Дніпро', 48.4647, 35.0462, '3')):
            prefix = 'UA-DEMO-' + code
            branch = Branch.objects.create(code=prefix, name=city + ' · навчальна філія',
                short_name=city, type='regional', lat=lat, lng=lng)
            owner = Employee.objects.create(full_name='Навчальний відповідальний · ' + city,
                role='Менеджер операцій', department='Операції', branch=branch)
            location = act('location', code=prefix + '-WH', name=city + ' · навчальний склад',
                kind='warehouse', branch_id=branch.pk)['location_id']
            order = act('order', code=prefix + '-SO', customer_id=customer.pk, owner_id=owner.pk,
                due_date=due, currency='UAH', branch_id=branch.pk,
                lines=[{'item_id': item, 'quantity': qty, 'price': '1800.00'}])['order_id']
            line = SalesLine.objects.get(order_id=order)
            documents = {'certificate': cert.pk}
            if code == 'KY':
                purchase = act('purchase', code=prefix + '-PO', item_id=item, supplier_id=supplier.pk,
                    quantity='5', price='1100.00', currency='UAH', due_date=due, revision='A',
                    direct_reason='Синтетичне поповнення навчального складу')['purchase_id']
                lot = act('receive', purchase_id=purchase, code=prefix + '-LOT', location_id=location,
                    quantity='5', documents=documents)['lot_id']
                act('opening', code=prefix + '-KG', item_id=kilogram, location_id=location,
                    quantity='10.125', unit_cost='80.00', currency='UAH', revision='A')
            else:
                lot = act('opening', code=prefix + '-LOT', item_id=item, location_id=location,
                    quantity='12' if code == 'LV' else '6', unit_cost='1100.00', currency='UAH',
                    revision='A', documents=documents)['lot_id']
            act('quality', lot_id=lot, result='blocked' if code == 'DN' else 'approved',
                inspector_id=owner.pk, note='Навчальна перевірка комплектності; синтетичні дані')
            if code != 'DN':
                act('confirm_order', order_id=order)
                act('reserve', lot_id=lot, quantity=qty, line_id=line.pk)
            if code == 'KY':
                act('ship', line_id=line.pk, lot_id=lot, quantity='2', reference=prefix + '-SHIP')
                invoice = act('invoice', order_id=order, code=prefix + '-INV', due_date=due)['invoice_id']
                act('payment', invoice_id=invoice, amount='1200.00', reference=prefix + '-PAY')
            result.append({'branch_id': branch.pk, 'location_id': location, 'order_id': order})
        Configuration.objects.create(key='ua_workpoints_dataset', value={
            'version': 1, 'synthetic': True, 'currency': 'UAH', 'as_of': str(as_of()),
            'points': result, 'money_basis': 'Навчальні UAH суми; старі валюти не конвертовано.'})
        self.stdout.write('Створено 3 навчальні філії/склади та 3 пов’язані замовлення UAH; Київ має поставку, рахунок і часткову оплату.')
