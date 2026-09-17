from scripts.check_support import login_test_client
"""A02: real transactions, threads, HTTP requests and database failure."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
import threading

from django.db import connection, connections, IntegrityError
from django.test import Client, TransactionTestCase
from employees.models import Employee
from .models import Salary, Transaction


class PaymentIntegrityTests(TransactionTestCase):
    def salary(self, currency='UAH', month=1):
        employee = Employee.objects.create(full_name='Синтетичний працівник A02 ' + currency)
        return Salary.objects.create(employee=employee, amount=Decimal('100.00'),
            currency=currency, period_year=2026, period_month=month)

    def client_with_csrf(self):
        client = Client(enforce_csrf_checks=True)
        login_test_client(client)
        client.get('/api/operations/status/')
        return client

    def pay(self, client, salary, payment_date='2026-09-11'):
        return client.post(f'/api/salaries/{salary.id}/pay/', {'payment_date': payment_date},
            content_type='application/json', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)

    def assert_one_payment(self, salary, count_before=0):
        salary.refresh_from_db()
        self.assertEqual(salary.status, 'paid')
        self.assertIsNotNone(salary.transaction_id)
        self.assertEqual(Transaction.objects.count(), count_before + 1)
        tx = salary.transaction
        self.assertEqual((tx.amount, tx.currency, tx.direction, tx.category),
            (Decimal('100.00'), salary.currency, 'out', 'salary'))
        self.assertEqual(tx.salary_record.id, salary.id)

    def test_each_currency_is_preserved(self):
        for currency in ('EUR', 'USD', 'UAH'):
            with self.subTest(currency=currency):
                n = Transaction.objects.count(); salary = self.salary(currency)
                _, tx = salary.mark_paid('2026-09-11')
                self.assert_one_payment(salary, n)
                self.assertEqual(tx.currency, currency)

    def test_http_replay_returns_same_receipt_without_second_expense(self):
        salary = self.salary(); client = self.client_with_csrf()
        first = self.pay(client, salary); again = self.pay(client, salary, '2026-09-12')
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(first.json(), again.json())
        self.assert_one_payment(salary)
        self.assertEqual(salary.payment_date, date(2026, 9, 11))

    def test_two_concurrent_stale_instances_produce_one_expense(self):
        for currency in ('EUR', 'USD', 'UAH'):
            with self.subTest(currency=currency):
                salary = self.salary(currency); before = Transaction.objects.count()
                ready = threading.Barrier(2)
                def worker():
                    try:
                        stale = Salary.objects.get(pk=salary.id)
                        ready.wait(timeout=10)
                        paid, tx = stale.mark_paid('2026-09-11')
                        return paid.status, paid.transaction_id, tx.id, str(tx.amount), tx.currency
                    finally:
                        connections.close_all()
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(lambda _: worker(), range(2)))
                self.assertEqual(results[0], results[1])
                self.assert_one_payment(salary, before)

    def test_two_concurrent_http_requests_return_identical_receipts(self):
        salary = self.salary(); clients = [self.client_with_csrf(), self.client_with_csrf()]
        ready = threading.Barrier(2)
        def worker(client):
            try:
                ready.wait(timeout=10)
                response = self.pay(client, salary)
                return response.status_code, response.json()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, clients))
        self.assertEqual([x[0] for x in results], [200, 200], results)
        self.assertEqual(results[0][1], results[1][1])
        self.assert_one_payment(salary)

    @contextmanager
    def reject_final_salary_update(self):
        # Real constraint failure after Transaction INSERT, not a mocked save.
        with connection.cursor() as cursor:
            if connection.vendor == 'sqlite':
                cursor.execute("""CREATE TRIGGER a02_reject_paid BEFORE UPDATE OF status ON finance_salary
                    WHEN NEW.status = 'paid' AND OLD.status != 'paid'
                    BEGIN SELECT RAISE(ABORT, 'A02 synthetic failure after expense'); END""")
            else:
                cursor.execute("""CREATE FUNCTION a02_reject_paid_fn() RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN IF NEW.status = 'paid' AND OLD.status != 'paid' THEN
                    RAISE EXCEPTION 'A02 synthetic failure after expense' USING ERRCODE = '23000';
                    END IF; RETURN NEW; END; $$""")
                cursor.execute('CREATE TRIGGER a02_reject_paid BEFORE UPDATE ON finance_salary FOR EACH ROW EXECUTE FUNCTION a02_reject_paid_fn()')
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute('DROP TRIGGER a02_reject_paid' + (' ON finance_salary' if connection.vendor == 'postgresql' else ''))
                if connection.vendor == 'postgresql':
                    cursor.execute('DROP FUNCTION a02_reject_paid_fn()')

    def test_error_after_expense_insert_rolls_back_and_retry_succeeds(self):
        salary = self.salary()
        with self.reject_final_salary_update(), self.assertRaises(IntegrityError):
            salary.mark_paid('2026-09-11')
        salary.refresh_from_db()
        self.assertEqual((salary.status, salary.transaction_id, salary.payment_date), ('pending', None, None))
        self.assertEqual(Transaction.objects.count(), 0)
        salary.mark_paid('2026-09-11')
        self.assert_one_payment(salary)

    def test_inconsistent_paid_history_is_not_rewritten(self):
        salary = self.salary(); salary.status = 'paid'; salary.save(update_fields=['status'])
        with self.assertRaises(ValueError):
            salary.mark_paid('2026-09-11')
        salary.refresh_from_db()
        self.assertEqual((salary.status, salary.transaction_id), ('paid', None))
        self.assertEqual(Transaction.objects.count(), 0)
