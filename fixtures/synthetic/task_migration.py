"""Own subprocess earlier Task schema. Never reshapes the shared test database."""
import json
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase,override_settings
from tasks.test_commands import CommandFixture
from tasks.models import Task

@override_settings(BOS_DATA_MODE='working',DEBUG=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class LegacyTaskMigrationTests(CommandFixture,TransactionTestCase):
    def test_actual_legacy_null_upgrade_and_empty_reverse_keep_values_ids_and_highwater(self):
        previous=[('tasks','0004_task_branch')];latest=[('tasks','0005_controlled_tasks')]
        MigrationExecutor(connection).migrate(previous)
        try:
            historical=MigrationExecutor(connection).loader.project_state(previous).apps.get_model('tasks','Task')
            source=historical.objects.create(id=21,title='Історичний текст',assignee='Попереднє ім’я',status='overdue',priority=None,category='Історична категорія',deadline='2020-01-02')
            removed=historical.objects.create(id=80001,title='Видалений тільки синтетичний ID');removed.delete()
            before=list(historical.objects.order_by('pk').values())
            MigrationExecutor(connection).migrate(latest)
            for row in Task.objects.order_by('pk').values():
                self.assertEqual({k:row[k] for k in before[0]},before[0]);self.assertEqual([row[k] for k in ('assignee_employee_id','sales_order_id','result','archived_at')],[None]*4)
            with connection.cursor() as cursor:cursor.execute("SELECT seq FROM sqlite_sequence WHERE name='tasks_task'");self.assertEqual(cursor.fetchone()[0],80001)
            MigrationExecutor(connection).migrate(previous);self.assertEqual(list(historical.objects.order_by('pk').values()),before)
            with connection.cursor() as cursor:cursor.execute("SELECT seq FROM sqlite_sequence WHERE name='tasks_task'");self.assertEqual(cursor.fetchone()[0],80001)
            MigrationExecutor(connection).migrate(latest);new=Task.objects.create(title='Наступний фактичний ID');self.assertGreater(new.pk,80001)
        finally:MigrationExecutor(connection).migrate(latest)
        print('C01_LEGACY '+json.dumps({'exact_old_rows':True,'all_new_fields_null':True,'highwater':80001,'next_id':new.pk}))

