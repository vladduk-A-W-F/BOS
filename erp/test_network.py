"""Targeted HTTP coverage of the live network, not full backend acceptance."""
import csv
import io
from decimal import Decimal as D
from unittest.mock import patch

from django.test import Client
from django.db import connection
from django.test.utils import CaptureQueriesContext

from branches.models import Branch
from erp.models import Location, Lot, PaymentRetention, StockTransfer
from operations.models import Configuration
from operations.test_access import A04SyntheticCase, nested_keys


class NetworkReadTests(A04SyntheticCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.branch.lat, cls.branch.lng = 50.45466, 30.5238
        cls.branch.save()
        cls.location.branch = cls.branch
        cls.location.save()
        cls.lot.currency = 'UAH'
        cls.lot.save()
        cls.order.currency = 'UAH'
        cls.order.fulfillment_location = cls.location
        cls.order.destination_country = 'PL'
        cls.order.save()
        cls.purchase.currency = 'UAH'
        cls.purchase.destination = cls.location
        cls.purchase.origin_country = 'DE'
        cls.purchase.save()
        cls.other_branch = Branch.objects.create(code='NET-LVI', name='Львів', lat=49.83826, lng=24.02324)
        cls.other_point = Location.objects.create(code='NET-LVI-WH', name='Склад Львів', branch=cls.other_branch)
        cls.other_lot = Lot.objects.create(code='NET-OTHER', item=cls.item, location=cls.other_point,
            revision='A', quantity='3.125', quality='approved', unit_cost='123.47', currency='UAH')
        cls.foreign_lot = Lot.objects.create(code='NET-EUR', item=cls.item, location=cls.location,
            revision='A', quantity='2', quality='approved', unit_cost='87.45', currency='EUR')
        cls.unassigned_point = Location.objects.create(code='NET-UNASSIGNED', name='Точка без філії')
        cls.unassigned_lot = Lot.objects.create(code='NET-UNASSIGNED-LOT', item=cls.item,
            location=cls.unassigned_point, revision='A', quantity='2', unit_cost='7.25', currency='UAH')
        cls.hold = PaymentRetention.objects.create(code='NET-HOLD', invoice=cls.invoices[2],
            currency='UAH', amount='100.00', reason='Утримання до документів')

    def network(self, client=None, query=''):
        response = (client or self.grant('ceo', 'view_document')).get('/api/erp/network/' + query)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_map_and_table_totals_use_same_currency_and_branch(self):
        data = self.network(query=f'?branch_id={self.branch.pk}&currency=UAH')
        self.assertEqual(data['schema'], 'bos.network.v1')
        self.assertEqual({row['location_id'] for row in data['rows']['lots']}, {self.location.pk})
        self.assertNotIn(self.foreign_lot.code, [row['code'] for row in data['rows']['lots']])
        expected = sum((D(row['value']) for row in data['rows']['lots']), D(0))
        self.assertEqual(D(data['metrics']['inventory_value']), expected)
        self.assertEqual(data['metrics']['point_count'], 1)
        self.assertEqual(data['metrics']['retained'], '100.00')
        self.assertEqual(D(data['metrics']['collectible']) + D(data['metrics']['retained']), D(data['metrics']['receivable']))
        self.assertEqual(data['rows']['purchases'][0]['process'], 'import')
        self.assertEqual(data['rows']['orders'][0]['process'], 'export')
        point = next(row for row in data['locations'] if row['id'] == self.location.pk)
        self.assertEqual(point['coordinate_basis'], 'branch')
        self.assertEqual(point['map_lat'], self.branch.lat)

    def test_point_filter_unassigned_and_foreign_currency_remain_explicit(self):
        data = self.network(query=f'?location_id={self.other_point.pk}')
        self.assertEqual([row['code'] for row in data['rows']['lots']], [self.other_lot.code])
        self.assertEqual(data['metrics']['inventory_value'], '385.84')
        data = self.network(query='?branch_id=unassigned')
        self.assertEqual([row['code'] for row in data['rows']['lots']], [self.unassigned_lot.code])
        self.assertEqual(data['rows']['points'][0]['coordinate_basis'], 'missing')
        data = self.network(query=f'?location_id={self.location.pk}&currency=EUR')
        self.assertEqual([row['code'] for row in data['rows']['lots']], [self.foreign_lot.code])
        self.foreign_lot.refresh_from_db()
        self.assertEqual(self.foreign_lot.currency, 'EUR')

    def test_manager_and_observer_have_no_financial_fields_or_hidden_records(self):
        financial = {'value', 'unit_cost', 'total_cost', 'amount', 'paid', 'open', 'price', 'extras',
            'inventory_value', 'in_transit_value', 'receivable', 'retained', 'collectible', 'approval_snapshot'}
        for role in ('manager', 'observer'):
            data = self.network(self.grant(role, 'view_document'))
            self.assertFalse(financial.intersection(nested_keys(data)), financial.intersection(nested_keys(data)))
            self.assertNotIn(self.hidden_lot.code, [row['code'] for row in data['rows']['lots']])
            self.assertNotIn(self.hidden_order.code, [row['code'] for row in data['rows']['orders']])
            self.assertEqual(data['rows']['retentions'], [])
            self.assertFalse(data['capabilities']['finance'])

    def test_unauthenticated_read_and_export_permissions(self):
        self.assertEqual(Client().get('/api/erp/network/').status_code, 401)
        manager = self.grant('manager', 'view_document')
        self.assertEqual(manager.get('/api/erp/network/export/').status_code, 403)
        self.grant('manager', 'export_workspace')
        self.assertEqual(manager.get('/api/erp/network/export/').status_code, 200)
        observer = self.grant('observer', 'view_document', 'export_workspace')
        self.assertEqual(observer.get('/api/erp/network/export/').status_code, 403)

    def test_csv_and_json_exports_match_filtered_projection_and_escape_formulas(self):
        self.other_point.name = '=HYPERLINK("bad")'
        self.other_point.save()
        client = self.grant('ceo', 'view_document', 'export_workspace')
        suffix = f'?location_id={self.other_point.pk}&currency=UAH'
        data = self.network(client, suffix)
        response = client.get('/api/erp/network/export/' + suffix + '&format=json')
        self.assertEqual(response.status_code, 200)
        exported = response.json()
        from datetime import datetime
        self.assertGreaterEqual(datetime.fromisoformat(exported['workflow'].pop('measured_at')),
                                datetime.fromisoformat(data['workflow'].pop('measured_at')))
        self.assertEqual(exported, data)
        response = client.get('/api/erp/network/export/' + suffix + '&table=points')
        self.assertEqual(response.status_code, 200)
        table = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(len(table), 1)
        self.assertEqual(table[0]['id'], str(self.other_point.pk))
        self.assertTrue(table[0]['name'].startswith("'="))
        self.assertEqual(table[0]['inventory_value'], data['metrics']['inventory_value'])

    def test_reads_write_nothing_and_reject_stale_projection(self):
        client = self.grant('ceo', 'view_document')
        before = list(Configuration.objects.order_by('pk').values())
        with CaptureQueriesContext(connection) as queries:
            self.network(client)
        writes = [row['sql'] for row in queries if row['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE '))]
        self.assertEqual(writes, [])
        self.assertEqual(before, list(Configuration.objects.order_by('pk').values()))
        with patch('erp.network_views.service.fingerprint', side_effect=['before', 'after']):
            response = client.get('/api/erp/network/')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'read_state_changed')

    def test_invalid_filters_and_invalid_coordinate_never_break_projection(self):
        client = self.grant('ceo', 'view_document')
        for query in ('?currency=GBP', '?branch_id=-1', '?location_id=none', '?branch_id=999999'):
            self.assertEqual(client.get('/api/erp/network/' + query).status_code, 422)
        self.branch.lat = 100
        self.branch.save()
        data = self.network(client)
        point = next(row for row in data['locations'] if row['id'] == self.location.pk)
        self.assertEqual(point['coordinate_basis'], 'missing')

    def test_transfer_and_retention_roundtrip_through_existing_confirmation(self):
        client = self.grant('ceo', 'view_document')
        payload = {'action': 'erp_transfer_dispatch', 'lot_id': self.other_lot.pk,
            'location_id': self.location.pk, 'quantity': '1', 'code': 'NET-TRANSFER', 'reason': 'Поповнення'}
        preview = self.post(client, '/api/erp/preview/', payload)
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertFalse(StockTransfer.objects.filter(code='NET-TRANSFER').exists())
        proposal = preview.json()['id']
        response = self.post(client, '/api/operations/confirm/', {'proposal_id': proposal, 'confirmed': True})
        self.assertEqual(response.status_code, 200, response.content)
        again = self.post(client, '/api/operations/confirm/', {'proposal_id': proposal, 'confirmed': True})
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(StockTransfer.objects.filter(code='NET-TRANSFER').count(), 1)
        data = self.network(client, f'?branch_id={self.other_branch.pk}')
        self.assertEqual(data['metrics']['in_transit_count'], 1)
        self.assertEqual(data['metrics']['in_transit_value'], '123.47')
        old = self.network(client)['metrics']
        preview = self.post(client, '/api/erp/preview/', {'action': 'erp_release_payment', 'retention_id': self.hold.pk, 'reason': 'Документи прийняті'})
        self.assertEqual(preview.status_code, 200, preview.content)
        response = self.post(client, '/api/operations/confirm/', {'proposal_id': preview.json()['id'], 'confirmed': True})
        self.assertEqual(response.status_code, 200, response.content)
        new = self.network(client)['metrics']
        self.assertEqual(old['receivable'], new['receivable'])
        self.assertEqual(D(new['collectible']) - D(old['collectible']), D('100'))

    def test_stale_confirm_returns_explicit_terminal_code(self):
        client = self.grant('ceo', 'view_document')
        preview = self.post(client, '/api/erp/preview/', {'action': 'erp_location_update',
            'location_id': self.location.pk, 'address': 'Адреса', 'reason': 'Уточнення'})
        self.assertEqual(preview.status_code, 200, preview.content)
        self.other_point.name = 'Змінена назва'
        self.other_point.save()
        response = self.post(client, '/api/operations/confirm/', {'proposal_id': preview.json()['id'], 'confirmed': True})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['code'], 'proposal_stale')
        self.location.refresh_from_db()
        self.assertNotEqual(self.location.address, 'Адреса')

    def test_next_action_respects_retained_money_and_fulfillment_point(self):
        from erp.experience import next_step
        from erp.queries import plan_line
        from boss_project.policy import Policy
        from django.test import RequestFactory
        client = self.grant('ceo', 'view_document')
        request = RequestFactory().get('/')
        request.user = self.users['ceo']
        request.session = client.session
        policy = Policy(request)
        for invoice in self.invoices[:2]:
            invoice.paid = invoice.amount
            invoice.save()
        result = next_step(self.order, policy)
        self.assertEqual(result['payload']['action'], 'erp_payment')
        self.assertEqual(D(result['payload']['amount']), D(self.invoices[2].amount) - D('100'))
        invoice = self.invoices[2]
        invoice.paid = D(invoice.amount) - D('100')
        invoice.save()
        result = next_step(self.order, policy)
        self.assertIsNone(result['payload'])
        self.assertIn('утримання', result['title'])
        self.line.shipped, self.line.invoiced = D(0), D(0)
        self.line.save()
        self.lot.quantity = D(0)
        self.lot.save()
        self.foreign_lot.quantity = D(0)
        self.foreign_lot.save()
        result = next_step(self.order, policy)
        self.assertEqual(result['payload']['action'], 'erp_transfer_dispatch')
        self.assertEqual(result['payload']['location_id'], self.location.pk)
        self.assertEqual(result['payload']['lot_id'], self.other_lot.pk)
        self.assertEqual(D(plan_line(self.line, policy)['free']), D(0))
