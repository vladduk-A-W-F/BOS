"""BATCH-02: isolated HTTP trace facts, field boundaries and read conflicts."""
import json
import time
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from erp import balances
from erp.models import (Event, InvoiceLink, Lot, Movement, OrderCancellation,
                        Production, Reservation, SalesLine)
from operations.models import AuditEvent, Configuration, Invoice
from operations.test_access import A04SyntheticCase as _SyntheticCase, nested_keys
from tasks.models import Task


class OrderTraceTests(_SyntheticCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.line.quantity = Decimal('10.000')
        cls.line.shipped = Decimal('2.000')
        cls.line.invoiced = Decimal('0')
        cls.line.save()
        cls.shipment = Movement.objects.get(line=cls.line, kind='shipment')
        cls.shipment.quantity = Decimal('-2.000')
        cls.shipment.save()
        cls.reservation = Reservation.objects.create(lot=cls.lot, line=cls.line, quantity='3.125')
        cls.receipt = Movement.objects.create(lot=cls.lot, kind='receipt', purchase=cls.purchase,
            quantity='9', reference='TRACE-RECEIPT')
        cls.job = Production.objects.create(code='TRACE-JOB', line=cls.line, item=cls.item,
            quantity='2', revision='A', location=cls.location, owner=cls.employee, due_date=cls.today)
        cls.task.sales_order = cls.order
        cls.task.assignee_employee = cls.employee
        cls.task.save()

    @property
    def url(self):
        return f'/api/erp/orders/{self.order.pk}/trace/'

    def get_trace(self, role='ceo'):
        return self.json_get(self.grant(role, 'view_document'), self.url)

    def cancellation(self, quantity='2.000'):
        self.grant('ceo')
        event = Event.objects.create(action='erp_cancel_order', role='ceo', payload={}, result={})
        return OrderCancellation.objects.create(line=self.line, quantity=quantity,
            operation_id=uuid4(), payload_hash='a'*64, code='TRACE-CANCEL', reason='PRIVATE REASON',
            business_date=self.today, actor=self.users['ceo'], event=event,
            before_snapshot={}, after_snapshot={})

    def hidden_reservation(self):
        lot = Lot.objects.create(code='TRACE-HIDDEN-LOT', item=self.item, location=self.location,
            revision='A', quantity='2', quality='approved', documents={'certificate': self.hidden_doc.pk})
        return Reservation.objects.create(lot=lot, line=self.line, quantity='1.875')

    def test_trace_decimal_sources_and_read_only(self):
        cancellation = self.cancellation()
        client = self.grant('ceo', 'view_document')
        before = list(Configuration.objects.order_by('pk').values())
        with CaptureQueriesContext(connection) as queries:
            start = time.monotonic()
            data = self.json_get(client, self.url)
            elapsed = time.monotonic() - start
        captured_queries = list(queries.captured_queries)
        line = data['lines'][0]
        self.assertEqual(data['schema'], 'bos.order-trace.v1')
        self.assertEqual(data['order']['id'], self.order.pk)
        self.assertEqual((line['ordered'], line['shipped'], line['cancelled'], line['open'], line['usable_reserved']),
            ('10.000', '2.000', '2.000', balances.quantity_text(balances.sales_open(self.line)), '3.125'))
        refs = line['source_refs']
        self.assertEqual(refs['line'], {'type': 'sales_line', 'id': self.line.pk})
        self.assertEqual(refs['cancellations'][0]['id'], cancellation.pk)
        self.assertEqual(refs['reservations'][0]['id'], self.reservation.pk)
        self.assertEqual(refs['shipments'][0]['quantity'], '-2.000')
        self.assertEqual(refs['lot_origins'], [{'relation':'lot_origin', 'lot_id':self.lot.pk,
            'receipt_id':self.receipt.pk, 'purchase_id':self.purchase.pk}])
        self.assertEqual(data['linked_jobs'][0]['owner']['role'], 'job_owner')
        self.assertEqual(data['linked_tasks'][0]['assignee']['role'], 'task_assignee')
        self.assertEqual(data['order']['owner']['role'], 'order_owner')
        self.assertEqual(data['completeness'], 'complete')
        self.assertEqual(before, list(Configuration.objects.order_by('pk').values()))
        for query in captured_queries:
            self.assertFalse(query['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ')), query['sql'])
        again = self.json_get(client, self.url)
        print('ORDER_TRACE_SAMPLE '+json.dumps(data,ensure_ascii=False))
        data.pop('generated_at'); again.pop('generated_at')
        self.assertEqual(data, again)
        print('ORDER_TRACE_SYNTHETIC_METRIC '+json.dumps({'sql_count':len(captured_queries), 'elapsed_seconds':round(elapsed,6),
            'backend':connection.vendor, 'lines':1, 'reservations':1, 'shipments':1, 'scope':'small fixture only'}))

    def test_ceo_manager_observer_field_allowlists(self):
        for role in ('ceo', 'manager', 'observer'):
            with self.subTest(role=role):
                client = self.grant(role, 'view_document')
                with CaptureQueriesContext(connection) as queries:
                    start = time.monotonic()
                    data = self.json_get(client, self.url)
                    elapsed = time.monotonic() - start
                print('ORDER_TRACE_ROLE_METRIC '+json.dumps({'role':role, 'sql_count':len(queries), 'elapsed_seconds':round(elapsed,6), 'backend':connection.vendor, 'scope':'small fixture only'}))
                self.assertTrue(data['lines'])
                self.assertTrue(data['linked_invoice_refs'])
                self.assertEqual(set(data['linked_invoice_refs'][0]), {'invoice_id','code','currency','due_date'})
                forbidden = {'price','cost','unit_cost','amount','paid','result','payload','approval_snapshot',
                    'phone','email','birthday','notes','reason','read_revision','erp_write','hidden_count'}
                self.assertFalse(set(nested_keys(data)) & forbidden)
                self.assert_no_canaries(data, (self.HIDDEN, self.HIDDEN_VERSION, self.HR_PHONE, self.HR_EMAIL)+self.FINANCE_AMOUNTS)

    def test_hidden_reservation_is_null_not_zero_or_visible_sum(self):
        hidden = self.hidden_reservation()
        for role in ('manager','observer'):
            data = self.get_trace(role); line = data['lines'][0]
            self.assertIsNone(line['usable_reserved'])
            self.assertEqual(line['completeness'], 'restricted')
            self.assertEqual(data['completeness'], 'restricted')
            self.assertNotIn(hidden.pk, [r['id'] for r in line['source_refs']['reservations']])
            self.assert_no_canaries(data, ('TRACE-HIDDEN-LOT', self.HIDDEN, '1.875'))
        self.assertEqual(self.get_trace()['lines'][0]['usable_reserved'], '5.000')

    def test_only_allowed_invoice_links_and_historical_tasks(self):
        invoice = Invoice.objects.create(code='TRACE-UNLINKED-PRIVATE', customer=self.customer,
            amount='98765.43', currency='EUR', due_date=self.today)
        InvoiceLink.objects.create(invoice=invoice, order=self.hidden_order, lines=[])
        task = Task.objects.create(title='TRACE-HISTORY-PRIVATE', sales_order=self.order,
            assignee_employee=self.employee, result=self.HIDDEN)
        AuditEvent.objects.create(action='update_task', task=task,
            payload={'schema':'bos.task-change.v1','source_refs':[{'order_id':self.hidden_order.pk}]})
        for role in ('manager','observer'):
            data = self.get_trace(role)
            self.assertNotIn(invoice.pk, [x['invoice_id'] for x in data['linked_invoice_refs']])
            self.assertNotIn(task.pk, [x['id'] for x in data['linked_tasks']])
            self.assertEqual(data['completeness'], 'restricted')
            self.assert_no_canaries(data, ('TRACE-UNLINKED-PRIVATE','TRACE-HISTORY-PRIVATE',self.HIDDEN))
        self.assertIn(task.pk, [x['id'] for x in self.get_trace()['linked_tasks']])

    def test_current_role_refresh_and_neutral_not_found(self):
        client = self.grant('ceo', 'view_document')
        url = f'/api/erp/orders/{self.hidden_order.pk}/trace/'
        self.assertEqual(client.get(url).status_code, 200)
        self.users['ceo'].groups.set([Group.objects.get_or_create(name='observer')[0]])
        denied = client.get(url); missing = client.get('/api/erp/orders/999999/trace/')
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(denied.json(), missing.json())
        self.assert_no_canaries(denied.json(), (self.HIDDEN, self.hidden_order.code))

    def test_method_and_no_documents_contract(self):
        for role in ('ceo','manager','observer'):
            client = self.grant(role, 'view_document')
            for method in ('HEAD','OPTIONS','POST','PUT','PATCH','DELETE','TRACE','CONNECT'):
                with self.subTest(role=role, method=method):
                    expected = 403 if role == 'observer' and method not in ('HEAD','OPTIONS') else 405
                    response = client.generic(method, self.url, HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
                    self.assertEqual(response.status_code, expected)
            self.users[role].user_permissions.clear()
            self.assertEqual(client.get(self.url).status_code, 200 if role == 'ceo' else 404)
        anon = Client(enforce_csrf_checks=True)
        anon.get('/api/auth/csrf/')
        for method in ('GET','HEAD','OPTIONS','POST','PUT','PATCH','DELETE','TRACE','CONNECT'):
            self.assertEqual(anon.generic(method, self.url,
                HTTP_X_CSRFTOKEN=anon.cookies[settings.CSRF_COOKIE_NAME].value).status_code, 401)
        technical = self.client_for('manager')
        self.users['manager'].groups.clear()
        for method in ('GET','HEAD','OPTIONS','POST','PUT','PATCH','DELETE','TRACE','CONNECT'):
            self.assertEqual(technical.generic(method, self.url,
                HTTP_X_CSRFTOKEN=technical.cookies[settings.CSRF_COOKIE_NAME].value).status_code, 403)

    def test_unrelated_order_purchase_not_allocated(self):
        other = SalesLine.objects.create(order=self.hidden_order, item=self.item, revision='A', quantity='6', price='1')
        Movement.objects.create(lot=self.lot, line=other, quantity='-1', kind='shipment', reference='OTHER-ORDER')
        data = self.get_trace()
        self.assertEqual([x['line_id'] for x in data['lines']], [self.line.pk])
        self.assertEqual(len(data['lines'][0]['source_refs']['shipments']), 1)
        self.assertEqual(data['scope']['purchase_allocation'], 'not_recorded')
        self.assertNotIn('allocated_purchase', json.dumps(data))

    def test_partial_refs_keep_full_decimal_and_old_shipments(self):
        Movement.objects.bulk_create([Movement(lot=self.lot, line=self.line, quantity='-0.001',
            kind='shipment', reference='TRACE-PADDING') for _ in range(101)])
        self.line.shipped=Decimal('2.101'); self.line.save()
        # Unrelated global padding must not hide the old order movement.
        Movement.objects.bulk_create([Movement(lot=self.hidden_lot, quantity='0', kind='test_padding',
            reference='UNRELATED') for _ in range(301)])
        data = self.get_trace(); line = data['lines'][0]
        self.assertEqual(line['shipped'], '2.101')
        self.assertEqual(line['open'], '7.899')
        self.assertEqual(len(line['source_refs']['shipments']), 100)
        self.assertIn(self.shipment.pk, [r['id'] for r in line['source_refs']['shipments']])
        self.assertTrue(line['has_more']['shipments'])
        self.assertEqual(data['completeness'], 'partial')

    def change_between_reads(self, mutate):
        from erp import order_trace
        original = order_trace.collect
        calls = []
        def collect(*args, **kwargs):
            result = original(*args, **kwargs)
            calls.append(True)
            if len(calls) == 1:
                mutate()
            return result
        with patch.object(order_trace, 'collect', side_effect=collect):
            response = self.grant('manager','view_document').get(self.url)
        self.assertLessEqual(len(calls), 2, 'Automatic retries are forbidden')
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()['code'], 'read_state_changed')
        self.assertEqual(set(response.json()), {'error','code'})

    def test_reservation_change_between_reads_has_no_payload(self):
        self.change_between_reads(lambda: Reservation.objects.filter(pk=self.reservation.pk).update(quantity='2.000'))

    def test_document_admission_change_between_reads_has_no_payload(self):
        self.item.required_documents=['certificate']; self.item.save()
        self.lot.documents={'certificate':self.public_doc.pk}; self.lot.save()
        self.change_between_reads(lambda: type(self.public_doc).objects.filter(pk=self.public_doc.pk).update(status='needs_review'))

    def test_permission_change_between_reads_has_no_payload(self):
        self.change_between_reads(lambda: self.users['manager'].user_permissions.clear())

    def test_metadata_and_membership_changes_between_reads_have_no_payload(self):
        mutations = [lambda: type(self.employee).objects.filter(pk=self.employee.pk).update(full_name='Changed owner'),
            lambda: Task.objects.create(title='New task membership', sales_order=self.order),
            lambda: Configuration.objects.create(key='erp_write', value={'sequence':1})]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.change_between_reads(mutate)

    def test_revoked_identity_between_reads_uses_identity_denial(self):
        from erp import order_trace
        original = order_trace.collect
        def collect(*args, **kwargs):
            result = original(*args, **kwargs)
            type(self.users['manager']).objects.filter(pk=self.users['manager'].pk).update(is_active=False)
            return result
        client = self.grant('manager','view_document')
        with patch.object(order_trace, 'collect', side_effect=collect):
            response = client.get(self.url)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'identity_denied')
        self.assertEqual(response['X-BoS-Identity'], 'denied')

    def test_hidden_latest_document_does_not_disclose_admission(self):
        self.item.required_documents=['certificate']; self.item.save()
        self.lot.documents={'certificate':self.public_version.pk}; self.lot.save()
        data = self.get_trace('observer'); line=data['lines'][0]
        self.assertIsNone(line['usable_reserved'])
        self.assertIsNone(line['source_refs']['reservations'][0]['usable'])
        self.assertEqual(line['completeness'], 'restricted')
        self.assert_no_canaries(data, (self.HIDDEN_VERSION,))

    def test_hidden_purchase_receipt_is_not_a_lot_origin(self):
        self.purchase.request = self.requests['R02']; self.purchase.save()
        for role in ('manager', 'observer'):
            data = self.get_trace(role)
            self.assertEqual(data['lines'][0]['source_refs']['lot_origins'], [])
            self.assertEqual(data['lines'][0]['completeness'], 'restricted')
            self.assert_no_canaries(data, (self.purchase.code, self.HIDDEN))
        self.assertEqual(self.get_trace()['lines'][0]['source_refs']['lot_origins'][0]['purchase_id'], self.purchase.pk)

    def test_physical_return_movement_does_not_reduce_gross_shipped(self):
        Movement.objects.create(lot=self.lot, line=self.line, quantity='1', kind='customer_return', reference='RETURN')
        data = self.get_trace(); line = data['lines'][0]
        self.assertEqual(line['shipped'], '2.000')
        self.assertEqual(line['open'], '8.000')
        self.assertEqual([row['id'] for row in line['source_refs']['shipments']], [self.shipment.pk])
        self.assertIn('фізичне повернення її не зменшує', line['basis'])

    def test_hidden_shipment_keeps_admitted_line_quantity_without_source_leak(self):
        hidden_lot = Lot.objects.create(code='TRACE-SHIP-HIDDEN-LOT', item=self.item,
            location=self.location, revision='A', quantity='1', quality='approved',
            documents={'certificate':self.hidden_doc.pk})
        hidden = Movement.objects.create(lot=hidden_lot, line=self.line, kind='shipment',
            quantity='-1.125', reference='TRACE-SHIP-HIDDEN-REF')
        SalesLine.objects.filter(pk=self.line.pk).update(shipped='3.125')
        for role in ('manager','observer'):
            data = self.get_trace(role); line = data['lines'][0]
            self.assertEqual(line['shipped'], '3.125')
            self.assertEqual(line['open'], '6.875')
            self.assertEqual(line['completeness'], 'restricted')
            self.assertEqual([r['id'] for r in line['source_refs']['shipments']], [self.shipment.pk])
            self.assertNotIn(hidden.pk, [r['id'] for r in line['source_refs']['shipments']])
            self.assert_no_canaries(data, ('TRACE-SHIP-HIDDEN-LOT','TRACE-SHIP-HIDDEN-REF','-1.125',self.HIDDEN))

    def test_snapshot_and_global_fingerprint_are_not_called(self):
        with (patch('erp.queries.snapshot', side_effect=AssertionError('global snapshot')),
                patch('erp.service.fingerprint', side_effect=AssertionError('global fingerprint'))):
            self.get_trace()
