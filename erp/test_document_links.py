"""Documents attached to sales orders and invoices: preview/confirm write path, role-scoped reads."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase, override_settings

from operations.models import Document, Invoice
from .bos4_demo import seed_bos4_demo
from .models import DocumentLink, SalesOrder


@override_settings(BOS_DATA_MODE='demo', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DocumentLinkTests(TransactionTestCase):
    def setUp(self):
        folder = TemporaryDirectory(prefix='bos4-links-test-')
        self.addCleanup(folder.cleanup)
        override = override_settings(MEDIA_ROOT=Path(folder.name) / 'media')
        override.enable()
        self.addCleanup(override.disable)
        seed_bos4_demo()
        self.order = SalesOrder.objects.get(code='ZM-0137')
        self.invoice = Invoice.objects.get(code='RF-0137')
        # A document of the test's own: the demo company itself may link its documents to ZM-0137/RF-0137.
        text = 'ДЕМО-ДАНІ. Синтетичне платіжне доручення для перевірки прив’язок.'
        self.document = Document.objects.create(code='SYN-LINK-PD', revision='A', title='Синтетичне платіжне доручення',
            access_level='operational', text=text, status='approved', checksum=hashlib.sha256(text.encode()).hexdigest())
        self.seed_links = DocumentLink.objects.count()

    def login(self, role):
        user = get_user_model().objects.create_user(username='synthetic-' + role, password='synthetic-pass')
        Group.objects.get_or_create(name=role)[0].user_set.add(user)
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label='operations',
                                                             codename__in=['view_document']))
        self.client.force_login(user)

    def link(self, **target):
        payload = {'action': 'erp_link_document', 'document_id': self.document.pk, **target}
        preview = self.client.post('/api/operations/preview/', payload, content_type='application/json')
        if preview.status_code != 200:
            return preview
        return self.client.post('/api/operations/confirm/', {'proposal_id': preview.json()['id'], 'confirmed': True},
                                content_type='application/json')

    def links(self, **query):
        return self.client.get('/api/erp/document-links/', query)

    def test_ceo_links_payment_order_to_order_and_invoice(self):
        self.login('ceo')
        self.assertEqual(self.link(order_id=self.order.pk, note='Платіжне доручення').status_code, 200)
        self.assertEqual(self.link(invoice_id=self.invoice.pk).status_code, 200)
        by_order = [x for x in self.links(order=self.order.pk).json()['links'] if x['document']['id'] == self.document.pk]
        self.assertEqual([(x['document']['code'], x['order']['code'], x['note']) for x in by_order],
                         [('SYN-LINK-PD', 'ZM-0137', 'Платіжне доручення')])
        by_document = self.links(document=self.document.pk).json()['links']
        self.assertEqual({(x['order'] or x['invoice'])['code'] for x in by_document}, {'ZM-0137', 'RF-0137'})
        self.assertEqual(self.link(order_id=self.order.pk).status_code, 422)
        self.assertEqual(DocumentLink.objects.count(), self.seed_links + 2)

    def test_exactly_one_target(self):
        self.login('ceo')
        self.assertEqual(self.link().status_code, 422)
        self.assertEqual(self.link(order_id=self.order.pk, invoice_id=self.invoice.pk).status_code, 422)
        self.assertEqual(DocumentLink.objects.count(), self.seed_links)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentLink.objects.create(document=self.document)

    def test_manager_links_orders_but_not_invoices_and_sees_no_invoice_links(self):
        self.login('ceo')
        self.link(invoice_id=self.invoice.pk)
        self.login('manager')
        self.assertEqual(self.link(invoice_id=self.invoice.pk).status_code, 403)
        self.assertEqual(self.link(order_id=self.order.pk).status_code, 200)
        self.assertEqual(self.links(invoice=self.invoice.pk).json()['links'], [])
        self.assertEqual(len(self.links(document=self.document.pk).json()['links']), 1)

    def test_observer_cannot_link_and_bad_query_is_refused(self):
        self.login('observer')
        self.assertEqual(self.link(order_id=self.order.pk).status_code, 403)
        self.assertEqual(DocumentLink.objects.count(), self.seed_links)
        self.assertEqual(self.links().status_code, 422)
        self.assertEqual(self.links(order=self.order.pk, invoice=self.invoice.pk).status_code, 422)

    def test_document_shows_the_lots_it_is_filed_under(self):
        self.login('ceo')
        certificate = Document.objects.get(code='KM-CERT-ZK0311')
        lots = self.links(document=certificate.pk).json()['lots']
        # The received lot and the lot split off it by a transfer (its code carries a database id).
        self.assertEqual({x['kind'] for x in lots}, {'certificate'})
        codes = sorted(x['code'] for x in lots)
        self.assertEqual(len(codes), 2)
        self.assertEqual(codes[0], 'KM-L-MA-7075-0926')
        self.assertTrue(codes[1].startswith('KM-T-MA-7075-'))
        self.assertEqual(self.links(order=self.order.pk).json()['lots'], [])

    def test_lots_need_the_right_to_see_the_document(self):
        # A manager without view_document sees no documents, so no lots through one either.
        user = get_user_model().objects.create_user(username='synthetic-blind', password='synthetic-pass')
        Group.objects.get_or_create(name='manager')[0].user_set.add(user)
        self.client.force_login(user)
        certificate = Document.objects.get(code='KM-CERT-ZK0311')
        self.assertEqual(self.links(document=certificate.pk).json()['lots'], [])

    def test_only_an_exact_integer_id_links_a_lot(self):
        # JSON true and 1.0 equal 1 in Python; they must not file a lot under document 1.
        from .models import Lot
        self.login('ceo')
        first = Document.objects.order_by('pk').first()
        lot = Lot.objects.exclude(documents={}).first()
        for odd in (True, float(first.pk)):
            Lot.objects.filter(pk=lot.pk).update(documents={'certificate': odd})
            self.assertNotIn(lot.code, [x['code'] for x in self.links(document=first.pk).json()['lots']], odd)
        Lot.objects.filter(pk=lot.pk).update(documents={'certificate': first.pk})
        self.assertIn(lot.code, [x['code'] for x in self.links(document=first.pk).json()['lots']])
