from scripts.check_support import login_test_client
"""A05 review: actual audit failure, archive responses and lock order.

Run only with verification_settings and Django's disposable test database.
No ORM/HTTP replacement: failures come from real database triggers.
"""
from contextlib import contextmanager
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection, IntegrityError
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext

from employees.models import Employee
from finance.commands import save_salary
from finance.models import Salary, Transaction
from operations.models import AuditEvent


class ArchiveReviewTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(full_name='Синтетичний A05 review', role='Тест')
        self.salary = Salary.objects.create(employee=self.employee, amount='100.25',
            currency='EUR', period_year=2026, period_month=9)
        self.client = Client(enforce_csrf_checks=True, raise_request_exception=False,
            REMOTE_ADDR='127.0.0.1')
        login_test_client(self.client)
        self.assertEqual(self.client.get('/api/operations/status/').status_code, 200)

    @contextmanager
    def reject_audit(self, action='salary.archive'):
        # A real write fails after the business update, exercising rollback.
        allowed = ('salary.archive', 'salary.update', 'salary.create')
        if action not in allowed:
            raise ValueError('Unsupported synthetic trigger target')
        with connection.cursor() as cursor:
            if connection.vendor == 'sqlite':
                cursor.execute(f"""CREATE TRIGGER a05_reject_audit BEFORE INSERT ON operations_auditevent
                    WHEN NEW.action = '{action}'
                    BEGIN SELECT RAISE(ABORT, 'A05 synthetic audit failure'); END""")
            elif connection.vendor == 'postgresql':
                cursor.execute(f"""CREATE FUNCTION a05_reject_audit_fn() RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN IF NEW.action = '{action}' THEN
                    RAISE EXCEPTION 'A05 synthetic audit failure' USING ERRCODE = '23000';
                    END IF; RETURN NEW; END; $$""")
                cursor.execute('CREATE TRIGGER a05_reject_audit BEFORE INSERT ON operations_auditevent FOR EACH ROW EXECUTE FUNCTION a05_reject_audit_fn()')
            else:
                raise RuntimeError('This acceptance test supports SQLite and PostgreSQL')
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute('DROP TRIGGER a05_reject_audit' + (' ON operations_auditevent' if connection.vendor == 'postgresql' else ''))
                if connection.vendor == 'postgresql':
                    cursor.execute('DROP FUNCTION a05_reject_audit_fn()')

    def assert_unarchived(self):
        self.salary.refresh_from_db()
        self.assertIsNone(self.salary.archived_at)
        self.assertEqual(self.salary.amount, Decimal('100.25'))
        self.assertEqual(self.salary.employee_id, self.employee.pk)
        self.assertEqual(Salary.objects.count(), 1)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.filter(action='salary.archive').count(), 0)

    def admin_client(self):
        get_user_model().objects.create_superuser(username='a05-review-admin', email='', password='synthetic-only')
        self.assertTrue(self.client.login(username='a05-review-admin', password='synthetic-only'))
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        return self.client

    def test_http_archive_audit_failure_rolls_back_and_returns_409(self):
        with self.reject_audit():
            response = self.client.delete(f'/api/salaries/{self.salary.pk}/',
                HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)
        self.assert_unarchived()
        self.assertEqual(response.status_code, 409, 'Rollback alone must not leave an HTTP 500')

    def test_admin_single_archive_audit_failure_rolls_back_and_returns_409(self):
        client = self.admin_client()
        with self.reject_audit():
            response = client.post(f'/admin/finance/salary/{self.salary.pk}/delete/', {'post': 'yes'},
                HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assert_unarchived()
        self.assertEqual(response.status_code, 409, 'Admin single-delete needs the same conflict response')

    def test_admin_bulk_archive_audit_failure_rolls_back_and_returns_409(self):
        client = self.admin_client()
        with self.reject_audit():
            response = client.post('/admin/finance/salary/',
                {'action': 'delete_selected', '_selected_action': [str(self.salary.pk)], 'post': 'yes', 'index': '0'},
                HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assert_unarchived()
        self.assertEqual(response.status_code, 409, 'Admin bulk-delete needs the same conflict response')

    def test_archive_replay_keeps_one_audit_record_and_original_timestamp(self):
        self.salary.delete()
        timestamp = self.salary.archived_at
        self.assertIsNotNone(timestamp)
        self.salary.delete()
        self.assertEqual(self.salary.archived_at, timestamp)
        records = AuditEvent.objects.filter(action='salary.archive')
        self.assertEqual(records.count(), 1)
        self.assertEqual(records.get().payload['id'], self.salary.pk)
        self.assertEqual(Salary.objects.count(), 1)

    def test_shared_save_rolls_back_money_when_audit_insert_fails(self):
        with self.reject_audit('salary.update'), self.assertRaises(IntegrityError):
            save_salary(instance=self.salary, changes={'amount': Decimal('200.75')})
        self.salary.refresh_from_db()
        self.assertEqual(self.salary.amount, Decimal('100.25'))
        self.assertEqual(AuditEvent.objects.filter(action='salary.update').count(), 0)

    def test_create_salary_locks_employee_before_active_status_read(self):
        # This traces actual SQL, rather than replacing an ORM method or
        # proving PostgreSQL behavior from a successful SQLite race.
        with CaptureQueriesContext(connection) as capture:
            save_salary(changes=dict(employee=self.employee, amount=Decimal('100.25'),
                currency='EUR', period_year=2026, period_month=10))
        statements = [row['sql'].lower() for row in capture.captured_queries]
        updates = [i for i, sql in enumerate(statements)
            if sql.lstrip().startswith('update') and 'employees_employee' in sql]
        reads = [i for i, sql in enumerate(statements)
            if sql.lstrip().startswith('select') and 'employees_employee' in sql]
        self.assertTrue(updates, 'Employee archive-vs-create requires a shared row write lock')
        self.assertTrue(reads, 'The candidate must actually validate the employee')
        self.assertLess(updates[0], reads[0], statements)
