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

rows=[]
def snapshot(f):
 return {m._meta.label_lower:list(m._base_manager.order_by(m._meta.pk.name).values()) for m in sorted(f.business_models,key=lambda m:m._meta.label_lower)}
def delta(before,after):
 return {key:{'before':before[key],'after':after[key]} for key in before if before[key]!=after[key]}
with override_settings(BOS_DATA_MODE='working',DEBUG=False,ANTHROPIC_API_KEY='',PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher']):
 f=SweepFixtures('operations.test_access');f.build();assert not f.issues,f.issues
 client=f.client('ceo');kw={'HTTP_X_CSRFTOKEN':client.cookies[settings.CSRF_COOKIE_NAME].value}
 for label,p,r in [('import',f.c03_import_proposal,f.c03_import_receipt)]+[(c,f.c03_proposals[c],f.c03_receipts[c]) for c in ('EUR','USD','UAH','salary')]:
  before=snapshot(f);response=client.post('/api/operations/confirm/',{'proposal_id':p['id'],'confirmed':True},content_type='application/json',**kw);after=snapshot(f)
  rows.append({'label':label,'method':'confirm','status':response.status_code,'literal_receipt_equal':response.json()==r,'delta':delta(before,after)})
 for label,payload in [('import',f.c03_import_payload),('EUR',f.c03_payloads['EUR'])]:
  before=snapshot(f);response=client.post('/api/erp/preview/',payload,content_type='application/json',**kw);after=snapshot(f)
  data=response.json();rows.append({'label':label,'method':'preview','status':response.status_code,'no_change':data.get('state')=='no_change' and data.get('id') is None,'delta':delta(before,after)})
report={'scope':'Only failed replay control diagnostic; actual 5 same-ID confirms + 2 no-change previews, all business model row values compared; no fullgate','source_root':str(root),'db':str(db),'rows':rows,'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['scripts/check_access.py','operations/service.py','erp/service.py','finance/statements.py']}}
output.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n');connection.close()
print(json.dumps([{'label':r['label'],'method':r['method'],'status':r['status'],'changed_models':list(r['delta'])} for r in rows]))
