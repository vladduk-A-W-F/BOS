"""Narrow author checks for CRM input contracts; execution is QA-owned."""
from django.test import SimpleTestCase

from .commands import clean


class CRMCommandContractTests(SimpleTestCase):
    def handoff(self):
        return {
            'action': 'crm_handoff',
            'training_session_id': '5cc269cf-8029-47b0-a98c-3d273b0ccf4d',
            'case_id': 'BOS3-CASE-03',
            'stable_handoff_hash': 'a' * 64,
            'counterparty_id': 1,
            'owner_id': 2,
            'order_id': 3,
            'invoice_id': 4,
            'title': 'Контроль рахунку',
            'next_action': 'Узгодити наступний контакт.',
            'stage': 'collection',
            'contact_email': 'procurement@example.invalid',
        }

    def test_handoff_accepts_only_typed_training_fields(self):
        self.assertEqual(clean(self.handoff())['case_id'], 'BOS3-CASE-03')

    def test_handoff_refuses_non_training_email(self):
        payload = self.handoff()
        payload['contact_email'] = 'person@example.com'
        with self.assertRaises(ValueError):
            clean(payload)

    def test_deal_update_requires_reason_and_change(self):
        with self.assertRaises(ValueError):
            clean({'action': 'crm_deal_update', 'deal_id': 1, 'reason': 'Уточнення'})

    def test_activity_refuses_unbounded_kind(self):
        with self.assertRaises(ValueError):
            clean({'action': 'crm_activity_update', 'deal_id': 1, 'owner_id': 2,
                   'kind': 'email', 'summary': 'Надіслати лист', 'status': 'planned'})
