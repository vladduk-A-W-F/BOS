import io, json, os, pathlib, time, uuid
work=pathlib.Path(__file__).resolve().parent
repo=work.parent/'bos-fullgit-20260920'
import sys
sys.path.insert(0,str(repo))
name=work/('check_'+uuid.uuid4().hex+'.sqlite3')
assert not name.exists()
os.environ.update(DJANGO_SETTINGS_MODULE='verification_settings',BOS_VERIFY_DB='sqlite',
    BOS_TEST_DB_NAME=str(name),BOS_TEST_MEDIA=str(work/'api-fixture-media'),BOS_DATA_MODE='demo')
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import Client, override_settings
from scripts.check_support import login_test_client
from erp import service
from boss_project.policy import Policy
output=work/'data-evidence/api-fixtures.json'
with override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher']):
    for command in ('migrate','seed_bos_demo','seed_erp_demo','seed_bos_workspace','seed_bos_ua'):
        call_command(command,stdout=io.StringIO(),verbosity=0)
    rows=[]
    smoke=[]
    for role in ('ceo','manager','observer'):
        client=Client(enforce_csrf_checks=True)
        login_test_client(client,role,capabilities=('view_document',))
        identity=client.get('/api/auth/me/')
        assert identity.status_code==200,identity.content
        identity=identity.json()
        before=service.fingerprint()
        start=time.perf_counter()
        points=client.get('/api/erp/workpoints/')
        snapshot=client.get('/api/erp/snapshot/')
        assert points.status_code==snapshot.status_code==200,(points.status_code,snapshot.status_code)
        assert service.fingerprint()==before
        rows.append({'role':role,'capabilities':Policy(points.wsgi_request).capabilities(),
            'access_revision':points['X-BoS-Access'],'workpoints':points.json(),'snapshot':snapshot.json()})
        smoke.append({'role':role,'endpoints':['workpoints','snapshot'],'http_statuses':[200,200],
            'handler_pair_seconds':round(time.perf_counter()-start,6),'measurement':'Django test client; not browser HTTP'})
    for path in ('/','/assets/app.js','/api/runtime/status/'):
        response=client.get(path)
        assert response.status_code==200,(path,response.status_code)
        if getattr(response,'streaming',False): b''.join(response.streaming_content)
        smoke.append({'path':path,'status':response.status_code})
output.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(work/'data-evidence/dev-handler-smoke.json').write_text(json.dumps({'profile':'verification/demo SQLite isolated',
    'database':str(name),'checks':smoke,'browser_run':False,'tcp_devserver_run':False},indent=2)+'\n',encoding='utf-8')
connection.close()
print(json.dumps({'fixture_file':str(output),'roles':len(rows),'handler_smoke':'PASS','database_preserved':str(name)}))
