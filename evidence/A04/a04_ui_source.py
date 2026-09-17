import json, os, sys
from pathlib import Path
root=Path('/workspace/sites/bos-original-refined')
sys.path[:0]=[str(root),str(root/'scripts')]
os.environ['DJANGO_SETTINGS_MODULE']='demo_settings'
os.environ['BOS_DATA_MODE']='demo'
os.environ['BOS_TEST_DB_NAME']=':memory:'
os.environ['BOS_TEST_MEDIA']='/workspace/scratch/c7b51e996a9f/tmp/a04_ui_media'
os.environ['BOS_TEST_DEPENDENCIES']='/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages'
from django.conf import settings
from check_support import configure,login_test_client
configure(settings)
import django
django.setup()
from django.core.management import call_command
from django.test import Client
from employees.models import Employee
for command in ('migrate','seed_bos_demo','seed_erp_demo','seed_bos_workspace'):
    call_command(command,verbosity=0)
out={}
for index,role in enumerate(('ceo','manager','observer')):
    client=Client(enforce_csrf_checks=True)
    user=login_test_client(client,role,capabilities=('view_document','download_document','export_workspace'))
    Employee.objects.filter(pk=list(Employee.objects.order_by('pk').values_list('pk',flat=True))[index]).update(user=user)
    out[role]={}
    for name,path in [('snapshot','/api/erp/snapshot/'),('requests','/api/operations/requests/'),('compare','/api/operations/compare/?code=R01'),('audit','/api/operations/audit/'),('employees','/api/employees/'),('counterparties','/api/counterparties/'),('contracts','/api/contracts/'),('tasks','/api/tasks/')]:
        response=client.get(path)
        assert response.status_code==200,(role,path,response.status_code,response.content[:300])
        out[role][name]=response.json()
Path('/workspace/scratch/c7b51e996a9f/tmp/a04_ui_source.json').write_text(json.dumps(out,ensure_ascii=False))
print('Actual HTTP response fixtures: 3 roles x 8 endpoints; memory-only synthetic database.')
