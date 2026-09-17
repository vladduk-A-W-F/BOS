"""A04: класифікація договору після створення видимого документа."""
from operations.models import Document
from operations.test_access import A04SyntheticCase, rows, text_body


class A04DocumentContractVisibilityTests(A04SyntheticCase):
    def test_visible_document_cannot_disclose_a_now_hidden_contract_fk(self):
        self.public_doc.contract = self.contracts['ceo']
        self.public_doc.save(update_fields=['contract'])
        for role in ('manager', 'observer'):
            client = self.grant(role, 'view_document')
            self.assertEqual(client.get(f'/api/contracts/{self.contracts["ceo"].pk}/').status_code, 404)
            for url in ('/api/operations/documents/', f'/api/operations/documents/{self.public_doc.pk}/'):
                with self.subTest(role=role, url=url):
                    response = client.get(url)
                    # Повний залежний документ може стати невидимим. Якщо
                    # лишається видимим за своїм рівнем, закритий FK прибрати.
                    self.assertIn(response.status_code, (200, 404), text_body(response))
                    if response.status_code == 200:
                        data = response.json()
                        records = [data] if 'id' in data else rows(data)
                        for record in records:
                            if record['id'] == self.public_doc.pk:
                                self.assertNotEqual(record.get('contract_id'), self.contracts['ceo'].pk)
        client = self.grant('manager', 'view_document', 'export_workspace')
        export = self.json_get(client, '/api/operations/export/')
        for record in export['documents']:
            if record['id'] == self.public_doc.pk:
                self.assertNotEqual(record.get('contract_id'), self.contracts['ceo'].pk)
        self.assertEqual(Document.objects.get(pk=self.public_doc.pk).contract_id, self.contracts['ceo'].pk)
