"""Synthetic unit coverage for the explicit BoS 3 development-control scope."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name('bos_control.py')
SPEC = importlib.util.spec_from_file_location('bos_control_under_test', MODULE_PATH)
bos_control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bos_control)


PIN = 'f55a15de4006d10c0d7c65f8a2ca8499fbb99819'
RUNTIME = '33d7d387aa582c04339a91ae94361948ea67904c'
ALTERNATE_PIN = 'a753a590727344b73f2c79e142c4c8ec6cc89c0d'


class Bos3ControlTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.docs = root / 'docs' / 'orchestration'
        self.bos3 = self.docs / 'bos3'
        self.bos3.mkdir(parents=True)
        self.root_patch = mock.patch.object(bos_control, 'ROOT', root)
        self.docs_patch = mock.patch.object(bos_control, 'DOCS', self.docs)
        self.bos3_patch = mock.patch.object(bos_control, 'BOS3_DOCS', self.bos3)
        self.root_patch.start()
        self.docs_patch.start()
        self.bos3_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.docs_patch.stop)
        self.addCleanup(self.bos3_patch.stop)
        (self.docs / 'CONTEXT_UA.md').write_text('legacy context\n', encoding='utf-8')
        (self.docs / 'PLAN_UA.md').write_text('legacy plan\n', encoding='utf-8')
        (self.bos3 / 'TEAM_CURRENT_RU.md').write_text('bos3 context\n', encoding='utf-8')
        (self.bos3 / 'ACTIVE_WORK_PLAN_RU.md').write_text('bos3 plan\n', encoding='utf-8')

    def state(self):
        return {
            'candidate_version': '0.3.0-dev.3',
            'product_candidate_commit': PIN,
            'candidate_manifest': 'LIGHT_PREVIEW_CANDIDATE.json',
            'delivered_runtime_version': '0.3.0-dev.1',
            'runtime_source_commit': RUNTIME,
            'readiness': {'technical_ready': False, 'pilot_allowed': False, 'mvp': False},
            'light_preview_delivery_permission': {
                'status': bos_control.PENDING_DELIVERY_STATUS,
                'exact_product_pin': PIN,
            },
            'cards': [
                {'id': 'B30-PREVIEW-DELIVERY', 'status': 'BLOCKED',
                 'owner': 'author', 'reviewer': 'reviewer'},
            ],
            'historical_cards_current_assignments': False,
            'historical_cards': [{'id': 'B30-04D', 'status': 'HISTORICAL'}],
            'weekly_execution': self.weekly_execution(),
        }

    def weekly_execution(self):
        return {
            'deadline_local': '2026-10-04T23:59:00+02:00',
            'timezone': 'Europe/Berlin',
            'changes_after_deadline_allowed': False,
            'workflow': 'DEVELOPMENT_WORKFLOW_RU.md',
            'goal_owner_thread_id': '01a0bf0f-a9e4-7631-87e1-bb1aed03f174',
            'max_active_workers': 4,
            'integrator_count': 1,
            'next_product_card': 'B30-PREVIEW-DELIVERY',
            'next_product_status': 'BLOCKED',
            'decision_owner': 'owner',
            'post_deadline_actions': ['read', 'report', 'pause_automation'],
            'priorities': [
                {'rank': 1, 'status': 'BLOCKED', 'blocker': 'owner decision',
                 'decision_owner': 'owner', 'next_action': 'wait'},
                {'rank': 2, 'status': 'PARTIAL'},
                {'rank': 3, 'status': 'DEFERRED'},
                {'rank': 4, 'status': 'DEFERRED'},
                {'rank': 5, 'status': 'DEFERRED'},
            ],
        }

    def write_fixture(self, state=None, candidate=None, runtime=None):
        state = self.state() if state is None else state
        candidate = candidate if candidate is not None else {
            'product_commit': PIN,
            'version': '0.3.0-dev.3',
            'readiness': {'technical_ready': False, 'pilot_allowed': False, 'mvp': False},
        }
        runtime = runtime if runtime is not None else {
            'source_commit': RUNTIME,
            'version': '0.3.0-dev.1',
            'technical_ready': False,
            'pilot_allowed': False,
            'mvp': False,
        }
        for name, value in (
            ('CONTROL_STATE.json', state),
            ('LOCAL_RUNTIME_RECEIPT.json', runtime),
        ):
            (self.bos3 / name).write_text(json.dumps(value), encoding='utf-8')
        manifest_name = state.get('candidate_manifest')
        if isinstance(manifest_name, str) and bos_control.SAFE_MANIFEST_NAME.fullmatch(manifest_name):
            (self.bos3 / manifest_name).write_text(json.dumps(candidate), encoding='utf-8')

    def validate_result(self, state=None, candidate=None, runtime=None):
        self.write_fixture(state, candidate, runtime)
        return bos_control.validate_bos3()

    def test_scope_routes_context_to_bos3_not_legacy(self):
        self.write_fixture()
        output = io.StringIO()
        with mock.patch.object(sys, 'argv', ['bos_control.py', '--scope', 'bos3', 'context']):
            with contextlib.redirect_stdout(output):
                self.assertEqual(bos_control.main(), 0)
        self.assertEqual(output.getvalue(), 'bos3 context\n')

    def test_historical_card_is_not_addressable(self):
        self.write_fixture()
        parser = argparse.ArgumentParser()
        args = argparse.Namespace(command='card', task='B30-04D')
        with self.assertRaises(SystemExit) as raised:
            bos_control.bos3_main(parser, args)
        self.assertEqual(raised.exception.code, 2)

    def test_valid_blocked_state_passes_with_weekly_contract(self):
        self.assertEqual(self.validate_result(self.state())['result'], 'PASS')

    def test_valid_pending_state_without_weekly_contract(self):
        state = self.state()
        state.pop('weekly_execution')
        self.write_fixture(state)
        self.assertEqual(bos_control.validate_bos3()['result'], 'PASS')
        status = bos_control.bos3_status()
        self.assertIsNone(status['cutoff_reached'])
        self.assertFalse(status['execution_authorized_by_tool'])

    def test_product_pin_mismatch_fails(self):
        state = self.state()
        state['product_candidate_commit'] = 'different-pin'
        result = self.validate_result(state)
        self.assertEqual(result['result'], 'FAIL')
        self.assertIn('Product candidate pin differs from manifest', result['errors'])

    def test_state_selected_alternate_manifest_is_used(self):
        state = self.state()
        state['candidate_manifest'] = 'TASK_CARD_DEV6_CANDIDATE.json'
        state['candidate_version'] = '0.3.0-dev.6'
        state['product_candidate_commit'] = ALTERNATE_PIN
        state['cards'][0]['status'] = 'DONE'
        state['cards'][0]['result_commit'] = PIN
        state['light_preview_delivery_permission'] = {
            'status': bos_control.CONSUMED_DELIVERY_STATUS,
            'exact_product_pin': PIN,
            'authorization_record': {
                'owner_message_ref': 'historic-owner-message',
                'exact_product_pin': PIN,
                'scope': 'owner_local_update_and_entry_only',
            },
            'consumed_attempts': 1,
            'result_record': 'evidence/historic-one-shot.json',
            'outcome': 'PASS_SCOPED',
        }
        state['weekly_execution']['next_product_card'] = None
        state['weekly_execution']['next_product_status'] = None
        candidate = {
            'product_commit': ALTERNATE_PIN,
            'version': '0.3.0-dev.6',
            'readiness': {'technical_ready': False, 'pilot_allowed': False, 'mvp': False},
        }
        self.assertEqual(self.validate_result(state, candidate)['result'], 'PASS')

    def test_missing_selected_manifest_fails(self):
        state = self.state()
        state['candidate_manifest'] = 'MISSING_CANDIDATE.json'
        self.write_fixture(state)
        (self.bos3 / state['candidate_manifest']).unlink()
        result = bos_control.validate_bos3()
        self.assertEqual(result['result'], 'FAIL')
        self.assertIn('Selected candidate manifest is unavailable or invalid', result['errors'])

    def test_unsafe_selected_manifest_fails_without_reading_it(self):
        state = self.state()
        state['candidate_manifest'] = '../LIGHT_PREVIEW_CANDIDATE.json'
        result = self.validate_result(state)
        self.assertEqual(result['result'], 'FAIL')
        self.assertIn('Candidate manifest must be a safe JSON filename', result['errors'])

    def test_nonobject_selected_manifest_fails(self):
        state = self.state()
        state['candidate_manifest'] = 'NONOBJECT_CANDIDATE.json'
        self.write_fixture(state)
        (self.bos3 / state['candidate_manifest']).write_text('[]', encoding='utf-8')
        result = bos_control.validate_bos3()
        self.assertEqual(result['result'], 'FAIL')
        self.assertIn('Selected candidate manifest must be a JSON object', result['errors'])

    def test_selected_manifest_pin_mismatch_fails(self):
        state = self.state()
        state['candidate_manifest'] = 'TASK_CARD_DEV6_CANDIDATE.json'
        candidate = {
            'product_commit': ALTERNATE_PIN,
            'version': '0.3.0-dev.3',
            'readiness': {'technical_ready': False, 'pilot_allowed': False, 'mvp': False},
        }
        result = self.validate_result(state, candidate)
        self.assertEqual(result['result'], 'FAIL')
        self.assertIn('Product candidate pin differs from manifest', result['errors'])

    def test_missing_pins_cannot_false_pass(self):
        state = self.state()
        state['product_candidate_commit'] = None
        state['runtime_source_commit'] = None
        candidate = {
            'product_commit': None,
            'version': '0.3.0-dev.3',
            'readiness': {'technical_ready': False, 'pilot_allowed': False, 'mvp': False},
        }
        runtime = {
            'source_commit': None,
            'version': '0.3.0-dev.1',
            'technical_ready': False,
            'pilot_allowed': False,
            'mvp': False,
        }
        result = self.validate_result(state, candidate, runtime)
        self.assertEqual(result['result'], 'FAIL')
        self.assertIn('Invalid full commit pin: state.product_candidate_commit', result['errors'])
        self.assertIn('Invalid full commit pin: candidate.product_commit', result['errors'])

    def test_readiness_true_fails(self):
        state = self.state()
        state['readiness']['pilot_allowed'] = True
        result = self.validate_result(state)
        self.assertEqual(result['result'], 'FAIL')
        self.assertIn('Readiness must stay false: state.pilot_allowed', result['errors'])

    def test_duplicate_current_card_id_fails(self):
        state = self.state()
        state['cards'].append(dict(state['cards'][0]))
        result = self.validate_result(state)
        self.assertEqual(result['result'], 'FAIL')
        self.assertIn('Duplicate active card IDs', result['errors'])

    def test_active_owner_reviewer_mismatch_fails(self):
        state = self.state()
        state['cards'][0]['status'] = 'IN_PROGRESS'
        state['cards'][0]['reviewer'] = 'author'
        result = self.validate_result(state)
        self.assertEqual(result['result'], 'FAIL')
        self.assertIn('Active card owner and reviewer match: B30-PREVIEW-DELIVERY', result['errors'])

    def test_authorized_record_is_valid_without_action(self):
        state = self.state()
        state['light_preview_delivery_permission'] = {
            'status': bos_control.AUTHORIZED_DELIVERY_STATUS,
            'authorization_record': {
                'owner_message_ref': 'owner-message-1',
                'exact_product_pin': PIN,
                'scope': 'owner_local_update_and_entry_only',
            },
        }
        self.assertEqual(self.validate_result(state)['result'], 'PASS')

    def test_status_never_authorizes_delivery(self):
        state = self.state()
        state['light_preview_delivery_permission'] = {
            'status': bos_control.AUTHORIZED_DELIVERY_STATUS,
            'authorization_record': {
                'owner_message_ref': 'owner-message-1',
                'exact_product_pin': PIN,
                'scope': 'owner_local_update_and_entry_only',
            },
        }
        self.write_fixture(state)
        status = bos_control.bos3_status()
        self.assertFalse(status['execution_authorized_by_tool'])
        self.assertTrue(status['requires_live_owner_instruction'])

    def test_consumed_record_is_valid_without_automatic_transition(self):
        state = self.state()
        state['cards'][0]['status'] = 'DONE'
        state['cards'][0]['result_commit'] = PIN
        state['light_preview_delivery_permission'] = {
            'status': bos_control.CONSUMED_DELIVERY_STATUS,
            'exact_product_pin': PIN,
            'authorization_record': {
                'owner_message_ref': 'owner-message-1',
                'exact_product_pin': PIN,
                'scope': 'owner_local_update_and_entry_only',
            },
            'consumed_attempts': 1,
            'result_record': 'evidence/one-shot.json',
            'outcome': 'PASS_SCOPED',
        }
        state['weekly_execution']['next_product_card'] = None
        state['weekly_execution']['next_product_status'] = None
        self.assertEqual(self.validate_result(state)['result'], 'PASS')

    def test_pending_delivery_cannot_be_ready(self):
        state = self.state()
        state['cards'][0]['status'] = 'READY'
        state['weekly_execution']['next_product_status'] = 'READY'
        result = self.validate_result(state)
        self.assertEqual(result['result'], 'FAIL')
        self.assertIn('Pending preview delivery card must stay BLOCKED', result['errors'])

    def test_done_priority_requires_evidence(self):
        state = self.state()
        state['weekly_execution']['priorities'][1] = {'rank': 2, 'status': 'DONE'}
        result = self.validate_result(state)
        self.assertEqual(result['result'], 'FAIL')
        self.assertIn('Done priority lacks evidence: 2', result['errors'])

    def test_cutoff_distinguishes_before_and_after_deadline(self):
        weekly = {
            'deadline_local': '2026-10-04T23:59:00+02:00',
            'timezone': 'Europe/Berlin',
        }
        before = bos_control.datetime.fromisoformat('2026-10-04T23:58:59+02:00')
        after = bos_control.datetime.fromisoformat('2026-10-05T00:00:00+02:00')
        self.assertFalse(bos_control.cutoff_reached(weekly, before))
        self.assertTrue(bos_control.cutoff_reached(weekly, after))


if __name__ == '__main__':
    unittest.main()
