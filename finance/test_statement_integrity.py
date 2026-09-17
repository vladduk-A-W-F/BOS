"""Named C03 boundary regressions on actual local HTTP/DB/private files."""
from copy import deepcopy
from datetime import date
from decimal import Decimal as D,localcontext
import hashlib,json
from pathlib import Path
from uuid import uuid4
from django.conf import settings
from django.test import Client,TransactionTestCase,override_settings
from django.db import connection
from finance.models import Counterparty,Transaction,FinancialIntent,Salary,StatementImport,StatementLine,StatementAllocation
from operations.models import Document,ActionProposal,Invoice,AuditEvent
from employees.models import Employee
from erp.models import Event,ImportBatch,ImportIdentity
from scripts.check_support import login_test_client
from . import test_statements as source_fixture

@override_settings(BOS_DATA_MODE='working',DEBUG=False,ANTHROPIC_API_KEY='',PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StatementIntegrityTests(TransactionTestCase):
    setUp=source_fixture.StatementTests.setUp;post=source_fixture.StatementTests.post;csv=source_fixture.StatementTests.csv;upload=source_fixture.StatementTests.upload
    source=source_fixture.StatementTests.source;import_payload=source_fixture.StatementTests.import_payload;commit=source_fixture.StatementTests.commit;counts=source_fixture.StatementTests.counts
    def prepared(self,*,rows=None,amount='10.00'):
        d=self.source(self.csv(rows) if rows else None);_,r=self.commit(self.import_payload(d));line=r['lines'][0]['line_id']
        return d,r,{'action':'erp_statement_reconcile','line_id':line,'transaction':{'mode':'create_transaction','category':'customer','description':'Точний грошовий запис виписки'},'matching':{'kind':'manual','counterparty_id':self.customer.pk,'counterparty_external_id':rows[0][5] if rows else 'client-1'},'reason':'Явне погодження першого зіставлення','allocations':[]}
    def allocation(self,amount='10.00',**changes):
        return {'allocation_key':str(uuid4()),'mode':'new_payment','invoice_id':self.invoice.pk,'amount':amount,'currency':'EUR','invoice_match':'exact_reference','reason':'Погоджена первинна оплата рахунку',**changes}
    def test_later_existing_same_bound_transaction_preserves_first_binding(self):
        _,_,d=self.prepared();_,first=self.commit(d);line=StatementLine.objects.get(pk=d['line_id']);snapshot=deepcopy(line.binding_snapshot)
        d['transaction']={'mode':'existing_transaction','transaction_id':first['transaction_id']};d['allocations']=[self.allocation()]
        _,r=self.commit(d);line.refresh_from_db();self.assertEqual(line.binding_snapshot,snapshot)
        self.assertFalse(r['transaction_created']);self.assertFalse(r['binding_created']);self.assertEqual(Transaction.objects.count(),1)
    def test_import_current_summary_status_filter_and_export_links(self):
        _,imp,d=self.prepared();_,r=self.commit(d)
        summary=self.http.get('/api/statements/summary/?status=unallocated');self.assertEqual(summary.status_code,200,summary.content)
        self.assertEqual(next(x for x in summary.json()['currencies'] if x['currency']=='EUR')['recorded']['in'],'10.00')
        detail=self.http.get(f"/api/statements/imports/{imp['import_id']}/");self.assertEqual(detail.status_code,200,detail.content)
        currencies=detail.json()['current_summary']['currencies'];self.assertEqual(next(x for x in currencies if x['currency']=='EUR')['incoming']['unallocated'],'10.00')
        export=self.http.get(f"/api/statements/imports/{imp['import_id']}/export/");self.assertEqual(export.status_code,200,export.content)
        import csv,io
        rows=list(csv.DictReader(io.StringIO(export.content.decode())));self.assertEqual(rows[0]['line_id'],d['line_id']);self.assertEqual(rows[0]['import_id'],imp['import_id']);self.assertEqual(rows[0]['transaction_id'],str(r['transaction_id']));self.assertEqual(rows[0]['status'],'unallocated');self.assertEqual(rows[0]['source_sha256'],imp['source_sha256'])
    def test_malformed_quote_reports_actual_logical_record(self):
        raw=self.csv()+b'bank-2,2026-09-01,in,1.00,EUR,,,unquoted"invalid\n'
        r=self.upload(raw);self.assertEqual(r.status_code,422,r.content);self.assertEqual(r.json()['errors'][0]['record'],3)
        self.assertEqual(Document.objects.count(),0)
    def test_actual_postwrite_transaction_drift_rolls_back_every_effect(self):
        _,_,d=self.prepared();d['allocations']=[self.allocation()]
        p=self.post('/api/erp/preview/',d);self.assertEqual(p.status_code,200,p.content);before=self.counts()
        self.assertEqual(connection.vendor,'sqlite')
        with connection.cursor() as c:c.execute('CREATE TRIGGER c03_owned_fault AFTER INSERT ON finance_transaction BEGIN UPDATE finance_transaction SET amount=amount+1 WHERE id=NEW.id; END')
        try:
            r=self.post('/api/operations/confirm/',{'proposal_id':p.json()['id'],'confirmed':True})
            self.assertEqual(r.status_code,409,r.content);self.assertEqual(self.counts(),before);self.invoice.refresh_from_db();self.assertEqual(self.invoice.paid,D(0));self.assertFalse(StatementAllocation.objects.exists());self.assertIsNone(ActionProposal.objects.get(pk=p.json()['id']).receipt)
        finally:
            with connection.cursor() as c:c.execute('DROP TRIGGER c03_owned_fault')
    def test_actual_original_bytes_tamper_invalidates_confirmation_and_replay(self):
        doc=self.source();p=self.post('/api/erp/preview/',self.import_payload(doc));self.assertEqual(p.status_code,200,p.content)
        source=Document.objects.get(pk=doc['id']);path=self.media/source.original_file.name;raw=path.read_bytes();path.write_bytes(b'bad-source')
        before=self.counts();r=self.post('/api/operations/confirm/',{'proposal_id':p.json()['id'],'confirmed':True});self.assertEqual(r.status_code,422,r.content);self.assertEqual(self.counts(),before);self.assertFalse(StatementImport.objects.exists())
        path.write_bytes(raw);done=self.post('/api/operations/confirm/',{'proposal_id':p.json()['id'],'confirmed':True});self.assertEqual(done.status_code,200,done.content)
        path.write_bytes(b'changed-again');before=self.counts();r=self.post('/api/operations/confirm/',{'proposal_id':p.json()['id'],'confirmed':True});self.assertEqual(r.status_code,422,r.content);self.assertEqual(self.counts(),before)
    def test_cross_actor_identical_import_and_allocation_are_global_no_change(self):
        doc,_,d=self.prepared();d['allocations']=[self.allocation()];_,receipt=self.commit(d);before=self.counts()
        other=Client(enforce_csrf_checks=True,raise_request_exception=False);login_test_client(other,'ceo',capabilities=('view_document','download_document'))
        for payload in (self.import_payload(doc),d):
            r=self.post('/api/erp/preview/',payload,other);self.assertEqual(r.status_code,200,r.content);self.assertEqual(r.json()['state'],'no_change');self.assertIsNone(r.json()['id'])
        self.assertEqual(self.counts(),before)
        bad=deepcopy(d);bad['allocations'][0]['reason']='Змінений первинний намір';r=self.post('/api/erp/preview/',bad,other);self.assertEqual(r.status_code,409,r.content);self.assertEqual(r.json()['code'],'statement_allocation_conflict');self.assertEqual(self.counts(),before)
    def test_historical_existing_transaction_allows_inactive_counterparty_but_protects_fields(self):
        tx=Transaction.objects.create(direction='in',amount='10.00',currency='EUR',date=date(2026,9,1),description='Історичний первинний запис',category='customer',counterparty=self.customer)
        Counterparty.objects.filter(pk=self.customer.pk).update(is_active=False)
        _,_,d=self.prepared();d['transaction']={'mode':'existing_transaction','transaction_id':tx.pk}
        _,r=self.commit(d);self.assertFalse(r['transaction_created']);self.assertEqual(FinancialIntent.objects.count(),0)
        before=tx.description;bad=self.http.patch(f'/api/transactions/{tx.pk}/',json.dumps({'description':'Непогоджена зміна опису'}),content_type='application/json',HTTP_X_CSRFTOKEN=self.http.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertEqual(bad.status_code,400,bad.content);tx.refresh_from_db();self.assertEqual(tx.description,before)
    def test_salary_source_links_only_exact_paid_transaction_without_new_money(self):
        employee=Employee.objects.create(full_name='C03 історичний працівник')
        salary=Salary.objects.create(employee=employee,amount='17.39',currency='UAH',period_year=2026,period_month=8)
        paid=self.post(f'/api/salaries/{salary.pk}/pay/',{'payment_date':'2026-09-01'});self.assertEqual(paid.status_code,200,paid.content);salary.refresh_from_db()
        _,_,d=self.prepared(rows=[['salary-line','2026-09-01','out','17.39','UAH','','','Історичний зарплатний рядок']])
        d['transaction']={'mode':'existing_transaction','transaction_id':salary.transaction_id};d['matching']={'kind':'salary_source','salary_id':salary.pk,'counterparty_id':None,'counterparty_external_id':''}
        before=Transaction.objects.count();_,r=self.commit(d);self.assertFalse(r['transaction_created']);self.assertEqual(Transaction.objects.count(),before);self.assertEqual(r['unallocated'],'0.00');self.assertEqual(StatementLine.objects.get().binding_snapshot['salary']['employee_id'],employee.pk)
    def test_actual_import_identity_mapping_uses_exact_namespace_and_target(self):
        from erp import test_initial_import as initial_fixture
        self.owner=Employee.objects.create(full_name='C03 власник фактичного початкового імпорту')
        batch=initial_fixture.InitialImportFixture.batch(self,'EUR','C03')
        p=self.post('/api/erp/import/preview/',batch);self.assertEqual(p.status_code,200,p.content)
        r=self.post('/api/operations/confirm/',{'proposal_id':p.json()['proposal']['id'],'confirmed':True});self.assertEqual(r.status_code,200,r.content)
        identity=ImportIdentity.objects.get(namespace=batch['namespace'],entity='counterparty',external_id='customer')
        self.customer=identity.counterparty
        _,_,d=self.prepared(rows=[['external','2026-09-01','in','10.00','EUR','customer','','Зіставлення actual B02 identity']])
        d['matching']={'kind':'import_identity','identity_id':identity.pk,'counterparty_id':self.customer.pk,'counterparty_external_id':'customer'}
        _,r=self.commit(d);stored=StatementLine.objects.get().binding_snapshot['import_identity'];self.assertEqual(stored['target_id'],self.customer.pk);self.assertEqual(stored['namespace'],batch['namespace']);self.assertEqual(stored['row_sha256'],identity.row_sha256)
    def test_low_decimal_context_and_three_currencies_remain_separate(self):
        rows=[['eur','2026-09-01','in','1234567.89','EUR','','','EUR'],['usd','2026-09-01','out','123.45','USD','','','USD'],['uah','2026-09-01','in','9801.07','UAH','','','UAH']]
        with localcontext() as ctx:
            ctx.prec=6
            _,imp,d=self.prepared(rows=rows);d['matching']['counterparty_id']=None;d['transaction']['category']='other'
            _,r=self.commit(d);self.assertEqual(r['amount'],'1234567.89');self.assertEqual(Transaction.objects.get().amount,D('1234567.89'))
            summary=self.http.get('/api/statements/summary/');self.assertEqual(summary.status_code,200,summary.content)
            sums={x['currency']:x for x in summary.json()['currencies']};self.assertEqual(sums['EUR']['recorded']['in'],'1234567.89');self.assertEqual(sums['USD']['imported']['out'],'123.45');self.assertEqual(sums['UAH']['imported']['in'],'9801.07');self.assertEqual(ctx.prec,6)
    def test_same_existing_payment_twice_is_rejected_before_proposal(self):
        _,manual=self.commit({'action':'erp_payment','invoice_id':self.invoice.pk,'amount':'10.00','reference':'C03-ONE-OLD-PAY'})
        _,_,d=self.prepared(rows=[['twice','2026-09-01','in','20.00','EUR','client-1','C03-INV','Один первинний ERP payment']])
        d['allocations']=[self.allocation(mode='existing_payment',payment_event_id=manual['erp_event_id']),self.allocation(mode='existing_payment',payment_event_id=manual['erp_event_id'])]
        before=self.counts();r=self.post('/api/erp/preview/',d)
        self.assertEqual(r.status_code,422,r.content);self.assertEqual(self.counts(),before);self.assertFalse(StatementAllocation.objects.exists())
    def test_oversized_statement_command_refuses_before_proposal(self):
        _,_,d=self.prepared();d['reason']='Ж'*16000
        before=self.counts();r=self.post('/api/erp/preview/',d)
        self.assertEqual(r.status_code,413,r.content);self.assertEqual(self.counts(),before)
    def test_c03_command_above_one_mib_keeps_explicit_size_status(self):
        _,_,d=self.prepared();d['reason']='x'*(1024*1024+1)
        before=self.counts();r=self.post('/api/erp/preview/',d)
        self.assertEqual(r.status_code,413,r.content);self.assertEqual(self.counts(),before)
    def test_presented_upload_stream_is_bounded_after_real_actor_before_parser(self):
        import io
        from django.http import HttpRequest
        from finance.statement_views import pre_body
        from finance.statement_csv import MAX_BODY
        class Measured(io.BytesIO):
            def __init__(self,value):super().__init__(value);self.calls=[]
            def read(self,n=-1):self.calls.append(n);return super().read(n)
        def request(raw,declared=None,user=None):
            r=HttpRequest();r.method='POST';r.path='/api/statements/sources/';r.user=user or self.user;r.session=self.http.session;r._stream=Measured(raw)
            if declared is not None:r.META['CONTENT_LENGTH']=declared
            return r
        for declared in (None,'1'):
            r=request(b'x'*(MAX_BODY+200),declared);result=pre_body(r)
            self.assertEqual(result.status_code,413);self.assertEqual(r._stream.calls,[MAX_BODY+1]);self.assertEqual(r._stream.tell(),MAX_BODY+1)
        r=request(b'x'*50,'100');self.assertEqual(pre_body(r).status_code,400)
        manager=Client(enforce_csrf_checks=True,raise_request_exception=False);user=login_test_client(manager,'manager',capabilities=('view_document',));r=request(b'x'*100,user=user)
        self.assertEqual(pre_body(r).status_code,403);self.assertEqual(r._stream.calls,[]);self.assertFalse(Document.objects.exists());self.assertFalse(ActionProposal.objects.exists())
