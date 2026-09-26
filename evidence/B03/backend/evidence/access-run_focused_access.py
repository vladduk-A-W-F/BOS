"""Only the new B03 outcome route; not the complete access gate."""
from pathlib import Path
import sys,os,json,hashlib,uuid,datetime,traceback
from collections import Counter
root=Path(__file__).resolve().parent/'source';phase=sys.argv[1]
runtime=Path(__file__).resolve().parent/('runtime_'+phase+'_'+uuid.uuid4().hex);runtime.mkdir();media=runtime/'media';media.mkdir();db=runtime/('check_'+uuid.uuid4().hex+'.sqlite3')
sys.path[:0]=[str(root),str(root/'scripts')]
os.environ.update(DJANGO_SETTINGS_MODULE='verification_settings',BOS_DATA_MODE='working',BOS_VERIFY_DB='sqlite',BOS_TEST_DB_NAME=str(db),BOS_TEST_MEDIA=str(media),PYTHONDONTWRITEBYTECODE='1')
os.environ.pop('ANTHROPIC_API_KEY',None)
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.db import connection,transaction
from django.test import override_settings
from scripts.access_isolation import OwnedSweepSQLite
from access_fixtures import SweepFixtures
import check_access as checker
owner=OwnedSweepSQLite.create_new(db,root);owner.assert_owned(connection)
if connection.introspection.table_names():raise RuntimeError('Refuse non-empty synthetic database')
call_command('migrate',verbosity=0)
report={'scope':'Only B03 outcome access extension; not gate4/fullverify/browser/PG acceptance','phase':phase,'runtime':str(runtime),'database_vendor':connection.vendor,'source_files':{},'cases':[],'failures':[]}
for name in ['scripts/access_fixtures.py','scripts/check_access.py','scripts/access_routes.json','erp/correction_views.py','erp/corrections.py']:
 report['source_files'][name]=hashlib.sha256((root/name).read_bytes()).hexdigest()
with override_settings(BOS_DATA_MODE='working',DEBUG=False,ANTHROPIC_API_KEY='',PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],ROOT_URLCONF='boss_project.server_urls'):
 fixtures=SweepFixtures('operations.test_access');fixtures.build()
 report['fixture']={'issues':fixtures.issues,'http':fixtures.correction_fixture_http,'source_ids':fixtures.correction_source_ids,'action':fixtures.correction_action,'operation_id':fixtures.correction_operation_id,'ceo_allocated_cost_control':fixtures.correction_receipt['allocated_cost']}
 live=checker.catalogue();manifest=json.loads((root/'scripts/access_routes.json').read_text());before=json.loads((root.parent/'BASE_ACCESS_ROUTES.json').read_text());old=before['patterns'];new=manifest['patterns'];live_rows=[checker.public_row(r) for r in live]
 report['catalogue']={'original_entries':len(old),'manifest_entries':len(new),'actual_entries':len(live),'old_entries_literal_equal':new[:len(old)]==old,'required_field_tests_unchanged':manifest['required_field_tests']==before['required_field_tests'],'unknown_actual':[json.loads(k) for k in (Counter(map(checker.signature,live))-Counter(map(checker.signature,new)))], 'missing_actual':[json.loads(k) for k in (Counter(map(checker.signature,new))-Counter(map(checker.signature,live)))]}
 rows=[r for r in live if r['pattern']=='api/erp/corrections/outcome/'];assert len(rows)==1;row=rows[0];path='/api/erp/corrections/outcome/'
 contexts=[(role,'full') for role in checker.ROLES]+[('manager','no_documents')]
 for role,variant in contexts:
  for method in checker.METHODS:
   case={'role':role,'variant':variant,'method':method,'route':path,'passed':False}
   try:expected,reason=checker.contract(row,path,method,role,variant);case.update(expectation=sorted(expected),policy=reason)
   except Exception as exc:expected=set();case['oracle_error']=str(exc)
   try:
    with transaction.atomic():
     client=fixtures.client(role);fixtures.limit_capabilities(role,variant);payload,mode=fixtures.payload(row,path,method,role,client);before_state=fixtures.state_digest()
     body=b'' if payload is None else json.dumps(payload).encode()
     response=client.generic(method,path+fixtures.query(row,path),body,content_type='application/json',HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
     leaks,size=checker.response_oracle(response,row,path,method,role,fixtures,variant)
     after_state=fixtures.state_digest();case.update(status=response.status_code,response_bytes=size,leaks=leaks,business_state_unchanged=after_state==before_state)
     if response.content and response.get('Content-Type','').startswith('application/json'):
      data=response.json();case['response']=data
     case['passed']=response.status_code in expected and not leaks and after_state==before_state
     transaction.set_rollback(True)
   except Exception as exc:case['execution_error']=type(exc).__name__+': '+str(exc);traceback.print_exc()
   report['cases'].append(case)
 report['totals']={'executed':len(report['cases']),'passed':sum(c['passed'] for c in report['cases']),'failed':sum(not c['passed'] for c in report['cases'])}
 report['complete_in_scoped_boundary']=not fixtures.issues and report['totals']['failed']==0 and len(new)==177 and len(live)==177 and report['catalogue']['old_entries_literal_equal'] and report['catalogue']['required_field_tests_unchanged'] and not report['catalogue']['unknown_actual'] and not report['catalogue']['missing_actual']
owner.assert_owned(connection);connection.close()
out=Path(__file__).resolve().parent/'evidence';out.mkdir(exist_ok=True);dest=out/(phase+'.json');dest.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n')
print(json.dumps({'report':str(dest),'catalogue':report['catalogue'],'totals':report['totals'],'scoped_complete':report['complete_in_scoped_boundary']},ensure_ascii=False))
raise SystemExit(0 if report['complete_in_scoped_boundary'] else 1)
