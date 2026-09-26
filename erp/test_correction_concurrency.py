"""B03 additive real HTTP pairs; prior A06/B02 methods and records are retained."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal as D
import json
import threading
from uuid import uuid4
from django.db import connections
from django.test import Client,TransactionTestCase,override_settings
from erp.test_corrections import CorrectionFixture
from erp.models import Event,Purchase,Movement,Lot
from erp.corrections import DOCUMENT_MODELS,MODELS
from operations.models import ActionProposal,Invoice
from erp.balances import purchase_open,invoice_settlement

ACTIONS=('cancel_remaining','return_supplier','return_from_shipment','credit_invoice','reverse_credit','confirm_supplier_claim')

@override_settings(BOS_DATA_MODE='working',DEBUG=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ERPCorrectionConcurrencyTests(CorrectionFixture,TransactionTestCase):
    def pair(self,ids):
        barrier=threading.Barrier(2);clients=[]
        for unused in range(2):
            client=Client(enforce_csrf_checks=True,raise_request_exception=False);client.cookies=deepcopy(self.http.cookies);clients.append(client)
        def worker(index):
            connections.close_all()
            try:
                barrier.wait(timeout=10);response=self.confirm(ids[index],clients[index]);return {'status':response.status_code,'json':response.json()}
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(worker,range(2)))

    def source(self,action,currency):
        if action in ('cancel_remaining','return_supplier','confirm_supplier_claim'):
            po,lot,source=self.supply(quantity='2.000',ordered='3.000',currency=currency)
            if action=='cancel_remaining':return self.command(action,purchase_id=po.pk,quantity='1.000')
            if action=='return_supplier':return self.command(action,receipt_id=source.pk,quantity='2.000')
            _,ret=self.correction(self.command('return_supplier',receipt_id=source.pk,quantity='1.000'))
            return self.command(action,claim_id=ret['claim_id'],amount='1.00',currency=currency,source_document_id=self.f.spec.pk)
        order,line,lot,source=self.sale(shipped='2.000',quantity='2.000',price='10.00',currency=currency)
        if action=='return_from_shipment':return self.command(action,shipment_id=source.pk,quantity='2.000',location_id=self.location.pk)
        inv=self.act('invoice',order_id=order.pk,code='B03-CON-INV-'+uuid4().hex[:12],due_date='2026-10-01')
        credit=self.command('credit_invoice',invoice_id=inv['invoice_id'],basis='commercial',source_document_id=self.f.spec.pk,allocations=[{'invoice_line_index':0,'amount':'20.00'}])
        if action=='credit_invoice':return credit
        _,created=self.correction(credit);return self.command(action,credit_id=created['invoice_adjustment_id'])

    def same_proposal(self,action):
        for currency in ('EUR','USD','UAH'):
            with self.subTest(currency=currency):
                payload=self.source(action,currency);proposal=self.preview(payload);before=Event.objects.count();gross=self.gross();model=DOCUMENT_MODELS[action]
                results=self.pair([proposal,proposal]);statuses=[r['status'] for r in results]
                self.assertIn(200,statuses,results);self.assertTrue(all(s in (200,409) for s in statuses),results)
                good=next(r['json'] for r in results if r['status']==200)
                for result in results:
                    if result['status']==200:self.assertEqual(result['json'],good)
                self.assertEqual(Event.objects.count(),before+1);self.assertEqual(model.objects.filter(operation_id=payload['operation_id']).count(),1);self.assertEqual(self.gross(),gross)
                row=model.objects.get(operation_id=payload['operation_id']);self.assertEqual(row.event.result,good);self.assertEqual(row.event.payload,payload)
                state={m._meta.label:list(m.objects.values()) for m in MODELS};replay=self.confirm(proposal);self.assertEqual(replay.status_code,200);self.assertEqual(replay.json(),good);self.assertEqual({m._meta.label:list(m.objects.values()) for m in MODELS},state)
                if action.startswith('return_'):
                    self.assertEqual(abs(row.result.quantity),row.quantity);self.assertEqual(row.result.cost,row.allocated_cost)
                if action=='cancel_remaining':self.assertEqual(purchase_open(Purchase.objects.get(pk=payload['purchase_id'])),D(0))
                print('A06_PAIR '+json.dumps({'mode':'http','action':action,'currency':currency,'workers':results},ensure_ascii=False))
                print('A06_PASS '+json.dumps({'mode':'http','action':action,'currency':currency,'inventory_id':'ERP-'+action,'erp_event_id':good['erp_event_id'],'statuses':statuses,'one_effect':True,'replay_unchanged':True},ensure_ascii=False))

    def test_distinct_proposals_same_operation_preserve_first_actor_event_and_receipt(self):
        payload=self.source('return_supplier','EUR');first=self.preview(payload);second=self.preview(payload);before=Event.objects.count()
        results=self.pair([first,second]);self.assertIn(200,[r['status'] for r in results]);self.assertTrue(all(r['status'] in (200,409) for r in results),results)
        first_receipt=next(r['json'] for r in results if r['status']==200)
        for proposal in (first,second):self.assertEqual(self.confirm(proposal).json(),first_receipt)
        self.assertEqual(Event.objects.count(),before+1);self.assertEqual(DOCUMENT_MODELS['return_supplier'].objects.count(),1)

    def test_distinct_operations_compete_for_all_six_source_budgets(self):
        for action in ACTIONS:
            with self.subTest(action=action):
                payload=self.source(action,'EUR');other={**payload,'operation_id':str(uuid4()),'code':'B03-OTHER-'+uuid4().hex[:12]};ids=[self.preview(payload),self.preview(other)]
                before=Event.objects.count();results=self.pair(ids);self.assertEqual(sorted(r['status'] for r in results),[200,409],results);self.assertEqual(Event.objects.count(),before+1)
                loser=next(i for i,r in enumerate(results) if r['status']==409);denied=self.post('/api/erp/preview/',[payload,other][loser]);self.assertEqual(denied.status_code,422,denied.content)
                self.assertEqual(Event.objects.count(),before+1)

    def test_cancellation_and_old_receiving_serialize_the_same_remaining_quantity(self):
        po,lot,source=self.supply(quantity='2.000',ordered='3.000');cancel=self.command('cancel_remaining',purchase_id=po.pk,quantity='1.000')
        receive={'action':'erp_receive','purchase_id':po.pk,'quantity':'1.000','code':'B03-CROSS-RECEIVE','location_id':self.location.pk}
        results=self.pair([self.preview(cancel),self.preview(receive)]);self.assertEqual(sorted(r['status'] for r in results),[200,409],results)
        po.refresh_from_db();self.assertEqual(po.quantity,D(3));self.assertEqual(purchase_open(po),D(0));self.assertIn(po.received,(D(2),D(3)))
        loser=next(i for i,r in enumerate(results) if r['status']==409);self.assertEqual(self.post('/api/erp/preview/',[cancel,receive][loser]).status_code,422)

    def test_credit_and_old_payment_serialize_without_negative_receivable_or_cash_rewrite(self):
        credit=self.source('credit_invoice','EUR');payment={'action':'erp_payment','invoice_id':credit['invoice_id'],'amount':'20.00','reference':'B03-CROSS-PAY'}
        results=self.pair([self.preview(credit),self.preview(payment)]);self.assertEqual(sorted(r['status'] for r in results),[200,409],results)
        inv=Invoice.objects.get(pk=credit['invoice_id']);settlement=invoice_settlement(inv);self.assertEqual(settlement['receivable'],D(0));self.assertEqual(inv.amount,D(20));self.assertEqual(inv.paid,D(20) if results[1]['status']==200 else D(0))
        self.assertEqual(settlement['customer_credit'],D(0))

    def test_corrections_serialize_with_legacy_reserve_ship_and_transfer(self):
        for case in ('cancel_ship','cancel_reserve','supplier_transfer','supplier_reserve'):
            with self.subTest(case=case):
                if case.startswith('cancel'):
                    order,line,lot,source=self.sale(shipped='1.000',quantity='3.000')
                    if case=='cancel_ship':self.act('reserve',lot_id=lot.pk,line_id=line.pk,quantity='2.000')
                    correction=self.command('cancel_remaining',line_id=line.pk,quantity='2.000')
                    other={'action':'erp_ship' if case=='cancel_ship' else 'erp_reserve','lot_id':lot.pk,'line_id':line.pk,'quantity':'2.000'}
                    if case=='cancel_ship':other['reference']='B03-SHIP-CONTEND'
                else:
                    po,lot,source=self.supply(quantity='4.000',ordered='4.000');self.act('quality',lot_id=lot.pk,result='approved',inspector_id=self.owner.pk,note='Synthetic approved source')
                    correction=self.command('return_supplier',receipt_id=source.pk,quantity='4.000')
                    if case=='supplier_transfer':
                        from erp.models import Location
                        location=Location.objects.create(code='B03-OTHER-WH',name='Synthetic transfer target')
                        other={'action':'erp_transfer','lot_id':lot.pk,'quantity':'4.000','location_id':location.pk,'code':'B03-CONTEND-TRANSFER','reason':'Synthetic physical transfer'}
                    else:
                        order,line,otherlot,shipment=self.sale(shipped='1.000',quantity='5.000');other={'action':'erp_reserve','lot_id':lot.pk,'line_id':line.pk,'quantity':'4.000'}
                before=Event.objects.count();results=self.pair([self.preview(correction),self.preview(other)]);self.assertEqual(sorted(r['status'] for r in results),[200,409],results);self.assertEqual(Event.objects.count(),before+1)
                from erp.models import Reservation
                from erp.balances import sales_open
                lot.refresh_from_db();self.assertGreaterEqual(lot.quantity,D(0));held=sum(Reservation.objects.filter(lot=lot).values_list('quantity',flat=True),D(0));self.assertLessEqual(held,lot.quantity)
                if case.startswith('cancel'):
                    line.refresh_from_db();self.assertLessEqual(sum(Reservation.objects.filter(line=line).values_list('quantity',flat=True),D(0)),sales_open(line))
                if case!='cancel_reserve':
                    loser=next(i for i,r in enumerate(results) if r['status']==409);self.assertEqual(self.post('/api/erp/preview/',[correction,other][loser]).status_code,422)

for _action in ACTIONS:
    def factory(action):
        def test(self):self.same_proposal(action)
        test.__name__='test_http_pair_'+action;return test
    setattr(ERPCorrectionConcurrencyTests,'test_http_pair_'+_action,factory(_action))
