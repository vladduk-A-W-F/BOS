"""A04: technical-admin separation and revocation boundary, real HTTP."""
import importlib
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client, override_settings
from django.urls import clear_url_caches
from ai_assistant.models import ChatMessage
from operations.test_access import A04SyntheticCase, text_body


class A04BoundaryTests(A04SyntheticCase):
    def test_business_roles_cannot_gain_private_admin_data_with_staff_flags(self):
        for role in ('ceo', 'manager', 'observer'):
            client = self.client_for(role)
            user = self.users[role]
            user.is_staff = user.is_superuser = True
            user.save(update_fields=['is_staff', 'is_superuser'])
            for path in ('/admin/finance/salary/', '/admin/employees/employee/', '/admin/auth/user/'):
                with self.subTest(role=role, path=path):
                    response = client.get(path)
                    self.assertIn(response.status_code, (302, 403), text_body(response))
                    self.assertNotIn(self.HR_PHONE, text_body(response))
                    self.assertNotIn(self.PAYROLL_AMOUNTS[0], text_body(response))

    def test_technical_admin_can_read_but_not_rewrite_or_delete_chat_evidence(self):
        user = get_user_model().objects.create_superuser('a04-technical-only', '', 'test-technical-only')
        client = Client(enforce_csrf_checks=True)
        self.assertTrue(client.login(username=user.username, password='test-technical-only'))
        message = ChatMessage.objects.create(role='user', content='A04 immutable history')
        url = f'/admin/ai_assistant/chatmessage/{message.pk}/'
        self.assertEqual(client.get(url + 'change/').status_code, 200)
        token = client.cookies['csrftoken'].value
        original = ChatMessage.objects.filter(pk=message.pk).values().get()
        for path, data in ((url+'change/', {'role':'user','content':'rewritten','_save':'Save'}),
                           (url+'delete/', {'post':'yes'}),
                           ('/admin/ai_assistant/chatmessage/', {'action':'delete_selected','_selected_action':str(message.pk),'post':'yes'})):
            with self.subTest(path=path):
                response = client.post(path, data, HTTP_X_CSRFTOKEN=token)
                self.assertEqual(ChatMessage.objects.filter(pk=message.pk).values().first(), original)
                self.assertNotIn(response.status_code, (500,))
        response = client.post('/admin/ai_assistant/chatmessage/add/', {'role':'user','content':'forged','_save':'Save'}, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ChatMessage.objects.filter(content='forged').exists())

    def test_access_revision_changes_on_role_or_capability_revocation(self):
        client = self.grant('ceo', 'view_document', 'download_document', 'export_workspace')
        status = self.json_get(client, '/api/operations/status/')
        original = status.get('access_revision')
        self.assertTrue(original, 'Browser must receive a server-derived access revision')
        self.assertEqual(client.get('/api/employees/')['X-BoS-Access'], original)
        self.users['ceo'].user_permissions.remove(Permission.objects.get(content_type__app_label='operations',codename='download_document'))
        after_permission = client.get('/api/employees/').get('X-BoS-Access')
        self.assertTrue(after_permission)
        self.assertNotEqual(after_permission, original)
        self.users['ceo'].groups.set([Group.objects.get_or_create(name='manager')[0]])
        self.assertNotEqual(client.get('/api/employees/').get('X-BoS-Access'), after_permission)

    def test_non_ceo_cannot_infer_private_hr_through_ordering(self):
        for role in ('manager', 'observer'):
            client = self.client_for(role)
            for field in ('kpi', '-birthday', 'created_at'):
                with self.subTest(role=role, field=field):
                    self.assertEqual(client.get('/api/employees/', {'ordering':field}).status_code, 403)
            self.assertEqual(client.get('/api/employees/', {'ordering':'full_name'}).status_code, 200)

    def test_debug_cannot_open_private_media_bypassing_document_policy(self):
        from pathlib import Path
        from django.conf import settings
        import boss_project.urls as urls
        path = Path(settings.MEDIA_ROOT) / 'a04-private.txt'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('A04_MEDIA_BYTES_SECRET')
        try:
            with override_settings(DEBUG=True):
                importlib.reload(urls)
                clear_url_caches()
                for client in (Client(), self.client_for('observer')):
                    response = client.get('/media/a04-private.txt')
                    self.assertEqual(response.status_code, 404)
                    self.assertNotIn('A04_MEDIA_BYTES_SECRET', text_body(response))
        finally:
            importlib.reload(urls)
            clear_url_caches()
            path.unlink(missing_ok=True)
