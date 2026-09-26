"""Focused C03 statement surfaces only: no fullgate, fullverify, browser or field suite."""
from pathlib import Path
import sys,os,json,hashlib,uuid,traceback,logging
from collections import Counter,defaultdict
from urllib.parse import urlencode
root=Path(sys.argv[1]).resolve(); output=Path(sys.argv[2]).resolve()
output.parent.mkdir(parents=True,exist_ok=True)
db=output.parent/('check_'+uuid.uuid4().hex+'.sqlite3');media=output.parent/('media_'+uuid.uuid4().hex);media.mkdir()
os.environ.update(DJANGO_SETTINGS_MODULE='verification_settings',BOS_DATA_MODE='working',BOS_TEST_DB_NAME=str(db),BOS_TEST_MEDIA=str(media))
sys.path[:0]=[str(root/'scripts'),str(root)]
import django;django.setup()
from django.conf import settings
from django.core.management import call_command
from django.db import connection,transaction
from django.test import override_settings
from django.urls import resolve
from scripts.access_isolation import OwnedSweepSQLite
from access_fixtures import SweepFixtures
from check_access import catalogue,signature,public_row,materialize,canonical,contract,response_oracle,admin_redirect_oracle,run_c03_controls,C03_SOURCE,C03_JOURNAL,METHODS,ROLES
settings.ROOT_URLCONF='boss_project.server_urls'
logging.getLogger('django.request').setLevel(logging.CRITICAL)
owner=OwnedSweepSQLite.create_new(db,root);owner.assert_owned(connection);call_command('migrate',verbosity=0)
live=catalogue();manifest=json.loads((root/'scripts/access_routes.json').read_text())
baseline=json.loads((output.parent.parent/'C01_BASELINE_ROUTES.json').read_text())
assert manifest['patterns'][:180]==baseline['patterns'] and len(baseline['patterns'])==180
assert manifest['required_field_tests']==baseline['required_field_tests'] and len(baseline['required_field_tests'])==57
assert Counter(map(signature,live))==Counter(map(signature,manifest['patterns'])) and len(live)==190
selected=[r for r in live if r['pattern'].startswith('api/statements/') or r['name']=='transaction-summary']
assert len(selected)==10,[(r['pattern'],r['name']) for r in selected]
cases=[];coverage=[]
with override_settings(BOS_DATA_MODE='working',DEBUG=False,ANTHROPIC_API_KEY='',PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher']):
 f=SweepFixtures('operations.test_access');f.build();assert not f.issues,f.issues
 definitions=defaultdict(list)
 for row in selected:
  for path in materialize(row,f):definitions[path].append(row)
 for path,rows in definitions.items():
  matched=resolve(path);row=next(r for r in rows if matched.func is r['_node'].callback)
  assert len(rows)==1,('unexpected_selected_shadow',path)
  coverage.append({'path':path,'pattern':row['pattern'],'name':row['name']})
  contexts=[(r,'full') for r in ROLES]
  if canonical(path)=='/api/statements/imports/{pk}/export/':contexts += [('ceo','no_export')]
  for role,variant in contexts:
   for method in METHODS:
    case={'route':path,'pattern':row['pattern'],'method':method,'role':role,'variant':variant,'passed':False}
    try:
     expected,reason=contract(row,path,method,role,variant);case.update(expectation=sorted(expected),policy=reason)
     committed=method=='POST' and canonical(path)==C03_SOURCE
     with owner.committed_case(connection,settings.MEDIA_ROOT) if committed else transaction.atomic():
      client=f.client(role);f.limit_capabilities(role,variant)
      data,mode=f.payload(row,path,method,role,client);before=f.state_digest();request_path=path+f.query(row,path)
      kwargs={'HTTP_X_CSRFTOKEN':client.cookies[settings.CSRF_COOKIE_NAME].value}
      if data is None:body=b'';ctype='application/json'
      elif mode=='form':body=urlencode(data,doseq=True).encode();ctype='application/x-www-form-urlencoded'
      elif mode=='multipart':
       from django.test.client import encode_multipart,BOUNDARY,MULTIPART_CONTENT
       body=encode_multipart(BOUNDARY,data);ctype=MULTIPART_CONTENT
      else:body=json.dumps(data).encode();ctype='application/json'
      response=client.generic(method,request_path,body,content_type=ctype,**kwargs)
      case['status']=response.status_code
      leaks,size=response_oracle(response,row,path,method,role,f,variant);case.update(leaks=leaks,response_bytes=size)
      redirect_ok,checks=admin_redirect_oracle(response,row,path,role,client,f,variant)
      case['redirect_checks']=checks
      changed=f.state_digest()!=before
      allowed_create=reason=='allowed_raw_create' and response.status_code==201
      case['unexpected_business_change']=changed and not allowed_create
      if allowed_create and not changed:leaks.append('missing_positive_source_creation')
      case['passed']=response.status_code in expected and not leaks and not case['unexpected_business_change'] and redirect_ok
      if not case['passed']:case['body_excerpt']=response.content[:350].decode(errors='replace')
      if not committed:transaction.set_rollback(True)
    except Exception as exc:case.update(error=str(exc),traceback=traceback.format_exc())
    cases.append(case)
  print('Focused statement surface',len(coverage),'/',len(definitions),'HTTP',len(cases),flush=True)
 controls=run_c03_controls(f,owner)
report={'scope':'Actual Django HTTP on own new synthetic SQLite/media; fixed10 selected statement/journal route definitions only, no fullgate/fullverify/browser/A09/field-suite execution','source_root':str(root),'db':str(db),'baseline_retained':{'route_records':180,'required_field_ids':57},'catalogue_exact':190,'selected_definitions':[public_row(r) for r in selected],'coverage':coverage,'cases':cases,'c03_controls':controls,'counts':{'selected_definitions':len(selected),'concrete_urls':len(coverage),'surface_http':len(cases),'surface_passed':sum(c['passed'] for c in cases),'control_groups':len(controls),'control_passed':sum(c['passed'] for c in controls),'control_http':sum(len(c['http']) for c in controls),'redirect_http':sum(len(c.get('redirect_checks',[])) for c in cases)},'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['scripts/access_fixtures.py','scripts/access_routes.json','scripts/check_access.py','finance/statement_views.py','finance/statements.py','finance/statement_reads.py']},'full_gate_run':False}
report['failures']=[c for c in cases if not c['passed']]+[c for c in controls if not c['passed']]
output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');connection.close()
print(json.dumps(report['counts'],ensure_ascii=False));print('Failures',len(report['failures']));sys.exit(bool(report['failures']))
