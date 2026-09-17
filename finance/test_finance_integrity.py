from scripts.check_support import login_test_client
"""A05: synthetic HTTP/admin/legacy-entry regressions, no mocked writes.

Draft destination: finance/test_finance_integrity.py. Run with Django's test
runner and verification_settings, never against a checkout database. The
archival contract is archived_at != NULL, same historical primary keys and
financial links; archived amounts remain part of historical ledger totals.
"""
from decimal import Decimal
from io import StringIO
import json
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.db.models import Sum
from django.test import Client, TestCase, override_settings

from ai_assistant.models import EmployeeChangeLog
from ai_assistant.views import execute_tool, employee_to_dict
from branches.models import Branch
from employees.models import Employee
from finance.models import Salary, Transaction


CURRENCIES = ('EUR', 'USD', 'UAH')
SALARY_FIELDS = (
    'id', 'employee_id', 'amount', 'currency', 'period_year', 'period_month',
    'status', 'payment_date', 'transaction_id', 'created_at',
)
EXPENSE_FIELDS = (
    'id', 'amount', 'currency', 'direction', 'category', 'date',
    'description', 'branch_id', 'counterparty_id', 'contract_id', 'created_at',
)
EMPLOYEE_FIELDS = ('id', 'full_name', 'role', 'branch_id', 'created_at')


class HistoryTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = get_user_model().objects.create_superuser(
            username='a05-synthetic-admin', email='', password='a05-synthetic-only',
        )

    def setUp(self):
        self.http = Client(enforce_csrf_checks=True, REMOTE_ADDR='127.0.0.1')
        login_test_client(self.http)
        self.assertEqual(self.http.get('/api/operations/status/').status_code, 200)
        self.branch = Branch.objects.create(code='A05-SYN', name='Синтетичний підрозділ A05')
        self._number = 0
        self._admin = None

    def api(self, method, path, data=None):
        return getattr(self.http, method)(
            path, data=json.dumps(data or {}), content_type='application/json',
            HTTP_X_CSRFTOKEN=self.http.cookies['csrftoken'].value,
            HTTP_IDEMPOTENCY_KEY=uuid4().hex,
        )

    def employee(self):
        self._number += 1
        return Employee.objects.create(
            full_name=f'Синтетичний працівник A05 {self._number}',
            role='Тестувальник', branch=self.branch,
        )

    def salary(self, currency='UAH', paid=False):
        sal = Salary.objects.create(
            employee=self.employee(), amount=Decimal('100.25'), currency=currency,
            period_year=2026, period_month=9,
        )
        if paid:
            response = self.api('post', f'/api/salaries/{sal.pk}/pay/', {'payment_date': '2026-09-11'})
            self.assertEqual(response.status_code, 200, response.content)
            sal.refresh_from_db()
        return sal

    def payment_snapshot(self, sal):
        sal.refresh_from_db()
        self.assertIsNotNone(sal.transaction_id)
        return {
            'salary': Salary._base_manager.values(*SALARY_FIELDS).get(pk=sal.pk),
            'expense': Transaction._base_manager.values(*EXPENSE_FIELDS).get(pk=sal.transaction_id),
            'employee': Employee._base_manager.values(*EMPLOYEE_FIELDS).get(pk=sal.employee_id),
        }

    def assert_history_unchanged(self, before):
        for key, model, fields in (
            ('salary', Salary, SALARY_FIELDS),
            ('expense', Transaction, EXPENSE_FIELDS),
            ('employee', Employee, EMPLOYEE_FIELDS),
        ):
            pk = before[key]['id']
            self.assertTrue(model._base_manager.filter(pk=pk).exists(), f'Lost historical {key} #{pk}')
            self.assertEqual(model._base_manager.values(*fields).get(pk=pk), before[key])
        sal = Salary._base_manager.get(pk=before['salary']['id'])
        self.assertEqual(Salary._base_manager.filter(transaction_id=sal.transaction_id).count(), 1)
        self.assertEqual(sal.transaction.amount, sal.amount)
        self.assertEqual(sal.transaction.currency, sal.currency)
        self.assertEqual(sal.transaction.date, sal.payment_date)
        self.assertEqual((sal.transaction.direction, sal.transaction.category), ('out', 'salary'))

    def ledger_totals(self):
        return list(Transaction._base_manager.order_by().values('currency', 'direction')
            .annotate(total=Sum('amount')).order_by('currency', 'direction'))

    def assert_archived(self, model, pk):
        self.assertTrue(model._base_manager.filter(pk=pk).exists(), f'Physical deletion of {model.__name__} #{pk}')
        obj = model._base_manager.get(pk=pk)
        self.assertIsNotNone(getattr(obj, 'archived_at', None), 'Archive must be persisted explicitly')
        return obj

    def assert_rejected(self, response):
        self.assertIn(response.status_code, (400, 409, 422), response.content)

    def assert_admin_rejected(self, response):
        self.assertEqual(response.status_code, 200, response.content)
        context = getattr(response, 'context_data', None) or {}
        admin_form = context.get('adminform')
        self.assertIsNotNone(admin_form, 'Admin must show the rejected form')
        self.assertTrue(admin_form.form.errors, 'Admin must explain why the write was rejected')

    def admin_post(self, path, data):
        if path.endswith('/add/'):
            data = {**data, 'bos_operation_id': uuid4().hex}
        if self._admin is None:
            self._admin = Client(enforce_csrf_checks=True, REMOTE_ADDR='127.0.0.1')
            self.assertTrue(self._admin.login(username='a05-synthetic-admin', password='a05-synthetic-only'))
            self.assertEqual(self._admin.get('/admin/').status_code, 200)
        return self._admin.post(path, data=data,
            HTTP_X_CSRFTOKEN=self._admin.cookies['csrftoken'].value)

    def salary_form(self, sal, **overrides):
        data = dict(employee=sal.employee_id, amount=str(sal.amount), currency=sal.currency,
            period_year=sal.period_year, period_month=sal.period_month, status=sal.status,
            payment_date=str(sal.payment_date or ''), transaction=sal.transaction_id or '',
            notes=sal.notes, _save='Зберегти')
        data.update(overrides)
        return data

    def expense_form(self, tx, **overrides):
        data = dict(direction=tx.direction, amount=str(tx.amount), currency=tx.currency,
            date=str(tx.date), description=tx.description, category=tx.category,
            counterparty=tx.counterparty_id or '', contract=tx.contract_id or '',
            branch=tx.branch_id or '', _save='Зберегти')
        data.update(overrides)
        return data


class FinanceHistoryHTTPTests(HistoryTestBase):
    def test_create_paid_cannot_leave_an_unlinked_salary_in_any_currency(self):
        for currency in CURRENCIES:
            with self.subTest(currency=currency):
                employee = self.employee()
                n_salary, n_expense = Salary.objects.count(), Transaction.objects.count()
                response = self.api('post', '/api/salaries/', dict(employee=employee.pk,
                    amount='100.25', currency=currency, period_year=2026,
                    period_month=9, status='paid', payment_date='2026-09-11'))
                if response.status_code == 201:
                    sal = Salary.objects.get(pk=response.json()['id'])
                    self.assertEqual((sal.status, sal.currency), ('paid', currency))
                    self.assertIsNotNone(sal.transaction_id, 'paid must have exactly one expense')
                    self.assertEqual(Transaction.objects.count(), n_expense + 1)
                    self.assert_history_unchanged(self.payment_snapshot(sal))
                else:
                    self.assert_rejected(response)
                    self.assertEqual(Salary.objects.count(), n_salary)
                    self.assertEqual(Transaction.objects.count(), n_expense)

    def test_editing_a_pending_salary_still_works(self):
        sal = self.salary()
        response = self.api('patch', f'/api/salaries/{sal.pk}/', {'amount': '150.75', 'currency': 'USD'})
        self.assertEqual(response.status_code, 200, response.content)
        sal.refresh_from_db()
        self.assertEqual((sal.amount, sal.currency, sal.status, sal.transaction_id),
            (Decimal('150.75'), 'USD', 'pending', None))
        self.assertEqual(Transaction.objects.count(), 0)

    def test_paid_salary_financial_fields_are_immutable(self):
        for change in (
            {'amount': '200.75'}, {'currency': 'USD'}, {'status': 'pending'},
            {'status': 'cancelled'}, {'transaction': None}, {'payment_date': '2026-09-12'},
            {'period_month': 10}, {'employee': None},
        ):
            with self.subTest(change=change):
                sal = self.salary(paid=True)
                before = self.payment_snapshot(sal)
                response = self.api('patch', f'/api/salaries/{sal.pk}/', change)
                self.assert_rejected(response)
                self.assert_history_unchanged(before)

    def test_paid_salary_cannot_be_reassigned_to_another_existing_employee(self):
        sal = self.salary(paid=True)
        other = self.employee()
        before = self.payment_snapshot(sal)
        response = self.api('patch', f'/api/salaries/{sal.pk}/', {'employee': other.pk})
        self.assert_rejected(response)
        self.assert_history_unchanged(before)

    def test_reopen_attempt_followed_by_pay_has_one_original_expense(self):
        sal = self.salary(paid=True)
        before = self.payment_snapshot(sal)
        n_expense = Transaction.objects.count()
        response = self.api('patch', f'/api/salaries/{sal.pk}/', {'status': 'pending', 'transaction': None})
        self.assert_rejected(response)
        replay = self.api('post', f'/api/salaries/{sal.pk}/pay/', {'payment_date': '2026-09-12'})
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.json()['transaction'], before['expense']['id'])
        self.assertEqual(Transaction.objects.count(), n_expense)
        self.assert_history_unchanged(before)

    def test_linked_expense_financial_fields_are_immutable(self):
        for change in (
            {'amount': '300.25'}, {'direction': 'in'}, {'currency': 'EUR'},
            {'date': '2026-09-12'}, {'category': 'other'}, {'branch': None},
        ):
            with self.subTest(change=change):
                sal = self.salary(paid=True)
                before = self.payment_snapshot(sal)
                response = self.api('patch', f'/api/transactions/{sal.transaction_id}/', change)
                self.assert_rejected(response)
                self.assert_history_unchanged(before)

    def test_put_cannot_bypass_paid_salary_protection(self):
        sal = self.salary(paid=True)
        before = self.payment_snapshot(sal)
        data = self.salary_form(sal, amount='400.25')
        data.pop('_save')
        response = self.api('put', f'/api/salaries/{sal.pk}/', data)
        self.assert_rejected(response)
        self.assert_history_unchanged(before)

    def test_put_cannot_bypass_linked_expense_protection(self):
        sal = self.salary(paid=True)
        before = self.payment_snapshot(sal)
        data = self.expense_form(sal.transaction, amount='400.25', direction='in')
        data.pop('_save')
        for field in ('counterparty', 'contract'):
            data[field] = None
        response = self.api('put', f'/api/transactions/{sal.transaction_id}/', data)
        self.assert_rejected(response)
        self.assert_history_unchanged(before)

    def _check_api_archive(self, target):
        model, endpoint, snapshot_key = target
        for currency in CURRENCIES:
            with self.subTest(model=model.__name__, currency=currency):
                sal = self.salary(currency, paid=True)
                before = self.payment_snapshot(sal)
                totals = self.ledger_totals()
                counts = (Salary._base_manager.count(), Transaction._base_manager.count(), Employee._base_manager.count())
                pk = before[snapshot_key]['id']
                response = self.api('delete', f'/api/{endpoint}/{pk}/')
                self.assertIn(response.status_code, (200, 202, 204), response.content)
                archived = self.assert_archived(model, pk)
                self.assert_history_unchanged(before)
                self.assertEqual(self.ledger_totals(), totals)
                self.assertEqual((Salary._base_manager.count(), Transaction._base_manager.count(), Employee._base_manager.count()), counts)
                first_archive = archived.archived_at
                response = self.api('delete', f'/api/{endpoint}/{pk}/')
                self.assertIn(response.status_code, (200, 202, 204, 404), response.content)
                archived.refresh_from_db()
                self.assertEqual(archived.archived_at, first_archive)
                self.assert_history_unchanged(before)
                self.assertEqual(self.ledger_totals(), totals)

    def test_archived_expenses_remain_in_financial_api_totals(self):
        for currency in CURRENCIES:
            sal = self.salary(currency, paid=True)
            response = self.api('delete', f'/api/transactions/{sal.transaction_id}/')
            self.assertIn(response.status_code, (200, 202, 204), response.content)
            self.assert_archived(Transaction, sal.transaction_id)
        response = self.http.get('/api/transactions/')
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        rows = payload.get('results', []) if isinstance(payload, dict) else payload
        totals = {}
        for row in rows:
            key = (row['currency'], row['direction'])
            totals[key] = totals.get(key, Decimal('0')) + Decimal(str(row['amount']))
        self.assertEqual(totals, {(currency, 'out'): Decimal('100.25') for currency in CURRENCIES})
        self.assertEqual(len(rows), 3)

    def test_delete_salary_archives_and_preserves_source_and_three_currency_totals(self):
        self._check_api_archive((Salary, 'salaries', 'salary'))

    def test_delete_expense_archives_and_preserves_source_and_three_currency_totals(self):
        self._check_api_archive((Transaction, 'transactions', 'expense'))

    def test_delete_employee_archives_and_preserves_source_and_three_currency_totals(self):
        self._check_api_archive((Employee, 'employees', 'employee'))

    def test_archived_pending_salary_cannot_be_paid(self):
        sal = self.salary()
        response = self.api('delete', f'/api/salaries/{sal.pk}/')
        self.assertIn(response.status_code, (200, 202, 204), response.content)
        self.assert_archived(Salary, sal.pk)
        response = self.api('post', f'/api/salaries/{sal.pk}/pay/', {'payment_date': '2026-09-11'})
        self.assertIn(response.status_code, (400, 404, 409, 422), response.content)
        historical = Salary._base_manager.get(pk=sal.pk)
        self.assertEqual((historical.status, historical.transaction_id), ('pending', None))
        self.assertEqual(Transaction._base_manager.count(), 0)

    def test_archived_employee_cannot_receive_a_new_accrual(self):
        sal = self.salary(paid=True)
        before = self.payment_snapshot(sal)
        response = self.api('delete', f'/api/employees/{sal.employee_id}/')
        self.assertIn(response.status_code, (200, 202, 204), response.content)
        self.assert_archived(Employee, sal.employee_id)
        response = self.api('post', '/api/salaries/', dict(employee=sal.employee_id,
            amount='100.25', currency='UAH', period_year=2026, period_month=10))
        self.assert_rejected(response)
        self.assertEqual(Salary._base_manager.count(), 1)
        self.assert_history_unchanged(before)

    def test_replay_after_expense_archive_never_creates_second_payment(self):
        sal = self.salary(paid=True)
        before = self.payment_snapshot(sal)
        response = self.api('delete', f'/api/transactions/{sal.transaction_id}/')
        self.assertIn(response.status_code, (200, 202, 204), response.content)
        self.assert_archived(Transaction, sal.transaction_id)
        response = self.api('post', f'/api/salaries/{sal.pk}/pay/', {'payment_date': '2026-09-12'})
        self.assertIn(response.status_code, (200, 400, 409, 422), response.content)
        self.assertEqual(Transaction._base_manager.count(), 1)
        self.assert_history_unchanged(before)


class FinanceHistoryAdminTests(HistoryTestBase):
    def test_admin_paid_without_expense_is_rejected_or_posted_atomically(self):
        for currency in CURRENCIES:
            with self.subTest(currency=currency):
                sal = self.salary(currency)
                before_count = Transaction.objects.count()
                response = self.admin_post(f'/admin/finance/salary/{sal.pk}/change/',
                    self.salary_form(sal, status='paid', payment_date='2026-09-11'))
                self.assertIn(response.status_code, (200, 302), response.content)
                sal.refresh_from_db()
                if sal.status == 'paid':
                    self.assertIsNotNone(sal.transaction_id)
                    self.assertEqual(Transaction.objects.count(), before_count + 1)
                    self.assert_history_unchanged(self.payment_snapshot(sal))
                else:
                    self.assert_admin_rejected(response)
                    self.assertEqual((sal.status, sal.transaction_id), ('pending', None))
                    self.assertEqual(Transaction.objects.count(), before_count)

    def test_admin_cannot_rewrite_a_paid_salary(self):
        sal = self.salary('EUR', paid=True)
        before = self.payment_snapshot(sal)
        response = self.admin_post(f'/admin/finance/salary/{sal.pk}/change/',
            self.salary_form(sal, amount='500.25', currency='USD', status='pending', transaction=''))
        self.assert_admin_rejected(response)
        self.assert_history_unchanged(before)

    def test_admin_cannot_rewrite_the_linked_expense(self):
        sal = self.salary('USD', paid=True)
        before = self.payment_snapshot(sal)
        response = self.admin_post(f'/admin/finance/transaction/{sal.transaction_id}/change/',
            self.expense_form(sal.transaction, amount='600.25', direction='in', currency='EUR'))
        self.assert_admin_rejected(response)
        self.assert_history_unchanged(before)

    def _check_admin_archive(self, model, key, mode):
        sal = self.salary('EUR', paid=True)
        before = self.payment_snapshot(sal)
        totals = self.ledger_totals()
        pk = before[key]['id']
        base = f'/admin/{model._meta.app_label}/{model._meta.model_name}/'
        if mode == 'single':
            response = self.admin_post(f'{base}{pk}/delete/', {'post': 'yes'})
        else:
            response = self.admin_post(base, {'action': 'delete_selected',
                '_selected_action': [str(pk)], 'post': 'yes', 'index': '0'})
        self.assertEqual(response.status_code, 302, response.content)
        self.assert_archived(model, pk)
        self.assert_history_unchanged(before)
        self.assertEqual(self.ledger_totals(), totals)

    def test_admin_single_salary_delete_archives(self):
        self._check_admin_archive(Salary, 'salary', 'single')

    def test_admin_bulk_salary_delete_archives(self):
        self._check_admin_archive(Salary, 'salary', 'bulk')

    def test_admin_single_expense_delete_archives(self):
        self._check_admin_archive(Transaction, 'expense', 'single')

    def test_admin_bulk_expense_delete_archives(self):
        self._check_admin_archive(Transaction, 'expense', 'bulk')

    def test_admin_single_employee_delete_archives(self):
        self._check_admin_archive(Employee, 'employee', 'single')

    def test_admin_bulk_employee_delete_archives(self):
        self._check_admin_archive(Employee, 'employee', 'bulk')


class FinanceLegacyEntryTests(HistoryTestBase):
    def test_ai_create_paid_never_leaves_a_salary_without_expense(self):
        employee = self.employee()
        result = execute_tool('create_salary', dict(employee_id=employee.pk,
            amount='100.25', currency='EUR', period_year=2026, period_month=9,
            status='paid', payment_date='2026-09-11'))
        self.assertIsInstance(result, str)
        rows = list(Salary._base_manager.filter(employee=employee))
        if not rows:
            self.assertEqual(Transaction._base_manager.count(), 0)
            return
        self.assertEqual(len(rows), 1)
        sal = rows[0]
        if sal.status == 'paid':
            self.assertIsNotNone(sal.transaction_id, result)
            self.assertEqual(Transaction._base_manager.count(), 1)
            self.assert_history_unchanged(self.payment_snapshot(sal))
        else:
            self.assertEqual((sal.status, sal.transaction_id), ('pending', None))
            self.assertEqual(Transaction._base_manager.count(), 0)

    def test_ai_cannot_create_negative_financial_rows(self):
        employee = self.employee()
        for tool, data in (
            ('create_salary', dict(employee_id=employee.pk, amount='-100.25', currency='EUR',
                period_year=2026, period_month=9)),
            ('create_transaction', dict(direction='out', amount='-100.25', currency='EUR',
                date='2026-09-11', description='Синтетична недопустима витрата', category='other')),
        ):
            with self.subTest(tool=tool):
                before = (Salary._base_manager.count(), Transaction._base_manager.count())
                result = execute_tool(tool, data)
                self.assertIsInstance(result, str)
                self.assertEqual((Salary._base_manager.count(), Transaction._base_manager.count()), before, result)

    def test_ai_delete_employee_preserves_history_and_archives_same_id(self):
        sal = self.salary('EUR', paid=True)
        before = self.payment_snapshot(sal)
        result = execute_tool('delete_employee', {'employee_id': sal.employee_id})
        self.assertIsInstance(result, str)
        self.assert_archived(Employee, sal.employee_id)
        self.assert_history_unchanged(before)

    def test_ai_undo_employee_creation_preserves_existing_payroll_history(self):
        employee = self.employee()
        EmployeeChangeLog.objects.create(action='create', employee_id=employee.pk,
            employee_name=employee.full_name, after=employee_to_dict(employee))
        sal = Salary.objects.create(employee=employee, amount='100.25', currency='USD',
            period_year=2026, period_month=9)
        sal.mark_paid('2026-09-11')
        before = self.payment_snapshot(sal)
        result = execute_tool('undo_last_change', {})
        self.assertIsInstance(result, str)
        # A payroll dependency may make undo impossible; it may be rejected or
        # archive the employee. Neither outcome can remove historical records.
        self.assert_history_unchanged(before)

    def test_ai_undo_employee_archive_never_allocates_a_replacement_id(self):
        sal = self.salary('UAH', paid=True)
        before = self.payment_snapshot(sal)
        result = execute_tool('delete_employee', {'employee_id': sal.employee_id})
        self.assertIsInstance(result, str)
        self.assert_archived(Employee, sal.employee_id)
        count = Employee._base_manager.count()
        execute_tool('undo_last_change', {})
        self.assertEqual(Employee._base_manager.count(), count)
        self.assert_history_unchanged(before)

    @override_settings(BOS_DATA_MODE='working')
    def test_cli_demo_seeds_refuse_working_mode_without_touching_history(self):
        sal = self.salary(paid=True)
        before = self.payment_snapshot(sal)
        for name in ('seed_bos_demo', 'seed_erp_demo', 'seed_bos_workspace'):
            with self.subTest(command=name):
                with self.assertRaises(CommandError):
                    call_command(name, stdout=StringIO(), stderr=StringIO())
                self.assert_history_unchanged(before)

    @override_settings(BOS_DATA_MODE='working')
    def test_cli_branch_seed_cannot_change_working_financial_attribution(self):
        sal = self.salary(paid=True)
        before = self.payment_snapshot(sal)
        branches = list(Branch.objects.order_by('pk').values())
        with self.assertRaises(CommandError):
            call_command('seed_branches', stdout=StringIO(), stderr=StringIO())
        self.assertEqual(list(Branch.objects.order_by('pk').values()), branches)
        self.assert_history_unchanged(before)

    @override_settings(BOS_DATA_MODE='working')
    def test_cli_branch_reset_cannot_detach_historical_expense(self):
        sal = self.salary('EUR', paid=True)
        before = self.payment_snapshot(sal)
        branches = list(Branch.objects.order_by('pk').values())
        with self.assertRaises(CommandError):
            call_command('seed_branches', reset=True, stdout=StringIO(), stderr=StringIO())
        self.assertEqual(list(Branch.objects.order_by('pk').values()), branches)
        self.assert_history_unchanged(before)
