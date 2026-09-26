"""PLAN-N1-SHIP: preserve the 60-symbol business limit and 100-symbol storage."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from erp import service
from erp.models import Event, Movement
from erp.test_concurrency import ERPConcurrencyBase as _FixtureBase, business_state
from erp.test_value_boundaries import physical_state
from operations.models import ActionProposal, Configuration


class ShippingReferenceLengthTests(_FixtureBase):
    PREVIEWS = ('/api/erp/preview/', '/api/operations/preview/')

    def post(self, path, payload):
        return self.http.post(path, json.dumps(payload, ensure_ascii=False),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=self.http.cookies[settings.CSRF_COOKIE_NAME].value)

    def state(self):
        return (physical_state(), list(Configuration.objects.order_by('pk').values()))

    def test_valid_60_business_and_100_raw_reference_round_trip(self):
        self.assertEqual(Movement._meta.get_field('reference').max_length, 100)
        for char in ('A', 'Ї', '🙂'):
            for reference in (char * 60, char * 60 + ' ' * 40, ' ' * 40 + char * 60):
                for adapter in ('dispatch', *self.PREVIEWS):
                    with self.subTest(reference=reference, adapter=adapter):
                        fixture, payload = self.prepare('ship', 'EUR')
                        payload['reference'] = reference
                        if adapter == 'dispatch':
                            receipt = service.dispatch(payload, role='ceo')
                        else:
                            before = business_state()
                            preview = self.post(adapter, payload)
                            self.assertEqual(preview.status_code, 200, preview.content)
                            self.assertEqual(business_state(), before, 'Preview wrote business rows')
                            proposal_id = preview.json()['id']
                            confirmed = self.post('/api/operations/confirm/',
                                {'proposal_id': proposal_id, 'confirmed': True})
                            self.assertEqual(confirmed.status_code, 200, confirmed.content)
                            receipt = confirmed.json()
                            self.assertEqual(receipt['state'], 'succeeded')
                            self.assertEqual(ActionProposal.objects.get(pk=proposal_id).receipt, receipt)
                            before_replay = physical_state()
                            replay = self.post('/api/operations/confirm/',
                                {'proposal_id': proposal_id, 'confirmed': True})
                            self.assertEqual(replay.status_code, 200, replay.content)
                            self.assertEqual(replay.json(), receipt)
                            self.assertEqual(physical_state(), before_replay)
                        movement = Movement.objects.get(line=fixture.line, kind='shipment')
                        self.assertEqual(movement.reference, reference)
                        self.assertEqual(receipt['reference'], reference)
                        self.assertEqual(Event.objects.get(pk=receipt['erp_event_id']).payload['reference'], reference)
                        fixture.lot.refresh_from_db()
                        fixture.line.refresh_from_db()
                        fixture.reservation.refresh_from_db()
                        self.assertEqual((fixture.lot.quantity, fixture.line.shipped, fixture.reservation.quantity),
                                         (Decimal('3'), Decimal('7'), Decimal('3')))
                        self.assertEqual((movement.quantity, movement.cost),
                                         (Decimal('-7'), Decimal('14')))

    def test_raw_101_and_business_61_refused_without_partial_shipping(self):
        for char in ('A', 'Ї', '🙂'):
            for reference, message in (
                (char * 60 + ' ' * 41, 'максимум 100 символів'),
                (' ' * 41 + char * 60, 'максимум 100 символів'),
                (char * 61, '1–60 символів'),
            ):
                for adapter in ('dispatch', *self.PREVIEWS, 'confirm'):
                    with self.subTest(reference=reference, adapter=adapter), transaction.atomic():
                        try:
                            fixture, payload = self.prepare('ship', 'EUR')
                            payload['reference'] = reference
                            proposal = None
                            if adapter == 'confirm':
                                proposal = ActionProposal.objects.create(
                                    session_key=self.http.session.session_key, user=self.user,
                                    role='ceo', payload=deepcopy(payload),
                                    fingerprint=service.fingerprint(),
                                    expires_at=timezone.now() + timedelta(minutes=10))
                            before = self.state()
                            response = None
                            error = None
                            try:
                                if adapter == 'dispatch':
                                    service.dispatch(payload, role='ceo')
                                elif adapter == 'confirm':
                                    response = self.post('/api/operations/confirm/',
                                        {'proposal_id': str(proposal.pk), 'confirmed': True})
                                else:
                                    response = self.post(adapter, payload)
                            except Exception as exc:
                                error = exc
                            after = self.state()
                            # Observe zero effects before test cleanup; this
                            # catches SQLite accepting an overlong reference.
                            self.assertEqual(after, before)
                            if adapter == 'dispatch':
                                self.assertIsInstance(error, ValueError)
                                self.assertIn(message, str(error))
                            else:
                                self.assertIsNone(error)
                                self.assertEqual(response.status_code, 422, response.content)
                                self.assertIn(message, response.json()['error'])
                        finally:
                            transaction.set_rollback(True)
