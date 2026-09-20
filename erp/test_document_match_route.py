"""HTTP integration of the accepted synthetic read adapter only."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from operations.document_matching import server_adapter
from .order_trace import ReadStateChanged


@override_settings(BOS_DATA_MODE='working', ANTHROPIC_API_KEY='')
class DocumentMatchRouteTests(TestCase):
    def document(self, *args, **kwargs):
        from operations.test_document_matching_server import DocumentMatchingServerTests
        return DocumentMatchingServerTests.document(self, *args, **kwargs)

    def receipt(self, *args, **kwargs):
        from operations.test_document_matching_server import DocumentMatchingServerTests
        return DocumentMatchingServerTests.receipt(self, *args, **kwargs)

    def setUp(self):
        from operations.test_document_matching_server import DocumentMatchingServerTests
        DocumentMatchingServerTests.setUp(self)
        self.client.force_login(self.user)

    @property
    def url(self):
        return f'/api/erp/purchases/{self.po.pk}/document-match/'

    @property
    def query(self):
        return {'document_id': self.doc.pk, 'supplier_id': self.supplier.pk, 'item_id': self.item.pk}

    def test_verified_original_http_evidence_and_no_writes(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url, self.query)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data['schema'], 'bos.document-match-read.v1')
        self.assertEqual((data['purchase_id'], data['document_id']), (self.po.pk, self.doc.pk))
        self.assertEqual(data['access_revision'], response['X-BoS-Access'])
        draft = data['draft']
        self.assertEqual(draft['decision'], 'accept_draft')
        self.assertEqual(draft['provider'], 'mock.synthetic-invoice.v1')
        self.assertIsNone(draft['operation_proposal'])
        self.assertEqual(draft['fields']['total']['value'], '12000.00')
        self.assertEqual(draft['fields']['total']['evidence']['source_sha256'], self.doc.checksum)
        self.assertFalse(any(row['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ')) for row in queries))

    def test_ceo_gate_precedes_selection_and_other_methods_fail(self):
        self.assertEqual(Client().get(self.url, self.query).status_code, 401)
        for role in ('manager', 'observer'):
            user = get_user_model().objects.create_user(username='route-' + role)
            user.groups.add(Group.objects.get_or_create(name=role)[0])
            client = Client(); client.force_login(user)
            self.assertEqual(client.get(self.url).status_code, 403)
            self.assertEqual(client.get(self.url, self.query).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.query).status_code, 405)

    def test_explicit_selection_and_safe_unsupported_document(self):
        missing = self.client.get(self.url, {'document_id': self.doc.pk})
        self.assertEqual(missing.status_code, 200)
        self.assertIn('supplier_selection_required', missing.json()['draft']['exceptions'])
        self.assertIn('item_selection_required', missing.json()['draft']['exceptions'])
        for query in ({}, {'document_id': 0}, {'document_id': [self.doc.pk, self.doc.pk]},
                      {'document_id': self.doc.pk, 'item_id': '1.5'}):
            self.assertEqual(self.client.get(self.url, query).status_code, 422)
        self.doc, self.path = self.document(b'Ordinary synthetic business note', 'note.txt')
        data = self.client.get(self.url, self.query).json()['draft']
        self.assertEqual(data['decision'], 'needs_information')
        self.assertIn('unsupported_document', data['exceptions'])
        self.assertIsNone(data['operation_proposal'])

    def test_stale_source_and_missing_ids_never_return_draft(self):
        with patch.object(server_adapter, 'build', side_effect=ReadStateChanged()):
            response = self.client.get(self.url, self.query)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(set(response.json()), {'error', 'code'})
        self.assertEqual(self.client.get(self.url, {**self.query, 'document_id': 99999999}).status_code, 404)
        self.assertEqual(self.client.get('/api/erp/purchases/99999999/document-match/', self.query).status_code, 404)
