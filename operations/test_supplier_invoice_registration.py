"""Isolated S2 supplier-invoice controls; no historical suite is invoked."""
from datetime import date
from decimal import Decimal
import json
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.contrib.sessions.backends.db import SessionStore
from django.test import TestCase, override_settings
from django.conf import settings
from django.db import connection
from pathlib import Path
from django.test import RequestFactory

from boss_project.identity import IdentityDenied
from boss_project.policy import Policy
from erp.models import Event, Lot, Movement, Purchase
from operations import service
from operations.document_matching import registration
from operations.models import ActionProposal, Configuration, Document, SupplierInvoiceRegistration
from operations.views import confirm as confirm_view
from operations.test_document_matching_server import DocumentMatchingServerTests
from erp.views import document_match
from erp.order_trace import ReadStateChanged


@override_settings(BOS_DATA_MODE='working', ANTHROPIC_API_KEY='')
class SupplierInvoiceRegistrationTests(TestCase):
    # Reuse only the synthetic fixture helpers; do not inherit the historical
    # read-adapter test methods into this bounded card.
    receipt=DocumentMatchingServerTests.receipt
    document=DocumentMatchingServerTests.document

    def setUp(self):
        self.assertEqual(connection.vendor,'sqlite')
        Path(settings.MEDIA_ROOT).mkdir(parents=True,exist_ok=True)
        DocumentMatchingServerTests.setup_fixture(self)
    def request(self, user=None):
        request=DocumentMatchingServerTests.request(self,user)
        request.session=SessionStore();request.session.create()
        return request

    def intent(self):
        return {'action':'erp_register_supplier_invoice','document_id':self.doc.pk,'purchase_id':self.po.pk,
                'supplier_id':self.supplier.pk,'item_id':self.item.pk,'source_sha256':self.doc.checksum}

    def preview(self, request=None):
        request=request or self.request()
        return request,service.preview(request,self.intent())['id']

    def confirm(self, request, proposal_id):
        return service.execute(request,proposal_id)

    def registration_state(self):
        """Persisted domain/history/proposal/mutex facts, not in-memory instances."""
        return {
            'registrations': list(SupplierInvoiceRegistration.objects.order_by('pk').values()),
            'events': list(Event.objects.order_by('pk').values()),
            'proposals': list(ActionProposal.objects.order_by('pk').values()),
            'write_mutex': list(Configuration.objects.filter(key='erp_write').values()),
        }

    def document_match_response(self):
        request = RequestFactory().get('/api/erp/purchases/%s/document-match/' % self.po.pk, {
            'document_id': self.doc.pk, 'supplier_id': self.supplier.pk, 'item_id': self.item.pk})
        request.user = self.user
        request.session = self.request().session
        return document_match(request, self.po.pk)

    def confirm_response(self, request, proposal_id):
        endpoint = RequestFactory().post('/api/operations/confirm/', data=json.dumps({
            'proposal_id': str(proposal_id), 'confirmed': True}), content_type='application/json')
        endpoint.user, endpoint.session = request.user, request.session
        return confirm_view(endpoint)

    def assert_neutral_refusal(self, response, expected_status):
        self.assertEqual(response.status_code, expected_status)
        payload = json.loads(response.content)
        self.assertTrue(payload.get('error'))
        # An error envelope must not carry IDs, amounts, the draft, or historical rows.
        self.assertLessEqual(set(payload), {'error', 'code'})
        return payload

    def test_registers_real_domain_row_event_and_read_status(self):
        request,proposal=self.preview();receipt=self.confirm(request,proposal)
        row=SupplierInvoiceRegistration.objects.get(pk=receipt['supplier_invoice_registration_id'])
        self.assertEqual(receipt['invoice_matching_status'],'matched')
        self.assertEqual(row.purchase_id,self.po.pk);self.assertEqual(row.supplier_id,self.supplier.pk)
        self.assertEqual(row.source_sha256,self.doc.checksum);self.assertEqual(row.receipt_ids,[x.pk for x in self.receipts])
        self.assertEqual(Event.objects.get(pk=receipt['erp_event_id']).result,receipt)
        fresh=self.request();view=registration.projection(fresh,self.po.pk,self.doc.pk)
        self.assertEqual(view['status'],'matched');self.assertEqual(view['items'][0]['id'],row.id)
        endpoint=RequestFactory().get('/api/erp/purchases/%s/document-match/' % self.po.pk,{
            'document_id':self.doc.pk,'supplier_id':self.supplier.pk,'item_id':self.item.pk})
        endpoint.user=self.user;endpoint.session=SessionStore();endpoint.session.create()
        response=document_match(endpoint,self.po.pk)
        self.assertEqual(response.status_code,200);data=__import__('json').loads(response.content)
        self.assertEqual(data['schema'],'bos.document-match-read.v1');self.assertEqual(data['draft']['decision'],'accept_draft')
        self.assertEqual(data['supplier_invoice_registration']['items'][0]['id'],row.id)

    def test_replay_and_second_proposal_keep_one_business_record(self):
        request,proposal=self.preview();first=self.confirm(request,proposal)
        self.assertEqual(self.confirm(request,proposal),first)
        second_request,second=self.preview();replay=self.confirm(second_request,second)
        self.assertTrue(replay['replayed']);self.assertEqual(replay['supplier_invoice_registration_id'],first['supplier_invoice_registration_id'])
        self.assertEqual(SupplierInvoiceRegistration.objects.count(),1)
        duplicate,_=self.document(self.raw,'duplicate.pdf')
        intent={**self.intent(),'document_id':duplicate.pk,'source_sha256':duplicate.checksum}
        duplicate_request=self.request();duplicate_proposal=service.preview(duplicate_request,intent)['id']
        same=self.confirm(duplicate_request,duplicate_proposal)
        self.assertTrue(same['replayed']);self.assertEqual(same['supplier_invoice_registration_id'],first['supplier_invoice_registration_id'])
        self.assertEqual((SupplierInvoiceRegistration.objects.count(),Event.objects.count()),(1,1))

    def test_changed_source_or_new_revision_requires_new_validation_without_history_overwrite(self):
        request,proposal=self.preview();first=self.confirm(request,proposal)
        self.path.write_bytes(b'corrupted private source')
        with self.assertRaises(service.Conflict):self.confirm(request,proposal)
        self.assertEqual(SupplierInvoiceRegistration.objects.count(),1)
        self.path.write_bytes(self.raw)
        successor,_=self.document(self.raw,'replacement.pdf',code=self.doc.code,revision='B')
        projection=registration.projection(self.request(),self.po.pk,self.doc.pk)
        self.assertEqual(projection['items'][0]['status'],'requires_revalidation')
        changed={**self.intent(),'document_id':successor.pk,'source_sha256':successor.checksum}
        with self.assertRaises(service.Conflict):
            request2=self.request();proposal2=service.preview(request2,changed)['id'];self.confirm(request2,proposal2)
        self.assertEqual(SupplierInvoiceRegistration.objects.get(pk=first['supplier_invoice_registration_id']).document_id,self.doc.pk)

    def test_mismatch_revoke_and_atomic_event_failure_leave_no_registration(self):
        Purchase.objects.filter(pk=self.po.pk).update(price=1201)
        with self.assertRaises(ValueError):service.preview(self.request(),self.intent())
        Purchase.objects.filter(pk=self.po.pk).update(price=1200)
        request,proposal=self.preview();self.user.groups.set([Group.objects.get_or_create(name='manager')[0]])
        with self.assertRaises(PermissionError):self.confirm(request,proposal)
        self.user.groups.set([Group.objects.get(name='ceo')])
        request,proposal=self.preview();before=(SupplierInvoiceRegistration.objects.count(),Event.objects.count(),ActionProposal.objects.get(pk=proposal).receipt)
        with patch('operations.document_matching.registration.Event.objects.create',side_effect=RuntimeError('synthetic atomic failure')):
            with self.assertRaises(RuntimeError):self.confirm(request,proposal)
        after=ActionProposal.objects.get(pk=proposal)
        self.assertEqual((SupplierInvoiceRegistration.objects.count(),Event.objects.count(),after.receipt),before)

    def test_command_boundary_keeps_invalid_preview_422_semantics_and_maps_stale_to_conflict(self):
        with self.assertRaises(ValueError):service.preview(self.request(),{**self.intent(),'source_sha256':'0'*64})
        with patch('operations.document_matching.registration.build',side_effect=ReadStateChanged()):
            with self.assertRaises(service.Conflict):service.preview(self.request(),self.intent())
        request,proposal=self.preview()
        with patch('operations.document_matching.registration.build',side_effect=ReadStateChanged()):
            with self.assertRaises(service.Conflict):self.confirm(request,proposal)
        self.assertEqual((SupplierInvoiceRegistration.objects.count(),Event.objects.count(),ActionProposal.objects.get(pk=proposal).receipt),(0,0,None))

    def test_cross_purchase_invoice_identity_refuses_without_second_row(self):
        first_request, first_proposal = self.preview()
        first = self.confirm(first_request, first_proposal)
        other = Purchase.objects.create(code='SYN-PO-SECOND', supplier=self.supplier, item=self.item,
            quantity=10, price=1200, revision='A', currency='UAH',
            due_date=date(2026, 9, 20), original_due=date(2026, 9, 20))
        other_receipts = []
        for index, quantity in enumerate((Decimal('4.000'), Decimal('6.000'))):
            lot = Lot.objects.create(code='SYN-SECOND-LOT-' + str(index), item=self.item,
                location=self.location, revision='A', quantity=quantity, unit_cost=1200, currency='UAH')
            other_receipts.append(Movement.objects.create(lot=lot, quantity=quantity, kind='receipt',
                reference=other.code, purchase=other, cost=quantity * Decimal('1200')))
        duplicate, _ = self.document(self.raw, 'same-invoice-other-purchase.pdf')
        selection = {**self.intent(), 'purchase_id': other.pk, 'document_id': duplicate.pk,
                     'source_sha256': duplicate.checksum}
        draft = registration.build(self.request(), duplicate.pk, purchase_id=other.pk,
                                   supplier_id=self.supplier.pk, item_id=self.item.pk)
        self.assertEqual(draft['decision'], 'accept_draft')
        self.assertEqual(draft['matches']['purchase_id'], other.pk)
        self.assertEqual(draft['matches']['receipt_ids'], [row.pk for row in other_receipts])
        self.assertEqual(draft['comparison']['receipt_quantity']['net'], '10.000')
        request = self.request()
        proposal = service.preview(request, selection)['id']
        before = self.registration_state()
        with self.assertRaises(service.Conflict):
            self.confirm(request, proposal)
        self.assertEqual(self.registration_state(), before)
        self.assertIsNone(ActionProposal.objects.get(pk=proposal).receipt)
        self.assertEqual(SupplierInvoiceRegistration.objects.count(), 1)
        self.assertFalse(SupplierInvoiceRegistration.objects.filter(purchase=other).exists())
        self.assertEqual(SupplierInvoiceRegistration.objects.get().pk, first['supplier_invoice_registration_id'])

    def test_late_event_or_receipt_save_failure_rolls_back_all_rows(self):
        for target in ('event_result', 'proposal_receipt'):
            with self.subTest(failure_after_domain_row=target):
                request, proposal = self.preview()
                before = self.registration_state()
                observed = []
                model = Event if target == 'event_result' else ActionProposal
                original_save = model.save

                def fail_late(instance, *args, **kwargs):
                    fields = set(kwargs.get('update_fields') or ())
                    late = ((target == 'event_result' and fields == {'result'}) or
                            (target == 'proposal_receipt' and fields == {'receipt'} and
                             isinstance(instance.receipt, dict) and instance.receipt.get('state') == 'succeeded'))
                    if not late:
                        return original_save(instance, *args, **kwargs)
                    row = SupplierInvoiceRegistration.objects.get(purchase=self.po)
                    event = Event.objects.get()
                    running = ActionProposal.objects.get(pk=proposal).receipt
                    self.assertEqual(running, {'state': 'running'})
                    result = instance.result if target == 'event_result' else instance.receipt
                    self.assertEqual(result['supplier_invoice_registration_id'], row.pk)
                    self.assertEqual(result['erp_event_id'], event.pk)
                    if target == 'proposal_receipt':
                        # The Event result has already been persisted before this failure.
                        self.assertEqual(event.result, result)
                    observed.append((row.pk, event.pk, running))
                    raise RuntimeError('synthetic late persistence failure')

                with patch.object(model, 'save', autospec=True, side_effect=fail_late):
                    with self.assertRaisesRegex(RuntimeError, 'synthetic late persistence failure'):
                        self.confirm(request, proposal)
                self.assertEqual(len(observed), 1, 'fault must occur after the domain row exists')
                self.assertEqual(self.registration_state(), before)
                self.assertIsNone(ActionProposal.objects.get(pk=proposal).receipt)
                self.assertEqual((SupplierInvoiceRegistration.objects.count(), Event.objects.count()), (0, 0))

    def test_duplicate_proposal_replay_revalidates_corrupted_and_superseded_accepted_original(self):
        request, original_proposal = self.preview()
        first = self.confirm(request, original_proposal)
        duplicate, duplicate_path = self.document(self.raw, 'second-upload.pdf')
        duplicate_request = self.request()
        selection = {**self.intent(), 'document_id': duplicate.pk, 'source_sha256': duplicate.checksum}
        duplicate_proposal = service.preview(duplicate_request, selection)['id']
        second = self.confirm(duplicate_request, duplicate_proposal)
        self.assertTrue(second['replayed'])
        self.assertEqual(second['supplier_invoice_registration_id'], first['supplier_invoice_registration_id'])
        self.assertEqual(ActionProposal.objects.get(pk=duplicate_proposal).receipt, second)
        accepted = self.registration_state()
        self.path.write_bytes(b'corrupted accepted original, duplicate upload remains intact')
        with self.assertRaises(service.Conflict):
            self.confirm(duplicate_request, duplicate_proposal)
        self.assertEqual(self.registration_state(), accepted)
        self.path.write_bytes(self.raw)
        successor, _ = self.document(self.raw, 'accepted-source-new-revision.pdf',
                                     code=self.doc.code, revision='B')
        self.assertNotEqual(successor.pk, self.doc.pk)
        self.assertEqual(duplicate_path.read_bytes(), self.raw)
        # The duplicate document itself is still valid; refusal concerns accepted history.
        current = registration.build(self.request(), duplicate.pk, purchase_id=self.po.pk,
                                     supplier_id=self.supplier.pk, item_id=self.item.pk)
        self.assertEqual(current['decision'], 'accept_draft')
        with self.assertRaises(service.Conflict):
            self.confirm(duplicate_request, duplicate_proposal)
        self.assertEqual(self.registration_state(), accepted)
        row = SupplierInvoiceRegistration.objects.get(pk=first['supplier_invoice_registration_id'])
        self.assertEqual(row.document_id, self.doc.pk)
        self.assertEqual((SupplierInvoiceRegistration.objects.count(), Event.objects.count()), (1, 1))

    def test_projection_revocation_on_stale_source_returns_no_invoice_values(self):
        request, proposal = self.preview()
        self.confirm(request, proposal)
        self.document(self.raw, 'superseding-original.pdf', code=self.doc.code, revision='B')
        # Keep the accepted row stale, but select a separately current upload so
        # the endpoint has already built a valid private draft before projection.
        self.doc, _ = self.document(self.raw, 'current-selected-invoice.pdf')
        admitted = self.document_match_response()
        self.assertEqual(admitted.status_code, 200)
        admitted_data = json.loads(admitted.content)
        self.assertEqual(admitted_data['draft']['decision'], 'accept_draft')
        self.assertEqual(admitted_data['draft']['fields']['total']['value'], '12000.00')
        self.assertEqual(admitted_data['supplier_invoice_registration']['status'], 'requires_revalidation')
        permission = Permission.objects.get(content_type__app_label='operations', codename='download_document')
        original_policy = registration.Policy
        before = self.registration_state()
        for phase in ('before_initial_policy', 'after_initial_policy'):
            for change, status in (('role', 403), ('inactive', 401), ('capability', 409)):
                with self.subTest(phase=phase, access_change=change):
                    entered, revoked = [], []

                    def revoke():
                        revoked.append(True)
                        if change == 'role':
                            self.user.groups.set([Group.objects.get_or_create(name='manager')[0]])
                        elif change == 'inactive':
                            type(self.user).objects.filter(pk=self.user.pk).update(is_active=False)
                        else:
                            self.user.user_permissions.add(permission)

                    def scheduled_policy(current):
                        if entered:
                            return original_policy(current)
                        entered.append(True)
                        # server_adapter.Policy is untouched: its completed CEO
                        # draft established the incoming read access revision.
                        draft_policy = original_policy(current)
                        self.assertTrue(draft_policy.ceo)
                        self.assertEqual(current.bos_access_revision, draft_policy.access_revision())
                        if phase == 'before_initial_policy':
                            revoke()
                        initial = original_policy(current)
                        if phase == 'after_initial_policy':
                            revoke()
                        return initial

                    try:
                        with patch.object(registration, 'Policy', side_effect=scheduled_policy), \
                                patch.object(registration, 'prepare', wraps=registration.prepare) as prepare:
                            response = self.document_match_response()
                            self.assertEqual(len(entered), 1)
                            self.assertEqual(len(revoked), 1)
                            prepare.assert_not_called()  # Accepted source is superseded in both phases.
                        payload = self.assert_neutral_refusal(response, status)
                        if status == 401:
                            self.assertEqual(payload['code'], 'identity_denied')
                            self.assertEqual(response['X-BoS-Identity'], 'denied')
                        elif status == 409:
                            self.assertEqual(payload['code'], 'read_state_changed')
                    finally:
                        self.user.groups.set([Group.objects.get(name='ceo')])
                        type(self.user).objects.filter(pk=self.user.pk).update(is_active=True)
                        self.user.user_permissions.remove(permission)
                    self.assertEqual(self.registration_state(), before)

    def test_projection_propagates_prepare_denials_and_admits_stale_source_for_revalidation(self):
        request, proposal = self.preview()
        receipt = self.confirm(request, proposal)
        before = self.registration_state()
        for error, status in ((PermissionError('synthetic denied'), 403),
                              (IdentityDenied('synthetic ended session', 401), 401),
                              (ReadStateChanged(), 409)):
            with self.subTest(error=type(error).__name__):
                with patch.object(registration, 'prepare', side_effect=error) as prepare:
                    with self.assertRaises(type(error)) as caught:
                        registration.projection(self.request(), self.po.pk, self.doc.pk)
                    self.assertIs(caught.exception, error)
                    prepare.assert_called_once()
                with patch.object(registration, 'prepare', side_effect=error) as prepare:
                    response = self.document_match_response()
                    prepare.assert_called_once()
                payload = self.assert_neutral_refusal(response, status)
                if status == 401:
                    self.assertEqual(payload['code'], 'identity_denied')
                elif status == 409:
                    self.assertEqual(payload['code'], 'read_state_changed')
                self.assertEqual(self.registration_state(), before)
        # The actor remains admitted; an actual corrupt file is stale data, not a
        # reason to hide immutable accepted history or call it currently matched.
        self.path.write_bytes(b'corrupted but still selected original')
        response = self.document_match_response()
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('source_unreadable', data['draft']['exceptions'])
        projection = data['supplier_invoice_registration']
        self.assertEqual(projection['status'], 'requires_revalidation')
        self.assertEqual(projection['items'][0]['status'], 'requires_revalidation')
        self.assertEqual(projection['items'][0]['id'], receipt['supplier_invoice_registration_id'])
        self.assertEqual(Decimal(projection['items'][0]['amount']), Decimal('12000.00'))
        self.assertEqual(self.registration_state(), before)

    def test_missing_receipt_domain_row_is_conflict_409_without_cached_success(self):
        request, proposal = self.preview()
        receipt = self.confirm(request, proposal)
        SupplierInvoiceRegistration.objects.filter(pk=receipt['supplier_invoice_registration_id']).delete()
        before = self.registration_state()
        self.assertEqual(ActionProposal.objects.get(pk=proposal).receipt, receipt)
        with self.assertRaises(service.Conflict):
            self.confirm(request, proposal)
        self.assertEqual(self.registration_state(), before)
        response = self.confirm_response(request, proposal)
        self.assert_neutral_refusal(response, 409)
        self.assertEqual(self.registration_state(), before)
