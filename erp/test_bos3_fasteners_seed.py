"""Run only through verification_settings with a new explicit isolated SQLite path."""
from io import StringIO
import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings

from employees.models import Employee
from operations.models import Configuration, Invoice
from erp.models import Lot, Movement, Production, Purchase, SalesLine, SalesOrder
from erp.service import fingerprint


@override_settings(BOS_DATA_MODE='demo')
class Bos3FastenersSeedTests(TestCase):
    username = 'bos3-owner-test'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configured = os.environ.get('BOS_TEST_DB_NAME')
        # Match the existing isolated-import guard through override_settings.
        profile = settings._wrapped
        while getattr(profile, 'SETTINGS_MODULE', None) is None and hasattr(profile, 'default_settings'):
            profile = profile.default_settings
        if (os.environ.get('DJANGO_SETTINGS_MODULE') != 'verification_settings'
                or getattr(profile, 'SETTINGS_MODULE', None) != 'verification_settings'
                or os.environ.get('BOS_VERIFY_DB', 'sqlite') != 'sqlite'
                or not configured):
            raise RuntimeError('B30-QH01 requires verification_settings and explicit BOS_TEST_DB_NAME SQLite.')
        configured_path = Path(configured)
        actual_path = Path(str(connection.settings_dict['NAME']))
        if not configured_path.is_absolute() or 'bos3-fasteners' not in configured_path.name.lower():
            raise RuntimeError('B30-QH01 requires a new absolute BOS_TEST_DB_NAME containing bos3-fasteners.')
        expected_test_path = Path(str(configured_path.resolve()) + '_django_test')
        if actual_path.resolve() != expected_test_path.resolve():
            raise RuntimeError('B30-QH01 database binding differs from explicit verification SQLite test path.')

    def setUp(self):
        self.owner = get_user_model().objects.create_user(username=self.username, password='unused-test-password')
        self.environment = {
            'BOS3_TRAINING_ENABLED': '1',
            'BOS3_TRAINING_PROFILE': 'isolated-synthetic',
            'BOS3_TRAINING_DB_MARKER': 'bos3-fasteners-uk-v1',
            'BOS3_TRAINING_OWNER_USERNAME': self.username,
            'BOS3_TRAINING_INSTALLATION_ID': 'test-installation-bos3',
        }

    def seed(self):
        with patch.dict(os.environ, self.environment, clear=False):
            call_command('seed_bos3_fasteners', owner_username=self.username, stdout=StringIO())

    def test_creates_three_coherent_case_states_and_marker(self):
        self.seed()
        marker = Configuration.objects.get(key='bos3_fixture').value
        self.assertEqual((marker['id'], marker['schema'], marker['synthetic'], marker['as_of']),
            ('bos3-fasteners-uk-v1', 1, True, '2026-09-30'))
        self.assertEqual(marker['owner_user_id'], self.owner.pk)
        organization = Configuration.objects.get(key='organization').value
        self.assertEqual(organization['name'], 'ТОВ «МайстерКріплення» · навчальна фабрика')
        self.assertEqual(Employee.objects.get(user=self.owner).department, 'Продажі')
        c1 = marker['source_map']['BOS3-CASE-01']
        self.assertEqual((SalesOrder.objects.get(pk=c1['order_id']).lines.get(pk=c1['line_id']).quantity,
            Production.objects.get(pk=c1['production_id']).quantity,
            Purchase.objects.get(pk=c1['purchase_id']).quantity),
            (Decimal('500.000'), Decimal('360.000'), Decimal('120.000')))
        self.assertEqual(Lot.objects.get(pk=c1['lot_ids']['wash_600']).quantity, Decimal('600.000'))
        c2 = marker['source_map']['BOS3-CASE-02']
        self.assertEqual((Lot.objects.get(pk=c2['approved_lot_id']).quality,
            Lot.objects.get(pk=c2['blocked_lot_id']).quality), ('approved', 'blocked'))
        c3 = marker['source_map']['BOS3-CASE-03']
        invoice = Invoice.objects.get(pk=c3['invoice_id'])
        self.assertEqual((invoice.amount, invoice.paid, invoice.amount - invoice.paid),
            (Decimal('16400.00'), Decimal('10000.00'), Decimal('6400.00')))
        self.assertTrue(Movement.objects.filter(reference='B3-C3-SHP-303', kind='shipment').exists())
        self.assertFalse(Movement.objects.filter(reference='B3-C2-SHP-202', kind='shipment').exists())

    def test_exact_replay_is_noop_and_changed_owner_refuses(self):
        self.seed()
        before = fingerprint()
        self.seed()
        self.assertEqual(fingerprint(), before)
        other = get_user_model().objects.create_user(username='bos3-other-test', password='unused-test-password')
        changed = {**self.environment, 'BOS3_TRAINING_OWNER_USERNAME': other.username}
        with patch.dict(os.environ, changed, clear=False):
            with self.assertRaises(CommandError):
                call_command('seed_bos3_fasteners', owner_username=other.username, stdout=StringIO())
        self.assertEqual(fingerprint(), before)

    def test_missing_guard_refuses_before_writing_business_rows(self):
        without_enable = {key: value for key, value in self.environment.items() if key != 'BOS3_TRAINING_ENABLED'}
        with patch.dict(os.environ, without_enable, clear=True):
            with self.assertRaises(CommandError):
                call_command('seed_bos3_fasteners', owner_username=self.username, stdout=StringIO())
        self.assertFalse(Configuration.objects.exists())
        self.assertFalse(SalesLine.objects.exists())

    def test_existing_organization_refuses_without_replacing_identity(self):
        original = {'name': 'Existing synthetic organization'}
        Configuration.objects.create(key='organization', value=original)
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(Configuration.objects.get(key='organization').value, original)
        self.assertFalse(SalesLine.objects.exists())
