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

import ast,inspect
selected=('statement_bound_transaction_protection','statement_exact_replay')
source=inspect.getsource(run_c03_controls);node=ast.parse(source).body[0]
original_calls=[item.value.args[0].value for item in node.body if isinstance(item,ast.Expr) and isinstance(item.value,ast.Call) and isinstance(item.value.func,ast.Name) and item.value.func.id=='run']
from check_access import C03_CONTROL_IDS
assert tuple(original_calls)==C03_CONTROL_IDS and len(original_calls)==12
# Select only two concrete failed controls; preserve each actual control body.
node.body=[item for item in node.body if not (isinstance(item,ast.Expr) and isinstance(item.value,ast.Call) and isinstance(item.value.func,ast.Name) and item.value.func.id=='run' and item.value.args[0].value not in selected)]
for item in node.body:
 if isinstance(item,ast.Assert):
  assert 'C03_CONTROL_IDS' in ast.unparse(item)
  item.test=ast.parse('tuple(row["id"] for row in results)=='+repr(selected),mode='eval').body
module=ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[]));namespace=dict(run_c03_controls.__globals__);exec(compile(module,'<actual-c03-controls-two-affected-only>','exec'),namespace)
with override_settings(BOS_DATA_MODE='working',DEBUG=False,ANTHROPIC_API_KEY='',PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher']):
 f=SweepFixtures('operations.test_access');f.build();assert not f.issues,f.issues
 results=namespace['run_c03_controls'](f,owner)
 path=f'/api/statements/imports/{f.c03_import_id}/export/';row=next(r for r in catalogue() if r['name']=='statement-export');before=f.state_digest()
 response=f.client('ceo').get(path);leaks,size=response_oracle(response,row,path,'GET','ceo',f,'full')
 export={'status':response.status_code,'leaks':leaks,'bytes':size,'passed':response.status_code==200 and not leaks and f.state_digest()==before,'state_unchanged':f.state_digest()==before,'header':response.content.decode().splitlines()[0]}
report={'scope':'Only 2 prior failed controls plus 1 CEO export surface; actual function source with top-level run selection; each nested assertion/request unchanged. No fullgate, no discovery shrink in shipped checker','source_root':str(root),'db':str(db),'selected':selected,'original_control_ids':original_calls,'results':results,'export':export,'counts':{'groups':len(results),'passed':sum(r['passed'] for r in results),'http':sum(len(r['http']) for r in results)},'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['scripts/access_fixtures.py','scripts/access_routes.json','scripts/check_access.py','operations/service.py','finance/statements.py','finance/statement_reads.py']}}
output.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n');connection.close();print(json.dumps(report['counts']));sys.exit(any(not r['passed'] for r in results) or not export['passed'])
