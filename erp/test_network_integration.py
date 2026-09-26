"""Composition of independently tested workflow and network HTTP projections."""
import json
from unittest.mock import patch
from django.db import connection
from django.test.utils import CaptureQueriesContext
from operations.test_access import A04SyntheticCase
from erp import network_workflow


class NetworkCompositionTests(A04SyntheticCase):
    def test_network_http_includes_workflow_documents_and_export_without_writes(self):
        client = self.grant('ceo', 'view_document', 'export_workspace')
        self.location.branch = self.branch
        self.location.save()
        self.item.currency = 'UAH'
        self.item.save()
        request = self.requests['R01']
        request.currency = 'UAH'
        request.save()
        self.assertIsNotNone(request.created_at)
        self.assertIsNotNone(self.purchase.created_at)
        self.purchase.currency = 'UAH'
        self.purchase.destination = self.location
        self.purchase.save()
        query = f'?location_id={self.location.pk}'
        with CaptureQueriesContext(connection) as queries:
            response = client.get('/api/erp/network/' + query)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual([r['code'] for r in data['workflow']['requests']], ['R01'])
        self.assertTrue(data['documents'])
        self.assertFalse(data['workflow']['comparison']['available'])
        self.assertEqual(data['workflow']['metrics']['request_count'], 1)
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ')) for q in queries.captured_queries))
        exported = client.get('/api/erp/network/export/' + query + '&format=json')
        self.assertEqual(exported.status_code, 200, exported.content)
        self.assertEqual(exported.json()['workflow']['requests'], data['workflow']['requests'])
        self.assertEqual(exported.json()['documents'], data['documents'])
        self.assertEqual(exported['Cache-Control'], 'private, no-store')

    def test_workflow_document_scope_race_aborts_whole_network_response(self):
        client = self.grant('manager', 'view_document')
        original = network_workflow.build
        def changed(policy, params):
            value = original(policy, params)
            self.public_doc.access_level = 'finance'
            self.public_doc.save(update_fields=['access_level'])
            return value
        with patch('erp.network.network_workflow.build', side_effect=changed):
            response = client.get('/api/erp/network/?currency=UAH')
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()['code'], 'read_state_changed')
        self.assertNotIn('documents', response.json())
