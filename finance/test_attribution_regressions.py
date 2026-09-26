"""Frozen A05 relationship-delete risks: preserve financial attribution.

The initial consistent paid history is synthetic ORM fixture data, not a
write path under test. The tested operations are real HTTP/admin/AI deletes.
"""
from decimal import Decimal

from ai_assistant.views import execute_tool
from branches.models import Branch
from finance.models import Counterparty, Contract, Salary, Transaction
from finance.test_finance_integrity import HistoryTestBase


class AttributionReviewTests(HistoryTestBase):
    def setUp(self):
        super().setUp()
        self.counterparty = Counterparty.objects.create(name='Синтетичний A05 контрагент')
        self.contract = Contract.objects.create(number='A05-C01', name='Синтетичний договір',
            counterparty=self.counterparty, amount='100.25', currency='EUR')
        employee = self.employee()
        expense = Transaction.objects.create(direction='out', amount=Decimal('100.25'),
            currency='EUR', date='2026-09-11', description='Синтетична історична виплата',
            category='salary', counterparty=self.counterparty, contract=self.contract, branch=self.branch)
        self.sample_salary = Salary.objects.create(employee=employee, amount=Decimal('100.25'),
            currency='EUR', period_year=2026, period_month=9, status='paid',
            payment_date='2026-09-11', transaction=expense)
        self.before = self.payment_snapshot(self.sample_salary)

    def assert_attribution_unchanged(self):
        self.assert_history_unchanged(self.before)
        self.assertTrue(Counterparty.objects.filter(pk=self.counterparty.pk).exists())
        self.assertTrue(Contract.objects.filter(pk=self.contract.pk).exists())
        self.assertTrue(Branch.objects.filter(pk=self.branch.pk).exists())

    def test_api_counterparty_delete_cannot_null_paid_expense_attribution(self):
        response = self.api('delete', f'/api/counterparties/{self.counterparty.pk}/')
        self.assert_attribution_unchanged()
        self.assertEqual(response.status_code, 409, response.content)

    def test_api_contract_delete_cannot_null_paid_expense_attribution(self):
        response = self.api('delete', f'/api/contracts/{self.contract.pk}/')
        self.assert_attribution_unchanged()
        self.assertEqual(response.status_code, 409, response.content)

    def test_admin_branch_delete_cannot_null_paid_expense_attribution(self):
        response = self.admin_post(f'/admin/branches/branch/{self.branch.pk}/delete/', {'post': 'yes'})
        self.assert_attribution_unchanged()
        # Django may show the native PROTECT explanation or a domain conflict.
        self.assertIn(response.status_code, (200, 409), response.content)

    def test_ai_counterparty_delete_cannot_null_paid_expense_attribution(self):
        result = execute_tool('delete_counterparty', {'counterparty_id': self.counterparty.pk})
        self.assertIsInstance(result, str)
        self.assert_attribution_unchanged()
