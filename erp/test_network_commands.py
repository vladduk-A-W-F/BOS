"""NETWORK-DOMAIN: isolated synthetic HTTP regressions; no historical data."""
from decimal import Decimal as D
from uuid import uuid4
from django.test import TestCase, Client, override_settings
from django.db import transaction
from scripts.check_support import login_test_client
from erp.test_corrections import CorrectionFixture
from erp.models import Location, Lot, StockTransfer, PaymentRetention, Event, Movement, SalesOrder, Purchase
from branches.models import Branch
from erp.balances import invoice_settlement
from erp.service import dispatch, fingerprint
from operations.models import Invoice
from operations import projections
from boss_project.policy import Policy


@override_settings(BOS_DATA_MODE='working',DEBUG=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class NetworkCommandTests(CorrectionFixture,TestCase):
    def setUp(self):
        super().setUp()
        self.branch=Branch.objects.create(code='N-KYI',name='Synthetic Kyiv',lat=50.45,lng=30.52)
        self.destination=Location.objects.create(code='N-DEST',name='Synthetic Lviv',branch=self.branch)

    def state(self):
        return super().state() | {m._meta.label:list(m.objects.order_by('pk').values()) for m in (StockTransfer,PaymentRetention,Location,Invoice)}

    def stock(self,quantity='10.000'):
        out=self.act('opening',code='N-LOT-'+uuid4().hex[:8],item_id=self.f.item.pk,location_id=self.location.pk,
            quantity=quantity,unit_cost='3.33',currency='UAH',revision='A',reason='Synthetic stock')
        self.act('quality',lot_id=out['lot_id'],result='approved',inspector_id=self.owner.pk,note='Physical verification')
        return Lot.objects.get(pk=out['lot_id'])

    def transfer(self,lot,**changes):
        return {'action':'erp_transfer_dispatch','lot_id':lot.pk,'quantity':'3.000','location_id':self.destination.pk,
            'code':'N-TR-'+uuid4().hex[:8],'reason':'Synthetic replenishment',**changes}

    def test_dispatch_receive_conserves_quantity_value_and_snapshots_with_proposal_replay(self):
        lot=self.stock();payload=self.transfer(lot)
        p=self.preview(payload);result=self.confirm(p).json();row=StockTransfer.objects.get(pk=result['transfer_id'])
        lot.refresh_from_db();self.assertEqual(lot.quantity,D(7));self.assertEqual(row.quantity,D(3))
        self.assertEqual(row.total_cost,D('9.99'));self.assertFalse(Lot.objects.filter(location=self.destination).exists())
        self.assertEqual(self.confirm(p).json(),result);self.assertEqual(StockTransfer.objects.count(),1)
        lot.revision='B';lot.unit_cost=D('99');lot.documents={'changed':999};lot.save()
        # Receipt must use the immutable dispatched identity, not a later source-lot edit.
        receipt=self.act('transfer_receive',transfer_id=row.pk,code='N-RECEIVED',reason='Physical arrival')
        received=Lot.objects.get(pk=receipt['lot_id']);row.refresh_from_db()
        self.assertEqual((received.quantity,received.unit_cost,received.revision,received.documents,received.quality),(D(3),D('3.33'),'A',{},'pending'))
        self.assertEqual(row.receipt_movement.cost,row.dispatch_movement.cost);self.assertEqual(row.status,'received')
        before=self.state();denied=self.post('/api/erp/preview/',{'action':'erp_transfer_receive','transfer_id':row.pk,'code':'N-AGAIN','reason':'again'})
        self.assertEqual(denied.status_code,422,denied.content);self.assertEqual(before,self.state())

    def test_unusable_reserved_or_same_point_transfers_reject_without_mutation(self):
        lot=self.stock();lot.quality='blocked';lot.save()
        for updates in ({},{'location_id':lot.location_id},{'quantity':'100.000'}):
            before=self.state();response=self.post('/api/erp/preview/',self.transfer(lot,**updates));self.assertEqual(response.status_code,422,response.content);self.assertEqual(self.state(),before)
        lot.quality='approved';lot.save()
        order,line,other,shipment=self.sale();self.act('reserve',lot_id=lot.pk,line_id=line.pk,quantity='8.000')
        response=self.post('/api/erp/preview/',self.transfer(lot));self.assertEqual(response.status_code,422,response.content)

    def test_money_hold_does_not_pay_and_blocks_manual_and_central_payment(self):
        order,line,lot,shipment=self.sale(shipped='10.000',quantity='10.000',price='10.00',currency='UAH')
        out=self.act('invoice',order_id=order.pk,code='N-INV',due_date='2026-10-01');invoice=Invoice.objects.get(pk=out['invoice_id'])
        result=self.act('hold_payment',invoice_id=invoice.pk,amount='30.00',code='N-HOLD',reason='Contractual guarantee')
        self.assertEqual(invoice_settlement(invoice)['receivable'],D(100));self.assertEqual(invoice_settlement(invoice)['collectible'],D(70));self.assertEqual(invoice.paid,D(0))
        response=self.post('/api/erp/preview/',{'action':'erp_payment','invoice_id':invoice.pk,'amount':'70.01','reference':'N-TOO-MUCH'})
        self.assertEqual(response.status_code,422,response.content)
        from erp.payments import post_payment
        with self.assertRaises(ValueError):post_payment(invoice.pk,'70.01','N-CENTRAL',role='ceo')
        self.act('payment',invoice_id=invoice.pk,amount='70.00',reference='N-COLLECTIBLE');invoice.refresh_from_db()
        self.assertEqual(invoice_settlement(invoice)['retained'],D(30));self.assertEqual(invoice_settlement(invoice)['collectible'],D(0))
        self.act('release_payment',retention_id=result['retention_id'],reason='Acceptance signed');invoice.refresh_from_db()
        self.assertEqual((invoice.paid,invoice_settlement(invoice)['receivable'],invoice_settlement(invoice)['collectible']),(D(70),D(30),D(30)))
        self.act('payment',invoice_id=invoice.pk,amount='30.00',reference='N-RELEASED');invoice.refresh_from_db();self.assertEqual(invoice_settlement(invoice)['receivable'],D(0))
        denied=self.post('/api/erp/preview/',{'action':'erp_release_payment','retention_id':result['retention_id'],'reason':'again'});self.assertEqual(denied.status_code,422)

    def test_credit_cannot_make_active_hold_exceed_ar(self):
        order,line,lot,shipment=self.sale(shipped='10.000',quantity='10.000',price='10.00')
        invoice=self.act('invoice',order_id=order.pk,code='N-CREDIT-INV',due_date='2026-10-01')['invoice_id']
        self.act('hold_payment',invoice_id=invoice,amount='90.00',code='N-CREDIT-HOLD',reason='Guarantee')
        payload=self.command('credit_invoice',invoice_id=invoice,basis='commercial',allocations=[{'invoice_line_index':0,'amount':'10.01'}],source_document_id=self.f.spec.pk)
        before=self.state();response=self.post('/api/erp/preview/',payload);self.assertEqual(response.status_code,422,response.content);self.assertEqual(self.state(),before)
        payload['allocations'][0]['amount']='10.00';self.correction(payload)
        self.assertEqual(invoice_settlement(Invoice.objects.get(pk=invoice))['collectible'],D(0))

    def test_retention_and_branch_changes_invalidate_previous_approval(self):
        lot=self.stock();p=self.preview(self.transfer(lot));self.branch.name='Changed';self.branch.save()
        denied=self.confirm(p);self.assertEqual(denied.status_code,409,denied.content);self.assertEqual(StockTransfer.objects.count(),0)
        order,line,lot,shipment=self.sale();invoice=self.act('invoice',order_id=order.pk,code='N-STALE-INV',due_date='2026-10-01')['invoice_id']
        p=self.preview({'action':'erp_payment','invoice_id':invoice,'amount':'24.68','reference':'N-STALE-PAY'})
        self.act('hold_payment',invoice_id=invoice,amount='1.00',code='N-STALE-HOLD',reason='Guarantee')
        denied=self.confirm(p);self.assertEqual(denied.status_code,409,denied.content)

    def test_metadata_and_old_payloads_compatible_and_coordinate_validation(self):
        self.assertIsNone(self.location.branch_id)
        self.act('location_update',location_id=self.location.pk,branch_id=self.branch.pk,lat='50.450100',lng='30.523400',address='Synthetic point',reason='Assign point')
        self.location.refresh_from_db();self.assertEqual(self.location.branch_id,self.branch.pk)
        self.act('location_update',location_id=self.location.pk,branch_id=None,lat=None,lng=None,reason='Clear mapping')
        self.location.refresh_from_db();self.assertIsNone(self.location.lat);self.assertIsNone(self.location.branch_id)
        for patch in ({'lat':'91','lng':'0'},{'lat':'NaN','lng':'0'},{'lat':'1'},{'lat':'1','lng':None},{'lat':'1.0000001','lng':'0'}):
            response=self.post('/api/erp/preview/',{'action':'erp_location_update','location_id':self.location.pk,'reason':'Invalid',**patch});self.assertEqual(response.status_code,422,response.content)
        po,lot,movement=self.supply()
        self.assertIsNone(po.destination_id);self.assertEqual(po.origin_country,'')
        denied=self.post('/api/erp/preview/',{'action':'erp_purchase_network','purchase_id':po.pk,'destination_id':self.destination.pk,'reason':'Rewrite history'})
        self.assertEqual(denied.status_code,422,denied.content)

    def test_explicit_destination_enforced_and_source_countries_stored(self):
        payload=self.payload(destination_id=self.destination.pk,origin_country='PL')
        proposal,receipt,po=self.buy(payload);self.assertEqual(po.destination_id,self.destination.pk);self.assertEqual(po.origin_country,'PL')
        response=self.post('/api/erp/preview/',{'action':'erp_receive','purchase_id':po.pk,'location_id':self.location.pk,'code':'N-WRONG-DEST','quantity':'1.000'})
        self.assertEqual(response.status_code,422,response.content)
        self.act('receive',purchase_id=po.pk,location_id=self.destination.pk,code='N-RIGHT-DEST',quantity='1.000')

    def test_manager_finance_denied_and_hidden_transfer_scope_enforced(self):
        manager=Client(enforce_csrf_checks=True,raise_request_exception=False);login_test_client(manager,'manager',capabilities=('view_document',))
        for payload in ({'action':'erp_hold_payment','invoice_id':999,'amount':'1.00','code':'SECRET','reason':'hold'},
                        {'action':'erp_release_payment','retention_id':999,'reason':'release'},
                        {'action':'erp_location_update','location_id':self.location.pk,'branch_id':self.branch.pk,'reason':'set'}):
            response=self.post('/api/erp/preview/',payload,manager);self.assertEqual(response.status_code,403,response.content)
        lot=self.stock();p=self.preview(self.transfer(lot));row=StockTransfer.objects.get(pk=self.confirm(p).json()['transfer_id'])
        self.f.spec.access_level='executive';self.f.spec.save()
        response=self.post('/api/erp/preview/',{'action':'erp_transfer_receive','transfer_id':row.pk,'code':'N-HIDDEN','reason':'receipt'},manager)
        self.assertIn(response.status_code,(403,404),response.content)

    def test_manager_transfer_receipt_does_not_expose_money(self):
        manager=Client(enforce_csrf_checks=True,raise_request_exception=False);login_test_client(manager,'manager',capabilities=('view_document',))
        lot=self.stock();p=self.preview(self.transfer(lot),manager);response=self.confirm(p,manager);self.assertEqual(response.status_code,200,response.content)
        result=response.json();self.assertNotIn('unit_cost',result);self.assertNotIn('total_cost',result);self.assertNotIn('settlement',result)

    def test_statement_preview_respects_hold_and_cumulative_allocations(self):
        # Exercise the statement planner through a minimal synthetic statement fixture.
        from types import SimpleNamespace
        from unittest.mock import patch
        from finance.statements import prepare_reconcile, StatementError
        invoice=Invoice.objects.create(code='N-STMT-INV',customer=self.f.supplier,amount=D(100),paid=D(0),currency='UAH',due_date='2026-10-01')
        PaymentRetention.objects.create(code='N-STMT-HOLD',invoice=invoice,amount=D(30),currency='UAH',reason='hold')
        line=SimpleNamespace(pk=uuid4(),first_import=SimpleNamespace(document=None),transaction=None,transaction_id=None,
            direction='in',amount=D(100),currency='UAH',booking_date='2026-09-12',invoice_reference=invoice.code)
        line.allocations=SimpleNamespace(values_list=lambda *a,**k: [])
        data={'line_id':str(line.pk),'reason':'Synthetic allocation','transaction':{'mode':'new_transaction','description':'Synthetic cash','category':'sales'},
            'matching':{'counterparty_id':invoice.customer_id},'allocations':[
                {'allocation_key':str(uuid4()),'invoice_id':invoice.pk,'amount':'40.00','currency':'UAH','invoice_match':'exact_reference','mode':'new_payment'},
                {'allocation_key':str(uuid4()),'invoice_id':invoice.pk,'amount':'30.01','currency':'UAH','invoice_match':'exact_reference','mode':'new_payment'}]}
        with patch('finance.statements.StatementLine.objects.select_related') as query,patch('finance.statements.original'),patch('finance.statements.matching_source',return_value={}):
            query.return_value.get.return_value=line
            with self.assertRaises(StatementError):prepare_reconcile(data,None)
