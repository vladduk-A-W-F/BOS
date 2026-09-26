"""B01 real HTTP/ORM regression contract, only owned synthetic databases."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
from decimal import Decimal as D
import hashlib
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace
from uuid import uuid4

from django.conf import settings
from django.db import connection, connections
from django.db.models import Sum
from django.db.models.deletion import ProtectedError
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext

from employees.models import Employee
from finance.models import Counterparty
from operations.models import ActionProposal, Configuration, Document, ProcurementRequest, SupplierQuote
from operations.private_storage import private_document_storage
from scripts.check_support import login_test_client
from erp import service
from erp.models import Event, Item, Location, Lot, Movement, Purchase


class BridgeFixture:
    def setUp(self):
        self.assertEqual(os.environ.get('DJANGO_SETTINGS_MODULE'), 'verification_settings')
        if connection.vendor == 'sqlite':
            self.assertTrue(Path(str(connection.settings_dict['NAME'])).name.startswith('check_'))
        self.http = Client(enforce_csrf_checks=True, raise_request_exception=False)
        self.user = login_test_client(self.http, 'ceo', capabilities=('view_document', 'export_workspace'))
        self.owner = Employee.objects.create(full_name='B01 синтетичний закупівельник')
        self.location = Location.objects.create(code='B01-W', name='B01 синтетичний склад')
        Configuration.objects.create(key='dataset', value={'as_of':'2026-09-12'})
        Configuration.objects.get_or_create(key='erp_write', defaults={'value':{'revision':0}})
        self.f = self.fixture('BASE')

    def document(self, code):
        raw = ('B01 synthetic source ' + code).encode()
        return Document.objects.create(code=code, revision='A', title=code, content=raw,
            text=raw.decode(), checksum=hashlib.sha256(raw).hexdigest(), status='approved', access_level='operational')

    def fixture(self, suffix, currency='EUR'):
        f = SimpleNamespace()
        f.spec = self.document('B01-SPEC-'+suffix)
        f.source = self.document('B01-QUOTE-'+suffix)
        f.supplier = Counterparty.objects.create(name='B01 постачальник '+suffix, type='supplier')
        f.item = Item.objects.create(code='B01-I-'+suffix, name='B01 номенклатура', unit='шт.',
            revision='A', document=f.spec, currency=currency)
        f.request = ProcurementRequest.objects.create(code='B01-R-'+suffix, part=f.item.code,
            revision='A', quantity=10, unit='шт.', currency=currency, required_by='2026-10-31',
            owner=self.owner, document=f.spec)
        f.terms = {'unit_price':'12.34','setup':'2.00','shipping':'3.00','tooling':'0.00',
            'special_processes':'0.00','currency':currency,'revision':'A','lead_weeks':12,
            'valid_until':'2026-10-31','moq':1,'coating_included':True,'material_certificate':True}
        f.quote = SupplierQuote.objects.create(code='B01-Q-'+suffix, request=f.request,
            supplier=f.supplier, document=f.source, terms=f.terms)
        return f

    def payload(self, f=None, **changes):
        f = f or self.f
        return {'action':'erp_purchase','code':'B01-PO-'+uuid4().hex[:12], 'item_id':f.item.pk,
            'supplier_id':f.supplier.pk,'quantity':'10','price':'12.34','extras':'5.00',
            'currency':f.request.currency,'due_date':'2026-10-20','revision':'A',
            'request_id':f.request.pk,'quote_id':f.quote.pk,
            'supplier_confirmation':'B01 лист CONF-001: менеджер підтвердив кількість і дату', **changes}

    def post(self, path, payload, client=None):
        client = client or self.http
        return client.post(path, payload, content_type='application/json',
                           HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)

    def preview(self, payload, client=None):
        before = self.state()
        response = self.post('/api/erp/preview/', payload, client)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.state(), before, 'Preview changed business rows')
        return response.json()['id']

    def confirm(self, proposal, client=None):
        return self.post('/api/operations/confirm/', {'proposal_id':proposal,'confirmed':True}, client)

    def buy(self, payload, client=None):
        proposal = self.preview(payload, client)
        response = self.confirm(proposal, client)
        self.assertEqual(response.status_code, 200, response.content)
        return proposal, response.json(), Purchase.objects.get(pk=response.json()['purchase_id'])

    def state(self):
        return {model._meta.label:list(model.objects.order_by('pk').values())
                for model in (Purchase, Lot, Movement, Event)} | {
            'operations.Configuration':list(Configuration.objects.exclude(key='erp_write').order_by('pk').values())}


@override_settings(BOS_DATA_MODE='working', DEBUG=False, ANTHROPIC_API_KEY='',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ProcurementBridgeTests(BridgeFixture, TestCase):
    def test_direct_purchase_needs_reason_and_preserves_explicit_reason(self):
        payload = self.payload()
        for field in ('quote_id','request_id','supplier_confirmation'):
            payload.pop(field)
        before = self.state()
        denied = self.post('/api/erp/preview/', payload)
        self.assertEqual(denied.status_code, 422, denied.content)
        self.assertEqual(self.state(), before)
        _, _, po = self.buy({**payload,'direct_reason':'Пряма синтетична закупівля за терміновою потребою'})
        self.assertIsNone(po.quote_id)
        self.assertEqual(po.approval_snapshot['source'], 'direct')
        self.assertEqual(po.approval_snapshot['direct_reason'], 'Пряма синтетична закупівля за терміновою потребою')
        self.assertEqual(Movement.objects.count(), 0)

    def test_quote_purchase_and_partial_receipts_in_three_currencies(self):
        for currency in ('EUR','USD','UAH'):
            with self.subTest(currency=currency):
                f = self.fixture(currency,currency)
                payload = self.payload(f)
                proposal, receipt, po = self.buy(payload)
                self.assertEqual((po.quote_id,po.request_id,po.item_id,po.supplier_id),
                                 (f.quote.pk,f.request.pk,f.item.pk,f.supplier.pk))
                self.assertEqual((po.quantity,po.price,po.extras,po.received,po.currency,po.revision),
                                 (D('10'),D('12.34'),D('5'),D('0'),currency,'A'))
                snap = po.approval_snapshot
                self.assertEqual((snap['source'],snap['quote_code'],snap['request_code']),
                                 ('quote',f.quote.code,f.request.code))
                self.assertEqual(snap['original_terms'], f.terms)
                self.assertEqual(snap['agreed_quantity'], '10')
                self.assertEqual(snap['agreed_due_date'], '2026-10-20')
                self.assertEqual(snap['supplier_confirmation'], payload['supplier_confirmation'])
                self.assertEqual(snap['confirmation_kind'], 'manager_attestation')
                self.assertEqual(snap['source_documents']['quote']['checksum'], f.source.checksum)
                self.assertEqual(snap['source_documents']['request']['document_id'], f.spec.pk)
                before = self.state()
                self.assertEqual(self.confirm(proposal).json(), receipt)
                self.assertEqual(self.state(), before)
                for n in ('4','6'):
                    receive = {'action':'erp_receive','purchase_id':po.pk,'quantity':n,
                               'code':'B01-RCV-'+uuid4().hex[:12],'location_id':self.location.pk}
                    pid = self.preview(receive)
                    response = self.confirm(pid)
                    self.assertEqual(response.status_code, 200, response.content)
                    after = self.state()
                    self.assertEqual(self.confirm(pid).json(), response.json())
                    self.assertEqual(self.state(), after)
                po.refresh_from_db()
                self.assertEqual((po.received,po.status), (D('10'),'received'))
                movements = Movement.objects.filter(purchase=po).order_by('pk')
                self.assertEqual(list(movements.values_list('quantity',flat=True)), [D('4'),D('6')])
                self.assertEqual(movements.aggregate(n=Sum('cost'))['n'], D('128.40'))
                self.assertTrue(all(m.lot.quality=='pending' and m.lot.currency==currency for m in movements))
                over = self.post('/api/erp/preview/', {**receive,'code':'B01-OVER-'+currency,'quantity':'1'})
                self.assertEqual(over.status_code, 422, over.content)

    def test_quote_bound_fields_and_confirmation_are_not_client_controlled(self):
        wrong_supplier = Counterparty.objects.create(name='B01 інший постачальник', type='supplier')
        wrong_item = Item.objects.create(code='B01-UNMAPPED',name='Інший',unit='шт.',revision='A')
        for changes in ({'supplier_id':wrong_supplier.pk},{'item_id':wrong_item.pk},{'price':'12.35'},
                {'extras':'4.99'},{'currency':'USD'},{'revision':'B'},{'request_id':None},
                {'supplier_confirmation':''},{'supplier_confirmation':True},
                {'due_date':'2026-09-11'},{'due_date':'2026-11-01'},{'quantity':'10.001'},
                {'direct_reason':'Неприпустимий подвійний шлях'}):
            with self.subTest(changes=changes):
                before = self.state()
                response = self.post('/api/erp/preview/', self.payload(**changes))
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(self.state(), before)
        self.f.item.unit='кг'; self.f.item.save(update_fields=['unit'])
        response=self.post('/api/erp/preview/',self.payload())
        self.assertEqual(response.status_code,422,response.content)

    def test_ineligible_or_unverified_source_is_refused(self):
        for terms in ({'valid_until':'2026-09-11'},{'moq':11},{'coating_included':False},
                      {'material_certificate':False},{'currency':'USD'},{'revision':'B'}):
            with self.subTest(terms=terms):
                self.f.quote.terms={**self.f.terms,**terms};self.f.quote.save(update_fields=['terms'])
                response=self.post('/api/erp/preview/',self.payload())
                self.assertEqual(response.status_code,422,response.content)
        self.f.quote.terms=deepcopy(self.f.terms);self.f.quote.save(update_fields=['terms'])
        self.f.source.status='needs_review';self.f.source.save(update_fields=['status'])
        response=self.post('/api/erp/preview/',self.payload())
        self.assertEqual(response.status_code,422,response.content)
        self.assertFalse(Purchase.objects.exists())

    def test_existing_netto_tax_basis_is_preserved_and_unknown_tax_basis_refused(self):
        self.f.quote.terms={**self.f.terms,'tax_basis':'excluding_VAT'}
        self.f.quote.save(update_fields=['terms'])
        _,_,po=self.buy(self.payload(quantity='4'))
        self.assertEqual(po.approval_snapshot['original_terms']['tax_basis'],'excluding_VAT')
        self.f.quote.terms={**self.f.terms,'tax_basis':'including_VAT'}
        self.f.quote.save(update_fields=['terms'])
        before=self.state()
        response=self.post('/api/erp/preview/',self.payload(quantity='4'))
        self.assertEqual(response.status_code,422,response.content)
        self.assertEqual(self.state(),before)

    def test_changed_request_or_quote_invalidates_old_proposal_without_rewriting_history(self):
        for model, obj, changes in ((SupplierQuote,self.f.quote,{'terms':{**self.f.terms,'shipping':'4.00'}}),
                                    (ProcurementRequest,self.f.request,{'quantity':9})):
            with self.subTest(model=model._meta.label):
                pid=self.preview(self.payload())
                prior={key:getattr(obj,key) for key in changes}
                model.objects.filter(pk=obj.pk).update(**changes)
                before=self.state()
                response=self.confirm(pid)
                self.assertEqual(response.status_code,409,response.content)
                self.assertEqual(self.state(),before)
                self.assertIsNone(ActionProposal.objects.get(pk=pid).receipt)
                model.objects.filter(pk=obj.pk).update(**prior)
        _,_,po=self.buy(self.payload())
        approved=deepcopy(po.approval_snapshot)
        self.f.quote.terms={**self.f.terms,'unit_price':'99.99'};self.f.quote.save(update_fields=['terms'])
        pid=self.preview({'action':'erp_postpone','purchase_id':po.pk,'due_date':'2026-10-25','reason':'Синтетичне перенесення'})
        self.assertEqual(self.confirm(pid).status_code,200)
        po.refresh_from_db()
        self.assertEqual(po.approval_snapshot,approved)
        self.assertEqual((po.price,po.original_due), (D('12.34'),date(2026,10,20)))

    def test_original_bytes_and_latest_version_rechecked_at_confirmation(self):
        pid=self.preview(self.payload())
        self.f.source.content=b'B01 changed original, unchanged recorded SHA'
        self.f.source.save(update_fields=['content'])
        before=self.state()
        response=self.confirm(pid)
        self.assertEqual(response.status_code,422,response.content)
        self.assertEqual(self.state(),before)
        self.assertIsNone(ActionProposal.objects.get(pk=pid).receipt)
        self.f.source.content=('B01 synthetic source '+self.f.source.code).encode();self.f.source.save(update_fields=['content'])
        pid=self.preview(self.payload())
        newer=self.document('B01-NEW')
        newer.code=self.f.source.code;newer.revision='B';newer.save()
        response=self.confirm(pid)
        self.assertEqual(response.status_code,409,response.content)
        self.assertFalse(Purchase.objects.exists())

    def test_split_allocation_and_compare_remainder_preserve_multiple_suppliers(self):
        _,_,first=self.buy(self.payload(quantity='6'))
        other=Counterparty.objects.create(name='B01 другий постачальник',type='supplier')
        quote=SupplierQuote.objects.create(code='B01-Q-SECOND',request=self.f.request,
                                          supplier=other,document=self.f.source,terms=self.f.terms)
        response=self.http.get('/api/operations/compare/?code='+self.f.request.code+'&quantity=4')
        self.assertEqual(response.status_code,200,response.content)
        data=response.json()
        self.assertEqual((data['request']['id'],data['request']['original_quantity'],data['request']['quantity']),
                         (self.f.request.pk,10,4))
        self.assertEqual((D(data['request']['allocated_quantity']),D(data['request']['remaining_quantity'])),(D('6'),D('4')))
        row=next(x for x in data['rows'] if x['id']==quote.pk)
        self.assertEqual(row['supplier_id'],other.pk)
        self.buy(self.payload(quantity='4',quote_id=quote.pk,supplier_id=other.pk))
        before=self.state()
        denied=self.post('/api/erp/preview/',self.payload(quantity='1'))
        self.assertEqual(denied.status_code,422,denied.content)
        self.assertEqual(self.state(),before)
        self.assertEqual(Purchase.objects.filter(request=self.f.request).aggregate(n=Sum('quantity'))['n'],D('10'))
        self.assertEqual(Purchase.objects.filter(request=self.f.request).count(),2)

    def test_direct_request_allocation_and_mapping_are_checked(self):
        payload=self.payload(quantity='6')
        payload.pop('quote_id');payload.pop('supplier_confirmation')
        payload['direct_reason']='Синтетична пряма закупівля частини вимоги'
        self.buy(payload)
        for changes in ({'quantity':'5'},{'revision':'B'},{'currency':'USD'}):
            response=self.post('/api/erp/preview/',{**payload,'code':'B01-DIR-'+uuid4().hex[:8],**changes})
            self.assertEqual(response.status_code,422,response.content)
        self.assertEqual(Purchase.objects.count(),1)

    def test_fractional_allocation_and_item_planning_currency_are_not_extra_restrictions(self):
        self.f.item.currency='USD';self.f.item.save(update_fields=['currency'])
        self.buy(self.payload(quantity='6.5'))
        self.buy(self.payload(quantity='3.5'))
        self.assertEqual(Purchase.objects.aggregate(n=Sum('quantity'))['n'],D('10'))
        self.assertEqual(set(Purchase.objects.values_list('currency',flat=True)),{'EUR'})

    def test_event_failure_rolls_back_po_and_receipt_then_retry_succeeds(self):
        pid=self.preview(self.payload())
        if connection.vendor=='sqlite':
            create="CREATE TRIGGER b01_event_failure BEFORE INSERT ON erp_event BEGIN SELECT RAISE(ABORT, 'B01 synthetic event failure'); END"
            drop=['DROP TRIGGER b01_event_failure']
        else:
            create="CREATE FUNCTION b01_event_fail() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'B01 synthetic event failure' USING ERRCODE='23514'; END; $$ LANGUAGE plpgsql"
            drop=['DROP TRIGGER b01_event_failure ON erp_event','DROP FUNCTION b01_event_fail()']
        with connection.cursor() as cursor:
            cursor.execute(create)
            if connection.vendor!='sqlite':
                cursor.execute('CREATE TRIGGER b01_event_failure BEFORE INSERT ON erp_event FOR EACH ROW EXECUTE FUNCTION b01_event_fail()')
        try:
            before=self.state()
            response=self.confirm(pid)
            self.assertEqual(response.status_code,409,response.content)
            self.assertEqual(self.state(),before)
            self.assertIsNone(ActionProposal.objects.get(pk=pid).receipt)
        finally:
            with connection.cursor() as cursor:
                for sql in drop:cursor.execute(sql)
        response=self.confirm(pid)
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(Purchase.objects.count(),1)
        self.assertEqual(Event.objects.filter(action='erp_purchase').count(),1)
        with self.assertRaises(ProtectedError):
            self.f.quote.delete()

    def test_bound_private_file_bytes_are_rechecked_without_fallback(self):
        raw=b'B01 real private quote original'
        receipt=private_document_storage.save_verified(raw,hashlib.sha256(raw).hexdigest(),legacy_blob_bytes=0)
        doc=Document.objects.create(code='B01-PRIVATE-Q',revision='A',title='B01 private quote',
            original_file=receipt.name,size=receipt.size,content=b'',text=raw.decode(),
            checksum=receipt.checksum,status='approved',access_level='operational')
        private_document_storage.finalize(receipt)
        self.f.quote.document=doc;self.f.quote.save(update_fields=['document'])
        pid=self.preview(self.payload())
        path=Path(settings.MEDIA_ROOT)/receipt.name
        try:
            path.write_bytes(b'B01 real private altered file')
            before=self.state()
            response=self.confirm(pid)
            self.assertEqual(response.status_code,422,response.content)
            self.assertEqual(self.state(),before)
            self.assertIsNone(ActionProposal.objects.get(pk=pid).receipt)
        finally:
            path.unlink()

    def test_source_scope_and_observer_projection_are_enforced(self):
        manager=Client(enforce_csrf_checks=True,raise_request_exception=False)
        login_test_client(manager,'manager',capabilities=('view_document','export_workspace'))
        observer=Client(enforce_csrf_checks=True,raise_request_exception=False)
        login_test_client(observer,'observer',capabilities=('view_document',))
        pid,_,po=self.buy(self.payload(),manager)
        for client in (self.http,manager):
            response=client.get('/api/erp/snapshot/')
            row=next(x for x in response.json()['purchases'] if x['id']==po.pk)
            self.assertEqual(row['approval_snapshot']['original_terms'],self.f.terms)
        response=observer.get('/api/erp/snapshot/')
        row=next(x for x in response.json()['purchases'] if x['id']==po.pk)
        self.assertEqual(row['approval_snapshot']['quote_code'],self.f.quote.code)
        for key in ('original_terms','supplier_confirmation','direct_reason','price','extras','confirmation_kind'):
            self.assertNotIn(key,row['approval_snapshot'])
        self.assertNotIn('price',row)
        self.assertEqual(self.post('/api/erp/preview/',self.payload(),observer).status_code,403)
        self.f.source.access_level='ceo';self.f.source.save(update_fields=['access_level'])
        for path in ('/api/erp/snapshot/','/api/erp/export/','/api/operations/export/'):
            response=manager.get(path)
            self.assertEqual(response.status_code,200,response.content)
            self.assertNotIn(self.f.quote.code,response.content.decode())
            self.assertNotIn('CONF-001',response.content.decode())
        self.assertEqual(self.confirm(pid,manager).status_code,404)
        denied=self.post('/api/erp/preview/',self.payload(quantity='1'),manager)
        self.assertEqual(denied.status_code,404,denied.content)

    def test_historical_snapshot_source_hides_po_not_an_operational_lot_or_partial_aggregate(self):
        manager=Client(enforce_csrf_checks=True,raise_request_exception=False)
        login_test_client(manager,'manager',capabilities=('view_document','export_workspace'))
        _,_,po=self.buy(self.payload(quantity='6'))
        pid=self.preview({'action':'erp_receive','purchase_id':po.pk,'code':'B01-SCOPED-LOT',
                          'quantity':'6','location_id':self.location.pk})
        received=self.confirm(pid)
        self.assertEqual(received.status_code,200,received.content)
        lot_id=received.json()['lot_id']
        # Current Quote now refers to a visible different document, but the
        # approved source remains the original document in the immutable PO.
        visible=self.document('B01-REPLACEMENT-SOURCE')
        self.f.quote.document=visible;self.f.quote.save(update_fields=['document'])
        self.f.source.access_level='ceo';self.f.source.save(update_fields=['access_level'])
        snapshot=manager.get('/api/erp/snapshot/').json()
        self.assertFalse(any(x['id']==po.pk for x in snapshot['purchases']))
        self.assertFalse(any(x.get('purchase_id')==po.pk for x in snapshot['movements']))
        lot=next(x for x in snapshot['lots'] if x['id']==lot_id)
        self.assertEqual(D(lot['quantity']),D('6'))
        self.assertNotIn('approval_snapshot',lot)
        self.assertNotIn('CONF-001',json.dumps(snapshot))
        limited=manager.get('/api/operations/compare/?code='+self.f.request.code).json()['request']
        self.assertEqual((limited['allocated_quantity'],limited['remaining_quantity'],limited['allocation_visibility']),
                         (None,None,'restricted'))
        complete=self.http.get('/api/operations/compare/?code='+self.f.request.code).json()['request']
        self.assertEqual((D(complete['allocated_quantity']),D(complete['remaining_quantity'])),(D('6'),D('4')))

    def test_creation_writers_lock_before_reading_source_rows(self):
        request={'code':'B01-R-HTTP','part':self.f.item.code,'revision':'A','quantity':10,'unit':'шт.',
            'currency':'EUR','required_by':'2026-10-31','owner_id':self.owner.pk,
            'document_id':self.f.spec.pk,'details':{}}
        quote={'code':'B01-Q-HTTP','request_code':self.f.request.code,'supplier_id':self.f.supplier.pk,
            'document_id':self.f.source.pk,'terms':self.f.terms}
        for path,payload in (('/api/operations/requests/create/',request),('/api/operations/quotes/create/',quote)):
            with self.subTest(path=path), CaptureQueriesContext(connection) as captured:
                response=self.post(path,payload)
            self.assertEqual(response.status_code,201,response.content)
            sql=[query['sql'].lower() for query in captured.captured_queries]
            locks=[i for i,x in enumerate(sql) if x.startswith('update "operations_configuration"')]
            reads=[i for i,x in enumerate(sql) if x.startswith('select') and any('"'+table+'"' in x
                    for table in ('operations_document','operations_procurementrequest','operations_supplierquote'))]
            self.assertTrue(locks,'Source writer did not acquire the canonical ERP mutex')
            self.assertTrue(reads)
            self.assertLess(locks[0],min(reads))


@override_settings(BOS_DATA_MODE='working', DEBUG=False, ANTHROPIC_API_KEY='',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ProcurementBridgeConcurrencyTests(BridgeFixture, TransactionTestCase):
    def test_two_confirmations_cannot_overallocate_and_successful_replay_is_identical(self):
        proposals=[self.preview(self.payload(quantity='6')) for _ in range(2)]
        cookies=deepcopy(self.http.cookies)
        barrier=threading.Barrier(2)
        def worker(pid):
            connections.close_all()
            client=Client(enforce_csrf_checks=True,raise_request_exception=False)
            client.cookies=deepcopy(cookies)
            try:
                barrier.wait(timeout=10)
                response=self.confirm(pid,client)
                return {'status':response.status_code,'json':response.json(),'proposal':pid}
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(worker,proposals))
        print('B01_CONCURRENCY '+json.dumps(results,ensure_ascii=False))
        self.assertEqual(sorted(x['status'] for x in results),[200,409],results)
        self.assertEqual(Purchase.objects.count(),1)
        self.assertEqual(Purchase.objects.aggregate(n=Sum('quantity'))['n'],D('6'))
        self.assertEqual(Event.objects.filter(action='erp_purchase').count(),1)
        winner=next(x for x in results if x['status']==200)
        before=self.state()
        self.assertEqual(self.confirm(winner['proposal']).json(),winner['json'])
        self.assertEqual(self.state(),before)
        loser=next(x for x in results if x['status']==409)
        self.assertEqual(self.confirm(loser['proposal']).status_code,409)
        self.assertEqual(self.state(),before)


class PurchaseSourceMigrationTests(TransactionTestCase):
    def test_historical_rows_ids_and_deleted_highwater_survive_forwards_and_backwards(self):
        # C01: execute this unchanged historical DDL oracle on its own new DB.
        from fixtures.synthetic.task_schema_isolation import isolated_case
        if isolated_case(self,task_boundary=None):return
        self.assertEqual(os.environ.get('DJANGO_SETTINGS_MODULE'),'verification_settings')
        executor=MigrationExecutor(connection)
        latest=executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda:MigrationExecutor(connection).migrate(latest))
        old_target=[('erp','0002_row_boundaries')]
        executor.migrate(old_target)
        apps=executor.loader.project_state(old_target).apps
        OldItem=apps.get_model('erp','Item');OldPurchase=apps.get_model('erp','Purchase')
        supplier=Counterparty.objects.create(name='B01 historical supplier',type='supplier')
        item=OldItem.objects.create(code='B01-HIST-I',name='B01 історична номенклатура')
        values={'item_id':item.pk,'supplier_id':supplier.pk,'quantity':'10','received':'4',
                'price':'12.34','extras':'5.00','currency':'EUR','due_date':'2026-10-20',
                'original_due':'2026-10-20','revision':'A','status':'partial'}
        po=OldPurchase.objects.create(code='B01-HIST-PO',**values)
        # Raise the sequence via an actual generated ID, then delete only this
        # own synthetic row. No existing installation is read or migrated.
        removed=OldPurchase.objects.create(code='B01-HIST-DELETED',**values)
        removed_id=removed.pk;removed.delete()
        before=list(OldPurchase.objects.order_by('pk').values())
        MigrationExecutor(connection).migrate(latest)
        after=list(Purchase.objects.order_by('pk').values())
        self.assertEqual([{k:v for k,v in row.items() if k not in ('quote_id','approval_snapshot')} for row in after],before)
        self.assertTrue(all(row['quote_id'] is None and row['approval_snapshot'] is None for row in after))
        migrated=Purchase.objects.create(code='B01-HIST-NEXT',**values)
        self.assertGreater(migrated.pk,removed_id)
        last_id=migrated.pk;migrated.delete()
        MigrationExecutor(connection).migrate(old_target)
        self.assertEqual(list(OldPurchase.objects.order_by('pk').values()),before)
        next_row=OldPurchase.objects.create(code='B01-HIST-ROLLBACK-NEXT',**values)
        self.assertGreater(next_row.pk,last_id)
        next_row.delete()
        MigrationExecutor(connection).migrate(latest)


@override_settings(BOS_DATA_MODE='working', DEBUG=False, ANTHROPIC_API_KEY='',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PurchaseSourceRollbackRefusalTests(BridgeFixture, TransactionTestCase):
    def test_actual_approved_po_refuses_lossy_rollback_with_schema_and_rows_unchanged(self):
        # C01: execute this unchanged historical DDL oracle on its own new DB.
        from fixtures.synthetic.task_schema_isolation import isolated_case
        if isolated_case(self,task_boundary=None):return
        executor=MigrationExecutor(connection)
        latest=executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda:MigrationExecutor(connection).migrate(latest))
        # Create the genuinely approved HTTP purchase on the current runtime,
        # then pin the empty later stages to the exact historical B01 boundary.
        # No populated source is deleted; the old state/oracle below is unchanged.
        _,_,po=self.buy(self.payload())
        from erp.models import ImportBatch,ImportIdentity
        from erp.corrections import MODELS
        self.assertFalse(ImportBatch.objects.exists())
        self.assertFalse(ImportIdentity.objects.exists())
        for model in MODELS:self.assertFalse(model.objects.exists())
        executor.migrate([('erp','0003_purchase_source')])
        def state():
            with connection.cursor() as cursor:
                description=connection.introspection.get_table_description(cursor,'erp_purchase')
                columns=[tuple(row) for row in description]
                constraints=connection.introspection.get_constraints(cursor,'erp_purchase')
                cursor.execute('SELECT * FROM erp_purchase ORDER BY id')
                rows=cursor.fetchall()
                cursor.execute('SELECT app,name FROM django_migrations ORDER BY app,name')
                migrations=cursor.fetchall()
                if connection.vendor=='sqlite':
                    cursor.execute("SELECT seq FROM sqlite_sequence WHERE name='erp_purchase'")
                else:
                    cursor.execute("SELECT last_value,is_called FROM erp_purchase_id_seq")
                sequence=cursor.fetchall()
            return {'columns':columns,'constraints':constraints,'rows':rows,
                    'migrations':migrations,'sequence':sequence}
        before=state()
        refused=False
        try:
            MigrationExecutor(connection).migrate([('erp','0002_row_boundaries')])
        except RuntimeError:
            refused=True
        after=state()
        changed=[key for key in before if before[key]!=after[key]]
        print('B01_SOURCE_ROLLBACK '+json.dumps({'refused':refused,'changed':changed,
              'purchase_id':po.pk,'source':'actual HTTP approved quote purchase'},ensure_ascii=False))
        self.assertTrue(refused,'Rollback removed approved source fields instead of refusing')
        self.assertEqual(after,before,'Refused migration changed schema, purchase rows, migration receipt or sequence')
