"""First owner contracts, using real identity/login and database transactions."""
from concurrent.futures import ThreadPoolExecutor
import getpass
import io
import json
import threading
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command, CommandError
from django.db import close_old_connections, connection
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings

from boss_project.identity import actor_for_user
from boss_project.policy import Policy
from branches.models import Branch
from employees.models import Employee
from operations.management.commands.bootstrap_bos_owner import MARKER
from operations.models import AuditEvent, Configuration


PASSWORD = 'Synthetic-Nova!Harbor-42'


@override_settings(BOS_DATA_MODE='working')
class FirstOwnerTests(TestCase):
    def bootstrap(self, *, password=PASSWORD, username='new-owner', **options):
        output = io.StringIO()
        with patch('sys.stdin', io.StringIO(password + '\n')):
            call_command('bootstrap_bos_owner', username=username, password_stdin=True,
                         stdout=output, stderr=output, **options)
        self.assertNotIn(password, output.getvalue())
        return get_user_model().objects.get(username=username)

    def assert_no_bootstrap(self):
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(Group.objects.exists())
        self.assertFalse(Configuration.objects.filter(key=MARKER).exists())
        self.assertFalse(AuditEvent.objects.filter(action='identity.bootstrap_owner').exists())

    def test_owner_can_use_real_login_without_technical_admin_or_extra_permissions(self):
        user = self.bootstrap()
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['ceo'])
        self.assertFalse(user.user_permissions.exists())
        self.assertFalse(Employee.objects.exists())
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)
        client = Client(enforce_csrf_checks=True, REMOTE_ADDR='127.0.0.1')
        self.assertEqual(client.get('/api/auth/csrf/').status_code, 200)
        response = client.post('/api/auth/login/', {'username': user.username, 'password': PASSWORD},
                               content_type='application/json',
                               HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {'user_id': user.pk, 'employee_id': None, 'role': 'ceo'})
        self.assertEqual(client.get('/api/auth/me/').json(), response.json())
        marker = Configuration.objects.get(key=MARKER)
        audit = AuditEvent.objects.get(action='identity.bootstrap_owner')
        self.assertEqual(marker.value, {'schema': 1, 'user_id': user.pk, 'role': 'ceo', 'permissions': []})
        self.assertEqual(audit.payload, {**marker.value, 'source': 'management_command'})
        self.assertNotIn(PASSWORD, repr(audit.payload))
        request = RequestFactory().get('/')
        request.user, request.session = user, {}
        capabilities = Policy(request).capabilities()
        self.assertTrue(capabilities['finance'])
        self.assertTrue(capabilities['view_documents'])  # Existing CEO policy.
        self.assertFalse(capabilities['download_documents'])
        self.assertFalse(capabilities['export_workspace'])

    def test_document_download_is_opt_in_and_does_not_grant_export(self):
        user = self.bootstrap(allow_document_download=True)
        self.assertEqual(user.get_all_permissions(), {
            'operations.view_document', 'operations.download_document'})

    def test_export_is_opt_in_and_does_not_grant_download(self):
        user = self.bootstrap(allow_workspace_export=True)
        self.assertEqual(user.get_all_permissions(), {'operations.export_workspace'})

    def test_both_permission_options_grant_only_the_document_model_permissions(self):
        user = self.bootstrap(allow_document_download=True, allow_workspace_export=True)
        self.assertEqual(user.get_all_permissions(), {
            'operations.view_document', 'operations.download_document', 'operations.export_workspace'})

    def test_weak_passwords_and_http_incompatible_length_leave_no_marker(self):
        for password in ('short', '1234567890123456', 'new-owner-1!', 'x' * 513):
            with self.subTest(password_kind='length-' + str(len(password))):
                with self.assertRaises(CommandError):
                    self.bootstrap(password=password)
                self.assert_no_bootstrap()

    def test_invalid_username_leaves_no_marker(self):
        with self.assertRaises(CommandError):
            self.bootstrap(username='invalid login')
        self.assert_no_bootstrap()

    def test_mismatch_does_not_create_user_or_marker(self):
        with patch('sys.stdin.isatty', return_value=True), patch(
                'operations.management.commands.bootstrap_bos_owner.getpass.getpass',
                side_effect=[PASSWORD, PASSWORD + 'mismatch']):
            with self.assertRaises(CommandError):
                call_command('bootstrap_bos_owner', username='new-owner')
        self.assert_no_bootstrap()

    def test_non_terminal_without_stdin_option_refuses_before_getpass(self):
        with patch('sys.stdin', io.StringIO(PASSWORD + '\n')), patch(
                'operations.management.commands.bootstrap_bos_owner.getpass.getpass') as prompt:
            with self.assertRaises(CommandError):
                call_command('bootstrap_bos_owner', username='new-owner')
        prompt.assert_not_called()
        self.assert_no_bootstrap()

    def test_getpass_warning_never_falls_back_to_echo_or_writes(self):
        for warn_on_call in (1, 2):
            with self.subTest(prompt=warn_on_call):
                calls = []

                def hidden_input(prompt):
                    calls.append(prompt)
                    if len(calls) == warn_on_call:
                        return getpass.fallback_getpass(prompt, stream=io.StringIO())
                    return PASSWORD

                with patch('sys.stdin.isatty', return_value=True), patch(
                        'operations.management.commands.bootstrap_bos_owner.getpass.getpass',
                        side_effect=hidden_input), patch('getpass._raw_input') as raw_input:
                    with self.assertRaises(CommandError):
                        call_command('bootstrap_bos_owner', username='new-owner')
                raw_input.assert_not_called()
                self.assertEqual(len(calls), warn_on_call)
                self.assert_no_bootstrap()

    def test_existing_user_is_not_elevated_or_changed(self):
        existing = get_user_model().objects.create_user('existing', password=PASSWORD)
        original_hash = existing.password
        with self.assertRaises(CommandError):
            self.bootstrap()
        existing.refresh_from_db()
        self.assertEqual(existing.password, original_hash)
        self.assertFalse(existing.groups.exists())
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertFalse(Configuration.objects.filter(key=MARKER).exists())
        self.assertFalse(AuditEvent.objects.exists())

    def test_existing_business_data_is_not_modified(self):
        branch = Branch.objects.create(code='SYNTHETIC-EXISTING', name='Існуючий тестовий офіс')
        before = list(Branch.objects.values())
        with self.assertRaises(CommandError):
            self.bootstrap()
        self.assertEqual(list(Branch.objects.values()), before)
        self.assertEqual(Branch.objects.get().pk, branch.pk)
        self.assert_no_bootstrap()

    def test_existing_privileged_group_cannot_be_inherited(self):
        group = Group.objects.create(name='ceo')
        group.permissions.add(Permission.objects.get(
            content_type__app_label='auth', content_type__model='user', codename='change_user'))
        with self.assertRaises(CommandError):
            self.bootstrap()
        self.assertEqual(group.permissions.count(), 1)
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(Configuration.objects.filter(key=MARKER).exists())

    def test_existing_configuration_and_marker_are_not_cleaned_up(self):
        marker = Configuration.objects.create(key=MARKER, value={'do_not_replace': True})
        with self.assertRaises(CommandError):
            self.bootstrap()
        marker.refresh_from_db()
        self.assertEqual(marker.value, {'do_not_replace': True})
        self.assertFalse(get_user_model().objects.exists())

    def test_repeat_preserves_owner_password_and_audit(self):
        user = self.bootstrap()
        before = list(get_user_model().objects.values())
        marker = Configuration.objects.get(key=MARKER).value
        audit = list(AuditEvent.objects.values())
        with self.assertRaises(CommandError):
            self.bootstrap(password='Other-Synthetic!Harbor-84', username='second-owner',
                           allow_document_download=True)
        self.assertEqual(list(get_user_model().objects.values()), before)
        self.assertEqual(Configuration.objects.get(key=MARKER).value, marker)
        self.assertEqual(list(AuditEvent.objects.values()), audit)
        self.assertEqual(actor_for_user(user).role, 'ceo')

    def test_missing_requested_permission_rolls_back_every_write(self):
        Permission.objects.filter(content_type__app_label='operations',
                                  content_type__model='document', codename='download_document').delete()
        with self.assertRaises(CommandError):
            self.bootstrap(allow_document_download=True)
        self.assert_no_bootstrap()

    @override_settings(BOS_DATA_MODE='demo')
    def test_demo_mode_refuses_without_prompting_or_writing(self):
        with patch('operations.management.commands.bootstrap_bos_owner.getpass.getpass') as prompt:
            with self.assertRaises(CommandError):
                call_command('bootstrap_bos_owner', username='new-owner')
        prompt.assert_not_called()
        self.assert_no_bootstrap()


@override_settings(BOS_DATA_MODE='working')
class FirstOwnerConcurrencyTests(TransactionTestCase):
    def test_two_actual_connections_create_exactly_one_owner(self):
        barrier = threading.Barrier(2)

        def run(index):
            close_old_connections()
            try:
                connection.ensure_connection()
                connection_id = id(connection.connection)
                proof = {'vendor': connection.vendor}
                if connection.vendor == 'postgresql':
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT current_database(), current_setting(%s)', ['server_version_num'])
                        database, version = cursor.fetchone()
                    self.assertEqual(database, connection.settings_dict['NAME'])
                    self.assertEqual(int(version) // 10000, 16)
                    proof.update(database=database, version_num=int(version))
                barrier.wait(timeout=10)
                try:
                    call_command('bootstrap_bos_owner', username=f'owner-{index}',
                                 stdout=io.StringIO(), stderr=io.StringIO())
                    return 'created', connection_id, proof
                except CommandError:
                    return 'refused', connection_id, proof
            finally:
                connection.close()

        with patch('sys.stdin.isatty', return_value=True), patch(
                'operations.management.commands.bootstrap_bos_owner.getpass.getpass', return_value=PASSWORD):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(run, index) for index in range(2)]
                results = [future.result(timeout=30) for future in futures]
        self.assertEqual(sorted(status for status, _, _ in results), ['created', 'refused'])
        self.assertEqual(len({connection_id for _, connection_id, _ in results}), 2)
        user = get_user_model().objects.get()
        self.assertEqual(actor_for_user(user).role, 'ceo')
        self.assertEqual(Group.objects.count(), 1)
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(Configuration.objects.get(key=MARKER).value['user_id'], user.pk)
        self.assertEqual(AuditEvent.objects.filter(action='identity.bootstrap_owner').count(), 1)
        print('BOOTSTRAP_OWNER_CONCURRENCY ' + json.dumps({
            'distinct_connections': 2, 'results': [
                {'status': status, **proof} for status, _, proof in results]}))
