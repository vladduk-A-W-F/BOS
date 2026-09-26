"""A06 independent financial-intent and mixed-operation regressions.

Only Django's disposable verification test database is supported.  Threads
hold separate real database connections; neither HTTP nor business commands
are mocked.  The operation key identifies intent, never amount/date equality.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
import json
import threading

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection, connections
from django.test import Client, TransactionTestCase

from ai_assistant.views import _create_salary, _create_transaction
from boss_project.archive import restore_record
from branches.models import Branch
from employees.models import Employee
from finance.commands import save_salary, save_transaction
from finance.models import Contract, Counterparty, Salary, Transaction
from operations.models import AuditEvent
from scripts.check_support import login_test_client


CURRENCIES = ('EUR', 'USD', 'UAH')
PASSWORD = 'synthetic-test-login-only'


class FinancialIntentConcurrencyTests(TransactionTestCase):
    """Every successful create must have one durable receipt and one audit."""

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True, raise_request_exception=False,
                             REMOTE_ADDR='127.0.0.1')
        self.actor = login_test_client(self.client)
        self.employee = Employee.objects.create(full_name='Синтетичний A06', role='Тест')
        self.branch = Branch.objects.create(code='A06', name='Синтетична A06')
        self.counterparty = Counterparty.objects.create(name='Синтетичний контрагент A06')
        self.contract = Contract.objects.create(number='A06-01', name='Синтетичний A06',
                                                counterparty=self.counterparty)

    def tx_payload(self, currency='UAH', **changes):
        value = dict(direction='out', amount='100.20', currency=currency,
                     date='2026-09-11', description='Синтетична закупівля A06',
                     category='supplier', counterparty=self.counterparty.pk,
                     contract=self.contract.pk, branch=self.branch.pk)
        value.update(changes)
        return value

    def salary_payload(self, currency='UAH', **changes):
        value = dict(employee=self.employee.pk, amount='100.20', currency=currency,
                     period_year=2026, period_month=9, notes='Синтетичне нарахування A06')
        value.update(changes)
        return value

    def second_client(self, actor=None):
        actor = actor or self.actor
        client = Client(enforce_csrf_checks=True, raise_request_exception=False,
                        REMOTE_ADDR='127.0.0.1')
        self.assertEqual(client.get('/api/auth/csrf/').status_code, 200)
        response = client.post('/api/auth/login/',
            {'username': actor.username, 'password': PASSWORD}, content_type='application/json',
            HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(client.session.get('_auth_user_id'), str(actor.pk))
        return client

    def request(self, client, method, path, payload=None, key=None):
        headers = {'HTTP_X_CSRFTOKEN': client.cookies[settings.CSRF_COOKIE_NAME].value}
        if key is not None:
            headers['HTTP_IDEMPOTENCY_KEY'] = key
        response = getattr(client, method)(path, data=json.dumps(payload or {}),
            content_type='application/json', **headers)
        try:
            body = response.json()
        except (ValueError, TypeError):
            body = response.content.decode(errors='replace')[:2000]
        return response.status_code, body

    def create_http(self, kind, payload, key, client=None, path=None):
        path = path or ('/api/transactions/' if kind == 'transaction' else '/api/salaries/')
        return self.request(client or self.client, 'post', path, payload, key)

    def pair(self, left, right):
        barrier = threading.Barrier(2)
        live_connections = []
        connection_lock = threading.Lock()

        def worker(operation):
            connections.close_all()
            try:
                connection.ensure_connection()
                # Keep references alive through both operations, so a reused
                # Python id cannot falsely prove connection independence.
                with connection_lock:
                    live_connections.append(connection.connection)
                barrier.wait(timeout=15)
                return operation()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker, operation) for operation in (left, right)]
            results = [future.result(timeout=45) for future in futures]
        self.assertEqual(len(live_connections), 2)
        self.assertIsNot(live_connections[0], live_connections[1])
        return results

    def intents(self):
        # Import at assertion time: an absent A06 model is a failing contract,
        # not an import error which prevents unrelated red tests from running.
        from finance.models import FinancialIntent
        return FinancialIntent.objects.all()

    def assert_created_once(self, kind, pk, currency='UAH', amount='100.20'):
        model = Transaction if kind == 'transaction' else Salary
        row = model.objects.get(pk=pk)
        self.assertEqual((row.amount, row.currency), (Decimal(amount), currency))
        self.assertEqual(AuditEvent.objects.filter(action=kind + '.create',
                                                  payload__id=pk).count(), 1)
        self.assertEqual(self.intents().filter(**{kind + '_id': pk}).count(), 1)
        receipt = self.intents().get(**{kind + '_id': pk})
        self.assertRegex(str(receipt.pk), r'^[0-9a-f]{64}$')
        self.assertRegex(receipt.payload_hash, r'^[0-9a-f]{64}$')
        self.assertIsNotNone(receipt.created_at)
        return row

    def assert_http_pair_replays(self, results, retry):
        # The accepted A06 contract permits one explicit conflict while the
        # other caller commits.  It does not permit two conflicts, HTTP 500,
        # two material effects, or failure to recover the original receipt.
        self.assertTrue(all(r[0] in (201, 409) for r in results), results)
        successes = [r for r in results if r[0] == 201]
        self.assertTrue(successes, results)
        pk = successes[0][1]['id']
        self.assertTrue(all(r[1]['id'] == pk for r in successes), results)
        again = retry()
        self.assertEqual(again[0], 201, again)
        self.assertEqual(again[1]['id'], pk)
        return pk

    def orm_keyed(self, command, payload, key):
        import finance.commands as commands
        try:
            row = command(changes=dict(payload), actor=self.actor, operation_id=key)
            return 201, row.pk
        except Exception as exc:
            conflict = getattr(commands, 'FinancialIntentConflict', None)
            if conflict is None or not isinstance(exc, conflict):
                raise
            return 409, str(exc)

    def assert_orm_pair_replays(self, results, retry):
        self.assertTrue(all(r[0] in (201, 409) for r in results), results)
        successes = [r for r in results if r[0] == 201]
        self.assertTrue(successes, results)
        pk = successes[0][1]
        self.assertTrue(all(r[1] == pk for r in successes), results)
        self.assertEqual(retry(), (201, pk))
        return pk

    def test_transaction_http_same_key_concurrent_all_currencies(self):
        other = self.second_client()
        for currency in CURRENCIES:
            with self.subTest(currency=currency):
                payload = self.tx_payload(currency)
                before = Transaction.objects.count()
                key = 'http-tx-' + currency
                results = self.pair(lambda: self.create_http('transaction', payload, key),
                                    lambda: self.create_http('transaction', payload, key, other))
                pk = self.assert_http_pair_replays(results,
                    lambda: self.create_http('transaction', payload, key))
                self.assertEqual(Transaction.objects.count(), before + 1)
                self.assert_created_once('transaction', pk, currency)

    def test_salary_http_same_key_concurrent_all_currencies(self):
        other = self.second_client()
        for month, currency in enumerate(CURRENCIES, 1):
            with self.subTest(currency=currency):
                payload = self.salary_payload(currency, period_month=month)
                before = Salary.objects.count()
                key = 'http-salary-' + currency
                results = self.pair(lambda: self.create_http('salary', payload, key),
                                    lambda: self.create_http('salary', payload, key, other))
                pk = self.assert_http_pair_replays(results,
                    lambda: self.create_http('salary', payload, key))
                self.assertEqual(Salary.objects.count(), before + 1)
                self.assertEqual(Transaction.objects.count(), 0)
                self.assert_created_once('salary', pk, currency)

    def test_transaction_orm_same_key_concurrent_all_currencies(self):
        for currency in CURRENCIES:
            with self.subTest(currency=currency):
                payload = self.tx_payload(currency)
                before = Transaction.objects.count()
                def operation():
                    return self.orm_keyed(save_transaction, payload, 'orm-tx-' + currency)
                results = self.pair(operation, operation)
                pk = self.assert_orm_pair_replays(results, operation)
                self.assertEqual(Transaction.objects.count(), before + 1)
                self.assert_created_once('transaction', pk, currency)

    def test_salary_orm_same_key_concurrent_all_currencies(self):
        for month, currency in enumerate(CURRENCIES, 1):
            with self.subTest(currency=currency):
                payload = self.salary_payload(currency, period_month=month)
                before = Salary.objects.count()
                def operation():
                    return self.orm_keyed(save_salary, payload, 'orm-salary-' + currency)
                results = self.pair(operation, operation)
                pk = self.assert_orm_pair_replays(results, operation)
                self.assertEqual(Salary.objects.count(), before + 1)
                self.assertEqual(Transaction.objects.count(), 0)
                self.assert_created_once('salary', pk, currency)

    def test_transaction_http_same_key_changed_full_payload_is_409(self):
        other_cp = Counterparty.objects.create(name='Інший синтетичний A06')
        other_contract = Contract.objects.create(number='A06-02', name='Другий A06', counterparty=other_cp)
        other_branch = Branch.objects.create(code='A06-02', name='Другий A06')
        first = self.create_http('transaction', self.tx_payload(), 'same-payload')
        self.assertEqual(first[0], 201, first)
        before = Transaction.objects.values().get(pk=first[1]['id'])
        for change in ({'amount': '101.20'}, {'currency': 'EUR'}, {'date': '2026-09-12'},
                       {'direction': 'in'}, {'description': 'Інший намір'}, {'category': 'other'},
                       {'counterparty': other_cp.pk}, {'contract': other_contract.pk},
                       {'branch': other_branch.pk}):
            with self.subTest(change=change):
                response = self.create_http('transaction', self.tx_payload(**change), 'same-payload')
                self.assertEqual(response[0], 409, response)
                self.assertEqual(Transaction.objects.values().get(pk=first[1]['id']), before)
                self.assertEqual(Transaction.objects.count(), 1)
                self.assertEqual(AuditEvent.objects.filter(action='transaction.create').count(), 1)
                self.assertEqual(self.intents().count(), 1)

    def test_salary_http_same_key_changed_full_payload_is_409(self):
        other_employee = Employee.objects.create(full_name='Інший A06', role='Тест')
        first = self.create_http('salary', self.salary_payload(), 'salary-same-payload')
        self.assertEqual(first[0], 201, first)
        before = Salary.objects.values().get(pk=first[1]['id'])
        for change in ({'amount': '101.20'}, {'currency': 'EUR'}, {'employee': other_employee.pk},
                       {'period_month': 10}, {'period_year': 2027}, {'notes': 'Інший намір'},
                       {'status': 'cancelled'}):
            with self.subTest(change=change):
                response = self.create_http('salary', self.salary_payload(**change), 'salary-same-payload')
                self.assertEqual(response[0], 409, response)
                self.assertEqual(Salary.objects.values().get(pk=first[1]['id']), before)
                self.assertEqual(Salary.objects.count(), 1)
                self.assertEqual(Transaction.objects.count(), 0)
                self.assertEqual(AuditEvent.objects.filter(action='salary.create').count(), 1)
                self.assertEqual(self.intents().count(), 1)

    def test_transaction_http_same_key_concurrent_mismatch_has_one_winner(self):
        other = self.second_client()
        payloads = [self.tx_payload(amount=value) for value in ('100.20', '200.30')]
        results = self.pair(lambda: self.create_http('transaction', payloads[0], 'tx-mismatch'),
                            lambda: self.create_http('transaction', payloads[1], 'tx-mismatch', other))
        self.assertEqual(sorted(r[0] for r in results), [201, 409], results)
        winner = results.index(next(r for r in results if r[0] == 201))
        self.assertEqual(Transaction.objects.count(), 1)
        self.assert_created_once('transaction', results[winner][1]['id'], amount=payloads[winner]['amount'])

    def test_salary_http_same_key_concurrent_mismatch_has_one_winner(self):
        other = self.second_client()
        payloads = [self.salary_payload(amount=value) for value in ('100.20', '200.30')]
        results = self.pair(lambda: self.create_http('salary', payloads[0], 'salary-mismatch'),
                            lambda: self.create_http('salary', payloads[1], 'salary-mismatch', other))
        self.assertEqual(sorted(r[0] for r in results), [201, 409], results)
        winner = results.index(next(r for r in results if r[0] == 201))
        self.assertEqual(Salary.objects.count(), 1)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assert_created_once('salary', results[winner][1]['id'], amount=payloads[winner]['amount'])

    def test_different_keys_identical_transaction_facts_remain_two_legitimate_rows(self):
        other = self.second_client()
        payload = self.tx_payload()
        results = self.pair(lambda: self.create_http('transaction', payload, 'distinct-1'),
                            lambda: self.create_http('transaction', payload, 'distinct-2', other))
        self.assertTrue(all(r[0] in (201, 409) for r in results), results)
        self.assertTrue(any(r[0] == 201 for r in results), results)
        retries = [self.create_http('transaction', payload, key, client)
                   for key, client in (('distinct-1', self.client), ('distinct-2', other))]
        self.assertEqual([r[0] for r in retries], [201, 201], retries)
        for first, retry in zip(results, retries):
            if first[0] == 201:
                self.assertEqual(first[1]['id'], retry[1]['id'])
        self.assertNotEqual(retries[0][1]['id'], retries[1][1]['id'])
        self.assertEqual(Transaction.objects.count(), 2)
        self.assertEqual(self.intents().count(), 2)
        self.assertEqual(AuditEvent.objects.filter(action='transaction.create').count(), 2)
        self.assertEqual(sum(Transaction.objects.values_list('amount', flat=True)), Decimal('200.40'))

    def test_different_keys_cannot_duplicate_one_salary_period(self):
        other = self.second_client()
        payload = self.salary_payload()
        results = self.pair(lambda: self.create_http('salary', payload, 'period-1'),
                            lambda: self.create_http('salary', payload, 'period-2', other))
        self.assertEqual(sum(r[0] == 201 for r in results), 1, results)
        self.assertTrue(all(r[0] in (201, 400, 409) for r in results), results)
        self.assertEqual(Salary.objects.count(), 1)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(self.intents().count(), 1, 'Rejected natural duplicate must not leave an intent claim')
        self.assertEqual(AuditEvent.objects.filter(action='salary.create').count(), 1)

    def test_required_http_header_missing_is_400_without_writes(self):
        for kind, payload in (('transaction', self.tx_payload()), ('salary', self.salary_payload())):
            with self.subTest(kind=kind):
                response = self.create_http(kind, payload, None)
                self.assertEqual(response[0], 400, response)
                self.assertEqual(Transaction.objects.count(), 0)
                self.assertEqual(Salary.objects.count(), 0)
                self.assertEqual(AuditEvent.objects.filter(action__in=('salary.create', 'transaction.create')).count(), 0)

    def test_invalid_http_keys_are_400_without_writes(self):
        for kind, payload in (('transaction', self.tx_payload()), ('salary', self.salary_payload())):
            for key in ('', ' ', 'with space', 'а06', 'slash/key', 'x' * 129, '\tkey'):
                with self.subTest(kind=kind, key=repr(key)):
                    response = self.create_http(kind, payload, key)
                    self.assertEqual(response[0], 400, response)
                    self.assertEqual(Transaction.objects.count(), 0)
                    self.assertEqual(Salary.objects.count(), 0)
                    self.assertEqual(AuditEvent.objects.filter(action__in=('salary.create', 'transaction.create')).count(), 0)

    def test_http_key_ascii_boundary_and_model_namespace(self):
        for index, key in enumerate(('k', 'A06:allowed_0.1-test', 'x' * 128), 1):
            with self.subTest(key=key):
                tx = self.create_http('transaction', self.tx_payload(), key)
                salary = self.create_http('salary', self.salary_payload(period_month=index), key)
                self.assertEqual([tx[0], salary[0]], [201, 201], [tx, salary])
                self.assert_created_once('transaction', tx[1]['id'])
                self.assert_created_once('salary', salary[1]['id'])
        self.assertEqual(self.intents().count(), 6)

    def test_transaction_format_aliases_replay_one_intent(self):
        first = self.create_http('transaction', self.tx_payload(), 'tx-alias')
        self.assertEqual(first[0], 201, first)
        for path in ('/api/transactions.json', '/api/transactions.json/', '/api/transactions/?format=json'):
            with self.subTest(path=path):
                response = self.create_http('transaction', self.tx_payload(), 'tx-alias', path=path)
                self.assertEqual(response[0], 201, response)
                self.assertEqual(response[1]['id'], first[1]['id'])
                self.assertEqual(Transaction.objects.count(), 1)
                self.assert_created_once('transaction', first[1]['id'])

    def test_salary_format_aliases_replay_one_intent(self):
        first = self.create_http('salary', self.salary_payload(), 'salary-alias')
        self.assertEqual(first[0], 201, first)
        for path in ('/api/salaries.json', '/api/salaries.json/', '/api/salaries/?format=json'):
            with self.subTest(path=path):
                response = self.create_http('salary', self.salary_payload(), 'salary-alias', path=path)
                self.assertEqual(response[0], 201, response)
                self.assertEqual(response[1]['id'], first[1]['id'])
                self.assertEqual(Salary.objects.count(), 1)
                self.assert_created_once('salary', first[1]['id'])

    def test_orm_transaction_equivalent_decimal_date_and_fk_forms_replay(self):
        first = save_transaction(changes=self.tx_payload(amount=Decimal('100.20'),
            date=date(2026, 9, 11), counterparty=self.counterparty, contract=self.contract,
            branch=self.branch), actor=self.actor, operation_id='normalize-tx')
        second_payload = self.tx_payload(amount='100.2', counterparty=str(self.counterparty.pk),
                                         contract=str(self.contract.pk), branch=str(self.branch.pk))
        for field in ('counterparty', 'contract', 'branch'):
            second_payload[field + '_id'] = second_payload.pop(field)
        second = save_transaction(changes=second_payload, actor=self.actor, operation_id='normalize-tx')
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(Transaction.objects.count(), 1)
        self.assert_created_once('transaction', first.pk)

    def test_orm_salary_equivalent_numbers_fk_and_explicit_defaults_replay(self):
        first = save_salary(changes=self.salary_payload(employee=self.employee,
            amount=Decimal('100.20')), actor=self.actor, operation_id='normalize-salary')
        payload = self.salary_payload(amount='100.2', period_year='2026', period_month='9',
            status='pending', payment_date=None, transaction=None)
        payload['employee_id'] = str(payload.pop('employee'))
        second = save_salary(changes=payload, actor=self.actor, operation_id='normalize-salary')
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(Salary.objects.count(), 1)
        self.assert_created_once('salary', first.pk)

    def test_transaction_http_replay_after_archive_returns_fresh_historical_row(self):
        first = self.create_http('transaction', self.tx_payload(), 'archive-tx')
        self.assertEqual(first[0], 201, first)
        pk = first[1]['id']
        self.assertEqual(self.request(self.client, 'delete', f'/api/transactions/{pk}/')[0], 204)
        before = Transaction.objects.values().get(pk=pk)
        self.assertIsNotNone(before['archived_at'])
        replay = self.create_http('transaction', self.tx_payload(), 'archive-tx')
        self.assertEqual(replay[0], 201, replay)
        self.assertEqual(replay[1]['id'], pk)
        self.assertTrue(replay[1]['archived_at'])
        self.assertEqual(Transaction.objects.values().get(pk=pk), before)
        self.assertEqual(Transaction.objects.count(), 1)
        self.assert_created_once('transaction', pk)
        self.assertEqual(AuditEvent.objects.filter(action='transaction.archive').count(), 1)

    def test_salary_http_replay_after_archive_preserves_marker_and_id(self):
        first = self.create_http('salary', self.salary_payload(), 'archive-salary')
        self.assertEqual(first[0], 201, first)
        pk = first[1]['id']
        self.assertEqual(self.request(self.client, 'delete', f'/api/salaries/{pk}/')[0], 204)
        before = Salary.objects.values().get(pk=pk)
        replay = self.create_http('salary', self.salary_payload(), 'archive-salary')
        self.assertEqual(replay[0], 201, replay)
        self.assertEqual(replay[1]['id'], pk)
        self.assertTrue(replay[1]['archived_at'])
        self.assertEqual(Salary.objects.values().get(pk=pk), before)
        self.assertEqual(Salary.objects.count(), 1)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assert_created_once('salary', pk)
        self.assertEqual(AuditEvent.objects.filter(action='salary.archive').count(), 1)

    def test_salary_create_replay_after_payment_does_not_reopen_or_add_expense(self):
        first = self.create_http('salary', self.salary_payload(), 'paid-salary')
        self.assertEqual(first[0], 201, first)
        pk = first[1]['id']
        paid = self.request(self.client, 'post', f'/api/salaries/{pk}/pay/', {'payment_date': '2026-09-11'})
        self.assertEqual(paid[0], 200, paid)
        before = Salary.objects.values().get(pk=pk)
        replay = self.create_http('salary', self.salary_payload(), 'paid-salary')
        self.assertEqual(replay[0], 201, replay)
        self.assertEqual((replay[1]['id'], replay[1]['status'], replay[1]['transaction']),
                         (pk, 'paid', before['transaction_id']))
        self.assertEqual(Salary.objects.values().get(pk=pk), before)
        self.assertEqual((Salary.objects.count(), Transaction.objects.count()), (1, 1))
        self.assert_created_once('salary', pk)

    def test_same_key_second_actor_creates_separate_legitimate_intent(self):
        other = Client(enforce_csrf_checks=True, raise_request_exception=False)
        second_actor = login_test_client(other)
        self.assertNotEqual(self.actor.pk, second_actor.pk)
        left = self.create_http('transaction', self.tx_payload(), 'per-actor')
        right = self.create_http('transaction', self.tx_payload(), 'per-actor', other)
        self.assertEqual([left[0], right[0]], [201, 201], [left, right])
        self.assertNotEqual(left[1]['id'], right[1]['id'])
        self.assertEqual(Transaction.objects.count(), 2)
        self.assertEqual(self.intents().count(), 2)

    def test_role_revocation_is_checked_before_financial_intent_replay(self):
        first = self.create_http('transaction', self.tx_payload(), 'revoked')
        self.assertEqual(first[0], 201, first)
        self.actor.groups.set([Group.objects.get_or_create(name='manager')[0]])
        replay = self.create_http('transaction', self.tx_payload(), 'revoked')
        self.assertEqual(replay[0], 403, replay)
        self.assertNotIn('100.20', str(replay[1]))
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(self.intents().count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action='transaction.create').count(), 1)

    @contextmanager
    def reject_create_audit(self, kind):
        if kind not in ('salary', 'transaction'):
            raise ValueError('Synthetic trigger kind is fixed')
        action = kind + '.create'
        with connection.cursor() as cursor:
            if connection.vendor == 'sqlite':
                cursor.execute(f"""CREATE TRIGGER a06_reject_audit BEFORE INSERT ON operations_auditevent
                    WHEN NEW.action = '{action}'
                    BEGIN SELECT RAISE(ABORT, 'A06 synthetic failure after financial INSERT'); END""")
            elif connection.vendor == 'postgresql':
                cursor.execute(f"""CREATE FUNCTION a06_reject_audit_fn() RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN IF NEW.action = '{action}' THEN
                    RAISE EXCEPTION 'A06 synthetic failure after financial INSERT' USING ERRCODE = '23000';
                    END IF; RETURN NEW; END; $$""")
                cursor.execute('CREATE TRIGGER a06_reject_audit BEFORE INSERT ON operations_auditevent FOR EACH ROW EXECUTE FUNCTION a06_reject_audit_fn()')
            else:
                raise RuntimeError('Only real SQLite/PostgreSQL are accepted')
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute('DROP TRIGGER a06_reject_audit' +
                    (' ON operations_auditevent' if connection.vendor == 'postgresql' else ''))
                if connection.vendor == 'postgresql':
                    cursor.execute('DROP FUNCTION a06_reject_audit_fn()')

    def rollback_case(self, kind, payload):
        with self.reject_create_audit(kind):
            response = self.create_http(kind, payload, 'audit-failure')
        self.assertEqual(response[0], 409, response)
        self.assertEqual((Transaction.objects.count(), Salary.objects.count()), (0, 0))
        self.assertEqual(self.intents().count(), 0, 'A failed command cannot consume its operation key')
        self.assertEqual(AuditEvent.objects.filter(action=kind + '.create').count(), 0)
        first = self.create_http(kind, payload, 'audit-failure')
        replay = self.create_http(kind, payload, 'audit-failure')
        self.assertEqual([first[0], replay[0]], [201, 201], [first, replay])
        self.assertEqual(first[1]['id'], replay[1]['id'])
        self.assert_created_once(kind, first[1]['id'])

    def test_transaction_audit_failure_rolls_back_intent_money_and_retries(self):
        self.rollback_case('transaction', self.tx_payload())

    def test_salary_audit_failure_rolls_back_intent_accrual_and_retries(self):
        self.rollback_case('salary', self.salary_payload())

    def test_orm_mismatch_raises_explicit_intent_conflict_without_mutation(self):
        import finance.commands as commands
        for kind, command, payload in (('transaction', save_transaction, self.tx_payload()),
                                        ('salary', save_salary, self.salary_payload())):
            with self.subTest(kind=kind):
                row = command(changes=payload, actor=self.actor, operation_id='orm-conflict')
                conflict = getattr(commands, 'FinancialIntentConflict', None)
                self.assertIsNotNone(conflict, 'Mismatch needs the explicit FinancialIntentConflict contract')
                with self.assertRaises(conflict):
                    command(changes={**payload, 'amount': '201.20'}, actor=self.actor,
                            operation_id='orm-conflict')
                self.assert_created_once(kind, row.pk)

    def test_legacy_transaction_helper_propagates_one_operation_key(self):
        payload = self.tx_payload()
        payload['counterparty_id'] = payload.pop('counterparty')
        payload['operation_id'] = 'legacy-tx'
        first = _create_transaction(dict(payload))
        second = _create_transaction(dict(payload))
        self.assertEqual(first, second)
        self.assertEqual(Transaction.objects.count(), 1)
        self.assert_created_once('transaction', Transaction.objects.get().pk)

    def test_legacy_salary_helper_propagates_one_operation_key(self):
        payload = self.salary_payload()
        payload['employee_id'] = payload.pop('employee')
        payload['operation_id'] = 'legacy-salary'
        first = _create_salary(dict(payload))
        second = _create_salary(dict(payload))
        self.assertEqual(first, second)
        self.assertEqual(Salary.objects.count(), 1)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assert_created_once('salary', Salary.objects.get().pk)

    def test_same_salary_pay_racing_edit_keeps_matching_expense_all_currencies(self):
        other = self.second_client()
        for month, currency in enumerate(CURRENCIES, 1):
            with self.subTest(currency=currency):
                salary = Salary.objects.create(employee=self.employee, amount='100.20', currency=currency,
                                               period_year=2026, period_month=month)
                before = Transaction.objects.count()
                results = self.pair(
                    lambda: self.request(self.client, 'post', f'/api/salaries/{salary.pk}/pay/', {'payment_date': '2026-09-11'}),
                    lambda: self.request(other, 'patch', f'/api/salaries/{salary.pk}/', {'amount': '200.30'}))
                self.assertEqual(results[0][0], 200, results)
                self.assertIn(results[1][0], (200, 400, 409), results)
                salary.refresh_from_db()
                self.assertEqual(salary.status, 'paid')
                self.assertIsNotNone(salary.transaction_id)
                self.assertEqual(Transaction.objects.count(), before + 1)
                expense = salary.transaction
                self.assertEqual((expense.amount, expense.currency, expense.date),
                                 (salary.amount, currency, salary.payment_date))
                self.assertEqual((expense.direction, expense.category), ('out', 'salary'))
                self.assertEqual(salary.amount, Decimal('200.30') if results[1][0] == 200 else Decimal('100.20'))

    def test_same_salary_pay_racing_archive_preserves_one_serial_history(self):
        other = self.second_client()
        salary = Salary.objects.create(employee=self.employee, amount='100.20', currency='EUR',
                                       period_year=2026, period_month=9)
        results = self.pair(
            lambda: self.request(self.client, 'post', f'/api/salaries/{salary.pk}/pay/', {'payment_date': '2026-09-11'}),
            lambda: self.request(other, 'delete', f'/api/salaries/{salary.pk}/'))
        self.assertIn(results[0][0], (200, 400), results)
        self.assertEqual(results[1][0], 204, results)
        salary.refresh_from_db()
        self.assertIsNotNone(salary.archived_at)
        self.assertEqual(Salary.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action='salary.archive').count(), 1)
        if results[0][0] == 200:
            self.assertEqual(salary.status, 'paid')
            self.assertEqual(Transaction.objects.count(), 1)
            self.assertEqual((salary.transaction.amount, salary.transaction.currency), (Decimal('100.20'), 'EUR'))
        else:
            self.assertEqual((salary.status, salary.transaction_id, salary.payment_date), ('pending', None, None))
            self.assertEqual(Transaction.objects.count(), 0)

    def test_salary_create_racing_employee_archive_never_rewrites_history(self):
        other = self.second_client()
        results = self.pair(
            lambda: self.create_http('salary', self.salary_payload(), 'employee-archive'),
            lambda: self.request(other, 'delete', f'/api/employees/{self.employee.pk}/'))
        self.assertIn(results[0][0], (201, 400, 409), results)
        self.assertEqual(results[1][0], 204, results)
        self.employee.refresh_from_db()
        self.assertIsNotNone(self.employee.archived_at)
        self.assertEqual(Employee.objects.filter(pk=self.employee.pk).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action='employee.archive').count(), 1)
        self.assertEqual(Transaction.objects.count(), 0)
        if results[0][0] == 201:
            salary = self.assert_created_once('salary', results[0][1]['id'])
            self.assertEqual(salary.employee_id, self.employee.pk)
            self.assertEqual(Salary.objects.count(), 1)
        else:
            self.assertEqual(Salary.objects.count(), 0)
            self.assertEqual(self.intents().count(), 0)

    def test_transaction_edit_racing_archive_keeps_one_historical_id(self):
        other = self.second_client()
        tx = save_transaction(changes=self.tx_payload(), actor=self.actor)
        results = self.pair(
            lambda: self.request(self.client, 'patch', f'/api/transactions/{tx.pk}/', {'amount': '200.30'}),
            lambda: self.request(other, 'delete', f'/api/transactions/{tx.pk}/'))
        self.assertIn(results[0][0], (200, 400, 409), results)
        self.assertEqual(results[1][0], 204, results)
        tx.refresh_from_db()
        self.assertIsNotNone(tx.archived_at)
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(tx.amount, Decimal('200.30') if results[0][0] == 200 else Decimal('100.20'))
        self.assertEqual(AuditEvent.objects.filter(action='transaction.archive').count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action='transaction.update').count(), int(results[0][0] == 200))

    def test_same_assignment_concurrent_salary_edit_has_one_update_audit(self):
        other = self.second_client()
        salary = Salary.objects.create(employee=self.employee, amount='100.20', currency='EUR',
                                       period_year=2026, period_month=9)
        results = self.pair(
            lambda: self.request(self.client, 'patch', f'/api/salaries/{salary.pk}/', {'notes': 'Спільний результат'}),
            lambda: self.request(other, 'patch', f'/api/salaries/{salary.pk}/', {'notes': 'Спільний результат'}))
        self.assertEqual([r[0] for r in results], [200, 200], results)
        salary.refresh_from_db()
        self.assertEqual((salary.notes, salary.amount, salary.currency), ('Спільний результат', Decimal('100.20'), 'EUR'))
        self.assertEqual(Salary.objects.count(), 1)
        self.assertEqual(Transaction.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.filter(action='salary.update').count(), 1)

    def test_duplicate_money_update_has_one_audit_per_record_all_currencies(self):
        other = self.second_client()
        for month, currency in enumerate(CURRENCIES, 1):
            for kind, command, payload, model, path in (
                ('transaction', save_transaction, self.tx_payload(currency), Transaction, 'transactions'),
                ('salary', save_salary, self.salary_payload(currency, period_month=month), Salary, 'salaries'),
            ):
                with self.subTest(kind=kind, currency=currency):
                    row = command(changes=payload, actor=self.actor)
                    url = f'/api/{path}/{row.pk}/'
                    before_count = model.objects.count()
                    data = {'amount': '200.30'}
                    results = self.pair(
                        lambda: self.request(self.client, 'patch', url, data),
                        lambda: self.request(other, 'patch', url, data))
                    self.assertTrue(all(r[0] in (200, 409) for r in results), results)
                    self.assertTrue(any(r[0] == 200 for r in results), results)
                    retry = self.request(self.client, 'patch', url, data)
                    self.assertEqual(retry[0], 200, retry)
                    self.assertEqual(retry[1]['id'], row.pk)
                    row.refresh_from_db()
                    self.assertEqual((row.amount, row.currency), (Decimal('200.30'), currency))
                    self.assertEqual(model.objects.count(), before_count)
                    self.assertEqual(AuditEvent.objects.filter(
                        action=kind + '.update', payload__id=row.pk).count(), 1)

    def test_archive_and_restore_each_duplicate_command_has_one_audit_and_same_ids(self):
        salary = Salary.objects.create(employee=self.employee, amount='100.20', currency='EUR',
                                       period_year=2026, period_month=9)
        salary.mark_paid('2026-09-11')
        ids = (self.employee.pk, salary.pk, salary.transaction_id)
        for model, pk in ((Employee, ids[0]), (Salary, ids[1]), (Transaction, ids[2])):
            with self.subTest(model=model.__name__):
                def archive():
                    row = model.objects.get(pk=pk)
                    row.delete(actor=self.actor)
                    return row.archived_at
                results = self.pair(archive, archive)
                self.assertIsNotNone(results[0])
                self.assertEqual(results[0], results[1])
                self.assertEqual(AuditEvent.objects.filter(action=model._meta.model_name + '.archive').count(), 1)
                def restore():
                    row = model.objects.get(pk=pk)
                    return restore_record(row, actor=self.actor).pk
                self.assertEqual(self.pair(restore, restore), [pk, pk])
                self.assertIsNone(model.objects.get(pk=pk).archived_at)
                self.assertEqual(AuditEvent.objects.filter(action=model._meta.model_name + '.restore').count(), 1)
        salary.refresh_from_db()
        self.assertEqual((self.employee.pk, salary.pk, salary.transaction_id), ids)
        self.assertEqual((Employee.objects.count(), Salary.objects.count(), Transaction.objects.count()), (1, 1, 1))
        self.assertEqual((salary.amount, salary.transaction.amount, salary.currency, salary.transaction.currency),
                         (Decimal('100.20'), Decimal('100.20'), 'EUR', 'EUR'))
