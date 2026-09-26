"""Install the isolated synthetic BoS 3.0 fasteners lesson fixture once."""
import hashlib
import json
import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from branches.models import Branch
from employees.models import Employee
from finance.models import Contract, Counterparty, Transaction
from operations.models import (AuditEvent, Configuration, Document, Invoice,
    ProcurementRequest, SupplierQuote)
from tasks.models import Task
from erp.models import (Event, Inspection, InvoiceLink, Item, Location, Lot, Movement,
    OperatorEntry, Production, Purchase, Reservation, SalesLine, SalesOrder)
from erp.service import dispatch, write_lock


FIXTURE_ID = 'bos3-fasteners-uk-v1'
SCHEMA_VERSION = 1
MANIFEST_KEY = 'bos3_fixture'
REJECTED_PATH_PARTS = ('online-review', 'review.sqlite', 'bos_demo.sqlite', 'bos_working.sqlite')


class Command(BaseCommand):
    help = 'Створює один ізольований synthetic fixture BoS 3.0 для навчання метизів.'

    def add_arguments(self, parser):
        parser.add_argument('--owner-username', required=True,
            help='Точне ім’я вже активного власника training installation.')

    def fixture_data(self):
        path = Path(__file__).resolve().parents[2] / 'seed' / 'bos3_fasteners_uk_v1.json'
        try:
            raw = path.read_bytes()
            data = json.loads(raw.decode('utf-8'))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CommandError('Не вдалося прочитати fixture BoS 3.0.') from exc
        if (not isinstance(data, dict) or data.get('fixture_id') != FIXTURE_ID
                or data.get('schema_version') != SCHEMA_VERSION or data.get('synthetic') is not True
                or data.get('as_of') != '2026-09-30' or data.get('currency') != 'UAH'):
            raise CommandError('Fixture BoS 3.0 має неправильний контракт.')
        return data, hashlib.sha256(raw).hexdigest()

    def guard_environment(self, owner_username):
        if settings.BOS_DATA_MODE != 'demo':
            raise CommandError('Fixture BoS 3.0 дозволено лише у training demo mode.')
        enabled = os.environ.get('BOS3_TRAINING_ENABLED')
        profile = os.environ.get('BOS3_TRAINING_PROFILE')
        marker = os.environ.get('BOS3_TRAINING_DB_MARKER')
        env_owner = os.environ.get('BOS3_TRAINING_OWNER_USERNAME')
        installation_id = os.environ.get('BOS3_TRAINING_INSTALLATION_ID')
        if enabled != '1' or profile != 'isolated-synthetic':
            raise CommandError('Потрібен явний isolated-synthetic training profile.')
        if marker != FIXTURE_ID or not installation_id or env_owner != owner_username:
            raise CommandError('Потрібні точні training marker, installation ID та owner identity.')
        if not owner_username or owner_username in {'admin', 'demo', 'bos-demo-ceo'}:
            raise CommandError('Потрібен окремий іменований власник training installation.')
        if connection.vendor != 'sqlite':
            raise CommandError('Fixture BoS 3.0 потребує окрему SQLite training базу.')
        database_name = str(connection.settings_dict.get('NAME', ''))
        database_path = Path(database_name).resolve()
        database_key = str(database_path).replace('\\', '/').lower()
        if (not database_name or 'bos3-fasteners' not in database_path.name.lower()
                or any(part in database_key for part in REJECTED_PATH_PARTS)):
            raise CommandError('База не має явного isolated training path marker.')
        user = get_user_model().objects.filter(username=owner_username, is_active=True).first()
        if user is None:
            raise CommandError('Власника training installation не знайдено або доступ відкликано.')
        return user, installation_id, hashlib.sha256(str(database_path).encode('utf-8')).hexdigest()

    def assert_empty_target(self):
        if Configuration.objects.filter(key__in=(MANIFEST_KEY, 'dataset', 'erp_dataset', 'ua_workpoints_dataset', 'organization')).exists():
            raise CommandError('Fixture або legacy seed уже присутній; автоматичне перезаписування заборонене.')
        models = (Branch, Employee, Counterparty, Contract, Transaction, Document,
                  ProcurementRequest, SupplierQuote, Invoice, AuditEvent, Task, Item, Location,
                  Lot, SalesOrder, SalesLine, Purchase, Production, Reservation, Movement,
                  Inspection, InvoiceLink, OperatorEntry, Event)
        if any(model.objects.exists() for model in models):
            raise CommandError('Цільова база не порожня; потрібна нова isolated training база.')

    @transaction.atomic
    def handle(self, *args, **options):
        owner, installation_id, database_identity = self.guard_environment(options['owner_username'])
        data, source_sha256 = self.fixture_data()
        # All fixture presence, replay and emptiness decisions share the ERP mutex.
        # The mutex itself writes Configuration['erp_write'], which is deliberately
        # not a business-data collision marker.
        write_lock()
        known = Configuration.objects.filter(key=MANIFEST_KEY).first()
        if known is not None:
            value = known.value if isinstance(known.value, dict) else {}
            if (value.get('id') == FIXTURE_ID and value.get('schema') == SCHEMA_VERSION
                    and value.get('hash') == source_sha256 and value.get('owner_user_id') == owner.pk
                    and value.get('installation_id') == installation_id):
                self.stdout.write('Fixture BoS 3.0 вже встановлено для цього власника; replay без змін.')
                return
            raise CommandError('Виявлено конфлікт fixture або owner; перезаписування заборонене.')
        self.assert_empty_target()

        branch = Branch.objects.create(code=data['company']['code'], name=data['company']['name'],
            short_name='МайстерКріплення', type='headquarters', status='green',
            employee_count=len(data['people']))
        Configuration.objects.create(key='organization', value={
            'name': data['company']['name'], 'description': data['company']['note'],
            'industry': 'Навчальна фабрика метизів', 'timezone': 'Europe/Kyiv'})
        people = {}
        for row in data['people']:
            people[row['key']] = Employee.objects.create(full_name=row['name'], role=row['role'],
                department=row['department'], branch=branch,
                user=owner if row['key'] == 'sales' else None)
        partners = {
            row['key']: Counterparty.objects.create(name=row['name'], type=row['type'],
                notes='Синтетичний навчальний запис BoS 3.0; не реальний контрагент.')
            for row in data['counterparties']
        }

        def sample_document(code, title, text, status='approved'):
            content = text.encode('utf-8')
            return Document.objects.create(code=code, revision='A', title=title,
                filename=code + '.txt', content=content, size=len(content), text=text,
                sections=[{'source': 'Навчальний зразок', 'text': text}],
                checksum=hashlib.sha256(content).hexdigest(), status=status,
                access_level='operational')

        spec_m10 = sample_document('B3-SPEC-M10-A', 'Навчальна специфікація M10×80',
            'Синтетичний зразок: 1 болт M10×80, 2 гайки M10, 2 шайби 10. '
            'Комплектація 0,80 грн/компл. Не є технічною документацією виробника.')
        spec_m12 = sample_document('B3-SPEC-M12-A', 'Навчальна специфікація M12×100',
            'Синтетичний зразок: 1 болт M12×100, 2 гайки M12, 2 шайби 12. '
            'Комплектація 1,00 грн/компл. Не є технічною документацією виробника.')
        qd_a = sample_document('B3-C2-QD-A', 'Навчальний запис якості LOT-A',
            'Синтетичний навчальний запис: LOT-A допущено до відвантаження у сценарії 2.')
        qd_b = sample_document('B3-C2-QD-B', 'Навчальна форма hold LOT-B',
            'Синтетична навчальна форма: документ покриття LOT-B відсутній; партія лишається hold.',
            status='needs_review')

        # This local dataset anchors projections only; it never changes wall-clock time.
        Configuration.objects.create(key='dataset', value={'id': FIXTURE_ID, 'synthetic': True,
            'as_of': '2026-09-28', 'note': 'Внутрішній seed anchor перед C1 purchase.'})

        def act(action, **values):
            return dispatch({'action': 'erp_' + action, **values}, role='ceo')

        locations = {
            row['key']: act('location', code=row['code'], name=row['name'], kind=row['kind'],
                branch_id=branch.pk)['location_id']
            for row in data['locations']
        }
        item_rows = {row['key']: row for row in data['items']}
        items = {}
        for key in ('bolt_m10', 'nut_m10', 'wash_m10', 'bolt_m12', 'nut_m12', 'wash_m12'):
            row = item_rows[key]
            items[key] = act('item', code=row['code'], name=row['name'], unit=row['unit'],
                kind=row['kind'], method=row['method'], revision='A', currency='UAH',
                planned_cost=row['planned_cost'])['item_id']
        for key, spec, bom, routing in (
            ('kit_m10', spec_m10, [('bolt_m10', '1'), ('nut_m10', '2'), ('wash_m10', '2')],
             [{'name': 'Комплектація', 'instruction': 'Зібрати навчальний комплект за специфікацією.', 'days': 1}]),
            ('kit_m12', spec_m12, [('bolt_m12', '1'), ('nut_m12', '2'), ('wash_m12', '2')],
             [{'name': 'Комплектація', 'instruction': 'Зібрати навчальний комплект за специфікацією.', 'days': 1}]),
        ):
            row = item_rows[key]
            items[key] = act('item', code=row['code'], name=row['name'], unit=row['unit'],
                kind=row['kind'], method=row['method'], revision='A', currency='UAH',
                document_id=spec.pk, planned_cost=row['planned_cost'],
                required_documents=['quality_record'] if key == 'kit_m12' else [],
                bom=[{'item_id': items[part], 'quantity': quantity} for part, quantity in bom],
                routing=routing)['item_id']

        production_location = locations['production']
        warehouse_location = locations['warehouse']
        def opening(code, item, location, quantity, cost, documents=None):
            lot_id = act('opening', code=code, item_id=items[item], location_id=location,
                quantity=quantity, unit_cost=cost, currency='UAH', revision='A',
                documents=documents or {}, reason='Початковий synthetic стан fixture BoS 3.0')['lot_id']
            return Lot.objects.get(pk=lot_id)

        # C1 starts before receipt/quality/reservation/production. The 120 washers PO is only planned.
        c1_product = opening('B3-C1-LOT-KIT-OPEN', 'kit_m10', production_location, '140', '12.00')
        c1_bolt = opening('B3-C1-LOT-BOLT-OPEN', 'bolt_m10', production_location, '400', '6.20')
        c1_nut = opening('B3-C1-LOT-NUT-OPEN', 'nut_m10', production_location, '800', '1.80')
        c1_wash = opening('B3-C1-LOT-WASH-OPEN', 'wash_m10', production_location, '600', '0.70')
        for lot in (c1_product, c1_bolt, c1_nut, c1_wash):
            act('quality', lot_id=lot.pk, result='approved', inspector_id=people['quality'].pk,
                note='Синтетичний стартовий стан C1; партію дозволено використати в навчанні.')
        c1_order = act('order', code='B3-C1-SO-101', customer_id=partners['budmontazh'].pk,
            owner_id=people['sales'].pk, due_date='2026-10-02', currency='UAH',
            fulfillment_location_id=production_location, branch_id=branch.pk,
            notes='C1: внутрішнє підтвердження навчального плану на 500 комплектів; '
                'це не клієнтська обіцянка строку або доставки.',
            lines=[{'item_id': items['kit_m10'], 'quantity': '500', 'price': '20.50'}])['order_id']
        act('confirm_order', order_id=c1_order)
        c1_line = SalesLine.objects.get(order_id=c1_order)
        c1_job = act('job', code='B3-C1-MO-101', item_id=items['kit_m10'], quantity='360',
            location_id=production_location, owner_id=people['production'].pk, due_date='2026-09-30',
            line_id=c1_line.pk)['production_id']
        c1_purchase = act('purchase', code='B3-C1-PO-101', item_id=items['wash_m10'],
            supplier_id=partners['washerprom'].pk, quantity='120', price='0.70', currency='UAH',
            due_date='2026-09-29', revision='A', production_id=c1_job,
            destination_id=production_location,
            direct_reason='Навчальний план закупівлі для дефіциту 120 шайб; дата не є підтвердженням постачальника.')['purchase_id']

        # C2 permits exactly LOT-A. LOT-B has an honest sample hold form, never accepted evidence.
        c2_order = act('order', code='B3-C2-SO-202', customer_id=partners['karkas'].pk,
            owner_id=people['sales'].pk, due_date='2026-10-03', currency='UAH',
            fulfillment_location_id=warehouse_location, branch_id=branch.pk,
            notes='C2: відвантажити тільки допущену партію 250 комплектів M12.',
            lines=[{'item_id': items['kit_m12'], 'quantity': '250', 'price': '27.50'}])['order_id']
        act('confirm_order', order_id=c2_order)
        c2_line = SalesLine.objects.get(order_id=c2_order)
        c2_a = opening('B3-C2-LOT-A', 'kit_m12', warehouse_location, '250', '16.40',
            {'quality_record': qd_a.pk})
        c2_b = opening('B3-C2-LOT-B', 'kit_m12', warehouse_location, '20', '16.40',
            {'quality_record': qd_b.pk})
        act('quality', lot_id=c2_a.pk, result='approved', inspector_id=people['quality'].pk,
            note='B3-C2-QD-A: навчальний допуск саме 250 комплектів LOT-A.')
        act('quality', lot_id=c2_b.pk, result='blocked', inspector_id=people['quality'].pk,
            note='B3-C2-QD-B: документ покриття відсутній; 20 комплектів LOT-B не відвантажувати.')

        # C3 is an already shipped/invoiced historical lesson state with one, and only one, payment.
        c3_order = act('order', code='B3-C3-SO-303', customer_id=partners['fasad'].pk,
            owner_id=people['sales'].pk, due_date='2026-09-23', currency='UAH',
            fulfillment_location_id=warehouse_location, branch_id=branch.pk,
            notes='C3: історична навчальна поставка; оплата 10 000 грн уже підтверджена.',
            lines=[{'item_id': items['kit_m10'], 'quantity': '800', 'price': '20.50'}])['order_id']
        act('confirm_order', order_id=c3_order)
        c3_line = SalesLine.objects.get(order_id=c3_order)
        c3_lot = opening('B3-C3-LOT-SHIP', 'kit_m10', warehouse_location, '800', '12.00')
        act('quality', lot_id=c3_lot.pk, result='approved', inspector_id=people['quality'].pk,
            note='Синтетичний історичний допуск C3 для вже виконаного відвантаження.')
        act('reserve', lot_id=c3_lot.pk, quantity='800', line_id=c3_line.pk)
        act('ship', line_id=c3_line.pk, lot_id=c3_lot.pk, quantity='800', reference='B3-C3-SHP-303')
        c3_invoice = act('invoice', order_id=c3_order, code='B3-C3-INV-303', due_date='2026-09-29')['invoice_id']
        act('payment', invoice_id=c3_invoice, amount='10000.00', reference='B3-C3-PAY-303')

        def quantity(value):
            return format(value.normalize(), 'f')

        c3_invoice_row = Invoice.objects.get(pk=c3_invoice)
        source_map = {
            'branch_id': branch.pk,
            'people': {key: person.pk for key, person in people.items()},
            'counterparties': {key: partner.pk for key, partner in partners.items()},
            'items': items,
            'locations': locations,
            'documents': {'m10_spec_id': spec_m10.pk, 'm12_spec_id': spec_m12.pk,
                'c2_lot_a_quality_document_id': qd_a.pk, 'c2_lot_b_hold_document_id': qd_b.pk},
            'BOS3-CASE-01': {'anchor': '2026-09-28', 'order_id': c1_order, 'line_id': c1_line.pk,
                'purchase_id': c1_purchase, 'production_id': c1_job, 'customer_id': partners['budmontazh'].pk,
                'owner_id': people['sales'].pk,
                'initial': {'finished_quantity': quantity(c1_product.quantity),
                    'production_quantity': quantity(Production.objects.get(pk=c1_job).quantity),
                    'bolt_quantity': quantity(c1_bolt.quantity), 'nut_quantity': quantity(c1_nut.quantity),
                    'washer_quantity': quantity(c1_wash.quantity), 'washer_required': '720',
                    'washer_shortage': '120'},
                'component_lot_ids': {'fg': c1_product.pk, 'bolt': c1_bolt.pk,
                    'nut': c1_nut.pk, 'washer': c1_wash.pk},
                'component_item_ids': {'fg': items['kit_m10'], 'bolt': items['bolt_m10'],
                    'nut': items['nut_m10'], 'washer': items['wash_m10']},
                'lot_ids': {'approved_kit_140': c1_product.pk, 'bolt_400': c1_bolt.pk,
                    'nut_800': c1_nut.pk, 'wash_600': c1_wash.pk}},
            'BOS3-CASE-02': {'anchor': '2026-09-29', 'order_id': c2_order, 'line_id': c2_line.pk,
                'customer_id': partners['karkas'].pk, 'owner_id': people['sales'].pk,
                'shipment_reference': 'B3-C2-SHP-202', 'approved_lot_id': c2_a.pk, 'blocked_lot_id': c2_b.pk,
                'initial': {'approved_quantity': quantity(c2_a.quantity),
                    'blocked_quantity': quantity(c2_b.quantity)}},
            'BOS3-CASE-03': {'anchor': '2026-09-30', 'order_id': c3_order, 'line_id': c3_line.pk,
                'customer_id': partners['fasad'].pk, 'owner_id': people['sales'].pk,
                'shipment_reference': 'B3-C3-SHP-303', 'invoice_id': c3_invoice,
                'payment_reference': 'B3-C3-PAY-303',
                'expected': {'invoice': str(c3_invoice_row.amount), 'paid': str(c3_invoice_row.paid),
                    'open': str(c3_invoice_row.amount - c3_invoice_row.paid)}}
        }
        Configuration.objects.filter(key='dataset').update(value={'id': FIXTURE_ID, 'synthetic': True,
            'as_of': data['as_of'], 'currency': 'UAH',
            'note': 'Симульована навчальна дата fixture; системний час не змінюється.'})
        Configuration.objects.create(key=MANIFEST_KEY, value={
            'id': FIXTURE_ID, 'schema': SCHEMA_VERSION, 'hash': source_sha256,
            'fixture_id': FIXTURE_ID, 'schema_version': SCHEMA_VERSION, 'source_sha256': source_sha256,
            'synthetic': True, 'as_of': data['as_of'], 'owner_username': owner.username,
            'owner_user_id': owner.pk, 'installation_id': installation_id,
            'database_identity_sha256': database_identity, 'source_map': source_map,
        })
        self.stdout.write('Fixture BoS 3.0 створено: три synthetic кейси метизів, UAH, as_of 2026-09-30.')
