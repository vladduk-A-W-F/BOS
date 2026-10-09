"""Read-only MCP endpoint: off without a key, Bearer key only, the key holder's Policy, nothing written.

Synthetic demo company only; the AI client is played by the Django test client.
"""
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TransactionTestCase, override_settings

from erp.bos4_demo import seed_bos4_demo
from erp.service import fingerprint
from operations.models import Configuration
from . import mcp


@override_settings(BOS_DATA_MODE='demo', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class McpTests(TransactionTestCase):
    def setUp(self):
        folder = TemporaryDirectory(prefix='bos4-mcp-test-')
        self.addCleanup(folder.cleanup)
        override = override_settings(MEDIA_ROOT=Path(folder.name) / 'media')
        override.enable()
        self.addCleanup(override.disable)
        seed_bos4_demo()
        self.users = {}

    def user(self, role):
        if role not in self.users:
            user = get_user_model().objects.create_user(username='synthetic-' + role, password='synthetic-pass')
            Group.objects.get_or_create(name=role)[0].user_set.add(user)
            self.users[role] = user
        return self.users[role]

    def key(self, role):
        out = StringIO()
        call_command('mcp_access', 'create', '--user', self.user(role).username, '--label', 'синтетичний клієнт',
                     stdout=out)
        return next(line for line in out.getvalue().splitlines() if line.startswith(mcp.PREFIX))

    def rpc(self, token, method, params=None, message_id=1, **headers):
        body = {'jsonrpc': '2.0', 'method': method, **({'params': params} if params is not None else {})}
        if message_id is not None:
            body['id'] = message_id
        if token:
            headers['HTTP_AUTHORIZATION'] = 'Bearer ' + token
        return self.client.post('/mcp/', json.dumps(body), content_type='application/json', **headers)

    def call(self, token, name, **arguments):
        response = self.rpc(token, 'tools/call', {'name': name, 'arguments': arguments})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()['result']

    def test_off_until_a_key_is_issued(self):
        self.assertEqual(self.rpc(None, 'initialize').status_code, 404)
        self.assertFalse(Configuration.objects.filter(key=mcp.KEY).exists())

    def test_a_ceo_client_initializes_lists_and_reads(self):
        token = self.key('ceo')
        before = fingerprint()
        hello = self.rpc(token, 'initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                                               'clientInfo': {'name': 'synthetic', 'version': '0'}})
        self.assertEqual(hello.status_code, 200)
        result = hello.json()['result']
        self.assertEqual((result['protocolVersion'], result['serverInfo']['name']), ('2025-03-26', 'bos'))
        self.assertIn('tools', result['capabilities'])
        self.assertEqual(self.rpc(token, 'notifications/initialized', message_id=None).status_code, 202)
        self.assertEqual(self.rpc(token, 'ping').json()['result'], {})
        listed = self.rpc(token, 'tools/list').json()['result']['tools']
        self.assertEqual([t['name'] for t in listed], ['monitoring_overview', 'standard_query', 'order_status'])
        self.assertTrue(all(t['annotations']['readOnlyHint'] and not t['annotations']['destructiveHint'] for t in listed))
        self.assertIn('debts', listed[1]['inputSchema']['properties']['key']['enum'])

        overview = self.call(token, 'monitoring_overview')
        self.assertFalse(overview['isError'])
        data = overview['structuredContent']
        self.assertEqual(json.loads(overview['content'][0]['text']), data)
        self.assertEqual(data['as_of'], '2026-10-05')
        self.assertIn('invoices', {n['key'] for n in data['numbers']})
        self.assertTrue(any('Офіс Сіті' in a['title'] for a in data['attention']))
        self.assertEqual(data['bento']['orders']['open'], next(n['value'] for n in data['numbers'] if n['key'] == 'orders'))
        self.assertTrue(data['bento']['money'])
        debts = self.call(token, 'standard_query', key='debts')['structuredContent']
        self.assertEqual(debts['title'], 'Хто винен і скільки')
        self.assertIn('RF-0137', [row[0] for row in debts['rows']])
        order = self.call(token, 'order_status', code='ZM-0141')['structuredContent']
        self.assertEqual((order['customer'], order['status'], order['currency']), ('ТОВ «Логістик Парк»', 'Підтверджено', 'UAH'))
        self.assertIn('price', order['lines'][0])
        self.assertEqual(set(order['next_step']), {'title', 'why'})          # words only, never an action payload
        self.assertEqual(fingerprint(), before)

    def test_an_observer_key_sees_what_an_observer_sees(self):
        token = self.key('observer')
        listed = self.rpc(token, 'tools/list').json()['result']['tools']
        self.assertNotIn('debts', listed[1]['inputSchema']['properties']['key']['enum'])
        refused = self.call(token, 'standard_query', key='debts')
        self.assertTrue(refused['isError'])
        data = self.call(token, 'monitoring_overview')['structuredContent']
        self.assertNotIn('invoices', {n['key'] for n in data['numbers']})
        self.assertNotIn('винен', json.dumps(data['attention'], ensure_ascii=False))
        self.assertEqual(data['bento']['money'], [])
        # Exactly the orders the observer's screens show: others answer «not found», never with their content.
        from boss_project.policy import Policy
        from erp.models import SalesOrder
        visible = set(Policy.for_user(self.user('observer')).queryset(SalesOrder).values_list('code', flat=True))
        for order in SalesOrder.objects.order_by('code'):
            reply = self.call(token, 'order_status', code=order.code)
            self.assertEqual(reply['isError'], order.code not in visible, order.code)
            if order.code in visible:
                self.assertNotIn('price', reply['structuredContent']['lines'][0])
                self.assertNotIn('currency', reply['structuredContent'])
            else:
                self.assertNotIn(order.customer.name, json.dumps(reply, ensure_ascii=False))
        self.assertTrue(self.call(token, 'order_status', code='ZM-9999')['isError'])

    def test_only_a_valid_bearer_key_from_a_non_browser_client_is_accepted(self):
        token = self.key('ceo')
        self.assertEqual(self.rpc(None, 'tools/list').status_code, 401)
        self.assertEqual(self.rpc(token + 'x', 'tools/list').status_code, 401)
        self.client.force_login(self.user('ceo'))                     # a signed-in browser session alone is not enough
        self.assertEqual(self.rpc(None, 'tools/list').status_code, 401)
        self.assertEqual(self.rpc(token, 'tools/list', HTTP_ORIGIN='https://example.test').status_code, 403)
        self.assertEqual(self.client.get('/mcp/', HTTP_AUTHORIZATION='Bearer ' + token).status_code, 405)
        self.user('ceo').groups.clear()                                # the holder lost the BoS role
        self.assertEqual(self.rpc(token, 'tools/list').status_code, 403)

    def test_protocol_errors(self):
        token = self.key('ceo')
        self.assertEqual(self.rpc(token, 'resources/list').json()['error']['code'], -32601)
        self.assertEqual(self.rpc(token, 'tools/call', {'name': 'delete_everything'}).json()['error']['code'], -32602)
        bad = self.client.post('/mcp/', '{', content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + token)
        self.assertEqual(bad.json()['error']['code'], -32700)
        batch = self.client.post('/mcp/', json.dumps([{'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}]),
                                 content_type='application/json', HTTP_AUTHORIZATION='Bearer ' + token)
        self.assertEqual(batch.json()['error']['code'], -32600)
        self.assertEqual(self.rpc(token, 'initialize', {'protocolVersion': '1999-01-01'}).json()['result']['protocolVersion'],
                         mcp.VERSIONS[0])
        from unittest import mock
        with mock.patch.dict(mcp.CALLS, {'monitoring_overview': mock.Mock(side_effect=RuntimeError('синтетичний збій'))}), \
                self.assertLogs('bos.connectors', 'ERROR'):
            failed = self.rpc(token, 'tools/call', {'name': 'monitoring_overview', 'arguments': {}})
        self.assertEqual((failed.status_code, failed.json()['error']['code']), (200, -32603))
        self.assertNotIn('синтетичний збій', failed.content.decode())

    def test_connections_page_shows_the_ceo_whether_mcp_is_on(self):
        for role in ('ceo', 'manager', 'observer'):
            self.client.force_login(self.user(role))
            data = self.client.get('/api/connectors/').json()
            if role == 'ceo':
                self.assertEqual(data['mcp'], {'enabled': False, 'path': '/mcp/', 'keys': []})
            else:
                self.assertNotIn('mcp', data)
        self.key('ceo')
        self.client.force_login(self.user('ceo'))
        shown = self.client.get('/api/connectors/').json()['mcp']
        self.assertTrue(shown['enabled'])
        self.assertEqual([(k['user'], k['label']) for k in shown['keys']], [('synthetic-ceo', 'синтетичний клієнт')])
        self.assertNotIn(mcp.keys()[0]['sha256'], json.dumps(shown))

    def test_keys_are_stored_as_hashes_listed_and_revoked(self):
        token = self.key('ceo')
        stored = json.dumps(Configuration.objects.get(key=mcp.KEY).value)
        self.assertNotIn(token, stored)
        entry = mcp.keys()[0]
        self.assertEqual((entry['user_id'], entry['label']), (self.user('ceo').pk, 'синтетичний клієнт'))
        listed = StringIO()
        call_command('mcp_access', 'list', stdout=listed)
        self.assertIn(entry['id'], listed.getvalue())
        self.assertNotIn(token, listed.getvalue())
        call_command('mcp_access', 'revoke', entry['id'], stdout=StringIO())
        self.assertEqual(self.rpc(token, 'tools/list').status_code, 404)              # no keys left: off again
        with self.assertRaises(CommandError):
            call_command('mcp_access', 'revoke', entry['id'], stdout=StringIO())
        nobody = get_user_model().objects.create_user(username='synthetic-norole', password='synthetic-pass')
        with self.assertRaises(CommandError):
            call_command('mcp_access', 'create', '--user', nobody.username, stdout=StringIO())
