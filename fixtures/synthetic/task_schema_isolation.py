"""Run earlier-schema test bodies on a new owned SQLite DB, never shared test DDL.

Only tests import this helper. Existing assertions run unchanged in the child;
current-schema typed transfer remains strict about the physical schema hash.
"""
import json,os,secrets,subprocess,sys,tempfile
from pathlib import Path
from uuid import uuid4
from django.db import connection
from django.conf import settings

_CASE='BOS_C01_SCHEMA_CASE';_MARKER='BOS_C01_SCHEMA_MARKER';_TOKEN='BOS_C01_SCHEMA_TOKEN'


def isolated_case(case,*,task_boundary=None,finance_boundary=None):
    if connection.vendor!='sqlite':return False
    test_id=case.id();expected=os.environ.get(_CASE)
    if expected:
        marker=Path(os.environ[_MARKER]);value=json.loads(marker.read_text())
        case.assertEqual(expected,test_id);case.assertEqual(value['case'],test_id)
        case.assertEqual(value['token'],os.environ.get(_TOKEN));case.assertEqual(value['boundary'],task_boundary);case.assertEqual(value.get('finance_boundary'),finance_boundary)
        path=Path(str(connection.settings_dict['NAME']))
        case.assertTrue(marker.is_file() and not marker.is_symlink());case.assertEqual(path,Path(value['database']+'_django_test'))
        case.assertEqual(path.parent,marker.parent);case.assertEqual(os.environ.get('DJANGO_SETTINGS_MODULE'),'verification_settings')
        if task_boundary is not None:
            from tasks.models import Task
            from django.db.models import Q
            from django.db.migrations.executor import MigrationExecutor
            case.assertFalse(Task.objects.filter(Q(assignee_employee_id__isnull=False)|Q(sales_order_id__isnull=False)|Q(archived_at__isnull=False)|(Q(result__isnull=False)&~Q(result=''))).exists())
            MigrationExecutor(connection).migrate([('tasks',task_boundary)])
        if finance_boundary is not None:
            from finance.models import StatementImport,StatementLine,StatementAllocation
            from django.db.migrations.executor import MigrationExecutor
            for model in (StatementImport,StatementLine,StatementAllocation):case.assertFalse(model.objects.exists())
            MigrationExecutor(connection).migrate([('finance',finance_boundary)])
        return False
    with tempfile.TemporaryDirectory(prefix='bos-c01-schema-case-') as folder:
        work=Path(folder);database=work/('check_'+uuid4().hex+'.sqlite3');marker=work/'issued.json';token=secrets.token_hex(32)
        with marker.open('x') as handle:json.dump({'case':test_id,'token':token,'database':str(database),'boundary':task_boundary,'finance_boundary':finance_boundary},handle)
        marker.chmod(0o600)
        env=os.environ.copy();env.update(DJANGO_SETTINGS_MODULE='verification_settings',BOS_VERIFY_DB='sqlite',BOS_TEST_DB_NAME=str(database),BOS_TEST_MEDIA=str(work/'media'),PYTHONDONTWRITEBYTECODE='1')
        env.update({_CASE:test_id,_MARKER:str(marker),_TOKEN:token})
        result=subprocess.run([sys.executable,'-B','manage.py','test',test_id,'--noinput','-v2'],cwd=Path(__file__).resolve().parents[2],env=env,capture_output=True,text=True,timeout=90)
        case.assertEqual(result.returncode,0,result.stdout+result.stderr);case.assertIn('Ran 1 test',result.stderr);case.assertIn('OK',result.stderr)
        print('C01_SCHEMA_ISOLATED '+json.dumps({'case':test_id,'actual_child_exit':result.returncode,'historical_task_boundary':task_boundary}))
        for line in result.stdout.splitlines():
            if line.startswith(('B01_SOURCE_ROLLBACK ','B03_REVERSE_REFUSED ')):print(line)
    return True
