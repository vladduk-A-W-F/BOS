"""A08 recovered HTTP acceptance: actual DB/files/CSRF, no implementation mocks."""
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, connections
from django.test import Client, TransactionTestCase, override_settings

from operations.models import AuditEvent, Configuration, Document
from operations.test_document_integrity import response_bytes
from scripts.check_support import login_test_client


@override_settings(BOS_DATA_MODE='working', DEBUG=False, ANTHROPIC_API_KEY='',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class A08UploadTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('DJANGO_SETTINGS_MODULE'), 'verification_settings')
        if connection.vendor == 'sqlite':
            self.assertTrue(Path(str(connection.settings_dict['NAME'])).name.startswith('check_'))
        self.folder = tempfile.TemporaryDirectory(prefix='bos-a08-upload-')
        self.addCleanup(self.folder.cleanup)
        self.media = Path(self.folder.name) / 'media'
        self.media.mkdir(mode=0o700)
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        login_test_client(self.client, 'ceo', capabilities=('view_document', 'download_document'))
        Configuration.objects.create(key='erp_write', value={'revision': 0})

    def upload(self, data=b'12345', *, code='A08-UPLOAD', revision='A', client=None):
        client = client or self.client
        return client.post('/api/operations/documents/upload/', {
            'file': SimpleUploadedFile('a08-evidence.txt', data, content_type='text/plain'),
            'code': code, 'revision': revision, 'title': 'Синтетичний документ A08'},
            HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)

    def rows(self):
        return {'documents': list(Document.objects.order_by('pk').values()),
                'audit': list(AuditEvent.objects.order_by('pk').values()),
                'configuration': list(Configuration.objects.order_by('pk').values())}

    def files(self):
        return {p.relative_to(self.media).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.media.rglob('*') if p.is_file()}

    def legacy(self, data=b'12345', code='A08-LEGACY'):
        return Document.objects.create(code=code, revision='A', title='Історичний документ',
            filename='legacy.txt', content=data, text=data.decode(), checksum=hashlib.sha256(data).hexdigest(),
            status='needs_review', access_level='operational')

    def bound(self, *, size=5):
        data=b'12345'
        doc=self.legacy(data)
        key='documents/ab/' + 'ab' + '1'*30 + '.blob'
        (self.media / 'documents').mkdir(mode=0o700)
        (self.media / 'documents/ab').mkdir(mode=0o700)
        path=self.media/key
        path.write_bytes(data)
        path.chmod(0o600)
        Document.objects.filter(pk=doc.pk).update(original_file=key, size=size)
        doc.refresh_from_db()
        return doc, path

    def test_upload_persists_private_original_and_reads_after_new_request(self):
        data='Сертифікат випробувань A08'.encode()
        response=self.upload(data)
        self.assertEqual(response.status_code, 201, response.content)
        doc=Document.objects.get(pk=response.json()['id'])
        self.assertEqual(bytes(doc.content), b'')
        self.assertEqual(doc.size, len(data))
        self.assertRegex(doc.original_file.name, r'^documents/[0-9a-f]{2}/[0-9a-f]{32}\.blob$')
        self.assertEqual(doc.checksum, hashlib.sha256(data).hexdigest())
        self.assertEqual((self.media / doc.original_file.name).read_bytes(), data)
        self.assertNotIn(doc.original_file.name.encode(), response.content)
        reader=Client(enforce_csrf_checks=True, raise_request_exception=False)
        reader.cookies=self.client.cookies.copy()
        got=reader.get(f'/api/operations/documents/{doc.pk}/download/')
        self.assertEqual(got.status_code, 200, response_bytes(got))
        # Another read proves independent request/stream, not a still-open upload buffer.
        got=reader.get(f'/api/operations/documents/{doc.pk}/download/')
        self.assertEqual(response_bytes(got), data)
        if os.name == 'posix':
            self.assertEqual((self.media/doc.original_file.name).stat().st_mode & 0o777, 0o600)

    def test_quota_counts_legacy_blob_and_all_existing_physical_files(self):
        self.legacy(b'1234')
        (self.media/'chat_files').mkdir()
        (self.media/'chat_files/archive.bin').write_bytes(b'12')
        (self.media/'unbound-orphan.bin').write_bytes(b'1234')
        before, files=self.rows(), self.files()
        with override_settings(BOS_DOCUMENT_QUOTA_BYTES=15):
            response=self.upload(b'123456')
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.files(), files)

    def test_quota_exact_limit_then_next_byte_refused_without_side_effects(self):
        self.legacy()
        with override_settings(BOS_DOCUMENT_QUOTA_BYTES=10):
            first=self.upload()
            self.assertEqual(first.status_code, 201, first.content)
            before, files=self.rows(), self.files()
            second=self.upload(b'1', code='A08-OVER')
        self.assertEqual(second.status_code, 422, second.content)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.files(), files)
        self.assertEqual(sum(len(bytes(d.content)) for d in Document.objects.all()) +
                         sum(p.stat().st_size for p in self.media.rglob('*') if p.is_file()), 10)

    def test_invalid_quota_configuration_refuses_instead_of_disabling_limit(self):
        for value in (-1, True, '10', None):
            with self.subTest(value=value):
                before, files=self.rows(), self.files()
                with override_settings(BOS_DOCUMENT_QUOTA_BYTES=value):
                    response=self.upload(code='A08-QUOTA-' + str(value))
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(self.rows(), before)
                self.assertEqual(self.files(), files)

    def test_denied_and_oversize_upload_create_no_document_or_file(self):
        observer=Client(enforce_csrf_checks=True, raise_request_exception=False)
        login_test_client(observer, 'observer')
        before, files=self.rows(), self.files()
        denied=self.upload(client=observer)
        self.assertEqual(denied.status_code, 403, denied.content)
        oversized=self.upload(b'a'*(10*1024*1024+1))
        self.assertEqual(oversized.status_code, 422, oversized.content)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.files(), files)

    def test_duplicate_version_rolls_back_only_own_new_file(self):
        self.assertEqual(self.upload().status_code, 201)
        before, files=self.rows(), self.files()
        duplicate=self.upload(b'new bytes')
        self.assertEqual(duplicate.status_code, 409, duplicate.content)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.files(), files)

    def test_late_actual_sql_failure_cleans_new_file_preserves_previous_file(self):
        self.assertEqual(self.upload().status_code, 201)
        before, files=self.rows(), self.files()
        if connection.vendor != 'sqlite':
            self.skipTest('SQLite trigger proof; PostgreSQL requires its actual runner')
        with connection.cursor() as cursor:
            cursor.execute("CREATE TRIGGER a08_reject_insert BEFORE INSERT ON operations_document WHEN NEW.code='A08-SQL-FAIL' BEGIN SELECT RAISE(ABORT,'synthetic A08 late failure'); END")
        try:
            rejected=self.upload(b'late SQL bytes', code='A08-SQL-FAIL')
            self.assertEqual(rejected.status_code, 409, rejected.content)
            self.assertEqual(self.rows(), before)
            self.assertEqual(self.files(), files)
        finally:
            with connection.cursor() as cursor: cursor.execute('DROP TRIGGER a08_reject_insert')

    def test_missing_or_corrupted_bound_original_never_uses_valid_legacy_backup(self):
        doc, path=self.bound()
        for case in ('corrupt', 'missing'):
            with self.subTest(case=case):
                if case=='corrupt': path.write_bytes(b'54321')
                else: path.unlink()
                before=self.rows()
                response=self.client.get(f'/api/operations/documents/{doc.pk}/download/')
                self.assertEqual(response.status_code, 422, response_bytes(response))
                review=self.client.post(f'/api/operations/documents/{doc.pk}/review/',
                    json.dumps({'checksum':doc.checksum}), content_type='application/json',
                    HTTP_X_CSRFTOKEN=self.client.cookies[settings.CSRF_COOKIE_NAME].value)
                self.assertEqual(review.status_code, 422, review.content)
                self.assertEqual(self.rows(), before)

    def test_private_file_has_no_raw_media_route_or_permission_bypass(self):
        doc, path=self.bound()
        manager=Client(enforce_csrf_checks=True, raise_request_exception=False)
        login_test_client(manager, 'manager', capabilities=('view_document',))
        self.assertEqual(manager.get(f'/api/operations/documents/{doc.pk}/').status_code, 200)
        self.assertEqual(manager.get(f'/api/operations/documents/{doc.pk}/download/').status_code, 403)
        for client in (self.client, manager, Client()):
            response=client.get('/media/'+doc.original_file.name)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn(b'12345', response.content)
        self.assertEqual(path.read_bytes(), b'12345')

    def test_two_real_uploads_cannot_both_spend_one_remaining_quota(self):
        self.legacy()
        barrier=threading.Barrier(2)
        cookies=self.client.cookies.copy()
        def run(index):
            connections.close_all()
            client=Client(enforce_csrf_checks=True, raise_request_exception=False)
            client.cookies=cookies.copy()
            statuses=[]
            try:
                barrier.wait(timeout=10)
                for _ in range(3):
                    response=self.upload(code=f'A08-PARALLEL-{index}', client=client)
                    statuses.append(response.status_code)
                    if response.status_code != 409: break
                return {'worker':index, 'statuses':statuses, 'final':response.status_code,
                        'body':response.content.decode(errors='replace')}
            finally:
                connections.close_all()
        with override_settings(BOS_DOCUMENT_QUOTA_BYTES=10):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(run,index) for index in range(2)]
                results=[future.result(timeout=30) for future in futures]
            # The winner may still be committing during all three immediate
            # contention retries. Retry only after both real workers have joined.
            for result in results:
                if result['final']==409:
                    response=self.upload(code=f"A08-PARALLEL-{result['worker']}")
                    result['statuses'].append(response.status_code)
                    result.update(final=response.status_code, body=response.content.decode(errors='replace'))
        print('BOS_A08_UPLOAD_CONCURRENCY '+json.dumps(results,ensure_ascii=False))
        self.assertEqual(sorted(x['final'] for x in results), [201,422], results)
        self.assertEqual(Document.objects.filter(code__startswith='A08-PARALLEL-').count(), 1)
        self.assertEqual(len(self.files()), 1)
        self.assertEqual(sum(len(bytes(d.content)) for d in Document.objects.all()) +
                         sum(p.stat().st_size for p in self.media.rglob('*') if p.is_file()), 10)

    def test_bound_original_without_recorded_size_is_not_usable(self):
        doc, path=self.bound(size=None)
        before, files=self.rows(), self.files()
        download=self.client.get(f'/api/operations/documents/{doc.pk}/download/')
        self.assertEqual(download.status_code, 422, response_bytes(download))
        review=self.client.post(f'/api/operations/documents/{doc.pk}/review/',
            json.dumps({'checksum':doc.checksum}), content_type='application/json',
            HTTP_X_CSRFTOKEN=self.client.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertEqual(review.status_code, 422, review.content)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.files(), files)
