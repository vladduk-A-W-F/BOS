"""Reject ambiguous JSON money/stock intentions before a proposal is stored."""
import json
from django.conf import settings
from erp.test_concurrency import ERPConcurrencyBase
from operations.models import ActionProposal


class JSONIntentBoundaryTests(ERPConcurrencyBase):
    def test_duplicate_top_level_or_nested_json_keys_do_not_create_proposals(self):
        for nested in (False, True):
            with self.subTest(nested=nested):
                fixture, payload = self.prepare('item' if nested else 'opening', 'EUR')
                raw = json.dumps(payload)
                raw = raw[:-1] + (', "external_codes": {"supplier": "A", "supplier": "B"}}'
                                  if nested else ', "quantity": "1.000"}')
                before = list(ActionProposal.objects.order_by('pk').values())
                response = self.http.post('/api/erp/preview/', raw, content_type='application/json',
                    HTTP_X_CSRFTOKEN=self.http.cookies[settings.CSRF_COOKIE_NAME].value)
                self.assertEqual(response.status_code, 422, response.content[:600])
                self.assertEqual(list(ActionProposal.objects.order_by('pk').values()), before)
                self.assert_ledger()
