"""BoS 4 M8: photos of reports (PNG/JPEG) in the private document store. Synthetic bytes only."""
import struct
import tempfile
import zlib
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TransactionTestCase, override_settings

from operations.models import Configuration, Document
from scripts.check_support import login_test_client


def png_bytes():
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    header = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
            + chunk(b'IDAT', zlib.compress(b'\x00\xff\xff\xff')) + chunk(b'IEND', b''))


JPEG = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9'


@override_settings(BOS_DATA_MODE='working', DEBUG=False, ANTHROPIC_API_KEY='',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DocumentImageTests(TransactionTestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='bos-m8-images-')
        self.addCleanup(folder.cleanup)
        self.media = Path(folder.name) / 'media'
        self.media.mkdir(mode=0o700)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.client = Client(enforce_csrf_checks=True)
        login_test_client(self.client, 'ceo', capabilities=('view_document', 'download_document'))
        Configuration.objects.create(key='erp_write', value={'revision': 0})

    def upload(self, name, data, code='M8-PHOTO', client=None):
        client = client or self.client
        return client.post('/api/operations/documents/upload/', {
            'file': SimpleUploadedFile(name, data), 'code': code, 'revision': 'A',
            'title': 'Фото звіту складу'}, HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)

    def files(self):
        return [p for p in self.media.rglob('*') if p.is_file()]

    def test_png_is_stored_privately_without_invented_text(self):
        data = png_bytes()
        response = self.upload('zvit-sklad.png', data)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertTrue(body['image'])
        self.assertEqual(body['status'], 'ocr_required')
        document = Document.objects.get(pk=body['id'])
        self.assertEqual((document.text, bytes(document.content)), ('', b''))
        self.assertEqual(len(self.files()), 1)
        view = self.client.get(f'/api/operations/documents/{document.pk}/view/')
        self.assertEqual(view.status_code, 200)
        self.assertEqual(view['Content-Type'], 'image/png')
        self.assertEqual(view['X-Content-Type-Options'], 'nosniff')
        self.assertIn('sandbox', view['Content-Security-Policy'])
        self.assertEqual(view.content, data)

    def test_jpeg_upload_and_view(self):
        response = self.upload('nakladna.jpg', JPEG, code='M8-JPEG')
        self.assertEqual(response.status_code, 201, response.content)
        view = self.client.get(f"/api/operations/documents/{response.json()['id']}/view/")
        self.assertEqual((view.status_code, view['Content-Type']), (200, 'image/jpeg'))

    def test_renamed_or_broken_image_is_refused_without_rows_or_files(self):
        for name, data in (('fake.png', b'not an image'), ('cut.jpg', JPEG[:-2]), ('page.html.png', b'<html></html>')):
            self.assertEqual(self.upload(name, data).status_code, 422)
        self.assertFalse(Document.objects.exists())
        self.assertEqual(self.files(), [])

    def test_view_only_for_images_and_with_download_right(self):
        text = self.upload('note.txt', 'Залишок 120 шт.'.encode(), code='M8-TEXT').json()
        self.assertEqual(self.client.get(f"/api/operations/documents/{text['id']}/view/").status_code, 404)
        image = self.upload('zvit.png', png_bytes(), code='M8-PNG').json()
        reader = Client(enforce_csrf_checks=True)
        login_test_client(reader, 'ceo', capabilities=('view_document',))
        self.assertEqual(reader.get(f"/api/operations/documents/{image['id']}/view/").status_code, 403)
        self.client.logout()
        self.assertIn(self.client.get(f"/api/operations/documents/{image['id']}/view/").status_code, (401, 403))
