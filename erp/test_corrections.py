"""B03 real HTTP regressions; synthetic fresh verification DB only."""
from copy import deepcopy
from decimal import Decimal as D,localcontext,ROUND_DOWN
from uuid import uuid4
from django.apps import apps
from django.db import connection
from django.test import TestCase,override_settings
from erp.test_procurement_bridge import BridgeFixture
from erp.models import Lot,Movement,Reservation,SalesLine,SalesOrder,Purchase,InvoiceLink,Event
from operations.models import Invoice
from finance.models import Counterparty,Transaction,Salary


class CorrectionFixture(BridgeFixture):
    def act(self,action,**fields):
        p=self.preview({'action':'erp_'+action,**fields});r=self.confirm(p)
        self.assertEqual(r.status_code,200,r.content)
        return r.json()

    def command(self,action,**fields):
        return {'action':'erp_'+action,'operation_id':str(uuid4()),'code':'B03-'+uuid4().hex[:16],
            'reason':'Синтетично погоджено зміну джерельного зобов’язання','business_date':'2026-09-12',**fields}

    def correction(self,payload):
        p=self.preview(payload);response=self.confirm(p);self.assertEqual(response.status_code,200,response.content)
        return p,response.json()

    def supply(self,quantity='4.000',currency='EUR',unit_price='5.00',ordered='10.000'):
        po=self.act('purchase',code='B03-PO-'+uuid4().hex[:10],item_id=self.f.item.pk,supplier_id=self.f.supplier.pk,
            quantity=ordered,price=unit_price,extras='0.00',currency=currency,due_date='2026-10-01',revision='A',direct_reason='Синтетичне пряме замовлення B03')
        receipt=self.act('receive',purchase_id=po['purchase_id'],code='B03-RCV-'+uuid4().hex[:10],location_id=self.location.pk,quantity=quantity)
        lot=Lot.objects.get(pk=receipt['lot_id']);movement=Movement.objects.get(lot=lot,kind='receipt')
        return Purchase.objects.get(pk=po['purchase_id']),lot,movement

    def sale(self,shipped='2.000',currency='EUR',quantity='10.000',price='12.34'):
        customer=Counterparty.objects.create(name='B03 synthetic customer',type='customer')
        result=self.act('order',code='B03-SO-'+uuid4().hex[:10],customer_id=customer.pk,owner_id=self.owner.pk,due_date='2026-10-01',currency=currency,
            lines=[{'item_id':self.f.item.pk,'quantity':quantity,'price':price}])
        order=SalesOrder.objects.get(pk=result['order_id']);line=order.lines.get();self.act('confirm_order',order_id=order.pk)
        opening=self.act('opening',code='B03-STK-'+uuid4().hex[:10],item_id=self.f.item.pk,location_id=self.location.pk,quantity='20.000',unit_cost='5.00',currency=currency,revision='A',reason='Синтетичний початковий stock B03')
        lot=Lot.objects.get(pk=opening['lot_id']);self.act('quality',lot_id=lot.pk,result='approved',inspector_id=self.owner.pk,note='Перевірено фізично')
        self.act('reserve',lot_id=lot.pk,line_id=line.pk,quantity=shipped)
        self.act('ship',line_id=line.pk,lot_id=lot.pk,quantity=shipped,reference='B03-SHIP-'+uuid4().hex[:10])
        line.refresh_from_db();lot.refresh_from_db()
        return order,line,lot,Movement.objects.get(lot=lot,kind='shipment')

    def gross(self):
        return {model._meta.label:list(model.objects.order_by('pk').values()) for model in (Purchase,SalesLine,Invoice,InvoiceLink,Transaction,Salary)}


@override_settings(BOS_DATA_MODE='working',DEBUG=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CorrectionTests(CorrectionFixture,TestCase):
    def test_cancel_remaining_releases_newest_own_reserves_without_gross_or_stock_rewrite(self):
        order,line,lot,shipment=self.sale();old=self.act('reserve',lot_id=lot.pk,line_id=line.pk,quantity='3.000');new=self.act('reserve',lot_id=lot.pk,line_id=line.pk,quantity='4.000')
        gross=self.gross();stock=list(Lot.objects.values());movements=list(Movement.objects.values());event_count=Event.objects.count()
        payload=self.command('cancel_remaining',line_id=line.pk,quantity='5.000');proposal,result=self.correction(payload)
        self.assertEqual(result['effective_open'],'3.000');self.assertEqual(result['cancelled_quantity'],'5.000')
        self.assertEqual(Reservation.objects.get(pk=new['reservation_id']).quantity,D('0'));self.assertEqual(Reservation.objects.get(pk=old['reservation_id']).quantity,D('3'))
        self.assertEqual(self.gross(),gross);self.assertEqual(list(Lot.objects.values()),stock);self.assertEqual(list(Movement.objects.values()),movements)
        self.assertEqual(Event.objects.count(),event_count+1)
        release=apps.get_model('erp','CancellationRelease').objects.get();self.assertEqual((release.reservation_id,release.quantity,release.before_quantity,release.after_quantity),(new['reservation_id'],D('4'),D('4'),D('0')))
        self.assertEqual(self.confirm(proposal).json(),result)
        _,replayed=self.correction(payload);self.assertEqual(replayed,result);self.assertEqual(Event.objects.count(),event_count+1)

    def test_supplier_return_keeps_receipt_gross_pending_claim_and_no_cash(self):
        po,lot,receipt=self.supply();gross=self.gross();source=list(Movement.objects.values());event_count=Event.objects.count()
        _,result=self.correction(self.command('return_supplier',receipt_id=receipt.pk,quantity='1.000'))
        lot.refresh_from_db();self.assertEqual(lot.quantity,D('3'));self.assertEqual(lot.quality,'pending');self.assertEqual(self.gross(),gross)
        returned=apps.get_model('erp','GoodsReturn').objects.get(pk=result['goods_return_id'])
        self.assertEqual(returned.source_id,receipt.pk);self.assertEqual(returned.allocated_cost,D('5.00'));self.assertEqual(returned.result.quantity,D('-1'))
        claim=apps.get_model('erp','SupplierClaim').objects.get(pk=result['claim_id']);self.assertEqual(claim.record_kind,'pending');self.assertIsNone(claim.agreed_amount)
        self.assertEqual(list(Movement.objects.filter(pk__in=[r['id'] for r in source]).values()),source);self.assertEqual(Event.objects.count(),event_count+1)

    def test_exact_customer_return_creates_blocked_lot_and_preserves_legacy_aggregate_cap(self):
        order,line,lot,shipment=self.sale();gross=self.gross()
        _,result=self.correction(self.command('return_from_shipment',shipment_id=shipment.pk,quantity='1.000',location_id=self.location.pk))
        returned=Lot.objects.get(pk=result['lot_id']);self.assertEqual((returned.quantity,returned.quality),(D('1'),'blocked'));self.assertEqual(self.gross(),gross)
        movement=Movement.objects.get(pk=result['movement_id']);self.assertEqual((movement.kind,movement.reference,movement.line_id),('return',lot.code,line.pk))
        legacy=self.act('return',line_id=line.pk,lot_id=lot.pk,quantity='1.000',code='B03-LEGACY',location_id=self.location.pk,reason='Остання фізично відвантажена одиниця')
        self.assertEqual(set(legacy)-{'state','erp_event_id','impact'},{'lot_id','quality','note'})
        denied=self.post('/api/erp/preview/',self.command('return_from_shipment',shipment_id=shipment.pk,quantity='0.001',location_id=self.location.pk))
        self.assertEqual(denied.status_code,422,denied.content);self.assertEqual(self.gross(),gross)

    def test_credit_and_full_reversal_share_settlement_without_rewriting_invoice_or_cash(self):
        order,line,lot,shipment=self.sale(shipped='10.000');created=self.act('invoice',order_id=order.pk,code='B03-INVOICE',due_date='2026-10-01');invoice_id=created['invoice_id']
        self.act('payment',invoice_id=invoice_id,amount='100.00',reference='B03-EXISTING-PAYMENT');gross=self.gross()
        payload=self.command('credit_invoice',invoice_id=invoice_id,basis='commercial',allocations=[{'invoice_line_index':0,'amount':'24.68'}],source_document_id=self.f.spec.pk)
        _,credit=self.correction(payload);self.assertEqual(credit['settlement']['receivable'],'0.00');self.assertEqual(credit['settlement']['customer_credit'],'1.28');self.assertEqual(self.gross(),gross)
        next_step=self.http.get('/api/erp/orders/'+str(order.pk)+'/next/').json();self.assertIsNone(next_step['payload']);self.assertIn('на користь клієнта',next_step['title'])
        denied=self.post('/api/erp/preview/',{'action':'erp_payment','invoice_id':invoice_id,'amount':'0.01','reference':'B03-FORBIDDEN-OVERPAY'});self.assertEqual(denied.status_code,422,denied.content)
        _,reversal=self.correction(self.command('reverse_credit',credit_id=credit['invoice_adjustment_id']))
        self.assertEqual(reversal['settlement']['receivable'],'23.40');self.assertEqual(reversal['settlement']['customer_credit'],'0.00');self.assertEqual(self.gross(),gross)

    def test_historical_return_source_scope_controls_rows_claims_events_replay_and_outcome(self):
        from django.test import Client
        from scripts.check_support import login_test_client
        source_doc=self.document('B03-HISTORICAL-SOURCE');replacement=self.document('B03-REPLACEMENT')
        po,lot,receipt=self.supply();self.act('attach',lot_id=lot.pk,kind='certificate',document_id=source_doc.pk)
        payload=self.command('return_supplier',receipt_id=receipt.pk,quantity='1.000');proposal,result=self.correction(payload)
        manager=Client(enforce_csrf_checks=True,raise_request_exception=False);login_test_client(manager,'manager',capabilities=('view_document',))
        url='/api/erp/corrections/outcome/';query={'action':payload['action'],'operation_id':payload['operation_id']}
        self.assertEqual(manager.get(url,query).status_code,200)
        self.act('attach',lot_id=lot.pk,kind='certificate',document_id=replacement.pk)
        source_doc.access_level='ceo';source_doc.save(update_fields=['access_level'])
        before=self.state();snapshot=manager.get('/api/erp/snapshot/').json()
        self.assertIn(lot.pk,[r['id'] for r in snapshot['lots']])
        self.assertNotIn(result['goods_return_id'],[r['id'] for r in snapshot['goods_returns']])
        self.assertNotIn(result['claim_id'],[r['id'] for r in snapshot['supplier_claims']])
        self.assertNotIn(result['erp_event_id'],[r['id'] for r in snapshot['events']])
        unknown=manager.get(url,query);self.assertEqual(unknown.status_code,404,unknown.content)
        self.assertEqual(unknown.json(),{'state':'unknown','receipt':None})
        denied=self.post('/api/erp/preview/',payload,manager);self.assertIn(denied.status_code,(403,404),denied.content)
        self.assertEqual(self.state(),before);self.assertEqual(self.http.get(url,query).status_code,200)

    def test_supplier_return_preview_keeps_existing_source_lot(self):
        po,lot,receipt=self.supply();payload=self.command('return_supplier',receipt_id=receipt.pk,quantity='1.000')
        before=self.state();response=self.post('/api/erp/preview/',payload);self.assertEqual(response.status_code,200,response.content)
        effect=response.json()['effect'];self.assertEqual(effect['lot_id'],lot.pk);self.assertIsNone(effect['goods_return_id']);self.assertIsNone(effect['movement_id']);self.assertEqual(self.state(),before)

    def test_actual_http_correction_under_low_decimal_context_is_exact(self):
        po,lot,receipt=self.supply(quantity='100000.000',ordered='100000.000',unit_price='12.34')
        self.sale(shipped='1.000',quantity='1.000',price='1234567.89')
        original_costs=self.http.get('/api/erp/snapshot/').json()['costs']
        payload=self.command('return_supplier',receipt_id=receipt.pk,quantity='99999.999')
        with localcontext() as context:
            context.prec=6;context.rounding=ROUND_DOWN
            proposal,result=self.correction(payload)
            snapshot=self.http.get('/api/erp/snapshot/');self.assertEqual(snapshot.status_code,200,snapshot.content)
            self.assertEqual(snapshot.json()['costs'],original_costs)
            self.assertEqual((context.prec,context.rounding),(6,ROUND_DOWN))
        self.assertEqual(result['allocated_cost'],'1233999.99');lot.refresh_from_db();self.assertEqual(lot.quantity,D('.001'))

    def test_cancelled_component_purchase_does_not_delay_bom_plan(self):
        from erp.models import Item
        from erp.queries import plan_line
        component=self.f.item
        finished=Item.objects.create(code='B03-FG',name='Synthetic assembly',unit='шт.',kind='product',method='make',revision='A',currency='EUR',bom=[{'item_id':component.pk,'quantity':'1.000'}])
        customer=Counterparty.objects.create(name='Synthetic BOM customer',type='customer')
        order=SalesOrder.objects.create(code='B03-BOM-SO',customer=customer,owner=self.owner,due_date='2026-10-01',currency='EUR',status='confirmed')
        line=SalesLine.objects.create(order=order,item=finished,revision='A',quantity='1.000',price='1.00')
        po=self.act('purchase',code='B03-COMP-PO',item_id=component.pk,supplier_id=self.f.supplier.pk,quantity='1.000',price='1.00',extras='0.00',currency='EUR',due_date='2027-01-01',revision='A',direct_reason='Synthetic component source')
        self.correction(self.command('cancel_remaining',purchase_id=po['purchase_id'],quantity='1.000'))
        from datetime import date,timedelta
        line.refresh_from_db();plan=plan_line(line);self.assertEqual(plan['estimated_date'],str(date(2026,9,12)+timedelta(days=component.lead_days)))
        self.assertEqual(D(plan['materials'][0]['expected']),D(0))

    def test_source_cost_is_conserved_across_three_split_returns_in_every_currency(self):
        for currency in ('EUR','USD','UAH'):
            with self.subTest(currency=currency):
                po,lot,source=self.supply(quantity='0.003',ordered='0.003',unit_price='3.33',currency=currency)
                self.assertEqual(source.cost,D('.01'));values=[]
                for unused in range(3):
                    _,receipt=self.correction(self.command('return_supplier',receipt_id=source.pk,quantity='0.001'));values.append(receipt['allocated_cost'])
                self.assertEqual(values,['0.00','0.01','0.00']);lot.refresh_from_db();self.assertEqual(lot.quantity,D(0));po.refresh_from_db();self.assertEqual(po.received,D('.003'))
                self.assertEqual(sum(apps.get_model('erp','GoodsReturn').objects.filter(source=source).values_list('allocated_cost',flat=True)),source.cost)
                denied=self.post('/api/erp/preview/',self.command('return_supplier',receipt_id=source.pk,quantity='0.001'));self.assertEqual(denied.status_code,422)

    def test_zero_supplier_confirmation_is_distinct_from_pending_and_has_verified_source(self):
        Claim=apps.get_model('erp','SupplierClaim');po,lot,source=self.supply()
        _,returned=self.correction(self.command('return_supplier',receipt_id=source.pk,quantity='1.000'))
        pending=Claim.objects.get(pk=returned['claim_id']);self.assertIsNone(pending.agreed_amount)
        payload=self.command('confirm_supplier_claim',claim_id=pending.pk,amount='0.00',currency='EUR',source_document_id=self.f.spec.pk)
        proposal,result=self.correction(payload);confirmation=Claim.objects.get(pk=result['supplier_claim_id']);self.assertEqual(confirmation.agreed_amount,D('0'));self.assertEqual(confirmation.source_snapshot['checksum'],self.f.spec.checksum)
        self.assertEqual(confirmation.parent_id,pending.pk);pending.refresh_from_db();self.assertIsNone(pending.agreed_amount)
        self.assertEqual(self.confirm(proposal).json(),result)
        denied=self.post('/api/erp/preview/',self.command('confirm_supplier_claim',claim_id=pending.pk,amount='1.00',currency='EUR',source_document_id=self.f.spec.pk));self.assertEqual(denied.status_code,422)
        from django.test import Client
        from scripts.check_support import login_test_client
        manager=Client(enforce_csrf_checks=True,raise_request_exception=False);login_test_client(manager,'manager',capabilities=('view_document',))
        snapshot=manager.get('/api/erp/snapshot/').json();row=next(r for r in snapshot['supplier_claims'] if r['id']==confirmation.pk)
        self.assertNotIn('agreed_amount',row);self.assertNotIn('source_snapshot',row);self.assertNotIn('source_document_id',row);self.assertNotIn('reason',row)
        self.assertNotIn(confirmation.event_id,[r['id'] for r in snapshot['correction_events']]);self.assertEqual(manager.get('/api/erp/corrections/outcome/',{'action':payload['action'],'operation_id':payload['operation_id']}).status_code,403)

    def test_cent_invoice_basis_zero_and_nonzero_budgets_return_then_reversal(self):
        from erp.models import Item
        from erp.corrections import invoice_basis
        order,line,lot,source=self.sale(shipped='0.500',quantity='0.500',price='0.01')
        second=SalesLine.objects.create(order=order,item=self.f.item,revision='A',quantity=D('.500'),price=D('.01'))
        self.act('reserve',lot_id=lot.pk,line_id=second.pk,quantity='0.500');self.act('ship',line_id=second.pk,lot_id=lot.pk,quantity='0.500',reference='SECOND-CENT-SHIP')
        other=Movement.objects.get(kind='shipment',line=second)
        inv=self.act('invoice',order_id=order.pk,code='B03-CENT-INVOICE',due_date='2026-10-01');invoice=Invoice.objects.get(pk=inv['invoice_id'])
        self.assertEqual(invoice.amount,D('.01'));basis=invoice_basis(invoice);self.assertEqual([r['budget'] for r in basis['lines']],['0.00','0.01'])
        sources=[source,other];credits=[]
        for index,src in enumerate(sources):
            _,ret=self.correction(self.command('return_from_shipment',shipment_id=src.pk,quantity='0.500',location_id=self.location.pk))
            _,credit=self.correction(self.command('credit_invoice',invoice_id=invoice.pk,basis='return',allocations=[{'return_id':ret['goods_return_id'],'invoice_line_index':index,'quantity':'0.500'}]));credits.append(credit)
        self.assertEqual([r['total'] for r in credits],['0.00','0.01']);self.assertEqual(credits[-1]['settlement']['net_amount'],'0.00')
        self.correction(self.command('reverse_credit',credit_id=credits[0]['invoice_adjustment_id']))
        zero=apps.get_model('erp','InvoiceAdjustment').objects.get(pk=credits[0]['invoice_adjustment_id']);reversal=zero.reversal
        self.assertEqual(list(zero.lines.values_list('invoice_line_index','quantity','amount')),list(reversal.lines.values_list('invoice_line_index','quantity','amount')))

    def test_commercial_and_physical_credit_share_money_cap_without_silent_clamp(self):
        order,line,lot,source=self.sale(shipped='2.000',quantity='2.000',price='10.00');inv=self.act('invoice',order_id=order.pk,code='B03-CAP-INVOICE',due_date='2026-10-01')
        _,ret=self.correction(self.command('return_from_shipment',shipment_id=source.pk,quantity='2.000',location_id=self.location.pk))
        _,credit=self.correction(self.command('credit_invoice',invoice_id=inv['invoice_id'],basis='commercial',source_document_id=self.f.spec.pk,allocations=[{'invoice_line_index':0,'amount':'1.00'}]))
        payload=self.command('credit_invoice',invoice_id=inv['invoice_id'],basis='return',allocations=[{'return_id':ret['goods_return_id'],'invoice_line_index':0,'quantity':'2.000'}])
        before=self.state();denied=self.post('/api/erp/preview/',payload);self.assertEqual(denied.status_code,422);self.assertEqual(self.state(),before)
        self.correction(self.command('reverse_credit',credit_id=credit['invoice_adjustment_id']));_,physical=self.correction(payload);self.assertEqual(physical['total'],'20.00')
        duplicate=self.post('/api/erp/preview/',self.command('credit_invoice',invoice_id=inv['invoice_id'],basis='return',allocations=[{'return_id':ret['goods_return_id'],'invoice_line_index':0,'quantity':'0.001'}]));self.assertEqual(duplicate.status_code,422)

    def test_imported_po_uses_only_current_quantity_and_keeps_import_receipt(self):
        from erp.test_initial_import import InitialImportFixture
        from erp.models import ImportBatch
        batch=InitialImportFixture.batch(self,suffix='B03');preview=self.post('/api/erp/import/preview/',batch);self.assertEqual(preview.status_code,200,preview.content)
        proposal=preview.json()['proposal']['id'];imported=self.confirm(proposal);self.assertEqual(imported.status_code,200,imported.content)
        po=Purchase.objects.get(code='B02-B03-PO');history=deepcopy(po.approval_snapshot);ledger=deepcopy(list(ImportBatch.objects.values()))
        received=self.act('receive',purchase_id=po.pk,code='B03-IMPORTED-RECEIVE',location_id=self.location.pk,quantity='2.000');source=Movement.objects.get(lot_id=received['lot_id'],kind='receipt')
        _,cancelled=self.correction(self.command('cancel_remaining',purchase_id=po.pk,quantity='1.000'));self.assertEqual(cancelled['effective_open'],'2.000')
        self.correction(self.command('return_supplier',receipt_id=source.pk,quantity='1.000'));po.refresh_from_db();self.assertEqual((po.quantity,po.received),(D(5),D(2)));self.assertEqual(po.approval_snapshot,history)
        self.assertEqual(self.confirm(proposal).json(),imported.json());self.assertEqual(list(ImportBatch.objects.values()),ledger)
        denied=self.post('/api/erp/preview/',self.command('cancel_remaining',purchase_id=po.pk,quantity='2.001'));self.assertEqual(denied.status_code,422)

    def test_late_sql_failure_rolls_back_return_claim_event_and_same_intent_can_retry(self):
        from operations.models import ActionProposal
        po,lot,source=self.supply();payload=self.command('return_supplier',receipt_id=source.pk,quantity='1.000');proposal=self.preview(payload);before=self.state()
        with connection.cursor() as cursor:cursor.execute("CREATE TRIGGER b03_claim_failure BEFORE INSERT ON erp_supplierclaim BEGIN SELECT RAISE(ABORT,'synthetic B03 late failure'); END")
        try:
            failed=self.confirm(proposal);self.assertEqual(failed.status_code,409,failed.content);self.assertEqual(self.state(),before);self.assertFalse(apps.get_model('erp','GoodsReturn').objects.exists());self.assertIsNone(ActionProposal.objects.get(pk=proposal).receipt)
        finally:
            with connection.cursor() as cursor:cursor.execute('DROP TRIGGER b03_claim_failure')
        done=self.confirm(proposal);self.assertEqual(done.status_code,200,done.content);self.assertEqual(apps.get_model('erp','GoodsReturn').objects.count(),1)

    def test_expired_proposal_new_login_and_old_history_recover_only_original_readonly_result(self):
        from django.test import Client
        from django.utils import timezone
        from datetime import timedelta
        from scripts.check_support import login_test_client
        from operations.models import ActionProposal
        po,lot,source=self.supply();payload=self.command('return_supplier',receipt_id=source.pk,quantity='1.000');proposal,result=self.correction(payload)
        Event.objects.bulk_create([Event(action='b03.synthetic.history',payload={},result={},role='ceo') for _ in range(310)])
        Movement.objects.bulk_create([Movement(lot=lot,kind='adjust',quantity=D(0),cost=D(0),reference='B03-HISTORY-'+str(n)) for n in range(310)])
        ActionProposal.objects.filter(pk=proposal).update(expires_at=timezone.now()-timedelta(days=1));old=self.state()
        manager=Client(enforce_csrf_checks=True,raise_request_exception=False);login_test_client(manager,'manager',capabilities=('view_document',))
        response=manager.get('/api/erp/corrections/outcome/',{'action':payload['action'],'operation_id':payload['operation_id']});self.assertEqual(response.status_code,200,response.content)
        returned=response.json()['receipt'];self.assertEqual(returned['erp_event_id'],result['erp_event_id']);self.assertNotIn('allocated_cost',returned);self.assertNotIn('actor_id',returned)
        snapshot=manager.get('/api/erp/snapshot/').json();self.assertIn(result['movement_id'],[r['id'] for r in snapshot['source_movements']]);self.assertIn(result['erp_event_id'],[r['id'] for r in snapshot['correction_events']]);self.assertNotIn(result['erp_event_id'],[r['id'] for r in snapshot['events']])
        self.assertEqual(self.state(),old);_,same=self.correction(payload);self.assertEqual(same,result)
        conflict=self.post('/api/erp/preview/',{**payload,'quantity':'0.001'});self.assertEqual(conflict.status_code,409,conflict.content)

    def test_recent_correction_event_has_one_row_per_visible_event_id(self):
        from django.test import Client
        from scripts.check_support import login_test_client
        po,lot,source=self.supply();self.correction(self.command('return_supplier',receipt_id=source.pk,quantity='1.000'))
        manager=Client(enforce_csrf_checks=True,raise_request_exception=False);login_test_client(manager,'manager',capabilities=('view_document',))
        data=manager.get('/api/erp/snapshot/').json();ids=[r['id'] for r in data['events']];self.assertEqual(len(ids),len(set(ids)))

    def test_manager_next_step_does_not_disclose_financial_return_resolution(self):
        from django.test import Client
        from scripts.check_support import login_test_client
        order,line,lot,source=self.sale(shipped='1.000',quantity='1.000',price='10.00');inv=self.act('invoice',order_id=order.pk,code='B03-PRIVATE-CREDIT',due_date='2026-10-01')
        _,ret=self.correction(self.command('return_from_shipment',shipment_id=source.pk,quantity='1.000',location_id=self.location.pk))
        manager=Client(enforce_csrf_checks=True,raise_request_exception=False);login_test_client(manager,'manager',capabilities=('view_document',))
        url='/api/erp/orders/'+str(order.pk)+'/next/';before=manager.get(url);self.assertEqual(before.status_code,200,before.content)
        self.correction(self.command('credit_invoice',invoice_id=inv['invoice_id'],basis='return',allocations=[{'return_id':ret['goods_return_id'],'invoice_line_index':0,'quantity':'1.000'}]))
        after=manager.get(url);self.assertEqual(after.status_code,200);self.assertEqual(before.json(),after.json())

    def test_source_return_refuses_reserve_and_extra_origin_and_claim_bad_bytes(self):
        po,lot,source=self.supply();order,line,other,ship=self.sale(shipped='1.000')
        self.act('quality',lot_id=lot.pk,result='approved',inspector_id=self.owner.pk,note='Synthetic quality approval')
        self.act('reserve',lot_id=lot.pk,line_id=line.pk,quantity='4.000')
        payload=self.command('return_supplier',receipt_id=source.pk,quantity='0.001');before=self.state();self.assertEqual(self.post('/api/erp/preview/',payload).status_code,422);self.assertEqual(self.state(),before)
        reservation=Reservation.objects.get(lot=lot,line=line);self.act('release',reservation_id=reservation.pk,quantity='4.000')
        self.act('adjust',lot_id=lot.pk,delta='1.000',reason='Synthetic additional positive origin')
        self.assertEqual(self.post('/api/erp/preview/',payload).status_code,422)
        po2,lot2,source2=self.supply();_,ret=self.correction(self.command('return_supplier',receipt_id=source2.pk,quantity='1.000'))
        from operations.models import Document
        Document.objects.filter(pk=self.f.spec.pk).update(content=b'B03 corrupted actual bytes')
        bad=self.command('confirm_supplier_claim',claim_id=ret['claim_id'],amount='1.00',currency='EUR',source_document_id=self.f.spec.pk)
        self.assertEqual(self.post('/api/erp/preview/',bad).status_code,422)

    def test_cancelled_quote_purchase_releases_request_allocation_but_return_does_not(self):
        _,_,po=self.buy(self.payload());received=self.act('receive',purchase_id=po.pk,quantity='4.000',code='B03-QUOTE-RCV',location_id=self.location.pk)
        self.correction(self.command('cancel_remaining',purchase_id=po.pk,quantity='6.000'))
        _,_,replacement=self.buy(self.payload(quantity='6.000'));self.assertEqual(replacement.quantity,D(6))
        source=Movement.objects.get(lot_id=received['lot_id'],kind='receipt');self.correction(self.command('return_supplier',receipt_id=source.pk,quantity='1.000'))
        denied=self.post('/api/erp/preview/',self.payload(quantity='0.001'));self.assertEqual(denied.status_code,422)
        po.refresh_from_db();self.assertEqual((po.quantity,po.received),(D(10),D(4)))

    def test_one_physical_return_cannot_credit_two_invoices_of_the_same_sales_line(self):
        order,line,lot,source=self.sale(shipped='1.000',quantity='2.000',price='10.00');first=self.act('invoice',order_id=order.pk,code='B03-MULTI-1',due_date='2026-10-01')
        self.act('reserve',lot_id=lot.pk,line_id=line.pk,quantity='1.000');self.act('ship',line_id=line.pk,lot_id=lot.pk,quantity='1.000',reference='B03-MULTI-SHIP')
        second=self.act('invoice',order_id=order.pk,code='B03-MULTI-2',due_date='2026-10-01')
        _,returned=self.correction(self.command('return_from_shipment',shipment_id=source.pk,quantity='1.000',location_id=self.location.pk))
        allocation={'return_id':returned['goods_return_id'],'invoice_line_index':0,'quantity':'1.000'}
        self.correction(self.command('credit_invoice',invoice_id=first['invoice_id'],basis='return',allocations=[allocation]))
        before=self.state();denied=self.post('/api/erp/preview/',self.command('credit_invoice',invoice_id=second['invoice_id'],basis='return',allocations=[allocation]));self.assertEqual(denied.status_code,422);self.assertEqual(self.state(),before)
