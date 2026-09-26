"""A03 red regression: real concurrent login failures, no auth/time mocks."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import close_old_connections
from django.test import Client, TransactionTestCase, override_settings


@override_settings(BOS_DATA_MODE='working')
class ConcurrentLoginLimitTests(TransactionTestCase):
    def test_completed_concurrent_failures_cannot_lose_the_rate_counter(self):
        cache.clear()
        user = get_user_model().objects.create_user(
            username='a03-rate-thread', password='Synthetic-valid-A03-password',
        )
        user.groups.add(Group.objects.get_or_create(name='ceo')[0])
        clients = []
        for _ in range(8):
            client = Client(enforce_csrf_checks=True, REMOTE_ADDR='127.0.0.1')
            self.assertEqual(client.get('/api/auth/csrf/').status_code, 200)
            clients.append(client)
        barrier = threading.Barrier(len(clients))

        def attempt(client):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return client.post('/api/auth/login/',
                    {'username': user.username, 'password': 'Synthetic-wrong-A03-password'},
                    content_type='application/json',
                    HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value).status_code
            finally:
                close_old_connections()

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=len(clients)) as pool:
            statuses = list(pool.map(attempt, clients))
        self.assertTrue(all(value in (401, 429) for value in statuses), statuses)
        self.assertGreaterEqual(statuses.count(401), 5, statuses)
        following = clients[0].post('/api/auth/login/',
            {'username': user.username, 'password': 'Synthetic-wrong-A03-password'},
            content_type='application/json',
            HTTP_X_CSRFTOKEN=clients[0].cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertLess(time.monotonic() - started, 60, 'Run must finish within the actual rate-limit window.')
        self.assertEqual(following.status_code, 429,
            f'After completed failures {statuses}, another failure was accepted: {following.status_code}')
