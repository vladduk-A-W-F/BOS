"""A06: real HTTP adapters keep one financial creation intent."""
from html.parser import HTMLParser
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from scripts.check_support import login_test_client
from finance.models import Transaction


class Inputs(HTMLParser):
    def __init__(self, html):
        super().__init__(); self.values = {}; self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input' and attrs.get('name'):
            self.values[attrs['name']] = attrs.get('value', '')


class FinancialIntentAdapterTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = login_test_client(self.client)
        self.data = dict(direction='in', amount='100.25', currency='EUR',
                         date='2026-09-11', description='Синтетичний дохід A06',
                         category='customer')

    def test_http_same_intent_returns_one_transaction(self):
        def send():
            return self.client.post('/api/transactions/', self.data,
                content_type='application/json', HTTP_IDEMPOTENCY_KEY='a06-http-one',
                HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)
        first, second = send(), send()
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(Transaction.objects.count(), 1)

    def test_http_missing_intent_does_not_create_ambiguous_money(self):
        response = self.client.post('/api/transactions/', self.data,
            content_type='application/json', HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(Transaction.objects.exists())

    def test_native_admin_supplies_stable_intent_and_resubmission_replays(self):
        User = get_user_model()
        admin = User.objects.create_superuser('a06-adapter-admin', '', 'a06-test-only')
        c = Client(enforce_csrf_checks=True)
        response = c.get('/admin/login/')
        response = c.post('/admin/login/', {'username': admin.username, 'password': 'a06-test-only',
            'next': '/admin/'}, HTTP_X_CSRFTOKEN=c.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 302)
        url = '/admin/finance/transaction/add/'
        response = c.get(url)
        self.assertEqual(response.status_code, 200)
        fields = Inputs(response.content.decode()).values
        self.assertIn('bos_operation_id', fields)
        self.assertTrue(fields['bos_operation_id'])
        payload = {**self.data, 'bos_operation_id': fields['bos_operation_id'], '_save': 'Зберегти'}
        for _ in range(2):
            response = c.post(url, payload, HTTP_X_CSRFTOKEN=c.cookies['csrftoken'].value)
            self.assertEqual(response.status_code, 302, response.content)
        self.assertEqual(Transaction.objects.count(), 1)

