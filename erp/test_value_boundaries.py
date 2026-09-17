"""A07 bounded writer regressions. Run only on a NEW verification database.

No monkeypatches, bypassed authentication, model substitution or installation DB
reads. ERPConcurrencyBase has no test methods; importing it does not inherit the
37 A06 cases. All mutations under test use the real dispatch or HTTP adapters.

Negative probes observe the complete physical business state BEFORE harness
cleanup. A test-owned outer transaction then removes unexpected accepted rows,
so one old SQLite overflow cannot poison later fixture reads. That cleanup is
never credited as a product rollback. Raw SELECT snapshots deliberately avoid
DecimalField conversion hiding an out-of-range SQLite value.
"""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal as D
import hashlib
import json
import re

from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from erp import service
from erp.models import Item, Location, Lot, SalesLine, Movement, InvoiceLink, Event
from erp.test_concurrency import (
    ERPConcurrencyBase as _FixtureBase, BUSINESS_MODELS, business_state,
)
from finance.commands import save_transaction
from finance.models import FinancialIntent, Transaction
from operations.models import ActionProposal, Document, Invoice


CURRENCIES = ('EUR', 'USD', 'UAH')
COVERAGE_MANIFEST = {
    'L01': {'fields': ['operations.Invoice.code'], 'limits': [30, 31],
            'inventory': ['ERP-invoice', 'CORE-dispatch', 'CORE-erp-preview', 'CORE-confirm']},
    'L02': {'fields': ['erp.Item.revision', 'erp.Lot.revision'], 'limits': [40, 41],
            'inventory': ['ERP-item', 'ERP-opening', 'CORE-dispatch', 'CORE-confirm']},
    'L03': {'fields': ['erp.Location.name', 'erp.Item.material'], 'limits': [200, 201],
            'inventory': ['ERP-location', 'ERP-item', 'CORE-dispatch', 'CORE-confirm']},
    'L04': {'fields': ['erp.Item.material', 'erp.Location.name', 'erp.Item.external_codes',
                       'erp.Item.routing', 'operations.Document.content'],
            'inventory': ['ERP-item', 'ERP-location', 'CORE-dispatch', 'CORE-erp-preview'],
            'rule': 'NUL/unpaired surrogate rejected before business SQL writes; bytes unchanged'},
    'N01': {'fields': ['erp.Lot.quantity', 'erp.Lot.unit_cost', 'operations.Invoice.paid'],
            'inventory': ['ERP-opening', 'ERP-payment', 'CORE-dispatch', 'CORE-confirm'],
            'rule': '3 quantity / 2 money decimals; finite; no silent precision loss'},
    'N02': {'fields': ['operations.Invoice.amount', 'erp.SalesLine.invoiced'],
            'inventory': ['ERP-invoice', 'CORE-dispatch', 'CORE-erp-preview', 'CORE-confirm'],
            'limits': ['999999999999.99', '1000000000000.00']},
}


def physical_state():
    """Exact read-only snapshot, including failed/old receipt claims and bytes."""
    state = {}
    with connection.cursor() as cursor:
        for model in (*BUSINESS_MODELS, ActionProposal, FinancialIntent):
            table = connection.ops.quote_name(model._meta.db_table)
            pk = connection.ops.quote_name(model._meta.pk.column)
            cursor.execute(f'SELECT * FROM {table} ORDER BY {pk}')
            state[model._meta.label] = tuple(
                tuple(bytes(v) if isinstance(v, memoryview) else deepcopy(v) for v in row)
                for row in cursor.fetchall())
    return state


class A07BoundaryTests(_FixtureBase):
    maxDiff = 1800

    def post_json(self, url, payload):
        # Escaped transport can represent an invalid surrogate without the test
        # client itself rejecting it before the real application receives it.
        return self.http.post(url, json.dumps(payload, ensure_ascii=True),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=self.http.cookies[settings.CSRF_COOKIE_NAME].value)

    def assert_same_physical(self, before, after, message):
        changed = [key for key in before if before[key] != after.get(key)]
        self.assertEqual(changed, [], message + ': ' + ', '.join(changed))

    def reject(self, payload, label, *, before_sql=False, adapters=('dispatch', 'preview', 'confirm')):
        """One logical invalid command, independently retried through each writer."""
        for adapter in adapters:
            with self.subTest(boundary=label, adapter=adapter):
                with transaction.atomic():
                    try:
                        proposal = None
                        if adapter == 'confirm':
                            # A pending proposal persisted before the new validator.
                            # JSONB cannot store NUL/unpaired surrogates at all, so
                            # those particular probes use dispatch/preview only.
                            proposal = ActionProposal.objects.create(
                                session_key=self.http.session.session_key,
                                user=self.user, role='ceo', payload=deepcopy(payload),
                                fingerprint=service.fingerprint(),
                                expires_at=timezone.now() + timedelta(minutes=10))
                        before = physical_state()
                        attempted_writes = []
                        tables = {model._meta.db_table for model in BUSINESS_MODELS}

                        def observe(execute, sql, params, many, context):
                            # Transparent instrumentation: executes the original
                            # SQL once with its original parameters and connection.
                            match = re.match(r'\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+["`]?([\w]+)', sql, re.I)
                            if match and match.group(1) in tables:
                                attempted_writes.append((match.group(1), sql.split()[0].upper()))
                            return execute(sql, params, many, context)

                        error = None
                        response = None
                        with connection.execute_wrapper(observe):
                            try:
                                if adapter == 'dispatch':
                                    service.dispatch(deepcopy(payload), role='ceo')
                                elif adapter == 'preview':
                                    response = self.post_json('/api/erp/preview/', payload)
                                else:
                                    response = self.post_json('/api/operations/confirm/', {
                                        'proposal_id': str(proposal.pk), 'confirmed': True})
                            except Exception as exc:
                                error = exc
                        after = physical_state()  # Before any test-owned cleanup.
                        changed = [key for key in before if before[key] != after[key]]
                        print('A07_OBSERVED ' + json.dumps({
                            'boundary': label, 'adapter': adapter,
                            'status': response.status_code if response is not None else None,
                            'exception': type(error).__name__ if error else None,
                            'changed_tables': changed, 'business_sql_writes': attempted_writes,
                        }, ensure_ascii=True))
                        with self.subTest(check='explicit_validation_refusal'):
                            if adapter == 'dispatch':
                                self.assertIsInstance(error, (ValueError, ValidationError),
                                    'Expected domain validation before persistence; got ' + repr(error))
                            else:
                                self.assertIsNone(error, repr(error))
                                self.assertEqual(response.status_code, 422, response.content[:700])
                                self.assertTrue(response.json().get('error'))
                        with self.subTest(check='exact_zero_effect_before_harness_cleanup'):
                            self.assert_same_physical(before, after, 'Refused command changed sources/history/receipt')
                        if before_sql:
                            with self.subTest(check='reject_before_business_sql'):
                                self.assertEqual(attempted_writes, [],
                                    'Invalid Unicode must not reach a business INSERT/UPDATE/DELETE')
                    finally:
                        transaction.set_rollback(True)

    def accepted(self, f, payload):
        before = business_state()
        proposals_before = {p.pk: (p.payload, p.receipt) for p in ActionProposal.objects.all()}
        preview = self.post_json('/api/erp/preview/', payload)
        self.assertEqual(preview.status_code, 200, ('Positive boundary preview', preview.content[:800]))
        self.assertEqual(business_state(), before, 'Preview changed business records')
        proposal = ActionProposal.objects.exclude(pk__in=proposals_before).get()
        self.assertEqual(str(proposal.pk), preview.json()['id'])
        self.assertEqual(proposal.user_id, self.user.pk)
        self.assertEqual(proposal.role, 'ceo')
        self.assertIsNone(proposal.receipt)
        response = self.post_json('/api/operations/confirm/', {
            'proposal_id': str(proposal.pk), 'confirmed': True})
        self.assertEqual(response.status_code, 200, ('Positive boundary confirm', response.content[:800]))
        receipt = response.json()
        self.assertEqual(receipt['state'], 'succeeded')
        after = business_state()
        action = payload['action']
        expected_new = {Event: 1}
        permitted = {}
        if action == 'erp_item':
            expected_new[Item] = 1
            obj = Item.objects.get(pk=receipt['item_id'])
            for field in ('code', 'revision', 'material', 'external_codes', 'routing'):
                if field in payload:
                    self.assertEqual(getattr(obj, field), payload[field])
        elif action == 'erp_location':
            expected_new[Location] = 1
            obj = Location.objects.get(pk=receipt['location_id'])
            self.assertEqual((obj.code, obj.name), (payload['code'], payload['name']))
        elif action == 'erp_opening':
            expected_new.update({Lot: 1, Movement: 1})
            obj = Lot.objects.get(pk=receipt['lot_id'])
            self.assertEqual((obj.code, obj.revision, obj.currency),
                             (payload['code'], payload['revision'], payload['currency']))
            self.assertEqual((obj.quantity, obj.unit_cost), (D(payload['quantity']), D(payload['unit_cost'])))
            movement = obj.movements.get()
            self.assertEqual((movement.quantity, movement.cost),
                (D(payload['quantity']), (D(payload['quantity']) * D(payload['unit_cost'])).quantize(D('.01'))))
        elif action == 'erp_invoice':
            expected_new.update({Invoice: 1, InvoiceLink: 1})
            obj = Invoice.objects.get(pk=receipt['invoice_id'])
            expected = D('0')
            expected_links = []
            for pk, old in before[SalesLine].items():
                if old['order_id'] != payload['order_id']:
                    continue
                remaining = old['shipped'] - old['invoiced']
                if remaining:
                    expected += remaining * old['price']
                    expected_links.append({'line_id': pk, 'quantity': str(remaining), 'price': str(old['price'])})
                    permitted[(SalesLine, pk)] = {'invoiced'}
                    self.assertEqual(after[SalesLine][pk]['invoiced'], old['shipped'])
            self.assertEqual((obj.code, obj.amount, obj.paid, obj.currency),
                (payload['code'], expected.quantize(D('.01')), D('0'), f.currency))
            link = InvoiceLink.objects.get(invoice=obj)
            self.assertEqual(link.order_id, payload['order_id'])
            self.assertEqual(sorted(link.lines, key=lambda x: x['line_id']),
                             sorted(expected_links, key=lambda x: x['line_id']))
        elif action == 'erp_payment':
            obj = Invoice.objects.get(pk=payload['invoice_id'])
            permitted[(Invoice, obj.pk)] = {'paid'}
            self.assertEqual(obj.paid, before[Invoice][obj.pk]['paid'] + D(payload['amount']))
            self.assertEqual(obj.currency, f.currency)
        else:
            raise AssertionError('Unexpected boundary action: ' + action)
        for model, old_rows in before.items():
            self.assertEqual(set(old_rows) - set(after[model]), set(), model.__name__ + ' lost a historical ID')
            self.assertEqual(len(set(after[model]) - set(old_rows)), expected_new.get(model, 0), model.__name__)
            for pk, old in old_rows.items():
                excluded = permitted.get((model, pk), set())
                self.assertEqual({k: v for k, v in after[model][pk].items() if k not in excluded},
                                 {k: v for k, v in old.items() if k not in excluded}, (model.__name__, pk))
        self.assertEqual(Event.objects.get(pk=receipt['erp_event_id']).action, action)
        proposal.refresh_from_db()
        self.assertEqual(proposal.receipt, receipt)
        self.assertEqual(ActionProposal.objects.count(), len(proposals_before) + 1)
        for old in ActionProposal.objects.filter(pk__in=proposals_before):
            self.assertEqual((old.payload, old.receipt), proposals_before[old.pk])
        stable = physical_state()
        replay = self.post_json('/api/operations/confirm/', {
            'proposal_id': str(proposal.pk), 'confirmed': True})
        self.assertEqual(replay.status_code, 200, replay.content[:800])
        self.assertEqual(replay.json(), receipt)
        self.assert_same_physical(stable, physical_state(), 'Receipt replay changed history')
        self.assert_ledger()
        return obj

    def big_invoice(self, currency, *, exact_max=False):
        f, payload = self.prepare('invoice', currency)
        q = D('999999.999') if exact_max else D('1000000')
        f.line.quantity = q
        f.line.shipped = q
        f.line.price = D('1000000.00')
        f.line.save(update_fields=['quantity', 'shipped', 'price'])
        # Reconcile the synthetic setup's existing movements, before the probe.
        Movement.objects.filter(lot=f.lot, kind='opening').update(quantity=q, cost=q * 2)
        Movement.objects.filter(lot=f.lot, kind='shipment').update(quantity=-q, cost=q * 2)
        if exact_max:
            second = SalesLine.objects.create(order=f.order, item=f.material, revision='A',
                quantity=D('1'), shipped=D('1'), price=D('999.99'))
            lot = Lot.objects.create(code=f.code('SECOND'), item=f.material, location=f.warehouse,
                quantity=D('0'), revision='A', quality='approved', unit_cost=D('2'), currency=currency)
            Movement.objects.create(lot=lot, quantity=D('1'), kind='opening', reference=lot.code, cost=D('2'))
            Movement.objects.create(lot=lot, quantity=D('-1'), kind='shipment', reference=lot.code,
                                    cost=D('2'), line=second)
        self.assert_ledger()
        return f, payload

    def test_l01_invoice_code_30_ascii_and_unicode_round_trip(self):
        for currency in CURRENCIES:
            for char in ('A', 'Ї', '🙂'):
                with self.subTest(currency=currency, char=char):
                    f, payload = self.prepare('invoice', currency)
                    payload['code'] = currency + char * 27
                    self.assertEqual(len(payload['code']), 30)
                    self.accepted(f, payload)

    def test_l01_invoice_code_31_refused_without_truncation_or_trim(self):
        for currency in CURRENCIES:
            for value in ('A' * 31, 'Ї' * 31, '🙂' * 31, 'A' * 30 + ' '):
                f, payload = self.prepare('invoice', currency)
                payload['code'] = value
                self.reject(payload, 'L01/code31/' + currency + '/' + repr(value))

    def test_l02_item_revision_40_accepted_41_refused(self):
        f, payload = self.prepare('item', 'EUR')
        payload['revision'] = 'Ї' * 40
        self.accepted(f, payload)
        f, payload = self.prepare('item', 'EUR')
        payload['revision'] = 'Ї' * 41
        self.reject(payload, 'L02/Item.revision/41')

    def test_l02_opening_revision_40_accepted_41_refused(self):
        for currency in CURRENCIES:
            f, payload = self.prepare('opening', currency)
            payload['revision'] = 'Ї' * 40
            self.accepted(f, payload)
            f, payload = self.prepare('opening', currency)
            payload['revision'] = 'Ї' * 41
            self.reject(payload, 'L02/Lot.revision/41/' + currency)

    def test_l03_location_name_200_accepted_201_refused(self):
        f, payload = self.prepare('location', 'EUR')
        payload['name'] = 'С' * 200
        self.accepted(f, payload)
        f, payload = self.prepare('location', 'EUR')
        payload['name'] = 'С' * 201
        self.reject(payload, 'L03/Location.name/201')

    def test_l03_item_material_200_accepted_201_refused(self):
        f, payload = self.prepare('item', 'EUR')
        payload['material'] = 'Т' * 200
        self.accepted(f, payload)
        f, payload = self.prepare('item', 'EUR')
        payload['material'] = 'Т' * 201
        self.reject(payload, 'L03/Item.material/201')

    def test_n02_computed_invoice_10_power_12_refuses_no_partial_invoiced(self):
        for currency in CURRENCIES:
            f, payload = self.big_invoice(currency)
            self.reject(payload, 'N02/Invoice.amount/1000000000000.00/' + currency)
            f.line.refresh_from_db()
            self.assertEqual(f.line.invoiced, D('0'))
            self.assertFalse(Invoice.objects.filter(code=payload['code']).exists())
            self.assert_ledger()

    def test_n02_computed_invoice_exact_max_round_trips(self):
        for currency in CURRENCIES:
            with self.subTest(currency=currency):
                f, payload = self.big_invoice(currency, exact_max=True)
                invoice = self.accepted(f, payload)
                self.assertEqual(invoice.amount, D('999999999999.99'))

    def test_n01_quantity_three_decimals_accepted_four_refused(self):
        for currency in CURRENCIES:
            f, payload = self.prepare('opening', currency)
            payload['quantity'] = '0.001'
            self.accepted(f, payload)
            f, payload = self.prepare('opening', currency)
            payload['quantity'] = '0.0001'
            self.reject(payload, 'N01/Lot.quantity/scale4/' + currency)

    def test_n01_money_two_decimals_accepted_three_refused(self):
        for currency in CURRENCIES:
            for action, field in (('opening', 'unit_cost'), ('payment', 'amount')):
                f, payload = self.prepare(action, currency)
                payload[field] = '0.01'
                self.accepted(f, payload)
                f, payload = self.prepare(action, currency)
                payload[field] = '0.001'
                self.reject(payload, 'N01/' + field + '/scale3/' + currency)

    def test_n01_nonfinite_quantities_costs_and_payments_refused(self):
        for currency in CURRENCIES:
            for action, field in (('opening', 'quantity'), ('opening', 'unit_cost'), ('payment', 'amount')):
                f, original = self.prepare(action, currency)
                for value in ('NaN', 'sNaN', 'Infinity', '-Infinity'):
                    payload = {**original, field: value}
                    self.reject(payload, 'N01/' + field + '/' + value + '/' + currency)

    def test_l04_scalar_nul_and_unpaired_surrogate_rejected_before_sql(self):
        for action, field in (('location', 'name'), ('item', 'material')):
            f, original = self.prepare(action, 'EUR')
            for value in ('До\x00після', 'До\ud800після', 'До\udfffпісля'):
                self.reject({**original, field: value}, 'L04/scalar/' + field + '/' + repr(value),
                            before_sql=True, adapters=('dispatch', 'preview'))

    def test_l04_nested_json_nul_and_unpaired_surrogate_rejected_before_sql(self):
        f, original = self.prepare('item', 'EUR')
        for value in ('До\x00після', 'До\ud800після', 'До\udfffпісля'):
            variants = (
                {'external_codes': {'джерело': [{'вкладений': value}]}},
                {'external_codes': {'джерело': {value: 'значення'}}},
                {'routing': [{'name': 'Виготовлення', 'instruction': value, 'days': 1}]},
            )
            for i, change in enumerate(variants):
                self.reject({**original, **change}, 'L04/nested/' + str(i) + '/' + repr(value),
                            before_sql=True, adapters=('dispatch', 'preview'))

    def test_l04_valid_unicode_json_and_binary_bytes_preserved(self):
        f, payload = self.prepare('item', 'EUR')
        payload['material'] = 'Сталь ЇЄҐ 🙂'
        payload['external_codes'] = {'джерело': [{'номер': 'К-001', 'примітка': 'ЇЄҐ🙂',
            'число': 7, 'сума': '0.01', 'активний': True, 'відсутній': None}]}
        payload['routing'] = [{'name': 'Виготовлення', 'instruction': 'Перевірити ЇЄҐ 🙂', 'days': 1}]
        content = bytes(range(256)) + b'\x00\xff\xfe\xed\xa0\x80'
        document = Document.objects.create(code=f.code('BIN'), revision='A',
            title='Синтетичні довільні байти', filename='a07_bytes.bin', content=content,
            text='Цей текст не є заміною binary-вмісту.', checksum=hashlib.sha256(content).hexdigest(),
            status='approved')
        original_document = Document.objects.values().get(pk=document.pk)
        self.accepted(f, payload)
        self.assertEqual(Document.objects.values().get(pk=document.pk), original_document)
        document.refresh_from_db()
        self.assertEqual(bytes(document.content), content)
        self.assertEqual(hashlib.sha256(bytes(document.content)).hexdigest(), original_document['checksum'])
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='operations',
            content_type__model='document', codename='download_document'))
        stable = physical_state()
        response = self.http.get(f'/api/operations/documents/{document.pk}/download/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), content)
        self.assert_same_physical(stable, physical_state(), 'Download changed binary/history')

    def test_l04_shared_financial_command_nul_refused_without_row_audit_or_intent(self):
        for currency in CURRENCIES:
            good = dict(direction='out', amount=D('10.01'), currency=currency,
                date='2026-09-11', description='Синтетична оплата ЇЄҐ 🙂', category='other')
            tx = save_transaction(changes=good, actor=self.user, operation_id='a07-good-' + currency)
            self.assertEqual((tx.amount, tx.currency, tx.description),
                             (D('10.01'), currency, good['description']))
            self.assertEqual(FinancialIntent.objects.filter(transaction_id=tx.pk).count(), 1)
            for value in ('До\x00після', 'До\ud800після'):
                with self.subTest(currency=currency, description=repr(value)):
                    with transaction.atomic():
                        try:
                            before = physical_state()
                            error = None
                            try:
                                save_transaction(changes={**good, 'description': value}, actor=self.user,
                                                 operation_id='a07-invalid-' + currency)
                            except Exception as exc:
                                error = exc
                            after = physical_state()
                            print('A07_FINANCE_OBSERVED ' + json.dumps({
                                'currency': currency, 'description': repr(value),
                                'exception': type(error).__name__ if error else None,
                                'changed_tables': [key for key in before if before[key] != after[key]],
                            }))
                            with self.subTest(check='ValidationError'):
                                self.assertIsInstance(error, ValidationError)
                            with self.subTest(check='exact_zero_effect_before_harness_cleanup'):
                                self.assert_same_physical(before, after, 'Invalid finance text changed sources/audit/intent')
                        finally:
                            transaction.set_rollback(True)
