"""Read saved evidence only; does not run tests or touch databases."""
from pathlib import Path
import hashlib, json

r=Path('/workspace/sites/bos-original-refined'); e=r/'evidence/D03'; f=e/'verify-1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def last(name):
 s=(f/name).read_text(); dec=json.JSONDecoder(); objects=[]
 for i,c in enumerate(s):
  if c=='{' and (i==0 or s[i-1]=='\n'):
   try:v,_=dec.raw_decode(s[i:])
   except ValueError:continue
   if isinstance(v,dict):objects.append(v)
 assert objects,name
 return objects[-1]
a=json.loads((e/'AFTER_FULL27.json').read_text());v=json.loads((f/'report.json').read_text())
assert a['report_sha256']==sha(f/'report.json')
assert a['source_sha256']==a['source_sha256_after']==v['source_sha256']=='833498c2aad1f0f2262fd74c664e315b874438b2d990bb425ad804d68ca7bac9'
assert json.loads((e/'PROCESS_EXIT.json').read_text())['exit_code']==1
assert not v['complete'] and v['source_databases_unchanged'] and a['source_unchanged']
assert a['source_databases']==json.loads((e/'BEFORE_FULL27.json').read_text())['source_databases']
assert v['environment']['system']=='Linux' and v['environment']['python'].startswith('3.12.14')
assert [g['id'] for g in v['gates']]==list(range(1,12))
for i in [1,2,3,5,6]:assert v['gates'][i-1]['parts'][0]['status']=='ПРОЙДЕНО'
for i in [4,7]:assert v['gates'][i-1]['status']=='ПРОЙДЕНО'
assert a['django']=={'tests':571,'ok':True}
functional=0
for name,x in a['sqlite_functional'].items():
 assert x['checks']==x['expected'] and x['returncode']==0
 if name=='check_launcher.py':assert x['checks']==5
 else:functional+=x['checks']
assert functional==151
assert a['invariants']['complete'] and len(a['invariants']['results'])==5 and all(x['runs']==1000 for x in a['invariants']['results'])
access=a['access'];assert access['complete'] and access['failures']==0
assert access['counts']['http_passed']==9432 and access['counts']['redirect_http_responses']==9
assert access['field_tests']['executed']==57 and access['field_tests']['skipped']==access['field_tests']['failures']==0
c=a['concurrency'];assert c['complete'] and c['tests']['succeeded']==c['tests']['discovered']==109 and c['runner_failures']==0
assert c['erp_stdout']['required']==c['erp_stdout']['observed']==c['erp_stdout']['unique']==116
assert not c['erp_stdout']['missing'] and not c['erp_stdout']['duplicates']
raw5=last('gate-05-sqlite.log');assert raw5['erp_schema']['actual']==raw5['erp_schema']['required'] and len(raw5['erp_schema']['actual'])==35
g6=json.loads((f/'gate-06-actual.json').read_text()); assert g6['complete'] and g6['passed']==len(g6['checks'])==821 and g6['confirm_HTTP_calls']==42 and g6['source_sha256']==v['source_sha256']
assert a['gate7']['complete'] and a['gate7']['checks']==18 and not a['gate7']['failures']
raw7=last('gate-07-sqlite.log');restore=next(x for x in raw7['checks'] if x['case']=='new_installation_native_restore');assert restore['passed'] and restore['tables']==56 and restore['private_files']==4
assert not a['gate8']['complete'] and a['gate8']['checks']==31
failed=a['gate8']['failures'];assert len(failed)==1 and failed[0]['case']=='oversized_request_413_no_partial_document' and failed[0]['error_type']=='ConnectionResetError' and failed[0]['documents_and_private_bytes_unchanged']
assert json.loads((e/'D03_DOCS_BEFORE.json').read_text())['passed']==1
assert json.loads((e/'DOCS_AFTER.json').read_text())['passed']==15
assert json.loads((e/'ROLES_PDF_QA.json').read_text())['pages']==3
