"""P06-F01: stable demo IDs must leave the next Task insert usable."""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TransactionTestCase, override_settings

from branches.models import Branch
from employees.models import Employee
from finance.models import Counterparty
from operations.models import (AuditEvent, Configuration, Document, Invoice,
                               ProcurementRequest, SupplierQuote)
from scripts.check_support import login_test_client
from tasks.models import Task


@override_settings(BOS_DATA_MODE='demo')
class DemoTaskSequenceTests(TransactionTestCase):
    reset_sequences = True

    def seed(self):
        call_command('seed_bos_demo', stdout=StringIO())

    def task_rows(self):
        return list(Task.objects.order_by('pk').values())

    def test_new_task_after_seed_preserves_all_eight_demo_tasks(self):
        self.seed()
        original = self.task_rows()
        self.assertEqual([row['id'] for row in original], list(range(1, 9)))
        task = Task.objects.create(title='Нове навчальне доручення')
        self.assertGreater(task.pk, 8)
        self.assertEqual(list(Task.objects.filter(pk__lte=8).order_by('pk').values()), original)
        self.assertEqual(Task.objects.count(), 9)

    def test_repeated_seed_preserves_rows_and_next_insert(self):
        self.seed()
        original = self.task_rows()
        models = (Branch, Employee, Counterparty, Document, Invoice,
                  ProcurementRequest, SupplierQuote, Configuration)
        domain = {m.__name__: list(m.objects.order_by('pk').values()) for m in models}
        self.seed()
        self.assertEqual(self.task_rows(), original)
        self.assertEqual({m.__name__: list(m.objects.order_by('pk').values()) for m in models}, domain)
        self.assertGreater(Task.objects.create(title='Після повторного запуску').pk, 8)

    def test_repeated_seed_does_not_rewind_consumed_task_ids(self):
        self.seed()
        consumed = Task.objects.create(title='Тимчасове навчальне доручення')
        consumed_pk = consumed.pk
        consumed.delete()
        self.seed()
        self.assertGreater(Task.objects.create(title='Наступне доручення').pk, consumed_pk)
        self.assertEqual(Task.objects.count(), 9)

    def test_approved_task_and_replay_after_seed(self):
        self.seed()
        original = self.task_rows()
        http = Client(enforce_csrf_checks=True)
        login_test_client(http, role='ceo')

        def post(path, payload):
            return http.post('/api/operations/' + path, payload,
                             content_type='application/json',
                             HTTP_X_CSRFTOKEN=http.cookies['csrftoken'].value)

        preview = post('preview/', {'action': 'create_task', 'title': 'Перевірити покриття',
                                   'assignee_id': 2, 'deadline': '2026-09-11',
                                   'request_code': 'R01'})
        self.assertEqual(preview.status_code, 200, preview.content)
        payload = {'proposal_id': preview.json()['id'], 'confirmed': True}
        response = post('confirm/', payload)
        self.assertEqual(response.status_code, 200, response.content)
        receipt = response.json()
        self.assertGreater(receipt['task_id'], 8)
        repeated = post('confirm/', payload)
        self.assertEqual(repeated.status_code, 200, repeated.content)
        self.assertEqual(repeated.json(), receipt)
        self.assertEqual(Task.objects.count(), 9)
        self.assertEqual(AuditEvent.objects.count(), 1)
        self.assertEqual(list(Task.objects.filter(pk__lte=8).order_by('pk').values()), original)

    def test_nonempty_database_still_refuses_seed(self):
        Task.objects.create(pk=99, title='Наявне навчальне доручення')
        original = self.task_rows()
        with self.assertRaises(CommandError):
            self.seed()
        self.assertEqual(self.task_rows(), original)
        self.assertFalse(Configuration.objects.filter(key='dataset').exists())

    @override_settings(BOS_DATA_MODE='working')
    def test_working_profile_still_refuses_seed(self):
        with self.assertRaises(CommandError):
            self.seed()
        self.assertFalse(Task.objects.exists())
        self.assertFalse(Configuration.objects.filter(key='dataset').exists())
