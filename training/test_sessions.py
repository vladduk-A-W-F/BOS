"""Independent server-side checks for the BoS 3.0 lesson boundary.

These tests intentionally use the isolated synthetic fixture and ordinary HTTP
endpoints. They do not run browser/E2E, PostgreSQL, old training harnesses or
the historical full suites.
"""
import os
from decimal import Decimal
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings

from employees.models import Employee
from crm.models import CRMDeal
from erp.models import Lot, Movement, Production, SalesLine
from operations.models import ActionProposal, Configuration, Document
from tasks.models import Task
from training.models import TrainingSession
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
