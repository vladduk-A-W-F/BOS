"""Той самий A04 Document.contract_id через відповідь review adapter."""
from operations.models import Document
from operations.test_access import A04SyntheticCase, text_body


class A04ReviewResponseProjectionTests(A04SyntheticCase):
    def test_review_without_contract_change_still_uses_document_projection(self):
        self.public_doc.contract = self.contracts['ceo']
        self.public_doc.save(update_fields=['contract'])
        client = self.grant('manager', 'view_document')
        detail = self.json_get(client, f'/api/operations/documents/{self.public_doc.pk}/')
        self.assertIsNone(detail.get('contract_id'))
        response = self.post(client, f'/api/operations/documents/{self.public_doc.pk}/review/', {
            'checksum': self.public_doc.checksum,
        })
        self.assertEqual(response.status_code, 200, text_body(response))
        self.assertNotEqual(response.json().get('contract_id'), self.contracts['ceo'].pk)
        self.assertEqual(Document.objects.get(pk=self.public_doc.pk).contract_id, self.contracts['ceo'].pk)
