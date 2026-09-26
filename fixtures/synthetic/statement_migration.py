"""C03 physical schema cases execute only through the isolated parent harness."""
import json,tempfile
from pathlib import Path
from uuid import uuid4
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase,override_settings
from finance import test_statements as fixture
from finance.models import StatementImport,StatementLine,StatementAllocation,Transaction
from operations.models import Document
from scripts import data_transfer as transfer
from scripts.schema_preflight import inspect_schema
from scripts.reconcile_data import make_snapshot
from scripts.check_data_transfer import sqlite_target
from fixtures.synthetic.table_inventory import B03_TABLES,C03_TABLES

@override_settings(BOS_DATA_MODE='working',DEBUG=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StatementMigrationTests(TransactionTestCase):
    setUp=fixture.StatementTests.setUp;post=fixture.StatementTests.post;csv=fixture.StatementTests.csv;upload=fixture.StatementTests.upload
    source=fixture.StatementTests.source;import_payload=fixture.StatementTests.import_payload;commit=fixture.StatementTests.commit;counts=fixture.StatementTests.counts
    def database_state(self):
        with connection.cursor() as c:
            c.execute('SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name');schema=c.fetchall()
            c.execute('SELECT name,seq FROM sqlite_sequence ORDER BY name');sequences=c.fetchall()
            rows={}
            for name in sorted(connection.introspection.table_names()):
                c.execute('SELECT * FROM '+connection.ops.quote_name(name)+' ORDER BY 1');rows[name]=c.fetchall()
        return {'schema':schema,'sequences':sequences,'rows':rows}
    def populated(self):
        doc=self.source();p,r=self.commit(self.import_payload(doc));d={'action':'erp_statement_reconcile','line_id':r['lines'][0]['line_id'],'transaction':{'mode':'create_transaction','category':'customer','description':'Первинний запис для точного переносу'},'matching':{'kind':'manual','counterparty_id':self.customer.pk,'counterparty_external_id':'client-1'},'reason':'Збереження погодженого першоджерела','allocations':[{'allocation_key':str(uuid4()),'mode':'new_payment','invoice_id':self.invoice.pk,'amount':'10.00','currency':'EUR','invoice_match':'exact_reference','reason':'Погоджена оплата точного рахунку'}]}
        p2,r2=self.commit(d)
        for model in (StatementImport,StatementLine,StatementAllocation):self.assertEqual(model.objects.count(),1)
        return [(p,r),(p2,r2)]
    def test_earlier_schema_addition_and_empty_reverse_preserve_all_old_rows_and_sequences(self):
        previous=[('finance','0007_money_boundaries')];latest=[('finance','0008_statement_ledgers')]
        MigrationExecutor(connection).migrate(previous)
        try:
            self.assertEqual(set(connection.introspection.table_names()),set(B03_TABLES))
            historical=MigrationExecutor(connection).loader.project_state(previous).apps.get_model('finance','Transaction')
            old=historical.objects.create(id=7,direction='in',amount='1.23',currency='EUR',date='2026-09-01',description='Історичний первинний запис',category='other')
            removed=historical.objects.create(id=70001,direction='out',amount='4.56',currency='USD',date='2026-09-02',description='Синтетичний high-water',category='other');removed.delete()
            before=self.database_state();old_rows=before['rows'];old_sequence=dict(before['sequences'])
            MigrationExecutor(connection).migrate(latest);after=self.database_state();self.assertEqual(set(after['rows']),set(C03_TABLES))
            for name in B03_TABLES-{'django_migrations'}:self.assertEqual(after['rows'][name],old_rows[name],name)
            # One real migration recorder INSERT advances its high-water;
            # every existing business table retains its exact sequence.
            for name,value in old_sequence.items():self.assertEqual(dict(after['sequences'])[name],value+(1 if name=='django_migrations' else 0),name)
            for model in (StatementImport,StatementLine,StatementAllocation):self.assertFalse(model.objects.exists())
            MigrationExecutor(connection).migrate(previous);back=self.database_state()
            self.assertEqual(back['schema'],before['schema']);self.assertEqual(dict(back['sequences']),{name:value+(1 if name=='django_migrations' else 0) for name,value in old_sequence.items()})
            for name in B03_TABLES-{'django_migrations'}:self.assertEqual(back['rows'][name],old_rows[name],name)
            self.assertEqual(back['rows']['django_migrations'],old_rows['django_migrations'])
        finally:MigrationExecutor(connection).migrate(latest)
        new=Transaction.objects.create(direction='in',amount='1.00',currency='EUR',date='2026-09-03',description='Наступний синтетичний ID',category='other')
        self.assertEqual(new.pk,70002)
        print('C03_MIGRATION '+json.dumps({'old_tables':53,'new_tables':56,'old_rows_unchanged':True,'old_highwater':70001,'next_id':new.pk}))
    def test_populated_reverse_refuses_before_any_schema_or_history_change(self):
        self.populated();before=self.database_state()
        with self.assertRaisesRegex(RuntimeError,'первинні виписки'):
            MigrationExecutor(connection).migrate([('finance','0007_money_boundaries')])
        self.assertEqual(self.database_state(),before)
        print('C03_REVERSE_REFUSED '+json.dumps({'populated_models':3,'schema_rows_sequences_migrations_unchanged':True}))
    def test_populated_full_typed_transfer_preserves_ids_bytes_binding_and_receipts(self):
        pairs=self.populated();source=Path(str(connection.settings_dict['NAME']));before=self.database_state()
        with tempfile.TemporaryDirectory(prefix='bos-c03-typed-') as folder:
            work=Path(folder);snapshot=work/('check_'+uuid4().hex+'.sqlite3');capture=make_snapshot(source,snapshot);self.assertTrue(capture['source_main_unchanged'])
            bundle=work/'typed';manifest=transfer.export_snapshot(snapshot,settings.MEDIA_ROOT,bundle,inspect_schema=inspect_schema);self.assertEqual(set(manifest['tables']),set(C03_TABLES))
            for model in (StatementImport,StatementLine,StatementAllocation):self.assertEqual(manifest['tables'][model._meta.db_table]['count'],1)
            target=sqlite_target(work,bundle/'media')
            try:
                transfer.import_to_disposable(bundle,target,verify_actual_schema=lambda t:inspect_schema(t.name));restored=transfer.validate_snapshot(Path(target.name),bundle/'media',inspect_schema=inspect_schema)
                for key in ('tables','sequences','media','media_references','logical_schema_hash'):self.assertEqual(restored[key],manifest[key],key)
                cursor=target.connection.cursor();line=StatementLine.objects.get();cursor.execute('SELECT binding_snapshot FROM finance_statementline WHERE id=?',(line.pk.hex,));self.assertEqual(json.loads(cursor.fetchone()[0]),line.binding_snapshot)
                for p,r in pairs:
                    cursor.execute('SELECT receipt FROM operations_actionproposal WHERE id=?',(p['id'].replace('-',''),));self.assertEqual(json.loads(cursor.fetchone()[0]),r)
            finally:target.connection.close()
            self.assertEqual(transfer.file_hash(snapshot),manifest['source_sha256'])
        self.assertEqual(self.database_state(),before)
        for p,r in pairs:self.assertEqual(self.post('/api/operations/confirm/',{'proposal_id':p['id'],'confirmed':True}).json(),r)
        after=self.database_state()
        # Replays retain only the exact accepted ERP mutex revision heartbeat.
        expected=json.loads(json.dumps(before['rows']['operations_configuration']))
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM operations_configuration LIMIT 0');columns=[x[0] for x in cursor.description]
        key_index=columns.index('key');value_index=columns.index('value');updated=0
        for row in expected:
            if row[key_index]=='erp_write':
                value=json.loads(row[value_index]);value['revision']+=len(pairs);row[value_index]=json.dumps(value);updated+=1
        self.assertEqual(updated,1)
        for expected_row,actual_row in zip(expected,after['rows']['operations_configuration']):
            expected_row[value_index]=json.loads(expected_row[value_index]);actual_row=list(actual_row);actual_row[value_index]=json.loads(actual_row[value_index]);self.assertEqual(actual_row,expected_row)
        self.assertEqual(len(expected),len(after['rows']['operations_configuration']))
        for name in before['rows']:
            if name!='operations_configuration':self.assertEqual(after['rows'][name],before['rows'][name],name)
        self.assertEqual(after['schema'],before['schema']);self.assertEqual(after['sequences'],before['sequences'])
        print('C03_TYPED '+json.dumps({'exact_tables':56,'populated_models':3,'literal_receipts':2,'source_bytes_and_ids_unchanged':True}))
