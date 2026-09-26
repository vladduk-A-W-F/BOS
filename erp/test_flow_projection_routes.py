"""New route and command handoff checks only; isolated synthetic data."""
from unittest.mock import patch

from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from operations.test_access import A04SyntheticCase
from . import service, supply_options, order_settlement
from .models import Reservation
from .order_trace import ReadStateChanged


class FlowProjectionRouteTests(A04SyntheticCase):
    @property
    def supply_url(self):
        return f'/api/erp/lines/{self.line.pk}/supply-options/'

    @property
    def settlement_url(self):
        return f'/api/erp/orders/{self.order.pk}/settlement/'

    def test_reads_are_get_only_and_anonymous_is_denied(self):
        client = self.grant('ceo', 'view_document')
        for url in (self.supply_url, self.settlement_url):
            self.assertEqual(Client().get(url).status_code, 401)
            before = service.fingerprint()
            with CaptureQueriesContext(connection) as captured:
                response = client.get(url)
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()['access_revision'], response['X-BoS-Access'])
            self.assertEqual(service.fingerprint(), before)
            self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT ', 'UPDATE ', 'DELETE ')) for q in captured))
            self.assertEqual(self.post(client, url, {}).status_code, 405)

    def test_finance_ceo_only_and_restricted_supply_no_inference(self):
        for role in ('manager', 'observer'):
            client = self.grant(role, 'view_document')
            self.assertEqual(client.get(self.settlement_url).status_code, 403)
            response = client.get(self.supply_url)
            self.assertEqual(response.status_code, 200, response.content)
            body = response.json()
            self.assertEqual(body['completeness'], 'restricted')
            for key in ('reserved_usable', 'quantity_to_cover', 'available_all_locations',
                        'uncovered_after_stock', 'unallocated_expected'):
                self.assertIsNone(body['quantities'][key])
            self.assertTrue(all(row['available'] is None and row['eligible'] is None for row in body['stock']))

    def test_explicit_target_and_invalid_duplicate_query(self):
        client = self.grant('ceo', 'view_document')
        self.assertIsNone(client.get(self.supply_url).json()['target_location'])
        response = client.get(self.supply_url, {'target_location_id': self.location.pk})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['target_location']['id'], self.location.pk)
        for query in ('target_location_id=', 'target_location_id=0', 'target_location_id=-1',
                      'target_location_id=1.1', 'target_location_id=true',
                      'target_location_id=1&target_location_id=2'):
            self.assertEqual(client.get(self.supply_url + '?' + query).status_code, 422)
        self.assertEqual(client.get(self.supply_url, {'target_location_id': 99999999}).status_code, 404)

    def test_stale_and_hidden_reads_never_return_old_payload(self):
        client = self.grant('ceo', 'view_document')
        for module, url in ((supply_options, self.supply_url), (order_settlement, self.settlement_url)):
            with patch.object(module, 'build', side_effect=ReadStateChanged()):
                response = client.get(url)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(set(response.json()), {'code', 'error'})
            self.assertEqual(response.json()['code'], 'read_state_changed')
        client = self.grant('manager', 'view_document')
        for line_id in (self.hidden_order.lines.get().pk, 99999999):
            response = client.get(f'/api/erp/lines/{line_id}/supply-options/')
            self.assertEqual(response.status_code, 404)
            self.assertEqual(set(response.json()), {'error'})

    def test_supply_reserve_uses_existing_preview_confirm_and_replay(self):
        client = self.grant('ceo', 'view_document')
        self.line.quantity, self.line.shipped, self.line.invoiced = 10, 0, 0
        self.line.save()
        self.lot.quantity = 5
        self.lot.save()
        response = client.get(self.supply_url)
        self.assertEqual(response.status_code, 200, response.content)
        stock = next(row for row in response.json()['stock'] if row['lot_id'] == self.lot.pk)
        self.assertTrue(stock['eligible'])
        count = Reservation.objects.count()
        preview = self.post(client, '/api/erp/preview/', {'action': 'erp_reserve',
            'lot_id': stock['lot_id'], 'line_id': self.line.pk, 'quantity': '1.000'})
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(Reservation.objects.count(), count)
        payload = {'proposal_id': preview.json()['id'], 'confirmed': True}
        first = self.post(client, '/api/operations/confirm/', payload)
        replay = self.post(client, '/api/operations/confirm/', payload)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(first.json(), replay.json())
        self.assertEqual(Reservation.objects.count(), count + 1)
        self.assertEqual(client.get(self.supply_url).json()['quantities']['reserved_usable'], '1.000')
