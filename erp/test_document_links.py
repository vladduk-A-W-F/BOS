"""Documents attached to sales orders and invoices: preview/confirm write path, role-scoped reads."""
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
        self.document = Document.objects.get(code='KM-PD-5521')

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
        by_order = self.links(order=self.order.pk).json()['links']
        self.assertEqual([(x['document']['code'], x['order']['code'], x['note']) for x in by_order],
                         [('KM-PD-5521', 'ZM-0137', 'Платіжне доручення')])
        by_document = self.links(document=self.document.pk).json()['links']
        self.assertEqual({(x['order'] or x['invoice'])['code'] for x in by_document}, {'ZM-0137', 'RF-0137'})
        self.assertEqual(self.link(order_id=self.order.pk).status_code, 422)
        self.assertEqual(DocumentLink.objects.count(), 2)

    def test_exactly_one_target(self):
        self.login('ceo')
        self.assertEqual(self.link().status_code, 422)
        self.assertEqual(self.link(order_id=self.order.pk, invoice_id=self.invoice.pk).status_code, 422)
        self.assertFalse(DocumentLink.objects.exists())
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
        self.assertFalse(DocumentLink.objects.exists())
        self.assertEqual(self.links().status_code, 422)
        self.assertEqual(self.links(order=self.order.pk, invoice=self.invoice.pk).status_code, 422)
