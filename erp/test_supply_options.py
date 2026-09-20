"""New supply projection only; owned synthetic database, no broad suite."""
import json
from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.test.utils import CaptureQueriesContext

from boss_project.policy import Policy
from branches.models import Branch
from operations.test_access import A04SyntheticCase
from . import service, supply_options
from .models import Location, Lot, Production, Purchase, Reservation, SalesLine
from .order_trace import ReadStateChanged


class SupplyOptionsTests(A04SyntheticCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.order.branch = cls.branch
        cls.order.save()
        cls.location.branch = cls.branch
        cls.location.save()
        cls.line.quantity, cls.line.shipped, cls.line.invoiced = 10, 0, 0
        cls.line.save()
        cls.lot.quantity = 6
        cls.lot.save()
        cls.other_branch = Branch.objects.create(code='SUP-OTHER', name='Other synthetic branch')
        cls.other_location = Location.objects.create(code='SUP-OTHER', name='Other warehouse', branch=cls.other_branch)
        cls.other_lot = Lot.objects.create(code='SUP-OTHER', item=cls.item, location=cls.other_location,
                                           revision='A', quantity='5', quality='approved', currency='UAH')

    def request_for(self, role='ceo'):
        self.grant(role, 'view_document')
        return self.scoped_request(role)

    def read(self, role='ceo', target=None):
        return supply_options.build(self.request_for(role), self.line.pk, target)

    def make_purchase(self, **values):
        values = {'code': 'SUP-PO', 'item': self.item, 'supplier': self.supplier,
                  'quantity': '8', 'received': '2', 'price': '10.00', 'currency': 'UAH',
                  'due_date': self.today, 'original_due': self.today, 'revision': 'A', **values}
        return Purchase.objects.create(**values)

    def test_exact_available_reserves_destination_and_no_writes(self):
        Reservation.objects.create(lot=self.lot, line=self.line, quantity='2')
        request = self.request_for()
        before = service.fingerprint()
        with CaptureQueriesContext(connection) as queries:
            data = supply_options.build(request, self.line.pk, self.location.pk)
        q = data['quantities']
        self.assertEqual(data['schema'], 'bos.supply-options.v1')
        self.assertEqual((q['remaining'], q['reserved_usable'], q['quantity_to_cover']), ('10.000', '2.000', '8.000'))
        self.assertEqual((q['available_target'], q['target_gap'], q['available_all_locations']), ('4.000', '4.000', '9.000'))
        self.assertEqual(q['uncovered_after_stock'], '0.000')
        self.assertEqual({r['relation'] for r in data['stock']}, {'target', 'other_location'})
        self.assertEqual(data['target_location']['branch_id'], self.branch.pk)
        self.assertIsNone(data['operation_proposal'])
        self.assertEqual(service.fingerprint(), before)
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ')) for q in queries))

    def test_no_implicit_target_or_first_warehouse(self):
        data = self.read()
        self.assertIsNone(data['target_location'])
        self.assertTrue(data['target_required_for_transfer'])
        self.assertIsNone(data['quantities']['available_target'])
        self.assertIsNone(data['quantities']['target_gap'])
        self.assertEqual({r['relation'] for r in data['stock']}, {'order_branch', 'other_or_unassigned_branch'})

    def test_pending_blocked_revision_and_fully_reserved_are_not_free(self):
        self.other_lot.quality = 'pending'
        self.other_lot.save()
        Reservation.objects.create(lot=self.lot, line=self.line, quantity='6')
        blocked = Lot.objects.create(code='SUP-BLOCKED', item=self.item, location=self.location,
                                     revision='A', quantity='4', quality='blocked')
        wrong = Lot.objects.create(code='SUP-REV', item=self.item, location=self.location,
                                   revision='B', quantity='8', quality='approved')
        data = self.read()
        self.assertEqual(data['stock'], [])
        self.assertEqual(data['quantities']['uncovered_after_stock'], '4.000')
        self.assertEqual({r['lot_id']: r['reason'] for r in data['waiting']},
                         {self.lot.pk: 'fully_reserved', self.other_lot.pk: 'quality_pending',
                          blocked.pk: 'quality_blocked', wrong.pk: 'revision_mismatch'})

    def test_missing_or_tampered_document_never_admits_stock(self):
        self.item.required_documents = ['certificate']
        self.item.save()
        self.lot.documents = {'certificate': self.public_doc.pk}
        self.lot.save()
        self.public_doc.content = b'tampered synthetic bytes'
        self.public_doc.save()
        data = self.read()
        self.assertEqual(data['stock'], [])
        self.assertTrue(all(row['reason'] == 'document_admission_required' for row in data['waiting']))
        self.assertEqual(data['quantities']['uncovered_after_stock'], '10.000')

    def test_partial_cancelled_purchase_is_only_unallocated_expectation(self):
        self.lot.quality = self.other_lot.quality = 'blocked'
        self.lot.save(); self.other_lot.save()
        Purchase.objects.filter(pk=self.purchase.pk).update(received=9, status='received')
        po = self.make_purchase()
        # A real existing cancellation writer validates and records this source.
        service.dispatch({'action': 'erp_cancel_remaining', 'operation_id': '00000000-0000-4000-8000-000000000071',
                          'code': 'SUP-CANCEL', 'purchase_id': po.pk, 'quantity': '1',
                          'business_date': str(self.today), 'reason': 'Synthetic cancellation'}, 'ceo',
                         correction_actor=Policy(self.request_for()).actor)
        data = self.read()
        row = next(r for r in data['purchases'] if r['purchase_id'] == po.pk)
        self.assertEqual(row['open_quantity'], '5.000')
        self.assertEqual(row['allocation'], 'not_recorded')
        self.assertEqual(data['quantities']['uncovered_after_stock'], '10.000')
        self.assertEqual(data['quantities']['unallocated_expected'], '5.000')
        self.assertEqual(data['quantities']['indicative_after_expected'], '5.000')
        self.assertNotIn('price', row)

    def test_restricted_roles_do_not_infer_hidden_reservations_or_latest_docs(self):
        self.item.required_documents = ['certificate']
        self.item.save()
        self.lot.documents = {'certificate': self.public_version.pk}
        self.lot.save()
        self.assertEqual(self.public_version.code, self.hidden_version.code)
        self.assertFalse(service.usable(self.lot, self.line.revision))
        hidden_line = SalesLine.objects.create(order=self.hidden_order, item=self.item,
                                               revision='A', quantity=8, price=1)
        Reservation.objects.create(lot=self.lot, line=hidden_line, quantity='3')
        for role in ('manager', 'observer'):
            data = self.read(role)
            self.assertEqual(data['completeness'], 'restricted')
            for key in ('reserved_usable', 'quantity_to_cover', 'available_all_locations',
                        'uncovered_after_stock', 'indicative_after_expected', 'unallocated_expected'):
                self.assertIsNone(data['quantities'][key], key)
            self.assertTrue(all(row['available'] is None and row['eligible'] is None for row in data['stock']))
            self.assertEqual(data['waiting'], [])
            self.assertNotIn(self.hidden_lot.pk, [r['lot_id'] for r in data['stock']])
            self.assertNotIn(self.HIDDEN, json.dumps(data))
            self.assertNotIn(self.HIDDEN_VERSION, json.dumps(data))
            self.assert_no_money(data)

    def test_other_revision_and_production_purchase_do_not_cover_unallocated_need(self):
        Purchase.objects.filter(pk=self.purchase.pk).update(received=9, status='received')
        same = self.make_purchase()
        different = self.make_purchase(code='SUP-PO-B', revision='B', currency='USD')
        job = Production.objects.create(code='SUP-JOB', item=self.item, line=self.line,
            quantity='1', revision='A', location=self.location, owner=self.employee, due_date=self.today)
        allocated = self.make_purchase(code='SUP-PO-JOB', production=job, currency='EUR')
        data = self.read()
        rows = {r['purchase_id']: r for r in data['purchases']}
        self.assertTrue(rows[same.pk]['eligible_as_unallocated_expectation'])
        self.assertEqual(rows[different.pk]['reason'], 'revision_mismatch')
        self.assertEqual(rows[allocated.pk]['reason'], 'allocated_to_production')
        self.assertFalse(rows[different.pk]['eligible_as_unallocated_expectation'])
        self.assertFalse(rows[allocated.pk]['eligible_as_unallocated_expectation'])
        self.assertEqual(data['quantities']['unallocated_expected'], '6.000')

    def test_committed_cancellation_after_second_collect_is_stale(self):
        original = supply_options.collect
        actor = Policy(self.request_for()).actor
        po = self.make_purchase()
        # Cancel unreserved quantity after the second DTO was collected. The
        # source PO/line stays unchanged; the appended correction model and ERP
        # write revision both guard this mutation (service.MODELS includes it).
        for index, source in enumerate(({'line_id': self.line.pk}, {'purchase_id': po.pk})):
            with self.subTest(source=source):
                calls = []
                fingerprint_before = service.fingerprint()
                model, pk = (SalesLine, self.line.pk) if 'line_id' in source else (Purchase, po.pk)
                target_before = model.objects.filter(pk=pk).values().get()
                def changing(*args, **kwargs):
                    value = original(*args, **kwargs)
                    calls.append(1)
                    if len(calls) == 2:
                        service.dispatch({'action': 'erp_cancel_remaining',
                            'operation_id': '00000000-0000-4000-8000-00000000008' + str(index),
                            'code': 'SUP-LATE-' + str(index), 'quantity': '1',
                            'business_date': str(self.today), 'reason': 'Synthetic late cancellation',
                            **source}, 'ceo', correction_actor=actor)
                        self.assertEqual(model.objects.filter(pk=pk).values().get(), target_before)
                        self.assertNotEqual(service.fingerprint(), fingerprint_before)
                    return value
                with patch.object(supply_options, 'collect', side_effect=changing), self.assertRaises(ReadStateChanged):
                    self.read()
                self.assertEqual(len(calls), 2)

    def test_hidden_line_and_unknown_target_fail_closed(self):
        request = self.request_for('manager')
        with self.assertRaises(ObjectDoesNotExist):
            supply_options.build(request, self.hidden_order.lines.first().pk)
        with self.assertRaises(ObjectDoesNotExist):
            supply_options.build(self.request_for(), self.line.pk, 999999)
        for bad in (True, 0, -1, '1', 1.5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                supply_options.build(self.request_for(), self.line.pk, bad)

    def test_data_changes_and_access_changes_conflict(self):
        original = supply_options.collect
        calls = []
        def changing(*args, **kwargs):
            value = original(*args, **kwargs)
            if not calls:
                Lot.objects.filter(pk=self.lot.pk).update(quantity='5')
            calls.append(1)
            return value
        with patch.object(supply_options, 'collect', side_effect=changing), self.assertRaises(ReadStateChanged):
            self.read()
        request = self.request_for()
        request.bos_access_revision = 'stale-access'
        with self.assertRaises(ReadStateChanged):
            supply_options.build(request, self.line.pk)
        with patch.object(Policy, 'access_revision', side_effect=['first', 'changed']), self.assertRaises(ReadStateChanged):
            supply_options.build(self.request_for(), self.line.pk)

    def test_limit_is_explicit_and_totals_include_all_sources(self):
        Lot.objects.bulk_create([Lot(code=f'SUP-CAP-{i}', item=self.item, location=self.location,
                                    revision='A', quantity='0.001', quality='approved') for i in range(101)])
        data = self.read()
        self.assertEqual(len(data['stock']), 100)
        self.assertTrue(data['limits']['has_more']['stock'])
        self.assertEqual(data['quantities']['available_all_locations'], '11.101')

    def test_nonbuy_or_quote_is_explicitly_unsupported(self):
        self.order.status = 'quote'; self.order.save()
        self.assertFalse(self.read()['supported'])
        self.order.status = 'confirmed'; self.order.save()
        self.item.method = 'make'; self.item.save()
        data = self.read()
        self.assertFalse(data['supported'])
        self.assertEqual(data['reason'], 'requires_confirmed_order_and_purchased_item')
