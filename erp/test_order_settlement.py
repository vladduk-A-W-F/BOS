"""Synthetic targeted checks of the new read projection; no route is installed here."""
import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from boss_project.identity import IdentityDenied
from boss_project.policy import Policy
from employees.models import Employee
from finance.models import Counterparty
from operations.models import Configuration, Invoice
from . import order_settlement, service
from .models import Event, InvoiceAdjustment, InvoiceLink, SalesOrder
from .order_trace import ReadStateChanged
from .payments import post_payment


@override_settings(BOS_DATA_MODE='working', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class OrderSettlementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = date(2026, 9, 20)
        cls.users = {}
        for role in ('ceo', 'manager', 'observer'):
            user = get_user_model().objects.create_user(username='settlement-' + role, password='synthetic-local-only')
            user.groups.add(Group.objects.get_or_create(name=role)[0])
            cls.users[role] = user
        cls.employee = Employee.objects.create(full_name='Settlement synthetic owner', role='Sales',
                                                phone='PRIVATE-HR-PHONE', email='PRIVATE-HR@example.invalid')
        cls.customer = Counterparty.objects.create(name='Settlement synthetic customer', type='customer')
        cls.order = SalesOrder.objects.create(code='SETTLEMENT-ORDER', customer=cls.customer, owner=cls.employee,
                                              due_date=cls.today, currency='UAH', notes='PRIVATE-ORDER-NOTES')
        cls.foreign = SalesOrder.objects.create(code='FOREIGN-ORDER', customer=cls.customer, owner=cls.employee,
                                                due_date=cls.today, currency='UAH')
        cls.invoice = Invoice.objects.create(code='SETTLEMENT-INV', customer=cls.customer, amount='100.00',
                                              paid=0, currency='UAH', due_date=cls.today)
        InvoiceLink.objects.create(order=cls.order, invoice=cls.invoice, lines=[])

    def request(self, role='ceo'):
        request = RequestFactory().get('/synthetic/order-settlement/')
        request.user = self.users[role]
        request.session = {}
        return request

    def read(self):
        return order_settlement.build(self.request(), self.order.pk)

    def pay(self, amount, reference, *, statement_writer=False):
        if statement_writer:
            return post_payment(self.invoice.pk, amount, reference, role='ceo', log=True)
        return service.dispatch({'action': 'erp_payment', 'invoice_id': self.invoice.pk,
                                 'amount': amount, 'reference': reference}, role='ceo')

    def credit(self, amount='10.00', *, reversal=None):
        event = Event.objects.create(action='erp_credit_invoice', role='ceo', payload={}, result={})
        return InvoiceAdjustment.objects.create(code='SC-' + uuid4().hex, operation_id=uuid4(),
            payload_hash='a' * 64, reason='PRIVATE-CREDIT-REASON', business_date=self.today,
            actor=self.users['ceo'], event=event, invoice=self.invoice, total=amount, currency='UAH',
            kind='reversal' if reversal else 'credit', basis='reversal' if reversal else 'commercial',
            reversed_credit=reversal, basis_snapshot={}, basis_hash='b' * 64)

    def test_partial_manual_and_statement_writer_payments_are_exact(self):
        manual = self.pay('30.00', 'MANUAL-30')
        statement = self.pay('20.00', 'STMT-' + uuid4().hex, statement_writer=True)
        data = self.read()
        self.assertEqual(data['schema'], 'bos.order-settlement.v1')
        self.assertEqual(data['totals'], [{'currency': 'UAH', 'gross_invoiced': '100.00', 'credited': '0.00',
                                         'invoiced': '100.00', 'paid': '50.00', 'open': '50.00', 'customer_credit': '0.00'}])
        history = data['invoices'][0]['payment_history']
        self.assertEqual((history['status'], history['recorded_total'], history['difference']), ('complete', '50.00', '0.00'))
        self.assertEqual([row['event_id'] for row in history['entries']], [manual['erp_event_id'], statement['erp_event_id']])
        self.assertEqual([row['amount'] for row in history['entries']], ['30.00', '20.00'])

    def test_credit_reversal_and_customer_credit_use_existing_settlement(self):
        self.pay('50.00', 'PAID-50')
        credit = self.credit()
        data = self.read()
        self.assertEqual((data['totals'][0]['invoiced'], data['totals'][0]['open']), ('90.00', '40.00'))
        reversal = self.credit(reversal=credit)
        data = self.read()
        self.assertEqual((data['totals'][0]['credited'], data['totals'][0]['open']), ('0.00', '50.00'))
        self.assertEqual([(x['adjustment_id'], x['active'], x['reversed_credit_id']) for x in data['invoices'][0]['adjustments']],
                         [(credit.pk, False, None), (reversal.pk, False, credit.pk)])
        self.credit('60.25')
        data = self.read()
        self.assertEqual((data['totals'][0]['open'], data['totals'][0]['customer_credit']), ('0.00', '10.25'))

    def test_exact_raw_payment_references_and_confirm_replay(self):
        self.client.force_login(self.users['ceo'])
        references = ('REF', ' REF ', ' ' + 'R' * 60 + ' ')
        for reference in references:
            preview = self.client.post('/api/erp/preview/', {'action': 'erp_payment',
                'invoice_id': self.invoice.pk, 'amount': '10.00', 'reference': reference},
                content_type='application/json')
            self.assertEqual(preview.status_code, 200, preview.content)
            confirmation = {'proposal_id': preview.json()['id'], 'confirmed': True}
            first = self.client.post('/api/operations/confirm/', confirmation, content_type='application/json')
            self.assertEqual(first.status_code, 200, first.content)
            replay = self.client.post('/api/operations/confirm/', confirmation, content_type='application/json')
            self.assertEqual(replay.status_code, 200, replay.content)
            self.assertEqual(first.json(), replay.json())
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid, Decimal('30.00'))
        history = self.read()['invoices'][0]['payment_history']
        self.assertEqual([entry['reference'] for entry in history['entries']], list(references))
        self.assertEqual((history['status'], history['recorded_total'], history['difference']),
                         ('complete', '30.00', '0.00'))
        self.assertEqual(Event.objects.filter(action='erp_payment').count(), 3)

    def test_currencies_are_separate_without_conversion(self):
        for currency, amount in (('EUR', '20.01'), ('USD', '31.29')):
            invoice = Invoice.objects.create(code='S-' + currency, customer=self.customer,
                                              amount=amount, currency=currency, due_date=self.today)
            InvoiceLink.objects.create(order=self.order, invoice=invoice, lines=[])
        data = self.read()
        self.assertEqual({row['currency']: row['open'] for row in data['totals']},
                         {'UAH': '100.00', 'EUR': '20.01', 'USD': '31.29'})

    def test_unrelated_global_events_do_not_hide_payments_or_leak_sources(self):
        own = self.pay('30.00', 'OWN-PAYMENT')
        foreign = Invoice.objects.create(code='FOREIGN-INVOICE', customer=self.customer, amount='987654.32',
                                          currency='EUR', due_date=self.today)
        InvoiceLink.objects.create(order=self.foreign, invoice=foreign, lines=[])
        Event.objects.bulk_create([Event(action='erp_payment', role='ceo',
            payload={'invoice_id': foreign.pk, 'amount': '45678.91', 'reference': 'FOREIGN-PAYMENT'},
            result={'private': 'PRIVATE-HR-PHONE'}) for _ in range(201)])
        Event.objects.filter(pk=own['erp_event_id']).update(result={'private': 'PRIVATE-RESULT'})
        data = self.read()
        self.assertEqual([entry['event_id'] for entry in data['invoices'][0]['payment_history']['entries']], [own['erp_event_id']])
        text = json.dumps(data)
        for canary in ('FOREIGN-', '987654.32', '45678.91', 'PRIVATE-', 'payload', 'result', 'reason', 'customer_id', 'owner_id'):
            self.assertNotIn(canary, text)

    def test_missing_legacy_history_is_explicit_without_fabricated_payments(self):
        Invoice.objects.filter(pk=self.invoice.pk).update(paid='50.00')
        data = self.read()
        history = data['invoices'][0]['payment_history']
        self.assertEqual((history['status'], history['recorded_total'], history['difference']), ('missing', '0.00', '50.00'))
        self.assertEqual(history['entries'], [])
        self.assertEqual(history['issues'], ['missing_history', 'sum_mismatch'])
        self.assertEqual(data['totals'][0]['open'], '50.00')
        self.assertEqual(data['payment_history_status'], 'incomplete')

    def test_invalid_legacy_events_do_not_become_valid_rounded_money(self):
        for index, value in enumerate(('NaN', 'Infinity', '-1.00', '1.001', True, {'amount': '5.00'})):
            Event.objects.create(action='erp_payment', role='ceo',
                payload={'invoice_id': self.invoice.pk, 'amount': value, 'reference': 'BAD-' + str(index)}, result={})
        Event.objects.create(action='erp_payment', role='ceo',
            payload={'invoice_id': str(self.invoice.pk), 'amount': '7.00', 'reference': 'STRING-ID'}, result={})
        data = self.read()
        history = data['invoices'][0]['payment_history']
        self.assertEqual(history['status'], 'inconsistent')
        self.assertEqual(history['recorded_total'], '0.00')
        self.assertEqual(len(history['entries']), 7)
        self.assertTrue(all(row['issues'] for row in history['entries']))
        self.assertEqual(history['entries'][-1]['issues'], ['invalid_invoice_id'])

    def test_legacy_duplicate_reference_and_sum_mismatch_are_explicit(self):
        self.pay('30.00', 'SAME-REFERENCE')
        Event.objects.create(action='erp_payment', role='ceo',
            payload={'invoice_id': self.invoice.pk, 'amount': '20.00', 'reference': 'SAME-REFERENCE'}, result={})
        Invoice.objects.filter(pk=self.invoice.pk).update(paid='50.00')
        history = self.read()['invoices'][0]['payment_history']
        self.assertEqual(history['issues'], ['invalid_history', 'sum_mismatch'])
        self.assertEqual(history['entries'][-1]['issues'], ['duplicate_reference'])
        self.assertEqual(history['difference'], '20.00')

    def test_payment_cap_keeps_full_reconciliation(self):
        Invoice.objects.filter(pk=self.invoice.pk).update(paid='1.05')
        Event.objects.bulk_create([Event(action='erp_payment', role='ceo',
            payload={'invoice_id': self.invoice.pk, 'amount': '0.01', 'reference': 'CAP-' + str(i)}, result={}) for i in range(105)])
        data = self.read()
        history = data['invoices'][0]['payment_history']
        self.assertEqual((len(history['entries']), history['has_more'], history['recorded_total'], history['status']),
                         (100, True, '1.05', 'complete'))
        self.assertEqual(data['totals'][0]['open'], '98.95')
        self.assertEqual(data['completeness'], 'partial')

    def test_invoice_cap_keeps_totals_across_all_rows(self):
        for index in range(100):
            invoice = Invoice.objects.create(code='CAP-INV-' + str(index), customer=self.customer, amount='0.01',
                                              currency='UAH', due_date=self.today)
            InvoiceLink.objects.create(order=self.order, invoice=invoice, lines=[])
        data = self.read()
        self.assertEqual(len(data['invoices']), 100)
        self.assertTrue(data['limits']['has_more']['invoices'])
        self.assertEqual(data['totals'][0]['gross_invoiced'], '101.00')
        self.assertEqual(data['totals'][0]['open'], '101.00')

    def test_adjustment_cap_keeps_all_active_credits(self):
        for _ in range(101):
            self.credit('0.01')
        data = self.read()
        self.assertEqual(len(data['invoices'][0]['adjustments']), 100)
        self.assertTrue(data['invoices'][0]['has_more']['adjustments'])
        self.assertEqual(data['totals'][0]['credited'], '1.01')
        self.assertEqual(data['totals'][0]['open'], '98.99')

    def test_roles_are_denied_before_any_order_or_financial_read(self):
        for role in ('manager', 'observer'):
            with self.subTest(role=role), CaptureQueriesContext(connection) as queries:
                with patch.object(order_settlement, 'collect', side_effect=AssertionError('finance queried')):
                    with self.assertRaises(PermissionError):
                        order_settlement.build(self.request(role), self.order.pk)
            for query in queries:
                self.assertNotIn('"erp_salesorder"', query['sql'])
                self.assertNotIn('"operations_invoice"', query['sql'])
                self.assertNotIn('"erp_event"', query['sql'])
        request = self.request()
        request.user = AnonymousUser()
        with self.assertRaises(IdentityDenied):
            order_settlement.build(request, self.order.pk)

    def test_policy_admission_of_order_and_linked_invoice_is_required(self):
        self.pay('30.00', 'POLICY-PAYMENT')
        self.credit('10.00')
        original = Policy.queryset
        for target in (SalesOrder, InvoiceLink, Invoice, InvoiceAdjustment, Event):
            def restrict(policy, model):
                return model.objects.none() if model is target else original(policy, model)
            with self.subTest(model=target), patch.object(Policy, 'queryset', restrict):
                if target is SalesOrder:
                    with self.assertRaises(SalesOrder.DoesNotExist):
                        self.read()
                elif target is Event:
                    # Even a future event-specific policy cannot disclose a source.
                    data = self.read()
                    history = data['invoices'][0]['payment_history']
                    self.assertEqual(history['entries'], [])
                    self.assertEqual((history['status'], history['difference']), ('missing', '30.00'))
                    self.assertNotIn('POLICY-PAYMENT', json.dumps(data))
                else:
                    with self.assertRaises(PermissionError):
                        self.read()

    def assert_changed(self, mutation, *, after_read=1):
        original, count = order_settlement.collect, []
        def collect(*args, **kwargs):
            result = original(*args, **kwargs)
            count.append(True)
            if len(count) == after_read:
                mutation()
            return result
        with patch.object(order_settlement, 'collect', side_effect=collect):
            with self.assertRaises(ReadStateChanged) as error:
                self.read()
        self.assertEqual(str(error.exception), '')
        self.assertLessEqual(len(count), 2, 'A stale read must not automatically retry')

    def test_financial_and_payment_source_changes_conflict(self):
        self.assert_changed(lambda: Invoice.objects.filter(pk=self.invoice.pk).update(paid='1.00'))
        event = Event.objects.create(action='erp_payment', role='ceo',
            payload={'invoice_id': self.invoice.pk, 'amount': '1.00', 'reference': 'FIRST'}, result={})
        self.assert_changed(lambda: Event.objects.filter(pk=event.pk).update(
            payload={'invoice_id': self.invoice.pk, 'amount': '1.00', 'reference': 'CHANGED'}))

    def test_membership_and_credit_reversal_changes_conflict(self):
        credit = self.credit()
        self.assert_changed(lambda: self.credit(reversal=credit))
        self.assert_changed(lambda: InvoiceLink.objects.filter(invoice=self.invoice).update(order=self.foreign))

    def test_access_changes_between_and_after_reads_conflict(self):
        observer = Group.objects.get(name='observer')
        self.assert_changed(lambda: self.users['ceo'].groups.set([observer]))
        self.users['ceo'].groups.set([Group.objects.get(name='ceo')])
        self.assert_changed(lambda: self.users['ceo'].groups.set([observer]), after_read=2)

    def test_existing_access_revision_and_write_revision_fail_closed(self):
        request = self.request()
        request.bos_access_revision = 'old-access'
        with patch.object(order_settlement, 'collect', side_effect=AssertionError('must not collect')):
            with self.assertRaises(ReadStateChanged):
                order_settlement.build(request, self.order.pk)
        self.assert_changed(lambda: Configuration.objects.create(key='erp_write', value={'sequence': 99}))

    def test_reads_have_no_write_or_global_snapshot_side_effects(self):
        with CaptureQueriesContext(connection) as queries:
            with (patch('erp.queries.snapshot', side_effect=AssertionError('global snapshot')),
                  patch('erp.service.fingerprint', side_effect=AssertionError('global fingerprint'))):
                data = self.read()
        self.assertEqual(data['completeness'], 'complete')
        for query in queries:
            self.assertFalse(query['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ')), query['sql'])
        self.assertFalse(Configuration.objects.filter(key='erp_write').exists())

    def test_empty_and_missing_orders(self):
        empty = order_settlement.build(self.request(), self.foreign.pk)
        self.assertEqual((empty['totals'], empty['invoices'], empty['completeness']), ([], [], 'complete'))
        with self.assertRaises(SalesOrder.DoesNotExist):
            order_settlement.build(self.request(), 999999)
