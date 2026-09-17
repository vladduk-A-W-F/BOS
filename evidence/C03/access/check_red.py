"""C03 pre-implementation expectations on frozen C01; own synthetic SQLite only."""
from pathlib import Path
import sys,os,json,hashlib,uuid,traceback,logging
from decimal import Decimal
from collections import Counter
root=Path(sys.argv[1]).resolve();output=Path(sys.argv[2]).resolve();output.parent.mkdir(parents=True,exist_ok=True)
db=output.parent/('check_'+uuid.uuid4().hex+'.sqlite3');media=output.parent/('media_'+uuid.uuid4().hex);media.mkdir()
os.environ.update(DJANGO_SETTINGS_MODULE='verification_settings',BOS_DATA_MODE='working',BOS_TEST_DB_NAME=str(db),BOS_TEST_MEDIA=str(media))
sys.path[:0]=[str(root/'scripts'),str(root)]
import django;django.setup()
from django.conf import settings
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection,transaction
from django.test import override_settings
from django.contrib import admin
from scripts.access_isolation import OwnedSweepSQLite
from access_fixtures import SweepFixtures
from check_access import catalogue,public_row
from operations.models import Document,ProcurementRequest
from finance.models import Transaction
settings.ROOT_URLCONF='boss_project.server_urls';logging.getLogger('django.request').setLevel(logging.CRITICAL)
owner=OwnedSweepSQLite.create_new(db,root);owner.assert_owned(connection);call_command('migrate',verbosity=0)
calls=[];checks=[]
csv=b'external_id,booking_date,direction,amount,currency,counterparty_external_id,invoice_reference,purpose\nC03-RED-EUR,2026-09-12,in,17.39,EUR,RED-CUSTOMER,,A04_C03_PRIVATE_PURPOSE\n'
def http(c,method,path,payload=None,multipart=False):
 kw={'HTTP_X_CSRFTOKEN':c.cookies[settings.CSRF_COOKIE_NAME].value}
 r=c.post(path,payload,**kw) if multipart else c.generic(method,path,json.dumps(payload or {}).encode(),content_type='application/json',**kw)
 calls.append({'method':method,'path':path,'status':r.status_code});return r
def require(r,status):
 assert r.status_code==status,(r.status_code,r.content[:300]);return r.json()
def upload():return {'file':SimpleUploadedFile('c03-access.csv',csv,content_type='text/csv'),'code':'A04-C03-SOURCE','revision':'A','title':'A04 C03 source'}
def check(name,fn,durable=False):
 start=len(calls)
 try:
  with owner.committed_case(connection,settings.MEDIA_ROOT) if durable else transaction.atomic():
   fn()
   if not durable:transaction.set_rollback(True)
  checks.append({'name':name,'passed':True,'http':calls[start:]})
 except Exception as exc:checks.append({'name':name,'passed':False,'error':str(exc),'traceback':traceback.format_exc(),'http':calls[start:]})
with override_settings(BOS_DATA_MODE='working',DEBUG=False,ANTHROPIC_API_KEY='',PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher']):
 f=SweepFixtures('operations.test_access');f.build();assert not f.issues,f.issues
 def routes():
  baseline=json.loads((output.parent.parent/'C01_BASELINE_ROUTES.json').read_text())['patterns'];added=json.loads((output.parent.parent/'PLANNED_ROUTE_ADDITIONS.json').read_text())
  sig=lambda row:json.dumps(row,sort_keys=True)
  actual=[public_row(x) for x in catalogue()]
  assert Counter(map(sig,actual))==Counter(map(sig,baseline+added)),('actual',len(actual),'expected',190)
  assert not {m._meta.model_name for m in admin.site._registry}&{'statementimport','statementline','statementallocation'}
 check('explicit190 catalogue with no statement ledger admin',routes)
 def roundtrip():
  c=f.client('ceo');created=require(http(c,'POST','/api/statements/sources/',upload(),True),201)
  assert created['checksum']==hashlib.sha256(csv).hexdigest() and created['status']=='needs_review'
  require(http(c,'POST',f'/api/operations/documents/{created["id"]}/review/',{'checksum':created['checksum']}),200)
  payload={'action':'erp_statement_import','document_id':created['id'],'source_sha256':created['checksum'],'source_system':'synthetic-bank','account_ref':'C03-RED-ACCOUNT','format':'bos_statement_csv_v1','parser_version':'1'}
  before=Transaction.objects.count();p=require(http(c,'POST','/api/erp/preview/',payload),200)
  r=require(http(c,'POST','/api/operations/confirm/',{'proposal_id':p['id'],'confirmed':True}),200)
  assert r['counts']=={'create':1,'reuse':0,'total':1} and Transaction.objects.count()==before
  assert require(http(c,'POST','/api/operations/confirm/',{'proposal_id':p['id'],'confirmed':True}),200)==r
 check('actual CEO source review import and exact replay without cash',roundtrip,True)
 for role in ('manager','observer'):
  def upload_denial(role=role):
   before=f.state_digest();r=require(http(f.client(role),'POST','/api/statements/sources/',upload(),True),403);assert f.state_digest()==before
  check(role+' cannot upload financial source before parser',upload_denial,True)
 for role in ('manager','observer'):
  def reads(role=role):
   c=f.client(role);uid='417a9537-3de8-4bf5-b99c-638cefcb96f0'
   for path in ('imports/',f'imports/{uid}/',f'imports/{uid}/export/','lines/',f'lines/{uid}/',f'lines/{uid}/candidates/','summary/'):
    require(http(c,'GET','/api/statements/'+path),403)
   for path in ('/api/transactions/summary/','/api/transactions/summary.json','/api/transactions/summary.json/'):
    require(http(c,'GET',path),403)
  check(role+' new reads denied including financial summary aliases',reads)
 def journal():
  expected={currency:{'in':Decimal(0),'out':Decimal(0)} for currency in ('EUR','USD','UAH')}
  for row in Transaction.objects.values('amount','currency','direction'):expected[row['currency']][row['direction']]+=row['amount']
  for path in ('/api/transactions/summary/','/api/transactions/summary.json','/api/transactions/summary.json/'):
   d=require(http(f.client('ceo'),'GET',path),200);assert d['includes_archived'] is True and d['balance_kind']=='period_movement'
   rows={r['currency']:r for r in d['currencies']};assert set(rows)==set(expected)
   for currency,t in expected.items():
    for name,value in {**t,'net':t['in']-t['out']}.items():assert rows[currency][name]==format(value,'.2f')
 check('CEO exact journal summary three currencies and aliases',journal)
 def historical():
  marker='A04_C03_HISTORICAL_SOURCE_SECRET';doc=f.seed.make_document('A04-C03-MARKER','operational',marker=marker)
  req=ProcurementRequest.objects.create(code='A04-C03-REQUEST',part='Synthetic',revision='A',quantity=1,currency='EUR',required_by=f.future,owner=f.seed.employee,document=doc)
  _,created=f.task_command('manager',{**f.task_payload(),'title':'A04 C03 historical task','request_code':req.code,'order_id':f.seed.order.pk})
  f.task_command('manager',{'action':'update_task','task_id':created['task_id'],'status':'done','result':marker,'reason':'Synthetic historical source proof'})
  # Explicit legacy fixture classification and mutable-label downgrade. This
  # does not pretend to be a successful C03 upload or rewrite an Import ledger.
  Document.objects.filter(pk=doc.pk).update(sections=[{'kind':'bos_statement_csv_v1'}],access_level='operational')
  c=f.client('manager')
  for path in (f'/api/operations/documents/{doc.pk}/',f'/api/operations/documents/{doc.pk}/download/',f'/api/tasks/{created["task_id"]}/',f'/api/tasks/{created["task_id"]}/history/'):
   r=http(c,'GET',path);assert r.status_code==404,(path,r.status_code);assert marker.encode() not in r.content
 check('permanent marker hides old document and historical Task source',historical)
result={'scope':'Actual C01-base Django HTTP + fixed manifest expectations; own synthetic SQLite/media; no fullgate/browser/A09; marker fixture explicitly synthetic','root':str(root),'checks':checks,'passed':sum(x['passed'] for x in checks),'failed':sum(not x['passed'] for x in checks),'http_count':len(calls),'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('scripts/access_routes.json','scripts/access_fixtures.py','scripts/check_access.py','finance/views.py','boss_project/policy.py')},'working_database_opened':False}
output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');connection.close();print(json.dumps({k:result[k] for k in ('passed','failed','http_count')},ensure_ascii=False));sys.exit(bool(result['failed']))
