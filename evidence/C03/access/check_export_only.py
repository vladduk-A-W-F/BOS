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

with override_settings(BOS_DATA_MODE='working',DEBUG=False,ANTHROPIC_API_KEY='',PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher']):
 f=SweepFixtures('operations.test_access');f.build();assert not f.issues,f.issues
 path=f'/api/statements/imports/{f.c03_import_id}/export/';row=next(r for r in catalogue() if r['name']=='statement-export');before=f.state_digest()
 response=f.client('ceo').get(path);leaks,size=response_oracle(response,row,path,'GET','ceo',f,'full')
 result={'status':response.status_code,'leaks':leaks,'bytes':size,'passed':response.status_code==200 and not leaks and f.state_digest()==before,'state_unchanged':f.state_digest()==before,'header':response.content.decode().splitlines()[0]}
report={'scope':'Only previous failed CEO export surface, stronger exact agreed CSV reference/status oracle; no fullgate','source_root':str(root),'db':str(db),'result':result,'source_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['scripts/access_fixtures.py','scripts/check_access.py','finance/statement_reads.py']}}
output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');connection.close();print(json.dumps(result));sys.exit(not result['passed'])
