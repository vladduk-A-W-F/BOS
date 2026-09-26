"""C03 additive actual HTTP/SQL races; no money writers or outcomes are mocked."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
from decimal import Decimal as D
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, connections, transaction
from django.test import Client, TransactionTestCase, override_settings

from finance.models import Counterparty, Transaction, FinancialIntent, StatementImport, StatementLine, StatementAllocation
from operations.models import Configuration, Document, Invoice, ActionProposal, AuditEvent
from erp.models import Event
from scripts.check_support import login_test_client


CURRENCIES = ('EUR','USD','UAH')
AMOUNTS = {'EUR':'17.39','USD':'123.45','UAH':'9801.07'}
STATEMENT_COVERAGE_MANIFEST = {
    'statement_import': {'inventory_ids':['ERP-statement_import','CORE-erp-preview','CORE-execute','CORE-confirm','CORE-dispatch'],
        'route':'/api/operations/confirm/','identity':'same proposal_id',
        'test':'StatementConcurrencyTests.test_http_pair_statement_import','currencies':['EUR','USD','UAH']},
    'statement_reconcile': {'inventory_ids':['ERP-statement_reconcile','CORE-erp-preview','CORE-execute','CORE-confirm','CORE-dispatch'],
        'route':'/api/operations/confirm/','identity':'same proposal_id',
        'test':'StatementConcurrencyTests.test_http_pair_statement_reconcile','currencies':['EUR','USD','UAH']},
}


@override_settings(BOS_DATA_MODE='working',DEBUG=False,ANTHROPIC_API_KEY='',
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StatementConcurrencyTests(TransactionTestCase):
    databases = {'default'}

    def setUp(self):
        self.assertEqual(os.environ.get('DJANGO_SETTINGS_MODULE'),'verification_settings')
        self.assertIn(connection.vendor,('sqlite','postgresql'))
        if connection.vendor=='sqlite':
            self.assertTrue(Path(str(connection.settings_dict['NAME'])).name.startswith('check_'))
            self.assertNotIn('memory',str(connection.settings_dict['NAME']).lower())
        folder=tempfile.TemporaryDirectory(prefix='bos-c03-concurrency-');self.addCleanup(folder.cleanup)
        self.media=Path(folder.name)/'private';self.media.mkdir(mode=0o700)
        media_override=override_settings(MEDIA_ROOT=self.media);media_override.enable();self.addCleanup(media_override.disable)
        self.http=Client(enforce_csrf_checks=True,raise_request_exception=False)
        self.user=login_test_client(self.http,'ceo',capabilities=('view_document','download_document','export_workspace'))
        Configuration.objects.create(key='erp_write',value={'revision':0})
        Configuration.objects.create(key='dataset',value={'as_of':'2026-09-12'})
        self.customer=Counterparty.objects.create(name='C03 concurrency synthetic customer',type='customer')

    def twin(self):
        client=Client(enforce_csrf_checks=True,raise_request_exception=False)
        client.cookies=deepcopy(self.http.cookies)
        return client

    def request(self,method,path,payload=None,client=None):
        client=client or self.http
        args={'HTTP_X_CSRFTOKEN':client.cookies[settings.CSRF_COOKIE_NAME].value}
        if payload is not None:args.update(data=json.dumps(payload,ensure_ascii=False),content_type='application/json')
        response=getattr(client,method)(path,**args)
        if response.streaming:
            body=b''.join(response.streaming_content);response.close();return {'status':response.status_code,'bytes':body}
        return {'status':response.status_code,'json':response.json() if response.content else None}

    def post(self,path,payload,client=None):return self.request('post',path,payload,client)

    def state(self,proposals=True):
        result={}
        for model in apps.get_models():
            label=model._meta.label
            if model._meta.app_label not in {'operations','erp','finance','employees','branches','tasks','ai_assistant'}:continue
            if label=='operations.LoginAttempt' or (not proposals and label=='operations.ActionProposal'):continue
            rows=model._base_manager.order_by('pk')
            if label=='operations.Configuration':rows=rows.exclude(key='erp_write')
            result[label]=list(rows.values())
        return result

    def source(self,currency,tag):
        # Invoice codes are data, not test names; keep them within the 30-character field.
        code='C03-'+currency+'-'+uuid4().hex[:12]
        invoice=Invoice.objects.create(code=code,customer=self.customer,amount=AMOUNTS[currency],
            paid='0.00',currency=currency,due_date=date(2026,9,30))
        raw=('external_id,booking_date,direction,amount,currency,counterparty_external_id,invoice_reference,purpose\n'
            +code+',2026-09-12,in,'+AMOUNTS[currency]+','+currency+',race-customer,'+code+',Synthetic concurrency source\n').encode()
        response=self.http.post('/api/statements/sources/',{'file':SimpleUploadedFile('race.csv',raw,content_type='text/csv'),
            'code':code,'revision':'A','title':'Synthetic C03 concurrency source'},
            HTTP_X_CSRFTOKEN=self.http.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertEqual(response.status_code,201,response.content);doc=response.json()
        reviewed=self.post(f"/api/operations/documents/{doc['id']}/review/",{'checksum':doc['checksum']})
        self.assertEqual(reviewed['status'],200,reviewed)
        self.assertEqual(doc['checksum'],hashlib.sha256(raw).hexdigest())
        source=self.request('get',f"/api/operations/documents/{doc['id']}/download/")
        self.assertEqual(source,{'status':200,'bytes':raw})
        payload={'action':'erp_statement_import','document_id':doc['id'],'source_sha256':doc['checksum'],
            'source_system':'synthetic-race','account_ref':'RACE-'+currency,'format':'bos_statement_csv_v1','parser_version':'1'}
        return {'currency':currency,'amount':AMOUNTS[currency],'invoice':invoice,'raw':raw,'document':doc,'payload':payload}

    def preview(self,payload,client=None):
        before=self.state(proposals=False);count=ActionProposal.objects.count()
        result=self.post('/api/erp/preview/',payload,client)
        self.assertEqual(result['status'],200,result);self.assertTrue(result['json']['id'])
        self.assertEqual(self.state(proposals=False),before,'Preview must preserve all business rows')
        self.assertEqual(ActionProposal.objects.count(),count+1)
        return result['json']

    def confirm(self,proposal,client=None):
        return self.post('/api/operations/confirm/',{'proposal_id':proposal['id'],'confirmed':True},client)

    def commit(self,payload):
        proposal=self.preview(payload);result=self.confirm(proposal)
        self.assertEqual(result['status'],200,result)
        return proposal,result['json']

    def imported(self,currency,tag):
        fixture=self.source(currency,tag);_,receipt=self.commit(fixture['payload'])
        fixture['line_id']=receipt['lines'][0]['line_id'];fixture['import_receipt']=receipt
        return fixture

    def reconcile(self,fixture,existing=None):
        tx={'mode':'existing_transaction','transaction_id':existing} if existing else {
            'mode':'create_transaction','category':'customer','description':'C03 real concurrent financial intent'}
        return {'action':'erp_statement_reconcile','line_id':fixture['line_id'],'transaction':tx,
            'matching':{'kind':'manual','counterparty_id':self.customer.pk,'counterparty_external_id':'race-customer'},
            'reason':'Explicit matching of the synthetic source and customer',
            'allocations':[{'allocation_key':str(uuid4()),'mode':'new_payment','invoice_id':fixture['invoice'].pk,
                'amount':fixture['amount'],'currency':fixture['currency'],'invoice_match':'exact_reference',
                'reason':'The complete invoice code and exact amount were checked'}]}

    def pair(self,proposals,clients=None):
        barrier=threading.Barrier(2);clients=clients or [self.twin(),self.twin()]
        def worker(index):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                return self.confirm(proposals[index],clients[index])
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(worker,range(2)))

    def successful_pair(self,proposals,clients=None):
        results=self.pair(proposals,clients);statuses=[r['status'] for r in results]
        self.assertIn(200,statuses,results);self.assertTrue(all(s in (200,409) for s in statuses),results)
        success=next(r['json'] for r in results if r['status']==200)
        return results,statuses,success

    def assert_import(self,fixture,receipt,before):
        self.assertEqual(receipt['counts'],{'create':1,'reuse':0,'total':1})
        self.assertEqual(StatementImport.objects.count(),before['imports']+1)
        self.assertEqual(StatementLine.objects.count(),before['lines']+1)
        self.assertEqual(Event.objects.count(),before['events']+1)
        self.assertEqual(Transaction.objects.count(),before['transactions'])
        self.assertEqual(FinancialIntent.objects.count(),before['intents'])
        self.assertEqual(AuditEvent.objects.count(),before['audits'])
        record=StatementImport.objects.get(pk=receipt['import_id'])
        self.assertEqual(record.first_commit_receipt,receipt);self.assertEqual(record.actor_id,self.user.pk)
        line=StatementLine.objects.get(pk=receipt['lines'][0]['line_id'])
        self.assertEqual((line.currency,line.amount,line.transaction_id),(fixture['currency'],D(fixture['amount']),None))

    def counts(self):
        return {'imports':StatementImport.objects.count(),'lines':StatementLine.objects.count(),
            'events':Event.objects.count(),'transactions':Transaction.objects.count(),
            'intents':FinancialIntent.objects.count(),'audits':AuditEvent.objects.count(),
            'allocations':StatementAllocation.objects.count()}

    def assert_reconcile(self,fixture,payload,before,new=True,actor_id=None):
        actor_id=self.user.pk if actor_id is None else actor_id
        fixture['invoice'].refresh_from_db();line=StatementLine.objects.get(pk=fixture['line_id'])
        self.assertEqual(fixture['invoice'].paid,D(fixture['amount']))
        self.assertEqual(Transaction.objects.count(),before['transactions']+int(new))
        self.assertEqual(FinancialIntent.objects.count(),before['intents']+int(new))
        self.assertEqual(AuditEvent.objects.count(),before['audits']+int(new))
        self.assertEqual(Event.objects.count(),before['events']+2)
        self.assertEqual(StatementAllocation.objects.count(),before['allocations']+1)
        self.assertEqual(line.bound_by_id,actor_id)
        self.assertEqual((line.transaction.amount,line.transaction.currency,line.transaction.counterparty_id),
            (D(fixture['amount']),fixture['currency'],self.customer.pk))
        allocation=StatementAllocation.objects.get(allocation_key=payload['allocations'][0]['allocation_key'])
        self.assertEqual((allocation.line_id,allocation.invoice_id,allocation.actor_id),
            (line.pk,fixture['invoice'].pk,actor_id))
        payment=allocation.payment_event
        self.assertEqual(payment.action,'erp_payment');self.assertEqual(D(payment.payload['amount']),D(fixture['amount']))
        self.assertEqual(payment.payload['reference'],'STMT-'+payload['allocations'][0]['allocation_key'].replace('-',''))
        return line

    def replay_unchanged(self,proposal,receipt,client=None):
        state=self.state();again=self.confirm(proposal,client)
        self.assertEqual(again,{'status':200,'json':receipt});self.assertEqual(self.state(),state)

    def pass_record(self,action,currency,statuses,receipt):
        print('A06_PASS '+json.dumps({'mode':'http','action':action,'currency':currency,
            'inventory_id':'ERP-'+action,'erp_event_id':receipt['erp_event_id'],'statuses':statuses,
            'one_effect':True,'replay_unchanged':True},ensure_ascii=False))

    def test_http_pair_statement_import(self):
        for currency in CURRENCIES:
            with self.subTest(currency=currency):
                fixture=self.source(currency,'PAIR-IMPORT');before=self.counts();proposal=self.preview(fixture['payload'])
                results,statuses,receipt=self.successful_pair([proposal,proposal])
                for result in results:
                    if result['status']==200:self.assertEqual(result['json'],receipt)
                self.assert_import(fixture,receipt,before);self.replay_unchanged(proposal,receipt)
                state=self.state();no_change=self.post('/api/erp/preview/',fixture['payload'])
                self.assertEqual(no_change['status'],200,no_change)
                self.assertEqual((no_change['json']['state'],no_change['json']['id']),('no_change',None))
                self.assertEqual(no_change['json']['first_commit_receipt'],receipt);self.assertEqual(self.state(),state)
                self.pass_record('statement_import',currency,statuses,receipt)

    def test_http_pair_statement_reconcile(self):
        for currency in CURRENCIES:
            with self.subTest(currency=currency):
                fixture=self.imported(currency,'PAIR-RECONCILE');payload=self.reconcile(fixture)
                before=self.counts();proposal=self.preview(payload);results,statuses,receipt=self.successful_pair([proposal,proposal])
                for result in results:
                    if result['status']==200:self.assertEqual(result['json'],receipt)
                line=self.assert_reconcile(fixture,payload,before);self.replay_unchanged(proposal,receipt)
                archived=self.request('delete',f'/api/transactions/{line.transaction_id}/')
                self.assertEqual(archived['status'],204,archived)
                self.assertIsNotNone(Transaction.objects.get(pk=line.transaction_id).archived_at)
                self.replay_unchanged(proposal,receipt)
                self.pass_record('statement_reconcile',currency,statuses,receipt)

    def test_distinct_import_proposals_same_source_have_one_immutable_effect(self):
        for currency in CURRENCIES:
            with self.subTest(currency=currency):
                fixture=self.source(currency,'DUP-IMPORT');before=self.counts()
                proposals=[self.preview(fixture['payload']),self.preview(fixture['payload'])]
                results,_,receipt=self.successful_pair(proposals);self.assert_import(fixture,receipt,before)
                domain=self.state(proposals=False)
                for proposal in proposals:
                    # A transport-conflict loser has not yet stored a receipt;
                    # its first domain reuse may fill that proposal only.
                    self.assertEqual(self.confirm(proposal),{'status':200,'json':receipt})
                    self.assertEqual(self.state(proposals=False),domain)
                    self.replay_unchanged(proposal,receipt)
                self.assertEqual(StatementImport.objects.get(pk=receipt['import_id']).first_commit_receipt,receipt)

    def test_distinct_reconcile_proposals_same_allocation_key_have_one_cash_payment(self):
        other=Client(enforce_csrf_checks=True,raise_request_exception=False)
        other_user=login_test_client(other,'ceo',capabilities=('view_document','download_document','export_workspace'))
        for currency in CURRENCIES:
            with self.subTest(currency=currency):
                fixture=self.imported(currency,'DUP-RECONCILE');payload=self.reconcile(fixture);before=self.counts()
                proposals=[self.preview(payload),self.preview(payload,other)]
                actors=[self.user.pk,other_user.pk];clients=[self.twin(),other]
                results,_,_=self.successful_pair(proposals,clients)
                winner=next(i for i,r in enumerate(results) if r['status']==200 and not r['json'].get('no_change'))
                line=self.assert_reconcile(fixture,payload,before,actor_id=actors[winner])
                domain=self.state(proposals=False)
                receipts=[]
                for index,proposal in enumerate(proposals):
                    result=self.confirm(proposal,clients[index]);self.assertEqual(result['status'],200,result)
                    receipts.append(result['json']);self.assertEqual(self.state(proposals=False),domain)
                    self.replay_unchanged(proposal,result['json'],clients[index])
                first=[r for r in receipts if not r.get('no_change')]
                reused=[r for r in receipts if r.get('no_change')]
                self.assertEqual(len(first),1);self.assertEqual(len(reused),1)
                self.assertEqual(line.binding_snapshot['first_commit_receipt'],first[0])
                self.assertEqual(reused[0]['transaction_id'],first[0]['transaction_id'])
                self.assertEqual(reused[0]['allocation_ids'],first[0]['new_allocation_ids'])

    def existing_transaction(self,fixture):
        # Finance creation requires its existing idempotency header; use the
        # actual HTTP route with a fresh synthetic key, never a raw money insert.
        response=self.http.post('/api/transactions/',json.dumps({'direction':'in','amount':fixture['amount'],
            'currency':fixture['currency'],'date':'2026-09-12','description':'Original selected cash record',
            'category':'customer','counterparty':self.customer.pk}),content_type='application/json',
            HTTP_X_CSRFTOKEN=self.http.cookies[settings.CSRF_COOKIE_NAME].value,HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.assertEqual(response.status_code,201,response.content)
        return response.json()['id']

    def held_pair(self,holder,waiter,while_held):
        held=threading.Event();release=threading.Event();attempted=threading.Event();done=threading.Event()
        blocked=[];trace=[];early=[]
        def first():
            connections.close_all()
            try:
                with transaction.atomic():
                    result=holder(self.twin());held.set()
                    if not release.wait(10):raise RuntimeError('Held transaction release timeout')
                return result
            finally:connections.close_all()
        def second():
            connections.close_all()
            def observe(execute,sql,params,many,context):
                if sql.lstrip().upper().startswith('UPDATE') and ('finance_transaction' in sql or 'operations_configuration' in sql):
                    trace.append('transaction' if 'finance_transaction' in sql else 'erp_mutex');attempted.set()
                return execute(sql,params,many,context)
            try:
                with connection.execute_wrapper(observe):return waiter(self.twin())
            finally:done.set();connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            hold=pool.submit(first)
            try:
                self.assertTrue(held.wait(10),'Holder did not execute its actual HTTP writer')
                wait=pool.submit(second);self.assertTrue(attempted.wait(10),'Waiter did not reach actual SQL UPDATE')
                blocked.append(not done.wait(.15))
                if not blocked[0]:
                    early.append(wait.result(timeout=1))
                    self.assertEqual(connection.vendor,'sqlite','PostgreSQL row writer must wait for the held lock')
                    self.assertEqual(early[0]['status'],409,early)
                while_held()
            finally:release.set()
            result=[hold.result(timeout=20),wait.result(timeout=20)]
        self.assertTrue(blocked[0] or (connection.vendor=='sqlite' and early[0]['status']==409))
        return result,trace,{'waited':blocked[0],'controlled_conflict_while_held':bool(early),
            'uncommitted_business_not_visible':True}

    def test_held_transaction_writes_serialize_before_reconcile_fingerprint_and_binding(self):
        for currency in CURRENCIES:
            with self.subTest(currency=currency):
                fixture=self.imported(currency,'HELD-PATCH');pk=self.existing_transaction(fixture)
                payload=self.reconcile(fixture,pk);proposal=self.preview(payload);before=self.counts()
                visible_state=self.state(proposals=False)
                def unchanged_while_held():
                    self.assertEqual(self.state(proposals=False),visible_state,'Held business mutation must remain invisible')
                    self.assertIsNone(StatementLine.objects.get(pk=fixture['line_id']).transaction_id)
                    self.assertEqual(Invoice.objects.get(pk=fixture['invoice'].pk).paid,D(0))
                    self.assertEqual(Event.objects.count(),before['events'])
                    self.assertEqual(StatementAllocation.objects.count(),before['allocations'])
                results,trace,first_lock=self.held_pair(
                    lambda c:self.request('patch',f'/api/transactions/{pk}/',{'description':'Changed by actual held writer'},c),
                    lambda c:self.confirm(proposal,c),unchanged_while_held)
                self.assertEqual([r['status'] for r in results],[200,409],results)
                first_statuses=[r['status'] for r in results]
                self.assertEqual(self.confirm(proposal)['status'],409,'Retry after release must revalidate the changed fingerprint')
                if connection.vendor=='postgresql':self.assertIn('transaction',trace)
                else:self.assertTrue(any(x in trace for x in ('transaction','erp_mutex')))
                self.assertIsNone(StatementLine.objects.get(pk=fixture['line_id']).transaction_id)
                fixture['invoice'].refresh_from_db();self.assertEqual(fixture['invoice'].paid,D(0))
                self.assertEqual(Event.objects.count(),before['events']);self.assertEqual(StatementAllocation.objects.count(),before['allocations'])
                self.assertEqual(Transaction.objects.get(pk=pk).description,'Changed by actual held writer')
                # A fresh explicit preview is necessary after the stale proposal.
                fresh=self.preview(payload);before=self.counts()
                visible_state=self.state(proposals=False)
                results,reverse_trace,reverse_lock=self.held_pair(
                    lambda c:self.confirm(fresh,c),
                    lambda c:self.request('patch',f'/api/transactions/{pk}/',{'description':'Must not replace bound source'},c),
                    unchanged_while_held)
                self.assertEqual(results[0]['status'],200,results)
                self.assertIn(results[1]['status'],(400,409) if connection.vendor=='sqlite' else (400,),results)
                reverse_initial=[r['status'] for r in results]
                retry=self.request('patch',f'/api/transactions/{pk}/',{'description':'Must not replace bound source'})
                self.assertEqual(retry['status'],400,retry)
                self.assertIn('transaction',reverse_trace)
                self.assert_reconcile(fixture,payload,before,new=False)
                self.assertEqual(Transaction.objects.get(pk=pk).description,'Changed by actual held writer')
                self.replay_unchanged(fresh,results[0]['json'])
                print('C03_HELD_TRANSACTION '+json.dumps({'currency':currency,'actual_vendor':connection.vendor,
                    'patch_then_reconcile_statuses':first_statuses,
                    'reconcile_then_patch_statuses':reverse_initial,'bound_edit_retry_status':retry['status'],
                    'first_trace':trace,'reverse_trace':reverse_trace,'first_lock':first_lock,'reverse_lock':reverse_lock,
                    'stale_reconcile_refused':True,'bound_source_edit_refused':True},ensure_ascii=False))
