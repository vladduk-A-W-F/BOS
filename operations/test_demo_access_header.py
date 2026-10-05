"""Demo: public reads tell a signed-in screen which access revision they belong to."""
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
