"""A05: deterministic stale snapshots from the real Employee write paths.

Read happens before archive, save after archive: an admissible concurrency
schedule with no replaced ORM methods, serializers, admin writers or SQL.
"""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from employees.models import Employee
from employees.serializers import EmployeeSerializer
from finance.models import Salary, Transaction


class EmployeeArchiveStaleReviewTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(full_name='Синтетичний A05 stale', role='Тест')
        self.salary = Salary.objects.create(employee=self.employee, amount='100.25', currency='EUR',
            period_year=2026, period_month=9)
        self.salary.mark_paid('2026-09-11')

    def archive_fresh_instance(self):
        fresh = Employee.objects.get(pk=self.employee.pk)
        fresh.delete()
        return fresh.archived_at

    def assert_archive_and_payment_preserved(self, timestamp):
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.archived_at, timestamp, 'Stale save silently restored an archived Employee')
        self.salary.refresh_from_db()
        self.assertEqual(self.salary.employee_id, self.employee.pk)
        self.assertEqual(self.salary.transaction.currency, self.salary.currency)
        self.assertEqual(self.salary.transaction.amount, self.salary.amount)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_api_serializer_stale_save_cannot_restore_archived_employee(self):
        stale = Employee.objects.get(pk=self.employee.pk)
        serializer = EmployeeSerializer(stale, data={'role': 'Оновлена посада'}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        timestamp = self.archive_fresh_instance()
        serializer.save()
        self.assert_archive_and_payment_preserved(timestamp)

    def test_admin_stale_save_cannot_restore_archived_employee(self):
        stale = Employee.objects.get(pk=self.employee.pk)
        request = RequestFactory().post('/admin/employees/employee/')
        request.user = get_user_model().objects.create_superuser(username='a05-stale-admin', email='', password='synthetic-only')
        model_admin = admin.site._registry[Employee]
        form_class = model_admin.get_form(request, obj=stale)
        form = form_class(data={
            'full_name': stale.full_name, 'role': 'Оновлена посада', 'department': '',
            'birthday': '', 'kpi': '0', 'phone': '', 'email': '', 'branch': '',
        }, instance=stale)
        self.assertTrue(form.is_valid(), form.errors)
        candidate = model_admin.save_form(request, form, change=True)
        timestamp = self.archive_fresh_instance()
        model_admin.save_model(request, candidate, form, change=True)
        self.assert_archive_and_payment_preserved(timestamp)
