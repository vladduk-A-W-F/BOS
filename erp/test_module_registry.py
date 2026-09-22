"""CORE-MODULE-REGISTRY: new isolated HTTP/descriptor contracts only."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import re
from unittest.mock import patch

from django.conf import settings
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from boss_project.policy import CEO_ACTIONS
from erp import module_registry as registry
from erp.models import Event, Lot, PaymentRetention, StockTransfer
from erp.service import SCHEMAS
from operations.models import ActionProposal, Configuration, Invoice
from scripts.check_support import login_test_client


@override_settings(BOS_DATA_MODE='working', DEBUG=False, ANTHROPIC_API_KEY='',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ModuleRegistryTests(TestCase):
    def client_for(self, role, capabilities=('view_document', 'export_workspace')):
        client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        user = login_test_client(client, role, capabilities=capabilities)
        return client, user

    def get(self, client):
        response = client.get('/api/erp/modules/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertIn('Cookie', response['Vary'])
        return response.json()

    def test_authentication_role_revocation_and_read_only_http_contract(self):
        self.assertEqual(Client().get('/api/erp/modules/').status_code, 401)
        client, user = self.client_for('ceo')
        self.get(client)
        post = client.post('/api/erp/modules/', {}, content_type='application/json',
                           HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertEqual(post.status_code, 405)
        self.assertEqual(post['Cache-Control'], 'private, no-store')
        user.groups.clear()
        self.assertEqual(client.get('/api/erp/modules/').status_code, 403)

    def test_ceo_descriptor_references_resolve_to_existing_models_routes_and_forms(self):
        client, _ = self.client_for('ceo')
        data = self.get(client)
        self.assertEqual(data['schema'], 'bos.modules.v1')
        self.assertEqual(data['data']['schema'], 'bos.network.v1')
        self.assertEqual(data['data']['endpoint'], '/api/erp/network/')
        self.assertEqual(reverse('bos-modules'), '/api/erp/modules/')
        models = {model['id']: model for model in data['models']}
        actions = {action['id']: action for action in data['actions']}
        modules = {module['id']: module for module in data['modules']}
        views = {view['id'] for view in data['views']}
        self.assertEqual(set(models), {'points', 'lots', 'purchases', 'orders', 'jobs', 'transfers', 'invoices', 'retentions'})
        self.assertEqual(views, {'control', 'flow', 'network', 'focus'})
        self.assertEqual(models['invoices']['key'], 'invoice_id')
        self.assertEqual(models['purchases']['status_field'], 'effective_status')
        frontend = (Path(settings.BASE_DIR) / 'frontend/boss_app_source.html').read_text()
        forms = frontend.split('const ERP_ACTIONS={', 1)[1].split('\n};', 1)[0]
        form_ids = set(re.findall(r'^\s*([a-z_]+):\[', forms, flags=re.MULTILINE))
        for model in models.values():
            self.assertEqual(model['source']['rows'], 'rows.' + model['id'])
            self.assertTrue(set(model['actions']).issubset(actions))
            self.assertTrue(set(model['views']).issubset(views))
            self.assertTrue(all(relation['target'] in models for relation in model['relations']))
        for action in actions.values():
            self.assertIn(action['model'], models)
            self.assertIn(action['ui_action'], form_ids)
            self.assertEqual(action['id'], 'erp_' + action['ui_action'])
            self.assertIn(action['ui_action'], SCHEMAS)
            self.assertTrue(resolve(action['preview_endpoint']).func)
            self.assertTrue(resolve(action['confirm_endpoint']).func)
        for module in modules.values():
            self.assertTrue(set(module['depends']).issubset(modules))
            self.assertTrue(set(module['models']).issubset(models))
            self.assertTrue(set(module['actions']).issubset(actions))
        self.assertTrue(any(column['type'] == 'money' for model in models.values() for column in model['columns']))

    def test_manager_financial_descriptors_and_ceo_actions_are_absent(self):
        client, _ = self.client_for('manager')
        data = self.get(client)
        self.assertFalse(data['permissions']['finance'])
        self.assertTrue(data['permissions']['write'])
        self.assertIn('settlements', {module['id'] for module in data['modules']})
        self.assertNotIn('retentions', {model['id'] for model in data['models']})
        invoice = next(model for model in data['models'] if model['id'] == 'invoices')
        self.assertEqual({column['key'] for column in invoice['columns']}, {'code', 'customer_name', 'due_date', 'currency'})
        self.assertEqual(invoice['actions'], [])
        self.assertFalse(any(column['finance'] or column['type'] == 'money'
                             for model in data['models'] for column in model['columns']))
        action_ids = {action['id'] for action in data['actions']}
        self.assertTrue(action_ids.isdisjoint(CEO_ACTIONS | {'erp_invoice'}))
        self.assertIn('erp_transfer_receive', action_ids)
        # A client-supplied role/configuration never changes server metadata.
        self.assertEqual(client.get('/api/erp/modules/?role=ceo&modules=settlements').json(), data)

    def test_observer_has_no_actions_or_export_even_with_export_permission(self):
        client, _ = self.client_for('observer')
        data = self.get(client)
        self.assertEqual(data['actions'], [])
        self.assertFalse(data['permissions']['write'])
        self.assertFalse(data['permissions']['export'])
        self.assertIsNone(data['data']['export_endpoint'])
        self.assertTrue(all(not model['actions'] for model in data['models']))
        self.assertTrue(all(not module['actions'] for module in data['modules']))
        self.assertIn('invoices', {model['id'] for model in data['models']})
        self.assertNotIn('retentions', {model['id'] for model in data['models']})

    def test_get_uses_no_business_writer_and_leaves_business_state_unchanged(self):
        client, _ = self.client_for('ceo')
        classes = (Event, Lot, PaymentRetention, StockTransfer, ActionProposal, Invoice, Configuration)
        before = {model._meta.label: list(model.objects.values()) for model in classes}
        with patch('erp.service.dispatch', side_effect=AssertionError('Read called a writer')), \
                patch('erp.network.build', side_effect=AssertionError('Registry queried operational rows')), \
                CaptureQueriesContext(connection) as queries:
            self.get(client)
        self.assertEqual(before, {model._meta.label: list(model.objects.values()) for model in classes})
        self.assertFalse(any(re.match(r'^\s*(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP)\b', query['sql'], re.I)
                             for query in queries.captured_queries))

    def test_invalid_server_composition_fails_closed_without_partial_descriptors(self):
        client, _ = self.client_for('ceo')
        for config in (None, 'operations', [], ['operations', 'unknown'], ['operations', 'operations'],
                       ['sales'], ['operations', 'settlements'], ['operations', 7]):
            with self.subTest(config=config), override_settings(BOS_ENABLED_MODULES=config):
                response = client.get('/api/erp/modules/')
                self.assertEqual(response.status_code, 503, response.content)
                self.assertEqual(response.json()['code'], 'module_configuration_invalid')
                self.assertNotIn('models', response.json())
                self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_valid_subset_and_broken_writer_mapping_preserve_referential_integrity(self):
        client, _ = self.client_for('ceo')
        with override_settings(BOS_ENABLED_MODULES=['operations', 'warehouse', 'procurement']):
            data = self.get(client)
            self.assertEqual({model['id'] for model in data['models']}, {'points', 'lots', 'transfers', 'purchases'})
            purchase = next(model for model in data['models'] if model['id'] == 'purchases')
            self.assertEqual(purchase['relations'], [{'field': 'destination_id', 'target': 'points'}])
        bad = replace(registry.ACTIONS[0], id='erp_arbitrary_sql', ui_action='arbitrary_sql')
        with patch.object(registry, 'ACTIONS', (bad,) + registry.ACTIONS[1:]):
            response = client.get('/api/erp/modules/')
            self.assertEqual(response.status_code, 503, response.content)
            self.assertNotIn('arbitrary_sql', response.content.decode())

    def test_descriptor_constants_and_returned_documents_cannot_mutate_registry(self):
        client, _ = self.client_for('ceo')
        with self.assertRaises(FrozenInstanceError):
            registry.MODELS[0].name = 'Changed'
        first = self.get(client)
        first['models'][0]['columns'].clear()
        first['modules'].clear()
        second = self.get(client)
        self.assertTrue(second['models'][0]['columns'])
        self.assertEqual(len(second['modules']), 6)
