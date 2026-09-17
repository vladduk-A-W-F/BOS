"""A08 first regression slice: genuine HTTP/SQL, synthetic data only.

No implementation mocks. Run as a tmp PYTHONPATH module with
verification_settings and an explicitly new check_*.sqlite3 test database.
"""
import hashlib
import json
import os
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from operations.models import AuditEvent, Configuration, Document
from scripts.check_support import login_test_client


def response_bytes(response):
    # Django's test-client streaming wrapper closes the file itself. Calling
    # response.close() again also closes TestCase's surrounding DB transaction.
    return b''.join(response.streaming_content) if response.streaming else response.content


@override_settings(BOS_DATA_MODE='working', DEBUG=False, ANTHROPIC_API_KEY='',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class A08DocumentIntegrityTests(TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('DJANGO_SETTINGS_MODULE'), 'verification_settings')
        if connection.vendor == 'sqlite':
            self.assertTrue(Path(str(connection.settings_dict['NAME'])).name.startswith('check_'))
        self.client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        login_test_client(self.client, 'ceo', capabilities=('view_document', 'download_document', 'export_workspace'))
        Configuration.objects.create(key='erp_write', value={'revision': 0})
        self.content = 'Синтетичний сертифікат A08. Сталь 20.'.encode('utf-8')
        self.doc = Document.objects.create(code='A08-CERT', revision='A',
            title='Синтетичний сертифікат A08', filename='a08-certificate.txt',
            content=self.content, text=self.content.decode('utf-8'),
            sections=[{'source': 'Текст', 'text': self.content.decode('utf-8')}],
            checksum=hashlib.sha256(self.content).hexdigest(), status='needs_review',
            access_level='operational')

    def rows(self):
        return {'documents': list(Document.objects.order_by('pk').values()),
                'audit': list(AuditEvent.objects.order_by('pk').values()),
                'configuration': list(Configuration.objects.order_by('pk').values())}

    def review(self):
        return self.client.post(f'/api/operations/documents/{self.doc.pk}/review/',
            json.dumps({'checksum': self.doc.checksum}), content_type='application/json',
            HTTP_X_CSRFTOKEN=self.client.cookies[settings.CSRF_COOKIE_NAME].value)

    def test_corrupted_blob_cannot_be_downloaded_under_original_checksum(self):
        corrupted = b'A08 CORRUPTED FILE BYTES'
        Document.objects.filter(pk=self.doc.pk).update(content=corrupted)
        before = self.rows()
        response = self.client.get(f'/api/operations/documents/{self.doc.pk}/download/')
        status, body = response.status_code, response_bytes(response)
        self.assertEqual(self.rows(), before, 'Read must not silently repair the evidence')
        self.assertEqual(status, 422, body)
        self.assertNotIn(corrupted, body)

    def test_corrupted_blob_cannot_be_approved_using_stored_checksum(self):
        Document.objects.filter(pk=self.doc.pk).update(content=b'A08 substituted bytes')
        before = self.rows()
        response = self.review()
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(self.rows(), before, 'Rejected review must not approve or change the ERP mutex')

    def test_legacy_text_only_download_requires_exact_stored_hash(self):
        Document.objects.filter(pk=self.doc.pk).update(content=b'', text='A08 UNVERIFIED FALLBACK')
        before = self.rows()
        response = self.client.get(f'/api/operations/documents/{self.doc.pk}/download/')
        status, body = response.status_code, response_bytes(response)
        self.assertEqual(self.rows(), before)
        self.assertEqual(status, 422, body)
        self.assertNotIn(b'A08 UNVERIFIED FALLBACK', body)

    def test_legacy_text_only_review_requires_exact_stored_hash(self):
        Document.objects.filter(pk=self.doc.pk).update(content=b'', text='A08 UNVERIFIED FALLBACK')
        before = self.rows()
        response = self.review()
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(self.rows(), before)

    def test_valid_legacy_text_only_remains_downloadable_without_repair(self):
        Document.objects.filter(pk=self.doc.pk).update(content=b'')
        before = self.rows()
        response = self.client.get(f'/api/operations/documents/{self.doc.pk}/download/')
        status, body = response.status_code, response_bytes(response)
        self.assertEqual(status, 200, body)
        self.assertEqual(body, self.content)
        self.assertEqual(self.rows(), before)

    def test_empty_original_hash_serves_empty_bytes_not_unrelated_text(self):
        Document.objects.filter(pk=self.doc.pk).update(content=b'', checksum=hashlib.sha256(b'').hexdigest(),
                                                       text='A08 DERIVED TEXT IS NOT ORIGINAL')
        before = self.rows()
        response = self.client.get(f'/api/operations/documents/{self.doc.pk}/download/')
        status, body = response.status_code, response_bytes(response)
        self.assertEqual(status, 200, body)
        self.assertEqual(body, b'', 'An empty original is identified by its actual SHA, not truthiness')
        self.assertEqual(self.rows(), before)

    def test_metadata_list_and_detail_do_not_select_binary_content(self):
        for path in ('/api/operations/documents/', f'/api/operations/documents/{self.doc.pk}/'):
            with self.subTest(path=path):
                with CaptureQueriesContext(connection) as queries:
                    response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.content)
                blob_selects = [q['sql'] for q in queries.captured_queries
                    if q['sql'].lstrip().upper().startswith('SELECT')
                    and 'operations_document' in q['sql']
                    and '"content"' in q['sql'].split(' FROM ', 1)[0]]
                self.assertEqual(blob_selects, [], 'Metadata must not hydrate originals from BLOB storage')

    def test_missing_download_permission_is_denied_before_integrity_oracle(self):
        client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        login_test_client(client, 'manager', capabilities=('view_document',))
        Document.objects.filter(pk=self.doc.pk).update(content=b'A08 CORRUPTED SECRET')
        before = self.rows()
        response = client.get(f'/api/operations/documents/{self.doc.pk}/download/')
        status, body = response.status_code, response_bytes(response)
        self.assertEqual(status, 403, body)
        self.assertNotIn(b'A08 CORRUPTED SECRET', body)
        self.assertEqual(self.rows(), before)
