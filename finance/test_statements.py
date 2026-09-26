"""C03 actual HTTP statements on new synthetic database and private media only."""
import csv,io,json,hashlib,os,tempfile
from pathlib import Path
from uuid import uuid4
from decimal import Decimal as D
from datetime import date
from django.conf import settings
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TransactionTestCase,Client,override_settings
from scripts.check_support import login_test_client
from operations.models import Configuration,Document,ActionProposal,Invoice,AuditEvent
from finance.models import Counterparty,Transaction,FinancialIntent
from erp.models import Event

HEADER=['external_id','booking_date','direction','amount','currency','counterparty_external_id','invoice_reference','purpose']

@override_settings(BOS_DATA_MODE='working',DEBUG=False,ANTHROPIC_API_KEY='',PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StatementTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('DJANGO_SETTINGS_MODULE'),'verification_settings')
        if connection.vendor=='sqlite':self.assertTrue(Path(connection.settings_dict['NAME']).name.startswith('check_'))
        folder=tempfile.TemporaryDirectory(prefix='bos-c03-');self.addCleanup(folder.cleanup)
        self.media=Path(folder.name)/'media';self.media.mkdir(mode=0o700)
        patch=override_settings(MEDIA_ROOT=self.media);patch.enable();self.addCleanup(patch.disable)
        self.http=Client(enforce_csrf_checks=True,raise_request_exception=False)
        self.user=login_test_client(self.http,'ceo',capabilities=('view_document','download_document','export_workspace'))
        Configuration.objects.create(key='erp_write',value={'revision':0})
        Configuration.objects.create(key='dataset',value={'as_of':'2026-09-12'})
        self.customer=Counterparty.objects.create(name='C03 синтетичний клієнт',type='customer')
        self.invoice=Invoice.objects.create(code='C03-INV',customer=self.customer,amount='10.00',currency='EUR',due_date=date(2026,9,30))
    def post(self,url,payload,client=None):
        c=client or self.http
        return c.post(url,json.dumps(payload,ensure_ascii=False),content_type='application/json',HTTP_X_CSRFTOKEN=c.cookies[settings.CSRF_COOKIE_NAME].value)
    def csv(self,rows=None):
        stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n');writer.writerow(HEADER)
        writer.writerows(rows or [['bank-1','2026-09-01','in','10.00','EUR','client-1','C03-INV','Оплата першого рахунку']])
        return stream.getvalue().encode()
    def upload(self,raw=None,code='C03-SOURCE',revision='A'):
        raw=self.csv() if raw is None else raw
        return self.http.post('/api/statements/sources/',{'file':SimpleUploadedFile('synthetic.csv',raw,content_type='text/csv'),'code':code,'revision':revision,'title':'C03 синтетична виписка'},HTTP_X_CSRFTOKEN=self.http.cookies[settings.CSRF_COOKIE_NAME].value)
    def source(self,raw=None,code='C03-SOURCE'):
        r=self.upload(raw,code);self.assertEqual(r.status_code,201,r.content);d=r.json()
        reviewed=self.post(f"/api/operations/documents/{d['id']}/review/",{'checksum':d['checksum']})
        self.assertEqual(reviewed.status_code,200,reviewed.content)
        return d
    def import_payload(self,d):
        return {'action':'erp_statement_import','document_id':d['id'],'source_sha256':d['checksum'],'source_system':'synthetic-bank','account_ref':'EUR-ACCOUNT','format':'bos_statement_csv_v1','parser_version':'1'}
    def commit(self,payload):
        p=self.post('/api/erp/preview/',payload);self.assertEqual(p.status_code,200,p.content)
        r=self.post('/api/operations/confirm/',{'proposal_id':p.json()['id'],'confirmed':True});self.assertEqual(r.status_code,200,r.content)
        return p.json(),r.json()
    def counts(self):
        return {m._meta.label:m.objects.count() for m in (Transaction,FinancialIntent,AuditEvent,Event,ActionProposal)}
    def test_private_upload_parser_rejects_record_error_without_bytes_or_history(self):
        before=self.counts();raw=self.csv([['bank-1','2026-09-01','in','1.230','EUR','','','Синтетична помилка']])
        r=self.upload(raw);self.assertEqual(r.status_code,422,r.content)
        self.assertEqual(r.json()['code'],'statement_csv_invalid')
        self.assertEqual(r.json()['errors'][0]['record'],2);self.assertEqual(r.json()['errors'][0]['column'],'amount')
        self.assertEqual(Document.objects.count(),0);self.assertEqual(list(self.media.rglob('*')),[]);self.assertEqual(self.counts(),before)
    def test_import_commits_sources_only_and_exact_byte_replay_has_no_proposal(self):
        d=self.source();before=self.counts();p,r=self.commit(self.import_payload(d))
        self.assertEqual(r['counts'],{'create':1,'reuse':0,'total':1})
        self.assertEqual(Transaction.objects.count(),before['finance.Transaction']);self.assertEqual(FinancialIntent.objects.count(),0)
        self.assertEqual(Event.objects.count(),1);self.assertEqual(AuditEvent.objects.count(),0)
        line=apps.get_model('finance','StatementLine').objects.get();self.assertEqual(str(line.pk),r['lines'][0]['line_id'])
        state=self.counts();again=self.post('/api/erp/preview/',self.import_payload(d))
        self.assertEqual(again.status_code,200,again.content);self.assertIsNone(again.json()['id']);self.assertEqual(again.json()['state'],'no_change');self.assertEqual(self.counts(),state)
    def test_reconcile_cash_and_payment_are_distinct_and_replay_exact(self):
        d=self.source();_,imported=self.commit(self.import_payload(d));line=imported['lines'][0]['line_id'];key=str(uuid4())
        payload={'action':'erp_statement_reconcile','line_id':line,'transaction':{'mode':'create_transaction','category':'customer','description':'C03 локальний грошовий запис'},'matching':{'kind':'manual','counterparty_id':self.customer.pk,'counterparty_external_id':'client-1'},'reason':'Погоджено точний первинний рядок','allocations':[{'allocation_key':key,'mode':'new_payment','invoice_id':self.invoice.pk,'amount':'10.00','currency':'EUR','invoice_match':'exact_reference','reason':'Повна оплата зазначеного рахунку'}]}
        preview,receipt=self.commit(payload);self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid,D('10'));self.assertEqual(Transaction.objects.count(),1);self.assertEqual(FinancialIntent.objects.count(),1)
        self.assertEqual(Event.objects.filter(action='erp_payment').count(),1);self.assertEqual(Event.objects.filter(action='erp_statement_reconcile').count(),1)
        self.assertEqual(receipt['allocated'],'10.00');self.assertEqual(receipt['unallocated'],'0.00');self.assertEqual(len(receipt['new_allocation_ids']),1)
        state=self.counts();replay=self.post('/api/operations/confirm/',{'proposal_id':preview['id'],'confirmed':True})
        self.assertEqual(replay.status_code,200,replay.content);self.assertEqual(replay.json(),receipt);self.assertEqual(self.counts(),state)
        no_change=self.post('/api/erp/preview/',payload);self.assertEqual(no_change.status_code,200,no_change.content);self.assertEqual(no_change.json()['state'],'no_change');self.assertEqual(self.counts(),state)
    def test_source_marker_stays_private_after_access_label_change_and_search_works(self):
        d=self.source();Document.objects.filter(pk=d['id']).update(access_level='operational')
        manager=Client(enforce_csrf_checks=True,raise_request_exception=False);login_test_client(manager,'manager',capabilities=('view_document','download_document'))
        for path in (f"/api/operations/documents/{d['id']}/",f"/api/operations/documents/{d['id']}/download/"):
            self.assertEqual(manager.get(path).status_code,404)
        self.assertNotIn(d['id'],[x['id'] for x in manager.get('/api/operations/documents/?q=C03-SOURCE').json()['items']])
        searched=self.http.get('/api/operations/documents/?q=C03-SOURCE');self.assertEqual(searched.status_code,200,searched.content)
        self.assertEqual(searched.json()['items'][0]['format'],'bos_statement_csv_v1')
        blocked=self.post('/api/erp/preview/',self.import_payload(d));self.assertEqual(blocked.status_code,422,blocked.content)
    def test_overlap_and_changed_identity_preserve_original_fields_and_first_source(self):
        d=self.source();_,first=self.commit(self.import_payload(d));original=apps.get_model('finance','StatementLine').objects.get();before=dict(original.__dict__)
        raw=self.csv([['bank-2','2026-09-01','in','10.00','EUR','','','Другий незалежний рядок'],['bank-1','2026-09-01','in','10.00','EUR','client-1','C03-INV','Оплата першого рахунку']])
        second=self.source(raw,'C03-OVERLAP');_,r=self.commit(self.import_payload(second));self.assertEqual(r['counts'],{'create':1,'reuse':1,'total':2})
        original.refresh_from_db();self.assertEqual(original.first_import_id,before['first_import_id']);self.assertEqual(original.purpose,before['purpose'])
        detail=self.http.get(f"/api/statements/imports/{r['import_id']}/");self.assertEqual(detail.status_code,200,detail.content);self.assertEqual(len(detail.json()['lines']),2)
        changed=self.source(self.csv([['bank-1','2026-09-01','in','10.01','EUR','client-1','C03-INV','Оплата першого рахунку']]),'C03-CONFLICT');state=self.counts()
        r=self.post('/api/erp/preview/',self.import_payload(changed));self.assertEqual(r.status_code,409,r.content);self.assertEqual(r.json()['code'],'statement_identity_conflict');self.assertEqual(self.counts(),state)
    def test_existing_payment_binding_never_increments_paid_or_makes_second_payment(self):
        _,manual=self.commit({'action':'erp_payment','invoice_id':self.invoice.pk,'amount':'10.00','reference':'C03-OLD-PAY'})
        d=self.source();_,imp=self.commit(self.import_payload(d));key=str(uuid4())
        payload={'action':'erp_statement_reconcile','line_id':imp['lines'][0]['line_id'],'transaction':{'mode':'create_transaction','category':'customer','description':'Зіставлення історичної оплати'},'matching':{'kind':'manual','counterparty_id':self.customer.pk,'counterparty_external_id':'client-1'},'reason':'Первинна оплата вже проведена у ERP','allocations':[{'allocation_key':key,'mode':'existing_payment','payment_event_id':manual['erp_event_id'],'invoice_id':self.invoice.pk,'amount':'10.00','currency':'EUR','invoice_match':'exact_reference','reason':'Звірено повну суму первинної оплати'}]}
        _,r=self.commit(payload);self.invoice.refresh_from_db();self.assertEqual(self.invoice.paid,D('10'))
        self.assertEqual(Event.objects.filter(action='erp_payment').count(),1);self.assertEqual(r['created_payment_event_ids'],[]);self.assertEqual(r['reused_payment_event_ids'],[manual['erp_event_id']])
        detail=self.http.get(f"/api/statements/lines/{imp['lines'][0]['line_id']}/");self.assertEqual(detail.status_code,200,detail.content)
        self.assertEqual(detail.json()['invoices'][0]['settlement']['receivable'],'0.00')
    def test_unallocated_cash_then_allocation_and_archived_cash_summary(self):
        d=self.source();_,imp=self.commit(self.import_payload(d));payload={'action':'erp_statement_reconcile','line_id':imp['lines'][0]['line_id'],'transaction':{'mode':'create_transaction','category':'customer','description':'Повний грошовий запис без розподілу'},'matching':{'kind':'manual','counterparty_id':self.customer.pk,'counterparty_external_id':'client-1'},'reason':'Кошти відображено до звірки рахунку','allocations':[]}
        _,first=self.commit(payload);self.invoice.refresh_from_db();self.assertEqual(self.invoice.paid,D(0));self.assertEqual(first['unallocated'],'10.00')
        payload['allocations']=[{'allocation_key':str(uuid4()),'mode':'new_payment','invoice_id':self.invoice.pk,'amount':'10.00','currency':'EUR','invoice_match':'exact_reference','reason':'Наступне явне погодження розподілу'}]
        _,second=self.commit(payload);self.assertFalse(second['transaction_created']);self.assertFalse(second['binding_created']);self.assertEqual(Transaction.objects.count(),1)
        archived=self.http.delete(f"/api/transactions/{first['transaction_id']}/",HTTP_X_CSRFTOKEN=self.http.cookies[settings.CSRF_COOKIE_NAME].value);self.assertEqual(archived.status_code,204,archived.content)
        summary=self.http.get('/api/transactions/summary/');self.assertEqual(summary.status_code,200,summary.content)
        self.assertTrue(summary.json()['includes_archived']);eur=next(x for x in summary.json()['currencies'] if x['currency']=='EUR');self.assertEqual(eur['in'],'10.00')
        protected=self.http.patch(f"/api/transactions/{first['transaction_id']}/",json.dumps({'description':'Спроба змінити первинний запис'}),content_type='application/json',HTTP_X_CSRFTOKEN=self.http.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertEqual(protected.status_code,400,protected.content)
    def test_candidates_signed_scope_and_complete_invoice_choices(self):
        d=self.source();_,imp=self.commit(self.import_payload(d));line=imp['lines'][0]['line_id']
        for n in range(3):Invoice.objects.create(code='C03-EXTRA-'+str(n),customer=self.customer,amount='3.00',currency='EUR',due_date=date(2026,9,30))
        path=f'/api/statements/lines/{line}/candidates/'
        first=self.http.get(path+'?section=invoices&limit=2');self.assertEqual(first.status_code,200,first.content);self.assertEqual(len(first.json()['items']),2)
        cursor=first.json()['next_cursor'];self.assertTrue(cursor)
        from urllib.parse import urlencode
        second=self.http.get(path+'?'+urlencode({'section':'invoices','limit':'2','cursor':cursor}));self.assertEqual(second.status_code,200,second.content)
        self.assertEqual(len({x['id'] for x in first.json()['items']+second.json()['items']}),4)
        changed=self.http.get(path+'?'+urlencode({'section':'transactions','limit':'2','cursor':cursor}));self.assertEqual(changed.status_code,400,changed.content)
        for section in ('transactions','payments','identities','salaries'):
            r=self.http.get(path+'?section='+section);self.assertEqual(r.status_code,200,r.content)
