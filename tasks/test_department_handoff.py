"""Ten synthetic HTTP regressions for the existing-Task handoff contract.

Preparation is syntax/AST only. Run exclusively with reviewed verification
settings, disposable check_* SQLite, and a dedicated BOS_TEST_MEDIA root.
"""
import hashlib
import os
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from boss_project.policy import Policy
from branches.models import Branch
from employees.models import Employee
from erp.models import Item, SalesLine, SalesOrder
from finance.models import Counterparty
from operations.models import ActionProposal, AuditEvent, Configuration, Document, ProcurementRequest
from scripts.check_support import login_test_client
from tasks.models import Task
from tasks.queries import source_refs


@override_settings(BOS_DATA_MODE='working', DEBUG=False,
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DepartmentHandoffTests(TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('DJANGO_SETTINGS_MODULE'), 'verification_settings')
        self.assertEqual(connection.vendor, 'sqlite')
        self.assertTrue(Path(str(connection.settings_dict['NAME'])).name.startswith('check_'))
        self.assertTrue(os.environ.get('BOS_TEST_MEDIA'))
        self.assertEqual(Path(settings.MEDIA_ROOT).resolve(), Path(os.environ['BOS_TEST_MEDIA']).resolve())
        Configuration.objects.create(key='dataset', value={'as_of': '2026-09-12'})
        Configuration.objects.get_or_create(key='erp_write', defaults={'value': {'revision': 0}})
        self.sequence = 0
        self.ceo, self.ceo_user = self.client_for('ceo')
        self.manager, self.manager_user = self.client_for('manager')
        self.receiver, self.recipient_user = self.client_for('manager')
        self.view_document = Permission.objects.get(
            content_type__app_label='operations', content_type__model='document', codename='view_document')
        self.dept = Branch.objects.create(code='DH-DEP', name='Відділ планування', type='department')
        self.other_dept = Branch.objects.create(code='DH-DEP2', name='Відділ виконання', type='department')
        self.sender = Employee.objects.create(full_name='Поточний менеджер', role='Менеджер',
                                               user=self.manager_user, branch=self.dept)
        self.recipient = Employee.objects.create(full_name='Отримувач доручення', role='Виконавець',
                                                  user=self.recipient_user, branch=self.other_dept)

    def client_for(self, role):
        client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        user = login_test_client(client, role, capabilities=('view_document', 'export_workspace'))
        return client, user

    def post(self, path, payload, client=None):
        client = client or self.ceo
        return client.post(path, payload, content_type='application/json',
                           HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)

    def source(self):
        self.sequence += 1
        code = 'DH-%02d' % self.sequence
        raw = ('Синтетичне джерело ' + code).encode('utf-8')
        document = Document.objects.create(code=code, revision='A', title=code, content=raw,
            checksum=hashlib.sha256(raw).hexdigest(), text=raw.decode('utf-8'),
            status='approved', access_level='operational')
        request = ProcurementRequest.objects.create(code=code+'-R', part=code, revision='A', quantity=1,
            unit='шт.', currency='UAH', required_by='2026-10-01', owner=self.sender, document=document)
        item = Item.objects.create(code=code, name=code, revision='A', unit='шт.', document=document)
        customer = Counterparty.objects.create(name=code, type='customer')
        order = SalesOrder.objects.create(code=code, customer=customer, owner=self.sender,
                                         due_date='2026-10-01', currency='UAH')
        SalesLine.objects.create(order=order, item=item, revision='A', quantity='1.000', price='1.00')
        return document, request, order

    def task(self):
        document, request, order = self.source()
        task = Task.objects.create(title='Зв’язане доручення', assignee='', assignee_employee=self.sender,
            deadline='2026-09-14', status='process', result='Фактичний незмінний результат',
            category='Планування', priority='high', branch=self.dept, sales_order=order)
        return task, document, request

    def payload(self, task, **changes):
        return {'action': 'handoff_task', 'task_id': task.pk, 'assignee_id': self.recipient.pk,
                'expected_result': 'Підготувати перевірений результат', 'deadline': '2026-09-15',
                'reason': 'Передати до відповідального відділу', **changes}

    def preview(self, payload, client=None):
        response = self.post('/api/operations/preview/', payload, client)
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()
        self.assertTrue(result['id'])
        return result

    def confirm(self, proposal, client=None):
        return self.post('/api/operations/confirm/', {'proposal_id': proposal['id'], 'confirmed': True}, client)

    def command(self, payload, client=None):
        proposal = self.preview(payload, client)
        response = self.confirm(proposal, client)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['state'], 'succeeded')
        return response.json()

    def status(self, proposal, client=None):
        return (client or self.ceo).get('/api/operations/task-proposals/' + proposal['id'] + '/')

    def update(self, task, **changes):
        return self.command({'action': 'update_task', 'task_id': task.pk,
                             'reason': 'Явна погоджена зміна доручення', **changes})

    def historical_task(self):
        old = self.source()
        request_only = self.source()
        current = self.source()
        receipt = self.command({'action': 'create_task', 'title': 'Доручення зі збереженою історією',
            'assignee_id': self.sender.pk, 'deadline': '2026-09-14', 'category': 'Планування',
            'priority': 'high', 'order_id': old[2].pk, 'request_code': request_only[1].code})
        task = Task.objects.get(pk=receipt['task_id'])
        self.assertEqual(task.branch_id, self.dept.pk)
        self.update(task, order_id=current[2].pk)
        self.update(task, status='done', result='Попередній фактичний результат збережено', priority='high')
        self.update(task, status='process')
        task.refresh_from_db()
        refs = source_refs(task)
        self.assertCountEqual(refs, [{'order_id': old[2].pk}, {'order_id': current[2].pk},
                                     {'request_code': request_only[1].code}])
        self.assertEqual(len({old[0].pk, request_only[0].pk, current[0].pk}), 3)
        return task, {'historical_order': old, 'historical_request': request_only, 'current': current}

    def business(self, include_proposals=False):
        # Eager copies: comparing lazy QuerySets after writes would hide mutations.
        result = {'tasks': list(Task.objects.order_by('pk').values()),
                  'audit': list(AuditEvent.objects.order_by('pk').values())}
        if include_proposals:
            result['proposals'] = list(ActionProposal.objects.order_by('pk').values())
        return deepcopy(result)

    def assert_preserved(self, before, after):
        for field in ('title', 'priority', 'category', 'result', 'branch_id', 'created_at', 'sales_order_id'):
            self.assertEqual(after[field], before[field], field)

    @contextmanager
    def changed(self, obj, **fields):
        rows = type(obj).objects.filter(pk=obj.pk)
        original = rows.values(*fields).get()
        rows.update(**fields)
        try:
            yield
        finally:
            rows.update(**original)

    @contextmanager
    def roles(self, user, names):
        original = list(user.groups.all())
        user.groups.set([Group.objects.get_or_create(name=name)[0] for name in names])
        try:
            yield
        finally:
            user.groups.set(original)

    @contextmanager
    def without_document_permission(self):
        self.recipient_user.user_permissions.remove(self.view_document)
        try:
            yield
        finally:
            self.recipient_user.user_permissions.add(self.view_document)

    def drift_cases(self, sources):
        return [
            ('role', lambda: self.roles(self.recipient_user, ['observer']), 403),
            ('link', lambda: self.changed(self.recipient, user_id=None), 403),
            ('archived', lambda: self.changed(self.recipient, archived_at=timezone.now()), 403),
            ('inactive', lambda: self.changed(self.recipient_user, is_active=False), 403),
            ('membership_missing', lambda: self.changed(self.recipient, branch_id=None), 403),
            ('membership_type', lambda: self.changed(self.other_dept, type='regional'), 403),
            ('capability', self.without_document_permission, 404),
            *[(name, lambda document=source[0]: self.changed(document, access_level='ceo'), 404)
              for name, source in sources.items()],
        ]

    def assert_refusal(self, response, status):
        self.assertEqual(response.status_code, status, response.content)
        value = response.json()
        self.assertIn('error', value)
        self.assertNotIn('receipt', value)
        self.assertNotIn('handoff', value)
        self.assertNotIn('impact', value)

    def test_01_strict_preview_schema_and_invalid_selection_do_not_mutate(self):
        task, _, _ = self.task()
        valid = self.payload(task)
        invalid = [dict(valid, **change) for change in (
            {'deadline': True}, {'deadline': '2026-9-15'}, {'deadline': '2026-09-11'},
            {'deadline': '2026-02-30'}, {'task_id': True}, {'task_id': '1'}, {'task_id': 0},
            {'assignee_id': False}, {'assignee_id': '2'}, {'assignee_id': -1},
            {'expected_result': '  '}, {'expected_result': 'x' * 2001}, {'reason': 'x'},
            {'sender_id': self.ceo_user.pk}, {'department_id': self.other_dept.pk})]
        invalid.append({key: value for key, value in valid.items() if key != 'reason'})
        for payload in invalid:
            with self.subTest(payload=payload):
                before = self.business(True)
                self.assert_refusal(self.post('/api/operations/preview/', payload), 422)
                self.assertEqual(self.business(True), before)
        for field in ('task_id', 'assignee_id'):
            before = self.business(True)
            self.assert_refusal(self.post('/api/operations/preview/', dict(valid, **{field: 999999})), 404)
            self.assertEqual(self.business(True), before)
        before = self.business(True)
        self.assert_refusal(self.post('/api/operations/preview/', self.payload(task, assignee_id=self.sender.pk)), 422)
        self.assertEqual(self.business(True), before)
        for changes in ({'status': 'done'}, {'archived_at': timezone.now()}, {'sales_order_id': None}):
            with self.subTest(changes=changes), self.changed(task, **changes):
                before = self.business(True)
                self.assert_refusal(self.post('/api/operations/preview/', valid), 422)
                self.assertEqual(self.business(True), before)
        before = self.business()
        proposal = self.preview(valid)
        self.assertEqual(proposal['payload'], valid)
        self.assertEqual(proposal['effect']['operation'], 'handoff')
        self.assertEqual(self.business(), before)
        self.assertIsNone(ActionProposal.objects.get(pk=proposal['id']).receipt)

    def test_02_ceo_and_current_manager_transfer_same_task_with_canonical_history(self):
        for client, user, employee in ((self.ceo, self.ceo_user, None), (self.manager, self.manager_user, self.sender)):
            with self.subTest(role='ceo' if employee is None else 'manager'):
                task, _ = self.historical_task()
                before = Task.objects.values().get(pk=task.pk)
                prior = list(AuditEvent.objects.filter(task=task).order_by('pk').values())
                refs = source_refs(task)
                count = Task.objects.count()
                proposal = self.preview(self.payload(task), client)
                response = self.confirm(proposal, client)
                self.assertEqual(response.status_code, 200, response.content)
                receipt = response.json()
                self.assertEqual(receipt['task_id'], task.pk)
                self.assertEqual(Task.objects.count(), count)
                task.refresh_from_db()
                self.assert_preserved(before, Task.objects.values().get(pk=task.pk))
                self.assertEqual(task.assignee_employee_id, self.recipient.pk)
                self.assertEqual(task.assignee, '')
                self.assertEqual(task.status, 'active')
                self.assertEqual(task.deadline.isoformat(), '2026-09-15')
                self.assertCountEqual(source_refs(task), refs)
                handoff = receipt['handoff']
                self.assertEqual(handoff['state'], 'sent')
                self.assertEqual(handoff['sender']['user_id'], user.pk)
                self.assertEqual(handoff['sender']['employee_id'], employee.pk if employee else None)
                self.assertEqual(handoff['sender']['role'], 'manager' if employee else 'ceo')
                self.assertEqual(handoff['sender']['department'],
                                 {'id': self.dept.pk, 'name': self.dept.name} if employee else {'id': None, 'name': None})
                self.assertEqual(handoff['previous_assignee']['employee_id'], self.sender.pk)
                self.assertEqual(handoff['recipient'], {'user_id': self.recipient_user.pk,
                    'employee_id': self.recipient.pk, 'role': 'manager',
                    'department': {'id': self.other_dept.pk, 'name': self.other_dept.name}})
                self.assertEqual(handoff['expected_result'], self.payload(task)['expected_result'])
                self.assertNotEqual(handoff['expected_result'], task.result)
                event = AuditEvent.objects.get(pk=receipt['audit_id'])
                self.assertEqual(event.action, 'handoff_task')
                self.assertEqual(event.payload['schema'], 'bos.task-change.v1')
                self.assertEqual(event.payload['before']['branch_id'], self.dept.pk)
                self.assertEqual(event.payload['before']['assignee_id'], self.sender.pk)
                self.assertEqual(event.payload['after']['assignee_id'], self.recipient.pk)
                self.assertEqual(event.payload['after']['deadline'], '2026-09-15')
                self.assertCountEqual(event.payload['source_refs'], refs)
                self.assertCountEqual(event.payload['before']['history_refs'], refs)
                self.assertCountEqual(event.payload['after']['history_refs'], refs)
                self.assertEqual(list(AuditEvent.objects.filter(pk__in=[row['id'] for row in prior]).order_by('pk').values()), prior)
                listing = self.receiver.get('/api/tasks/', {'department_id': self.other_dept.pk})
                self.assertEqual(listing.status_code, 200, listing.content)
                row = next(row for row in listing.json() if row['id'] == task.pk)
                self.assertEqual(row['handoff']['expected_result'], handoff['expected_result'])
                self.assertEqual(row['branch'], self.dept.pk)
                detail = self.receiver.get(f'/api/tasks/{task.pk}/')
                self.assertEqual(detail.status_code, 200, detail.content)
                self.assertEqual(detail.json()['handoff']['deadline'], '2026-09-15')
                history = self.receiver.get(f'/api/tasks/{task.pk}/history/')
                self.assertEqual(history.status_code, 200, history.content)
                item = next(row for row in history.json()['items'] if row['id'] == receipt['audit_id'])
                self.assertEqual(item['handoff'], handoff)
                self.assertEqual(item['actor']['id'], user.pk)
                self.assertEqual(item['transition'], 'handoff')

    def test_03_ceo_without_employee_has_explicit_null_sender_department(self):
        self.assertFalse(Employee.objects.filter(user=self.ceo_user).exists())
        task, _, _ = self.task()
        # Also exercise the null previous-assignee lock set without inventing identity.
        Task.objects.filter(pk=task.pk).update(assignee_employee=None)
        receipt = self.command(self.payload(task))
        self.assertEqual(receipt['handoff']['sender'], {'user_id': self.ceo_user.pk, 'role': 'ceo',
            'employee_id': None, 'department': {'id': None, 'name': None}})
        self.assertIsNone(receipt['handoff']['previous_assignee']['employee_id'])

    def test_04_observer_unrelated_wrong_role_link_and_archived_recipient_are_denied(self):
        task, _, _ = self.task()
        observer, _ = self.client_for('observer')
        unrelated, user = self.client_for('manager')
        Employee.objects.create(full_name='Інший менеджер', role='Менеджер', user=user, branch=self.dept)
        for client in (observer, unrelated):
            before = self.business(True)
            self.assert_refusal(self.post('/api/operations/preview/', self.payload(task), client), 403)
            self.assertEqual(self.business(True), before)
        variants = [
            ('wrong_role', lambda: self.roles(self.recipient_user, ['observer'])),
            ('no_role', lambda: self.roles(self.recipient_user, [])),
            ('multiple_roles', lambda: self.roles(self.recipient_user, ['ceo', 'manager'])),
            ('unlinked', lambda: self.changed(self.recipient, user_id=None)),
            ('archived', lambda: self.changed(self.recipient, archived_at=timezone.now())),
            ('inactive', lambda: self.changed(self.recipient_user, is_active=False)),
            ('no_department', lambda: self.changed(self.recipient, branch_id=None)),
            ('non_department', lambda: self.changed(self.other_dept, type='regional')),
        ]
        # A legacy department string and a CEO job title must not grant membership/role.
        Employee.objects.filter(pk=self.recipient.pk).update(role='Директор', department=self.other_dept.name)
        for name, mutate in variants:
            with self.subTest(name=name), mutate():
                before = self.business(True)
                self.assert_refusal(self.post('/api/operations/preview/', self.payload(task)), 403)
                self.assertEqual(self.business(True), before)

    def test_05_all_accumulated_historical_sources_must_be_visible(self):
        task, sources = self.historical_task()
        for name in ('historical_order', 'historical_request'):
            with self.subTest(source=name), self.changed(sources[name][0], access_level='ceo'):
                policy = Policy.for_user(self.recipient_user)
                self.assertTrue(policy.queryset(SalesOrder).filter(pk=task.sales_order_id).exists())
                self.assertFalse(policy.documents().filter(pk=sources[name][0].pk).exists())
                self.assertFalse(policy.tasks().filter(pk=task.pk).exists())
                before = self.business(True)
                self.assert_refusal(self.post('/api/operations/preview/', self.payload(task)), 404)
                self.assertEqual(self.business(True), before)
        with self.changed(sources['current'][0], access_level='ceo'):
            before = self.business(True)
            self.assert_refusal(self.post('/api/operations/preview/', self.payload(task)), 404)
            self.assertEqual(self.business(True), before)

    def test_06_role_link_membership_and_source_drift_after_preview_blocks_confirm_and_status(self):
        task, sources = self.historical_task()
        proposal = self.preview(self.payload(task))
        for phase in ('pending', 'stored_receipt'):
            if phase == 'stored_receipt':
                successful = self.confirm(proposal)
                self.assertEqual(successful.status_code, 200, successful.content)
                stored = successful.json()
            for name, mutate, status in self.drift_cases(sources):
                with self.subTest(phase=phase, drift=name), mutate():
                    before = self.business(True)
                    self.assert_refusal(self.confirm(proposal), status)
                    self.assert_refusal(self.status(proposal), status)
                    self.assertEqual(self.business(True), before)
                    current = ActionProposal.objects.get(pk=proposal['id']).receipt
                    if phase == 'pending':
                        self.assertIsNone(current)
                    else:
                        self.assertEqual(current['audit_id'], stored['audit_id'])
            restored = self.status(proposal)
            self.assertEqual(restored.status_code, 200, restored.content)
            self.assertEqual(restored.json()['state'], 'pending' if phase == 'pending' else 'succeeded')
        before = self.business(True)
        self.assertEqual(self.confirm(proposal).json(), stored)
        self.assertEqual(self.status(proposal).json()['receipt'], stored)
        self.assertEqual(self.business(True), before)
        # Still-eligible membership changes and ordinary task drift require a fresh proposal.
        another, _, _ = self.task()
        pending = self.preview(self.payload(another))
        for obj, changes in ((self.recipient, {'branch_id': self.dept.pk}), (another, {'title': 'Змінений заголовок'})):
            with self.changed(obj, **changes):
                before = self.business(True)
                response = self.confirm(pending)
                self.assert_refusal(response, 409)
                self.assertEqual(response.json()['code'], 'proposal_stale')
                self.assertEqual(self.business(True), before)

    def test_07_same_proposal_replay_is_stable_and_competing_old_proposal_is_stale(self):
        task, _, _ = self.task()
        first = self.preview(self.payload(task), self.manager)
        competing = self.preview(self.payload(task, deadline='2026-09-16'), self.manager)
        count = Task.objects.count()
        response = self.confirm(first, self.manager)
        self.assertEqual(response.status_code, 200, response.content)
        task.refresh_from_db()
        self.assertNotEqual(task.assignee_employee_id, self.sender.pk)
        before = self.business(True)
        self.assertEqual(self.confirm(first, self.manager).json(), response.json())
        self.assertEqual(self.status(first, self.manager).json()['receipt'], response.json())
        stale = self.confirm(competing, self.manager)
        self.assert_refusal(stale, 409)
        self.assertEqual(stale.json()['code'], 'proposal_stale')
        self.assertEqual(self.business(True), before)
        self.assertEqual(Task.objects.count(), count)
        self.assertEqual(AuditEvent.objects.filter(task=task, action='handoff_task').count(), 1)
        with self.roles(self.manager_user, ['observer']):
            self.assert_refusal(self.confirm(first, self.manager), 403)
            self.assert_refusal(self.status(first, self.manager), 403)
        self.assertEqual(self.business(True), before)

    def test_08_late_audit_and_receipt_failures_roll_back_task_audit_and_receipt(self):
        task, _, _ = self.task()
        for failure in ('audit_after_insert', 'receipt_after_save'):
            with self.subTest(failure=failure):
                proposal = self.preview(self.payload(task))
                before = self.business(True)
                seen = []
                real_create = AuditEvent.objects.create
                real_save = ActionProposal.save

                def after_audit_insert(*args, **kwargs):
                    event = real_create(*args, **kwargs)
                    current = Task.objects.get(pk=task.pk)
                    self.assertEqual(current.assignee_employee_id, self.recipient.pk)
                    self.assertEqual(current.deadline.isoformat(), '2026-09-15')
                    self.assertTrue(AuditEvent.objects.filter(pk=event.pk).exists())
                    self.assertEqual(ActionProposal.objects.get(pk=proposal['id']).receipt, {'state': 'running'})
                    seen.append(str(event.pk))
                    raise RuntimeError('Synthetic failure after real audit insertion')

                def after_receipt_save(instance, *args, **kwargs):
                    result = real_save(instance, *args, **kwargs)
                    if str(instance.pk) == proposal['id'] and kwargs.get('update_fields') == ['receipt']:
                        self.assertEqual(instance.receipt['state'], 'succeeded')
                        self.assertEqual(Task.objects.get(pk=task.pk).assignee_employee_id, self.recipient.pk)
                        self.assertTrue(AuditEvent.objects.filter(pk=instance.receipt['audit_id'], task=task).exists())
                        self.assertEqual(ActionProposal.objects.get(pk=proposal['id']).receipt, instance.receipt)
                        seen.append(instance.receipt['audit_id'])
                        raise RuntimeError('Synthetic failure after real final receipt save')
                    return result

                fault = (patch('tasks.handoffs.AuditEvent.objects.create', side_effect=after_audit_insert)
                         if failure == 'audit_after_insert'
                         else patch.object(ActionProposal, 'save', autospec=True, side_effect=after_receipt_save))
                with fault:
                    response = self.confirm(proposal)
                self.assertEqual(response.status_code, 500)
                self.assertEqual(len(seen), 1, 'The intended late boundary must actually be reached')
                self.assertEqual(self.business(True), before)
                self.assertIsNone(ActionProposal.objects.get(pk=proposal['id']).receipt)
                self.assertFalse(AuditEvent.objects.filter(pk=seen[0]).exists())

    def test_09_current_projection_department_filter_repetition_and_policy_denial(self):
        task, sources = self.historical_task()
        receipt = self.command(self.payload(task))
        rows = self.receiver.get('/api/tasks/', {'department_id': self.other_dept.pk})
        self.assertEqual(rows.status_code, 200, rows.content)
        self.assertEqual([row['id'] for row in rows.json()], [task.pk])
        row = rows.json()[0]
        self.assertEqual(row['handoff']['state'], 'sent')
        self.assertTrue(row['handoff']['current'])
        self.assertEqual(row['handoff']['expected_result'], receipt['handoff']['expected_result'])
        self.assertEqual(row['branch'], self.dept.pk)
        self.assertEqual(self.ceo.get('/api/tasks/', {'department_id': self.dept.pk}).json(), [])
        for value in ('0', '-1', '1.0', 'true', '١', '9223372036854775808'):
            self.assertEqual(self.ceo.get('/api/tasks/', {'department_id': value}).status_code, 400)
        self.assertEqual(self.ceo.get('/api/tasks/', {'department_id': ['1', '2']}).status_code, 400)
        with self.changed(self.other_dept, type='regional'):
            self.assertEqual(self.ceo.get('/api/tasks/', {'department_id': self.other_dept.pk}).json(), [])
        with self.changed(sources['historical_request'][0], access_level='ceo'):
            self.assertEqual(self.receiver.get('/api/tasks/', {'department_id': self.other_dept.pk}).json(), [])
            self.assertEqual(self.receiver.get(f'/api/tasks/{task.pk}/').status_code, 404)
            self.assertEqual(self.receiver.get(f'/api/tasks/{task.pk}/history/').status_code, 404)
            self.assertEqual(self.ceo.get(f'/api/tasks/{task.pk}/').status_code, 200)

    def test_10_generic_reassignment_preserves_history_and_never_reactivates_old_handoff(self):
        task, _ = self.historical_task()  # Real ordinary create/update/complete/reopen, not fake audit rows.
        before = Task.objects.values().get(pk=task.pk)
        refs = source_refs(task)
        handoff = self.command(self.payload(task))
        events = list(AuditEvent.objects.filter(task=task).order_by('pk').values())
        count = Task.objects.count()
        away = self.update(task, assignee_id=self.sender.pk)
        self.assertEqual(Task.objects.get(pk=task.pk).assignee_employee_id, self.sender.pk)
        returned = self.update(task, assignee_id=self.recipient.pk)
        task.refresh_from_db()
        self.assertEqual(task.assignee_employee_id, self.recipient.pk)
        self.assert_preserved(before, Task.objects.values().get(pk=task.pk))
        self.assertEqual(Task.objects.count(), count)
        self.assertCountEqual(source_refs(task), refs)
        self.assertEqual(list(AuditEvent.objects.filter(pk__in=[row['id'] for row in events]).order_by('pk').values()), events)
        for receipt, assignee in ((away, self.sender), (returned, self.recipient)):
            event = AuditEvent.objects.get(pk=receipt['audit_id'])
            self.assertEqual(event.action, 'update_task')
            self.assertEqual(event.payload['transition'], 'update')
            self.assertEqual(event.payload['after']['assignee_id'], assignee.pk)
            self.assertEqual(event.payload['after']['branch_id'], self.dept.pk)
            self.assertEqual(event.payload['after']['result'], before['result'])
            self.assertCountEqual(event.payload['source_refs'], refs)
        row = self.receiver.get(f'/api/tasks/{task.pk}/').json()
        self.assertFalse(row['handoff']['current'])
        self.assertEqual(row['handoff']['state'], 'superseded')
        self.assertEqual(row['handoff']['expected_result'], handoff['handoff']['expected_result'])
        history = self.receiver.get(f'/api/tasks/{task.pk}/history/').json()['items']
        self.assertTrue({away['audit_id'], returned['audit_id'], handoff['audit_id']} <= {row['id'] for row in history})
        original = next(row for row in history if row['id'] == handoff['audit_id'])
        self.assertEqual(original['handoff'], handoff['handoff'])
        self.assertEqual(original['after']['result'], before['result'])
