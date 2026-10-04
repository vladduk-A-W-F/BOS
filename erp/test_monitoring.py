"""BoS 4 monitoring API over the synthetic demo company: read-only, role-scoped."""
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TransactionTestCase, override_settings

from .bos4_demo import seed_bos4_demo
from .service import fingerprint


@override_settings(BOS_DATA_MODE='demo', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class MonitoringTests(TransactionTestCase):
    def setUp(self):
        folder = TemporaryDirectory(prefix='bos4-monitoring-test-')
        self.addCleanup(folder.cleanup)
        override = override_settings(MEDIA_ROOT=Path(folder.name) / 'media')
        override.enable()
        self.addCleanup(override.disable)
        seed_bos4_demo()

    def login(self, role):
        user = get_user_model().objects.create_user(username='synthetic-' + role, password='synthetic-pass')
        Group.objects.get_or_create(name=role)[0].user_set.add(user)
        self.client.force_login(user)

    def table(self, data, key):
        return next(t for t in data['tables'] if t['key'] == key)

    def test_ceo_sees_numbers_tables_and_debts(self):
        self.login('ceo')
        before = fingerprint()
        data = self.client.get('/api/erp/monitoring/').json()
        self.assertEqual(fingerprint(), before)
        self.assertEqual(data['as_of'], '2026-10-05')
        self.assertEqual([t['key'] for t in data['tables']], ['orders', 'lots', 'invoices', 'tasks', 'movements'])
        orders = self.table(data, 'orders')
        self.assertEqual({r['cells'][0] for r in orders['rows']}, {'ZM-0141', 'ZM-0144', 'ZM-0146'})
        late = next(r for r in orders['rows'] if r['cells'][0] == 'ZM-0144')
        self.assertTrue(late['late'])
        self.assertEqual(late['cells'][4], '90 з 100')
        lots = self.table(data, 'lots')
        self.assertIn('KM-L-SHM-2-0918', [r['cells'][4] for r in lots['rows']])
        debts = {r['cells'][0]: r['cells'] for r in self.table(data, 'invoices')['rows']}
        self.assertEqual(debts['RF-0137'][4], 168000)
        self.assertEqual(debts['RF-0137'][6], 4)
        self.assertNotIn('RF-0139', debts)
        tasks = self.table(data, 'tasks')['rows']
        self.assertTrue(all(r['late'] for r in tasks[:sum(r['late'] for r in tasks)]))
        numbers = {n['key']: n['value'] for n in data['numbers']}
        self.assertEqual(numbers['invoices'], 168000 + 777700)
        self.assertEqual(numbers['purchases'], 2)

    def test_standard_queries(self):
        self.login('ceo')
        keys = [q['key'] for q in self.client.get('/api/erp/monitoring/').json()['queries']]
        self.assertEqual(len(keys), 6)
        debts = self.client.get('/api/erp/monitoring/query/debts/').json()
        self.assertEqual(debts['title'], 'Хто винен і скільки')
        self.assertEqual(debts['rows'][0]['cells'][0], 'RF-0137')
        late = self.client.get('/api/erp/monitoring/query/late_orders/').json()
        self.assertEqual([r['cells'][0] for r in late['rows']], ['ZM-0144'])
        po = self.client.get('/api/erp/monitoring/query/late_purchases/').json()
        self.assertEqual([r['cells'][0] for r in po['rows']], ['ZK-0311', 'ZK-0309'])
        today = self.client.get('/api/erp/monitoring/query/received_today/').json()
        self.assertTrue(today['rows'])
        self.assertEqual(self.client.get('/api/erp/monitoring/query/unknown/').status_code, 422)

    def test_observer_gets_no_money(self):
        self.login('observer')
        data = self.client.get('/api/erp/monitoring/').json()
        self.assertNotIn('invoices', [t['key'] for t in data['tables']])
        self.assertNotIn('invoices', [n['key'] for n in data['numbers']])
        self.assertEqual(len(self.table(data, 'orders')['columns']), 5)
        self.assertNotIn('debts', [q['key'] for q in data['queries']])
        self.assertEqual(self.client.get('/api/erp/monitoring/query/debts/').status_code, 403)

    def test_anonymous_and_writes_refused(self):
        self.assertIn(self.client.get('/api/erp/monitoring/').status_code, (401, 403))
        self.login('ceo')
        self.assertEqual(self.client.post('/api/erp/monitoring/').status_code, 405)

    def test_showcase_is_public_only_for_demo(self):
        data = self.client.get('/api/erp/showcase/').json()
        self.assertEqual(data['company'], 'Каркас Меблі · демо')
        self.assertEqual([c['title'] for c in data['cases']], ['Комплектуючі для партії меблів',
            'Відвантаження лише допущеної партії', 'Рахунок, оплата й нагадування'])
        self.assertTrue(all(3 <= len(c['steps']) <= 4 for c in data['cases']))
        with override_settings(BOS_DATA_MODE='production'):
            # Outside demo the address is not public at all.
            self.assertEqual(self.client.get('/api/erp/showcase/').status_code, 401)
