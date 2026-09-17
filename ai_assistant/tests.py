from scripts.check_support import login_test_client
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient
from django.test import TestCase

from .models import ChatFile, ChatMessage


class ChatHistoryTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = login_test_client(self.client)

    def test_list_history_returns_oldest_first(self):
        ChatMessage.objects.create(user=self.user, visibility_role='ceo', role='user', content='Привіт')
        ChatMessage.objects.create(user=self.user, visibility_role='ceo', role='assistant', content='Вітаю!')
        resp = self.client.get('/api/chat/history/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual([m['role'] for m in resp.data], ['user', 'assistant'])

    def test_delete_history_removes_messages_and_files(self):
        """A04: clearing a view archives history and preserves source files."""
        msg = ChatMessage.objects.create(user=self.user, visibility_role='ceo', role='user', content='з файлом')
        attached = ChatFile.objects.create(
            chat_message=msg, original_name='test.txt',
            file=SimpleUploadedFile('test.txt', b'hello', content_type='text/plain'),
            mime_type='text/plain', size=5,
        )
        resp = self.client.delete('/api/chat/history/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(list(ChatMessage.objects.values_list('pk', flat=True)), [msg.pk])
        self.assertEqual(list(ChatFile.objects.values_list('pk', flat=True)), [attached.pk])
        msg.refresh_from_db()
        self.assertIsNotNone(msg.archived_at)
        self.assertEqual(attached.chat_message_id, msg.pk)
        with attached.file.open('rb') as saved:
            self.assertEqual(saved.read(), b'hello')
        self.assertEqual(self.client.get('/api/chat/history/').data, [])
