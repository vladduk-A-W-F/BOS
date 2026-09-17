"""B02 real HTTP contract. All records/files belong to the isolated test database."""
from copy import deepcopy
from datetime import date
from decimal import Decimal as D
import csv
import io
import json
import os
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, TestCase, override_settings
from employees.models import Employee
from finance.models import Counterparty
from operations.models import ActionProposal, Configuration
from scripts.check_support import login_test_client
from erp.models import Item, Location, Lot, Movement, Purchase, SalesOrder, SalesLine, Event


class InitialImportFixture:
    def setUp(self):
        self.assertEqual(os.environ.get('DJANGO_SETTINGS_MODULE'), 'verification_settings')
        self.assertTrue(Path(str(connection.settings_dict['NAME'])).name.startswith('check_'))
        self.http = Client(enforce_csrf_checks=True, raise_request_exception=False)
        self.user = login_test_client(self.http, 'ceo', capabilities=('view_document','export_workspace'))
        self.owner = Employee.objects.create(full_name='B02 синтетичний відповідальний')
        Configuration.objects.create(key='dataset', value={'as_of':'2026-09-12'})
        Configuration.objects.get_or_create(key='erp_write', defaults={'value':{'revision':0}})

    def batch(self, currency='EUR', suffix='A'):
        code=lambda value:'B02-'+suffix+'-'+value
        rows=[
            {'entity':'counterparty','external_id':'supplier','name':'B02 постачальник '+suffix,'type':'supplier'},
            {'entity':'counterparty','external_id':'customer','name':'B02 клієнт '+suffix,'type':'customer'},
            {'entity':'item','external_id':'material','bos_code':code('I'),'name':'B02 матеріал','unit':'кг','kind':'material','revision':'A','currency':currency},
            {'entity':'location','external_id':'warehouse','bos_code':code('W'),'name':'B02 склад'},
            {'entity':'opening_lot','external_id':'lot-one','bos_code':code('L1'),'item_ref':'material','location_ref':'warehouse','unit':'кг','revision':'A','quantity':'1.250','unit_cost':'2.34','currency':currency,'source_reference':'B02 зріз STOCK-1','reason':'Початковий синтетичний залишок'},
            {'entity':'opening_lot','external_id':'lot-two','bos_code':code('L2'),'item_ref':'material','location_ref':'warehouse','unit':'кг','revision':'A','quantity':'3.750','unit_cost':'2.34','currency':currency,'source_reference':'B02 зріз STOCK-2','reason':'Початковий синтетичний залишок'},
            {'entity':'sales_order','external_id':'sale','bos_code':code('SO'),'customer_ref':'customer','owner_id':self.owner.pk,'due_date':'2026-10-01','currency':currency,'source_status':'confirmed'},
            {'entity':'sales_line','external_id':'sale-line','order_ref':'sale','item_ref':'material','unit':'кг','revision':'A','quantity':'2.500','price':'4.12'},
            {'entity':'purchase_open_balance','external_id':'purchase-line','bos_code':code('PO'),'item_ref':'material','supplier_ref':'supplier','unit':'кг','revision':'A','source_order_code':'SOURCE-PO-7','source_line_id':'1','original_quantity':'8.000','received_before_cutover':'3.000','remaining_quantity':'5.000','price':'1.23','original_extras':'0.80','remaining_extras':'0.40','currency':currency,'original_due':'2026-09-01','due_date':'2026-09-01','source_reference':'B02 первинний реєстр закупівель'}]
        money=[]
        for curr in ('EUR','UAH','USD'):
            actual=curr==currency
            money.append({'currency':curr,'opening_raw_value':'11.70000' if actual else '0.00000',
                'opening_movement_cost':'11.70' if actual else '0.00','sales_open_value':'10.30000' if actual else '0.00000',
                'purchase_original_value':'10.64000' if actual else '0.00000','purchase_cutover_open_value':'6.55000' if actual else '0.00000'})
        return {'format':'bos.initial-import.v1','batch_id':str(uuid4()),'namespace':'synthetic-'+suffix.lower(),
            'cutover':'2026-09-12','tax_basis':'excluding_VAT','bindings':[],'rows':rows,
            'expected_source_control_totals':{'counts':{'counterparty':2,'item':1,'location':1,'opening_lot':2,'sales_order':1,'sales_line':1,'purchase_open_balance':1},
                'money':money,'stock':[{'item_ref':'material','location_ref':'warehouse','unit':'кг','revision':'A','currency':currency,'quantity':'5.000'}]}}

    def post(self,path,payload,client=None):
        client=client or self.http
        return client.post(path,json.dumps(payload,ensure_ascii=False),content_type='application/json',HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)

    def state(self):
        return {m._meta.label:list(m.objects.order_by('pk').values()) for m in
            (Employee,Counterparty,Item,Location,Lot,Movement,Purchase,SalesOrder,SalesLine,Event)}

    def preview(self,batch):
        before=self.state();r=self.post('/api/erp/import/preview/',batch)
        self.assertEqual(r.status_code,200,r.content);self.assertTrue(r.json()['valid'])
        self.assertEqual(self.state(),before)
        return r.json()

    def confirm(self,preview):
        return self.post('/api/operations/confirm/',{'proposal_id':preview['proposal']['id'],'confirmed':True})

    def commit(self,batch):
        p=self.preview(batch);r=self.confirm(p);self.assertEqual(r.status_code,200,r.content)
        return p,r.json()

    def multipart(self,batch):
        manifest=deepcopy(batch);rows=manifest.pop('rows');manifest['csv_files']=[];parts={}
        for entity in sorted({row['entity'] for row in rows}):
            selected=[{k:v for k,v in row.items() if k!='entity'} for row in rows if row['entity']==entity]
            stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=sorted({k for row in selected for k in row}));writer.writeheader();writer.writerows(selected)
            part='rows_'+entity;manifest['csv_files'].append({'entity':entity,'part':part})
            parts[part]=SimpleUploadedFile(part+'.csv',stream.getvalue().encode(),content_type='text/csv')
        parts['manifest']=SimpleUploadedFile('manifest.json',json.dumps(manifest).encode(),content_type='application/json')
        return parts


@override_settings(BOS_DATA_MODE='working',DEBUG=False,ANTHROPIC_API_KEY='',PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class InitialImportTests(InitialImportFixture,TestCase):
    def test_actual_three_currency_import_preserves_overdue_origin_and_pending_stock(self):
        for currency in ('EUR','UAH','USD'):
            with self.subTest(currency=currency):
                batch=self.batch(currency,currency);p,r=self.commit(batch)
                self.assertEqual(p['source_control_totals'],batch['expected_source_control_totals'])
                self.assertTrue(all(row['target_id'] is None for row in p['mappings']))
                self.assertEqual(r['counts']['create'],9)
                po=Purchase.objects.get(code='B02-'+currency+'-PO')
                self.assertEqual((po.quantity,po.received,po.extras,po.due_date,po.original_due),(D('5'),D('0'),D('.40'),date(2026,9,1),date(2026,9,1)))
                self.assertEqual(po.approval_snapshot['source'],'imported_open_balance')
                self.assertEqual(po.approval_snapshot['received_before_cutover'],'3.000')
                self.assertFalse(Movement.objects.filter(purchase=po).exists())
                lots=Lot.objects.filter(item=po.item)
                self.assertEqual(sum(x.quantity for x in lots),D('5'));self.assertEqual(set(lots.values_list('quality',flat=True)),{'pending'})
                self.assertEqual(Movement.objects.get(lot__code='B02-'+currency+'-L1').cost,D('2.92'))
                self.assertTrue(all(row['target_id'] for row in r['mappings']))

    def test_multiple_row_errors_and_totals_mismatch_never_commit(self):
        batch=self.batch();batch['rows'][4]['quantity']='1.2501';batch['rows'][5]['location_ref']='missing';batch['rows'][8]['remaining_quantity']='6'
        before=self.state();r=self.post('/api/erp/import/preview/',batch)
        self.assertEqual(r.status_code,422,r.content);self.assertFalse(r.json()['valid']);self.assertIsNone(r.json()['proposal'])
        self.assertGreaterEqual(len(r.json()['errors']),3);self.assertEqual(self.state(),before)
        self.assertEqual(ActionProposal.objects.count(),0)
        batch=self.batch();batch['expected_source_control_totals']['money'][0]['purchase_cutover_open_value']='7.00000'
        r=self.post('/api/erp/import/preview/',batch);self.assertEqual(r.status_code,422,r.content)
        self.assertIn('TOTALS_MISMATCH',[x['code'] for x in r.json()['errors']]);self.assertEqual(self.state(),before)

    def test_exact_replay_after_actual_receipt_keeps_source_totals_and_current_rows(self):
        batch=self.batch();p,receipt=self.commit(batch);po=Purchase.objects.get();location=Location.objects.get()
        normal=self.post('/api/erp/preview/',{'action':'erp_receive','purchase_id':po.pk,'code':'B02-RECEIPT','location_id':location.pk,'quantity':'2'})
        self.assertEqual(normal.status_code,200,normal.content)
        accepted=self.post('/api/operations/confirm/',{'proposal_id':normal.json()['id'],'confirmed':True});self.assertEqual(accepted.status_code,200,accepted.content)
        stable=self.state();again=self.confirm(p);self.assertEqual(again.status_code,200,again.content);self.assertEqual(again.json(),receipt);self.assertEqual(self.state(),stable)
        preview=self.preview(batch);self.assertEqual(preview['counts']['create'],0);self.assertEqual(preview['source_control_totals'],batch['expected_source_control_totals'])
        eur=next(x for x in preview['live_before']['money'] if x['currency']=='EUR');self.assertEqual(eur['purchase_open_value'],'3.93')
        self.assertEqual(preview['live_before'],preview['projected_after'])
        changed=deepcopy(batch);changed['rows'][-1]['price']='1.24'
        denied=self.post('/api/erp/import/preview/',changed);self.assertEqual(denied.status_code,409,denied.content);self.assertEqual(self.state(),stable)

    def test_json_csv_canonical_identity_and_whole_sales_composition(self):
        batch=self.batch();batch['rows'][7]['quantity']='2.5';p,receipt=self.commit(batch)
        second=deepcopy(batch);second['batch_id']=str(uuid4());second['rows'].reverse()
        parts=self.multipart(second)
        r=self.http.post('/api/erp/import/preview/',parts,HTTP_X_CSRFTOKEN=self.http.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertEqual(r.status_code,200,r.content);self.assertEqual(r.json()['counts']['create'],0)
        self.assertEqual(r.json()['semantic_sha256'],p['semantic_sha256'])
        new=deepcopy(batch);new['batch_id']=str(uuid4());extra=deepcopy(new['rows'][7]);extra['external_id']='new-line';new['rows'].append(extra)
        denied=self.post('/api/erp/import/preview/',new);self.assertEqual(denied.status_code,409,denied.content)
        self.assertEqual(SalesLine.objects.count(),1)

    def test_late_real_sql_failure_rolls_back_all_new_rows_and_receipt(self):
        batch=self.batch();p=self.preview(batch);before=self.state()
        with connection.cursor() as cursor:cursor.execute("CREATE TRIGGER b02_fail_po BEFORE INSERT ON erp_purchase BEGIN SELECT RAISE(ABORT,'own synthetic B02 failure'); END")
        failed=self.confirm(p);self.assertEqual(failed.status_code,409,failed.content);self.assertEqual(self.state(),before)
        self.assertIsNone(ActionProposal.objects.get(pk=p['proposal']['id']).receipt)
        with connection.cursor() as cursor:cursor.execute('DROP TRIGGER b02_fail_po')
        done=self.confirm(p);self.assertEqual(done.status_code,200,done.content);self.assertEqual(Purchase.objects.count(),1)

    def test_import_does_not_bypass_normal_purchase_and_roles_or_stale_owner(self):
        batch=self.batch();p=self.preview(batch)
        Employee.objects.filter(pk=self.owner.pk).update(full_name='Змінено після preview')
        self.assertEqual(self.confirm(p).status_code,409)
        for role in ('manager','observer'):
            client=Client(enforce_csrf_checks=True,raise_request_exception=False);login_test_client(client,role)
            denied=self.post('/api/erp/import/preview/',batch,client);self.assertEqual(denied.status_code,403,denied.content)
        _,_=self.commit(batch)
        po=Purchase.objects.get()
        raw={'action':'erp_purchase','code':'B02-NORMAL','item_id':po.item_id,'supplier_id':po.supplier_id,'quantity':'1','price':'1.23','currency':'EUR','due_date':'2026-09-01','revision':'A','direct_reason':'Нове погодження'}
        denied=self.post('/api/erp/preview/',raw);self.assertEqual(denied.status_code,422,denied.content)
        raw['source']='imported_open_balance';self.assertEqual(self.post('/api/erp/preview/',raw).status_code,422)

    def test_persisted_opening_conflict_and_batch_source_export(self):
        batch=self.batch();_,receipt=self.commit(batch);stable=self.state()
        mixed=deepcopy(batch);mixed['batch_id']=str(uuid4());lot=deepcopy(mixed['rows'][4]);lot['external_id']='new-lot';lot['bos_code']='B02-NEW-LOT';mixed['rows'].append(lot)
        denied=self.post('/api/erp/import/preview/',mixed);self.assertEqual(denied.status_code,409,denied.content);self.assertEqual(self.state(),stable)
        detail=self.http.get('/api/erp/import/batches/'+batch['batch_id']+'/');self.assertEqual(detail.status_code,200,detail.content)
        self.assertEqual(detail.json()['first_commit_receipt'],receipt)
        export=self.http.get('/api/erp/import/batches/'+batch['batch_id']+'/export/');self.assertEqual(export.status_code,200,export.content)
        self.assertEqual(export.json()['first_commit_receipt'],receipt);self.assertEqual(len(export.json()['canonical_source']['rows']),9)

    def test_raw_duplicate_json_oversize_and_server_templates(self):
        token=self.http.cookies[settings.CSRF_COOKIE_NAME].value
        dup=self.http.post('/api/erp/import/preview/',b'{"format":"x","format":"y"}',content_type='application/json',HTTP_X_CSRFTOKEN=token)
        self.assertEqual(dup.status_code,400,dup.content)
        huge=self.http.post('/api/erp/import/preview/',b' '*200000,content_type='application/json',HTTP_X_CSRFTOKEN=token);self.assertEqual(huge.status_code,413,huge.content[:500])
        response=self.http.get('/api/erp/import/template/',{'owner_id':self.owner.pk,'format':'json'});self.assertEqual(response.status_code,200,response.content)
        self.preview(response.json())
        response=self.http.get('/api/erp/import/template/',{'owner_id':self.owner.pk,'format':'csv'});self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(set(response.json()),{'manifest','files'})
        wrapper=response.json();parts={'manifest':SimpleUploadedFile('manifest.json',json.dumps(wrapper['manifest'],ensure_ascii=False).encode())}
        for item in wrapper['files']:parts[item['part']]=SimpleUploadedFile(item['filename'],item['content_utf8'].encode())
        denied=self.http.post('/api/erp/import/preview/',parts);self.assertEqual(denied.status_code,403)
        parts={'manifest':SimpleUploadedFile('manifest.json',json.dumps(wrapper['manifest'],ensure_ascii=False).encode())}
        for item in wrapper['files']:parts[item['part']]=SimpleUploadedFile(item['filename'],item['content_utf8'].encode())
        parsed=self.http.post('/api/erp/import/preview/',parts,HTTP_X_CSRFTOKEN=token)
        self.assertEqual(parsed.status_code,200,parsed.content);self.assertEqual(parsed.json()['counts']['create'],27)
        self.assertTrue(all(row['purchase_cutover_open_value']=='6.55000' for row in parsed.json()['source_control_totals']['money']))

    def test_explicit_multipart_binding_keeps_raw_source_and_rejects_duplicate(self):
        batch=self.batch();supplier=Counterparty.objects.create(name='Наявний B02 постачальник',type='supplier')
        batch['rows']=[r for r in batch['rows'] if r['external_id']!='supplier'];batch['expected_source_control_totals']['counts']['counterparty']=1
        raw=json.dumps(batch,ensure_ascii=False).encode();binding=[{'entity':'counterparty','external_id':'supplier','target_id':supplier.pk}]
        parts={'batch':SimpleUploadedFile('batch.json',raw),'bindings':SimpleUploadedFile('bindings.json',json.dumps(binding).encode())}
        response=self.http.post('/api/erp/import/preview/',parts,HTTP_X_CSRFTOKEN=self.http.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertEqual(response.status_code,200,response.content);self.assertEqual(response.json()['counts']['bind'],1)
        confirmed=self.confirm(response.json());self.assertEqual(confirmed.status_code,200,confirmed.content)
        self.assertEqual(Purchase.objects.get().supplier_id,supplier.pk)
        exported=self.http.get('/api/erp/import/batches/'+batch['batch_id']+'/export/').json()
        import hashlib
        self.assertEqual(exported['source_part_sha256']['batch'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(exported['canonical_source']['bindings'],binding)
        batch['batch_id']=str(uuid4());batch['bindings']=binding
        parts={'batch':SimpleUploadedFile('batch.json',json.dumps(batch).encode()),'bindings':SimpleUploadedFile('bindings.json',json.dumps(binding).encode())}
        stable=self.state();denied=self.http.post('/api/erp/import/preview/',parts,HTTP_X_CSRFTOKEN=self.http.cookies[settings.CSRF_COOKIE_NAME].value)
        self.assertEqual(denied.status_code,422,denied.content);self.assertEqual(self.state(),stable)

    def test_forged_context_and_preview_phase_cannot_commit_historical_purchase(self):
        from erp import importing,service
        from django.db import transaction
        from boss_project.identity import actor_for_user
        batch=self.batch();self.commit(batch);po=Purchase.objects.get();principal=actor_for_user(self.user)
        data={'code':'B02-FORGED','item_id':po.item_id,'supplier_id':po.supplier_id,'quantity':'1.000','price':'1.23','extras':'0.00','currency':'EUR','due_date':'2026-09-01','revision':'A'}
        stable=self.state()
        with self.assertRaises(TypeError):importing.ImportAuthority()
        with self.assertRaises(PermissionError):service.dispatch({'action':'erp_purchase',**data},role='ceo',import_context=object())
        with transaction.atomic():
            with importing.authority('purchase',importing.digest(data),principal,'preview',{'batch':batch,'source':batch['rows'][-1]}) as ctx:
                with self.assertRaises(PermissionError):service.dispatch({'action':'erp_purchase',**data},role='ceo',import_context=ctx,import_phase='apply')
            with self.assertRaises(PermissionError):service.dispatch({'action':'erp_purchase',**data},role='ceo',import_context=ctx,import_phase='preview')
        self.assertEqual(self.state(),stable)

    def test_imported_source_projection_hides_commercial_values_from_observer(self):
        batch=self.batch();self.commit(batch)
        client=Client(enforce_csrf_checks=True,raise_request_exception=False);login_test_client(client,'observer')
        response=client.get('/api/erp/snapshot/');self.assertEqual(response.status_code,200,response.content)
        snapshot=response.json()['purchases'][0]['approval_snapshot']
        self.assertEqual(snapshot['source'],'imported_open_balance')
        self.assertEqual(snapshot['source_order_code'],'SOURCE-PO-7')
        for key in ('price','remaining_extras','original_quantity','received_before_cutover','source_reference','actor_id'):self.assertNotIn(key,snapshot)
        for suffix in ('','export/'):
            response=client.get('/api/erp/import/batches/'+batch['batch_id']+'/'+suffix)
            self.assertEqual(response.status_code,403,response.content)

    def test_existing_source_document_bytes_and_versions_are_rechecked(self):
        import hashlib
        from operations.models import Document
        raw=b'B02 exact source bytes'
        doc=Document.objects.create(code='B02-DOC',revision='A',title='B02 первинний документ',content=raw,checksum=hashlib.sha256(raw).hexdigest(),status='approved',access_level='management')
        batch=self.batch();batch['rows'][-1]['source_documents']={'primary':{'document_id':doc.pk,'code':doc.code,'revision':doc.revision,'checksum':doc.checksum}}
        p=self.preview(batch);before=self.state()
        Document.objects.filter(pk=doc.pk).update(content=b'Changed without changing declared checksum')
        failed=self.confirm(p);self.assertIn(failed.status_code,(409,422),failed.content);self.assertEqual(self.state(),before)
        Document.objects.filter(pk=doc.pk).update(content=raw)
        _,_=self.commit(batch);snapshot=Purchase.objects.get().approval_snapshot
        self.assertEqual(snapshot['source_documents']['primary']['checksum'],hashlib.sha256(raw).hexdigest())
        denied=self.post('/api/operations/preview/',{'action':'erp_import_batch','batch':batch})
        self.assertEqual(denied.status_code,422,denied.content)

    def test_late_sql_value_tampering_is_detected_before_atomic_commit(self):
        batch=self.batch();p=self.preview(batch);before=self.state()
        with connection.cursor() as cursor:cursor.execute("CREATE TRIGGER b02_alter_po AFTER INSERT ON erp_purchase BEGIN UPDATE erp_purchase SET price=price+1 WHERE id=NEW.id; END")
        failed=self.confirm(p);self.assertEqual(failed.status_code,422,failed.content);self.assertEqual(self.state(),before)
        self.assertIsNone(ActionProposal.objects.get(pk=p['proposal']['id']).receipt)
        with connection.cursor() as cursor:cursor.execute('DROP TRIGGER b02_alter_po')

    def test_strict_uuid_text_and_control_count_types_refuse_without_http500(self):
        for field,value in (('batch_id',1),('batch_id',None),('source_reference',1),('source_reference',None),('count',True),('count',1.0)):
            with self.subTest(field=field,value=value):
                batch=self.batch()
                if field=='source_reference':batch['rows'][-1][field]=value
                elif field=='count':batch['expected_source_control_totals']['counts']['item']=value
                else:batch[field]=value
                before=self.state();response=self.post('/api/erp/import/preview/',batch)
                self.assertIn(response.status_code,(400,422),response.content[:800]);self.assertFalse(response.json()['valid']);self.assertEqual(self.state(),before)

    def test_current_targets_include_reused_rows_without_reparenting_identities(self):
        from erp.models import ImportIdentity
        batch=self.batch();self.commit(batch);first={x.pk:x.first_batch_id for x in ImportIdentity.objects.all()}
        replay=deepcopy(batch);replay['batch_id']=str(uuid4());self.commit(replay)
        response=self.http.get('/api/erp/import/batches/'+replay['batch_id']+'/')
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(len(response.json()['current_targets']),9)
        self.assertEqual({x.pk:x.first_batch_id for x in ImportIdentity.objects.all()},first)
        mixed=deepcopy(batch);mixed['batch_id']=str(uuid4())
        item=deepcopy(mixed['rows'][2]);item['external_id']='second-item';item['bos_code']='B02-SECOND-I';mixed['rows'].append(item)
        lot=deepcopy(mixed['rows'][4]);lot.update(external_id='second-item-lot',bos_code='B02-SECOND-LOT',item_ref='second-item',quantity='1.000',unit_cost='2.00');mixed['rows'].append(lot)
        totals=mixed['expected_source_control_totals'];totals['counts']['item']+=1;totals['counts']['opening_lot']+=1
        totals['money'][0]['opening_raw_value']='13.70000';totals['money'][0]['opening_movement_cost']='13.70'
        totals['stock'].append({'item_ref':'second-item','location_ref':'warehouse','unit':'кг','revision':'A','currency':'EUR','quantity':'1.000'})
        self.commit(mixed)
        response=self.http.get('/api/erp/import/batches/'+mixed['batch_id']+'/')
        self.assertEqual(response.status_code,200,response.content);self.assertEqual(len(response.json()['current_targets']),11)
        self.assertEqual({x.pk:x.first_batch_id for x in ImportIdentity.objects.filter(pk__in=first)},first)

    def test_binding_only_mapping_reuse_and_profile_validation(self):
        from erp.importing import source_totals
        from erp.models import ImportIdentity
        supplier=Counterparty.objects.create(name='Наявний постачальник mapping',type='supplier')
        batch=self.batch();batch['rows']=[];batch['bindings']=[{'entity':'counterparty','external_id':'bound','target_id':supplier.pk}]
        batch['expected_source_control_totals']=source_totals([])
        p=self.preview(batch)
        self.assertEqual(p['counts'],{'create':0,'reuse':0,'bind':1})
        self.assertEqual(len(p['mappings']),1)
        self.assertEqual((p['mappings'][0]['decision'],p['mappings'][0]['target_id'],p['mappings'][0]['display_name']),('bind',supplier.pk,supplier.name))
        response=self.confirm(p);self.assertEqual(response.status_code,200,response.content)
        original=ImportIdentity.objects.get();first=original.first_batch_id
        batch['batch_id']=str(uuid4());p=self.preview(batch)
        self.assertEqual(p['counts'],{'create':0,'reuse':1,'bind':0});self.assertEqual(p['mappings'][0]['decision'],'reuse')
        response=self.confirm(p);self.assertEqual(response.status_code,200,response.content)
        detail=self.http.get('/api/erp/import/batches/'+batch['batch_id']+'/').json()
        self.assertEqual(len(detail['current_targets']),1);self.assertEqual(detail['current_targets'][0]['target_id'],supplier.pk)
        original.refresh_from_db();self.assertEqual(original.first_batch_id,first)
        supplier.is_active=False;supplier.save(update_fields=['is_active'])
        replay=self.preview(batch);self.assertEqual(self.confirm(replay).status_code,200)
        batch['batch_id']=str(uuid4());batch['namespace']='new-profile-source'
        denied=self.post('/api/erp/import/preview/',batch);self.assertEqual(denied.status_code,422,denied.content)
        for entity,obj in [('location',Location.objects.create(code='B02-NOT-WAREHOUSE',name='Виробництво',kind='production')),('item',Item.objects.create(code='B02-MAKE',name='Вироблюване',method='make'))]:
            batch['bindings']=[{'entity':entity,'external_id':'bound','target_id':obj.pk}]
            denied=self.post('/api/erp/import/preview/',batch);self.assertEqual(denied.status_code,422,denied.content)

    def test_new_rows_recheck_profile_of_reused_bindings(self):
        from erp.importing import source_totals
        item=Item.objects.create(code='B02-BOUND-ITEM',name='Наявний матеріал',method='buy',kind='material',unit='кг',revision='A')
        location=Location.objects.create(code='B02-BOUND-WH',name='Наявний склад',kind='warehouse')
        batch=self.batch();opening=deepcopy(batch['rows'][4]);batch['rows']=[]
        batch['bindings']=[{'entity':'item','external_id':'material','target_id':item.pk},{'entity':'location','external_id':'warehouse','target_id':location.pk}]
        batch['expected_source_control_totals']=source_totals([]);self.commit(batch)
        for model,target,field,value in [(Location,location,'kind','production'),(Item,item,'method','make')]:
            model.objects.filter(pk=target.pk).update(**{field:value})
            changed=deepcopy(batch);changed['batch_id']=str(uuid4());changed['rows']=[opening];changed['expected_source_control_totals']=source_totals([opening])
            before=self.state();denied=self.post('/api/erp/import/preview/',changed)
            self.assertEqual(denied.status_code,422,denied.content);self.assertEqual(self.state(),before)
            model.objects.filter(pk=target.pk).update(**{field:'warehouse' if field=='kind' else 'buy'})

    def test_low_ambient_decimal_context_preserves_exact_http_totals(self):
        from decimal import localcontext,ROUND_DOWN
        from fractions import Fraction
        from erp.importing import round_fraction
        batch=self.batch();next(r for r in batch['rows'] if r['entity']=='sales_line')['price']='123456.78'
        next(r for r in batch['expected_source_control_totals']['money'] if r['currency']=='EUR')['sales_open_value']='308641.95000'
        with localcontext() as context:
            context.prec=6;context.rounding=ROUND_DOWN
            preview,receipt=self.commit(batch)
            self.assertEqual(next(r for r in preview['source_control_totals']['money'] if r['currency']=='EUR')['sales_open_value'],'308641.95000')
            self.assertEqual(next(r for r in receipt['live_after']['money'] if r['currency']=='EUR')['sales_open_value'],'308641.95')
            self.assertEqual(round_fraction(Fraction('1234567.89')),D('1234567.89'))
            self.assertEqual((context.prec,context.rounding),(6,ROUND_DOWN))
