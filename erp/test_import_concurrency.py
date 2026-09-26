"""Additional B02 concurrency evidence; the original A06 84/89 baseline stays intact."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
import json
import threading
from unittest.mock import patch
from uuid import uuid4

from django.db import connection,connections
from django.test import Client,TransactionTestCase,override_settings
from erp.test_initial_import import InitialImportFixture
from erp.models import Purchase,Event,ImportBatch,ImportIdentity,Lot,Movement
from operations.models import ActionProposal
from finance.models import Counterparty
from employees.models import Employee


@override_settings(BOS_DATA_MODE='working',DEBUG=False,ANTHROPIC_API_KEY='',PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ERPImportConcurrencyTests(InitialImportFixture,TransactionTestCase):
    def twins(self):
        result=[]
        for _ in range(2):
            client=Client(enforce_csrf_checks=True,raise_request_exception=False);client.cookies=deepcopy(self.http.cookies);result.append(client)
        return result

    def pair(self,previews):
        barrier=threading.Barrier(2);clients=self.twins()
        def worker(index):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                r=self.post('/api/operations/confirm/',{'proposal_id':previews[index]['proposal']['id'],'confirmed':True},clients[index])
                return {'status':r.status_code,'json':r.json()}
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(worker,range(2)))

    def test_http_pair_import_batch(self):
        for currency in ('EUR','USD','UAH'):
            with self.subTest(currency=currency):
                batch=self.batch(currency,currency);p=self.preview(batch);before_events=Event.objects.count();before_po=Purchase.objects.count()
                results=self.pair([p,p]);statuses=[r['status'] for r in results]
                self.assertIn(200,statuses,results);self.assertTrue(all(x in (200,409) for x in statuses),results)
                good=next(r['json'] for r in results if r['status']==200)
                for result in results:
                    if result['status']==200:self.assertEqual(result['json'],good)
                self.assertEqual(Event.objects.count(),before_events+1);self.assertEqual(Purchase.objects.count(),before_po+1)
                self.assertEqual(ImportBatch.objects.filter(pk=batch['batch_id']).count(),1)
                self.assertEqual(ImportIdentity.objects.filter(namespace=batch['namespace']).count(),9)
                self.assertEqual(ImportBatch.objects.get(pk=batch['batch_id']).receipt,good)
                after=self.state();replay=self.confirm(p);self.assertEqual(replay.status_code,200,replay.content);self.assertEqual(replay.json(),good);self.assertEqual(self.state(),after)
                print('A06_PAIR '+json.dumps({'mode':'http','action':'import_batch','currency':currency,'workers':results},ensure_ascii=False))
                print('A06_PASS '+json.dumps({'mode':'http','action':'import_batch','currency':currency,'inventory_id':'ERP-import_batch','erp_event_id':good['erp_event_id'],'statuses':statuses,'one_effect':True,'replay_unchanged':True},ensure_ascii=False))

    def test_distinct_batches_same_source_ids_have_one_effect_and_stale_loser(self):
        batch=self.batch();other=deepcopy(batch);other['batch_id']=str(uuid4());first=self.preview(batch);second=self.preview(other)
        results=self.pair([first,second]);self.assertEqual(sorted(r['status'] for r in results),[200,409],results)
        self.assertEqual(Purchase.objects.count(),1);self.assertEqual(Event.objects.count(),1);self.assertEqual(ImportIdentity.objects.count(),9)
        self.assertEqual(Movement.objects.count(),2)
        loser=results.index(next(r for r in results if r['status']==409));before=self.state()
        self.assertEqual(self.confirm([first,second][loser]).status_code,409);self.assertEqual(self.state(),before)

    def locked_crud(self,kind):
        from erp import importing
        batch=self.batch();supplier=Counterparty.objects.create(name='B02 lock source',type='supplier')
        batch['rows']=[r for r in batch['rows'] if r['external_id']!='supplier'];batch['expected_source_control_totals']['counts']['counterparty']=1
        batch['bindings']=[{'entity':'counterparty','external_id':'supplier','target_id':supplier.pk}]
        preview=self.preview(batch);entered=threading.Event();attempted=threading.Event();done=threading.Event();checks=[]
        original=importing.locked_references;once=[False]
        def hold(value):
            original(value)
            if not once[0]:
                once[0]=True;entered.set();self.assertTrue(attempted.wait(10),'Updater did not reach SQL')
                checks.append(not done.wait(.1))
        def updater():
            connections.close_all()
            def trace(execute,sql,params,many,context):
                if sql.lstrip().upper().startswith('UPDATE'):attempted.set()
                return execute(sql,params,many,context)
            try:
                self.assertTrue(entered.wait(10))
                with connection.execute_wrapper(trace):
                    if kind=='counterparty':Counterparty.objects.filter(pk=supplier.pk).update(type='customer')
                    else:Employee.objects.filter(pk=self.owner.pk).delete()
                done.set()
            finally:connections.close_all()
        client=self.twins()[0]
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(updater)
            with patch.object(importing,'locked_references',side_effect=hold):
                response=self.post('/api/operations/confirm/',{'proposal_id':preview['proposal']['id'],'confirmed':True},client)
            future.result(timeout=20)
        self.assertEqual(response.status_code,200,response.content);self.assertEqual(checks,[True]);self.assertTrue(done.is_set())
        self.assertEqual(Purchase.objects.count(),1)
        if kind=='counterparty':self.assertEqual(Counterparty.objects.get(pk=supplier.pk).type,'customer')
        else:self.assertIsNotNone(Employee.objects.get(pk=self.owner.pk).archived_at)

    def test_counterparty_update_serializes_behind_import_reference_lock(self):self.locked_crud('counterparty')
    def test_employee_archive_serializes_behind_import_reference_lock(self):self.locked_crud('employee')
