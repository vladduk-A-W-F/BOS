"""Targeted new-card checks; synthetic HTTP/ORM sources, never the full suite."""
import io
import json
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.models.deletion import ProtectedError
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from branches.models import Branch
from operations.models import Configuration, Invoice
from operations.test_access import A04SyntheticCase
from erp import service, workpoints
from erp.models import Event, InvoiceAdjustment, Item, Location, Lot, Movement, Reservation, SalesOrder, SalesLine


class WorkpointTests(A04SyntheticCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.location.branch = cls.branch
        cls.location.save()
        cls.order.branch = cls.branch
        cls.order.save()
        cls.branch.lat, cls.branch.lng = 50.4501, 30.5234
        cls.branch.save()

    def read(self, role='ceo'):
        return self.json_get(self.grant(role, 'view_document'), '/api/erp/workpoints/')

    def point(self, data):
        return next(p for p in data['points'] if p['branch'] and p['branch']['id'] == self.branch.pk)

    def test_exact_currency_groups_sources_and_read_only(self):
        client = self.grant('ceo', 'view_document')
        before = service.fingerprint()
        with CaptureQueriesContext(connection) as queries:
            data = self.json_get(client, '/api/erp/workpoints/')
        p = self.point(data)
        self.assertEqual(data['schema'], 'bos.workpoints.v1')
        self.assertEqual(data['scope'], 'visible_records')
        self.assertEqual({m['currency']: m['invoiced'] for m in p['money']},
            dict(zip(('EUR', 'USD', 'UAH'), self.FINANCE_AMOUNTS[:3])))
        for row in p['money']:
            self.assertEqual(row['open'], row['invoiced'])
            self.assertEqual(row['paid'], '0.00')
            self.assertTrue(row['invoice_ids'])
        self.assertIn(self.order.pk, p['order_ids'])
        self.assertIn(self.location.pk, p['location_ids'])
        self.assertEqual(before, service.fingerprint())
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ')) for q in queries))
        print('WORKPOINT_SAMPLE ' + json.dumps(data, ensure_ascii=False))

    def test_quantity_units_are_not_combined(self):
        item = Item.objects.create(code='WP-KG', name='Material', unit='кг')
        lot = Lot.objects.create(code='WP-KG-LOT', item=item, location=self.location,
            revision='A', quantity='0.125', quality='approved')
        stock = self.point(self.read())['stock']
        self.assertGreaterEqual(len(stock), 2)
        kg = next(row for row in stock if row['item_id'] == item.pk)
        self.assertEqual((kg['unit'], kg['quantity'], kg['lot_ids']), ('кг', '0.125', [lot.pk]))

    def test_private_ids_money_and_hidden_reservations_never_leak(self):
        Reservation.objects.create(lot=self.lot, line=self.line, quantity='1.125')
        hidden_line = SalesLine.objects.create(order=self.hidden_order, item=self.item,
            revision='A', quantity='5', price='10')
        hidden = Reservation.objects.create(lot=self.lot, line=hidden_line, quantity='2.875')
        for role in ('manager', 'observer'):
            data = self.read(role)
            p = self.point(data)
            self.assertEqual(p['completeness'], 'restricted')
            self.assertIsNone(p['money'])
            stock = next(row for row in p['stock'] if row['item_id'] == self.item.pk)
            self.assertEqual(stock['reserved'], '1.125')
            self.assertIsNone(stock['available'])
            for point in data['points']:
                self.assertNotIn(self.hidden_order.pk, point['order_ids'])
                self.assertNotIn(self.hidden_lot.pk, point['lot_ids'])
                self.assertNotIn(self.hidden_doc.pk, point['document_ids'])
                self.assertNotIn('hidden_count', point)
            self.assert_no_canaries(data, [self.HIDDEN, self.HR_PHONE, *self.FINANCE_AMOUNTS])
            before = json.dumps(data['points'], sort_keys=True)
            hidden.quantity = Decimal('3.875'); hidden.save()
            after = json.dumps(self.read(role)['points'], sort_keys=True)
            self.assertEqual(before, after)

    def test_non_document_role_does_not_gain_document_sources(self):
        data = self.json_get(self.client_for('observer'), '/api/erp/workpoints/')
        self.assertTrue(all(p['document_ids'] == [] for p in data['points']))

    def test_credits_reversals_and_overpayment_keep_currency_sources(self):
        self.grant('ceo')
        inv = self.invoices[2]
        inv.amount = Decimal('3600.00'); inv.paid = Decimal('3500.25'); inv.save()
        def credit(code, amount, reversed_credit=None):
            event = Event.objects.create(action='erp_credit_invoice', role='ceo', payload={}, result={})
            return InvoiceAdjustment.objects.create(code=code, operation_id=uuid4(), payload_hash='a'*64,
                reason='Synthetic correction', business_date=self.today, actor=self.users['ceo'], event=event,
                invoice=inv, kind='reversal' if reversed_credit else 'credit',
                basis='reversal' if reversed_credit else 'commercial', basis_snapshot={}, basis_hash='b'*64,
                total=amount, currency='UAH', reversed_credit=reversed_credit)
        credit('WP-CREDIT', '200.50')
        reversed_credit = credit('WP-REVERSED', '100.25')
        credit('WP-REVERSAL', '100.25', reversed_credit)
        money = {row['currency']: row for row in self.point(self.read())['money']}
        uah = money['UAH']
        self.assertEqual([uah[k] for k in ('gross_invoiced', 'credited', 'invoiced', 'paid', 'open', 'customer_credit')],
            ['3600.00', '200.50', '3399.50', '3500.25', '0.00', '100.75'])
        self.assertEqual(uah['invoice_ids'], [inv.pk])
        self.assertEqual(money['EUR']['invoiced'], self.FINANCE_AMOUNTS[0])

    def test_global_movement_cap_and_unassigned_legacy_sources(self):
        old = Movement.objects.filter(lot=self.lot).first()
        Movement.objects.bulk_create([Movement(lot=self.lot, quantity='0', kind='adjust',
            reference='WP-CAP-' + str(i)) for i in range(301)])
        data = self.read()
        ids = [pk for p in data['points'] for pk in p['movement_ids']]
        self.assertEqual(len(ids), 300)
        self.assertNotIn(old.pk, ids)
        self.assertTrue(all(p['movement_scope'] == 'latest_300_visible_global' for p in data['points']))
        null = next(p for p in data['points'] if p['branch'] is None)
        self.assertIn(self.hidden_order.pk, null['order_ids'])

    def test_branch_delete_is_protected_and_pending_deleted_reference_refuses(self):
        with self.assertRaises(ProtectedError): self.branch.delete()
        spare = Branch.objects.create(code='WP-SPARE', name='No records')
        client = self.grant('ceo')
        payload = {'action': 'erp_location', 'code': 'WP-DELETED', 'name': 'Gone', 'kind': 'warehouse', 'branch_id': spare.pk}
        preview = self.post(client, '/api/erp/preview/', payload)
        self.assertEqual(preview.status_code, 200, preview.content)
        spare.delete()
        response = self.post(client, '/api/operations/confirm/', {'proposal_id': preview.json()['id'], 'confirmed': True})
        self.assertIn(response.status_code, (404, 409), response.content)
        self.assertFalse(Location.objects.filter(code='WP-DELETED').exists())

    def test_branch_is_owning_order_not_fulfilment_location(self):
        other = Branch.objects.create(code='WP-OTHER', name='Other branch')
        self.order.branch = other; self.order.save()
        data = self.read()
        physical = self.point(data)
        owned = next(p for p in data['points'] if p['branch'] and p['branch']['id'] == other.pk)
        self.assertIn(self.order.pk, owned['order_ids'])
        self.assertNotIn(self.order.pk, physical['order_ids'])
        self.assertIn(self.lot.pk, physical['lot_ids'])
        self.assertEqual(owned['lot_ids'], [])

    def test_preview_confirm_replay_and_optional_legacy_links(self):
        client = self.grant('manager', 'view_document')
        for action, data, model in [
            ('location', {'code': 'WP-NEW-LOC', 'name': 'New', 'kind': 'warehouse'}, Location),
            ('order', {'code': 'WP-NEW-SO', 'customer_id': self.customer.pk, 'owner_id': self.employee.pk,
                'due_date': str(self.today), 'currency': 'UAH',
                'lines': [{'item_id': self.item.pk, 'quantity': '2', 'price': '1800.01'}]}, SalesOrder)]:
            payload = {'action': 'erp_' + action, **data, 'branch_id': self.branch.pk}
            preview = self.post(client, '/api/erp/preview/', payload)
            self.assertEqual(preview.status_code, 200, preview.content)
            self.assertFalse(model.objects.filter(code=data['code']).exists())
            confirm = {'proposal_id': preview.json()['id'], 'confirmed': True}
            first = self.post(client, '/api/operations/confirm/', confirm)
            self.assertEqual(first.status_code, 200, first.content)
            second = self.post(client, '/api/operations/confirm/', confirm)
            self.assertEqual(second.status_code, 200, second.content)
            self.assertEqual(model.objects.get(code=data['code']).branch_id, self.branch.pk)
            self.assertEqual(model.objects.filter(code=data['code']).count(), 1)
        legacy = service.dispatch({'action': 'erp_location', 'code': 'WP-LEGACY', 'name': 'Legacy', 'kind': 'warehouse'})
        self.assertIsNone(Location.objects.get(pk=legacy['location_id']).branch_id)
        snap = self.json_get(client, '/api/erp/snapshot/')
        self.assertEqual(next(r for r in snap['orders'] if r['code'] == 'WP-NEW-SO')['branch_id'], self.branch.pk)
        self.assertEqual(set(snap['branches'][0]), set(workpoints.BRANCH_FIELDS))

    def test_invalid_branch_observer_and_changed_branch_confirmation(self):
        payload = {'action': 'erp_location', 'code': 'WP-DENIED', 'name': 'Denied', 'kind': 'warehouse', 'branch_id': 99999999}
        for role in ('ceo', 'manager'):
            response = self.post(self.grant(role, 'view_document'), '/api/erp/preview/', payload)
            self.assertEqual(response.status_code, 404, response.content)
        payload['branch_id'] = self.branch.pk
        denied = self.post(self.grant('observer', 'view_document'), '/api/erp/preview/', payload)
        self.assertEqual(denied.status_code, 403)
        client = self.grant('ceo')
        preview = self.post(client, '/api/erp/preview/', payload).json()
        self.branch.name = 'Changed branch'; self.branch.save()
        response = self.post(client, '/api/operations/confirm/', {'proposal_id': preview['id'], 'confirmed': True})
        self.assertEqual(response.status_code, 409, response.content)
        self.assertFalse(Location.objects.filter(code='WP-DENIED').exists())

    def test_source_and_access_change_fail_closed(self):
        client = self.grant('ceo')
        original = workpoints.collect
        for mutation in ('source', 'rights'):
            calls = []
            def changing(policy):
                data = original(policy)
                calls.append(1)
                if len(calls) == 1:
                    if mutation == 'source':
                        Branch.objects.filter(pk=self.branch.pk).update(name='Changed during read')
                    else:
                        self.users['ceo'].groups.clear()
                return data
            with patch('erp.workpoints.collect', side_effect=changing):
                response = client.get('/api/erp/workpoints/')
            self.assertIn(response.status_code, (403, 409), response.content)
            self.assertNotIn('points', response.json())


@override_settings(BOS_DATA_MODE='demo', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class UkrainianSeedTests(TestCase):
    def seed(self):
        call_command('seed_bos_ua', stdout=io.StringIO())

    def test_real_ua_seed_exact_balance_and_idempotence_preserves_eur(self):
        call_command('seed_bos_demo', stdout=io.StringIO())
        call_command('seed_erp_demo', stdout=io.StringIO())
        old_orders = list(SalesOrder.objects.values())
        old_lots = list(Lot.objects.values())
        old_invoices = list(Invoice.objects.values())
        self.seed()
        self.assertEqual(Branch.objects.filter(code__startswith='UA-DEMO-').count(), 3)
        self.assertEqual(SalesOrder.objects.filter(code__startswith='UA-DEMO-', currency='UAH').count(), 3)
        inv = Invoice.objects.get(code='UA-DEMO-KY-INV')
        self.assertEqual((inv.amount, inv.paid, inv.currency), (Decimal('3600.00'), Decimal('1200.00'), 'UAH'))
        lot = Lot.objects.get(code='UA-DEMO-KY-LOT')
        self.assertEqual((lot.quantity, service.reserved(lot)), (Decimal('3.000'), Decimal('3.000')))
        self.assertTrue(Movement.objects.filter(lot=lot, kind='receipt', purchase__code='UA-DEMO-KY-PO').exists())
        self.assertEqual(list(SalesOrder.objects.filter(pk__in=[r['id'] for r in old_orders]).values()), old_orders)
        self.assertEqual(list(Lot.objects.filter(pk__in=[r['id'] for r in old_lots]).values()), old_lots)
        self.assertEqual(list(Invoice.objects.filter(pk__in=[r['id'] for r in old_invoices]).values()), old_invoices)
        before = service.fingerprint()
        config_before = list(Configuration.objects.order_by('pk').values())
        self.seed()
        self.assertEqual(service.fingerprint(), before)
        self.assertEqual(list(Configuration.objects.order_by('pk').values()), config_before)

    def test_collision_refuses_without_partial_writes(self):
        Configuration.objects.create(key='dataset', value={'as_of': '2026-09-09'})
        Item.objects.create(code='UA-DEMO-PRODUCT', name='Preserved')
        before = service.fingerprint()
        with self.assertRaises(CommandError): self.seed()
        self.assertEqual(service.fingerprint(), before)

    def test_working_mode_and_missing_base_refuse(self):
        with self.assertRaises(CommandError): self.seed()
        with override_settings(BOS_DATA_MODE='working'):
            with self.assertRaises(CommandError): self.seed()
        self.assertFalse(Branch.objects.exists())

    def test_midway_failure_rolls_back_all_seed_rows(self):
        call_command('seed_bos_demo', stdout=io.StringIO())
        before = service.fingerprint()
        configs = list(Configuration.objects.order_by('pk').values())
        original = service.dispatch
        def fail(payload, *args, **kwargs):
            if payload['action'] == 'erp_payment': raise ValueError('Synthetic interruption')
            return original(payload, *args, **kwargs)
        with patch('erp.management.commands.seed_bos_ua.dispatch', side_effect=fail):
            with self.assertRaisesRegex(ValueError, 'Synthetic interruption'): self.seed()
        self.assertEqual(service.fingerprint(), before)
        self.assertEqual(list(Configuration.objects.order_by('pk').values()), configs)
