from scripts.check_support import login_test_client
from rest_framework import status
from rest_framework.test import APIClient
from django.test import TestCase

from employees.models import Employee
from .models import Counterparty, Salary, Transaction
from .serializers import CounterpartySerializer


class SalaryPayTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        login_test_client(self.client)
        self.employee = Employee.objects.create(full_name='Марія Петренко', role='Бухгалтер')

    def _create_salary(self, status_='pending'):
        return Salary.objects.create(
            employee=self.employee, amount=25000, period_year=2026,
            period_month=6, status=status_,
        )

    def test_pay_creates_transaction_and_marks_paid(self):
        salary = self._create_salary()
        resp = self.client.post(f'/api/salaries/{salary.id}/pay/', {'payment_date': '2026-07-05'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        salary.refresh_from_db()
        self.assertEqual(salary.status, 'paid')
        self.assertEqual(str(salary.payment_date), '2026-07-05')
        self.assertIsNotNone(salary.transaction)

        tx = Transaction.objects.get(pk=salary.transaction_id)
        self.assertEqual(tx.direction, 'out')
        self.assertEqual(tx.category, 'salary')
        self.assertEqual(float(tx.amount), 25000.0)

    def test_pay_again_rejected(self):
        salary = self._create_salary(status_='paid')
        resp = self.client.post(f'/api/salaries/{salary.id}/pay/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pay_invalid_date_rejected(self):
        salary = self._create_salary()
        resp = self.client.post(f'/api/salaries/{salary.id}/pay/', {'payment_date': 'not-a-date'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        salary.refresh_from_db()
        self.assertEqual(salary.status, 'pending')
        self.assertIsNone(salary.transaction_id)


class CounterpartySerializerTestCase(TestCase):
    def test_serializes_unannotated_instance_without_crash(self):
        """Регрессия: раньше падал с AttributeError на объекте без аннотации."""
        cp = Counterparty.objects.create(name='ТОВ Ромашка')
        data = CounterpartySerializer(cp).data
        self.assertEqual(data['total_debit'], 0.0)
        self.assertEqual(data['total_credit'], 0.0)
        self.assertEqual(data['balance'], 0.0)

    def test_with_totals_annotates_sums(self):
        cp = Counterparty.objects.create(name='ТОВ Ромашка')
        Transaction.objects.create(direction='in', amount=1000, date='2026-07-01', description='оплата', counterparty=cp)
        Transaction.objects.create(direction='out', amount=300, date='2026-07-02', description='повернення', counterparty=cp)
        data = CounterpartySerializer(Counterparty.objects.with_totals().get(pk=cp.pk)).data
        self.assertEqual(data['total_debit'], 1000.0)
        self.assertEqual(data['total_credit'], 300.0)
        self.assertEqual(data['balance'], 700.0)
