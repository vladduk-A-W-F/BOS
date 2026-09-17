"""Synthetic fixture adapter for check_access; never reads production data."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import importlib
import json

from django import forms
from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import model_to_dict
from django.test import Client, RequestFactory


class SweepFixtures:
    def __init__(self, module):
        self.module = module
        self.issues = []
        self.password = 'Synthetic-access-gate-password-2026'
        self.users = {}
        self.cookies = {}
        self.api = {}
        self.admin = {}

    def build(self):
        from scripts.check_support import login_test_client
        from employees.models import Employee
        from finance.models import Salary, Transaction, Counterparty, Contract
        from tasks.models import Task
        from branches.models import Branch
        from operations.models import Document
        from ai_assistant.models import ChatMessage, ChatFile, ClaudeUsageLog, TaskChangeLog, EmployeeChangeLog
        source = importlib.import_module(self.module)
        self.seed = source.A04SyntheticCase(methodName='runTest')
        self.seed.setUpTestData()
        self.seed.setUp()
        self.today = date.today()
        self.future = (self.today + timedelta(days=90)).isoformat()
        User = get_user_model()
        for role in ('ceo', 'manager', 'observer'):
            client = Client(enforce_csrf_checks=True)
            user = login_test_client(client, role)
            # Keep known valid credentials for auth-route positive controls.
            user.set_password(self.password)
            user.save(update_fields=['password'])
            # Password change invalidates the old session; use another real login.
            response = client.post('/api/auth/login/', {'username': user.username, 'password': self.password},
                content_type='application/json', HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
            if response.status_code != 200:
                raise ValueError('synthetic_business_login_failed:' + role + ':' + str(response.status_code))
            self.users[role] = user
            self.cookies[role] = deepcopy(client.cookies)
        tech = User.objects.create_superuser('a04-technical-admin', 'tech@example.invalid', self.password)
        if tech.groups.exists():
            raise ValueError('Technical administrator must have no BoS Group')
        self.users['technical_admin'] = tech
        client = Client(enforce_csrf_checks=True)
        client.get('/admin/login/')
        response = client.post('/admin/login/', {'username': tech.username, 'password': self.password, 'next': '/admin/'},
            HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
        if response.status_code != 302 or client.session.get('_auth_user_id') != str(tech.pk):
            raise ValueError('genuine_staff_login_failed')
        self.cookies['technical_admin'] = deepcopy(client.cookies)
        anon = Client(enforce_csrf_checks=True)
        if anon.get('/api/auth/csrf/').status_code != 200:
            raise ValueError('csrf_bootstrap_failed')
        self.cookies['anonymous'] = deepcopy(anon.cookies)
        ct = ContentType.objects.get_for_model(Document)
        for role in ('ceo', 'manager', 'observer'):
            codenames = ['download_document']
            if role in ('manager', 'observer'):
                codenames.append('view_document')
            if role in ('ceo', 'manager'):
                codenames.append('export_workspace')
            for codename in codenames:
                perm = Permission.objects.filter(content_type=ct, codename=codename).first()
                if perm is None:
                    self.issues.append('missing_migrated_permission:operations.' + codename)
                    # Preserve runnable red route evidence, but never green a missing capability migration.
                    perm = Permission.objects.create(content_type=ct, codename=codename, name='Synthetic access gate ' + codename)
                self.users[role].user_permissions.add(perm)
        for model, fields in ((Document, {'access_level'}), (ChatMessage, {'user', 'visibility_role', 'archived_at'})):
            missing = fields - {f.name for f in model._meta.fields}
            if missing:
                self.issues.append('missing_schema:' + model._meta.label_lower + ':' + ','.join(sorted(missing)))

        self.api['tasks'] = Task.objects.create(title='A04 ROUTE TASK', assignee=self.seed.employee.full_name, deadline=self.future)
        self.api['employees'] = Employee.objects.create(full_name='A04 ROUTE EMPLOYEE', role='Операції',
            phone=self.seed.HR_PHONE, email=self.seed.HR_EMAIL, birthday=self.seed.HR_DATE)
        self.api['counterparties'] = Counterparty.objects.create(name='A04 ROUTE COUNTERPARTY', type='other')
        free_cp = Counterparty.objects.create(name='A04 CONTRACT SUPPORT', type='supplier')
        self.api['contracts'] = Contract.objects.create(number='A04-ROUTE-CONTRACT', name='A04 ROUTE CONTRACT',
            counterparty=free_cp, amount='19.23', currency='EUR', status='draft')
        # Operational contract ownership/scope must be represented by a real document.
        self.seed.make_document('A04-ROUTE-CONTRACT-DOC', 'operational', contract=self.api['contracts'])
        self.api['transactions'] = Transaction.objects.create(direction='out', category='other',
            description='A04 ROUTE TRANSACTION', amount='119.23', currency='EUR', date=self.today)
        salary_employee = Employee.objects.create(full_name='A04 ROUTE PAYROLL EMPLOYEE', role='Операції')
        self.api['salaries'] = Salary.objects.create(employee=salary_employee, amount='91827.43', currency='EUR',
            period_year=self.today.year, period_month=12, notes='A04_ROUTE_PRIVATE_SALARY')
        self.chat_markers = {}
        for role in ('ceo', 'manager', 'observer'):
            marker = 'A04_ROUTE_OWN_CHAT_' + role.upper()
            self.chat_markers[role] = marker
            kwargs = {'role': 'assistant', 'content': marker}
            fields = {f.name for f in ChatMessage._meta.fields}
            if 'user' in fields:
                kwargs['user'] = self.users[role]
            if 'visibility_role' in fields:
                kwargs['visibility_role'] = role
            ChatMessage.objects.create(**kwargs)

        # Admin detail/bulk fixtures are deliberately unlinked to protected history;
        # A05's linked-history 409 cases are exercised by its separate regressions.
        self.admin['auth.group'] = Group.objects.create(name='A04 ROUTE MUTABLE GROUP')
        self.admin['auth.user'] = User.objects.create_user('a04-route-mutable-user', password=self.password)
        self.admin['tasks.task'] = Task.objects.create(title='A04 ADMIN TASK', assignee='A04 Operator', deadline=self.future)
        self.admin['employees.employee'] = Employee.objects.create(full_name='A04 ADMIN EMPLOYEE', role='Операції')
        self.admin['finance.counterparty'] = Counterparty.objects.create(name='A04 ADMIN COUNTERPARTY', type='other')
        cp = Counterparty.objects.create(name='A04 ADMIN CONTRACT SUPPORT', type='other')
        self.admin['finance.contract'] = Contract.objects.create(number='A04-ADMIN-CT', name='A04 ADMIN CONTRACT', counterparty=cp, status='draft')
        self.admin['finance.transaction'] = Transaction.objects.create(direction='out', category='other',
            description='A04 ADMIN TRANSACTION', amount='23.45', currency='UAH', date=self.today)
        emp = Employee.objects.create(full_name='A04 ADMIN PAYROLL SUPPORT', role='Операції')
        self.admin['finance.salary'] = Salary.objects.create(employee=emp, amount='123.45', currency='USD',
            period_year=self.today.year, period_month=12)
        self.admin['branches.branch'] = Branch.objects.create(code='A04-ADMIN-BRANCH', name='A04 ADMIN BRANCH')
        msg = ChatMessage.objects.create(role='assistant', content='A04 ADMIN PRIVATE CHAT')
        self.admin['ai_assistant.chatmessage'] = msg
        chatfile = ChatFile(chat_message=msg, original_name='A04_ADMIN_PRIVATE_FILE.txt', mime_type='text/plain', size=22,
                            parsed_text='A04 ADMIN PRIVATE FILE')
        chatfile.file.save('A04_ADMIN_PRIVATE_FILE.txt', ContentFile(b'A04 ADMIN PRIVATE FILE'), save=True)
        self.admin['ai_assistant.chatfile'] = chatfile
        self.admin['ai_assistant.taskchangelog'] = TaskChangeLog.objects.create(action='update', task_id=self.api['tasks'].pk,
            task_title='A04 ADMIN TASK LOG', before={'title': 'old'}, after={'title': 'new'})
        self.admin['ai_assistant.employeechangelog'] = EmployeeChangeLog.objects.create(action='update',
            employee_id=self.seed.employee.pk, employee_name='A04 ADMIN PRIVATE EMPLOYEE LOG',
            before={'phone': self.seed.HR_PHONE}, after={'phone': self.seed.HR_PHONE})
        self.admin['ai_assistant.claudeusagelog'] = ClaudeUsageLog.objects.create(endpoint='chat',
            model='A04 ADMIN PRIVATE USAGE', input_tokens=1, output_tokens=1, chat_message=msg)
        registered = {model._meta.label_lower for model in admin.site._registry}
        if registered != set(self.admin):
            raise ValueError('unmapped_admin_fixtures:' + repr(registered ^ set(self.admin)))
        for instance in list(self.admin.values()) + list(self.api.values()):
            if not type(instance)._base_manager.filter(pk=instance.pk).exists():
                raise ValueError('missing_existing_fixture:' + instance._meta.label_lower)
        self.business_models = [m for m in apps.get_models(include_auto_created=True) if m._meta.app_label in
            {'auth', 'tasks', 'employees', 'finance', 'erp', 'operations', 'ai_assistant', 'branches'}
            and m._meta.model_name != 'loginattempt']
        self.baseline_proposal = self.preview_task(self.client('ceo'))
        # B02 receipt fixture uses a genuine approved binding-only import; no
        # earlier business rows/history are changed or synthesized as approvals.
        from erp.importing import source_totals
        from operations.service import as_of
        from uuid import uuid4
        batch={'format':'bos.initial-import.v1','batch_id':str(uuid4()),'namespace':'a04-import-fixture','cutover':str(as_of()),
            'tax_basis':'excluding_VAT','rows':[],'bindings':[{'entity':'counterparty','external_id':'A04-IMPORT-BOUND','target_id':free_cp.pk}],
            'expected_source_control_totals':source_totals([])}
        client=self.client('ceo');csrf=client.cookies[settings.CSRF_COOKIE_NAME].value
        preview=client.post('/api/erp/import/preview/',batch,content_type='application/json',HTTP_X_CSRFTOKEN=csrf)
        if preview.status_code!=200:raise ValueError('import_fixture_preview_failed:'+str(preview.status_code))
        receipt=client.post('/api/operations/confirm/',{'proposal_id':preview.json()['proposal']['id'],'confirmed':True},content_type='application/json',HTTP_X_CSRFTOKEN=csrf)
        if receipt.status_code!=200:raise ValueError('import_fixture_confirm_failed:'+str(receipt.status_code))
        self.import_batch_id=batch['batch_id']
        self.build_correction_outcome()
        self.build_task_controls()
        self.build_statement_controls()

    def statement_upload_payload(self, code='A04-C03-NEW-SOURCE'):
        return {'code':code,'revision':'A','title':'A04 C03 private source',
            'file':SimpleUploadedFile('a04-c03.csv',self.c03_csv,content_type='text/csv')}

    def statement_command(self, payload):
        client=self.client('ceo');kw={'HTTP_X_CSRFTOKEN':client.cookies[settings.CSRF_COOKIE_NAME].value}
        preview=client.post('/api/erp/preview/',payload,content_type='application/json',**kw)
        self.c03_fixture_http.append({'phase':'preview','action':payload['action'],'status':preview.status_code})
        if preview.status_code!=200 or not preview.json().get('id'):
            raise ValueError('c03_fixture_preview_failed:'+str(preview.status_code)+':'+preview.content.decode())
        p=preview.json();response=client.post('/api/operations/confirm/',{'proposal_id':p['id'],'confirmed':True},content_type='application/json',**kw)
        self.c03_fixture_http.append({'phase':'confirm','action':payload['action'],'status':response.status_code})
        if response.status_code!=200:raise ValueError('c03_fixture_confirm_failed:'+str(response.status_code)+':'+response.content.decode())
        return p,response.json()

    def build_statement_controls(self):
        """Real CSV/private upload, approved import and both cash-source kinds."""
        import csv,io
        from uuid import uuid4
        from operations.models import Document,ProcurementRequest
        from finance.models import StatementImport,StatementLine,StatementAllocation
        self.c03_fixture_http=[]
        self.c03_markers={name:'A04_C03_PRIVATE_'+name.upper() for name in ('purpose','external','description','task_result')}
        self.c03_source_system='a04-access-bank';self.c03_account_ref='A04-C03-ACCOUNT'
        rows=[];self.c03_amounts={'EUR':'17.39','USD':'123.45','UAH':'9801.07'}
        for currency,amount in self.c03_amounts.items():
            rows.append([self.c03_markers['external']+'-'+currency,self.today.isoformat(),'in',amount,currency,'A04-C03-CUSTOMER','A04-INV-'+currency,self.c03_markers['purpose']+' '+currency+'\n=synthetic text'])
        salary=self.seed.salaries[0]
        rows.append([self.c03_markers['external']+'-SALARY',salary.payment_date.isoformat(),'out',str(salary.amount),salary.currency,'','',self.c03_markers['purpose']+' SALARY'])
        stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n')
        writer.writerow(['external_id','booking_date','direction','amount','currency','counterparty_external_id','invoice_reference','purpose']);writer.writerows(rows)
        self.c03_csv=stream.getvalue().encode();self.c03_sha=hashlib.sha256(self.c03_csv).hexdigest()
        client=self.client('ceo');kw={'HTTP_X_CSRFTOKEN':client.cookies[settings.CSRF_COOKIE_NAME].value}
        response=client.post('/api/statements/sources/',self.statement_upload_payload('A04-C03-SOURCE'),**kw)
        self.c03_fixture_http.append({'phase':'source_upload','status':response.status_code})
        if response.status_code!=201:raise ValueError('c03_fixture_source_failed:'+str(response.status_code)+':'+response.content.decode())
        doc=response.json();self.c03_document_id=doc['id'];self.c03_document=Document.objects.get(pk=doc['id'])
        if doc['checksum']!=self.c03_sha:raise ValueError('c03_fixture_source_checksum')
        reviewed=client.post('/api/operations/documents/'+str(doc['id'])+'/review/',{'checksum':doc['checksum']},content_type='application/json',**kw)
        if reviewed.status_code!=200:raise ValueError('c03_fixture_review_failed:'+str(reviewed.status_code))
        self.c03_import_payload={'action':'erp_statement_import','document_id':doc['id'],'source_sha256':doc['checksum'],'source_system':self.c03_source_system,'account_ref':self.c03_account_ref,'format':'bos_statement_csv_v1','parser_version':'1'}
        self.c03_import_proposal,self.c03_import_receipt=self.statement_command(self.c03_import_payload)
        self.c03_import_id=self.c03_import_receipt['import_id'];self.c03_lines={};self.c03_receipts={};self.c03_proposals={};self.c03_payloads={}
        self.c03_line_ids={row['external_id']:row['line_id'] for row in self.c03_import_receipt['lines']}
        for currency,amount in self.c03_amounts.items():
            line_id=self.c03_line_ids[self.c03_markers['external']+'-'+currency];self.c03_lines[currency]=line_id
            invoice=next(row for row in self.seed.invoices if row.currency==currency)
            payload={'action':'erp_statement_reconcile','line_id':line_id,
                'transaction':{'mode':'create_transaction','category':'customer','description':self.c03_markers['description']+' '+currency},
                'matching':{'kind':'manual','counterparty_id':self.seed.customer.pk,'counterparty_external_id':'A04-C03-CUSTOMER'},
                'reason':'Синтетичне зіставлення явного контрагента з джерелом',
                'allocations':[{'allocation_key':str(uuid4()),'mode':'new_payment','invoice_id':invoice.pk,'amount':amount,'currency':currency,'invoice_match':'exact_reference','reason':'Точний номер синтетичного рахунку у джерелі'}]}
            self.c03_payloads[currency]=payload;self.c03_proposals[currency],self.c03_receipts[currency]=self.statement_command(payload)
        line_id=self.c03_line_ids[self.c03_markers['external']+'-SALARY'];self.c03_lines['salary']=line_id
        payload={'action':'erp_statement_reconcile','line_id':line_id,'transaction':{'mode':'existing_transaction','transaction_id':salary.transaction_id},
            'matching':{'kind':'salary_source','salary_id':salary.pk,'counterparty_id':None,'counterparty_external_id':''},'reason':'Прив’язка саме наявного джерела виплаченої зарплати','allocations':[]}
        self.c03_payloads['salary']=payload;self.c03_proposals['salary'],self.c03_receipts['salary']=self.statement_command(payload)
        # Legacy source graph canary only; no procurement commitment is executed.
        request=ProcurementRequest.objects.create(code='A04-C03-SOURCE-REF',part='Успадковане посилання для перевірки доступу',revision='A',quantity=1,currency='EUR',required_by=self.future,owner=self.seed.employee,document=self.c03_document)
        _,created=self.task_command('ceo',{**self.task_payload(),'title':'A04 C03 private historical task','request_code':request.code,'order_id':self.seed.order.pk})
        self.c03_task_id=created['task_id']
        self.task_command('ceo',{'action':'update_task','task_id':self.c03_task_id,'status':'done','result':self.c03_markers['task_result'],'reason':'Перевірка спадкової конфіденційності джерела'})
        # Additional actual unimported upload exercises marker-only permanence.
        pending=client.post('/api/statements/sources/',self.statement_upload_payload('A04-C03-UNIMPORTED'),**kw)
        if pending.status_code!=201:raise ValueError('c03_unimported_source_failed:'+str(pending.status_code))
        self.c03_unimported_document_id=pending.json()['id']
        if any(model in admin.site._registry for model in (StatementImport,StatementLine,StatementAllocation)):
            raise ValueError('unexpected_statement_admin_registration')

    def task_command(self, role, payload):
        """Actual approved C01 change; never fabricate its audit or receipt."""
        client = self.client(role)
        headers = {'HTTP_X_CSRFTOKEN': client.cookies[settings.CSRF_COOKIE_NAME].value}
        preview = client.post('/api/operations/preview/', payload, content_type='application/json', **headers)
        if preview.status_code != 200 or not preview.json().get('id'):
            raise ValueError('c01_fixture_preview_failed:' + str(preview.status_code) + ':' + preview.content.decode())
        proposal = preview.json()
        response = client.post('/api/operations/confirm/', {'proposal_id': proposal['id'], 'confirmed': True}, content_type='application/json', **headers)
        if response.status_code != 200:
            raise ValueError('c01_fixture_confirm_failed:' + str(response.status_code) + ':' + response.content.decode())
        return proposal, response.json()

    def build_task_controls(self):
        from operations.models import AuditEvent
        self.c01_markers = {name: 'A04_C01_' + name.upper() for name in (
            'visible_result', 'archive_result', 'current_hidden_result', 'history_hidden_result',
            'legacy_raw_payload', 'archive_reason', 'restore_reason')}
        self.c01_tasks = {}
        self.c01_proposals = {}
        self.c01_receipts = {}
        for name, role, order in (
            ('visible', 'manager', self.seed.order), ('archived', 'manager', self.seed.order),
            ('current_hidden', 'ceo', self.seed.hidden_order), ('history_hidden', 'ceo', self.seed.hidden_order),
            ('outcome', 'ceo', self.seed.order)):
            p, r = self.task_command(role, {**self.task_payload(), 'title': 'A04 C01 ' + name,
                'order_id': order.pk, 'request_code': 'R01'})
            self.c01_tasks[name] = r['task_id']
            marker = self.c01_markers.get(name + '_result', 'A04_C01_OUTCOME_RESULT')
            if name == 'archived':
                marker = self.c01_markers['archive_result']
            p, r = self.task_command(role, {'action': 'update_task', 'task_id': r['task_id'],
                'status': 'done', 'result': marker, 'reason': 'A04 C01 complete ' + name})
            self.c01_proposals[name] = p['id']
            self.c01_receipts[name] = r
        self.task_command('manager', {'action': 'update_task', 'task_id': self.c01_tasks['archived'],
            'archived': True, 'reason': self.c01_markers['archive_reason']})
        self.task_command('ceo', {'action': 'update_task', 'task_id': self.c01_tasks['history_hidden'],
            'order_id': self.seed.order.pk, 'reason': 'A04 C01 relink keeps historical source restriction'})
        # Explicit synthetic legacy payload and unrelated padding. Neither is
        # presented as a C01 command-generated history or historical repair.
        AuditEvent.objects.create(action='update_task', task_id=self.c01_tasks['visible'],
            payload={'untyped_private': self.c01_markers['legacy_raw_payload']})
        AuditEvent.objects.bulk_create([AuditEvent(action='a04_c01_padding', payload={'synthetic_padding': index}) for index in range(101)])
        self.c01_pending_manager = self.preview_task(self.client('manager'))


    def build_correction_outcome(self):
        """One real supplier return; no domain rows or receipts are fabricated."""
        from decimal import Decimal
        from uuid import uuid4
        from erp.models import Movement, Purchase, Lot, GoodsReturn
        from operations.service import as_of
        self.correction_cost_canary = '73429.17'
        self.correction_reason_canary = 'A04_B03_RETURN_REASON_CANARY'
        client = self.client('ceo')
        csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
        self.correction_fixture_http = []

        def command(payload):
            response = client.post('/api/erp/preview/', payload, content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
            self.correction_fixture_http.append({'action': payload['action'], 'phase': 'preview', 'status': response.status_code})
            if response.status_code != 200:
                raise ValueError('correction_fixture_preview_failed:' + payload['action'] + ':' + str(response.status_code))
            result = client.post('/api/operations/confirm/', {'proposal_id': response.json()['id'], 'confirmed': True},
                                 content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
            self.correction_fixture_http.append({'action': payload['action'], 'phase': 'confirm', 'status': result.status_code})
            if result.status_code != 200:
                raise ValueError('correction_fixture_confirm_failed:' + payload['action'] + ':' + str(result.status_code))
            return result.json()

        item = self.seed.item
        po = command({'action': 'erp_purchase', 'code': 'A04-B03-PO', 'item_id': item.pk,
            'supplier_id': self.seed.supplier.pk, 'quantity': '2.000', 'price': self.correction_cost_canary,
            'extras': '0.00', 'currency': item.currency, 'revision': item.revision,
            'due_date': str(as_of() + timedelta(days=1)), 'direct_reason': 'Синтетичне пряме замовлення для перевірки доступу'})
        receipt = command({'action': 'erp_receive', 'purchase_id': po['purchase_id'], 'code': 'A04-B03-RECEIPT',
            'location_id': self.seed.location.pk, 'quantity': '2.000', 'documents': {'certificate': self.seed.public_doc.pk}})
        movement = Movement.objects.get(lot_id=receipt['lot_id'], purchase_id=po['purchase_id'], kind='receipt')
        self.correction_action = 'erp_return_supplier'
        self.correction_operation_id = str(uuid4())
        self.correction_receipt = command({'action': self.correction_action, 'operation_id': self.correction_operation_id,
            'code': 'A04-B03-RETURN', 'receipt_id': movement.pk, 'quantity': '1.000',
            'business_date': str(as_of()), 'reason': self.correction_reason_canary})
        returned = GoodsReturn.objects.get(pk=self.correction_receipt['goods_return_id'])
        if returned.source_id != movement.pk or returned.result_id != self.correction_receipt['movement_id']:
            raise ValueError('correction_fixture_source_mismatch')
        if Purchase.objects.get(pk=po['purchase_id']).received != Decimal('2.000') or Lot.objects.get(pk=receipt['lot_id']).quantity != Decimal('1.000'):
            raise ValueError('correction_fixture_gross_or_stock_mismatch')
        if returned.allocated_cost != Decimal(self.correction_cost_canary) or self.correction_receipt.get('allocated_cost') != self.correction_cost_canary:
            raise ValueError('correction_fixture_private_cost_control_missing')
        self.correction_source_ids = {'purchase_id': po['purchase_id'], 'receipt_id': movement.pk,
            'lot_id': receipt['lot_id'], 'goods_return_id': returned.pk, 'movement_id': returned.result_id,
            'claim_id': self.correction_receipt['claim_id'], 'erp_event_id': self.correction_receipt['erp_event_id']}

    def client(self, role):
        client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        client.cookies = deepcopy(self.cookies[role])
        return client

    def limit_capabilities(self, role, variant):
        if variant == 'full' or role not in self.users:
            return
        name = {'no_export': 'export_workspace', 'no_documents': 'view_document', 'no_download': 'download_document'}[variant]
        permissions = Permission.objects.filter(content_type__app_label='operations', codename=name)
        self.users[role].user_permissions.remove(*permissions)

    def route_values(self, row):
        pattern = row['pattern']
        values = {'format': 'json', 'url': '_a04_known_catchall_missing_', 'batch_id': self.import_batch_id,
                  'proposal_id': self.c01_proposals['outcome']}
        if pattern.startswith('admin/'):
            model = row['model'] or ('auth.user' if 'auth/user/<id>' in pattern else None)
            if model:
                obj = self.admin[model]
                if not type(obj)._base_manager.filter(pk=obj.pk).exists():
                    raise ValueError('missing_admin_object:' + model)
                values.update(object_id=obj.pk, id=obj.pk)
            if '/r/' in pattern:
                obj = self.admin['employees.employee']
                values.update(content_type_id=ContentType.objects.get_for_model(obj).pk, object_id=obj.pk)
            return values
        for family, instance in self.api.items():
            if pattern.startswith('api/^' + family + '/'):
                values['pk'] = instance.pk
        if pattern.startswith('api/^tasks/') and 'history' in pattern:
            values['pk'] = self.c01_tasks['visible']
        if pattern.startswith('api/statements/imports/'):
            values['pk']=self.c03_import_id
        elif pattern.startswith('api/statements/lines/'):
            values['pk']=self.c03_lines['EUR']
        if 'api/operations/documents/' in pattern:
            values['pk'] = self.seed.public_doc.pk
        elif 'api/erp/orders/' in pattern:
            values['pk'] = self.seed.order.pk
        elif 'api/erp/changes/' in pattern:
            values['pk'] = self.seed.change.pk
        elif 'api/operations/rfq/' in pattern:
            values['code'] = 'R01'
        return values

    def query(self, row, path):
        if row['name'] == 'admin:autocomplete':
            return '?app_label=finance&model_name=salary&field_name=employee&term=A04'
        if path == '/api/erp/corrections/outcome/':
            from urllib.parse import urlencode
            return '?' + urlencode({'action': self.correction_action, 'operation_id': self.correction_operation_id})
        if path == '/api/erp/import/template/':
            return '?owner_id='+str(self.seed.employee.pk)+'&format=json'
        if path == '/api/operations/compare/':
            return '?code=R01&quantity=3'
        return ''

    def preview_task(self, client):
        response = client.post('/api/operations/preview/', self.task_payload(), content_type='application/json',
            HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
        if response.status_code != 200:
            raise ValueError('valid_proposal_fixture_failed:' + str(response.status_code))
        return response.json()['id']

    def task_payload(self):
        return {'action': 'create_task', 'title': 'A04 ROUTE PROPOSED TASK',
                'assignee_id': self.seed.employee.pk, 'deadline': self.future}

    def payload(self, row, path, method, role, client):
        from check_access import canonical
        route = canonical(path)
        if path.startswith('/admin/'):
            return self.admin_payload(row, path, method, role)
        if route == '/api/auth/login/':
            user = self.users['ceo' if role == 'anonymous' else role]
            return {'username': user.username, 'password': self.password, 'role': 'ceo'}, 'json'
        if method in ('GET', 'HEAD', 'OPTIONS', 'TRACE', 'CONNECT'):
            return None, 'json'
        parts = route.split('/')
        if len(parts) > 2 and parts[2] in self.api:
            family = parts[2]
            if 'pay' in parts:
                return {'payment_date': self.today.isoformat()}, 'json'
            if method == 'DELETE':
                return {}, 'json'
            values = self.api_values(family)
            if method == 'PATCH':
                field = {'tasks': 'title', 'employees': 'role', 'counterparties': 'name',
                         'contracts': 'name', 'transactions': 'description', 'salaries': 'amount'}[family]
                values = {field: values[field]}
            return values, 'json'
        if route == '/api/erp/import/preview/':
            from erp.import_views import template_batch
            return template_batch(self.seed.employee.pk), 'json'
        if route == '/api/statements/sources/':
            return self.statement_upload_payload(), 'multipart'
        if route == '/api/erp/preview/':
            return {'action': 'erp_item', 'code': 'A04-NEW-ERP', 'name': 'A04 NEW ERP ITEM',
                'unit': 'шт.', 'kind': 'product', 'method': 'buy', 'revision': 'A', 'currency': 'EUR'}, 'json'
        if route == '/api/operations/preview/':
            return self.task_payload(), 'json'
        if route == '/api/operations/confirm/':
            proposal = self.preview_task(client) if role in ('ceo', 'manager') else self.baseline_proposal
            return {'proposal_id': proposal, 'confirmed': True}, 'json'
        if route == '/api/operations/requests/create/':
            return {'code': 'A04-R-NEW', 'part': 'A04 NEW REQUEST', 'revision': 'A', 'quantity': 3,
                'unit': 'шт.', 'currency': 'EUR', 'required_by': self.future, 'owner_id': self.seed.employee.pk,
                'document_id': self.seed.public_doc.pk, 'details': {'material': 'Сталь'}}, 'json'
        if route == '/api/operations/quotes/create/':
            return {'code': 'A04-Q-NEW', 'request_code': 'R01', 'supplier_id': self.seed.supplier.pk,
                    'document_id': self.seed.public_doc.pk, 'terms': self.seed.quotes[0].terms}, 'json'
        if route.endswith('/review/'):
            return {'checksum': self.seed.public_doc.checksum}, 'json'
        if route == '/api/operations/documents/upload/':
            return {'code': 'A04-UPLOAD-NEW', 'revision': 'A', 'title': 'A04 NEW DOCUMENT',
                'file': SimpleUploadedFile('a04.txt', b'A04 SYNTHETIC UPLOAD', content_type='text/plain')}, 'multipart'
        if route == '/api/operations/chat/':
            return {'message': 'Що потребує уваги?'}, 'json'
        if route == '/api/operations/settings/':
            return {'name': 'A04 SYNTHETIC ORGANIZATION'}, 'json'
        if route in {'/api/chat/', '/api/chat/file/', '/api/meeting/protocol/', '/api/dictate/process/'}:
            return {'message': 'A04 read context', 'text': 'A04 synthetic input'}, 'json'
        return {}, 'json'

    def api_values(self, family):
        instance = self.api[family]
        common = {
            'tasks': {'title': 'A04 NEW TASK', 'assignee': self.seed.employee.full_name, 'deadline': self.future,
                'priority': 'medium', 'status': 'active', 'category': 'Операції', 'branch': None},
            'employees': {'full_name': 'A04 NEW EMPLOYEE', 'role': 'Оновлена посада', 'department': 'Операції',
                'birthday': None, 'kpi': 0, 'phone': '', 'email': '', 'branch': None},
            'counterparties': {'name': 'A04 NEW COUNTERPARTY', 'type': 'other', 'edrpou': '', 'phone': '',
                'email': '', 'address': '', 'notes': '', 'is_active': True},
            'contracts': {'number': 'A04-NEW-CONTRACT', 'name': 'A04 NEW CONTRACT',
                'counterparty': self.seed.supplier.pk, 'category': 'supply', 'status': 'draft',
                'amount': '12.34', 'currency': 'EUR', 'start_date': None, 'end_date': None, 'notes': ''},
            'transactions': {'direction': 'out', 'amount': '99.12', 'currency': 'EUR', 'date': self.today.isoformat(),
                'description': 'A04 NEW TRANSACTION', 'category': 'other', 'counterparty': None, 'contract': None, 'branch': None},
            'salaries': {'employee': self.api['salaries'].employee_id, 'amount': '223.45', 'currency': 'EUR',
                'period_year': self.today.year, 'period_month': 11, 'status': 'pending',
                'payment_date': None, 'transaction': None, 'notes': ''},
        }
        return common[family]

    def admin_payload(self, row, path, method, role):
        if method != 'POST':
            return None, 'form'
        name = row['name'].removeprefix('admin:')
        if name == 'login':
            user = self.users.get(role, self.users['observer'])
            return {'username': user.username, 'password': self.password, 'next': '/admin/'}, 'form'
        if name in ('password_change', 'auth_user_password_change'):
            return {'old_password': self.password, 'new_password1': 'Synthetic-new-password-A04',
                    'new_password2': 'Synthetic-new-password-A04', 'password1': 'Synthetic-new-password-A04',
                    'password2': 'Synthetic-new-password-A04'}, 'form'
        model_name = row['model']
        if not model_name:
            return {}, 'form'
        obj = self.admin[model_name]
        obj.refresh_from_db()
        if name.endswith('_delete'):
            return {'post': 'yes'}, 'form'
        if name.endswith('_changelist'):
            return {'action': 'delete_selected', '_selected_action': [str(obj.pk)], 'post': 'yes', 'index': '0'}, 'form'
        if not name.endswith(('_add', '_change')):
            return {}, 'form'
        if model_name == 'tasks.task':
            # Complete legacy write attempt, independent of readonly form
            # fields: 403 must come from command admission, not empty input.
            return {'title': 'A04 C01 ADMIN WRITE ATTEMPT', 'assignee': 'A04 Operator',
                'deadline': self.future, 'priority': 'medium', 'status': 'active',
                'category': 'Операції', 'branch': ''}, 'form'
        if model_name.startswith('ai_assistant.'):
            # Full valid payloads are independent of readonly ModelAdmin fields:
            # an incomplete form must not hide a writable audit model.
            from ai_assistant.models import ChatMessage
            if model_name == 'ai_assistant.chatmessage':
                return {'content': 'A04 TAMPERED CHAT', 'role': 'assistant',
                    'user': self.users['ceo'].pk, 'visibility_role': 'ceo', 'archived_at': ''}, 'form'
            if model_name == 'ai_assistant.taskchangelog':
                return {'action': 'update', 'task_id': self.api['tasks'].pk,
                    'task_title': 'A04 TAMPERED TASK LOG', 'before': '{}', 'after': '{"title":"tampered"}'}, 'form'
            if model_name == 'ai_assistant.employeechangelog':
                return {'action': 'update', 'employee_id': self.seed.employee.pk,
                    'employee_name': 'A04 TAMPERED EMPLOYEE LOG', 'before': '{}', 'after': '{"role":"tampered"}'}, 'form'
            if model_name == 'ai_assistant.claudeusagelog':
                return {'endpoint': 'chat', 'model': 'A04 TAMPERED USAGE', 'input_tokens': 2,
                    'output_tokens': 3, 'chat_message': self.admin['ai_assistant.chatmessage'].pk}, 'form'
            if model_name == 'ai_assistant.chatfile':
                message = self.admin['ai_assistant.chatmessage']
                if name.endswith('_add'):
                    message = ChatMessage.objects.create(role='assistant', content='A04 FREE FILE SUPPORT')
                return {'chat_message': message.pk, 'original_name': 'A04_TAMPERED_FILE.txt',
                    'mime_type': 'text/plain', 'size': 12, 'parsed_text': 'A04 TAMPERED',
                    'file': SimpleUploadedFile('A04_TAMPERED_FILE.txt', b'A04 TAMPERED', content_type='text/plain')}, 'multipart'
            raise ValueError('unknown_audit_model_payload:' + model_name)
        if model_name == 'auth.user' and name.endswith('_add'):
            return {'username': 'a04-new-admin-user', 'password1': self.password, 'password2': self.password,
                    'usable_password': 'true'}, 'form'
        model_admin = admin.site._registry[type(obj)]
        request = RequestFactory().post(path)
        request.user = self.users['technical_admin']
        adding = name.endswith('_add')
        form_class = model_admin.get_form(request, obj=None if adding else obj)
        form = form_class(instance=None if adding else obj)
        values = model_to_dict(obj)
        data = {}
        for key, field in form.fields.items():
            value = values.get(key, getattr(obj, key, field.initial))
            if callable(value):
                value = value()
            if isinstance(field, forms.ModelMultipleChoiceField):
                value = [x.pk for x in value] if value is not None else []
            elif isinstance(field, forms.ModelChoiceField):
                value = getattr(value, 'pk', value) or ''
            elif isinstance(field, forms.JSONField):
                value = json.dumps(value) if value is not None else ''
            elif isinstance(field, forms.SplitDateTimeField):
                data[key + '_0'] = value.strftime('%Y-%m-%d') if value else ''
                data[key + '_1'] = value.strftime('%H:%M:%S') if value else ''
                continue
            elif isinstance(field, forms.BooleanField):
                if value:
                    data[key] = 'on'
                continue
            elif value is None:
                value = ''
            elif isinstance(value, (date,)):
                value = value.isoformat()
            data[key] = value
        if model_name == 'auth.user':
            data.update(first_name='A04 Changed', last_name='Operator', email='changed@example.invalid')
        elif model_name == 'auth.group':
            data['name'] = 'A04 NEW GROUP'
        elif model_name == 'employees.employee':
            data['role'] = 'Оновлена посада'
            if adding:
                data['full_name'] = 'A04 NEW ADMIN EMPLOYEE'
        elif model_name == 'finance.salary':
            data['amount'] = '223.45'
            if adding:
                data['period_month'] = 10
        elif model_name == 'finance.transaction':
            data['description'] = 'A04 NEW ADMIN TRANSACTION'
        elif model_name == 'branches.branch':
            data['name'] = 'A04 NEW ADMIN BRANCH'
            if adding:
                data['code'] = 'A04-NEW-ADMIN-BRANCH'
        else:
            key = 'title' if model_name == 'tasks.task' else 'name'
            data[key] = 'A04 NEW ADMIN RECORD'
        if not form_class(data=data, instance=None if adding else obj).is_valid():
            errors = form_class(data=data, instance=None if adding else obj)
            errors.is_valid()
            raise ValueError('invalid_positive_admin_form:' + model_name + ':' + str(errors.errors))
        return data, 'form'

    def forbidden_markers(self, role, path, variant):
        s = self.seed
        markers = [str(settings.SECRET_KEY), 'A04_INTERNAL_SECRET_CANARY']
        private_hr = [s.HR_PHONE, s.HR_EMAIL, s.HR_DATE]
        payroll = list(s.PAYROLL_AMOUNTS) + ['91827.43', 'A04_ROUTE_PRIVATE_SALARY', 'A04_PAYROLL_SECRET_', 'A04_UNLINKED_PAYROLL_SECRET']
        if role not in ('ceo', 'technical_admin'):
            markers += private_hr + payroll + [s.HIDDEN, s.HIDDEN_VERSION]
        if role in ('anonymous', 'observer'):
            markers += [s.MANAGEMENT]
        if role == 'anonymous':
            markers += ['A04 ROUTE', 'A04 ADMIN', 'Відкрите доручення A04', 'Постачальник A04', 'Синтетичний Працівник A04', 'A04-OPEN']
        if role != 'technical_admin':
            markers += ['A04 ADMIN PRIVATE CHAT', 'A04 ADMIN PRIVATE FILE', 'A04_ADMIN_PRIVATE_FILE', 'A04 ADMIN PRIVATE USAGE']
        if role not in ('ceo', 'technical_admin'):
            markers += ['A04 ADMIN PRIVATE EMPLOYEE LOG']
        if path.startswith('/api/chat/history/'):
            markers += [marker for owner, marker in self.chat_markers.items() if owner != role]
        if variant == 'no_documents' and role != 'ceo':
            markers += ['A04-OPEN', s.HIDDEN, s.HIDDEN_VERSION, s.MANAGEMENT, 'A04-ROUTE-CONTRACT-DOC']
        if path == '/api/erp/corrections/outcome/' and role != 'ceo':
            markers += [self.correction_cost_canary, self.correction_reason_canary]
            if role != 'manager' or variant == 'no_documents':
                markers += ['A04-B03-PO', 'A04-B03-RECEIPT', 'A04-B03-RETURN']
        if role != 'ceo' and (role != 'technical_admin' or not path.startswith('/admin/')):
            markers += [self.c01_markers['current_hidden_result'], self.c01_markers['history_hidden_result'],
                        'A04 C01 current_hidden', 'A04 C01 history_hidden']
        if '/history' in path and path.startswith('/api/tasks/'):
            markers += [self.c01_markers['legacy_raw_payload']]
        if variant == 'no_documents' and role != 'ceo':
            markers += list(self.c01_markers.values()) + ['A04 C01 visible', 'A04 C01 archived']
        if role!='ceo' and (role!='technical_admin' or not path.startswith('/admin/')):
            markers += list(self.c03_markers.values()) + [self.c03_account_ref,self.c03_source_system,
                'A04-C03-SOURCE','A04-C03-UNIMPORTED','A04 C03 private historical task']
        return list(set(markers))

    def positive_anchors(self, row, path, role, variant):
        """Known records must actually appear; an empty 200 is not a read control."""
        from check_access import canonical
        route = canonical(path)
        if path.startswith('/admin/'):
            if role != 'technical_admin':
                return []
            if row['model'] and not row['name'].endswith(('_add', '_delete')) and row['name'] != 'admin:None':
                obj = self.admin[row['model']]
                actual = type(obj)._base_manager.get(pk=obj.pk)
                if row['name'].endswith('_changelist'):
                    return ['/admin/' + row['model'].replace('.', '/') + '/' + str(actual.pk) + '/change/']
                return [str(actual)]
            if row['name'] == 'admin:autocomplete':
                return ['A04 ADMIN EMPLOYEE']
            if row['name'] == 'admin:index':
                return ['/admin/finance/salary/']
            return []
        if role not in ('ceo', 'manager', 'observer'):
            return []
        if route == '/api/erp/corrections/outcome/' and role in ('ceo', 'manager') and variant == 'full':
            return [self.correction_action, self.correction_operation_id, '"goods_return_id": ' + str(self.correction_source_ids['goods_return_id']), '"receipt_id": ' + str(self.correction_source_ids['receipt_id'])]
        if route.startswith('/api/erp/import/') and role=='ceo':
            return ['bos.initial-import.v1'] if route.endswith('/template/') else ['a04-import-fixture','A04-IMPORT-BOUND'] if '/batches/' in route else ['\"valid\": true']
        if route.startswith('/api/auth/') or route == '/api/runtime/status/':
            return []
        if route == '/api/tasks/{pk}/history/' and variant == 'full':
            return ['"task_id": ' + str(self.c01_tasks['visible']), self.c01_markers['visible_result']]
        if route == '/api/operations/task-proposals/{proposal_id}/' and role == 'ceo':
            return [self.c01_proposals['outcome'], str(self.c01_receipts['outcome']['audit_id'])]
        if route.startswith('/api/statements/') and role=='ceo':
            if route.endswith('/export/'):
                return [self.c03_sha,self.c03_import_id,self.c03_lines['EUR'],'reconciled']
            if route.endswith('/candidates/'):
                return [self.c03_lines['EUR'],'A04-INV-EUR']
            if route=='/api/statements/summary/':
                return [self.c03_account_ref,self.c03_source_system]
            return [self.c03_account_ref,self.c03_source_system]
        if route=='/api/transactions/summary/' and role=='ceo':
            return ['period_movement','includes_archived','EUR','USD','UAH']
        family = route.split('/')[2] if len(route.split('/')) > 2 else ''
        if family in self.api:
            if family == 'transactions' and role == 'manager':
                # Identifier + allowed keys; the description and amount must be absent.
                return ['"id": ' + str(self.api['transactions'].pk), '"currency"', '"category"']
            field = {'tasks': 'title', 'employees': 'full_name', 'counterparties': 'name',
                     'contracts': 'number', 'transactions': 'description', 'salaries': 'amount'}[family]
            obj = self.api[family]
            actual = type(obj)._base_manager.get(pk=obj.pk)
            return [str(getattr(actual, field))]
        if route == '/api/chat/history/':
            return [self.chat_markers[role]]
        if route == '/api/':
            return ['/api/tasks.json' if '.json' in path else '/api/tasks/']
        if route.startswith('/api/operations/documents/') and variant != 'no_documents':
            return ['A04-OPEN']
        if route in ('/api/operations/requests/', '/api/operations/compare/', '/api/operations/rfq/{code}/'):
            return ['R01']
        if route in ('/api/erp/snapshot/', '/api/erp/export/', '/api/operations/export/'):
            return ['A04-ITEM']
        if route == '/api/erp/orders/{pk}/draft/':
            return ['A04-SO-OPEN']
        if route == '/api/erp/changes/{pk}/impact/':
            return ['A04-CHANGE']
        if route == '/api/operations/summary/':
            return ['Відкрите доручення A04']
        return []

    def state_digest(self):
        digest = hashlib.sha256()
        for model in sorted(self.business_models, key=lambda m: m._meta.label_lower):
            digest.update(model._meta.label_lower.encode())
            records = list(model._base_manager.order_by(model._meta.pk.name).values())
            digest.update(json.dumps(records, sort_keys=True, default=str).encode())
        return digest.hexdigest()
