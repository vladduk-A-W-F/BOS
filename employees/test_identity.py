"""A03 synthetic regression draft; intended for employees/test_identity.py.

Run only with --settings=verification_settings on a disposable test database.
Real Django HTTP, CSRF, credentials, sessions, groups and ORM; no auth mocks.
Accepted me response: {user_id, employee_id: null|int, role}.
Existing 151+5 test bodies are not changed by this file.
"""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.management import call_command, CommandError
from django.db import IntegrityError, models, transaction
from django.test import Client, TestCase, override_settings

from employees.models import Employee
from finance.models import Salary, Transaction
from operations.models import ActionProposal, AuditEvent
from tasks.models import Task


User = get_user_model()
PASSWORD = 'A03-synthetic-only-passphrase'
BUSINESS_ROLES = {'ceo', 'manager', 'observer'}


@override_settings(BOS_DATA_MODE='working')
class IdentityBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.groups = {role: Group.objects.get_or_create(name=role)[0]
                      for role in sorted(BUSINESS_ROLES)}
        cls.ceo = User.objects.create_user(username='a03-ceo', password=PASSWORD)
        cls.manager = User.objects.create_user(username='a03-manager', password=PASSWORD)
        cls.observer = User.objects.create_user(username='a03-observer', password=PASSWORD)
        cls.second_ceo = User.objects.create_user(username='a03-second-ceo', password=PASSWORD)
        for user, role in ((cls.ceo, 'ceo'), (cls.manager, 'manager'),
                           (cls.observer, 'observer'), (cls.second_ceo, 'ceo')):
            user.groups.add(cls.groups[role])

    def setUp(self):
        # Only a synthetic test process; isolates the real login rate limiter.
        cache.clear()

    def new_client(self, remote='127.0.0.1'):
        value = Client(enforce_csrf_checks=True, REMOTE_ADDR=remote)
        response = value.get('/api/auth/csrf/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn(settings.CSRF_COOKIE_NAME, value.cookies)
        return value

    def post(self, client, path, payload=None):
        return client.post(path, data=payload or {}, content_type='application/json',
            HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)

    def login(self, user, client=None, **extra):
        client = client or self.new_client()
        response = self.post(client, '/api/auth/login/',
                             {'username': user.username, 'password': PASSWORD, **extra})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(client.session.get('_auth_user_id'), str(user.pk))
        self.assertTrue(client.session.get('_auth_user_backend'))
        return client

    def me(self, client, user, role, employee_id=None):
        response = client.get('/api/auth/me/')
        self.assertEqual(response.status_code, 200, response.content)
        value = response.json()
        self.assertEqual(value['user_id'], user.pk)
        self.assertEqual(value['role'], role)
        self.assertEqual(value['employee_id'], employee_id)
        return value

    def link(self, user, employee):
        call_command('link_bos_user', user_id=user.pk, employee_id=employee.pk,
                     stdout=StringIO(), stderr=StringIO())
        employee.refresh_from_db()
        self.assertEqual(employee.user_id, user.pk)

    def employee(self, name='Синтетичний працівник A03'):
        return Employee.objects.create(full_name=name, role='Інженер', department='Синтетика')

    def proposal(self, client, employee=None):
        employee = employee or self.employee()
        before = Task.objects.count()
        response = self.post(client, '/api/operations/preview/', {
            'action': 'create_task', 'title': 'Синтетичне доручення A03',
            'assignee_id': employee.pk, 'deadline': '2026-12-01',
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Task.objects.count(), before)
        return ActionProposal.objects.get(pk=response.json()['id'])

    def confirm(self, client, proposal):
        return self.post(client, '/api/operations/confirm/',
                         {'proposal_id': str(proposal.pk), 'confirmed': True})

    def assert_confirm_denied_without_effect(self, client, proposal, status=403):
        before = (Task.objects.count(), AuditEvent.objects.count())
        proposal.refresh_from_db()
        receipt = proposal.receipt
        response = self.confirm(client, proposal)
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual((Task.objects.count(), AuditEvent.objects.count()), before)
        proposal.refresh_from_db()
        self.assertEqual(proposal.receipt, receipt)
        self.assertNotIn('task_id', response.json())
        self.assertNotIn('audit_id', response.json())


class AuthenticationTests(IdentityBase):
    def test_csrf_bootstrap_never_creates_a_ceo_session(self):
        client = self.new_client()
        response = client.get('/api/auth/csrf/')
        self.assertNotEqual(response.json().get('role'), 'ceo')
        self.assertNotIn('_auth_user_id', client.session)
        self.assertEqual(client.get('/api/auth/me/').status_code, 401)

    def test_login_requires_csrf_and_rotates_session_and_token(self):
        client = self.new_client()
        data = {'username': self.ceo.username, 'password': PASSWORD}
        denied = client.post('/api/auth/login/', data, content_type='application/json')
        self.assertEqual(denied.status_code, 403)
        self.assertNotIn('_auth_user_id', client.session)
        denied = client.post('/api/auth/login/', data, content_type='application/json',
                             HTTP_X_CSRFTOKEN='x' * 32)
        self.assertEqual(denied.status_code, 403)
        session = client.session
        session['a03_nonce'] = 'synthetic'; session.save()
        old_key = session.session_key
        old_csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
        self.login(self.ceo, client)
        self.assertNotEqual(client.session.session_key, old_key)
        self.assertNotEqual(client.cookies[settings.CSRF_COOKIE_NAME].value, old_csrf)
        self.me(client, self.ceo, 'ceo')
        self.ceo.refresh_from_db()
        self.assertFalse(self.ceo.is_staff)
        self.assertFalse(self.ceo.is_superuser)

    def test_bad_credentials_and_inactive_user_cannot_login(self):
        client = self.new_client()
        bad = self.post(client, '/api/auth/login/',
                        {'username': self.ceo.username, 'password': 'wrong-synthetic-password'})
        self.assertEqual(bad.status_code, 401)
        self.assertNotIn('_auth_user_id', client.session)
        self.ceo.is_active = False; self.ceo.save(update_fields=['is_active'])
        denied = self.post(client, '/api/auth/login/',
                           {'username': self.ceo.username, 'password': PASSWORD})
        self.assertEqual(denied.status_code, 401)
        self.assertNotIn('_auth_user_id', client.session)

    def test_login_requires_exactly_one_business_group(self):
        no_role = User.objects.create_user(username='a03-no-role', password=PASSWORD)
        multiple = User.objects.create_user(username='a03-multiple', password=PASSWORD)
        multiple.groups.add(self.groups['ceo'], self.groups['manager'])
        for user in (no_role, multiple):
            with self.subTest(username=user.username):
                client = self.new_client()
                response = self.post(client, '/api/auth/login/',
                                     {'username': user.username, 'password': PASSWORD})
                self.assertEqual(response.status_code, 403, response.content)
                self.assertNotIn('_auth_user_id', client.session)
        # An unrelated Django group is not a second business role.
        self.manager.groups.add(Group.objects.create(name='a03-document-readers'))
        self.me(self.login(self.manager), self.manager, 'manager')

    def test_login_payload_and_session_role_do_not_grant_ceo(self):
        client = self.login(self.manager, role='ceo')
        self.me(client, self.manager, 'manager')
        session = client.session
        session['bos_role'] = 'ceo'; session.save()
        self.me(client, self.manager, 'manager')
        before = set(self.manager.groups.values_list('name', flat=True))
        response = self.post(client, '/api/operations/settings/', {'name': 'Недозволена зміна A03'})
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(set(self.manager.groups.values_list('name', flat=True)), before)

    def test_anonymous_fake_session_role_has_no_business_access(self):
        client = self.new_client()
        session = client.session
        session['bos_role'] = 'ceo'; session.save()
        self.assertEqual(client.get('/api/auth/me/').status_code, 401)
        before = (Task.objects.count(), ActionProposal.objects.count())
        response = self.post(client, '/api/operations/preview/', {
            'action': 'create_task', 'title': 'Не має бути створено',
            'assignee_id': self.employee().pk, 'deadline': '2026-12-01',
        })
        self.assertEqual(response.status_code, 401, response.content)
        self.assertEqual((Task.objects.count(), ActionProposal.objects.count()), before)

    def test_logout_requires_csrf_and_invalidates_old_cookie(self):
        client = self.login(self.ceo)
        old_session = client.cookies[settings.SESSION_COOKIE_NAME].value
        denied = client.post('/api/auth/logout/', {}, content_type='application/json')
        self.assertEqual(denied.status_code, 403)
        self.me(client, self.ceo, 'ceo')
        self.assertEqual(self.post(client, '/api/auth/logout/').status_code, 200)
        self.assertEqual(client.get('/api/auth/me/').status_code, 401)
        reused = self.new_client()
        reused.cookies[settings.SESSION_COOKIE_NAME] = old_session
        self.assertEqual(reused.get('/api/auth/me/').status_code, 401)

    def test_deactivated_user_and_revoked_group_lose_existing_access(self):
        client = self.login(self.ceo)
        self.ceo.is_active = False; self.ceo.save(update_fields=['is_active'])
        self.assertEqual(client.get('/api/auth/me/').status_code, 401)
        client = self.login(self.manager)
        self.manager.groups.clear()
        self.assertEqual(client.get('/api/auth/me/').status_code, 403)

    def test_working_role_setter_is_404_for_every_method(self):
        client = self.login(self.ceo)
        for method in ('get', 'post', 'put', 'patch', 'delete', 'head', 'options'):
            with self.subTest(method=method):
                response = getattr(client, method)('/api/operations/role/',
                    data={'role': 'ceo'}, content_type='application/json',
                    HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
                self.assertEqual(response.status_code, 404, response.content)
        self.me(client, self.ceo, 'ceo')

    def test_five_failed_logins_limit_the_sixth_for_60_seconds(self):
        client = self.new_client()
        for _ in range(5):
            response = self.post(client, '/api/auth/login/',
                {'username': self.ceo.username, 'password': 'wrong-synthetic-password'})
            self.assertEqual(response.status_code, 401, response.content)
        response = self.post(client, '/api/auth/login/',
            {'username': self.ceo.username, 'password': PASSWORD})
        self.assertEqual(response.status_code, 429, response.content)
        self.assertIn('Retry-After', response)
        self.assertGreater(int(response['Retry-After']), 0)
        self.assertLessEqual(int(response['Retry-After']), 60)
        self.assertNotIn('_auth_user_id', client.session)
        # Real independent keys: another username or another loopback IP works.
        self.me(self.login(self.manager), self.manager, 'manager')
        self.me(self.login(self.ceo, self.new_client(remote='::1')), self.ceo, 'ceo')


class IdentityLinkTests(IdentityBase):
    def test_employee_user_schema_is_nullable_one_to_one_set_null(self):
        field = Employee._meta.get_field('user')
        self.assertTrue(field.one_to_one)
        self.assertTrue(field.null)
        self.assertIs(field.remote_field.on_delete, models.SET_NULL)
        self.assertIs(field.remote_field.model, User)

    def test_explicit_link_preserves_employee_and_payroll_ids(self):
        employee = self.employee()
        salary = Salary.objects.create(employee=employee, amount=Decimal('123.45'),
            currency='EUR', period_year=2026, period_month=9)
        salary.mark_paid(date(2026, 9, 11))
        snapshot = (employee.pk, employee.created_at, salary.pk, salary.employee_id,
                    salary.transaction_id, salary.amount, salary.currency)
        counts = (Employee.objects.count(), Salary.objects.count(), Transaction.objects.count())
        self.link(self.manager, employee)
        self.link(self.manager, employee)  # Explicit idempotent repeat, not an upsert of a new employee.
        salary.refresh_from_db()
        self.assertEqual((employee.pk, employee.created_at, salary.pk, salary.employee_id,
                          salary.transaction_id, salary.amount, salary.currency), snapshot)
        self.assertEqual((Employee.objects.count(), Salary.objects.count(), Transaction.objects.count()), counts)
        self.me(self.login(self.manager), self.manager, 'manager', employee.pk)

    def test_link_does_not_infer_authority_from_employee_job_title(self):
        employee = self.employee()
        employee.role = 'ceo'; employee.save(update_fields=['role'])
        self.link(self.observer, employee)
        self.me(self.login(self.observer), self.observer, 'observer', employee.pk)
        self.assertEqual(set(self.observer.groups.values_list('name', flat=True)), {'observer'})

    def test_conflicting_mapping_is_rejected_without_rebinding(self):
        first, second = self.employee('Синтетична особа А'), self.employee('Синтетична особа Б')
        self.link(self.manager, first)
        before = list(Employee.objects.order_by('pk').values('id', 'user_id', 'full_name'))
        for user, employee in ((self.manager, second), (self.observer, first)):
            with self.subTest(user=user.pk, employee=employee.pk):
                with self.assertRaises(CommandError):
                    call_command('link_bos_user', user_id=user.pk, employee_id=employee.pk,
                                 stdout=StringIO(), stderr=StringIO())
                self.assertEqual(list(Employee.objects.order_by('pk').values('id', 'user_id', 'full_name')), before)

    def test_link_to_missing_id_does_not_create_or_guess_an_employee(self):
        employee = self.employee()
        before = (Employee.objects.count(), User.objects.count())
        for user_id, employee_id in ((self.manager.pk, employee.pk + 99999),
                                     (self.manager.pk + 99999, employee.pk)):
            with self.subTest(user_id=user_id, employee_id=employee_id):
                with self.assertRaises(CommandError):
                    call_command('link_bos_user', user_id=user_id, employee_id=employee_id,
                                 stdout=StringIO(), stderr=StringIO())
                self.assertEqual((Employee.objects.count(), User.objects.count()), before)
        employee.refresh_from_db()
        self.assertIsNone(employee.user_id)

    def test_database_rejects_two_employees_for_the_same_user(self):
        first = self.employee()
        self.link(self.manager, first)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Employee.objects.create(full_name='Другий зв’язок заборонено', role='Тест', user=self.manager)
        self.assertEqual(Employee.objects.filter(user=self.manager).count(), 1)
        first.refresh_from_db()
        self.assertEqual(first.user_id, self.manager.pk)

    def test_set_null_keeps_employee_and_salary_when_synthetic_user_is_deleted(self):
        employee = self.employee()
        self.link(self.manager, employee)
        salary = Salary.objects.create(employee=employee, amount='10.00', currency='UAH',
                                       period_year=2026, period_month=9)
        pk, created_at = employee.pk, employee.created_at
        self.manager.delete()  # Synthetic FK behavior test; access withdrawal normally deactivates.
        employee.refresh_from_db(); salary.refresh_from_db()
        self.assertEqual((employee.pk, employee.created_at, salary.employee_id), (pk, created_at, pk))
        self.assertIsNone(employee.user_id)

    def test_archiving_linked_employee_revokes_access_without_losing_history(self):
        employee = self.employee()
        self.link(self.manager, employee)
        salary = Salary.objects.create(employee=employee, amount='25.75', currency='USD',
                                       period_year=2026, period_month=9)
        salary.mark_paid('2026-09-11')
        snapshot = (employee.pk, self.manager.pk, salary.pk, salary.employee_id,
                    salary.transaction_id, salary.amount, salary.currency)
        manager_client = self.login(self.manager)
        self.me(manager_client, self.manager, 'manager', employee.pk)
        ceo_client = self.login(self.ceo)
        response = ceo_client.delete(f'/api/employees/{employee.pk}/',
            HTTP_X_CSRFTOKEN=ceo_client.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertEqual(response.status_code, 204, response.content)
        employee.refresh_from_db(); salary.refresh_from_db(); self.manager.refresh_from_db()
        self.assertIsNotNone(employee.archived_at)
        self.assertEqual((employee.pk, self.manager.pk, salary.pk, salary.employee_id,
                          salary.transaction_id, salary.amount, salary.currency), snapshot)
        self.assertEqual(employee.user_id, self.manager.pk)
        # Deactivation gives anonymous401; a retained active User with an
        # archived Employee must instead get authenticated-forbidden403.
        expected = 401 if not self.manager.is_active else 403
        self.assertEqual(manager_client.get('/api/auth/me/').status_code, expected)
        denied = self.post(manager_client, '/api/operations/preview/', {
            'action': 'create_task', 'title': 'Недозволено після архіву',
            'assignee_id': employee.pk, 'deadline': '2026-12-01',
        })
        self.assertEqual(denied.status_code, expected, denied.content)


class ProposalIdentityTests(IdentityBase):
    def test_proposal_has_nullable_real_user_fk_for_legacy_migration(self):
        field = ActionProposal._meta.get_field('user')
        self.assertTrue(field.null)
        self.assertIs(field.remote_field.model, User)

    def test_real_author_session_and_successful_replay(self):
        client = self.login(self.ceo)
        proposal = self.proposal(client)
        self.assertEqual(proposal.user_id, self.ceo.pk)
        self.assertEqual(proposal.session_key, client.session.session_key)
        self.assertEqual(proposal.role, 'ceo')
        response = self.confirm(client, proposal)
        self.assertEqual(response.status_code, 200, response.content)
        before = (Task.objects.count(), AuditEvent.objects.count())
        replay = self.confirm(client, proposal)
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.json(), response.json())
        self.assertEqual((Task.objects.count(), AuditEvent.objects.count()), before)

    def test_same_user_in_another_real_session_cannot_confirm(self):
        first = self.login(self.ceo)
        second = self.login(self.ceo)
        self.assertNotEqual(first.session.session_key, second.session.session_key)
        self.assert_confirm_denied_without_effect(second, self.proposal(first))

    def test_different_author_is_rejected_even_if_session_field_matches(self):
        client = self.login(self.ceo)
        proposal = self.proposal(client)
        # Persisted synthetic mismatch isolates the author check from the
        # independent session check. This is a real ORM fixture, not an auth mock.
        ActionProposal.objects.filter(pk=proposal.pk).update(user=self.second_ceo)
        self.assert_confirm_denied_without_effect(client, proposal)

    def test_legacy_proposal_without_author_requires_a_new_preview(self):
        client = self.login(self.ceo)
        proposal = self.proposal(client)
        ActionProposal.objects.filter(pk=proposal.pk).update(user=None)
        self.assert_confirm_denied_without_effect(client, proposal)
        replacement = self.proposal(client)
        self.assertNotEqual(proposal.pk, replacement.pk)
        self.assertEqual(self.confirm(client, replacement).status_code, 200)
        proposal.refresh_from_db()
        self.assertIsNone(proposal.user_id)  # Never guess an owner for a historical row.

    def test_role_change_between_preview_and_confirm_is_rechecked(self):
        client = self.login(self.ceo)
        proposal = self.proposal(client)
        self.ceo.groups.set([self.groups['manager']])
        self.me(client, self.ceo, 'manager')
        self.assert_confirm_denied_without_effect(client, proposal)

    def test_role_revocation_is_checked_before_returning_old_receipt(self):
        client = self.login(self.ceo)
        proposal = self.proposal(client)
        self.assertEqual(self.confirm(client, proposal).status_code, 200)
        self.ceo.groups.set([self.groups['observer']])
        self.assert_confirm_denied_without_effect(client, proposal)

    def test_author_and_legacy_checks_happen_before_receipt(self):
        for new_author in (self.second_ceo, None):
            with self.subTest(author=getattr(new_author, 'pk', None)):
                client = self.login(self.ceo)
                proposal = self.proposal(client)
                self.assertEqual(self.confirm(client, proposal).status_code, 200)
                ActionProposal.objects.filter(pk=proposal.pk).update(user=new_author)
                self.assert_confirm_denied_without_effect(client, proposal)

    def test_logout_and_relogin_does_not_reuse_old_proposal(self):
        client = self.login(self.ceo)
        proposal = self.proposal(client)
        self.assertEqual(self.post(client, '/api/auth/logout/').status_code, 200)
        self.login(self.ceo, client)
        self.assertNotEqual(proposal.session_key, client.session.session_key)
        self.assert_confirm_denied_without_effect(client, proposal)

    def test_deactivation_prevents_confirmation(self):
        client = self.login(self.ceo)
        proposal = self.proposal(client)
        self.ceo.is_active = False; self.ceo.save(update_fields=['is_active'])
        self.assert_confirm_denied_without_effect(client, proposal, status=401)


@override_settings(BOS_DATA_MODE='demo')
class DemoIdentityTests(IdentityBase):
    def test_demo_switch_uses_real_users_without_creating_a_seventh_employee(self):
        call_command('seed_bos_demo', stdout=StringIO(), stderr=StringIO())
        self.assertEqual(Employee.objects.count(), 6)
        employee_ids = list(Employee.objects.order_by('pk').values_list('pk', flat=True))
        client = self.new_client()
        seen = set()
        for role in ('ceo', 'manager', 'observer'):
            response = self.post(client, '/api/operations/role/', {'role': role})
            self.assertEqual(response.status_code, 200, response.content)
            me = client.get('/api/auth/me/')
            self.assertEqual(me.status_code, 200, me.content)
            value = me.json()
            self.assertEqual(value['role'], role)
            self.assertEqual(client.session.get('_auth_user_id'), str(value['user_id']))
            user = User.objects.get(pk=value['user_id'])
            self.assertEqual(set(user.groups.filter(name__in=BUSINESS_ROLES)
                                 .values_list('name', flat=True)), {role})
            self.assertTrue(user.is_active)
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)
            seen.add(user.pk)
            self.assertEqual(list(Employee.objects.order_by('pk').values_list('pk', flat=True)), employee_ids)
        self.assertEqual(len(seen), 3, 'Changing demo role must not rewrite one shared User group.')
