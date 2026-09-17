"""B03 populated source history: real SQL constraints, reverse refusal and typed copy."""
from copy import deepcopy
from decimal import Decimal as D
import json
import tempfile
from pathlib import Path
from uuid import uuid4
from django.apps import apps
from django.conf import settings
from django.db import connection,transaction,IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import TransactionTestCase,override_settings
from erp.test_corrections import CorrectionFixture
from erp.corrections import MODELS
from erp.models import Lot,Movement,Event,Purchase
from scripts import data_transfer as transfer
from scripts.schema_preflight import inspect_schema
from scripts.reconcile_data import make_snapshot
from scripts.check_data_transfer import sqlite_target
from fixtures.synthetic.table_inventory import C03_TABLES


@override_settings(BOS_DATA_MODE='working',DEBUG=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CorrectionPreservationTests(CorrectionFixture,TransactionTestCase):
    def populated(self):
        receipts=[];order,line,lot,shipment=self.sale(shipped='1.000',quantity='5.000',price='10.00');self.act('reserve',lot_id=lot.pk,line_id=line.pk,quantity='3.000')
        receipts.append(self.correction(self.command('cancel_remaining',line_id=line.pk,quantity='3.000')))
        po,receipt_lot,source=self.supply();pair=self.correction(self.command('return_supplier',receipt_id=source.pk,quantity='1.000'));receipts.append(pair)
        receipts.append(self.correction(self.command('confirm_supplier_claim',claim_id=pair[1]['claim_id'],amount='4.00',currency='EUR',source_document_id=self.f.spec.pk)))
        inv=self.act('invoice',order_id=order.pk,code='B03-PRESERVE-INV',due_date='2026-10-01')
        credit=self.correction(self.command('credit_invoice',invoice_id=inv['invoice_id'],basis='commercial',source_document_id=self.f.spec.pk,allocations=[{'invoice_line_index':0,'amount':'1.00'}]));receipts.append(credit)
        receipts.append(self.correction(self.command('reverse_credit',credit_id=credit[1]['invoice_adjustment_id'])))
        for model in MODELS:self.assertTrue(model.objects.exists(),model._meta.label)
        return receipts

    def all_rows(self):return {model._meta.label:list(model.objects.order_by('pk').values()) for model in (*MODELS,Lot,Movement,Event,Purchase)}

    def database_state(self):
        with connection.cursor() as cursor:
            if connection.vendor=='sqlite':
                cursor.execute('SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name');schema=cursor.fetchall()
                cursor.execute('SELECT name,seq FROM sqlite_sequence ORDER BY name');sequences=cursor.fetchall()
            else:
                schema={table:connection.introspection.get_constraints(cursor,table) for table in connection.introspection.table_names()};sequences=[]
            cursor.execute('SELECT app,name,applied FROM django_migrations ORDER BY app,name');migrations=cursor.fetchall()
        return {'schema':schema,'sequences':sequences,'migrations':migrations,'rows':self.all_rows()}

    def test_populated_corrections_refuse_lossy_backward_before_any_schema_or_row_change(self):
        # C01: execute this unchanged historical DDL oracle on its own new DB.
        from fixtures.synthetic.task_schema_isolation import isolated_case
        if isolated_case(self,task_boundary='0004_task_branch',finance_boundary='0007_money_boundaries'):return
        self.populated();before=self.database_state()
        with self.assertRaisesRegex(RuntimeError,'історію коригувань'):
            MigrationExecutor(connection).migrate([('erp','0004_initial_import_ledger')])
        self.assertEqual(self.database_state(),before)
        print('B03_REVERSE_REFUSED '+json.dumps({'populated_models':6,'schema_rows_sequences_migrations_unchanged':True}))

    def test_real_sql_boundaries_and_protected_sources_refuse_without_rewriting_history(self):
        self.populated();before=self.all_rows()
        values=[('OrderCancellation','quantity',D(0)),('CancellationRelease','quantity',D(999)),('GoodsReturn','allocated_cost',D(999)),('SupplierClaim','currency','BAD'),('InvoiceAdjustment','total',D(-1)),('InvoiceAdjustmentLine','amount',D(-1))]
        for name,field,value in values:
            with self.subTest(model=name):
                row=apps.get_model('erp',name).objects.first()
                with self.assertRaises(IntegrityError),transaction.atomic():type(row).objects.filter(pk=row.pk).update(**{field:value})
        returned=apps.get_model('erp','GoodsReturn').objects.first()
        with self.assertRaises(ProtectedError):returned.source.delete()
        with self.assertRaises(ProtectedError):returned.event.delete()
        self.assertEqual(self.all_rows(),before)

    def test_all_six_populated_ledgers_typed_transfer_preserves_exact_ids_hashes_and_receipts(self):
        receipts=self.populated();before=self.all_rows();source=Path(str(connection.settings_dict['NAME']))
        with tempfile.TemporaryDirectory(prefix='bos-b03-typed-') as folder:
            work=Path(folder);snapshot=work/('check_'+uuid4().hex+'.sqlite3');capture=make_snapshot(source,snapshot);self.assertTrue(capture['source_main_unchanged'])
            bundle=work/'typed';manifest=transfer.export_snapshot(snapshot,settings.MEDIA_ROOT,bundle,inspect_schema=inspect_schema);self.assertEqual(set(manifest['tables']),set(C03_TABLES))
            for model in MODELS:self.assertEqual(manifest['tables'][model._meta.db_table]['count'],model.objects.count())
            target=sqlite_target(work,bundle/'media')
            try:
                transfer.import_to_disposable(bundle,target,verify_actual_schema=lambda row:inspect_schema(row.name));restored=transfer.validate_snapshot(Path(target.name),bundle/'media',inspect_schema=inspect_schema)
                for key in ('tables','sequences','media','media_references','logical_schema_hash'):self.assertEqual(restored[key],manifest[key],key)
                cursor=target.connection.cursor()
                for proposal,receipt in receipts:
                    cursor.execute('SELECT result FROM erp_event WHERE id=?',(receipt['erp_event_id'],));self.assertEqual(json.loads(cursor.fetchone()[0]),receipt)
            finally:target.connection.close()
            self.assertEqual(transfer.file_hash(snapshot),manifest['source_sha256'])
        self.assertEqual(self.all_rows(),before)
        for proposal,receipt in receipts:self.assertEqual(self.confirm(proposal).json(),receipt)
        self.assertEqual(self.all_rows(),before)
        print('B03_TYPED '+json.dumps({'exact_tables':56,'populated_models':6,'source_unchanged':True,'receipt_replays':len(receipts)}))
