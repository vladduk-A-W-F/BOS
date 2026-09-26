"""A08: current byte integrity at existing ERP admission guards.

One synthetic test with three genuine preview -> corrupt -> confirm paths.
No mocks, no real databases, no production modifications.
"""
import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.test import Client, TestCase, override_settings

from employees.models import Employee
from erp.models import ChangeOrder, Event, Inspection, Item, Location, Lot
from erp.service import dispatch
from operations.models import ActionProposal, Configuration, Document
from scripts.check_support import login_test_client


@override_settings(BOS_DATA_MODE='working', DEBUG=False, ANTHROPIC_API_KEY='',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class A08ERPDocumentIntegrityTests(TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('DJANGO_SETTINGS_MODULE'), 'verification_settings')
        if connection.vendor == 'sqlite':
            self.assertTrue(Path(str(connection.settings_dict['NAME'])).name.startswith('check_'))
        self.client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        login_test_client(self.client, 'ceo', capabilities=('view_document', 'download_document'))
        self.employee = Employee.objects.create(full_name='Синтетичний інспектор A08 ERP')
        self.location = Location.objects.create(code='A08-E-W', name='Синтетичний склад')
        Configuration.objects.create(key='erp_write', value={'revision': 0})
        self.evidence = []
        self.addCleanup(self.save_evidence)

    def save_evidence(self):
        value = os.environ.get('A08_ERP_DOCUMENT_EVIDENCE')
        if value:
            Path(value).write_text(json.dumps(self.evidence, ensure_ascii=False, indent=2) + '\n')

    def post(self, path, payload):
        return self.client.post(path, json.dumps(payload), content_type='application/json',
            HTTP_X_CSRFTOKEN=self.client.cookies[settings.CSRF_COOKIE_NAME].value)

    def rows(self):
        return deepcopy({model._meta.label: list(model.objects.order_by('pk').values())
            for model in (Item, Lot, ChangeOrder, Inspection, Event, Configuration, ActionProposal, Document)})

    def fixture(self, action):
        code = 'A08-' + action.upper()
        raw = ('Синтетична специфікація ' + code + ' версія B').encode('utf-8')
        doc = Document.objects.create(code=code, revision='B', title='Синтетична специфікація',
            content=raw, text=raw.decode('utf-8'), checksum=hashlib.sha256(raw).hexdigest(),
            filename=code+'.txt', access_level='operational', status='approved')
        item = Item.objects.create(code=code, name='Синтетичний виріб', kind='material', method='buy',
            revision='A', required_documents=['cert'], currency='EUR')
        lot = Lot.objects.create(code=code, item=item, location=self.location, quantity='10',
            unit_cost='2.00', currency='EUR', revision='A', quality='pending', documents={'cert':doc.pk})
        if action == 'quality':
            payload = {'action':'erp_quality', 'lot_id':lot.pk, 'result':'approved',
                       'inspector_id':self.employee.pk, 'note':'Синтетична перевірка сертифіката'}
        else:
            payload = {'action':'erp_change', 'code':code, 'item_id':item.pk, 'document_id':doc.pk,
                       'target_revision':'B', 'reason':'Синтетична зміна специфікації'}
            if action == 'apply_change':
                created = dispatch(payload, 'ceo')
                payload = {'action':'erp_apply_change', 'change_id':created['change_id'],
                           'disposition':'Погоджено синтетичну версію B'}
        return doc, item, lot, payload

    def test_confirmation_rechecks_original_bytes_for_quality_change_and_apply_change(self):
        for action in ('quality', 'change', 'apply_change'):
            doc, item, lot, payload = self.fixture(action)
            preview = self.post('/api/erp/preview/', payload)
            self.assertEqual(preview.status_code, 200, preview.content)
            proposal = preview.json()['id']
            # Change physical source only: stored status/hash/version and the
            # proposal fingerprint remain unchanged. This is exactly the risk.
            Document.objects.filter(pk=doc.pk).update(content=b'A08 ERP SUBSTITUTED ORIGINAL')
            before = self.rows()
            confirmed = self.post('/api/operations/confirm/', {'proposal_id':proposal, 'confirmed':True})
            after = self.rows()
            changed = [name for name in before if before[name] != after[name]]
            self.evidence.append({'action':action, 'preview_status':preview.status_code,
                'confirmation_status':confirmed.status_code, 'response':confirmed.json(),
                'changed_models':changed, 'document_id':doc.pk,
                'stored_checksum':doc.checksum,
                'actual_checksum':hashlib.sha256(b'A08 ERP SUBSTITUTED ORIGINAL').hexdigest()})
            with self.subTest(action=action, contract='controlled refusal'):
                self.assertEqual(confirmed.status_code, 422, confirmed.content)
            with self.subTest(action=action, contract='no stock/version/receipt mutation'):
                self.assertEqual(changed, [], 'Changed models: ' + ', '.join(changed))
