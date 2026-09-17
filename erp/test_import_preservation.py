"""Real populated B02 provenance through migration refusal and full typed transfer."""
import json
import tempfile
from pathlib import Path
from uuid import uuid4
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase,override_settings
from django.conf import settings
from erp.test_initial_import import InitialImportFixture
from erp.models import ImportBatch,ImportIdentity,Purchase
from scripts import data_transfer as transfer
from scripts.schema_preflight import inspect_schema
from scripts.reconcile_data import make_snapshot
from scripts.check_data_transfer import sqlite_target


@override_settings(BOS_DATA_MODE='working',DEBUG=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ImportPreservationTests(InitialImportFixture,TransactionTestCase):
    def ledger(self):
        return {m._meta.label:list(m.objects.order_by('pk').values()) for m in (ImportBatch,ImportIdentity)}

    def test_populated_import_history_refuses_backward_migration_unchanged(self):
        # C01: execute this unchanged historical DDL oracle on its own new DB.
        from fixtures.synthetic.task_schema_isolation import isolated_case
        if isolated_case(self,task_boundary=None):return
        batch=self.batch();self.commit(batch)
        # This is the exact B02 rollback boundary; no later B03 source exists.
        executor=MigrationExecutor(connection);latest=executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda:MigrationExecutor(connection).migrate(latest))
        from erp.corrections import MODELS
        for model in MODELS:self.assertFalse(model.objects.exists())
        executor.migrate([('erp','0004_initial_import_ledger')])
        before=(self.state(),self.ledger())
        with connection.cursor() as c:
            c.execute("SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name");schema=c.fetchall()
            c.execute('SELECT * FROM django_migrations ORDER BY id');migrations=c.fetchall()
        with self.assertRaisesRegex(RuntimeError,'журнал походження'):
            MigrationExecutor(connection).migrate([('erp','0003_purchase_source')])
        with connection.cursor() as c:
            c.execute("SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name");self.assertEqual(c.fetchall(),schema)
            c.execute('SELECT * FROM django_migrations ORDER BY id');self.assertEqual(c.fetchall(),migrations)
        self.assertEqual((self.state(),self.ledger()),before)

    def test_populated_ledger_full_typed_transfer_preserves_source_receipts_and_ids(self):
        from fixtures.synthetic.table_inventory import C03_TABLES
        batch=self.batch();preview,receipt=self.commit(batch);before=(self.state(),self.ledger())
        source=Path(str(connection.settings_dict['NAME']))
        with tempfile.TemporaryDirectory(prefix='bos-b02-typed-') as folder:
            work=Path(folder);snapshot=work/('check_'+uuid4().hex+'.sqlite3')
            capture=make_snapshot(source,snapshot);self.assertTrue(capture['source_main_unchanged'])
            bundle=work/'typed';manifest=transfer.export_snapshot(snapshot,settings.MEDIA_ROOT,bundle,inspect_schema=inspect_schema)
            self.assertEqual(set(manifest['tables']),set(C03_TABLES))
            self.assertEqual(manifest['tables']['erp_importbatch']['count'],1)
            self.assertEqual(manifest['tables']['erp_importidentity']['count'],9)
            target=sqlite_target(work,bundle/'media')
            try:
                transfer.import_to_disposable(bundle,target,verify_actual_schema=lambda row:inspect_schema(row.name))
                restored=transfer.validate_snapshot(Path(target.name),bundle/'media',inspect_schema=inspect_schema)
                for key in ('tables','sequences','media','media_references','logical_schema_hash'):self.assertEqual(restored[key],manifest[key],key)
                cur=target.connection.cursor();cur.execute('SELECT id,receipt,canonical_source FROM erp_importbatch')
                row=cur.fetchone();self.assertEqual(row[0],batch['batch_id'].replace('-',''))
                self.assertEqual(json.loads(row[1]),receipt);self.assertEqual(json.loads(row[2]),ImportBatch.objects.get().canonical_source)
                cur.execute('SELECT approval_snapshot FROM erp_purchase');self.assertEqual(json.loads(cur.fetchone()[0]),Purchase.objects.get().approval_snapshot)
            finally:target.connection.close()
            self.assertEqual(transfer.file_hash(snapshot),manifest['source_sha256'])
        self.assertEqual((self.state(),self.ledger()),before)
        replay=self.confirm(preview);self.assertEqual(replay.json(),receipt);self.assertEqual((self.state(),self.ledger()),before)
