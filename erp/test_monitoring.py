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
        self.assertEqual(next(r for r in orders['rows'] if r['cells'][0] == 'ZM-0141')['cells'][4], '120 з 254')
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
        self.assertEqual(numbers['purchases'], 1)

    def test_attention_lists_what_needs_a_decision_in_plain_words(self):
        self.login('ceo')
        data = self.client.get('/api/erp/monitoring/').json()
        items = data['attention']
        titles = [a['title'] for a in items]
        # Titles name the customer or the product; the record code stays in the detail.
        self.assertEqual(titles[0], 'Замовлення для ТОВ «Офіс Сіті» прострочене на 2 дні')
        self.assertIn('ТОВ «Агроснаб Дніпро» винен 168 000 грн', titles)
        self.assertIn('Шафа металева ШМ-2, двостулкова: партія заблокована', titles)
        self.assertIn('Фарба порошкова сіра RAL 7035: постачання запізнюється на 2 дні', titles)
        details = ' '.join(a['detail'] for a in items)
        for code in ('ZM-0144', 'KM-L-SHM-2-0918', 'ZK-0309'):
            self.assertIn(code, details)
            self.assertFalse(any(code in t for t in titles))
        self.assertNotIn('ZK-0311', details)
        # Worst first: every danger item comes before any warning.
        levels = [a['level'] for a in items]
        self.assertEqual(levels, sorted(levels, key=lambda l: l != 'danger'))
        self.assertTrue(all(a['ref']['kind'] and a['ref']['id'] for a in items))
        self.assertLessEqual(len(items), 8)

    def test_foreign_currency_debt_keeps_its_currency_and_is_not_added_to_hryvnia(self):
        from datetime import date
        from operations.models import Invoice
        customer = Invoice.objects.get(code='RF-0137').customer
        Invoice.objects.create(code='RF-EUR-1', customer=customer, amount='1000.00', paid='250.00', currency='EUR',
                               due_date=date(2026, 9, 30))
        self.login('ceo')
        data = self.client.get('/api/erp/monitoring/').json()
        numbers = {n['key']: (n['label'], n['value']) for n in data['numbers']}
        self.assertEqual(numbers['invoices'], ('До оплати, грн', 168000 + 777700))
        self.assertEqual(numbers['invoices_eur'], ('До оплати, EUR', 750))
        debts = {r['cells'][0]: r['cells'] for r in self.table(data, 'invoices')['rows']}
        self.assertEqual((debts['RF-EUR-1'][4], debts['RF-EUR-1'][7]), (750, 'EUR'))
        self.assertEqual(debts['RF-0137'][7], 'UAH')
        self.assertNotIn('грн', ''.join(self.table(data, 'invoices')['columns']))
        titles = [a['title'] for a in data['attention']]
        self.assertIn(f'{customer.name} винен 750 EUR', titles)
        self.assertIn(f'{customer.name} винен 168 000 грн', titles)
        orders = self.table(data, 'orders')
        self.assertEqual(orders['columns'][-2:], ['Сума', 'Валюта'])
        self.assertTrue(all(r['cells'][-1] == 'UAH' for r in orders['rows']))

    def test_connected_sources_are_a_separate_block(self):
        from connectors.models import Connector, ConnectorSnapshot
        from django.utils import timezone
        self.login('ceo')
        before = self.client.get('/api/erp/monitoring/').json()
        self.assertEqual((before['sources'], before['source_attention']), ([], []))
        owner = get_user_model().objects.get(username='synthetic-ceo')
        source = Connector.objects.create(kind='csv', name='Замовлення з Excel', dataset='orders', created_by=owner,
                                          mapping={'code': 'Номер', 'customer': 'Клієнт'}, last_sync_at=timezone.now())
        ConnectorSnapshot.objects.create(connector=source, columns=['Номер', 'Клієнт'], rows=[['ЗМ-1', 'ТОВ Ліс']],
                                         row_count=1, sha256='0' * 64)
        data = self.client.get('/api/erp/monitoring/').json()
        self.assertEqual(data['sources'][0]['table']['rows'][0]['cells'], ['ЗМ-1', 'ТОВ Ліс'])
        self.assertEqual(data['source_attention'], [])
        # ERP tables and attention are unchanged by a connected source.
        self.assertEqual((data['tables'], data['attention']), (before['tables'], before['attention']))

    def test_attention_has_no_money_for_observer(self):
        self.login('observer')
        items = self.client.get('/api/erp/monitoring/').json()['attention']
        self.assertTrue(items)
        self.assertFalse(any('грн' in a['title'] + a['detail'] for a in items))
        self.assertNotIn('invoice', [a['ref']['kind'] for a in items])

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
        self.assertEqual([r['cells'][0] for r in po['rows']], ['ZK-0309'])
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

    def test_showcase_wording_comes_from_code_for_an_installed_demo(self):
        from operations.models import Configuration
        row = Configuration.objects.get(key='demo_cases')
        stored = row.value
        stored['cases'][0]['steps'][0]['text'] = 'ZM-0141: стара редакція'
        row.value = stored
        row.save()
        step = self.client.get('/api/erp/showcase/').json()['cases'][0]['steps'][0]
        self.assertEqual(step['text'], 'Замовлення на 254 вироби на 1 922 800 грн; під нього закуплено 300 кутників')

    def test_showcase_is_public_only_for_demo(self):
        data = self.client.get('/api/erp/showcase/').json()
        self.assertEqual(data['company'], 'Каркас Меблі · демо')
        self.assertEqual([c['title'] for c in data['cases']], ['Комплектуючі для партії меблів',
            'Відвантаження лише допущеної партії', 'Рахунок, оплата й нагадування'])
        self.assertTrue(all(3 <= len(c['steps']) <= 4 for c in data['cases']))
        # A person reads plain words: no internal record codes, and only public fields leave the server.
        import re
        code = re.compile(r'\b[A-Z]{2,4}-[A-Z0-9-]*\d')
        for case in data['cases']:
            self.assertEqual(set(case), {'key', 'title', 'summary', 'result', 'steps'})
            for step in case['steps']:
                self.assertEqual(set(step), {'title', 'text'})
                self.assertIsNone(code.search(step['text']), step['text'])
            self.assertIsNone(code.search(case['summary'] + case['result']['value']))
        with override_settings(BOS_DATA_MODE='production'):
            # Outside demo the address is not public at all.
            self.assertEqual(self.client.get('/api/erp/showcase/').status_code, 401)
