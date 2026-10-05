"""Demo: public reads tell a signed-in screen which access revision they belong to."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings

from scripts.check_support import login_test_client


@override_settings(BOS_DATA_MODE='demo', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DemoAccessHeaderTests(TestCase):
    def test_status_carries_the_same_revision_as_protected_reads(self):
        client = Client()
        login_test_client(client, 'ceo')
        status = client.get('/api/operations/status/')
        tasks = client.get('/api/tasks/')
        self.assertEqual((status.status_code, tasks.status_code), (200, 200))
        self.assertTrue(tasks['X-BoS-Access'])
        # «Доручення» compares both headers with the runtime revision; a missing one read as «права змінилися».
        self.assertEqual(status['X-BoS-Access'], tasks['X-BoS-Access'])
        self.assertEqual(status.json()['access_revision'], tasks['X-BoS-Access'])

    def test_anonymous_public_read_has_no_revision(self):
        response = Client().get('/api/operations/status/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('X-BoS-Access', response)

    def test_session_changing_paths_never_get_a_pre_view_revision(self):
        # Signed in as A, then logging in as B: the response must not carry A's revision.
        other = get_user_model().objects.create_user(username='synthetic-b', password='synthetic-pass-b')
        other.groups.add(Group.objects.get_or_create(name='manager')[0])
        client = Client()
        login_test_client(client, 'ceo')
        response = client.post('/api/auth/login/', {'username': 'synthetic-b', 'password': 'synthetic-pass-b'},
                               content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn('X-BoS-Access', response)
        self.assertNotIn('X-BoS-Access', client.get('/api/auth/me/'))
        self.assertNotIn('X-BoS-Access', client.post('/api/auth/logout/'))

    def test_only_get_reads_carry_it(self):
        client = Client()
        login_test_client(client, 'ceo')
        self.assertNotIn('X-BoS-Access', client.post('/api/operations/role/', {'role': 'observer'},
                                                     content_type='application/json'))


@override_settings(BOS_DATA_MODE='working', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class WorkingModeAccessHeaderTests(TestCase):
    def test_working_mode_auth_paths_are_unchanged(self):
        client = Client()
        login_test_client(client, 'ceo')
        self.assertNotIn('X-BoS-Access', client.get('/api/auth/me/'))
        # Not public outside demo: the ordinary protected path sets the header, as before.
        self.assertIn('X-BoS-Access', client.get('/api/operations/status/'))
