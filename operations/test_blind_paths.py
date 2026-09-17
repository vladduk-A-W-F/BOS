"""П'ять додаткових A04 обходів. Тільки синтетичні HTTP/ORM fixtures.

Використовує незмінний прийнятий operations.test_access.A04SyntheticCase.
Запуск: manage.py test a04_test_blind_paths --settings=verification_settings.
"""
import json
from datetime import timedelta

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from erp.models import Event, Item, Lot, SalesOrder
from finance.models import Transaction
from operations.models import ActionProposal, AuditEvent, Document, ProcurementRequest, SupplierQuote
from operations.test_access import A04SyntheticCase, aliases, rows, text_body
from tasks.models import Task


class A04BlindPathTests(A04SyntheticCase):
    def test_nested_erp_ids_are_scoped_on_both_preview_adapters(self):
        client = self.grant('manager', 'view_document')
        payloads = [
            {
                'action': 'erp_order', 'code': 'A04-BLIND-ORDER',
                'customer_id': self.customer.pk, 'owner_id': self.employee.pk,
                'due_date': (self.today + timedelta(days=20)).isoformat(), 'currency': 'EUR',
                'lines': [{'item_id': self.hidden_item.pk, 'quantity': '2', 'price': '1'}],
            },
            {
                'action': 'erp_item', 'code': 'A04-BLIND-BOM', 'name': 'Виріб зі сліпою специфікацією',
                'unit': 'шт.', 'kind': 'product', 'method': 'make', 'revision': 'A', 'currency': 'EUR',
                'document_id': self.public_doc.pk,
                'bom': [{'item_id': self.hidden_item.pk, 'quantity': '1'}],
            },
            {
                'action': 'erp_receive', 'purchase_id': self.purchase.pk,
                'code': 'A04-BLIND-CERT', 'location_id': self.location.pk, 'quantity': '1',
                'documents': {'certificate': self.hidden_doc.pk},
            },
        ]
        for url in ('/api/erp/preview/', '/api/operations/preview/'):
            for payload in payloads:
                with self.subTest(url=url, action=payload['action']):
                    before = (ActionProposal.objects.count(), Item.objects.count(),
                              SalesOrder.objects.count(), Lot.objects.count(), Event.objects.count())
                    response = self.post(client, url, payload)
                    self.assertEqual(response.status_code, 404, text_body(response))
                    self.assertEqual((ActionProposal.objects.count(), Item.objects.count(),
                                      SalesOrder.objects.count(), Lot.objects.count(), Event.objects.count()), before)

    def test_projected_rows_never_retain_hidden_foreign_ids(self):
        # Звичайна синтетична customer transaction не є оплаченою зарплатою.
        # Видимий запис може мати закритий FK після зміни класифікації джерела.
        transaction = Transaction.objects.get(pk=self.transactions[0].pk)
        transaction.contract = self.contracts['ceo']
        transaction.save(update_fields=['contract'])
        self.item.bom = [{'item_id': self.hidden_item.pk, 'quantity': '1'}]
        self.item.save(update_fields=['bom'])
        self.lot.documents = {'certificate': self.hidden_doc.pk}
        self.lot.save(update_fields=['documents'])
        client = self.grant('manager', 'view_document')

        # Проєкція може прибрати весь залежний рядок або закритий FK. Оригінал
        # мусить лишитися в ORM. Не приймається заміна робочих FK у самій БД.
        for url in aliases('/api/transactions/'):
            with self.subTest(url=url):
                data = rows(self.json_get(client, url))
                for row in data:
                    if row['id'] == transaction.pk:
                        self.assertNotEqual(row.get('contract'), self.contracts['ceo'].pk)
        data = self.json_get(client, '/api/erp/snapshot/')
        for row in data['items']:
            if row['id'] == self.item.pk:
                self.assertNotIn(self.hidden_item.pk, [line.get('item_id') for line in row.get('bom', [])])
        for row in data['lots']:
            if row['id'] == self.lot.pk:
                self.assertNotIn(self.hidden_doc.pk, row.get('documents', {}).values())
        self.assertEqual(Transaction.objects.get(pk=transaction.pk).contract_id, self.contracts['ceo'].pk)
        self.assertEqual(Item.objects.get(pk=self.item.pk).bom, self.item.bom)
        self.assertEqual(Lot.objects.get(pk=self.lot.pk).documents, self.lot.documents)

    def test_blind_forms_cannot_create_or_relink_hidden_sources_or_versions(self):
        client = self.grant('manager', 'view_document')
        payloads = [
            ('/api/operations/requests/create/', {
                'code': 'A04-BLIND-R', 'part': 'Нова заявка', 'revision': 'A', 'quantity': 2,
                'unit': 'шт.', 'currency': 'EUR', 'required_by': (self.today + timedelta(days=20)).isoformat(),
                'owner_id': self.employee.pk, 'document_id': self.hidden_doc.pk, 'details': {},
            }),
            ('/api/operations/quotes/create/', {
                'code': 'A04-BLIND-Q', 'request_code': 'R02', 'supplier_id': self.supplier.pk,
                'document_id': self.public_doc.pk, 'terms': self.quotes[0].terms,
            }),
            (f'/api/operations/documents/{self.public_doc.pk}/review/', {
                'checksum': self.public_doc.checksum, 'contract_id': self.contracts['ceo'].pk,
            }),
        ]
        def state():
            return (Document.objects.count(), ProcurementRequest.objects.count(), SupplierQuote.objects.count(),
                    Document.objects.get(pk=self.public_doc.pk).contract_id)
        for url, payload in payloads:
            with self.subTest(url=url):
                before = state()
                response = self.post(client, url, payload)
                self.assertEqual(response.status_code, 404, text_body(response))
                self.assertEqual(state(), before)
        before = state()
        response = client.post('/api/operations/documents/upload/', {
            'code': self.hidden_doc.code, 'revision': 'B', 'title': 'Сліпа нова версія',
            'file': SimpleUploadedFile('A04_NEW_VERSION.txt', b'Synthetic A04 bytes', content_type='text/plain'),
        }, HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertEqual(response.status_code, 404, text_body(response))
        self.assertEqual(state(), before)
        self.assertFalse(Document.objects.filter(code=self.hidden_doc.code, revision='B').exists())

    def test_completed_proposal_replay_rechecks_document_permission(self):
        client = self.grant('manager', 'view_document')
        response = self.post(client, '/api/operations/preview/', {
            'action': 'create_task', 'title': 'A04 виконана дія для відкритої заявки',
            'assignee_id': self.employee.pk, 'deadline': (self.today + timedelta(days=5)).isoformat(),
            'request_code': 'R01',
        })
        self.assertEqual(response.status_code, 200, text_body(response))
        proposal_id = response.json()['id']
        completed = self.post(client, '/api/operations/confirm/', {'proposal_id': proposal_id, 'confirmed': True})
        self.assertEqual(completed.status_code, 200, text_body(completed))
        self.assertEqual(completed.json()['state'], 'succeeded')
        before = (Task.objects.count(), AuditEvent.objects.count())
        receipt = ActionProposal.objects.get(pk=proposal_id).receipt
        self.users['manager'].user_permissions.clear()
        denied = self.post(client, '/api/operations/confirm/', {'proposal_id': proposal_id, 'confirmed': True})
        self.assertIn(denied.status_code, (403, 404), text_body(denied))
        self.assertNotIn('succeeded', text_body(denied))
        self.assertEqual((Task.objects.count(), AuditEvent.objects.count()), before)
        self.assertEqual(ActionProposal.objects.get(pk=proposal_id).receipt, receipt)

    def test_browsable_html_and_metadata_share_the_same_field_and_fk_scope(self):
        canaries = (self.HR_PHONE, self.HR_EMAIL, self.HR_DATE, self.HIDDEN,
                    self.contracts['ceo'].number, self.contracts['ceo'].name) + self.PAYROLL_AMOUNTS
        for role in ('manager', 'observer'):
            client = self.grant(role, 'view_document')
            for url in ('/api/employees/', '/api/contracts/', '/api/transactions/'):
                with self.subTest(role=role, url=url):
                    response = client.get(url, HTTP_ACCEPT='text/html')
                    # JSON-only renderer is a valid way to avoid unsafe HTML.
                    self.assertIn(response.status_code, (200, 403, 404, 406))
                    self.assert_no_canaries(text_body(response), canaries)
                    options = client.options(url, HTTP_ACCEPT='application/json')
                    self.assertIn(options.status_code, (200, 403, 404, 405))
                    self.assert_no_canaries(text_body(options), canaries)
