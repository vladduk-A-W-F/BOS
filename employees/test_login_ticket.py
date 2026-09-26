"""A03 ticket ABA regression: real bucket lifecycle, no ORM or time mocks."""
from django.test import TransactionTestCase


class LateLoginSuccessTests(TransactionTestCase):
    def test_late_success_cannot_erase_new_failure_after_another_success(self):
        from boss_project import login_limit
        from operations.models import LoginAttempt

        args = ('a03-ticket-aba', '127.0.0.1')
        ticket_a, retry_a = login_limit.reserve(*args)
        ticket_b, retry_b = login_limit.reserve(*args)
        self.assertIsNone(retry_a)
        self.assertIsNone(retry_b)
        login_limit.succeeded(ticket_b)
        ticket_c, retry_c = login_limit.reserve(*args)
        self.assertIsNone(retry_c)
        self.assertEqual(LoginAttempt.objects.get().attempts, 1)

        # A and B authenticated successfully, but A completes late. C has
        # already reserved its own attempt and then failed authentication.
        login_limit.succeeded(ticket_a)
        self.assertEqual(LoginAttempt.objects.get().attempts, 1,
            'An old success cleared a failure reserved after another success.')
        self.assertNotEqual(ticket_a, ticket_c,
            'A login ticket must not be reused after the counter resets.')

        for _ in range(4):
            ticket, retry = login_limit.reserve(*args)
            self.assertIsNotNone(ticket)
            self.assertIsNone(retry)
        sixth, retry = login_limit.reserve(*args)
        self.assertIsNone(sixth)
        self.assertGreaterEqual(retry, 1)
