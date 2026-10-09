"""«Таблиця за посиланням»: CSV, JSON or Excel from any other server's public https link. Read-only.

Synthetic only: name resolution and the HTTPS exchange are replaced by local functions; no network.
"""
from datetime import timedelta
import io
import json
import socket
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone

from . import periodic, sources
from .models import Connector


def resolver(*addresses):
    family = lambda a: socket.AF_INET6 if ':' in a else socket.AF_INET
    return lambda host, port, **kw: [(family(a), socket.SOCK_STREAM, 6, '', (a, port)) for a in addresses]


class FetchUrlTests(SimpleTestCase):
    def fetch(self, url, body, kind='', addresses=('93.184.216.34',)):
        seen = []

        def get(host, address, path):
            seen.append((host, address, path))
            return body, kind
        with mock.patch.object(sources.socket, 'getaddrinfo', side_effect=resolver(*addresses)):
            return sources.fetch_url(url, get=get), seen

    def test_csv_json_and_excel_from_a_public_link(self):
        table, seen = self.fetch('https://export.example.com/orders.csv?token=abc', 'Номер;Сума\nZM-1;10\n'.encode())
        self.assertEqual((table['columns'], table['rows']), (['Номер', 'Сума'], [['ZM-1', '10']]))
        self.assertEqual(seen, [('export.example.com', ('93.184.216.34', 443), '/orders.csv?token=abc')])
        rows = [{'code': 'ZM-1', 'amount': 10.5, 'tags': ['a']}, {'code': 'ZM-2', 'customer': None}]
        table, _ = self.fetch('https://api.example.com/v1/orders', json.dumps({'data': rows}).encode(), 'application/json')
        self.assertEqual(table['columns'], ['code', 'amount', 'tags', 'customer'])
        self.assertEqual(table['rows'], [['ZM-1', '10.5', '["a"]', ''], ['ZM-2', '', '', '']])
        table, _ = self.fetch('https://api.example.com/rows', b'[["A","B"],["1","2"]]')
        self.assertEqual((table['columns'], table['rows']), (['A', 'B'], [['1', '2']]))
        from openpyxl import Workbook
        book, out = Workbook(), io.BytesIO()
        book.active.append(['Код', 'Залишок'])
        book.active.append(['MS-0253', 75])
        book.save(out)
        table, _ = self.fetch('https://files.example.com/stock', out.getvalue(), 'application/octet-stream')
        self.assertEqual(table['rows'], [['MS-0253', '75']])

    def test_only_public_https_addresses_are_read(self):
        for url in ('http://example.com/a.csv', 'ftp://example.com/a.csv', 'https://user:pass@example.com/a.csv',
                    'https://example.com:8443/a.csv', 'file:///etc/passwd', ''):
            with self.subTest(url=url), self.assertRaises(sources.SourceError):
                self.fetch(url, b'A\n1\n')
        for address in ('127.0.0.1', '10.0.0.5', '192.168.1.10', '172.16.0.1', '169.254.169.254', '100.64.0.1',
                        '0.0.0.0', '::1', 'fd00::1', 'fe80::1', '224.0.0.1'):
            with self.subTest(address=address), self.assertRaisesRegex(sources.SourceError, 'внутрішньої мережі'):
                self.fetch('https://intranet.example.com/a.csv', b'A\n1\n', addresses=('93.184.216.34', address))

    def test_pages_redirects_and_broken_answers_are_explained(self):
        with self.assertRaisesRegex(sources.SourceError, 'вебсторінка'):
            self.fetch('https://example.com/', b'<!DOCTYPE html><html></html>')
        with self.assertRaisesRegex(sources.SourceError, 'некоректний JSON'):
            self.fetch('https://example.com/a.json', b'{"data": [', 'application/json')
        with self.assertRaisesRegex(sources.SourceError, 'масив об’єктів'):
            self.fetch('https://example.com/a.json', b'{"total": 3}', 'application/json')
        with self.assertRaisesRegex(sources.SourceError, '5 МБ'):
            self.fetch('https://example.com/a.csv', b'A\n' + b'1\n' * (sources.MAX_BYTES // 2 + 1))
        with mock.patch.object(sources.socket, 'getaddrinfo', side_effect=socket.gaierror('nope')), \
                self.assertRaisesRegex(sources.SourceError, 'не знайдено'):
            sources.fetch_url('https://missing.example.com/a.csv', get=lambda *a: (b'A\n1\n', ''))

        class Response:
            def __init__(self, status):
                self.status = status

            def read(self, limit):
                return b'A\n1\n'

            def getheader(self, name, default=None):
                return 'text/csv'

        class Connection:
            status = 302

            def __init__(self, *args, **kwargs):
                pass

            def request(self, *args, **kwargs):
                pass

            def getresponse(self):
                return Response(Connection.status)

            def close(self):
                pass
        context = mock.Mock()
        with mock.patch.object(sources.socket, 'getaddrinfo', side_effect=resolver('93.184.216.34')), \
                mock.patch.object(sources.socket, 'create_connection') as connect, \
                mock.patch.object(sources.ssl, 'create_default_context', return_value=context), \
                mock.patch.object(sources.http.client, 'HTTPSConnection', Connection):
            with self.assertRaisesRegex(sources.SourceError, 'перенаправляє'):
                sources.fetch_url('https://example.com/a.csv')
            connect.assert_called_with(('93.184.216.34', 443), timeout=sources.FETCH_TIMEOUT)
            context.wrap_socket.assert_called_with(connect.return_value, server_hostname='example.com')
            Connection.status = 403
            with self.assertRaisesRegex(sources.SourceError, '403'):
                sources.fetch_url('https://example.com/a.csv')
            Connection.status = 200
            self.assertEqual(sources.fetch_url('https://example.com/a.csv')['rows'], [['1']])


class UrlConnectorTests(TransactionTestCase):
    def setUp(self):
        self.addCleanup(periodic.stop)
        user = get_user_model().objects.create_user(username='synthetic-ceo', password='synthetic-pass')
        Group.objects.get_or_create(name='ceo')[0].user_set.add(user)
        self.client.force_login(user)

    def post(self, path, **data):
        return self.client.post('/api/connectors/' + path, data)

    def test_a_linked_server_is_previewed_created_refreshed_and_read_periodically(self):
        body = json.dumps([{'Номер': 'ZM-1', 'Клієнт': 'Синтетичний'}]).encode()
        served = {'body': body}
        with mock.patch.object(sources.socket, 'getaddrinfo', side_effect=resolver('93.184.216.34')), \
                mock.patch.object(sources, '_https_get', side_effect=lambda *a: (served['body'], 'application/json')):
            preview = self.post('preview/', kind='url', url='https://api.example.com/orders', dataset='other')
            self.assertEqual(preview.status_code, 200, preview.content)
            created = self.post('create/', kind='url', url='https://api.example.com/orders', dataset='other',
                                name='Замовлення з іншого сервера', expected_sha256=preview.json()['sha256'])
            self.assertEqual(created.status_code, 201, created.content)
            connector = Connector.objects.get()
            self.assertEqual((connector.kind, connector.source_url), ('url', 'https://api.example.com/orders'))
            served['body'] = json.dumps([{'Номер': 'ZM-1'}, {'Номер': 'ZM-2'}]).encode()
            refreshed = self.post(f'{connector.pk}/sync/')
            self.assertEqual(refreshed.status_code, 200, refreshed.content)
            self.assertEqual(connector.snapshots.first().row_count, 2)
            Connector.objects.filter(pk=connector.pk).update(last_sync_at=timezone.now() - timedelta(hours=1))
            served['body'] = json.dumps([{'Номер': 'ZM-3'}]).encode()
            self.assertEqual(periodic.run_once(), {'synced': [connector.pk], 'failed': []})
        self.assertEqual(connector.snapshots.first().rows, [['ZM-3']])
        catalog = {c['kind']: c for c in self.client.get('/api/connectors/').json()['catalog']}
        self.assertEqual(catalog['url']['state'], 'available')

    def test_an_internal_address_is_refused_before_any_request(self):
        sent = []
        with mock.patch.object(sources.socket, 'getaddrinfo', side_effect=resolver('192.168.0.10')), \
                mock.patch.object(sources, '_https_get', side_effect=lambda *a: sent.append(a)):
            response = self.post('preview/', kind='url', url='https://router.example.com/export.csv', dataset='other')
        self.assertEqual(response.status_code, 422)
        self.assertIn('внутрішньої мережі', response.json()['error'])
        self.assertEqual((sent, Connector.objects.count()), ([], 0))
