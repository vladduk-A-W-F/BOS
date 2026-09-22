"""New composition boundaries only; never imports/discovers exhausted suites."""
from datetime import date
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from branches.models import Branch
from boss_project.policy import Policy
from operations.models import Invoice
from . import order_settlement, service
from .models import (Event, InvoiceLink, Item, Location, Lot, PaymentRetention,
                     Purchase, Reservation, SalesLine, SalesOrder, StockTransfer)


@override_settings(BOS_DATA_MODE='working', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class NetworkCompositionContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Reuse fixture construction only, not its TestCase or any test methods.
        from .test_order_settlement import OrderSettlementTests
        OrderSettlementTests.setUpTestData.__func__(cls)
        cls.branch = Branch.objects.create(code='COMPOSE-ORG', name='Організаційна філія')
        cls.other_branch = Branch.objects.create(code='COMPOSE-FULFIL', name='Інша філія виконання')
        cls.location = Location.objects.create(code='COMPOSE-LOC', name='Точка виконання', branch=cls.other_branch)
        cls.other_location = Location.objects.create(code='COMPOSE-OTHER', name='Інша точка', branch=cls.branch)
        cls.item = Item.objects.create(code='COMPOSE-ITEM', name='Синтетична номенклатура', method='buy',
                                       revision='A', currency='UAH', required_documents=[])

    def setUp(self):
        self.client.force_login(self.users['ceo'])

    def preview(self, payload, expected=200):
        response = self.client.post('/api/erp/preview/', payload, content_type='application/json')
        self.assertEqual(response.status_code, expected, response.content)
        return response.json()

    def confirm(self, proposal, expected=200):
        response = self.client.post('/api/operations/confirm/',
            {'proposal_id': proposal['id'], 'confirmed': True}, content_type='application/json')
        self.assertEqual(response.status_code, expected, response.content)
        return response.json()

    def execute(self, payload):
        before = Event.objects.count()
        proposal = self.preview(payload)
        self.assertEqual(Event.objects.count(), before)
        first = self.confirm(proposal)
        self.assertEqual(self.confirm(proposal), first)
        self.assertEqual(Event.objects.count(), before + 1)
        return first

    def settlement(self):
        response = self.client.get(f'/api/erp/orders/{self.order.pk}/settlement/')
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def hold(self, amount='40.00', code='COMPOSE-HOLD'):
        return self.execute({'action': 'erp_hold_payment', 'invoice_id': self.invoice.pk,
                             'amount': amount, 'code': code, 'reason': 'Синтетична договірна умова'})

    def test_organisational_branch_and_cross_branch_fulfillment_survive_preview_replay(self):
        payload = {'action': 'erp_order', 'code': 'COMPOSE-SO', 'customer_id': self.customer.pk,
                   'owner_id': self.employee.pk, 'branch_id': self.branch.pk,
                   'fulfillment_location_id': self.location.pk, 'destination_country': 'UA',
                   'due_date': '2026-12-31', 'currency': 'UAH',
                   'lines': [{'item_id': self.item.pk, 'quantity': '1', 'price': '5.00'}]}
        receipt = self.execute(payload)
        row = SalesOrder.objects.get(pk=receipt['order_id'])
        self.assertEqual((row.branch_id, row.fulfillment_location_id), (self.branch.pk, self.location.pk))
        unlinked = self.execute({**payload, 'code': 'COMPOSE-NULL', 'branch_id': None,
                                 'fulfillment_location_id': None, 'destination_country': ''})
        row = SalesOrder.objects.get(pk=unlinked['order_id'])
        self.assertIsNone(row.branch_id)
        self.assertIsNone(row.fulfillment_location_id)
        self.preview({**payload, 'code': 'COMPOSE-INVALID', 'branch_id': 99999999}, 404)
        self.preview({'action': 'erp_location', 'code': 'COMPOSE-BAD-SUPPLIER', 'name': 'Invalid',
                      'kind': 'supplier', 'supplier_id': self.customer.pk, 'branch_id': self.branch.pk}, 404)

    def test_snapshot_union_preserves_branch_type_and_nonfinancial_projection(self):
        self.order.branch, self.order.fulfillment_location = self.branch, self.location
        self.order.save()
        self.hold()
        body = self.client.get('/api/erp/snapshot/').json()
        branch = next(row for row in body['branches'] if row['id'] == self.branch.pk)
        row = next(row for row in body['orders'] if row['id'] == self.order.pk)
        self.assertEqual(branch['type'], self.branch.type)
        self.assertEqual((row['branch_id'], row['fulfillment_location_id']), (self.branch.pk, self.location.pk))
        network = self.client.get('/api/erp/network/', {'currency': 'UAH', 'branch_id': self.other_branch.pk})
        self.assertEqual(network.status_code, 200, network.content)
        network_order = next(row for row in network.json()['rows']['orders'] if row['id'] == self.order.pk)
        self.assertEqual((network_order['branch_id'], network_order['location_branch_id'], network_order['location_id']),
                         (self.branch.pk, self.other_branch.pk, self.location.pk))
        network_invoice = next(row for row in network.json()['rows']['invoices'] if row['invoice_id'] == self.invoice.pk)
        self.assertEqual((network_invoice['branch_id'], network_invoice['location_branch_id'], network_invoice['location_id']),
                         (self.branch.pk, self.other_branch.pk, self.location.pk))
        self.assertEqual(service.MODELS.count(Branch), 1)
        self.assertIn(StockTransfer, service.MODELS)
        self.assertIn(PaymentRetention, service.MODELS)
        for role in ('manager', 'observer'):
            client = Client(); client.force_login(self.users[role])
            response = client.get('/api/erp/snapshot/')
            self.assertEqual(response.status_code, 200, response.content)
            result = response.json()
            self.assertEqual(result.get('retentions', []), [])
            self.assertNotIn('COMPOSE-HOLD', response.content.decode())
            for invoice in result.get('invoices', []):
                self.assertTrue({'retained', 'collectible', 'amount', 'paid', 'open'}.isdisjoint(invoice))

    def test_retention_sources_hold_release_and_other_order_are_exact(self):
        hold = self.hold()
        foreign = Invoice.objects.create(code='COMPOSE-FOREIGN', customer=self.customer,
            amount='88.00', paid=0, currency='UAH', due_date=date(2026, 12, 31))
        InvoiceLink.objects.create(order=self.foreign, invoice=foreign, lines=[])
        PaymentRetention.objects.create(code='FOREIGN-HOLD-SECRET', invoice=foreign, amount='11.00',
                                         currency='UAH', reason='FOREIGN-REASON')
        first = self.settlement(); row = first['invoices'][0]
        self.assertEqual((row['open'], row['retained'], row['collectible'], row['paid']),
                         ('100.00', '40.00', '60.00', '0.00'))
        self.assertEqual([entry['retention_id'] for entry in row['retentions']], [hold['retention_id']])
        self.assertNotIn('FOREIGN-', str(first))
        self.execute({'action': 'erp_release_payment', 'retention_id': hold['retention_id'],
                      'reason': 'Умову виконано'})
        row = self.settlement()['invoices'][0]
        self.assertEqual((row['open'], row['retained'], row['collectible'], row['paid']),
                         ('100.00', '0.00', '100.00', '0.00'))
        self.assertEqual(row['retentions'][0]['status'], 'released')

    def test_retention_change_invalidates_old_payment_and_collectible_replays_once(self):
        old = self.preview({'action': 'erp_payment', 'invoice_id': self.invoice.pk,
                            'amount': '100.00', 'reference': 'BEFORE-HOLD'})
        self.hold()
        self.confirm(old, 409)
        self.preview({'action': 'erp_payment', 'invoice_id': self.invoice.pk,
                      'amount': '60.01', 'reference': 'OVER-COLLECTIBLE'}, 422)
        self.execute({'action': 'erp_payment', 'invoice_id': self.invoice.pk,
                      'amount': '60.00', 'reference': ' COLLECTIBLE '})
        row = self.settlement()['invoices'][0]
        self.assertEqual((row['open'], row['retained'], row['collectible'], row['paid']),
                         ('40.00', '40.00', '0.00', '60.00'))
        self.assertEqual(row['payment_history']['entries'][0]['reference'], ' COLLECTIBLE ')
        self.assertEqual(Event.objects.filter(action='erp_payment').count(), 1)

    def test_hidden_retention_fails_closed_and_changed_source_returns_neutral_conflict(self):
        self.hold()
        original = Policy.queryset
        def restricted(policy, model):
            return model.objects.none() if model is PaymentRetention else original(policy, model)
        with patch.object(Policy, 'queryset', restricted):
            response = self.client.get(f'/api/erp/orders/{self.order.pk}/settlement/')
        self.assertEqual(response.status_code, 403)
        collect = order_settlement.collect; calls = []
        def changed(policy, order_id):
            value = collect(policy, order_id); calls.append(True)
            if len(calls) == 1: PaymentRetention.objects.filter(invoice=self.invoice).update(reason='Changed source')
            return value
        with patch.object(order_settlement, 'collect', changed):
            response = self.client.get(f'/api/erp/orders/{self.order.pk}/settlement/')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(set(response.json()), {'code', 'error'})

    def test_supply_destination_is_explicit_and_other_currency_never_covers_demand(self):
        from finance.models import Counterparty
        supplier = Counterparty.objects.create(name='Composition supplier', type='supplier')
        self.order.branch, self.order.fulfillment_location, self.order.status = self.branch, self.location, 'confirmed'
        self.order.save()
        line = SalesLine.objects.create(order=self.order, item=self.item, revision='A', quantity=5, price=1)
        Lot.objects.create(code='COMPOSE-EUR', item=self.item, location=self.location, revision='A',
                            quantity=9, quality='approved', currency='EUR', unit_cost=1, documents={})
        for code, destination, currency in [('RIGHT', self.location, 'UAH'), ('OTHER', self.other_location, 'UAH'),
                                           ('UNKNOWN', None, 'UAH'), ('EURO', self.location, 'EUR')]:
            Purchase.objects.create(code='COMPOSE-PO-' + code, item=self.item, supplier=supplier, quantity=1,
                price=1, currency=currency, due_date=date(2026, 12, 31), original_due=date(2026, 12, 31),
                revision='A', destination=destination)
        url = f'/api/erp/lines/{line.pk}/supply-options/'
        initial = self.client.get(url).json()
        self.assertIsNone(initial['target_location'])
        self.assertEqual(initial['line']['order_branch_id'], self.branch.pk)
        self.assertEqual(initial['fulfillment_location']['id'], self.location.pk)
        body = self.client.get(url, {'target_location_id': self.location.pk}).json()
        self.assertEqual(body['quantities']['available_all_locations'], '0.000')
        self.assertEqual(body['quantities']['unallocated_expected'], '1.000')
        self.assertEqual([row['code'] for row in body['purchases'] if row['eligible_as_unallocated_expectation']],
                         ['COMPOSE-PO-RIGHT'])
        self.assertEqual(body['waiting'][0]['reason'], 'currency_mismatch')
        self.assertIsNone(body['operation_proposal'])

    def test_other_location_reserve_does_not_cover_fulfillment_demand(self):
        self.order.fulfillment_location, self.order.status = self.location, 'confirmed'
        self.order.save()
        line = SalesLine.objects.create(order=self.order, item=self.item, revision='A', quantity=5, price=1)
        lot = Lot.objects.create(code='COMPOSE-RESERVED-ELSEWHERE', item=self.item, location=self.other_location,
            revision='A', quantity=5, quality='approved', currency='UAH', unit_cost=1, documents={})
        reserve = Reservation.objects.create(line=line, lot=lot, quantity=5)
        response = self.client.get(f'/api/erp/lines/{line.pk}/supply-options/')
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body['quantities']['reserved_visible'], '5.000')
        self.assertEqual(body['quantities']['reserved_usable'], '0.000')
        self.assertEqual(body['quantities']['quantity_to_cover'], '5.000')
        self.assertEqual(body['quantities']['available_all_locations'], '0.000')
        self.assertEqual(body['reservations'][0]['reservation_id'], reserve.pk)
        self.assertEqual(body['reservations'][0]['reason'], 'release_transfer_required')
        self.preview({'action': 'erp_ship', 'line_id': line.pk, 'lot_id': lot.pk,
                      'quantity': '5', 'reference': 'WRONG-POINT'}, 422)
