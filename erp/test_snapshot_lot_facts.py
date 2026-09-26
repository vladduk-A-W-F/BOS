"""Seven new, small synthetic snapshot controls; no old suite imports."""
from collections import Counter
from datetime import date
from decimal import Decimal as D
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.test import TestCase, override_settings

from boss_project.policy import Policy
from employees.models import Employee
from finance.models import Counterparty
from operations.models import Configuration, Document
from operations import private_storage
from . import queries, service
from .models import Item, Location, Lot, Production, Reservation, SalesLine, SalesOrder


REFERENCE_SHA = '40dd86d217e2dec7872bfdb85a134acede07d6b2a95ee41ef3f382b03b8ba098'


def reference_reader():
    path = Path(__file__).resolve().parents[1] / 'tests/fixtures/snapshot_lot_facts/queries_030103.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != REFERENCE_SHA:
        raise AssertionError('Pinned pre-change reader fixture changed')
    spec = importlib.util.spec_from_file_location('erp._snapshot_lot_facts_reference', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@override_settings(BOS_DATA_MODE='working')
class SnapshotLotFactsTests(TestCase):
    def setUp(self):
        # Runner supplies a fresh owned D: parent; no existing media is reused.
        self.work = tempfile.TemporaryDirectory(prefix='snapshot-facts-',
            dir=os.environ.get('BOS_FACTS_TEST_ROOT', tempfile.gettempdir()))
        self.addCleanup(self.work.cleanup)
        self.media = Path(self.work.name) / 'media'
        self.media.mkdir(mode=0o700)
        settings = override_settings(MEDIA_ROOT=self.media)
        settings.enable(); self.addCleanup(settings.disable)
        self.original = reference_reader()
        Configuration.objects.create(key='dataset', value={'as_of': '2026-09-21'})
        users = get_user_model()
        self.ceo = users.objects.create_user(username='facts-ceo')
        self.manager = users.objects.create_user(username='facts-manager')
        self.ceo.groups.add(Group.objects.get_or_create(name='ceo')[0])
        self.manager.groups.add(Group.objects.get_or_create(name='manager')[0])
        self.manager.user_permissions.add(Permission.objects.get(
            content_type__app_label='operations', codename='view_document'))
        self.owner = Employee.objects.create(full_name='Synthetic owner', role='Manager', user=self.manager)
        self.customer = Counterparty.objects.create(name='Synthetic customer', type='customer')
        self.here = Location.objects.create(code='FACT-HERE', name='Explicit fulfillment')
        self.other = Location.objects.create(code='FACT-OTHER', name='Other stock')
        self.certificate = self.document('FACT-CERT', 'A', b'synthetic certificate A')
        self.private = self.document('FACT-PRIVATE', 'A', b'private synthetic certificate', access='ceo')
        self.component = Item.objects.create(code='FACT-PART', name='Part', revision='A',
            required_documents=['certificate'], minimum=1, currency='UAH')
        self.assembly = Item.objects.create(code='FACT-ASSEMBLY', name='Assembly', revision='A',
            method='make', required_documents=['certificate'], minimum=1, currency='UAH',
            bom=[{'item_id': self.component.pk, 'quantity': '2'}], routing=[{'days': 1}])
        self.part = self.lot('FACT-PART-LOT', self.component, '10')
        self.finished = self.lot('FACT-FINISHED', self.assembly, '2')
        self.elsewhere = self.lot('FACT-ELSEWHERE', self.assembly, '50', location=self.other)
        self.revision_b = self.lot('FACT-REV-B', self.assembly, '40', revision='B')
        self.blocked = self.lot('FACT-BLOCKED', self.component, '3', quality='blocked', documents={})
        self.foreign = self.lot('FACT-EUR', self.component, '20', currency='EUR')
        self.hidden = self.lot('FACT-HIDDEN', self.component, '999',
            documents={'certificate': self.private.pk})
        self.open_line = self.line('FACT-OPEN', self.assembly, '8')
        self.closed_line = self.line('FACT-CLOSED', self.assembly, '1', shipped='1')
        self.reserve = Reservation.objects.create(lot=self.finished, line=self.open_line, quantity='1')
        self.job = Production.objects.create(code='FACT-JOB', line=self.open_line,
            item=self.assembly, quantity='1', revision='A', location=self.here, owner=self.owner,
            due_date=date(2026, 9, 24), currency='UAH')
        Reservation.objects.create(lot=self.part, production=self.job, quantity='2')

    def document(self, code, revision, raw, access='operational'):
        store = private_storage.private_document_storage
        receipt = store.save_verified(raw, hashlib.sha256(raw).hexdigest(), legacy_blob_bytes=0)
        store.finalize(receipt)
        return Document.objects.create(code=code, revision=revision, title=code,
            status='approved', access_level=access, checksum=receipt.checksum,
            original_file=receipt.name, size=receipt.size, content=b'')

    def lot(self, code, item, quantity, **values):
        defaults = dict(location=self.here, revision='A', quality='approved', currency='UAH',
                        documents={'certificate': self.certificate.pk})
        defaults.update(values)
        return Lot.objects.create(code=code, item=item, quantity=quantity, **defaults)

    def line(self, code, item, quantity, shipped='0'):
        order = SalesOrder.objects.create(code=code, customer=self.customer, owner=self.owner,
            fulfillment_location=self.here, status='confirmed', currency='UAH', due_date=date(2026, 9, 25))
        return SalesLine.objects.create(order=order, item=item, revision='A', quantity=quantity,
                                       shipped=shipped, price='10.00')

    def policy(self, user=None):
        return Policy(SimpleNamespace(user=user or self.ceo, session={}))

    def row(self, data, name, pk, key='id'):
        return next(row for row in data[name] if row[key] == pk)

    def corrupt_certificate(self):
        path = self.media / self.certificate.original_file.name
        raw = path.read_bytes()
        path.write_bytes(b'X' + raw[1:])  # Same size, genuine checksum mismatch.

    def test_ceo_snapshot_exactly_matches_pinned_reader(self):
        actual = queries.snapshot(self.policy())
        self.assertEqual(actual, self.original.snapshot(self.policy()))
        closed = self.row(actual, 'plans', self.closed_line.pk, 'line_id')
        self.assertEqual(D(closed['remaining']), 0)
        self.assertEqual(len(closed['materials']), 1)
        self.assertEqual(D(closed['materials'][0]['need']), 0)
        opened = self.row(actual, 'plans', self.open_line.pk, 'line_id')
        self.assertEqual((D(opened['reserved']), D(opened['free'])), (D(1), D(1)))
        self.assertEqual(self.row(actual, 'lots', self.blocked.pk)['missing_documents'], ['certificate'])

    def test_restricted_projection_and_visible_reservation_cache_miss_match_reference(self):
        actual = queries.snapshot(self.policy(self.manager))
        self.assertEqual(actual, self.original.snapshot(self.policy(self.manager)))
        self.assertNotIn(self.hidden.pk, [row['id'] for row in actual['lots']])
        self.assertNotIn(self.private.pk, [row['id'] for row in actual['documents']])
        # Narrow only the caller's Lot query. An otherwise permitted reservation
        # still carries its selected lot, so a missing fact must use live checks.
        original_filter = Policy.filter_queryset
        def narrower(policy, rows):
            allowed = original_filter(policy, rows)
            return allowed.exclude(pk=self.finished.pk) if rows.model is Lot else allowed
        with patch.object(Policy, 'filter_queryset', narrower):
            expected = self.original.snapshot(self.policy(self.manager))
            with patch.object(queries, 'usable', wraps=service.usable) as fallback:
                actual = queries.snapshot(self.policy(self.manager))
            self.assertEqual(actual, expected)
            self.assertTrue(any(call.args[0].pk == self.finished.pk and call.args[1] == 'A'
                                for call in fallback.call_args_list))
            self.assertEqual(D(self.row(actual, 'plans', self.open_line.pk, 'line_id')['reserved']), 1)

    def test_actual_file_verifications_once_per_lot_per_snapshot(self):
        store = private_storage.private_document_storage
        expected = Counter(lot.documents['certificate'] for lot in Lot.objects.all()
                           if 'certificate' in lot.documents)
        names = {doc.pk: doc.original_file.name for doc in Document.objects.all()}
        expected_files = Counter({names[pk]: count for pk, count in expected.items()})
        # wraps delegates to the physical reader; no admission or bytes are mocked.
        with patch.object(store, 'read_verified', wraps=store.read_verified) as verified:
            first = queries.snapshot(self.policy())
            self.assertEqual(Counter(call.args[0] for call in verified.call_args_list), expected_files)
            verified.reset_mock()
            second = queries.snapshot(self.policy())
            self.assertEqual(Counter(call.args[0] for call in verified.call_args_list), expected_files)
            self.assertEqual(first, second)

    def test_same_policy_transaction_next_snapshot_refreshes_reservations_and_quality(self):
        policy = self.policy()
        with transaction.atomic():
            first = queries.snapshot(policy)
            Reservation.objects.filter(pk=self.reserve.pk).update(quantity='2')
            Lot.objects.filter(pk=self.part.pk).update(quality='blocked')
            second = queries.snapshot(policy)
        self.assertEqual(D(self.row(first, 'lots', self.finished.pk)['available']), 1)
        self.assertEqual((D(self.row(second, 'lots', self.finished.pk)['reserved']),
                          D(self.row(second, 'lots', self.finished.pk)['available'])), (D(2), D(0)))
        self.assertEqual(D(self.row(second, 'lots', self.part.pk)['available']), 0)
        self.assertEqual(second['summary']['blocked_lots'], first['summary']['blocked_lots'] + 1)
        self.assertEqual(second, self.original.snapshot(policy))

    def test_next_snapshot_rechecks_physically_corrupted_document(self):
        policy = self.policy()
        first = queries.snapshot(policy)
        self.assertEqual(self.row(first, 'lots', self.part.pk)['missing_documents'], [])
        self.corrupt_certificate()
        second = queries.snapshot(policy)
        self.assertEqual(self.row(second, 'lots', self.part.pk)['missing_documents'], ['certificate'])
        self.assertEqual(D(self.row(second, 'lots', self.part.pk)['available']), 0)
        self.assertGreater(second['summary']['blocked_lots'], first['summary']['blocked_lots'])
        self.assertEqual(second, self.original.snapshot(policy))

    def test_next_snapshot_rechecks_newer_document_version(self):
        policy = self.policy()
        first = queries.snapshot(policy)
        self.assertEqual(self.row(first, 'lots', self.part.pk)['missing_documents'], [])
        newer = self.document('FACT-CERT', 'B', b'synthetic certificate B')
        second = queries.snapshot(policy)
        self.assertEqual(self.row(second, 'lots', self.part.pk)['missing_documents'], ['certificate'])
        Lot.objects.filter(pk=self.part.pk).update(documents={'certificate': newer.pk})
        third = queries.snapshot(policy)
        self.assertEqual(self.row(third, 'lots', self.part.pk)['missing_documents'], [])
        self.assertEqual(D(self.row(third, 'lots', self.part.pk)['available']), 8)
        self.assertEqual(third, self.original.snapshot(policy))

    def test_standalone_plan_keeps_live_checks_and_revision_short_circuit(self):
        item = Item.objects.create(code='FACT-BUY', name='Buy', revision='A',
                                  required_documents=['certificate'], currency='UAH')
        line = self.line('FACT-BUY-SO', item, '2')
        line.refresh_from_db()
        blocked = self.lot('FACT-BUY-BLOCKED', item, '9', quality='blocked')
        wrong_revision = self.lot('FACT-BUY-B', item, '4', revision='B')
        Reservation.objects.create(lot=wrong_revision, line=line, quantity='1')
        with patch.object(service, 'accepted_documents', wraps=service.accepted_documents) as admission:
            first = queries.plan_line(line, self.policy())
            self.assertEqual(admission.call_count, 0)  # Quality and revision short circuits.
        self.assertEqual((D(first['free']), D(first['reserved'])), (D(0), D(0)))
        Lot.objects.filter(pk=blocked.pk).update(quality='approved')
        second = queries.plan_line(line, self.policy())
        self.assertEqual(D(second['free']), 9)
        self.corrupt_certificate()
        third = queries.plan_line(line, self.policy())
        self.assertEqual(D(third['free']), 0)
        self.assertEqual(third, self.original.plan_line(line, self.policy()))
