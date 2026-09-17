"""C01 actual earlier-schema preservation and populated typed transfer."""
import json,tempfile
from pathlib import Path
from uuid import uuid4
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase,override_settings
from tasks.test_commands import CommandFixture
from tasks.models import Task
from operations.models import AuditEvent,ActionProposal
from scripts import data_transfer as transfer
from scripts.schema_preflight import inspect_schema
from scripts.reconcile_data import make_snapshot
from scripts.check_data_transfer import sqlite_target
from fixtures.synthetic.table_inventory import C03_TABLES

@override_settings(BOS_DATA_MODE='working',DEBUG=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TaskPreservationTests(CommandFixture,TransactionTestCase):
    def db_state(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name');schema=cursor.fetchall()
            cursor.execute('SELECT name,seq FROM sqlite_sequence ORDER BY name');sequences=cursor.fetchall()
            cursor.execute('SELECT app,name,applied FROM django_migrations ORDER BY app,name');migrations=cursor.fetchall()
        return {'schema':schema,'sequences':sequences,'migrations':migrations,'rows':self.state()}

    def test_actual_completed_archived_result_refuses_reverse_before_any_schema_change(self):
        task,p,r=self.create();self.command({'action':'update_task','task_id':task.pk,'status':'done','result':'Не можна втратити погоджений результат','reason':'Завершено фактичне доручення'})
        self.command({'action':'update_task','task_id':task.pk,'archived':True,'reason':'Збережено у постійному архіві'})
        before=self.db_state()
        with self.assertRaisesRegex(RuntimeError,'Відкат C01'):MigrationExecutor(connection).migrate([('tasks','0004_task_branch')])
        self.assertEqual(self.db_state(),before)

    def test_mixed_tasks_and_receipts_typed_transfer_preserve_full_native_columns(self):
        from erp.models import SalesOrder
        from finance.models import Counterparty
        customer=Counterparty.objects.create(name='Synthetic C01 typed customer',type='customer');order=SalesOrder.objects.create(code='C01-TYPED-ORDER',customer=customer,owner=self.employee,due_date='2026-10-01',currency='EUR')
        legacy=Task.objects.create(title='Legacy NULL result',assignee='Історичний працівник',status='done');task,p,r=self.create(order_id=order.pk)
        pairs=[(p,r),self.command({'action':'update_task','task_id':task.pk,'status':'done','result':'Повний результат\nДругий рядок','reason':'Підтверджено для переносу'}),self.command({'action':'update_task','task_id':task.pk,'archived':True,'reason':'Збережено перед переносом'})]
        before=self.state();source=Path(str(connection.settings_dict['NAME']))
        with tempfile.TemporaryDirectory(prefix='bos-c01-typed-') as folder:
            work=Path(folder);snapshot=work/('check_'+uuid4().hex+'.sqlite3');capture=make_snapshot(source,snapshot);self.assertTrue(capture['source_main_unchanged'])
            bundle=work/'typed';manifest=transfer.export_snapshot(snapshot,settings.MEDIA_ROOT,bundle,inspect_schema=inspect_schema);self.assertEqual(set(manifest['tables']),set(C03_TABLES));self.assertEqual(manifest['tables']['tasks_task']['count'],2)
            target=sqlite_target(work,bundle/'media')
            try:
                transfer.import_to_disposable(bundle,target,verify_actual_schema=lambda row:inspect_schema(row.name));restored=transfer.validate_snapshot(Path(target.name),bundle/'media',inspect_schema=inspect_schema)
                for key in ('tables','sequences','media','media_references','logical_schema_hash'):self.assertEqual(restored[key],manifest[key],key)
                cursor=target.connection.cursor();cursor.execute('SELECT result,assignee_employee_id,archived_at FROM tasks_task WHERE id=?',(legacy.pk,));self.assertEqual(cursor.fetchone(),(None,None,None))
                cursor.execute('SELECT sales_order_id FROM tasks_task WHERE id=?',(task.pk,));self.assertEqual(cursor.fetchone()[0],order.pk)
                for proposal,receipt in pairs:
                    cursor.execute('SELECT receipt FROM operations_actionproposal WHERE id=?',(proposal['id'].replace('-',''),));self.assertEqual(json.loads(cursor.fetchone()[0]),receipt)
            finally:target.connection.close()
            self.assertEqual(transfer.file_hash(snapshot),manifest['source_sha256'])
        self.assertEqual(self.state(),before)
        for p,r in pairs:self.assertEqual(self.confirm(p).json(),r)
        self.assertEqual(self.state(),before)
        print('C01_TYPED '+json.dumps({'exact_tables':56,'tasks':2,'receipt_replays':3,'legacy_null':True,'source_unchanged':True}))


class LegacyTaskMigrationIsolationTests(__import__('django.test',fromlist=['SimpleTestCase']).SimpleTestCase):
    def test_actual_legacy_null_upgrade_and_empty_reverse_keep_values_ids_and_highwater(self):
        import os,subprocess,sys
        with tempfile.TemporaryDirectory(prefix='bos-c01-historical-') as folder:
            work=Path(folder);env=os.environ.copy();env.update(DJANGO_SETTINGS_MODULE='verification_settings',BOS_VERIFY_DB='sqlite',BOS_TEST_DB_NAME=str(work/('check_'+uuid4().hex+'.sqlite3')),BOS_TEST_MEDIA=str(work/'media'),PYTHONDONTWRITEBYTECODE='1')
            result=subprocess.run([sys.executable,'-B','manage.py','test','fixtures.synthetic.task_migration.LegacyTaskMigrationTests','--noinput','-v2'],cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True,text=True,timeout=45)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertIn('C01_LEGACY ',result.stdout);print(result.stdout[result.stdout.index('C01_LEGACY '):].strip())
