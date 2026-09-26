"""A04: справжні HTTP/ORM регресії прийнятої матриці доступу.

Запускати тільки з verification_settings та окремими BOS_TEST_DB_NAME/MEDIA.
Цей файл не читає робочі SQLite, не викликає LLM, не підміняє HTTP чи ORM.
До міграцій helper залишає нові поля невстановленими, щоб red містив реальні
витоки endpoint-ів. Окремий тест вимагає поля й безпечні schema defaults.
"""
import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import Client, RequestFactory, TestCase, override_settings

from ai_assistant.models import ChatFile, ChatMessage, EmployeeChangeLog
from branches.models import Branch
from employees.models import Employee
from erp.models import (
    ChangeOrder, Event, InvoiceLink, Item, Location, Lot, Movement, Purchase,
    SalesLine, SalesOrder,
)
from finance.models import Contract, Counterparty, Salary, Transaction
from operations.models import (
    ActionProposal, AuditEvent, Configuration, Document, Invoice,
    ProcurementRequest, SupplierQuote,
)
from scripts.check_support import login_test_client
from tasks.models import Task


def aliases(path):
    """Реальні DRF aliases, без вигаданих маршрутів."""
    return (path, path.rstrip('/') + '.json', path.rstrip('/') + '.json/')


def body_bytes(response):
    if getattr(response, 'streaming', False):
        return b''.join(response.streaming_content)
    return response.content


def text_body(response):
    return body_bytes(response).decode('utf-8', errors='replace')


def rows(data):
    if isinstance(data, list):
        return data
    if 'results' in data:
        return data['results']
    return data['items']


def nested_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from nested_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_keys(child)


@override_settings(
    BOS_DATA_MODE='working', DEBUG=False, ANTHROPIC_API_KEY='',
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class A04SyntheticCase(TestCase):
    HR_PHONE = '+380000A04SECRET'
    HR_EMAIL = 'a04-private-hr@example.invalid'
    HR_DATE = '1979-04-23'
    HIDDEN = 'A04_CEO_DOCUMENT_SECRET'
    MANAGEMENT = 'A04_MANAGEMENT_DOCUMENT_SECRET'
    HIDDEN_VERSION = 'A04_CEO_VERSION_SECRET'
    FINANCE_AMOUNTS = ('77771.13', '88882.24', '99993.35', '123456.78')
    PAYROLL_AMOUNTS = ('23761.41', '23862.52', '23963.63')
    MONEY_KEYS = {
        'amount', 'paid', 'open', 'price', 'unit_price', 'setup', 'shipping',
        'tooling', 'special_processes', 'extras', 'cost', 'unit_cost',
        'planned_cost', 'actual_cost', 'labor_cost', 'order_value',
        'shipped_value', 'shipped_cost', 'gross_margin', 'purchase_open',
        'stock_value', 'revenue', 'expenses', 'ebitda', 'net_profit',
        'net_margin', 'cash_flow', 'receivable', 'payable', 'receivables',
        'total_debit', 'total_credit', 'balance', 'revenue_pct',
    }

    @classmethod
    def make_document(cls, code, level=None, *, revision='A', marker=None, contract=None):
        marker = marker or code
        content = (marker + ' · синтетичний приватний документ').encode()
        values = dict(code=code, revision=revision, title=marker,
                      filename=marker + '.txt', text=content.decode(), content=content,
                      sections=[{'source': marker + ':1', 'text': content.decode()}],
                      checksum=hashlib.sha256(content).hexdigest(), status='approved',
                      contract=contract)
        if level is not None and 'access_level' in {f.name for f in Document._meta.fields}:
            values['access_level'] = level
        return Document.objects.create(**values)

    @classmethod
    def setUpTestData(cls):
        cls.today = date.today()
        Configuration.objects.create(key='dataset', value={'as_of': cls.today.isoformat()})
        Configuration.objects.create(key='cash', value={'amount': '123456.78', 'currency': 'UAH'})
        cls.branch = Branch.objects.create(code='A04', name='Синтетична філія A04', type='headquarters')
        cls.employee = Employee.objects.create(
            full_name='Синтетичний Працівник A04', role='Постачання', department='Операції',
            birthday=date.fromisoformat(cls.HR_DATE), phone=cls.HR_PHONE,
            email=cls.HR_EMAIL, kpi=77, branch=cls.branch,
        )
        cls.supplier = Counterparty.objects.create(name='Постачальник A04', type='supplier')
        cls.customer = Counterparty.objects.create(name='Покупець A04', type='customer')
        cls.contracts = {}
        for i, level in enumerate(('operational', 'management', 'ceo')):
            cls.contracts[level] = Contract.objects.create(
                number='A04-CT-' + level, name='Договір A04 ' + level,
                counterparty=cls.supplier, category='supply', status='active',
                amount=Decimal('65432.17') + i, currency='EUR',
            )
        cls.public_doc = cls.make_document('A04-OPEN', 'operational', contract=cls.contracts['operational'])
        cls.management_doc = cls.make_document('A04-MANAGEMENT', 'management', marker=cls.MANAGEMENT,
                                               contract=cls.contracts['management'])
        cls.hidden_doc = cls.make_document('A04-CEO', 'ceo', marker=cls.HIDDEN,
                                           contract=cls.contracts['ceo'])
        cls.legacy_doc = cls.make_document('A04-UNCLASSIFIED')
        cls.public_version = cls.make_document('A04-VERSIONS', 'operational', revision='A')
        cls.hidden_version = cls.make_document('A04-VERSIONS', 'ceo', revision='B', marker=cls.HIDDEN_VERSION)
        cls.requests = {}
        for code, doc in [('R01', cls.public_doc), ('R02', cls.hidden_doc), ('R03', cls.management_doc)]:
            cls.requests[code] = ProcurementRequest.objects.create(
                code=code, part='Виріб ' + code, revision='A', quantity=3,
                currency='EUR', required_by=cls.today + timedelta(days=90),
                owner=cls.employee, document=doc, details={'material': 'Сталь A04'},
            )
        cls.hidden_version_request = ProcurementRequest.objects.create(
            code='A04-HIDDEN-VERSION-REQUEST', part=cls.HIDDEN_VERSION, revision='B', quantity=1,
            required_by=cls.today + timedelta(days=90), owner=cls.employee, document=cls.hidden_version,
        )
        cls.quotes = []
        for i, doc in enumerate((cls.public_doc, cls.hidden_doc, cls.management_doc)):
            cls.quotes.append(SupplierQuote.objects.create(
                code='Q1' + str(i + 1), request=cls.requests['R01'], supplier=cls.supplier, document=doc,
                terms={'unit_price': str(Decimal('4567.89') + i), 'setup': '101.23',
                       'shipping': '20.34', 'tooling': '0', 'special_processes': '0',
                       'currency': 'EUR', 'revision': 'A', 'lead_weeks': 2,
                       'valid_until': (cls.today + timedelta(days=365)).isoformat(),
                       'moq': 1, 'coating_included': True, 'material_certificate': True},
            ))
        cls.location = Location.objects.create(code='A04-WH', name='Склад A04')
        cls.item = Item.objects.create(code='A04-ITEM', name='Виріб A04', document=cls.public_doc,
                                       planned_cost='4567.89', currency='EUR')
        cls.hidden_item = Item.objects.create(code='A04-HIDDEN-ITEM', name=cls.HIDDEN,
                                              document=cls.hidden_doc, planned_cost='8976.54')
        cls.lot = Lot.objects.create(code='A04-LOT', item=cls.item, location=cls.location,
                                     revision='A', quantity=12, quality='approved', unit_cost='4321.98')
        cls.hidden_lot = Lot.objects.create(code='A04-HIDDEN-LOT', item=cls.hidden_item,
                                            location=cls.location, revision='A', quantity=10,
                                            quality='approved', unit_cost='9876.54')
        cls.order = SalesOrder.objects.create(code='A04-SO-OPEN', customer=cls.customer,
                                              owner=cls.employee, due_date=cls.today + timedelta(days=90),
                                              status='confirmed')
        cls.line = SalesLine.objects.create(order=cls.order, item=cls.item, revision='A',
                                            quantity=4, shipped=4, invoiced=4, price='6543.21')
        cls.hidden_order = SalesOrder.objects.create(code='A04-SO-HIDDEN', customer=cls.customer,
                                                     owner=cls.employee, due_date=cls.today + timedelta(days=90),
                                                     status='confirmed', notes=cls.HIDDEN)
        SalesLine.objects.create(order=cls.hidden_order, item=cls.hidden_item, revision='A',
                                 quantity=7, price='9876.54')
        cls.change = ChangeOrder.objects.create(code='A04-CHANGE', item=cls.item,
                                                document=cls.public_doc, target_revision='A', reason='A04')
        cls.hidden_change = ChangeOrder.objects.create(code='A04-HIDDEN-CHANGE', item=cls.hidden_item,
                                                       document=cls.hidden_doc, target_revision='A', reason=cls.HIDDEN)
        cls.purchase = Purchase.objects.create(code='A04-PO', item=cls.item, supplier=cls.supplier,
                                                request=cls.requests['R01'], quantity=9, price='4321.98',
                                                extras='12.34', revision='A', due_date=cls.today + timedelta(days=30),
                                                original_due=cls.today + timedelta(days=30))
        Movement.objects.create(lot=cls.lot, quantity=-4, kind='shipment', reference='A04-SHIP',
                                 line=cls.line, cost='17287.92')
        cls.invoices = []
        cls.transactions = []
        cls.salaries = []
        for index, currency in enumerate(('EUR', 'USD', 'UAH')):
            invoice = Invoice.objects.create(code='A04-INV-' + currency, customer=cls.customer,
                                              amount=cls.FINANCE_AMOUNTS[index], paid='0', currency=currency,
                                              due_date=cls.today - timedelta(days=3))
            cls.invoices.append(invoice)
            InvoiceLink.objects.create(invoice=invoice, order=cls.order, lines=[cls.line.pk])
            cls.transactions.append(Transaction.objects.create(
                direction='in', amount=cls.FINANCE_AMOUNTS[index], currency=currency,
                date=cls.today, description='A04_TRANSACTION_PRIVATE_DESCRIPTION_' + currency,
                category='customer', counterparty=cls.customer, contract=cls.contracts['operational'],
                branch=cls.branch,
            ))
            salary = Salary.objects.create(employee=cls.employee, amount=cls.PAYROLL_AMOUNTS[index],
                                            currency=currency, period_year=cls.today.year,
                                            period_month=index + 1, notes='A04_PAYROLL_SECRET_' + currency)
            salary.mark_paid(cls.today.isoformat())
            cls.salaries.append(salary)
        cls.unlinked_payroll = Transaction.objects.create(
            direction='out', amount='91827.36', currency='USD', date=cls.today,
            description='A04_UNLINKED_PAYROLL_SECRET', category='salary',
        )
        cls.task = Task.objects.create(title='Відкрите доручення A04', assignee=cls.employee.full_name,
                                       deadline=cls.today - timedelta(days=1), status='active')
        EmployeeChangeLog.objects.create(action='update', employee_id=cls.employee.pk,
                                          employee_name='A04_HR_EVENT_SECRET',
                                          before={'phone': cls.HR_PHONE}, after={'email': cls.HR_EMAIL})
        AuditEvent.objects.create(action='erp_payment', payload={
            'invoice_id': cls.invoices[0].pk, 'amount': cls.FINANCE_AMOUNTS[0],
            'document_id': cls.hidden_doc.pk, 'note': cls.HIDDEN,
        })
        Event.objects.create(action='erp_payment', role='ceo', payload={
            'amount': cls.FINANCE_AMOUNTS[0], 'document_id': cls.hidden_doc.pk, 'note': cls.HIDDEN,
        }, result={'private': cls.HIDDEN, 'amount': cls.FINANCE_AMOUNTS[0]})

    def setUp(self):
        cache.clear()
        self.clients = {}
        self.users = {}

    def client_for(self, role):
        if role not in self.clients:
            client = Client(enforce_csrf_checks=True)
            self.users[role] = login_test_client(client, role)
            self.clients[role] = client
        return self.clients[role]

    def grant(self, role, *codenames):
        self.client_for(role)
        ct = ContentType.objects.get_for_model(Document)
        for codename in codenames:
            permission, _ = Permission.objects.get_or_create(
                content_type=ct, codename=codename, defaults={'name': 'Synthetic A04 ' + codename})
            self.users[role].user_permissions.add(permission)
        return self.clients[role]

    def post(self, client, url, payload):
        return client.post(url, payload, content_type='application/json',
                           HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)

    def json_get(self, client, url):
        response = client.get(url)
        self.assertEqual(response.status_code, 200, (url, text_body(response)))
        return response.json()

    def assert_no_canaries(self, data, canaries):
        text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, default=str)
        for canary in canaries:
            with self.subTest(canary=canary):
                self.assertNotIn(str(canary), text)

    def assert_no_money(self, data):
        self.assertFalse(self.MONEY_KEYS.intersection(nested_keys(data)),
                         self.MONEY_KEYS.intersection(nested_keys(data)))
        self.assert_no_canaries(data, self.FINANCE_AMOUNTS + self.PAYROLL_AMOUNTS)

    def assert_hidden(self, client, url, marker=None):
        response = client.get(url)
        self.assertEqual(response.status_code, 404, (url, response.status_code, text_body(response)))
        self.assert_no_canaries(text_body(response) + str(dict(response.headers)),
                                [marker or self.HIDDEN])

    def scoped_request(self, role):
        self.client_for(role)
        request = RequestFactory().get('/api/chat/')
        request.user = self.users[role]
        request.session = self.clients[role].session
        return request

    def message(self, role, text, visibility=None):
        self.client_for(role)
        values = {'role': 'assistant', 'content': text}
        fields = {f.name for f in ChatMessage._meta.fields}
        if 'user' in fields:
            values['user'] = self.users[role]
        if 'visibility_role' in fields:
            values['visibility_role'] = visibility or role
        return ChatMessage.objects.create(**values)


class A04FinanceReadTests(A04SyntheticCase):
    def test_ceo_retains_three_currency_finance_and_payroll_data(self):
        client = self.client_for('ceo')
        salary_rows = rows(self.json_get(client, '/api/salaries/'))
        self.assertEqual({row['currency'] for row in salary_rows}, {'EUR', 'USD', 'UAH'})
        self.assertEqual({row['amount'] for row in salary_rows}, set(self.PAYROLL_AMOUNTS))
        tx_rows = rows(self.json_get(client, '/api/transactions/'))
        self.assertTrue({salary.transaction_id for salary in self.salaries}.issubset({row['id'] for row in tx_rows}))
        employee = self.json_get(client, f'/api/employees/{self.employee.pk}/')
        self.assertEqual(employee['phone'], self.HR_PHONE)
        self.assertEqual(employee['email'], self.HR_EMAIL)

    def test_payroll_forbidden_for_manager_observer_in_all_get_aliases(self):
        for role in ('manager', 'observer'):
            client = self.client_for(role)
            for url in aliases('/api/salaries/') + aliases(f'/api/salaries/{self.salaries[0].pk}/'):
                with self.subTest(role=role, url=url):
                    response = client.get(url)
                    self.assertIn(response.status_code, (403, 404))
                    self.assert_no_canaries(text_body(response), self.PAYROLL_AMOUNTS + ('A04_PAYROLL_SECRET',))

    def test_employee_directory_remains_useful_without_hr_fields(self):
        for role in ('manager', 'observer'):
            client = self.client_for(role)
            for url in aliases('/api/employees/') + aliases(f'/api/employees/{self.employee.pk}/'):
                with self.subTest(role=role, url=url):
                    data = self.json_get(client, url)
                    item = data if isinstance(data, dict) and 'id' in data else rows(data)[0]
                    self.assertEqual(item['id'], self.employee.pk)
                    self.assertEqual(item['full_name'], self.employee.full_name)
                    self.assertFalse({'birthday', 'phone', 'email', 'kpi', 'salaries', 'salary', 'user'}.intersection(item))
                    self.assert_no_canaries(data, (self.HR_PHONE, self.HR_EMAIL, self.HR_DATE))

    def test_manager_transaction_whitelist_and_payroll_sources_excluded(self):
        client = self.client_for('manager')
        allowed = {'id', 'date', 'direction', 'category', 'currency', 'contract', 'counterparty', 'branch', 'archived_at'}
        excluded_ids = {s.transaction_id for s in self.salaries} | {self.unlinked_payroll.pk}
        for url in aliases('/api/transactions/'):
            with self.subTest(url=url):
                data = rows(self.json_get(client, url))
                self.assertTrue({t.pk for t in self.transactions}.issubset({r['id'] for r in data}))
                self.assertTrue(excluded_ids.isdisjoint({r['id'] for r in data}))
                for row in data:
                    self.assertTrue(set(row).issubset(allowed), set(row) - allowed)
                self.assert_no_canaries(data, self.FINANCE_AMOUNTS + self.PAYROLL_AMOUNTS + ('A04_TRANSACTION_PRIVATE',))
        for transaction in self.transactions:
            for url in aliases(f'/api/transactions/{transaction.pk}/'):
                with self.subTest(url=url):
                    data = self.json_get(client, url)
                    self.assertEqual(data['id'], transaction.pk)
                    self.assertTrue(set(data).issubset(allowed), set(data) - allowed)
        for pk in excluded_ids:
            for url in aliases(f'/api/transactions/{pk}/'):
                with self.subTest(url=url):
                    self.assert_hidden(client, url, 'A04_PAYROLL')

    def test_observer_cannot_read_transaction_routes_or_aliases(self):
        client = self.client_for('observer')
        for url in aliases('/api/transactions/') + aliases(f'/api/transactions/{self.transactions[0].pk}/'):
            with self.subTest(url=url):
                response = client.get(url)
                self.assertIn(response.status_code, (403, 404))
                self.assert_no_canaries(text_body(response), self.FINANCE_AMOUNTS)

    def test_observer_counterparties_have_no_financial_aggregates(self):
        client = self.client_for('observer')
        for url in aliases('/api/counterparties/') + aliases(f'/api/counterparties/{self.customer.pk}/'):
            with self.subTest(url=url):
                data = self.json_get(client, url)
                self.assert_no_money(data)
                self.assertIn(self.customer.name, json.dumps(data, ensure_ascii=False))


class A04AggregateReadTests(A04SyntheticCase):
    def test_observer_snapshot_retains_operations_without_money_or_private_records(self):
        client = self.grant('observer', 'view_document')
        data = self.json_get(client, '/api/erp/snapshot/')
        self.assertIn(self.item.pk, [x['id'] for x in data['items']])
        self.assertIn(self.lot.pk, [x['id'] for x in data['lots']])
        self.assertEqual(next(x for x in data['lots'] if x['id'] == self.lot.pk)['quantity'], '12.000')
        self.assert_no_money(data)
        self.assert_no_canaries(data, (self.HIDDEN, self.HIDDEN_VERSION, self.MANAGEMENT, self.hidden_order.code, self.hidden_lot.code))

    def test_manager_snapshot_retains_allowed_procurement_prices_not_ceo_sources(self):
        client = self.grant('manager', 'view_document')
        data = self.json_get(client, '/api/erp/snapshot/')
        purchase = next(p for p in data['purchases'] if p['id'] == self.purchase.pk)
        self.assertEqual(Decimal(purchase['price']), Decimal(self.purchase.price))
        self.assert_no_canaries(data, (self.HIDDEN, self.HIDDEN_VERSION) + self.PAYROLL_AMOUNTS)
        self.assertNotIn(self.hidden_item.pk, [x['id'] for x in data['items']])

    def test_dashboard_summary_and_helicopter_have_no_financial_side_channel(self):
        for role in ('manager', 'observer'):
            client = self.client_for(role)
            for url in ('/api/dashboard/summary/', '/api/dashboard/helicopter/'):
                with self.subTest(role=role, url=url):
                    data = self.json_get(client, url)
                    self.assert_no_money(data)
                    if 'dimensions' in data:
                        self.assertNotIn('finance', [d['key'] for d in data['dimensions']])
                    if 'fires' in data:
                        self.assertFalse(any(f.get('dimension') == 'finance' for f in data['fires']))
                    if 'branches_health' in data:
                        self.assertTrue(all('pct' not in x for x in data['branches_health']))

    def test_dashboard_activity_hides_hr_events_but_ceo_can_read_them(self):
        ceo = self.json_get(self.client_for('ceo'), '/api/dashboard/activity/')
        self.assertIn('A04_HR_EVENT_SECRET', json.dumps(ceo, ensure_ascii=False))
        for role in ('manager', 'observer'):
            data = self.json_get(self.client_for(role), '/api/dashboard/activity/')
            self.assert_no_canaries(data, ('A04_HR_EVENT_SECRET', self.HR_PHONE, self.HR_EMAIL))

    def test_operations_summary_finance_is_filtered_for_non_ceo(self):
        ceo = self.json_get(self.client_for('ceo'), '/api/operations/summary/')
        self.assertEqual(set(ceo['receivables']), {'EUR', 'USD', 'UAH'})
        for role in ('manager', 'observer'):
            with self.subTest(role=role):
                data = self.json_get(self.client_for(role), '/api/operations/summary/')
                self.assertIn(self.task.pk, [t['id'] for t in data['overdue_tasks']])
                self.assert_no_money(data)

    def test_audit_payload_is_filtered_before_response(self):
        for role in ('manager', 'observer'):
            with self.subTest(role=role):
                data = self.json_get(self.grant(role, 'view_document'), '/api/operations/audit/')
                self.assert_no_canaries(data, (self.HIDDEN,) + self.PAYROLL_AMOUNTS)
                if role == 'observer':
                    self.assert_no_money(data)

    def test_hidden_erp_order_and_change_have_no_detail_draft_or_next_route(self):
        for role in ('manager', 'observer'):
            client = self.grant(role, 'view_document')
            for url in (f'/api/erp/orders/{self.hidden_order.pk}/next/',
                        f'/api/erp/orders/{self.hidden_order.pk}/draft/',
                        f'/api/erp/changes/{self.hidden_change.pk}/impact/'):
                with self.subTest(role=role, url=url):
                    self.assert_hidden(client, url)

    def test_observer_next_step_cannot_disclose_payment_amount_or_ceo_action(self):
        client = self.grant('observer', 'view_document')
        data = self.json_get(client, f'/api/erp/orders/{self.order.pk}/next/')
        self.assert_no_money(data)
        self.assertNotEqual((data.get('payload') or {}).get('action'), 'erp_payment')


class A04DocumentReadTests(A04SyntheticCase):
    def test_document_classification_defaults_and_chat_owner_schema_exist(self):
        doc_fields = {f.name: f for f in Document._meta.fields}
        self.assertIn('access_level', doc_fields)
        self.assertEqual(doc_fields['access_level'].get_default(), 'ceo')
        self.assertEqual(Document.objects.get(pk=self.legacy_doc.pk).access_level, 'ceo')
        chat_fields = {f.name: f for f in ChatMessage._meta.fields}
        self.assertIn('user', chat_fields)
        self.assertTrue(chat_fields['user'].null)
        self.assertIn('visibility_role', chat_fields)
        self.assertIn('archived_at', chat_fields)
        for codename in ('view_document', 'download_document', 'export_workspace'):
            self.assertTrue(Permission.objects.filter(content_type__app_label='operations', codename=codename).exists(), codename)

    def test_document_permission_is_separate_from_business_role(self):
        for role in ('manager', 'observer'):
            client = self.client_for(role)
            response = client.get('/api/operations/documents/')
            self.assertEqual(response.status_code, 403)
            self.assert_hidden(client, f'/api/operations/documents/{self.public_doc.pk}/', self.public_doc.code)

    def test_document_levels_filter_all_rows_for_each_role(self):
        expectations = {
            'ceo': {self.public_doc.pk, self.management_doc.pk, self.hidden_doc.pk, self.legacy_doc.pk},
            'manager': {self.public_doc.pk, self.management_doc.pk},
            'observer': {self.public_doc.pk},
        }
        all_ids = {self.public_doc.pk, self.management_doc.pk, self.hidden_doc.pk, self.legacy_doc.pk}
        for role, expected in expectations.items():
            with self.subTest(role=role):
                client = self.grant(role, 'view_document')
                data = rows(self.json_get(client, '/api/operations/documents/'))
                self.assertEqual({d['id'] for d in data}.intersection(all_ids), expected)
                for doc_id in all_ids - expected:
                    self.assert_hidden(client, f'/api/operations/documents/{doc_id}/')

    def test_hidden_versions_do_not_hide_visible_version_or_leak_metadata_hits(self):
        for role in ('manager', 'observer'):
            client = self.grant(role, 'view_document')
            listing = rows(self.json_get(client, '/api/operations/documents/?q=A04-VERSIONS'))
            self.assertEqual([d['id'] for d in listing], [self.public_version.pk])
            detail = self.json_get(client, f'/api/operations/documents/{self.public_version.pk}/')
            self.assertEqual({d['id'] for d in detail['versions']}, {self.public_version.pk})
            self.assertNotIn(self.hidden_version_request.code, detail['related_requests'])
            self.assert_no_canaries(detail, (self.HIDDEN_VERSION, self.hidden_version.checksum))
            search = self.json_get(client, '/api/operations/documents/?q=' + self.HIDDEN_VERSION)
            self.assertEqual(rows(search), [])

    def test_request_list_compare_and_rfq_share_document_scope(self):
        for role in ('manager', 'observer'):
            client = self.grant(role, 'view_document')
            data = rows(self.json_get(client, '/api/operations/requests/'))
            codes = {row['code'] for row in data}
            self.assertIn('R01', codes)
            self.assertNotIn('R02', codes)
            self.assertEqual('R03' in codes, role == 'manager')
            for url in ('/api/operations/compare/?code=R02', '/api/operations/compare/?code=R02&quantity=25',
                        '/api/operations/rfq/R02/'):
                with self.subTest(role=role, url=url):
                    self.assert_hidden(client, url)

    def test_compare_keeps_allowed_quotes_without_hidden_rows_or_observer_prices(self):
        for role in ('manager', 'observer'):
            client = self.grant(role, 'view_document')
            data = self.json_get(client, '/api/operations/compare/?code=R01&quantity=25')
            codes = {row['code'] for row in data['rows']}
            self.assertIn('Q11', codes)
            self.assertNotIn('Q12', codes)
            self.assertEqual('Q13' in codes, role == 'manager')
            if role == 'observer':
                self.assert_no_money(data)
                self.assertTrue(all('total' not in row for row in data['rows']))
            else:
                visible = next(row for row in data['rows'] if row['code'] == 'Q11')
                self.assertEqual(Decimal(visible['total']), Decimal('4567.89') * 25 + Decimal('121.57'))

    def test_contract_details_aliases_respect_document_scope_and_financial_fields(self):
        for role in ('manager', 'observer'):
            client = self.grant(role, 'view_document')
            for url in aliases('/api/contracts/'):
                data = rows(self.json_get(client, url))
                ids = {row['id'] for row in data}
                self.assertIn(self.contracts['operational'].pk, ids)
                self.assertNotIn(self.contracts['ceo'].pk, ids)
                if role == 'observer':
                    self.assertNotIn(self.contracts['management'].pk, ids)
                    self.assert_no_money(data)
            for url in aliases(f'/api/contracts/{self.contracts["ceo"].pk}/'):
                self.assert_hidden(client, url, self.contracts['ceo'].number)
            for url in aliases(f'/api/contracts/{self.contracts["operational"].pk}/'):
                data = self.json_get(client, url)
                self.assertEqual(data['id'], self.contracts['operational'].pk)
                if role == 'observer':
                    self.assert_no_money(data)

    def test_download_capability_required_even_for_ceo_and_preserves_scope(self):
        for role in ('ceo', 'manager', 'observer'):
            client = self.grant(role, 'view_document')
            url = f'/api/operations/documents/{self.public_doc.pk}/download/'
            denied = client.get(url)
            self.assertEqual(denied.status_code, 403)
            self.assert_no_canaries(text_body(denied), (self.public_doc.text,))
            self.grant(role, 'download_document')
            allowed = client.get(url)
            self.assertEqual(allowed.status_code, 200)
            self.assertEqual(body_bytes(allowed), bytes(self.public_doc.content))
            if role != 'ceo':
                self.assert_hidden(client, f'/api/operations/documents/{self.hidden_doc.pk}/download/')

    def test_revoking_document_permissions_affects_existing_session_immediately(self):
        client = self.grant('manager', 'view_document', 'download_document')
        self.json_get(client, f'/api/operations/documents/{self.public_doc.pk}/')
        allowed = client.get(f'/api/operations/documents/{self.public_doc.pk}/download/')
        self.assertEqual(allowed.status_code, 200)
        body_bytes(allowed)
        self.users['manager'].user_permissions.clear()
        self.assert_hidden(client, f'/api/operations/documents/{self.public_doc.pk}/', self.public_doc.code)
        denied = client.get(f'/api/operations/documents/{self.public_doc.pk}/download/')
        self.assertIn(denied.status_code, (403, 404))
        self.assert_no_canaries(text_body(denied), (self.public_doc.text,))


class A04ExportTests(A04SyntheticCase):
    def test_ceo_and_manager_need_explicit_export_permission(self):
        for role in ('ceo', 'manager'):
            client = self.grant(role, 'view_document')
            for url in ('/api/erp/export/', '/api/operations/export/'):
                with self.subTest(role=role, url=url):
                    response = client.get(url)
                    self.assertEqual(response.status_code, 403)
                    self.assert_no_canaries(text_body(response), (self.HIDDEN,) + self.FINANCE_AMOUNTS)

    def test_observer_cannot_export_even_with_export_permission(self):
        client = self.grant('observer', 'view_document', 'export_workspace')
        for url in ('/api/erp/export/', '/api/operations/export/'):
            response = client.get(url)
            self.assertEqual(response.status_code, 403)
            self.assert_no_canaries(text_body(response), (self.HIDDEN,) + self.FINANCE_AMOUNTS)

    def test_export_is_a_projection_of_allowed_data_not_an_unfiltered_database(self):
        for role in ('ceo', 'manager'):
            client = self.grant(role, 'view_document', 'export_workspace')
            for url in ('/api/erp/export/', '/api/operations/export/'):
                with self.subTest(role=role, url=url):
                    data = self.json_get(client, url)
                    erp = data.get('erp', data)
                    self.assertIn(self.item.pk, [row['id'] for row in erp['items']])
                    if role == 'manager':
                        self.assert_no_canaries(data, (self.HIDDEN, self.HIDDEN_VERSION) + self.PAYROLL_AMOUNTS)
                        self.assertNotIn(self.hidden_doc.pk, [row['id'] for row in erp['documents']])
                    else:
                        self.assertIn(self.hidden_doc.pk, [row['id'] for row in erp['documents']])

    def test_export_permission_revocation_applies_without_new_login(self):
        client = self.grant('manager', 'view_document', 'export_workspace')
        self.json_get(client, '/api/erp/export/')
        self.users['manager'].user_permissions.remove(Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Document), codename='export_workspace'))
        for url in ('/api/erp/export/', '/api/operations/export/'):
            self.assertEqual(client.get(url).status_code, 403)


class A04ProposalAccessTests(A04SyntheticCase):
    def test_manager_cannot_preview_ceo_only_actions_on_either_adapter(self):
        client = self.grant('manager', 'view_document')
        payloads = [
            {'action': 'erp_payment', 'invoice_id': self.invoices[0].pk,
             'amount': '1', 'reference': 'A04-UNAUTHORIZED-PAY'},
            {'action': 'erp_opening', 'item_id': self.item.pk, 'location_id': self.location.pk,
             'code': 'A04-UNAUTHORIZED-OPENING', 'revision': 'A', 'quantity': '2',
             'unit_cost': '1', 'currency': 'EUR', 'documents': {}},
        ]
        before = (ActionProposal.objects.count(), Lot.objects.count(), Invoice.objects.get(pk=self.invoices[0].pk).paid)
        for url in ('/api/erp/preview/', '/api/operations/preview/'):
            for payload in payloads:
                with self.subTest(url=url, action=payload['action']):
                    response = self.post(client, url, payload)
                    self.assertEqual(response.status_code, 403, text_body(response))
        self.assertEqual((ActionProposal.objects.count(), Lot.objects.count(),
                          Invoice.objects.get(pk=self.invoices[0].pk).paid), before)

    def test_hidden_document_references_cannot_be_previewed_via_either_adapter(self):
        client = self.grant('manager', 'view_document')
        payload = {'action': 'erp_attach', 'lot_id': self.lot.pk,
                   'kind': 'certificate', 'document_id': self.hidden_doc.pk}
        before = (ActionProposal.objects.count(), Event.objects.count(), Lot.objects.get(pk=self.lot.pk).documents)
        for url in ('/api/erp/preview/', '/api/operations/preview/'):
            with self.subTest(url=url):
                response = self.post(client, url, payload)
                self.assertEqual(response.status_code, 404, text_body(response))
                self.assert_no_canaries(text_body(response), (self.HIDDEN,))
        self.assertEqual((ActionProposal.objects.count(), Event.objects.count(),
                          Lot.objects.get(pk=self.lot.pk).documents), before)

    def test_task_preview_cannot_reference_hidden_procurement_request(self):
        client = self.grant('manager', 'view_document')
        before = ActionProposal.objects.count()
        response = self.post(client, '/api/operations/preview/', {
            'action': 'create_task', 'title': 'A04 прихований контекст', 'assignee_id': self.employee.pk,
            'deadline': (self.today + timedelta(days=5)).isoformat(), 'request_code': 'R02',
        })
        self.assertEqual(response.status_code, 404)
        self.assertEqual(ActionProposal.objects.count(), before)

    def test_confirm_rechecks_document_capability_after_preview(self):
        client = self.grant('manager', 'view_document')
        response = self.post(client, '/api/operations/preview/', {
            'action': 'create_task', 'title': 'A04 відкритий запит', 'assignee_id': self.employee.pk,
            'deadline': (self.today + timedelta(days=5)).isoformat(), 'request_code': 'R01',
        })
        self.assertEqual(response.status_code, 200, text_body(response))
        proposal_id = response.json()['id']
        before = (Task.objects.count(), AuditEvent.objects.count())
        self.users['manager'].user_permissions.clear()
        denied = self.post(client, '/api/operations/confirm/', {'proposal_id': proposal_id, 'confirmed': True})
        self.assertIn(denied.status_code, (403, 404))
        self.assertEqual((Task.objects.count(), AuditEvent.objects.count()), before)
        self.assertIsNone(ActionProposal.objects.get(pk=proposal_id).receipt)


class A04AssistantAccessTests(A04SyntheticCase):
    def test_local_assistant_observer_has_no_financial_answer_or_hidden_sources(self):
        client = self.grant('observer', 'view_document')
        before = (Task.objects.count(), Event.objects.count(), ActionProposal.objects.count())
        for prompt in ('Що потребує уваги?', 'Покажи ERP собівартість та рахунки',
                       'Порівняй R01', 'Хто відповідає за R02?', 'Покажи A04-SO-HIDDEN'):
            with self.subTest(prompt=prompt):
                response = self.post(client, '/api/operations/chat/', {'message': prompt})
                self.assertIn(response.status_code, (200, 404))
                data = response.json()
                self.assert_no_canaries(data, self.FINANCE_AMOUNTS + self.PAYROLL_AMOUNTS +
                                        (self.HIDDEN, 'Q12', self.hidden_order.code, 'R02:', '4567.89', '13825.24'))
                self.assert_no_money(data)
        self.assertEqual((Task.objects.count(), Event.objects.count(), ActionProposal.objects.count()), before)

    def test_local_assistant_manager_keeps_allowed_comparison_but_no_closed_sources(self):
        client = self.grant('manager', 'view_document')
        response = self.post(client, '/api/operations/chat/', {'message': 'Порівняй R01'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('Q11', json.dumps(data, ensure_ascii=False))
        self.assertIn('13825.24', json.dumps(data, ensure_ascii=False))
        self.assert_no_canaries(data, (self.HIDDEN, 'Q12') + self.PAYROLL_AMOUNTS)

    def test_legacy_context_uses_request_and_ignores_global_finance_cache(self):
        from ai_assistant import views
        for role in ('ceo', 'manager', 'observer'):
            self.grant(role, 'view_document')
        ceo_context = views._build_finance_context(self.scoped_request('ceo'))
        self.assertIn(self.contracts['ceo'].number, ceo_context)
        cache.set('ctx_finance', 'A04_GLOBAL_CACHE_CEO_SECRET ' + self.FINANCE_AMOUNTS[0], 300)
        cache.set('ctx_employees', 'A04_GLOBAL_CACHE_HR_SECRET ' + self.HR_PHONE, 300)
        for role in ('manager', 'observer'):
            request = self.scoped_request(role)
            finance = views._build_finance_context(request)
            staff = views._build_employees_context(request)
            self.assert_no_canaries(finance, self.FINANCE_AMOUNTS + self.PAYROLL_AMOUNTS +
                                    ('A04_GLOBAL_CACHE_CEO_SECRET', self.contracts['ceo'].number))
            self.assert_no_canaries(staff, ('A04_GLOBAL_CACHE_HR_SECRET', self.HR_PHONE, self.HR_EMAIL))
            self.assertIn(self.employee.full_name, staff)

    def test_context_rechecks_actual_group_and_document_permission_without_cache(self):
        from ai_assistant import views
        self.grant('ceo', 'view_document')
        request = self.scoped_request('ceo')
        first = views._build_finance_context(request)
        self.assertIn(self.contracts['ceo'].number, first)
        self.users['ceo'].groups.set([Group.objects.get_or_create(name='observer')[0]])
        after = views._build_finance_context(request)
        self.assert_no_canaries(after, self.FINANCE_AMOUNTS + self.PAYROLL_AMOUNTS +
                                (self.contracts['ceo'].number, self.contracts['management'].number))
        self.users['ceo'].user_permissions.clear()
        after_revoke = views._build_finance_context(request)
        self.assert_no_canaries(after_revoke, (self.contracts['operational'].number,))

    def test_context_without_principal_cannot_read_business_sources(self):
        from ai_assistant import views
        from django.contrib.auth.models import AnonymousUser
        request = RequestFactory().get('/api/chat/')
        request.user = AnonymousUser()
        request.session = {}
        for builder in (views._build_tasks_context, views._build_employees_context, views._build_finance_context):
            with self.subTest(builder=builder.__name__):
                # TypeError is intentionally not an accepted access decision.
                with self.assertRaises(PermissionError):
                    builder(request)

    def test_chat_history_is_owned_and_legacy_null_owner_never_leaks(self):
        self.message('ceo', 'A04_CEO_CHAT_PRIVATE')
        self.message('manager', 'A04_MANAGER_CHAT_OWN')
        self.message('observer', 'A04_OBSERVER_CHAT_OWN')
        ChatMessage.objects.create(role='assistant', content='A04_LEGACY_UNOWNED_CHAT_SECRET')
        for role, own in (('ceo', 'A04_CEO_CHAT_PRIVATE'), ('manager', 'A04_MANAGER_CHAT_OWN'),
                          ('observer', 'A04_OBSERVER_CHAT_OWN')):
            with self.subTest(role=role):
                data = self.json_get(self.client_for(role), '/api/chat/history/')
                encoded = json.dumps(data, ensure_ascii=False)
                self.assertIn(own, encoded)
                self.assert_no_canaries(data, tuple(x for x in ('A04_CEO_CHAT_PRIVATE', 'A04_MANAGER_CHAT_OWN',
                                                                'A04_OBSERVER_CHAT_OWN', 'A04_LEGACY_UNOWNED_CHAT_SECRET') if x != own))

    def test_ceo_history_stays_private_after_same_owner_is_downgraded(self):
        self.message('ceo', 'A04_PRIOR_CEO_ONLY ' + self.FINANCE_AMOUNTS[0])
        client = self.client_for('ceo')
        self.assertIn('A04_PRIOR_CEO_ONLY', json.dumps(self.json_get(client, '/api/chat/history/')))
        for role in ('manager', 'observer'):
            self.users['ceo'].groups.set([Group.objects.get_or_create(name=role)[0]])
            data = self.json_get(client, '/api/chat/history/')
            self.assert_no_canaries(data, ('A04_PRIOR_CEO_ONLY', self.FINANCE_AMOUNTS[0]))

    def test_own_history_delete_archives_preserving_foreign_rows_files_and_bytes(self):
        for role in ('ceo', 'manager'):
            with self.subTest(role=role), TemporaryDirectory(prefix='bos-a04-archive-') as media:
                with override_settings(MEDIA_ROOT=media):
                    own = self.message(role, 'A04_OWN_TO_ARCHIVE_' + role)
                    foreign = self.message('observer', 'A04_FOREIGN_PRESERVE_' + role)
                    legacy = ChatMessage.objects.create(role='assistant', content='A04_UNOWNED_PRESERVE_' + role)
                    attached = ChatFile(chat_message=own, original_name='A04_ARCHIVE_' + role + '.txt',
                                        mime_type='text/plain', size=23)
                    attached.file.save('A04_ARCHIVE_' + role + '.txt', ContentFile(b'A04_ARCHIVE_KEEP_BYTES'), save=True)
                    before_ids = set(ChatMessage.objects.values_list('pk', flat=True))
                    before_file_ids = set(ChatFile.objects.values_list('pk', flat=True))
                    client = self.client_for(role)
                    response = client.delete('/api/chat/history/',
                                             HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
                    self.assertIn(response.status_code, (200, 204))
                    self.assertEqual(set(ChatMessage.objects.values_list('pk', flat=True)), before_ids)
                    self.assertEqual(set(ChatFile.objects.values_list('pk', flat=True)), before_file_ids)
                    own.refresh_from_db()
                    foreign.refresh_from_db()
                    legacy.refresh_from_db()
                    self.assertIsNotNone(getattr(own, 'archived_at', None))
                    self.assertIsNone(getattr(foreign, 'archived_at', None))
                    self.assertIsNone(getattr(legacy, 'archived_at', None))
                    attached.refresh_from_db()
                    self.assertEqual(attached.chat_message_id, own.pk)
                    with attached.file.open('rb') as saved:
                        self.assertEqual(saved.read(), b'A04_ARCHIVE_KEEP_BYTES')
                    history = self.json_get(client, '/api/chat/history/')
                    self.assert_no_canaries(history, ('A04_OWN_TO_ARCHIVE_' + role, attached.original_name))

    def test_observer_cannot_archive_chat_history(self):
        own = self.message('observer', 'A04_OBSERVER_KEEP_HISTORY')
        client = self.client_for('observer')
        before_ids = set(ChatMessage.objects.values_list('pk', flat=True))
        response = client.delete('/api/chat/history/',
                                 HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(set(ChatMessage.objects.values_list('pk', flat=True)), before_ids)
        own.refresh_from_db()
        self.assertIsNone(getattr(own, 'archived_at', None))
        history = self.json_get(client, '/api/chat/history/')
        self.assertIn('A04_OBSERVER_KEEP_HISTORY', json.dumps(history))

    def test_private_chat_file_cannot_leak_through_other_history_or_public_media(self):
        with TemporaryDirectory(prefix='bos-a04-private-') as media:
            with override_settings(MEDIA_ROOT=media):
                message = self.message('ceo', 'A04_FILE_MESSAGE_PRIVATE')
                attached = ChatFile(chat_message=message, original_name='A04_PRIVATE_CHAT_FILENAME.txt',
                                    mime_type='text/plain', size=31, parsed_text='A04_PRIVATE_CHAT_PARSED_TEXT')
                attached.file.save('A04_PRIVATE_CHAT_FILE.txt', ContentFile(b'A04_PRIVATE_CHAT_BYTES'), save=True)
                for role in ('manager', 'observer'):
                    data = self.json_get(self.client_for(role), '/api/chat/history/')
                    self.assert_no_canaries(data, ('A04_FILE_MESSAGE_PRIVATE', attached.original_name,
                                                   attached.parsed_text, attached.file.name))
                for client in (Client(), self.client_for('ceo'), self.client_for('manager'), self.client_for('observer')):
                    response = client.get(attached.file.url)
                    self.assertEqual(response.status_code, 404)
                    self.assertNotIn('A04_PRIVATE_CHAT_BYTES', text_body(response))


class A04BoundaryReadTests(A04SyntheticCase):
    def test_anonymous_cannot_read_any_current_business_get_surface(self):
        client = Client()
        urls = [
            '/api/', '/api/tasks/', f'/api/tasks/{self.task.pk}/', '/api/branches/',
            '/api/dashboard/summary/', '/api/dashboard/helicopter/', '/api/dashboard/activity/',
            '/api/operations/portfolio/', '/api/operations/status/', '/api/runtime/status/',
            '/api/operations/requests/', '/api/operations/compare/?code=R01', '/api/operations/summary/',
            '/api/operations/documents/', f'/api/operations/documents/{self.public_doc.pk}/',
            f'/api/operations/documents/{self.public_doc.pk}/download/', '/api/operations/audit/',
            '/api/operations/export/', '/api/operations/rfq/R01/', '/api/erp/snapshot/', '/api/erp/export/',
            f'/api/erp/orders/{self.order.pk}/next/', f'/api/erp/orders/{self.order.pk}/draft/',
            f'/api/erp/changes/{self.change.pk}/impact/', '/api/chat/history/',
        ]
        for path in ('/api/employees/', f'/api/employees/{self.employee.pk}/',
                     '/api/counterparties/', f'/api/counterparties/{self.customer.pk}/',
                     '/api/contracts/', f'/api/contracts/{self.contracts["operational"].pk}/',
                     '/api/transactions/', f'/api/transactions/{self.transactions[0].pk}/',
                     '/api/salaries/', f'/api/salaries/{self.salaries[0].pk}/'):
            urls.extend(aliases(path))
        for url in urls:
            with self.subTest(url=url):
                response = client.get(url)
                self.assertIn(response.status_code, (401, 403))
                self.assert_no_canaries(text_body(response), (self.HR_PHONE, self.HR_EMAIL, self.HIDDEN) + self.FINANCE_AMOUNTS)
        self.assertNotIn('_auth_user_id', client.session)

    def test_head_options_and_json_aliases_do_not_expose_forbidden_salary_data(self):
        for role in ('manager', 'observer'):
            client = self.client_for(role)
            for url in aliases('/api/salaries/') + aliases(f'/api/salaries/{self.salaries[0].pk}/'):
                for method in ('head', 'options'):
                    with self.subTest(role=role, url=url, method=method):
                        response = getattr(client, method)(url)
                        self.assertIn(response.status_code, (200, 403, 404, 405))
                        self.assert_no_canaries(text_body(response) + str(dict(response.headers)),
                                                self.PAYROLL_AMOUNTS + ('A04_PAYROLL_SECRET', self.HR_EMAIL))
