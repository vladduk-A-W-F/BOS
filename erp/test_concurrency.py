"""A06: actual HTTP proposal pairs and actual ORM resource contention.

Run only with verification_settings and a NEW disposable test database.  There
are no reads of installation databases, mocks, auth bypasses or product writes
in this module.  Root can copy this file unchanged to erp/test_concurrency.py.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
from decimal import Decimal as D
import hashlib
import json
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

from django.conf import settings
from django.db import connections, connection, IntegrityError, OperationalError
from django.db.models import Sum
from django.test import Client, TransactionTestCase

from employees.models import Employee
from finance.models import Counterparty, Salary, Transaction
from operations.models import ActionProposal, AuditEvent, Configuration, Document, Invoice
from operations.service import Conflict
from erp import service
from erp.models import (
    Item, Location, Lot, SalesOrder, SalesLine, Production, Reservation, Purchase,
    Movement, Inspection, ChangeOrder, InvoiceLink, OperatorEntry, Event,
)
from scripts.check_support import login_test_client


CURRENCIES = ('EUR', 'USD', 'UAH')
ERP_ACTIONS = (
    'item', 'location', 'order', 'confirm_order', 'opening', 'purchase', 'receive',
    'job', 'reserve', 'release', 'transfer', 'quality', 'attach', 'start',
    'operator', 'finish', 'ship', 'return', 'invoice', 'payment', 'change',
    'apply_change', 'resolve_job', 'postpone', 'postpone_job', 'adjust',
)
FINANCIAL_ACTIONS = frozenset((
    'item', 'order', 'opening', 'purchase', 'receive', 'job', 'reserve', 'release',
    'transfer', 'finish', 'ship', 'return', 'invoice', 'payment', 'adjust',
))
CONTENTION_CASES = (
    'reserve', 'release', 'receive', 'transfer', 'finish', 'ship', 'return',
    'adjust', 'invoice', 'payment', 'payment_dup',
)
COVERAGE_MANIFEST = {
    'erp_proposal_http': {
        action: {
            'inventory_ids': ['ERP-' + action, 'CORE-erp-preview', 'CORE-execute',
                              'CORE-confirm', 'CORE-dispatch'] +
                             (['DEF-01'] if action == 'finish' else []),
            'route': '/api/operations/confirm/', 'identity': 'same proposal_id',
            'test': 'ERPProposalConcurrencyTests.test_http_pair_' + action,
            'currencies': list(CURRENCIES if action in FINANCIAL_ACTIONS else ('EUR',)),
        } for action in ERP_ACTIONS
    },
    'erp_resource_orm': {
        case: {
            'inventory_ids': ['ERP-' + ('payment' if case == 'payment_dup' else case),
                              'CORE-dispatch'],
            'entrypoint': 'erp.service.dispatch',
            'test': 'ERPResourceConcurrencyTests.test_orm_contention_' + case,
            'currencies': list(CURRENCIES),
        } for case in CONTENTION_CASES
    },
}

COVERAGE_MANIFEST['erp_proposal_http']['import_batch'] = {'inventory_ids': ['ERP-import_batch', 'CORE-erp-preview', 'CORE-execute', 'CORE-confirm', 'CORE-dispatch'], 'route': '/api/operations/confirm/', 'identity': 'same proposal_id', 'test': 'ERPImportConcurrencyTests.test_http_pair_import_batch', 'currencies': ['EUR', 'USD', 'UAH']}

COVERAGE_MANIFEST['erp_proposal_http'].update({'cancel_remaining': {'inventory_ids': ['ERP-cancel_remaining', 'CORE-erp-preview', 'CORE-execute', 'CORE-confirm', 'CORE-dispatch'], 'route': '/api/operations/confirm/', 'identity': 'same proposal_id', 'test': 'ERPCorrectionConcurrencyTests.test_http_pair_cancel_remaining', 'currencies': ['EUR', 'USD', 'UAH']}, 'return_supplier': {'inventory_ids': ['ERP-return_supplier', 'CORE-erp-preview', 'CORE-execute', 'CORE-confirm', 'CORE-dispatch'], 'route': '/api/operations/confirm/', 'identity': 'same proposal_id', 'test': 'ERPCorrectionConcurrencyTests.test_http_pair_return_supplier', 'currencies': ['EUR', 'USD', 'UAH']}, 'return_from_shipment': {'inventory_ids': ['ERP-return_from_shipment', 'CORE-erp-preview', 'CORE-execute', 'CORE-confirm', 'CORE-dispatch'], 'route': '/api/operations/confirm/', 'identity': 'same proposal_id', 'test': 'ERPCorrectionConcurrencyTests.test_http_pair_return_from_shipment', 'currencies': ['EUR', 'USD', 'UAH']}, 'credit_invoice': {'inventory_ids': ['ERP-credit_invoice', 'CORE-erp-preview', 'CORE-execute', 'CORE-confirm', 'CORE-dispatch'], 'route': '/api/operations/confirm/', 'identity': 'same proposal_id', 'test': 'ERPCorrectionConcurrencyTests.test_http_pair_credit_invoice', 'currencies': ['EUR', 'USD', 'UAH']}, 'reverse_credit': {'inventory_ids': ['ERP-reverse_credit', 'CORE-erp-preview', 'CORE-execute', 'CORE-confirm', 'CORE-dispatch'], 'route': '/api/operations/confirm/', 'identity': 'same proposal_id', 'test': 'ERPCorrectionConcurrencyTests.test_http_pair_reverse_credit', 'currencies': ['EUR', 'USD', 'UAH']}, 'confirm_supplier_claim': {'inventory_ids': ['ERP-confirm_supplier_claim', 'CORE-erp-preview', 'CORE-execute', 'CORE-confirm', 'CORE-dispatch'], 'route': '/api/operations/confirm/', 'identity': 'same proposal_id', 'test': 'ERPCorrectionConcurrencyTests.test_http_pair_confirm_supplier_claim', 'currencies': ['EUR', 'USD', 'UAH']}})

BUSINESS_MODELS = (
    Item, Location, Lot, SalesOrder, SalesLine, Production, Reservation, Purchase,
    Movement, Inspection, ChangeOrder, InvoiceLink, OperatorEntry, Event,
    Invoice, Document, Salary, Transaction, AuditEvent,
)
CREATED_ROWS = {
    'item': {Item: 1}, 'location': {Location: 1},
    'order': {SalesOrder: 1, SalesLine: 1}, 'confirm_order': {},
    'opening': {Lot: 1, Movement: 1}, 'purchase': {Purchase: 1},
    'receive': {Lot: 1, Movement: 1}, 'job': {Production: 1},
    'reserve': {Reservation: 1}, 'release': {},
    'transfer': {Lot: 1, Movement: 2}, 'quality': {Inspection: 1}, 'attach': {},
    'start': {}, 'operator': {OperatorEntry: 1},
    'finish': {Lot: 1, Movement: 3}, 'ship': {Movement: 1},
    'return': {Lot: 1, Movement: 1}, 'invoice': {Invoice: 1, InvoiceLink: 1},
    'payment': {}, 'change': {ChangeOrder: 1}, 'apply_change': {},
    'resolve_job': {}, 'postpone': {}, 'postpone_job': {}, 'adjust': {Movement: 1},
}
ALLOWED_EXISTING_CHANGES = {
    'confirm_order': {SalesOrder: {'status'}},
    'receive': {Purchase: {'received', 'status'}},
    'release': {Reservation: {'quantity'}},
    'transfer': {Lot: {'quantity'}}, 'quality': {Lot: {'quality'}},
    'attach': {Lot: {'documents'}}, 'start': {Production: {'status'}},
    'finish': {Lot: {'quantity'}, Reservation: {'quantity'},
               Production: {'produced', 'actual_cost', 'status'}},
    'ship': {Lot: {'quantity'}, Reservation: {'quantity'}, SalesLine: {'shipped'}},
    'invoice': {SalesLine: {'invoiced'}}, 'payment': {Invoice: {'paid'}},
    'apply_change': {Item: {'revision', 'document_id'}, Production: {'needs_review'},
                     ChangeOrder: {'status', 'disposition'}},
    'resolve_job': {Production: {'needs_review'}},
    'postpone': {Purchase: {'due_date'}}, 'postpone_job': {Production: {'due_date'}},
    'adjust': {Lot: {'quantity'}},
}


def business_state():
    return {model: {r['id']: r for r in model.objects.order_by('pk').values()}
            for model in BUSINESS_MODELS}


class ERPConcurrencyBase(TransactionTestCase):
    """Only helpers; concrete classes below supply 37 explicit manifest cases."""
    databases = {'default'}

    def setUp(self):
        # File locking is essential.  Reject a misleading in-memory test run.
        if connection.vendor == 'sqlite':
            name = str(connection.settings_dict['NAME'])
            self.assertNotIn('memory', name.lower(), name)
            self.assertNotEqual(name, ':memory:')
        self.assertIn(connection.vendor, ('sqlite', 'postgresql'))
        self.assertEqual(set(ERP_ACTIONS)|{'import_batch'}|{'return_supplier', 'reverse_credit', 'cancel_remaining', 'confirm_supplier_claim', 'return_from_shipment', 'credit_invoice'}|{'statement_import','statement_reconcile'}, set(service.SCHEMAS),
                         'Every current schema must remain in the explicit coverage manifest')
        Configuration.objects.get_or_create(key='erp_write', defaults={'value': {'revision': 0}})
        self.http = Client(enforce_csrf_checks=True, raise_request_exception=False)
        self.user = login_test_client(self.http)
        self.assertEqual(self.http.session.get('_auth_user_id'), str(self.user.pk))

    def base_fixture(self, currency):
        prefix = 'A06-' + uuid4().hex[:8]
        f = SimpleNamespace(prefix=prefix, currency=currency)
        f.code = lambda suffix: prefix + '-' + suffix
        f.owner = Employee.objects.create(full_name='Синтетичний оператор ' + prefix)
        f.customer = Counterparty.objects.create(name=prefix + ' клієнт', type='customer')
        f.supplier = Counterparty.objects.create(name=prefix + ' постачальник', type='supplier')
        f.warehouse = Location.objects.create(code=f.code('W'), name='Синтетичний склад')
        f.production_location = Location.objects.create(code=f.code('P'), name='Синтетична дільниця', kind='production')
        f.material = Item.objects.create(code=f.code('M'), name='Синтетичний матеріал',
            kind='material', method='buy', unit='шт.', revision='A', currency=currency)
        f.product = Item.objects.create(code=f.code('F'), name='Синтетичний виріб',
            kind='product', method='make', unit='шт.', revision='A', currency=currency,
            planned_cost=D('3.00'), bom=[{'item_id': f.material.pk, 'quantity': '1'}],
            routing=[{'name': 'Виготовлення', 'instruction': 'Синтетична інструкція', 'days': 1}])
        f.lot = Lot.objects.create(code=f.code('L'), item=f.material, location=f.warehouse,
            quantity=D('10'), revision='A', quality='approved', unit_cost=D('2.00'), currency=currency)
        Movement.objects.create(lot=f.lot, quantity=D('10'), kind='opening',
            reference=f.lot.code, cost=D('20.00'))
        f.order = SalesOrder.objects.create(code=f.code('SO'), customer=f.customer,
            owner=f.owner, due_date=date(2026, 9, 20), currency=currency, status='confirmed')
        f.line = SalesLine.objects.create(order=f.order, item=f.material, revision='A',
            quantity=D('10'), price=D('5.00'))
        f.purchase = Purchase.objects.create(code=f.code('PO'), item=f.material,
            supplier=f.supplier, quantity=D('10'), price=D('2.00'), extras=D('10.00'),
            currency=currency, due_date=date(2026, 9, 20), original_due=date(2026, 9, 20), revision='A')
        f.job = Production.objects.create(code=f.code('J'), item=f.product,
            quantity=D('10'), revision='A', bom=deepcopy(f.product.bom),
            routing=deepcopy(f.product.routing), currency=currency, planned_cost=D('30.00'),
            location=f.production_location, owner=f.owner, due_date=date(2026, 9, 20))
        return f

    def document(self, f, revision):
        content = ('Синтетична версія ' + f.prefix + revision).encode()
        return Document.objects.create(code=f.code('DOC'), revision=revision,
            title='Синтетичний документ', filename=f.code('doc.txt'), content=content,
            text=content.decode(), checksum=hashlib.sha256(content).hexdigest(), status='approved')

    def production_material(self, f):
        f.lot.location = f.production_location
        f.lot.save(update_fields=['location'])
        f.reservations = [Reservation.objects.create(lot=f.lot, production=f.job, quantity=D('5'))
                          for _ in range(2)]

    def shipped_fixture(self, f):
        f.lot.quantity = D('0'); f.lot.save(update_fields=['quantity'])
        f.line.shipped = D('10'); f.line.save(update_fields=['shipped'])
        Movement.objects.create(lot=f.lot, quantity=D('-10'), kind='shipment',
            reference=f.code('OLD-SHIP'), cost=D('20.00'), line=f.line)

    def finished_history(self, f):
        """Valid old production: one material consumed and one output made."""
        job = Production.objects.create(code=f.code('DONE'), item=f.product, quantity=D('1'),
            produced=D('1'), status='done', revision='A', currency=f.currency,
            bom=deepcopy(f.product.bom), routing=deepcopy(f.product.routing),
            actual_cost=D('3.00'), planned_cost=D('3.00'), owner=f.owner,
            location=f.production_location, due_date=date(2026, 9, 20))
        raw = Lot.objects.create(code=f.code('OLD-M'), item=f.material,
            location=f.production_location, quantity=D('0'), revision='A',
            quality='approved', unit_cost=D('2.00'), currency=f.currency)
        Movement.objects.create(lot=raw, quantity=D('1'), kind='opening', reference=raw.code, cost=D('2.00'))
        Movement.objects.create(lot=raw, quantity=D('-1'), kind='consume', reference=job.code,
            cost=D('2.00'), production=job)
        out = Lot.objects.create(code=f.code('OLD-F'), item=f.product, location=f.warehouse,
            quantity=D('1'), revision='A', quality='approved', unit_cost=D('3.00'), currency=f.currency)
        Movement.objects.create(lot=out, quantity=D('1'), kind='production', reference=job.code,
            cost=D('3.00'), production=job)
        OperatorEntry.objects.create(production=job, operation='Виготовлення', operator=f.owner,
            result='done', minutes=1, defects=D('0'), note='Синтетична історія')
        f.done_job, f.old_output = job, out

    def prepare(self, action, currency):
        f = self.base_fixture(currency)
        payload = {'action': 'erp_' + action}
        if action == 'item':
            payload.update(code=f.code('NEW'), name='Синтетичний компонент', unit='шт.',
                           kind='component', method='buy', revision='A', currency=currency)
        elif action == 'location':
            payload.update(code=f.code('W2'), name='Синтетичний другий склад', kind='warehouse')
        elif action == 'order':
            payload.update(code=f.code('SO2'), customer_id=f.customer.pk, owner_id=f.owner.pk,
                due_date='2026-09-20', currency=currency,
                lines=[{'item_id': f.material.pk, 'quantity': '10', 'price': '5.00'}])
        elif action == 'confirm_order':
            f.order.status = 'quote'; f.order.save(update_fields=['status'])
            payload.update(order_id=f.order.pk)
        elif action == 'opening':
            payload.update(code=f.code('OPEN'), item_id=f.material.pk, location_id=f.warehouse.pk,
                           quantity='10', unit_cost='2.00', currency=currency, revision='A')
        elif action == 'purchase':
            payload.update(code=f.code('PO2'), item_id=f.material.pk, supplier_id=f.supplier.pk,
                quantity='10', price='2.00', extras='10.00', currency=currency,
                due_date='2026-09-20', revision='A',direct_reason='Синтетична пряма закупівля для перевірки конкурентності')
        elif action == 'receive':
            payload.update(purchase_id=f.purchase.pk, code=f.code('RCV'),
                           location_id=f.warehouse.pk, quantity='7')
        elif action == 'job':
            payload.update(code=f.code('J2'), item_id=f.product.pk, quantity='10',
                location_id=f.production_location.pk, owner_id=f.owner.pk, due_date='2026-09-20')
        elif action == 'reserve':
            payload.update(lot_id=f.lot.pk, line_id=f.line.pk, quantity='7')
        elif action == 'release':
            f.reservation = Reservation.objects.create(lot=f.lot, line=f.line, quantity=D('10'))
            payload.update(reservation_id=f.reservation.pk, quantity='7')
        elif action == 'transfer':
            payload.update(lot_id=f.lot.pk, quantity='7', location_id=f.production_location.pk,
                           code=f.code('TR'), reason='Синтетичне переміщення')
        elif action == 'quality':
            f.lot.quality = 'pending'; f.lot.save(update_fields=['quality'])
            payload.update(lot_id=f.lot.pk, result='approved', inspector_id=f.owner.pk,
                           note='Синтетичний контроль')
        elif action == 'attach':
            f.document = self.document(f, 'A')
            f.material.required_documents = ['cert']; f.material.save(update_fields=['required_documents'])
            f.lot.quality = 'pending'; f.lot.save(update_fields=['quality'])
            payload.update(lot_id=f.lot.pk, kind='cert', document_id=f.document.pk)
        elif action in ('start', 'finish'):
            self.production_material(f)
            payload.update(production_id=f.job.pk)
            if action == 'finish':
                f.job.status = 'running'; f.job.save(update_fields=['status'])
                OperatorEntry.objects.create(production=f.job, operation='Виготовлення',
                    operator=f.owner, result='done', minutes=10, defects=D('0'), note='Синтетичний факт')
                payload.update(quantity='7', code=f.code('OUT'), location_id=f.warehouse.pk, labor_cost='7.00')
        elif action == 'operator':
            f.job.status = 'running'; f.job.save(update_fields=['status'])
            payload.update(production_id=f.job.pk, operation='Виготовлення', operator_id=f.owner.pk,
                           result='done', minutes=10, defects='0', note='Синтетичний запис')
        elif action == 'ship':
            f.reservation = Reservation.objects.create(lot=f.lot, line=f.line, quantity=D('10'))
            payload.update(line_id=f.line.pk, lot_id=f.lot.pk, quantity='7', reference=f.code('SHIP'))
        elif action in ('return', 'invoice'):
            self.shipped_fixture(f)
            if action == 'return':
                payload.update(line_id=f.line.pk, lot_id=f.lot.pk, quantity='7', code=f.code('RET'),
                               location_id=f.warehouse.pk, reason='Синтетичне повернення')
            else:
                payload.update(order_id=f.order.pk, code=f.code('INV2'), due_date='2026-10-01')
        elif action == 'payment':
            f.invoice = Invoice.objects.create(code=f.code('INV'), customer=f.customer,
                amount=D('10.00'), currency=currency, due_date=date(2026, 10, 1))
            InvoiceLink.objects.create(invoice=f.invoice, order=f.order, lines=[])
            payload.update(invoice_id=f.invoice.pk, amount='7.00', reference=f.code('PAY'))
        elif action in ('change', 'apply_change'):
            f.document = self.document(f, 'B')
            if action == 'change':
                payload.update(code=f.code('ECO'), item_id=f.product.pk, document_id=f.document.pk,
                               target_revision='B', reason='Синтетична зміна')
            else:
                self.finished_history(f)
                f.change = ChangeOrder.objects.create(code=f.code('ECO'), item=f.product,
                    document=f.document, target_revision='B', reason='Синтетична зміна')
                payload.update(change_id=f.change.pk, disposition='Розглянути відкриту роботу')
        elif action == 'resolve_job':
            f.job.needs_review = True; f.job.save(update_fields=['needs_review'])
            payload.update(production_id=f.job.pk, disposition='Погоджено завершити версію A')
        elif action == 'postpone':
            payload.update(purchase_id=f.purchase.pk, due_date='2026-10-01', reason='Синтетичне перенесення')
        elif action == 'postpone_job':
            payload.update(production_id=f.job.pk, due_date='2026-10-01', reason='Синтетичне перенесення')
        elif action == 'adjust':
            payload.update(lot_id=f.lot.pk, delta='-7', reason='Синтетична інвентаризація')
        else:
            raise AssertionError('Fixture absent: ' + action)
        return f, payload

    def post(self, client, url, payload):
        return client.post(url, payload, content_type='application/json',
            HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)

    def twin_clients(self):
        clients = [Client(enforce_csrf_checks=True, raise_request_exception=False) for _ in range(2)]
        for client in clients:
            client.cookies = deepcopy(self.http.cookies)
        return clients

    def parallel(self, calls):
        barrier = threading.Barrier(2, timeout=15)
        def run(index):
            connections.close_all()
            try:
                connection.ensure_connection()
                physical_connection = id(connection.connection)
                barrier.wait()
                started = time.monotonic()
                result = calls[index]()
                ended = time.monotonic()
                return {'worker': index, 'connection': physical_connection,
                        'started': started, 'ended': ended, **result}
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, i) for i in range(2)]
            results = [future.result(timeout=45) for future in futures]
        self.assertNotEqual(results[0]['connection'], results[1]['connection'])
        self.assertLess(max(r['started'] for r in results), min(r['ended'] for r in results),
                        'The two actual operation intervals must overlap')
        return results

    def http_result(self, client, proposal_id):
        response = self.post(client, '/api/operations/confirm/',
                             {'proposal_id': str(proposal_id), 'confirmed': True})
        result = {'status': response.status_code}
        if 'application/json' in response.get('Content-Type', ''):
            result['json'] = response.json()
        else:
            result['body'] = response.content.decode(errors='replace')[:800]
        return result

    def assert_ledger(self):
        for lot in Lot.objects.all():
            total = lot.movements.aggregate(n=Sum('quantity'))['n'] or D('0')
            self.assertEqual(lot.quantity, total, lot.code)
            self.assertGreaterEqual(lot.quantity, D('0'), lot.code)
            held = service.reserved(lot)
            self.assertGreaterEqual(held, D('0'), lot.code)
            self.assertLessEqual(held, lot.quantity, lot.code)
            self.assertIn(lot.currency, CURRENCIES)
        for line in SalesLine.objects.all():
            self.assertLessEqual(D('0'), line.invoiced)
            self.assertLessEqual(line.invoiced, line.shipped)
            self.assertLessEqual(line.shipped, line.quantity)
        for invoice in Invoice.objects.all():
            self.assertLessEqual(D('0'), invoice.paid)
            self.assertLessEqual(invoice.paid, invoice.amount)
        for job in Production.objects.all():
            self.assertLessEqual(D('0'), job.produced)
            self.assertLessEqual(job.produced, job.quantity)

    def new_rows(self, model, before):
        return model.objects.exclude(pk__in=before[model])

    def oracle(self, action, f, before, result):
        """Independent amounts/counts, plus unchanged historical fields/rows."""
        after = business_state()
        expected = {**CREATED_ROWS[action], Event: 1}
        for model in BUSINESS_MODELS:
            self.assertEqual(len(after[model]) - len(before[model]), expected.get(model, 0),
                             (action, model._meta.label, 'new row count'))
            allowed = ALLOWED_EXISTING_CHANGES.get(action, {}).get(model, set())
            for pk, old in before[model].items():
                self.assertIn(pk, after[model], (action, model._meta.label, pk, 'history missing'))
                for field, value in old.items():
                    if field not in allowed:
                        self.assertEqual(after[model][pk][field], value,
                            (action, model._meta.label, pk, field, 'historical field changed'))
        event = self.new_rows(Event, before).get()
        self.assertEqual((event.action, event.role), ('erp_' + action, 'ceo'))
        self.assertEqual(event.pk, result['erp_event_id'])
        self.assert_ledger()
        f.lot.refresh_from_db(); f.line.refresh_from_db(); f.job.refresh_from_db()
        f.purchase.refresh_from_db(); f.order.refresh_from_db(); f.product.refresh_from_db()

        def lot_result(quantity, cost, quality, item, location):
            lot = self.new_rows(Lot, before).get()
            self.assertEqual(lot.pk, result['lot_id'])
            self.assertEqual((lot.quantity, lot.unit_cost, lot.currency, lot.quality,
                              lot.item_id, lot.location_id, lot.revision),
                             (D(quantity), D(cost), f.currency, quality, item.pk, location.pk, 'A'))
            return lot

        moves = list(self.new_rows(Movement, before).order_by('id'))
        if action == 'item':
            item = self.new_rows(Item, before).get()
            self.assertEqual((item.pk, item.code, item.currency, item.kind, item.method, item.revision),
                             (result['item_id'], f.code('NEW'), f.currency, 'component', 'buy', 'A'))
        elif action == 'location':
            loc = self.new_rows(Location, before).get()
            self.assertEqual((loc.pk, loc.code, loc.kind), (result['location_id'], f.code('W2'), 'warehouse'))
        elif action == 'order':
            order = self.new_rows(SalesOrder, before).get(); line = self.new_rows(SalesLine, before).get()
            self.assertEqual((order.pk, order.code, order.status, order.currency, order.customer_id, order.owner_id),
                             (result['order_id'], f.code('SO2'), 'quote', f.currency, f.customer.pk, f.owner.pk))
            self.assertEqual((line.order_id, line.item_id, line.quantity, line.price, line.shipped, line.invoiced),
                             (order.pk, f.material.pk, D('10'), D('5'), D('0'), D('0')))
        elif action == 'confirm_order':
            self.assertEqual((f.order.status, result['order_id']), ('confirmed', f.order.pk))
        elif action == 'opening':
            lot = lot_result('10', '2', 'pending', f.material, f.warehouse)
            self.assertEqual([(m.lot_id, m.kind, m.quantity, m.cost) for m in moves],
                             [(lot.pk, 'opening', D('10'), D('20'))])
        elif action == 'purchase':
            po = self.new_rows(Purchase, before).get()
            self.assertEqual((po.pk, po.quantity, po.received, po.price, po.extras, po.currency, po.status),
                             (result['purchase_id'], D('10'), D('0'), D('2'), D('10'), f.currency, 'ordered'))
        elif action == 'receive':
            lot = lot_result('7', '3', 'pending', f.material, f.warehouse)
            self.assertEqual((f.purchase.received, f.purchase.status), (D('7'), 'partial'))
            self.assertEqual([(m.lot_id, m.kind, m.quantity, m.cost, m.purchase_id) for m in moves],
                             [(lot.pk, 'receipt', D('7'), D('21'), f.purchase.pk)])
        elif action == 'job':
            job = self.new_rows(Production, before).get()
            self.assertEqual((job.pk, job.quantity, job.produced, job.planned_cost, job.actual_cost,
                              job.currency, job.status, job.revision),
                             (result['production_id'], D('10'), D('0'), D('30'), D('0'), f.currency, 'planned', 'A'))
            self.assertEqual((job.bom, job.routing), (f.product.bom, f.product.routing))
        elif action == 'reserve':
            reservation = self.new_rows(Reservation, before).get()
            self.assertEqual((reservation.pk, reservation.lot_id, reservation.quantity),
                             (result['reservation_id'], f.lot.pk, D('7')))
            self.assertIn(reservation.line_id, f.acceptable_line_ids if hasattr(f, 'acceptable_line_ids') else [f.line.pk])
            self.assertEqual((f.lot.quantity, service.free(f.lot)), (D('10'), D('3')))
        elif action == 'release':
            f.reservation.refresh_from_db()
            self.assertEqual((f.reservation.quantity, f.lot.quantity), (D('3'), D('10')))
        elif action == 'transfer':
            out = lot_result('7', '2', 'approved', f.material, f.production_location)
            self.assertEqual(f.lot.quantity, D('3'))
            self.assertEqual([(m.lot_id, m.kind, m.quantity, m.cost) for m in moves],
                [(f.lot.pk, 'transfer_out', D('-7'), D('14')), (out.pk, 'transfer_in', D('7'), D('14'))])
        elif action == 'quality':
            inspection = self.new_rows(Inspection, before).get()
            self.assertEqual((f.lot.quality, inspection.pk, inspection.lot_id, inspection.inspector_id, inspection.result),
                ('approved', result['inspection_id'], f.lot.pk, f.owner.pk, 'approved'))
            self.assertEqual(f.lot.quantity, D('10'))
        elif action == 'attach':
            self.assertEqual((f.lot.documents, f.lot.quality, f.lot.quantity),
                             ({'cert': f.document.pk}, 'pending', D('10')))
        elif action == 'start':
            self.assertEqual((f.job.status, f.job.produced, service.reserved(f.lot)), ('running', D('0'), D('10')))
        elif action == 'operator':
            entry = self.new_rows(OperatorEntry, before).get()
            self.assertEqual((entry.pk, entry.production_id, entry.operation, entry.operator_id,
                              entry.result, entry.minutes, entry.defects),
                (result['entry_id'], f.job.pk, 'Виготовлення', f.owner.pk, 'done', 10, D('0')))
        elif action == 'finish':
            out = lot_result('7', '3', 'pending', f.product, f.warehouse)
            self.assertEqual((f.lot.quantity, service.reserved(f.lot)), (D('3'), D('3')))
            self.assertEqual((f.job.produced, f.job.actual_cost, f.job.status, D(result['cost'])),
                             (D('7'), D('21'), 'running', D('21')))
            self.assertEqual([(m.lot_id, m.kind, m.quantity, m.cost, m.production_id) for m in moves],
                [(f.lot.pk, 'consume', D('-5'), D('10'), f.job.pk),
                 (f.lot.pk, 'consume', D('-2'), D('4'), f.job.pk),
                 (out.pk, 'production', D('7'), D('21'), f.job.pk)])
        elif action == 'ship':
            self.assertEqual((f.lot.quantity, service.reserved(f.lot), f.line.shipped), (D('3'), D('3'), D('7')))
            self.assertEqual([(m.lot_id, m.kind, m.quantity, m.cost, m.line_id) for m in moves],
                [(f.lot.pk, 'shipment', D('-7'), D('14'), f.line.pk)])
        elif action == 'return':
            out = lot_result('7', '2', 'blocked', f.material, f.warehouse)
            self.assertEqual((f.lot.quantity, f.line.shipped, f.line.invoiced), (D('0'), D('10'), D('0')))
            self.assertEqual([(m.lot_id, m.kind, m.quantity, m.cost, m.line_id, m.reference) for m in moves],
                [(out.pk, 'return', D('7'), D('14'), f.line.pk, f.lot.code)])
        elif action == 'invoice':
            invoice = self.new_rows(Invoice, before).get(); link = self.new_rows(InvoiceLink, before).get()
            self.assertEqual((invoice.pk, invoice.amount, invoice.paid, invoice.currency, f.line.invoiced),
                             (result['invoice_id'], D('50'), D('0'), f.currency, D('10')))
            self.assertEqual((link.invoice_id, link.order_id), (invoice.pk, f.order.pk))
            self.assertEqual(len(link.lines), 1)
            self.assertEqual((link.lines[0]['line_id'], D(link.lines[0]['quantity']), D(link.lines[0]['price'])),
                             (f.line.pk, D('10'), D('5')))
            self.assertEqual(D(result['amount']), D('50'))
        elif action == 'payment':
            f.invoice.refresh_from_db()
            self.assertEqual((f.invoice.paid, f.invoice.currency, result['invoice_id'], D(result['paid'])),
                             (D('7'), f.currency, f.invoice.pk, D('7')))
            self.assertEqual(event.payload['reference'], f.payment_reference)
        elif action == 'change':
            change = self.new_rows(ChangeOrder, before).get()
            self.assertEqual((change.pk, change.item_id, change.document_id, change.target_revision, change.status),
                             (result['change_id'], f.product.pk, f.document.pk, 'B', 'draft'))
            self.assertEqual(f.product.revision, 'A')
        elif action == 'apply_change':
            f.change.refresh_from_db(); f.done_job.refresh_from_db(); f.old_output.refresh_from_db()
            self.assertEqual((f.change.status, f.product.revision, f.product.document_id, f.job.needs_review),
                             ('approved', 'B', f.document.pk, True))
            self.assertEqual((f.done_job.needs_review, f.done_job.revision, f.old_output.revision, f.job.revision),
                             (False, 'A', 'A', 'A'))
            self.assertEqual(result['affected_jobs'], [f.job.pk])
        elif action == 'resolve_job':
            self.assertEqual((f.job.needs_review, f.job.revision), (False, 'A'))
        elif action == 'postpone':
            self.assertEqual((f.purchase.due_date, f.purchase.original_due), (date(2026, 10, 1), date(2026, 9, 20)))
        elif action == 'postpone_job':
            self.assertEqual(f.job.due_date, date(2026, 10, 1))
        elif action == 'adjust':
            self.assertEqual(f.lot.quantity, D('3'))
            self.assertEqual([(m.lot_id, m.kind, m.quantity, m.cost) for m in moves],
                             [(f.lot.pk, 'adjustment', D('-7'), D('14'))])
        return after


class ERPProposalConcurrencyTests(ERPConcurrencyBase):
    def run_http_pair(self, action, currency):
        f, payload = self.prepare(action, currency)
        if action == 'payment':
            f.payment_reference = payload['reference']
        before = business_state()
        prior_proposals = set(ActionProposal.objects.values_list('pk', flat=True))
        preview = self.post(self.http, '/api/erp/preview/', payload)
        self.assertEqual(preview.status_code, 200, ('valid fixture preview', action, currency, preview.content))
        self.assertEqual(business_state(), before, 'Actual preview must roll back every business write')
        proposal_id = preview.json()['id']
        proposal = ActionProposal.objects.exclude(pk__in=prior_proposals).get()
        self.assertEqual(str(proposal.pk), proposal_id)
        self.assertIsNone(proposal.receipt)
        self.assertEqual(proposal.user_id, self.user.pk)
        old_proposal_fields = (proposal.payload, proposal.fingerprint, proposal.expires_at,
                               proposal.user_id, proposal.role, proposal.session_key)
        clients = self.twin_clients()
        results = self.parallel([lambda c=c: self.http_result(c, proposal_id) for c in clients])
        print('A06_PAIR ' + json.dumps({'mode': 'http', 'action': action, 'currency': currency,
            'proposal_id': proposal_id, 'workers': results}, default=str, ensure_ascii=False))
        statuses = [r['status'] for r in results]
        self.assertIn(200, statuses, results)
        self.assertTrue(all(status in (200, 409) for status in statuses), results)
        success = next(r['json'] for r in results if r['status'] == 200)
        self.assertEqual(success['state'], 'succeeded')
        for r in results:
            if r['status'] == 200:
                self.assertEqual(r['json'], success, 'Concurrent receipts must be identical')
            else:
                self.assertTrue(r.get('json', {}).get('error'), r)
        after = self.oracle(action, f, before, success)
        proposal.refresh_from_db()
        self.assertEqual(proposal.receipt, success)
        self.assertEqual((proposal.payload, proposal.fingerprint, proposal.expires_at,
                          proposal.user_id, proposal.role, proposal.session_key), old_proposal_fields)
        self.assertEqual(ActionProposal.objects.count(), len(prior_proposals) + 1)
        replay = self.http_result(self.http, proposal_id)
        self.assertEqual(replay, {'status': 200, 'json': success})
        self.assertEqual(business_state(), after, 'Successful receipt replay must not change data/history')
        proposal.refresh_from_db(); self.assertEqual(proposal.receipt, success)
        print('A06_PASS ' + json.dumps({'mode': 'http', 'action': action, 'currency': currency,
            'inventory_id': 'ERP-' + action, 'erp_event_id': success['erp_event_id'],
            'statuses': statuses, 'one_effect': True, 'replay_unchanged': True}, ensure_ascii=False))


class ERPResourceConcurrencyTests(ERPConcurrencyBase):
    def run_contention(self, case, currency):
        action = 'payment' if case == 'payment_dup' else case
        f, payload = self.prepare(action, currency)
        pair = [deepcopy(payload), deepcopy(payload)]
        if case == 'reserve':
            other = SalesOrder.objects.create(code=f.code('OTHER'), customer=f.customer,
                owner=f.owner, due_date=date(2026, 9, 20), currency=currency, status='confirmed')
            line = SalesLine.objects.create(order=other, item=f.material, revision='A',
                                           quantity=D('10'), price=D('5.00'))
            pair[1]['line_id'] = line.pk
            f.acceptable_line_ids = [f.line.pk, line.pk]
        if case in ('receive', 'transfer', 'finish', 'return', 'invoice'):
            pair[0]['code'] += '-A'; pair[1]['code'] += '-B'
        if case in ('ship', 'payment'):
            pair[0]['reference'] += '-A'; pair[1]['reference'] += '-B'
        if case == 'payment_dup':
            f.invoice.amount = D('20.00'); f.invoice.save(update_fields=['amount'])
        before = business_state()
        def invoke(d):
            try:
                return {'status': 'succeeded', 'result': service.dispatch(deepcopy(d), role='ceo', log=True)}
            except (ValueError, Conflict, IntegrityError, OperationalError) as exc:
                return {'status': type(exc).__name__, 'message': str(exc)}
        results = self.parallel([lambda d=d: invoke(d) for d in pair])
        print('A06_PAIR ' + json.dumps({'mode': 'orm', 'case': case, 'currency': currency,
                                       'workers': results}, default=str, ensure_ascii=False))
        successes = [r for r in results if r['status'] == 'succeeded']
        self.assertEqual(len(successes), 1, results)
        loser = next(r for r in results if r['status'] != 'succeeded')
        self.assertIn(loser['status'], ('ValueError', 'Conflict', 'OperationalError'),
                      'Duplicate codes are not the oracle for these distinct resource attempts: ' + str(results))
        winner = successes[0]
        if action == 'payment':
            f.payment_reference = pair[winner['worker']]['reference']
        after = self.oracle(action, f, before, winner['result'])
        # Once the real concurrent transaction completes, current business state
        # must reject the other attempt; no swallowing repeated lock failures.
        with self.assertRaises(ValueError):
            service.dispatch(pair[loser['worker']], role='ceo', log=True)
        self.assertEqual(business_state(), after, 'Rejected resource retry must fully roll back')
        print('A06_PASS ' + json.dumps({'mode': 'orm', 'case': case, 'currency': currency,
            'inventory_id': 'ERP-' + action, 'erp_event_id': winner['result']['erp_event_id'],
            'one_effect': True, 'loser_retry_rejected': True}, ensure_ascii=False))


def _make_http_test(action):
    def test(self):
        for currency in (CURRENCIES if action in FINANCIAL_ACTIONS else ('EUR',)):
            with self.subTest(action=action, currency=currency):
                self.run_http_pair(action, currency)
    test.__name__ = 'test_http_pair_' + action
    test.__doc__ = 'Real concurrent confirmation/replay and exact poststate: ERP-' + action
    return test


def _make_contention_test(case):
    def test(self):
        for currency in CURRENCIES:
            with self.subTest(case=case, currency=currency):
                self.run_contention(case, currency)
    test.__name__ = 'test_orm_contention_' + case
    test.__doc__ = 'Two actual resource contenders and exact single effect: ' + case
    return test


for _action in ERP_ACTIONS:
    setattr(ERPProposalConcurrencyTests, 'test_http_pair_' + _action, _make_http_test(_action))
for _case in CONTENTION_CASES:
    setattr(ERPResourceConcurrencyTests, 'test_orm_contention_' + _case, _make_contention_test(_case))
