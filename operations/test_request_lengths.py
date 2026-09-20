"""PLAN-N1-REQUEST: raw text boundaries through the authenticated HTTP writer."""
from copy import deepcopy
import hashlib
import json

from django.apps import apps
from django.conf import settings
from django.test import Client, TestCase, override_settings

from employees.models import Employee
from operations.models import Document, ProcurementRequest
from scripts.check_support import login_test_client


@override_settings(
    BOS_DATA_MODE='working', ANTHROPIC_API_KEY='',
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class ProcurementRequestLengthTests(TestCase):
    LIMITS = {'code': 30, 'part': 120, 'revision': 40, 'unit': 20}

    def setUp(self):
        self.http = Client(enforce_csrf_checks=True, raise_request_exception=False)
        login_test_client(self.http)
        self.owner = Employee.objects.create(full_name='Синтетичний відповідальний N1')
        content = b'Synthetic N1 request specification'
        self.document = Document.objects.create(
            code='N1-SPEC', revision='A', title='Синтетична специфікація N1',
            content=content, checksum=hashlib.sha256(content).hexdigest(), status='approved')
        self.sequence = 0

    def payload(self):
        self.sequence += 1
        return {
            'code': 'N1-R-' + str(self.sequence), 'part': 'Синтетична деталь',
            'revision': 'A', 'quantity': 2, 'unit': 'шт.', 'currency': 'EUR',
            'required_by': '2026-10-01', 'owner_id': self.owner.pk,
            'document_id': self.document.pk, 'details': {},
        }

    def post(self, payload):
        return self.http.post('/api/operations/requests/create/',
            json.dumps(payload, ensure_ascii=False), content_type='application/json',
            HTTP_X_CSRFTOKEN=self.http.cookies[settings.CSRF_COOKIE_NAME].value)

    def state(self):
        # Includes the ERP mutex, proposal receipts, audit rows and all business
        # sources. Read the state before any test-owned cleanup or rollback.
        labels = ('operations', 'erp', 'finance', 'tasks', 'employees', 'branches', 'ai_assistant')
        return {
            model._meta.label: deepcopy(list(model.objects.order_by('pk').values()))
            for label in labels for model in apps.get_app_config(label).get_models()
        }

    def test_model_limits_accept_exact_raw_text_without_trimming(self):
        for field, limit in self.LIMITS.items():
            self.assertEqual(ProcurementRequest._meta.get_field(field).max_length, limit)
            for char in ('A', 'Ї', '🙂'):
                for value in (char * limit, char * (limit - 1) + ' '):
                    with self.subTest(field=field, value=value):
                        payload = self.payload()
                        payload[field] = value
                        before = ProcurementRequest.objects.count()
                        response = self.post(payload)
                        self.assertEqual(response.status_code, 201, response.content)
                        self.assertEqual(ProcurementRequest.objects.count(), before + 1)
                        saved = ProcurementRequest.objects.get(code=payload['code'])
                        self.assertEqual(getattr(saved, field), value)
                        self.assertEqual(len(getattr(saved, field)), limit)
                        self.assertEqual((saved.owner_id, saved.document_id),
                                         (self.owner.pk, self.document.pk))

    def test_raw_overflow_refused_without_trimming_or_partial_writes(self):
        for field, limit in self.LIMITS.items():
            for char in ('A', 'Ї', '🙂'):
                for value in (char * (limit + 1), char * limit + ' ', ' ' + char * limit):
                    with self.subTest(field=field, value=value):
                        payload = self.payload()
                        payload[field] = value
                        before = self.state()
                        response = self.post(payload)
                        # Check state first: an accepted overlong SQLite row must
                        # not be hidden by an early response-status assertion.
                        self.assertEqual(self.state(), before)
                        self.assertEqual(response.status_code, 422, response.content)
                        self.assertIn(f'максимум {limit} символів', response.json()['error'])
