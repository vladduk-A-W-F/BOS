"""Independent server-side checks for the BoS 3.0 lesson boundary.

These tests intentionally use the isolated synthetic fixture and ordinary HTTP
endpoints. They do not run browser/E2E, PostgreSQL, old training harnesses or
the historical full suites.
"""
import os
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.db.models.query import QuerySet
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from employees.models import Employee
from boss_project.policy import Policy
from crm.models import CRMDeal
from crm import commands as crm_commands, projections as crm_projections
from erp.models import Lot, Movement, Production, Reservation, SalesLine, SalesOrder
from operations.models import ActionProposal, Configuration, Document
from operations.service import Conflict
from tasks.models import Task
from training.models import TrainingSession
from training import service as training_service
from training.service import normalized_current_step, session_state


class CurrentStepNormalizationTests(SimpleTestCase):
    def test_blank_stale_locked_and_selected_completed(self):
        steps = [{'id': 'order', 'status': 'completed'},
                 {'id': 'supply', 'status': 'needs_recheck'},
                 {'id': 'crm', 'status': 'locked'}]
        self.assertEqual(normalized_current_step(steps, ''), 'supply')
        self.assertEqual(normalized_current_step(steps, 'unknown'), 'supply')
        self.assertEqual(normalized_current_step(steps, 'crm'), 'supply')
        self.assertEqual(normalized_current_step(steps, 'order'), 'order')
        self.assertEqual(normalized_current_step(steps, 'supply'), 'supply')

    def test_all_completed_and_empty_are_deterministic(self):
        completed = [{'id': 'order', 'status': 'completed'},
                     {'id': 'supply', 'status': 'completed'}]
        self.assertEqual(normalized_current_step(completed, ''), 'order')
        self.assertEqual(normalized_current_step(completed, 'supply'), 'supply')
        self.assertIsNone(normalized_current_step([], 'missing'))

    def test_empty_projected_session_has_no_step_index(self):
        session = SimpleNamespace(progress={}, status='in_progress', current_step='',
                                  public_id='synthetic-session', tour_state={})
        marker = {'id': 'synthetic-fixture', 'hash': 'synthetic-hash', 'as_of': '2026-10-01'}
        with patch('training.service.identity', return_value={}), patch(
                'training.service.observations', return_value=({}, [], [])):
            state = session_state(SimpleNamespace(role='ceo'), marker, 'BOS3-CASE-01', session)
        self.assertEqual(state['steps'], [])
        self.assertIsNone(state['current_step'])


@override_settings(BOS_DATA_MODE='demo', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TrainingSessionContractTests(TestCase):
    """One owner-bound database fixture per Django TestCase transaction."""

    owner_username = 'bos3-training-owner'
    installation_id = 'training-sessions-contract'

    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username=self.owner_username, password='synthetic-test-password')
        Group.objects.get_or_create(name='ceo')[0].user_set.add(self.owner)
        self.environment = {
            'BOS3_TRAINING_ENABLED': '1',
            'BOS3_TRAINING_PROFILE': 'isolated-synthetic',
            'BOS3_TRAINING_DB_MARKER': 'bos3-fasteners-uk-v1',
            'BOS3_TRAINING_OWNER_USERNAME': self.owner_username,
            'BOS3_TRAINING_INSTALLATION_ID': self.installation_id,
        }
        database_name = os.environ.get('BOS_TEST_DB_NAME')
        if not database_name or 'bos3-fasteners' not in Path(database_name).name.lower():
            self.fail('QA must provide a fresh BOS_TEST_DB_NAME containing bos3-fasteners.')
        self.env_patch = patch.dict(os.environ, self.environment, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        call_command('seed_bos3_fasteners', owner_username=self.owner_username, stdout=StringIO())
        self.marker = Configuration.objects.get(key='bos3_fixture').value
        self.client.force_login(self.owner)

    def get_state(self, case_id, expected=200, client=None):
        response = (client or self.client).get(f'/api/training/sessions/{case_id}/')
        self.assertEqual(response.status_code, expected, response.content)
        return response.json()

    def change(self, case_id, action, body, expected=200, client=None):
        response = (client or self.client).post(
            f'/api/training/sessions/{case_id}/{action}/', body,
            content_type='application/json')
        self.assertEqual(response.status_code, expected, response.content)
        return response.json()

    def start(self, case_id):
        return self.change(case_id, 'start', {})

    def check(self, case_id, step_id, value=None, expected=200):
        body = {'step_id': step_id}
        if value is not None:
            body['answers'] = {'value': value}
        return self.change(case_id, 'check', body, expected=expected)

    def erp_execute(self, payload):
        preview = self.client.post('/api/erp/preview/', payload, content_type='application/json')
        self.assertEqual(preview.status_code, 200, preview.content)
        confirm = self.client.post('/api/operations/confirm/', {
            'proposal_id': preview.json()['id'], 'confirmed': True}, content_type='application/json')
        self.assertEqual(confirm.status_code, 200, confirm.content)
        return confirm.json()

    def test_start_ordered_answer_wrong_answer_and_server_persistence(self):
        """A click cannot unlock C1; only the correct server-checked answer can."""
        first = self.start('BOS3-CASE-01')
        self.assertEqual(first['status'], 'in_progress')
        self.assertIsNotNone(first['session_id'])
        self.check('BOS3-CASE-01', 'supply', expected=422)
        self.check('BOS3-CASE-01', 'order', '499', expected=422)
        session = TrainingSession.objects.get(public_id=first['session_id'])
        self.assertEqual(session.progress, {})
        after = self.check('BOS3-CASE-01', 'order', '500')
        self.assertEqual(after['steps'][0]['status'], 'completed')
        self.assertEqual(after['steps'][1]['status'], 'available')
        session.refresh_from_db()
        self.assertIn('order', session.progress)

        resumed = Client()
        resumed.force_login(self.owner)
        restored = self.get_state('BOS3-CASE-01', client=resumed)
        self.assertEqual(restored['session_id'], first['session_id'])
        self.assertEqual(restored['steps'][0]['status'], 'completed')

    def test_current_step_get_is_projection_and_start_persists_normalized_selection(self):
        self.assertEqual(self.get_state('BOS3-CASE-01')['current_step'], 'order')
        started = self.start('BOS3-CASE-01')
        session = TrainingSession.objects.get(public_id=started['session_id'])
        self.assertEqual(started['current_step'], 'order')
        self.assertEqual(session.current_step, 'order')

        TrainingSession.objects.filter(pk=session.pk).update(current_step='crm')
        before = TrainingSession.objects.values('current_step', 'progress', 'status', 'updated_at').get(pk=session.pk)
        projected = self.get_state('BOS3-CASE-01')
        self.assertEqual(projected['current_step'], 'order')
        after = TrainingSession.objects.values('current_step', 'progress', 'status', 'updated_at').get(pk=session.pk)
        self.assertEqual(after, before)
        self.assertEqual(self.start('BOS3-CASE-01')['current_step'], 'order')
        session.refresh_from_db()
        self.assertEqual(session.current_step, 'order')

        self.check('BOS3-CASE-01', 'order', '500')
        self.change('BOS3-CASE-01', 'navigate', {'step_id': 'order'})
        self.assertEqual(self.get_state('BOS3-CASE-01')['current_step'], 'order')
        self.assertEqual(self.start('BOS3-CASE-01')['current_step'], 'order')
        self.change('BOS3-CASE-01', 'navigate', {'step_id': 'supply'})
        self.assertEqual(self.get_state('BOS3-CASE-01')['current_step'], 'supply')

        TrainingSession.objects.filter(pk=session.pk).update(current_step='crm')
        self.assertEqual(self.get_state('BOS3-CASE-01')['current_step'], 'supply')
        self.assertEqual(self.start('BOS3-CASE-01')['current_step'], 'supply')
        session.refresh_from_db()
        self.assertEqual(session.current_step, 'supply')

    def test_paused_session_projects_then_persists_current_step_on_resume(self):
        started = self.start('BOS3-CASE-01')
        self.change('BOS3-CASE-01', 'pause', {})
        session = TrainingSession.objects.get(public_id=started['session_id'])
        TrainingSession.objects.filter(pk=session.pk).update(current_step='unknown')
        projected = self.get_state('BOS3-CASE-01')
        self.assertEqual(projected['status'], 'paused')
        self.assertEqual(projected['current_step'], 'order')
        session.refresh_from_db()
        self.assertEqual(session.current_step, 'unknown')
        self.assertEqual(session.status, 'paused')

        resumed = self.start('BOS3-CASE-01')
        self.assertEqual(resumed['status'], 'in_progress')
        self.assertEqual(resumed['current_step'], 'order')
        session.refresh_from_db()
        self.assertEqual(session.current_step, 'order')
        self.assertEqual(session.status, 'in_progress')

    def test_changed_source_reports_on_read_without_write_and_persists_on_next_mutation(self):
        self.start('BOS3-CASE-01')
        self.check('BOS3-CASE-01', 'order', '500')
        line = SalesLine.objects.get(pk=self.marker['source_map']['BOS3-CASE-01']['line_id'])
        line.quantity = Decimal('501.000')
        line.save(update_fields=['quantity'])

        state = self.get_state('BOS3-CASE-01')
        self.assertEqual(state['status'], 'needs_recheck')
        self.assertEqual(state['steps'][0]['status'], 'needs_recheck')
        session = TrainingSession.objects.get(public_id=state['session_id'])
        # A GET is deliberately a read: it must not mutate the persisted session.
        self.assertEqual(session.status, 'in_progress')
        changed = self.change('BOS3-CASE-01', 'navigate', {'step_id': 'order'})
        self.assertEqual(changed['status'], 'needs_recheck')
        session.refresh_from_db()
        self.assertEqual(session.status, 'needs_recheck')

    def test_ceo_finance_case_and_observer_progress_only(self):
        ceo = self.get_state('BOS3-CASE-03')
        self.assertEqual(ceo['facts']['balance'], '6400.00')
        self.assertEqual(ceo['learning_mode'], 'practice')

        ceo_group = Group.objects.get(name='ceo')
        observer_group = Group.objects.get_or_create(name='observer')[0]
        self.owner.groups.remove(ceo_group)
        self.owner.groups.add(observer_group)
        catalog = self.client.get('/api/training/content/')
        self.assertEqual(catalog.status_code, 200, catalog.content)
        case = next(row for row in catalog.json()['cases'] if row['case_id'] == 'BOS3-CASE-01')
        self.assertFalse(case['available'])
        self.change('BOS3-CASE-01', 'start', {}, expected=404)

        # A real local owner bootstrap grants this narrow read capability; it does
        # not alter the observer role or the policy's operational source boundary.
        self.owner.user_permissions.add(Permission.objects.get(
            content_type__app_label='operations', codename='view_document'))
        self.assertEqual(Document.objects.get(code='B3-SPEC-M10-A').access_level, 'operational')
        catalog = self.client.get('/api/training/content/')
        self.assertEqual(catalog.status_code, 200, catalog.content)
        case = next(row for row in catalog.json()['cases'] if row['case_id'] == 'BOS3-CASE-01')
        self.assertTrue(case['available'])
        observer = self.start('BOS3-CASE-01')
        self.assertEqual(observer['learning_mode'], 'read_only')
        self.check('BOS3-CASE-01', 'order', '500')
        # Observer may record a learning answer but cannot mutate an ERP work item.
        response = self.client.post('/api/operations/preview/', {
            'action': 'create_task', 'title': 'Недозволена дія observer', 'assignee_id': 1,
            'deadline': '2026-10-01'}, content_type='application/json')
        self.assertEqual(response.status_code, 403, response.content)

    def test_foreign_user_and_disabled_marker_are_rejected_before_lesson_state(self):
        other = get_user_model().objects.create_user(username='foreign-training-user', password='synthetic-test-password')
        Group.objects.get(name='ceo').user_set.add(other)
        foreign = Client()
        foreign.force_login(other)
        self.get_state('BOS3-CASE-01', expected=403, client=foreign)

        with patch.dict(os.environ, {'BOS3_TRAINING_ENABLED': '0'}, clear=False):
            self.get_state('BOS3-CASE-01', expected=403)

    def test_marker_hash_and_bound_database_identity_reject_before_session_read(self):
        original = Configuration.objects.get(key='bos3_fixture')
        bad_hash = {**original.value, 'hash': '0' * 64}
        Configuration.objects.filter(pk=original.pk).update(value=bad_hash)
        self.get_state('BOS3-CASE-01', expected=403)

        Configuration.objects.filter(pk=original.pk).update(value=original.value)
        bad_path_identity = {**original.value, 'database_identity_sha256': 'f' * 64}
        Configuration.objects.filter(pk=original.pk).update(value=bad_path_identity)
        self.get_state('BOS3-CASE-01', expected=403)

    def test_crm_completion_and_post_completion_tour(self):
        """C3 completes only after task evidence and CRM preview/confirm, never export."""
        started = self.start('BOS3-CASE-03')
        self.check('BOS3-CASE-03', 'invoice', '6400')
        source = self.marker['source_map']['BOS3-CASE-03']
        owner = Employee.objects.get(pk=source['owner_id'])
        task_preview = self.client.post('/api/operations/preview/', {
            'action': 'create_task', 'title': 'Узгодити оплату B3-C3', 'assignee_id': owner.pk,
            'deadline': '2026-10-01', 'order_id': source['order_id'],
            'category': 'Фінанси', 'priority': 'medium'}, content_type='application/json')
        self.assertEqual(task_preview.status_code, 200, task_preview.content)
        task_confirm = self.client.post('/api/operations/confirm/', {
            'proposal_id': task_preview.json()['id'], 'confirmed': True}, content_type='application/json')
        self.assertEqual(task_confirm.status_code, 200, task_confirm.content)
        task = Task.objects.get(sales_order_id=source['order_id'])
        self.assertEqual((task.title, task.assignee_employee_id, task.category, task.priority),
                         ('Узгодити оплату B3-C3', owner.pk, 'Фінанси', 'medium'))
        self.check('BOS3-CASE-03', 'followup')

        before_crm = self.get_state('BOS3-CASE-03')
        self.assertEqual(before_crm['status'], 'in_progress')
        draft = self.client.get(
            f"/api/crm/handoff/{started['session_id']}/", {'case_id': 'BOS3-CASE-03'})
        self.assertEqual(draft.status_code, 200, draft.content)
        self.assertFalse(draft.json()['existing'])
        crm_preview = self.client.post('/api/operations/preview/', draft.json()['payload'],
            content_type='application/json')
        self.assertEqual(crm_preview.status_code, 200, crm_preview.content)
        crm_confirm = self.client.post('/api/operations/confirm/', {
            'proposal_id': crm_preview.json()['id'], 'confirmed': True}, content_type='application/json')
        self.assertEqual(crm_confirm.status_code, 200, crm_confirm.content)
        completed = self.check('BOS3-CASE-03', 'crm')
        self.assertEqual(completed['status'], 'completed')
        tour = self.change('BOS3-CASE-03', 'tour', {'status': 'completed'})
        self.assertEqual(tour['tour_state']['status'], 'completed')

    def test_case_01_receipt_and_production_use_only_erp_preview_confirm(self):
        self.start('BOS3-CASE-01')
        self.check('BOS3-CASE-01', 'order', '500')
        self.check('BOS3-CASE-01', 'supply', '120')
        source = self.marker['source_map']['BOS3-CASE-01']
        production_location = self.marker['source_map']['locations']['production']
        inspector_id = self.marker['source_map']['people']['quality']
        receipt = self.erp_execute({
            'action': 'erp_receive', 'purchase_id': source['purchase_id'],
            'code': 'B3-C1-RCV-101', 'location_id': production_location, 'quantity': '120'})
        received_lot = Lot.objects.get(pk=receipt['lot_id'])
        self.assertEqual(received_lot.quality, 'pending')
        self.erp_execute({'action': 'erp_quality', 'lot_id': received_lot.pk, 'result': 'approved',
            'inspector_id': inspector_id, 'note': 'Навчальна перевірка приймання шайб.'})
        self.check('BOS3-CASE-01', 'receipt')

        component_lots = source['component_lot_ids']
        for lot_id, quantity in ((component_lots['bolt'], '360'), (component_lots['nut'], '720'),
                                 (component_lots['washer'], '600'), (received_lot.pk, '120')):
            self.erp_execute({'action': 'erp_reserve', 'lot_id': lot_id, 'production_id': source['production_id'],
                              'quantity': quantity})
        self.erp_execute({'action': 'erp_start', 'production_id': source['production_id']})
        job = Production.objects.get(pk=source['production_id'])
        for route in job.routing:
            self.erp_execute({'action': 'erp_operator', 'production_id': job.pk, 'operation': route['name'],
                              'operator_id': job.owner_id, 'result': 'done', 'minutes': 30,
                              'defects': '0', 'note': 'Навчальна операція виконана.'})
        finished = self.erp_execute({'action': 'erp_finish', 'production_id': job.pk, 'quantity': '360',
            'code': 'B3-C1-FG-101', 'location_id': production_location, 'labor_cost': '288.00'})
        output_lot = Lot.objects.get(pk=finished['lot_id'])
        self.assertEqual(output_lot.quality, 'pending')
        self.erp_execute({'action': 'erp_quality', 'lot_id': output_lot.pk, 'result': 'approved',
            'inspector_id': job.owner_id, 'note': 'Навчальний допуск готових комплектів.'})
        state = self.check('BOS3-CASE-01', 'production')
        self.assertEqual(state['steps'][3]['status'], 'completed')
        job.refresh_from_db()
        self.assertEqual((job.status, job.produced, job.actual_cost), ('done', Decimal('360.000'), Decimal('4320.00')))

    def test_case_02_reserve_ship_crm_replay_noop_stale_and_foreign_privacy(self):
        started = self.start('BOS3-CASE-02')
        self.check('BOS3-CASE-02', 'order', '250')
        self.check('BOS3-CASE-02', 'quality', '20')
        source = self.marker['source_map']['BOS3-CASE-02']
        blocked = Lot.objects.get(pk=source['blocked_lot_id'])
        blocked_before = (blocked.quantity, blocked.quality)
        self.erp_execute({'action': 'erp_reserve', 'lot_id': source['approved_lot_id'],
                          'line_id': source['line_id'], 'quantity': '250'})
        self.check('BOS3-CASE-02', 'reservation')
        self.erp_execute({'action': 'erp_ship', 'line_id': source['line_id'],
                          'lot_id': source['approved_lot_id'], 'quantity': '250',
                          'reference': source['shipment_reference']})
        self.check('BOS3-CASE-02', 'shipment')
        blocked.refresh_from_db()
        self.assertEqual((blocked.quantity, blocked.quality), blocked_before)
        shipment = Movement.objects.get(reference=source['shipment_reference'], kind='shipment')
        self.assertEqual(shipment.lot_id, source['approved_lot_id'])

        draft = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': 'BOS3-CASE-02'})
        self.assertEqual(draft.status_code, 200, draft.content)
        preview = self.client.post('/api/operations/preview/', draft.json()['payload'], content_type='application/json')
        self.assertEqual(preview.status_code, 200, preview.content)
        confirmed = self.client.post('/api/operations/confirm/', {
            'proposal_id': preview.json()['id'], 'confirmed': True}, content_type='application/json')
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        state = self.check('BOS3-CASE-02', 'crm')
        self.assertEqual(state['status'], 'completed')
        deal = CRMDeal.objects.get(training_session__public_id=started['session_id'])
        self.assertEqual(CRMDeal.objects.filter(training_session__public_id=started['session_id']).count(), 1)

        before_replay = ActionProposal.objects.count()
        existing = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': 'BOS3-CASE-02'})
        self.assertEqual(existing.status_code, 200, existing.content)
        self.assertTrue(existing.json()['existing'])
        self.assertEqual(ActionProposal.objects.count(), before_replay)
        no_change = self.client.post('/api/operations/preview/', {
            'action': 'crm_deal_update', 'deal_id': deal.pk, 'reason': 'Перевірка без зміни.',
            'next_action': deal.next_action}, content_type='application/json')
        self.assertEqual(no_change.status_code, 200, no_change.content)
        self.assertEqual((no_change.json()['state'], no_change.json()['id']), ('no_change', None))

        old = self.client.post('/api/operations/preview/', {
            'action': 'crm_deal_update', 'deal_id': deal.pk, 'reason': 'Застарілий preview.',
            'next_action': 'Старий навчальний текст контакту.'}, content_type='application/json')
        self.assertEqual(old.status_code, 200, old.content)
        newer = self.client.post('/api/operations/preview/', {
            'action': 'crm_deal_update', 'deal_id': deal.pk, 'reason': 'Актуалізація наступної дії.',
            'next_action': 'Актуальна навчальна наступна дія.'}, content_type='application/json')
        self.assertEqual(newer.status_code, 200, newer.content)
        updated = self.client.post('/api/operations/confirm/', {
            'proposal_id': newer.json()['id'], 'confirmed': True}, content_type='application/json')
        self.assertEqual(updated.status_code, 200, updated.content)
        stale = self.client.post('/api/operations/confirm/', {
            'proposal_id': old.json()['id'], 'confirmed': True}, content_type='application/json')
        self.assertEqual(stale.status_code, 409, stale.content)

        ceo_group = Group.objects.get(name='ceo')
        manager_group = Group.objects.get_or_create(name='manager')[0]
        self.owner.groups.remove(ceo_group)
        self.owner.groups.add(manager_group)
        role_hidden = self.client.get(f'/api/crm/deals/{deal.pk}/')
        self.assertEqual(role_hidden.status_code, 404, role_hidden.content)
        self.assertNotIn(source['shipment_reference'].encode(), role_hidden.content)

        foreign_user = get_user_model().objects.create_user(username='c2-foreign-user', password='synthetic-test-password')
        Group.objects.get(name='ceo').user_set.add(foreign_user)
        foreign = Client()
        foreign.force_login(foreign_user)
        hidden = foreign.get(f'/api/crm/deals/{deal.pk}/')
        self.assertEqual(hidden.status_code, 403, hidden.content)
        self.assertNotIn(source['shipment_reference'].encode(), hidden.content)

    def test_optional_tour_is_separate_from_lesson_completion(self):
        started = self.start('BOS3-CASE-01')
        tour = self.change('BOS3-CASE-01', 'tour', {'status': 'skipped'})
        self.assertEqual(tour['tour_state']['status'], 'skipped')
        self.assertEqual(tour['status'], 'in_progress')
        session = TrainingSession.objects.get(public_id=started['session_id'])
        self.assertEqual(session.status, 'in_progress')

    def _d02_batch(self, case_id):
        with patch('training.service._expected_stamps', wraps=training_service._expected_stamps) as spy:
            state = self.get_state(case_id)
        marker, observed_case, rows, access = spy.call_args.args
        self.assertEqual(observed_case, case_id)
        return state, deepcopy(marker), deepcopy(rows), access

    def test_d02_f01_01(self):
        matrix = {
            'BOS3-CASE-01': [('order', set()), ('supply', set()),
                             ('receipt', {'purchase'}), ('production', {'production'}),
                             ('crm', {'deals'})],
            'BOS3-CASE-02': [('order', set()), ('quality', {'blocked_lot'}),
                             ('reservation', {'approved_lot', 'blocked_lot', 'reservations', 'shipments'}),
                             ('shipment', {'approved_lot', 'blocked_lot', 'shipments'}),
                             ('crm', {'deals'})],
            'BOS3-CASE-03': [('invoice', {'invoice'}),
                             ('followup', {'invoice', 'tasks', 'assignee_refs'}),
                             ('crm', {'deals'})],
        }
        common = {'order', 'line', 'customer_ref'}
        for case_id, expected in matrix.items():
            state, marker, rows, access = self._d02_batch(case_id)
            self.assertEqual([row['id'] for row in rows], [item[0] for item in expected])
            for row, (_, additions) in zip(rows, expected):
                self.assertEqual(set(row['_source_ids']), common | additions)
                self.assertEqual(row['_source_ids']['order'][0], 'erp.salesorder')
                self.assertEqual(row['_source_ids']['line'][0], 'erp.salesline')
                self.assertEqual(row['_source_ids']['customer_ref'][0], 'finance.counterparty')
            first = training_service._expected_stamps(marker, case_id, rows, access)
            self.assertEqual(first, training_service._expected_stamps(marker, case_id, rows, access))
            self.assertEqual(len(first), len(expected))
            self.assertNotIn('_source_ids', repr(state))

    def test_d02_f01_02(self):
        variants = [('BOS3-CASE-01', 'purchase', 2),
                    ('BOS3-CASE-01', 'production', 3),
                    ('BOS3-CASE-02', 'blocked_lot', 1),
                    ('BOS3-CASE-02', 'approved_lot', 2),
                    ('BOS3-CASE-03', 'invoice', 0)]
        for case_id, slot, first_changed in variants:
            _, marker, rows, access = self._d02_batch(case_id)
            before = training_service._expected_stamps(marker, case_id, rows, access)
            changed = deepcopy(rows)
            for row in changed:
                if slot in row['_source_ids']:
                    row['_source_ids'][slot][1] += 100000
            after = training_service._expected_stamps(marker, case_id, changed, access)
            for index, row in enumerate(rows):
                self.assertEqual(before[row['id']] == after[row['id']], index < first_changed)
        _, marker, rows, access = self._d02_batch('BOS3-CASE-01')
        before = training_service._expected_stamps(marker, 'BOS3-CASE-01', rows, access)
        for slot in ('order', 'line', 'customer_ref'):
            changed = deepcopy(rows)
            for row in changed:
                row['_source_ids'][slot][1] += 100000
            after = training_service._expected_stamps(marker, 'BOS3-CASE-01', changed, access)
            self.assertTrue(all(before[key] != after[key] for key in before))

    def test_d02_f01_03(self):
        policy = Policy.for_user(self.owner)
        marker = deepcopy(self.marker)
        marker['source_map']['BOS3-CASE-01']['order_id'] = 999999999
        with self.assertRaises(SalesOrder.DoesNotExist):
            training_service.observations(policy, marker, 'BOS3-CASE-01', None)
        _, marker, rows, access = self._d02_batch('BOS3-CASE-01')
        rows[0]['_source_ids']['order'][1] = None
        with self.assertRaises(Conflict):
            training_service._expected_stamps(marker, 'BOS3-CASE-01', rows, access)

    def test_d02_f01_04(self):
        _, marker, rows, access = self._d02_batch('BOS3-CASE-03')
        tasks = [{'id': 101001, 'assignee_employee_id': 201001,
                  'deadline': '2026-10-02', 'title': 'Перший контакт'},
                 {'id': 101002, 'assignee_employee_id': 201002,
                  'deadline': '2026-10-03', 'title': 'Другий контакт'}]
        followup = next(row for row in rows if row['id'] == 'followup')
        actual_tasks = deepcopy(followup['observed']['tasks'])
        actual_passed = followup['passed']
        self.assertEqual(actual_tasks, [])
        self.assertFalse(actual_passed)
        followup['observed']['tasks'] = deepcopy(tasks)
        followup['passed'] = True
        followup['_source_ids']['tasks'] = [['tasks.task', task['id']] for task in tasks]
        followup['_source_ids']['assignee_refs'] = [
            [task['id'], ['employees.employee', task['assignee_employee_id']]] for task in tasks]
        before = training_service._expected_stamps(marker, 'BOS3-CASE-03', rows, access)
        shuffled = deepcopy(rows)
        row = next(item for item in shuffled if item['id'] == 'followup')
        row['observed']['tasks'].reverse()
        row['_source_ids']['tasks'].reverse()
        row['_source_ids']['assignee_refs'].reverse()
        self.assertEqual(before, training_service._expected_stamps(marker, 'BOS3-CASE-03', shuffled, access))
        row['observed']['tasks'][0]['id'] = 101003
        row['_source_ids']['tasks'][0][1] = 101003
        row['_source_ids']['assignee_refs'][0][0] = 101003
        after = training_service._expected_stamps(marker, 'BOS3-CASE-03', shuffled, access)
        self.assertEqual(before['invoice'], after['invoice'])
        self.assertNotEqual(before['followup'], after['followup'])
        self.assertNotEqual(before['crm'], after['crm'])
        order = SalesOrder.objects.get(pk=self.marker['source_map']['BOS3-CASE-03']['order_id'])
        Task.objects.create(title='Без призначення', sales_order=order, deadline=None,
                            assignee_employee=None)
        _, _, fresh, _ = self._d02_batch('BOS3-CASE-03')
        fresh_followup = next(item for item in fresh if item['id'] == 'followup')
        self.assertEqual(fresh_followup['observed']['tasks'], actual_tasks)
        self.assertEqual(fresh_followup['passed'], actual_passed)

    def test_d02_f01_05(self):
        _, marker, rows, access = self._d02_batch('BOS3-CASE-02')
        reservation = next(row for row in rows if row['id'] == 'reservation')
        shipment = next(row for row in rows if row['id'] == 'shipment')
        movement = {'pk': 501001, 'lot_id': reservation['_source_ids']['approved_lot'][1],
                    'quantity': Decimal('1')}
        reservation['_source_ids']['shipments'] = [['erp.movement', movement['pk']]]
        shipment['_source_ids']['shipments'] = [['erp.movement', movement['pk']]]
        shipment['observed']['movements'] = [movement]
        base = training_service._expected_stamps(marker, 'BOS3-CASE-02', rows, access)
        duplicates = deepcopy(rows)
        next(row for row in duplicates if row['id'] == 'reservation')['_source_ids']['shipments'].append(
            ['erp.movement', movement['pk']])
        duplicate_shipment = next(row for row in duplicates if row['id'] == 'shipment')
        duplicate_shipment['_source_ids']['shipments'].append(['erp.movement', movement['pk']])
        duplicate_shipment['observed']['movements'].append(deepcopy(movement))
        self.assertEqual(base, training_service._expected_stamps(marker, 'BOS3-CASE-02', duplicates, access))
        duplicate_shipment['observed']['movements'][-1]['quantity'] = Decimal('2')
        with self.assertRaises(Conflict):
            training_service._expected_stamps(marker, 'BOS3-CASE-02', duplicates, access)

        policy = Policy.for_user(self.owner)
        refs = self.marker['source_map']['BOS3-CASE-02']
        repeated = SimpleNamespace(pk=501002, line_id=refs['line_id'],
                                   lot_id=refs['approved_lot_id'], quantity=Decimal('2'))
        original_queryset = policy.queryset

        def with_repeated_reservation(model):
            if model is Reservation:
                return SimpleNamespace(filter=lambda **kwargs: [repeated, repeated])
            return original_queryset(model)

        with patch.object(policy, 'queryset', side_effect=with_repeated_reservation):
            facts, _, _ = training_service.observations(policy, self.marker, 'BOS3-CASE-02', None)
        self.assertEqual(facts['reserved'], '4')
        contradictory = SimpleNamespace(pk=repeated.pk, line_id=repeated.line_id,
                                        lot_id=repeated.lot_id, quantity=Decimal('3'))

        def with_conflicting_reservation(model):
            if model is Reservation:
                return SimpleNamespace(filter=lambda **kwargs: [repeated, contradictory])
            return original_queryset(model)

        with patch.object(policy, 'queryset', side_effect=with_conflicting_reservation):
            with self.assertRaises(Conflict):
                training_service.observations(policy, self.marker, 'BOS3-CASE-02', None)

    def test_d02_f01_06(self):
        _, marker, rows, access = self._d02_batch('BOS3-CASE-02')
        reservation = next(row for row in rows if row['id'] == 'reservation')
        shipment = next(row for row in rows if row['id'] == 'shipment')
        movement = {'pk': 601001, 'lot_id': reservation['_source_ids']['approved_lot'][1],
                    'quantity': Decimal('1')}
        reservation['_source_ids']['reservations'] = [['erp.reservation', 601002]]
        reservation['_source_ids']['shipments'] = [['erp.movement', movement['pk']]]
        shipment['_source_ids']['shipments'] = [['erp.movement', movement['pk']]]
        shipment['observed']['movements'] = [movement]
        before = training_service._expected_stamps(marker, 'BOS3-CASE-02', rows, access)
        changed_reservation = deepcopy(rows)
        next(row for row in changed_reservation if row['id'] == 'reservation')[
            '_source_ids']['reservations'][0][1] = 601003
        after = training_service._expected_stamps(marker, 'BOS3-CASE-02', changed_reservation, access)
        self.assertEqual([before[key] == after[key] for key in before],
                         [True, True, False, False, False])
        changed_movement = deepcopy(rows)
        next(row for row in changed_movement if row['id'] == 'reservation')[
            '_source_ids']['shipments'][0][1] = 601004
        changed_shipment = next(row for row in changed_movement if row['id'] == 'shipment')
        changed_shipment['_source_ids']['shipments'][0][1] = 601004
        changed_shipment['observed']['movements'][0]['pk'] = 601004
        after = training_service._expected_stamps(marker, 'BOS3-CASE-02', changed_movement, access)
        self.assertEqual([before[key] == after[key] for key in before],
                         [True, True, False, False, False])
        changed_lot = deepcopy(rows)
        next(row for row in changed_lot if row['id'] == 'shipment')[
            'observed']['movements'][0]['lot_id'] += 1
        after = training_service._expected_stamps(marker, 'BOS3-CASE-02', changed_lot, access)
        self.assertNotEqual(before['shipment'], after['shipment'])

    def test_d02_f01_07(self):
        for case_id in training_service.CASE_IDS:
            started = self.start(case_id)
            _, marker, rows, access = self._d02_batch(case_id)
            legacy = {row['id']: {'stamp': training_service.digest({
                'observed': row['observed'], 'answer': row['expected'],
                'access': access, 'fixture': marker['hash']})} for row in rows}
            legacy['orphan'] = {'stamp': 'retained-unknown'}
            session = TrainingSession.objects.get(public_id=started['session_id'])
            TrainingSession.objects.filter(pk=session.pk).update(progress=legacy)
            state = self.get_state(case_id)
            self.assertEqual(state['steps'][0]['status'], 'needs_recheck')
            self.assertTrue(all(row['status'] == 'locked' for row in state['steps'][1:]))
            session.refresh_from_db()
            self.assertEqual(session.progress, legacy)
            current = training_service._expected_stamps(marker, case_id, rows, access)
            self.assertTrue(all(current[row['id']] != legacy[row['id']]['stamp'] for row in rows))
        _, marker, rows, access = self._d02_batch('BOS3-CASE-01')
        observer_rows = deepcopy(rows)
        for row in observer_rows:
            if row['kind'] != 'answer':
                row.update(kind='answer', expected='500', passed=False)
        observer = training_service._expected_stamps(marker, 'BOS3-CASE-01', observer_rows, access)
        for row in observer_rows:
            old = training_service.digest({'observed': row['observed'], 'answer': row['expected'],
                                           'access': access, 'fixture': marker['hash']})
            self.assertNotEqual(observer[row['id']], old)

    def test_d02_f01_08(self):
        started = self.start('BOS3-CASE-01')
        session = TrainingSession.objects.get(public_id=started['session_id'])
        TrainingSession.objects.filter(pk=session.pk).update(
            status='completed', current_step='crm', progress={'order': {'stamp': 'legacy'}})
        before = TrainingSession.objects.values(
            'status', 'current_step', 'progress', 'updated_at').get(pk=session.pk)
        with patch.object(TrainingSession, 'save', side_effect=AssertionError('GET save')), patch(
                'erp.service.write_lock', side_effect=AssertionError('GET mutex')):
            first = self.get_state('BOS3-CASE-01')
            second = self.get_state('BOS3-CASE-01')
        self.assertEqual(first, second)
        self.assertEqual(first['status'], 'needs_recheck')
        self.assertEqual(first['steps'][0]['status'], 'needs_recheck')
        self.assertEqual(TrainingSession.objects.values(
            'status', 'current_step', 'progress', 'updated_at').get(pk=session.pk), before)

    def test_d02_f01_09(self):
        started = self.start('BOS3-CASE-01')
        session = TrainingSession.objects.get(public_id=started['session_id'])
        with patch('training.service.observations', wraps=training_service.observations) as observed:
            self.check('BOS3-CASE-01', 'order', '499', expected=422)
        self.assertEqual(observed.call_count, 1)
        session.refresh_from_db()
        self.assertEqual(session.progress, {})
        with patch('training.service.observations', wraps=training_service.observations) as observed:
            result = self.check('BOS3-CASE-01', 'order', '500')
        self.assertEqual(observed.call_count, 1)
        session.refresh_from_db()
        self.assertEqual(set(session.progress), {'order'})
        self.assertEqual(set(session.progress['order']), {'stamp'})
        self.assertEqual(result['steps'][0]['status'], 'completed')
        self.assertEqual(Decimal(result['steps'][0]['evidence']['observed']['quantity']), Decimal('500'))
        with patch('training.service.observations', wraps=training_service.observations) as observed:
            self.check('BOS3-CASE-01', 'crm', expected=422)
        self.assertEqual(observed.call_count, 1)
        session.refresh_from_db()
        self.assertEqual(set(session.progress), {'order'})

    def test_d02_f01_10(self):
        _, marker, rows, access = self._d02_batch('BOS3-CASE-01')
        before = training_service._expected_stamps(marker, 'BOS3-CASE-01', rows, access)
        changed = training_service._expected_stamps(marker, 'BOS3-CASE-01', rows, access + '-changed')
        self.assertTrue(all(before[key] != changed[key] for key in before))

        ceo = Group.objects.get(name='ceo')
        observer = Group.objects.get_or_create(name='observer')[0]
        self.owner.groups.remove(ceo)
        self.owner.groups.add(observer)
        self.owner.user_permissions.add(Permission.objects.get(
            content_type__app_label='operations', codename='view_document'))
        state, marker, rows, access = self._d02_batch('BOS3-CASE-01')
        self.assertEqual(state['learning_mode'], 'read_only')
        for row in rows:
            if row['id'] in ('receipt', 'production', 'crm'):
                self.assertEqual(row['kind'], 'answer')
                self.assertFalse(row['passed'])
        self.get_state('BOS3-CASE-03', expected=403)

        empty_session = SimpleNamespace(progress={}, status='in_progress', current_step='',
                                        public_id='empty-session', tour_state={})
        no_access = SimpleNamespace(role='ceo', access_revision=lambda: self.fail('empty access read'))
        with patch('training.service.identity', return_value={}), patch(
                'training.service.observations', return_value=({}, [], [])):
            empty = session_state(no_access, marker, 'BOS3-CASE-01', empty_session)
        self.assertEqual(empty['steps'], [])
        self.assertIsNone(empty['current_step'])

    def test_d02_f01_11(self):
        started = self.start('BOS3-CASE-01')
        self.check('BOS3-CASE-01', 'order', '500')
        shortage = self.marker['source_map']['BOS3-CASE-01']['initial']['washer_shortage']
        self.check('BOS3-CASE-01', 'supply', str(shortage))
        session = TrainingSession.objects.get(public_id=started['session_id'])
        supply_stamp = session.progress['supply']['stamp']
        unchanged = self.check('BOS3-CASE-01', 'order', '500')
        self.assertEqual(unchanged['steps'][1]['status'], 'completed')
        session.refresh_from_db()
        self.assertEqual(session.progress['supply']['stamp'], supply_stamp)

        line = SalesLine.objects.get(pk=self.marker['source_map']['BOS3-CASE-01']['line_id'])
        line.quantity = Decimal('501.000')
        line.save(update_fields=['quantity'])
        stale = self.get_state('BOS3-CASE-01')
        self.assertEqual(stale['steps'][0]['status'], 'needs_recheck')
        self.assertEqual(stale['steps'][1]['status'], 'locked')
        rechecked = self.check('BOS3-CASE-01', 'order', '501')
        self.assertEqual(rechecked['steps'][0]['status'], 'completed')
        self.assertEqual(rechecked['steps'][1]['status'], 'needs_recheck')
        session.refresh_from_db()
        self.assertEqual(session.progress['supply']['stamp'], supply_stamp)

    def test_d02_f01_12(self):
        started = self.start('BOS3-CASE-01')
        session = TrainingSession.objects.get(public_id=started['session_id'])
        TrainingSession.objects.filter(pk=session.pk).update(
            progress={'unknown-orphan': {'stamp': 'untouched'}})
        self.change('BOS3-CASE-01', 'navigate', {'step_id': 'order'})
        self.change('BOS3-CASE-01', 'pause', {})
        self.start('BOS3-CASE-01')
        self.change('BOS3-CASE-01', 'tour', {'status': 'skipped'})
        session.refresh_from_db()
        self.assertEqual(session.progress, {'unknown-orphan': {'stamp': 'untouched'}})
        state = self.get_state('BOS3-CASE-01')
        self.assertNotIn('_source_ids', repr(state))
        for row in state['steps']:
            self.assertEqual(set(row), {'id', 'title', 'route', 'kind', 'instruction',
                                        'status', 'evidence', 'question', 'answer_fields'})
        self.check('BOS3-CASE-01', 'order', '500')
        session.refresh_from_db()
        self.assertEqual(set(session.progress), {'unknown-orphan', 'order'})
        self.assertEqual(set(session.progress['order']), {'stamp'})



    def test_d08_f02_01(self):
        case_id = 'BOS3-CASE-03'
        started = self.start(case_id)
        self.check(case_id, 'invoice', '6400')
        source = self.marker['source_map'][case_id]
        task = Task.objects.create(title='Погодити оплату', sales_order_id=source['order_id'],
                                   assignee_employee_id=source['owner_id'], deadline='2026-10-01')
        self.check(case_id, 'followup')
        session = TrainingSession.objects.get(public_id=started['session_id'])
        policy = Policy.for_user(self.owner)
        self.assertTrue(training_service.case03_handoff_ready(
            policy, self.marker, session, source['order_id'], source['invoice_id']))
        draft = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual(draft.status_code, 200, draft.content)
        preview = self.client.post('/api/operations/preview/', draft.json()['payload'],
                                   content_type='application/json')
        self.assertEqual(preview.status_code, 200, preview.content)
        confirm = self.client.post('/api/operations/confirm/',
                                   {'proposal_id': preview.json()['id'], 'confirmed': True},
                                   content_type='application/json')
        self.assertEqual(confirm.status_code, 200, confirm.content)
        self.assertEqual(CRMDeal.objects.filter(training_session=session).count(), 1)
        self.assertEqual(Task.objects.get(pk=task.pk).sales_order_id, source['order_id'])

    def test_d08_f02_02(self):
        case_id = 'BOS3-CASE-03'
        started = self.start(case_id)
        source = self.marker['source_map'][case_id]
        Task.objects.create(title='Видиме доручення', sales_order_id=source['order_id'],
                            assignee_employee_id=source['owner_id'], deadline='2026-10-01')
        draft = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual((draft.status_code, draft.json()),
                         (422, {'error': 'Спочатку перевірте попередній крок.'}))
        self.check(case_id, 'invoice', '6400')
        self.check(case_id, 'followup')
        session = TrainingSession.objects.get(public_id=started['session_id'])
        ready = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual(ready.status_code, 200, ready.content)
        payload = ready.json()['payload']
        valid_progress = deepcopy(session.progress)
        TrainingSession.objects.filter(pk=session.pk).update(progress={})
        before = ActionProposal.objects.count()
        preview = self.client.post('/api/operations/preview/', payload, content_type='application/json')
        self.assertEqual((preview.status_code, preview.json()),
                         (422, {'error': 'Спочатку перевірте попередній крок.'}))
        self.assertEqual(ActionProposal.objects.count(), before)
        self.assertFalse(CRMDeal.objects.exists())
        TrainingSession.objects.filter(pk=session.pk).update(progress=valid_progress)
        preview = self.client.post('/api/operations/preview/', payload, content_type='application/json')
        self.assertEqual(preview.status_code, 200, preview.content)
        TrainingSession.objects.filter(pk=session.pk).update(progress={})
        confirm = self.client.post('/api/operations/confirm/',
                                   {'proposal_id': preview.json()['id'], 'confirmed': True},
                                   content_type='application/json')
        self.assertEqual((confirm.status_code, confirm.json()),
                         (422, {'error': 'Спочатку перевірте попередній крок.'}))
        self.assertIsNone(ActionProposal.objects.get(pk=preview.json()['id']).receipt)
        self.assertEqual(TrainingSession.objects.get(pk=session.pk).progress, {})
        self.assertFalse(CRMDeal.objects.exists())

    def test_d08_f02_03(self):
        case_id = 'BOS3-CASE-03'
        started = self.start(case_id)
        source = self.marker['source_map'][case_id]
        session = TrainingSession.objects.get(public_id=started['session_id'])
        policy = Policy.for_user(self.owner)
        Task.objects.create(title='Поточне доручення', sales_order_id=source['order_id'],
                            assignee_employee_id=source['owner_id'], deadline='2026-10-01')
        self.assertFalse(training_service.case03_handoff_ready(
            policy, self.marker, session, source['order_id'], source['invoice_id']))
        incomplete = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual(incomplete.status_code, 422, incomplete.content)
        self.check(case_id, 'invoice', '6400')
        session.refresh_from_db()
        self.assertFalse(training_service.case03_handoff_ready(
            policy, self.marker, session, source['order_id'], source['invoice_id']))
        incomplete = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual(incomplete.status_code, 422, incomplete.content)
        self.check(case_id, 'followup')
        session.refresh_from_db()
        self.assertTrue(training_service.case03_handoff_ready(
            policy, self.marker, session, source['order_id'], source['invoice_id']))
        projected = training_service.session_state(policy, self.marker, case_id, session)
        for step in projected['steps']:
            if step['id'] == 'followup':
                step['evidence']['passed'] = False
        with patch('training.service._project_observation', return_value=projected):
            self.assertFalse(training_service.case03_handoff_ready(
                policy, self.marker, session, source['order_id'], source['invoice_id']))
            denied = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual((denied.status_code, denied.json()),
                         (422, {'error': 'Спочатку перевірте попередній крок.'}))
        observation = training_service.observations(policy, self.marker, case_id, session)
        for changed in ('missing', 'duplicate'):
            rows = deepcopy(observation[2])
            if changed == 'missing':
                rows.pop(0)
            else:
                rows.insert(0, deepcopy(rows[0]))
            with patch('training.service.observations', return_value=(observation[0], observation[1], rows)):
                self.assertFalse(training_service.case03_handoff_ready(
                    policy, self.marker, session, source['order_id'], source['invoice_id']))
                denied = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
            self.assertEqual((denied.status_code, denied.json()),
                             (422, {'error': 'Спочатку перевірте попередній крок.'}))
        from operations.models import Invoice
        paid_before = Invoice.objects.get(pk=source['invoice_id']).paid
        Invoice.objects.filter(pk=source['invoice_id']).update(paid=paid_before + Decimal('1'))
        self.assertFalse(training_service.case03_handoff_ready(
            policy, self.marker, session, source['order_id'], source['invoice_id']))
        denied = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual(denied.status_code, 422, denied.content)
        Invoice.objects.filter(pk=source['invoice_id']).update(paid=paid_before)
        task = Task.objects.get(sales_order_id=source['order_id'])
        Task.objects.filter(pk=task.pk).update(title='Змінений поточний контакт')
        changed_task = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual(changed_task.status_code, 422, changed_task.content)
        Task.objects.filter(pk=task.pk).update(title='Поточне доручення')
        TrainingSession.objects.filter(pk=session.pk).update(progress={'invoice': {'stamp': 'old'},
            'followup': session.progress['followup']}, status='paused')
        session.refresh_from_db()
        self.assertFalse(training_service.case03_handoff_ready(
            policy, self.marker, session, source['order_id'], source['invoice_id']))
        stale = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual((stale.status_code, stale.json()),
                         (422, {'error': 'Спочатку перевірте попередній крок.'}))

    def test_d08_f02_04(self):
        case_id = 'BOS3-CASE-03'
        started = self.start(case_id)
        self.check(case_id, 'invoice', '6400')
        source = self.marker['source_map'][case_id]
        task = Task.objects.create(title='Контакт', sales_order_id=source['order_id'],
                                   assignee_employee_id=source['owner_id'], deadline='2026-10-01')
        self.check(case_id, 'followup')
        draft = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id}).json()
        session = TrainingSession.objects.get(public_id=started['session_id'])
        before = deepcopy(session.progress)
        mutations = (
            ('archived', {'archived_at': timezone.now()}),
            ('without_assignee', {'assignee_employee_id': None}),
            ('without_deadline', {'deadline': None}),
            ('moved_order', {'sales_order_id': self.marker['source_map']['BOS3-CASE-01']['order_id']}),
        )
        for label, change in mutations:
            with self.subTest(task_change=label):
                preview = self.client.post('/api/operations/preview/', draft['payload'],
                                           content_type='application/json')
                self.assertEqual(preview.status_code, 200, preview.content)
                Task.objects.filter(pk=task.pk).update(**change)
                confirm = self.client.post('/api/operations/confirm/',
                    {'proposal_id': preview.json()['id'], 'confirmed': True},
                    content_type='application/json')
                self.assertEqual((confirm.status_code, confirm.json()),
                    (422, {'error': 'Спочатку перевірте попередній крок.'}))
                self.assertIsNone(ActionProposal.objects.get(pk=preview.json()['id']).receipt)
                self.assertFalse(CRMDeal.objects.filter(training_session=session).exists())
                self.assertEqual(TrainingSession.objects.get(pk=session.pk).progress, before)
                Task.objects.filter(pk=task.pk).update(archived_at=None,
                    assignee_employee_id=source['owner_id'], deadline='2026-10-01',
                    sales_order_id=source['order_id'])
        preview = self.client.post('/api/operations/preview/', draft['payload'],
                                   content_type='application/json')
        self.assertEqual(preview.status_code, 200, preview.content)
        Task.objects.filter(pk=task.pk).delete()
        confirm = self.client.post('/api/operations/confirm/',
            {'proposal_id': preview.json()['id'], 'confirmed': True}, content_type='application/json')
        self.assertEqual((confirm.status_code, confirm.json()),
                         (422, {'error': 'Спочатку перевірте попередній крок.'}))
        self.assertIsNone(ActionProposal.objects.get(pk=preview.json()['id']).receipt)
        self.assertFalse(CRMDeal.objects.filter(training_session=session).exists())
        self.assertEqual(TrainingSession.objects.get(pk=session.pk).progress, before)

    def test_d08_f02_05(self):
        case_id = 'BOS3-CASE-03'
        started = self.start(case_id)
        self.check(case_id, 'invoice', '6400')
        source = self.marker['source_map'][case_id]
        first = Task.objects.create(title='Контакт', sales_order_id=source['order_id'],
                                    assignee_employee_id=source['owner_id'], deadline='2026-10-01')
        second = Task.objects.create(title='Наступний контакт', sales_order_id=source['order_id'],
                                     assignee_employee_id=source['owner_id'], deadline='2026-10-02')
        self.check(case_id, 'followup')
        session = TrainingSession.objects.get(public_id=started['session_id'])
        policy = Policy.for_user(self.owner)
        self.assertTrue(training_service.case03_handoff_ready(
            policy, self.marker, session, source['order_id'], source['invoice_id']))
        observation = training_service.observations(policy, self.marker, case_id, session)
        shuffled = deepcopy(observation[2])
        followup = next(row for row in shuffled if row['id'] == 'followup')
        followup['observed']['tasks'].reverse()
        followup['_source_ids']['tasks'].reverse()
        followup['_source_ids']['assignee_refs'].reverse()
        with patch('training.service.observations', return_value=(observation[0], observation[1], shuffled)):
            self.assertTrue(training_service.case03_handoff_ready(
                policy, self.marker, session, source['order_id'], source['invoice_id']))
        with patch.object(policy, 'tasks', wraps=policy.tasks) as task_query:
            self.assertTrue(training_service.case03_handoff_ready(
                policy, self.marker, session, source['order_id'], source['invoice_id']))
        self.assertEqual(task_query.call_count, 1)
        other_assignee = Employee.objects.exclude(pk=source['owner_id']).first()
        self.assertIsNotNone(other_assignee)
        draft = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id}).json()
        before = deepcopy(session.progress)
        for label, update in (('title', {'title': 'Змінений контакт'}),
                              ('deadline', {'deadline': '2026-10-03'}),
                              ('assignee', {'assignee_employee_id': other_assignee.pk})):
            with self.subTest(task_change=label):
                preview = self.client.post('/api/operations/preview/', draft['payload'],
                                           content_type='application/json')
                self.assertEqual(preview.status_code, 200, preview.content)
                Task.objects.filter(pk=first.pk).update(**update)
                confirm = self.client.post('/api/operations/confirm/',
                    {'proposal_id': preview.json()['id'], 'confirmed': True},
                    content_type='application/json')
                self.assertEqual((confirm.status_code, confirm.json()),
                    (422, {'error': 'Спочатку перевірте попередній крок.'}))
                self.assertIsNone(ActionProposal.objects.get(pk=preview.json()['id']).receipt)
                self.assertFalse(CRMDeal.objects.filter(training_session=session).exists())
                self.assertEqual(TrainingSession.objects.get(pk=session.pk).progress, before)
            Task.objects.filter(pk=first.pk).update(title='Контакт', deadline='2026-10-01',
                                                     assignee_employee_id=source['owner_id'])
        preview = self.client.post('/api/operations/preview/', draft['payload'],
                                   content_type='application/json')
        self.assertEqual(preview.status_code, 200, preview.content)
        Task.objects.filter(pk=first.pk).delete()
        Task.objects.create(title='Контакт', sales_order_id=source['order_id'],
                            assignee_employee_id=source['owner_id'], deadline='2026-10-01')
        replaced = self.client.post('/api/operations/confirm/',
            {'proposal_id': preview.json()['id'], 'confirmed': True}, content_type='application/json')
        self.assertEqual((replaced.status_code, replaced.json()),
                         (422, {'error': 'Спочатку перевірте попередній крок.'}))
        self.assertIsNone(ActionProposal.objects.get(pk=preview.json()['id']).receipt)
        self.assertFalse(CRMDeal.objects.filter(training_session=session).exists())
        self.assertEqual(TrainingSession.objects.get(pk=session.pk).progress, before)
        self.assertTrue(Task.objects.filter(pk=second.pk).exists())
        self.check(case_id, 'followup')
        current = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual(current.status_code, 200, current.content)
        preview = self.client.post('/api/operations/preview/', current.json()['payload'],
                                   content_type='application/json')
        self.assertEqual(preview.status_code, 200, preview.content)
        observation = training_service.observations(policy, self.marker, case_id, session)
        reordered = deepcopy(observation[2])
        followup = next(row for row in reordered if row['id'] == 'followup')
        followup['observed']['tasks'].reverse()
        followup['_source_ids']['tasks'].reverse()
        followup['_source_ids']['assignee_refs'].reverse()
        with patch('training.service.observations', return_value=(observation[0], observation[1], reordered)):
            accepted = self.client.post('/api/operations/confirm/',
                {'proposal_id': preview.json()['id'], 'confirmed': True},
                content_type='application/json')
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertEqual(CRMDeal.objects.filter(training_session=session).count(), 1)

    def test_d08_f02_06(self):
        case_id = 'BOS3-CASE-03'
        started = self.start(case_id)
        self.check(case_id, 'invoice', '6400')
        source = self.marker['source_map'][case_id]
        task = Task.objects.create(title='Контакт', sales_order_id=source['order_id'],
                                   assignee_employee_id=source['owner_id'], deadline='2026-10-01')
        self.check(case_id, 'followup')
        session = TrainingSession.objects.get(public_id=started['session_id'])
        policy = Policy.for_user(self.owner)
        draft = crm_projections.draft(policy, started['session_id'], case_id)
        refs = crm_commands._case_sources(policy, self.marker, session, case_id)
        deal = CRMDeal.objects.create(training_session=session, case_id=case_id,
            stable_handoff_hash=draft['payload']['stable_handoff_hash'],
            counterparty=refs['counterparty'], owner=refs['owner'], sales_order=refs['order'],
            invoice=refs['invoice'], title=draft['payload']['title'],
            next_action=draft['payload']['next_action'], stage=draft['payload']['stage'])
        Task.objects.filter(pk=task.pk).update(archived_at=timezone.now())
        TrainingSession.objects.filter(pk=session.pk).update(progress={'invoice': {'stamp': 'legacy'}},
                                                           status='completed')
        with patch('crm.projections.case03_handoff_ready', side_effect=AssertionError('existing draft gate')):
            existing = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual(existing.status_code, 200, existing.content)
        self.assertEqual(existing.json()['deal']['id'], deal.pk)
        with patch('crm.commands.case03_handoff_ready', side_effect=AssertionError('existing preview gate')):
            preview = self.client.post('/api/operations/preview/', draft['payload'],
                                       content_type='application/json')
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(preview.json()['state'], 'existing')
        self.assertEqual(CRMDeal.objects.count(), 1)

    def test_d08_f02_07(self):
        case_id = 'BOS3-CASE-03'
        started = self.start(case_id)
        self.check(case_id, 'invoice', '6400')
        source = self.marker['source_map'][case_id]
        task = Task.objects.create(title='Контакт', sales_order_id=source['order_id'],
                                   assignee_employee_id=source['owner_id'], deadline='2026-10-01')
        self.check(case_id, 'followup')
        draft = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id}).json()
        preview = self.client.post('/api/operations/preview/', draft['payload'], content_type='application/json')
        confirmed = self.client.post('/api/operations/confirm/',
            {'proposal_id': preview.json()['id'], 'confirmed': True}, content_type='application/json')
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        session = TrainingSession.objects.get(public_id=started['session_id'])
        TrainingSession.objects.filter(pk=session.pk).update(progress={'invoice': {'stamp': 'legacy'}})
        Task.objects.filter(pk=task.pk).update(archived_at=timezone.now())
        with patch('crm.commands.prepare', side_effect=AssertionError('stored receipt replayed')):
            replay = self.client.post('/api/operations/confirm/',
                {'proposal_id': preview.json()['id'], 'confirmed': True}, content_type='application/json')
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.json()['deal_id'], confirmed.json()['deal_id'])
        self.assertEqual(CRMDeal.objects.count(), 1)

    def test_d08_f02_08(self):
        started = self.start('BOS3-CASE-03')
        proposal = ActionProposal.objects.create(
            user=self.owner, session_key=self.client.session.session_key, role='ceo',
            payload={'action': 'crm_handoff', 'training_session_id': started['session_id']},
            fingerprint='synthetic', expires_at=timezone.now() + timedelta(minutes=10),
            receipt={'schema': 'crm.deal-receipt.v1', 'state': 'succeeded', 'deal_id': 999999})
        foreign_user = get_user_model().objects.create_user(username='foreign-d08', password='synthetic-password')
        Group.objects.get(name='ceo').user_set.add(foreign_user)
        foreign = Client()
        foreign.force_login(foreign_user)
        wrong_user = foreign.post('/api/operations/confirm/',
            {'proposal_id': str(proposal.pk), 'confirmed': True}, content_type='application/json')
        self.assertEqual(wrong_user.status_code, 403, wrong_user.content)
        other_session = Client()
        other_session.force_login(self.owner)
        wrong_session = other_session.post('/api/operations/confirm/',
            {'proposal_id': str(proposal.pk), 'confirmed': True}, content_type='application/json')
        self.assertEqual(wrong_session.status_code, 403, wrong_session.content)
        self.owner.groups.remove(Group.objects.get(name='ceo'))
        self.owner.groups.add(Group.objects.get_or_create(name='manager')[0])
        wrong_role = self.client.post('/api/operations/confirm/',
            {'proposal_id': str(proposal.pk), 'confirmed': True}, content_type='application/json')
        self.assertEqual(wrong_role.status_code, 403, wrong_role.content)

    def test_d08_f02_09(self):
        case_id = 'BOS3-CASE-03'
        started = self.start(case_id)
        session = TrainingSession.objects.get(public_id=started['session_id'])
        policy = Policy.for_user(self.owner)
        with patch('crm.projections.case03_handoff_ready', return_value=True):
            payload = crm_projections.draft(policy, started['session_id'], case_id)['payload']
        refs = crm_commands._case_sources(policy, self.marker, session, case_id)
        deal = CRMDeal.objects.create(training_session=session, case_id=case_id,
            stable_handoff_hash=crm_commands._handoff_hash(self.marker, session, case_id, refs),
            counterparty=refs['counterparty'], owner=refs['owner'], sales_order=refs['order'],
            invoice=refs['invoice'], title='Контакт', next_action='Передзвонити', stage='collection')
        proposal = ActionProposal.objects.create(user=self.owner, session_key=self.client.session.session_key,
            role='ceo', payload=payload,
            fingerprint='synthetic', expires_at=timezone.now() + timedelta(minutes=10),
            receipt={'schema': 'crm.deal-receipt.v1', 'state': 'succeeded',
                     'action': 'crm_handoff', 'deal_id': deal.pk})
        with patch.object(Policy, 'crm_deals', return_value=CRMDeal.objects.none()):
            denied = self.client.post('/api/operations/confirm/',
                {'proposal_id': str(proposal.pk), 'confirmed': True}, content_type='application/json')
        self.assertEqual(denied.status_code, 403, denied.content)
        self.assertEqual(denied.json(), {'error': 'CRM-квитанція більше недоступна.'})
        missing_activity = ActionProposal.objects.create(
            user=self.owner, session_key=self.client.session.session_key, role='ceo',
            payload=payload, fingerprint='synthetic', expires_at=timezone.now() + timedelta(minutes=10),
            receipt={'schema': 'crm.deal-receipt.v1', 'state': 'succeeded',
                     'action': 'crm_handoff', 'deal_id': deal.pk, 'activity_id': 999999999})
        unavailable = self.client.post('/api/operations/confirm/',
            {'proposal_id': str(missing_activity.pk), 'confirmed': True}, content_type='application/json')
        self.assertEqual(unavailable.status_code, 404, unavailable.content)
        self.assertEqual(unavailable.json(), {'error': 'Запис не знайдено в поточній базі.'})

    def test_d08_f02_10(self):
        case_id = 'BOS3-CASE-03'
        started = self.start(case_id)
        session = TrainingSession.objects.get(public_id=started['session_id'])
        with patch('crm.projections.case03_handoff_ready', return_value=True):
            payload = crm_projections.draft(Policy.for_user(self.owner), started['session_id'], case_id)['payload']
        foreign_user = get_user_model().objects.create_user(username='foreign-d08-owner',
                                                              password='synthetic-password')
        Group.objects.get(name='ceo').user_set.add(foreign_user)
        foreign = Client()
        foreign.force_login(foreign_user)
        denied = foreign.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual(denied.status_code, 403, denied.content)
        for field, changed in (('user_id', foreign_user.pk), ('role', 'manager'),
                               ('installation_id', 'other-installation'),
                               ('fixture_id', 'other-fixture'), ('fixture_hash', '0' * 64)):
            with self.subTest(session_field=field):
                original = getattr(session, field)
                TrainingSession.objects.filter(pk=session.pk).update(**{field: changed})
                with patch('crm.projections.case03_handoff_ready',
                           side_effect=AssertionError('session before Q02')):
                    wrong_draft = self.client.get(
                        f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
                with patch('crm.commands.case03_handoff_ready',
                           side_effect=AssertionError('session before Q02')):
                    wrong_preview = self.client.post('/api/operations/preview/', payload,
                        content_type='application/json')
                self.assertEqual(wrong_draft.status_code, 403, wrong_draft.content)
                self.assertEqual(wrong_preview.status_code, 403, wrong_preview.content)
                TrainingSession.objects.filter(pk=session.pk).update(**{field: original})
        with patch('crm.commands.case03_handoff_ready', side_effect=AssertionError('prior gate')):
            for change in ({'stable_handoff_hash': '0' * 64}, {'order_id': payload['order_id'] + 1},
                           {'invoice_id': payload['invoice_id'] + 1},
                           {'owner_id': payload['owner_id'] + 1}):
                preview = self.client.post('/api/operations/preview/', {**payload, **change},
                                           content_type='application/json')
                self.assertEqual(preview.status_code, 403, preview.content)
        wrong_case = self.client.get(f"/api/crm/handoff/{started['session_id']}/",
                                     {'case_id': 'BOS3-CASE-02'})
        self.assertEqual(wrong_case.status_code, 403, wrong_case.content)
        with patch('crm.commands.case03_handoff_ready', side_effect=AssertionError('case before Q02')):
            wrong_post_case = self.client.post('/api/operations/preview/',
                {**payload, 'case_id': 'BOS3-CASE-02'}, content_type='application/json')
        self.assertEqual(wrong_post_case.status_code, 403, wrong_post_case.content)
        missing_marker = deepcopy(self.marker)
        missing_marker['source_map'][case_id]['order_id'] = 999999999
        with patch('crm.commands._marker', return_value=missing_marker), patch(
                'crm.commands.case03_handoff_ready', side_effect=AssertionError('source before Q02')):
            missing = self.client.post('/api/operations/preview/', payload, content_type='application/json')
        self.assertEqual(missing.status_code, 404, missing.content)
        policy = Policy.for_user(self.owner)
        refs = crm_commands._case_sources(policy, self.marker, session, case_id)
        other_owner = Employee.objects.exclude(pk=refs['owner'].pk).first()
        self.assertIsNotNone(other_owner)
        wrong_owner_refs = {**refs, 'owner': other_owner}
        with patch('crm.commands._marker', return_value=self.marker), patch(
                'crm.commands._case_sources', return_value=wrong_owner_refs), patch.object(
                Policy, 'ceo', property(lambda self: False)), patch(
                'crm.commands.case03_handoff_ready', side_effect=AssertionError('owner before Q02')):
            owner_denied = self.client.post('/api/operations/preview/', payload,
                                            content_type='application/json')
        self.assertEqual(owner_denied.status_code, 403, owner_denied.content)

    def test_d08_f02_11(self):
        case_id = 'BOS3-CASE-03'
        started = self.start(case_id)
        self.check(case_id, 'invoice', '6400')
        source = self.marker['source_map'][case_id]
        Task.objects.create(title='Контакт', sales_order_id=source['order_id'],
                            assignee_employee_id=source['owner_id'], deadline='2026-10-01')
        self.check(case_id, 'followup')
        ready = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual(ready.status_code, 200, ready.content)
        payload = ready.json()['payload']
        admitted = self.client.post('/api/operations/preview/', payload,
                                    content_type='application/json')
        self.assertEqual(admitted.status_code, 200, admitted.content)
        session = TrainingSession.objects.get(public_id=started['session_id'])
        TrainingSession.objects.filter(pk=session.pk).update(status='completed', current_step='crm',
                                                           progress={'invoice': {'stamp': 'legacy'}})
        with patch('crm.projections.case03_handoff_ready', side_effect=AssertionError('completed draft gate')):
            draft = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual(draft.status_code, 403, draft.content)
        with patch('crm.commands.case03_handoff_ready', side_effect=AssertionError('completed prepare gate')):
            preview = self.client.post('/api/operations/preview/', payload, content_type='application/json')
        self.assertEqual(preview.status_code, 403, preview.content)
        with patch('crm.commands.case03_handoff_ready', side_effect=AssertionError('completed confirm gate')):
            confirm = self.client.post('/api/operations/confirm/',
                {'proposal_id': admitted.json()['id'], 'confirmed': True},
                content_type='application/json')
        self.assertEqual(confirm.status_code, 403, confirm.content)
        self.assertIsNone(ActionProposal.objects.get(pk=admitted.json()['id']).receipt)
        self.assertEqual(TrainingSession.objects.get(pk=session.pk).progress,
                         {'invoice': {'stamp': 'legacy'}})
        self.assertFalse(CRMDeal.objects.filter(training_session=session).exists())

    def test_d08_f02_12(self):
        for case_id in ('BOS3-CASE-01', 'BOS3-CASE-02'):
            started = self.start(case_id)
            with patch('crm.projections.case03_handoff_ready',
                       side_effect=AssertionError('other case draft gate')):
                draft = self.client.get(f"/api/crm/handoff/{started['session_id']}/",
                                        {'case_id': case_id})
            self.assertEqual(draft.status_code, 200, draft.content)
            with patch('crm.commands.case03_handoff_ready',
                       side_effect=AssertionError('other case preview gate')):
                preview = self.client.post('/api/operations/preview/', draft.json()['payload'],
                                           content_type='application/json')
            self.assertEqual(preview.status_code, 200, preview.content)
            with patch('crm.commands.case03_handoff_ready',
                       side_effect=AssertionError('other case confirm gate')):
                confirm = self.client.post('/api/operations/confirm/',
                    {'proposal_id': preview.json()['id'], 'confirmed': True},
                    content_type='application/json')
            self.assertEqual(confirm.status_code, 200, confirm.content)
            with patch('crm.projections.case03_handoff_ready',
                       side_effect=AssertionError('other case recovery gate')):
                recovered = self.client.get(f"/api/crm/handoff/{started['session_id']}/",
                                            {'case_id': case_id})
            self.assertEqual(recovered.status_code, 200, recovered.content)
            self.assertTrue(recovered.json()['existing'])
            with patch('crm.commands.case03_handoff_ready',
                       side_effect=AssertionError('other case existing gate')):
                existing = self.client.post('/api/operations/preview/', draft.json()['payload'],
                                            content_type='application/json')
            self.assertEqual(existing.status_code, 200, existing.content)
            self.assertEqual(existing.json()['state'], 'existing')
        deal = CRMDeal.objects.get(case_id='BOS3-CASE-01')
        with patch('crm.commands.case03_handoff_ready',
                   side_effect=AssertionError('unrelated update gate')):
            update = self.client.post('/api/operations/preview/',
                {'action': 'crm_deal_update', 'deal_id': deal.pk, 'reason': 'Зміна контакту',
                 'next_action': 'Передзвонити після уточнення строку.'},
                content_type='application/json')
        self.assertEqual(update.status_code, 200, update.content)
        with patch('crm.commands.case03_handoff_ready',
                   side_effect=AssertionError('unrelated confirm gate')):
            applied = self.client.post('/api/operations/confirm/',
                {'proposal_id': update.json()['id'], 'confirmed': True},
                content_type='application/json')
        self.assertEqual(applied.status_code, 200, applied.content)
        deal.refresh_from_db()
        self.assertEqual(deal.next_action, 'Передзвонити після уточнення строку.')

    def test_d08_f02_13(self):
        case_id = 'BOS3-CASE-03'
        started = self.start(case_id)
        self.check(case_id, 'invoice', '6400')
        source = self.marker['source_map'][case_id]
        Task.objects.create(title='Контакт', sales_order_id=source['order_id'],
                            assignee_employee_id=source['owner_id'], deadline='2026-10-01')
        self.check(case_id, 'followup')
        session = TrainingSession.objects.get(public_id=started['session_id'])
        before = (session.status, session.current_step, deepcopy(session.progress))
        with patch('erp.service.write_lock', side_effect=AssertionError('GET mutex')), patch.object(
                TrainingSession, 'save', side_effect=AssertionError('GET session save')), patch.object(
                CRMDeal, 'save', side_effect=AssertionError('GET deal save')), patch.object(
                QuerySet, 'select_for_update', side_effect=AssertionError('GET row lock')):
            draft = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
            self.assertTrue(training_service.case03_handoff_ready(Policy.for_user(self.owner),
                self.marker, session, source['order_id'], source['invoice_id']))
        self.assertEqual(draft.status_code, 200, draft.content)
        session.refresh_from_db()
        self.assertEqual((session.status, session.current_step, session.progress), before)
        calls = []
        from erp.service import write_lock as original_write_lock
        original_session = crm_commands._session
        original_sources = crm_commands._case_sources
        original_gate = crm_commands.case03_handoff_ready
        original_existing = CRMDeal.objects.select_for_update
        def observed_session(*args, **kwargs):
            calls.append('session')
            return original_session(*args, **kwargs)
        def observed_lock(*args, **kwargs):
            calls.append('mutex')
            return original_write_lock(*args, **kwargs)
        def observed_sources(*args, **kwargs):
            calls.append('sources')
            return original_sources(*args, **kwargs)
        def observed_gate(*args, **kwargs):
            calls.append('gate')
            return original_gate(*args, **kwargs)
        def observed_existing(*args, **kwargs):
            calls.append('existing')
            return original_existing(*args, **kwargs)
        with patch('erp.service.write_lock', side_effect=observed_lock), patch(
                'crm.commands._session', side_effect=observed_session), patch(
                'crm.commands._case_sources', side_effect=observed_sources), patch(
                'crm.commands.case03_handoff_ready', side_effect=observed_gate), patch.object(
                CRMDeal.objects, 'select_for_update', side_effect=observed_existing):
            preview = self.client.post('/api/operations/preview/', draft.json()['payload'],
                                       content_type='application/json')
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(calls, ['mutex', 'session', 'sources', 'existing', 'gate'])
        calls.clear()
        with patch('erp.service.write_lock', side_effect=observed_lock), patch(
                'crm.commands._session', side_effect=observed_session), patch(
                'crm.commands._case_sources', side_effect=observed_sources), patch(
                'crm.commands.case03_handoff_ready', side_effect=observed_gate), patch.object(
                CRMDeal.objects, 'select_for_update', side_effect=observed_existing):
            confirm = self.client.post('/api/operations/confirm/',
                {'proposal_id': preview.json()['id'], 'confirmed': True},
                content_type='application/json')
        self.assertEqual(confirm.status_code, 200, confirm.content)
        self.assertEqual(calls, ['mutex', 'session', 'sources', 'existing', 'gate'])
        with patch('crm.commands.prepare', side_effect=AssertionError('receipt before prepare')):
            replay = self.client.post('/api/operations/confirm/',
                {'proposal_id': preview.json()['id'], 'confirmed': True},
                content_type='application/json')
        self.assertEqual(replay.status_code, 200, replay.content)

    def test_d08_f02_14(self):
        case_id = 'BOS3-CASE-03'
        started = self.start(case_id)
        self.check(case_id, 'invoice', '6400')
        source = self.marker['source_map'][case_id]
        Task.objects.create(title='Контакт', sales_order_id=source['order_id'],
                            assignee_employee_id=source['owner_id'], deadline='2026-10-01')
        self.check(case_id, 'followup')
        expected = {'error': 'Спочатку перевірте попередній крок.'}
        ready = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual(ready.status_code, 200, ready.content)
        payload = ready.json()['payload']
        preview = self.client.post('/api/operations/preview/', payload, content_type='application/json')
        self.assertEqual(preview.status_code, 200, preview.content)
        session = TrainingSession.objects.get(public_id=started['session_id'])
        valid_progress = deepcopy(session.progress)
        TrainingSession.objects.filter(pk=session.pk).update(progress={'invoice': {'stamp': 'stale'}})
        draft = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual((draft.status_code, draft.json()), (422, expected))
        denied_preview = self.client.post('/api/operations/preview/', payload,
                                          content_type='application/json')
        self.assertEqual((denied_preview.status_code, denied_preview.json()), (422, expected))
        confirm = self.client.post('/api/operations/confirm/',
            {'proposal_id': preview.json()['id'], 'confirmed': True}, content_type='application/json')
        self.assertEqual((confirm.status_code, confirm.json()), (422, expected))
        self.assertIsNone(ActionProposal.objects.get(pk=preview.json()['id']).receipt)
        self.assertFalse(CRMDeal.objects.exists())
        self.assertEqual(TrainingSession.objects.get(pk=session.pk).progress, {'invoice': {'stamp': 'stale'}})
        bad_hash = self.client.post('/api/operations/preview/',
            {**payload, 'stable_handoff_hash': '0' * 64}, content_type='application/json')
        self.assertEqual(bad_hash.status_code, 403, bad_hash.content)
        missing = self.client.get('/api/crm/handoff/00000000-0000-0000-0000-000000000001/',
                                  {'case_id': case_id})
        self.assertEqual(missing.status_code, 404, missing.content)
        TrainingSession.objects.filter(pk=session.pk).update(progress=valid_progress)
        ActionProposal.objects.filter(pk=preview.json()['id']).update(
            expires_at=timezone.now() - timedelta(seconds=1))
        expired = self.client.post('/api/operations/confirm/',
            {'proposal_id': preview.json()['id'], 'confirmed': True}, content_type='application/json')
        self.assertEqual(expired.status_code, 409, expired.content)

    def test_d08_f02_15(self):
        case_id = 'BOS3-CASE-03'
        source = self.marker['source_map'][case_id]
        from operations.models import Invoice
        invoice = Invoice.objects.get(pk=source['invoice_id'])
        invoice.paid = invoice.amount
        invoice.save(update_fields=['paid'])
        started = self.start(case_id)
        self.check(case_id, 'invoice', '0')
        task = Task.objects.create(title='Контакт без результату', sales_order_id=source['order_id'],
                                   assignee_employee_id=source['owner_id'], deadline='2020-01-01',
                                   status='active', result=None)
        self.check(case_id, 'followup')
        session = TrainingSession.objects.get(public_id=started['session_id'])
        policy = Policy.for_user(self.owner)
        self.assertTrue(training_service.case03_handoff_ready(
            policy, self.marker, session, source['order_id'], source['invoice_id']))
        draft = self.client.get(f"/api/crm/handoff/{started['session_id']}/", {'case_id': case_id})
        self.assertEqual(draft.status_code, 200, draft.content)
        self.assertEqual(draft.json()['schema'], 'crm.handoff-draft.v1')
        self.assertEqual(set(draft.json()['payload']), {
            'action', 'training_session_id', 'case_id', 'stable_handoff_hash',
            'counterparty_id', 'owner_id', 'order_id', 'invoice_id', 'title',
            'next_action', 'stage', 'contact_name', 'contact_role', 'contact_email'})
        preview = self.client.post('/api/operations/preview/', draft.json()['payload'],
                                   content_type='application/json')
        self.assertEqual(preview.status_code, 200, preview.content)
        confirm = self.client.post('/api/operations/confirm/',
            {'proposal_id': preview.json()['id'], 'confirmed': True},
            content_type='application/json')
        self.assertEqual(confirm.status_code, 200, confirm.content)
        self.assertEqual((confirm.json()['schema'], confirm.json()['state']),
                         ('crm.deal-receipt.v1', 'succeeded'))
        self.assertEqual(CRMDeal.objects.filter(training_session=session).count(), 1)
        Task.objects.filter(pk=task.pk).update(status='done', result='Закрито без оплати')
        self.assertTrue(training_service.case03_handoff_ready(
            policy, self.marker, session, source['order_id'], source['invoice_id']))
        self.assertFalse(training_service.case03_handoff_ready(
            policy, self.marker, session, None, source['invoice_id']))
        self.assertFalse(training_service.case03_handoff_ready(
            policy, self.marker, session, source['order_id'], None))
        self.assertFalse(training_service.case03_handoff_ready(
            policy, self.marker, session, source['order_id'] + 1, source['invoice_id']))
        self.assertFalse(training_service.case03_handoff_ready(
            policy, self.marker, session, source['order_id'], source['invoice_id'] + 1))
