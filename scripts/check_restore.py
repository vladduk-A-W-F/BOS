"""Gate 7: owned actual TLS -> fenced native backup -> NEW install/restore -> TLS.

Only this command's synthetic installation is populated. No existing database,
media root or live installation can be selected as a source by CLI arguments.
All secrets and private payload remain in the newly created private workdir.
"""
import argparse
from pathlib import Path
import hashlib,http.client,json,os,secrets,ssl,subprocess,sys,tempfile,uuid
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from boss_project.version import VERSION
from fixtures.synthetic.table_inventory import B03_TABLES, C03_TABLES
from scripts.restore_corrections_fixture import populate as populate_corrections, verify_restored as verify_restored_corrections
from scripts.restore_tasks_fixture import populate as populate_tasks, verify_restored as verify_restored_tasks
from scripts.restore_statements_fixture import populate as populate_statements, verify_restored as verify_restored_statements
from scripts import install_server as installer
from scripts.package_server import package
from scripts.provision_runtime import provision_install
from scripts.lifecycle_server import load_owned,child_environment
from scripts.maintenance_control import ManagedSupervisor
from scripts.generation_ledger import GenerationLedger
from scripts.backup_server import capture_backup,inspect_backup,inventory
from scripts.restore_server import restore_new
from scripts.managed_runtime import BoSRuntime
from scripts.check_install import port

SEED = r'''

import django,json,sys,uuid,hashlib
from decimal import Decimal
from datetime import date
from pathlib import Path
django.setup()
from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group,Permission
from django.contrib.sessions.models import Session
from employees.models import Employee
from finance.models import Counterparty,Transaction
from finance.commands import save_transaction
from operations.models import Document
from operations.private_storage import private_document_storage
assert not any(m.objects.exists() for m in apps.get_models() if m._meta.app_label in {'operations','erp','finance','employees','branches','tasks','ai_assistant'})
assert not get_user_model().objects.exists()
password=json.load(sys.stdin)['password']
u=get_user_model().objects.create_user('restore-ceo',password=password)
u.groups.add(Group.objects.get_or_create(name='ceo')[0])
u.user_permissions.add(*Permission.objects.filter(content_type__app_label='operations',codename__in=['view_document','download_document','export_workspace']))
employee=Employee.objects.create(full_name='Тестова особа відновлення',role='Керівник',user=u)
# C01 additions belong only to this new synthetic company.
from tasks.models import Task
second_employee=Employee.objects.create(full_name='Тестова друга особа відновлення',role='Менеджер')
legacy_tasks=[Task.objects.create(title='Історичне відкрите доручення',assignee='Історичний виконавець',status='active',deadline=date(2026,9,10)),
              Task.objects.create(title='Історичне завершене доручення',assignee='Історичний виконавець',status='done',priority='low',deadline=date(2026,9,10))]
party=Counterparty.objects.create(name='Синтетичний контрагент',type='customer')
ids=[]
for currency,value in [('EUR','17.39'),('USD','123.45'),('UAH','9801.07')]:
 row=save_transaction(changes={'direction':'in','amount':Decimal(value),'currency':currency,'date':date(2026,9,12),'description':'Тест резервної копії','category':'customer','counterparty':party},actor=u,operation_id=str(uuid.uuid4()))
 ids.append(row.pk)
blob=b'\x00\xffBoS synthetic original\r\n'
with transaction.atomic(durable=True):
 receipt=private_document_storage.save_verified(blob,hashlib.sha256(blob).hexdigest(),legacy_blob_bytes=0)
 document=Document.objects.create(code='RESTORE-001',revision='A',title='Тестовий оригінал',filename='test.bin',original_file=receipt.name,size=len(blob),content=b'',checksum=receipt.checksum,status='reviewed')
private_document_storage.finalize(receipt)
legacy=b'Legacy synthetic\x00\xff'
Document.objects.create(code='RESTORE-002',revision='B',title='Тестовий BLOB',content=legacy,size=len(legacy),checksum=hashlib.sha256(legacy).hexdigest())
# Additional B02 source; the original two documents and their bytes stay intact.
import_blob=b'BoS synthetic approved import source\r\n'
with transaction.atomic(durable=True):
 import_file=private_document_storage.save_verified(import_blob,hashlib.sha256(import_blob).hexdigest(),legacy_blob_bytes=0)
 import_document=Document.objects.create(code='RESTORE-IMPORT',revision='A',title='Синтетична підстава імпорту',filename='import.txt',original_file=import_file.name,size=len(import_blob),content=b'',checksum=import_file.checksum,status='approved')
private_document_storage.finalize(import_file)
extra=Path(settings.MEDIA_ROOT)/'orphan.bin';extra.write_bytes(b'orphan retained');extra.chmod(0o600)
# This intentionally creates session history using the actual backend.
from django.contrib.sessions.backends.db import SessionStore
session=SessionStore();session['synthetic']='retained';session.save()
print(json.dumps({'user_id':u.pk,'counterparty_id':party.pk,'employee_id':employee.pk,'second_employee_id':second_employee.pk,'legacy_task_ids':[t.pk for t in legacy_tasks],'document_id':document.pk,'import_document':{'document_id':import_document.pk,'code':import_document.code,'revision':import_document.revision,'checksum':import_document.checksum},'transaction_ids':ids,'currencies':3,'amounts':['17.39','123.45','9801.07'],'stored_session_rows':Session.objects.count()}))

'''

def main():
    if not __debug__:
        print('Assert вимкнено: приймання заборонено.');return 2
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    import shutil
    prerequisites={'BOS_SERVER_WHEELHOUSE':os.environ.get('BOS_SERVER_WHEELHOUSE'),
                   'BOS_CADDY_BIN':os.environ.get('BOS_CADDY_BIN'),'openssl':shutil.which('openssl')}
    missing=[name for name,value in prerequisites.items() if not value]
    if missing:
        result={'gate':7,'complete':False,'status':'НЕ ЗАПУЩЕНО','reason':'Відсутні prerequisites: '+', '.join(missing)}
        if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False));return 2
    wheelhouse=Path(prerequisites['BOS_SERVER_WHEELHOUSE']).absolute();caddy=Path(prerequisites['BOS_CADDY_BIN']).absolute()
    work=Path(tempfile.mkdtemp(prefix='bos-restore-check-'));work.chmod(0o700)
    target,registry=work/'company',work/'registry'
    chosen=set()
    while len(chosen)<4:chosen.add(port())
    https_port,http_port,restore_https_port,restore_http_port=sorted(chosen)
    origin=f'https://localhost:{https_port}';restore_origin=f'https://localhost:{restore_https_port}'
    report={'gate':7,'complete':False,'version':VERSION,'synthetic_work':str(work),
        'scope':'actual same-N TLS, capture, clean restore and restored HTTPS; no upgrade/rollback or Windows/PG',
        'checks':[], 'management_code_sha256':{name:hashlib.sha256((ROOT/'scripts'/(name+'.py')).read_bytes()).hexdigest() for name in ('maintenance_control','generation_ledger','backup_server','restore_server','managed_runtime')}}
    report_path=args.output or work/'report.json'
    def save():
        report_path.parent.mkdir(parents=True,exist_ok=True)
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    def check(case,**data):
        report['checks'].append({'case':case,'passed':True,**data});save()
    save()
    try:
        report['package']=package(ROOT,work/'package')
        installed=provision_install(installer=installer,target=target,registry=registry,source_root=work/'package',origin=origin,wheelhouse=wheelhouse)
        state={'installation_id':installed['installation_id'],'password':'BoS_private_'+secrets.token_urlsafe(24)}
        _,release,python,config=load_owned(installer,target=target,registry=registry,installation_id=state['installation_id'])
        seeded=subprocess.run([str(python),'-B','-c',SEED],cwd=release,env=child_environment(config),input=json.dumps({'password':state['password']}),text=True,capture_output=True,timeout=60)
        if seeded.returncode:raise RuntimeError('SYNTHETIC_SEED_FAILED')
        report['seed']=json.loads(seeded.stdout)
        check('fresh_offline_install_and_independent_three_currency_fixture')
    except BaseException as exc:
        report['error_type']=type(exc).__name__;report['reason']='Чиста синтетична установка не завершена.';save();print(json.dumps(report,ensure_ascii=False));return 1

    class HTTPS:
     def __init__(self,origin):self.origin=origin;self.port=urlsplit(origin).port;self.cookies={};self.ctx=ssl.create_default_context(cafile=str(work/'localhost.crt'))
     def request(self,method,path,payload=None):
      headers={'Host':f'localhost:{self.port}','Origin':self.origin}
      if self.cookies:headers['Cookie']='; '.join(k+'='+v for k,v in self.cookies.items())
      if payload is not None:
       payload=json.dumps(payload).encode();headers['Content-Type']='application/json';headers['X-CSRFToken']=self.cookies.get('csrftoken','')
      conn=http.client.HTTPSConnection('localhost',self.port,context=self.ctx,timeout=10)
      try:
       conn.request(method,path,body=payload,headers=headers);r=conn.getresponse();body=r.read()
       for k,v in r.getheaders():
        if k.lower()=='set-cookie':self.cookies.update({n:m.value for n,m in SimpleCookie(v).items()})
       return r.status,body
      finally:conn.close()
     def login(self):
      assert self.request('GET','/api/auth/csrf/')[0]==200
      assert self.request('POST','/api/auth/login/',{'username':'restore-ceo','password':state['password']})[0]==200
      assert self.request('GET','/api/tasks/')[0]==200
      return sorted(k for k in self.cookies if k.startswith('bos_session_'))
    ledger=None
    try:
     cert=work/'localhost.crt';key=work/'localhost.key'
     p=subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','2','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],capture_output=True,text=True,timeout=20)
     assert p.returncode==0;key.chmod(0o600)
     def adapter(bundle,recordid,http_port):return BoSRuntime(installer=installer,target=bundle,registry=registry,installation_id=recordid,caddy=caddy,certificate=cert,private_key=key,http_port=http_port,ca_certificate=cert,emit=lambda e:None)
     factory=GenerationLedger.create
     ledger=factory(installer=installer,target=target,registry=registry,installation_id=state['installation_id'])
     runtime=adapter(target,state['installation_id'],http_port)
     with ManagedSupervisor(installer=installer,target=target,registry=registry,installation_id=state['installation_id'],start_callback=runtime,drain_timeout=15) as owner:
      owner.start();client=HTTPS(origin);source_cookie_names=client.login()
      code,original_document=client.request('GET','/api/operations/documents/1/download/')
      assert code==200,(code,original_document[:100])
      check('original_real_TLS_login_document',document_sha256=hashlib.sha256(original_document).hexdigest())
      status,body=client.request('GET','/api/erp/import/template/?format=json&owner_id='+str(report['seed']['employee_id']))
      assert status==200,(status,body[:200])
      import_package=json.loads(body)
      for row in import_package['rows']:
       if row['entity']=='purchase_open_balance':row['source_documents']={'specification':report['seed']['import_document']}
      status,body=client.request('POST','/api/erp/import/preview/',import_package)
      assert status==200,(status,body[:400])
      preview=json.loads(body);assert preview['valid'] and preview['counts']['create']==len(import_package['rows'])
      status,body=client.request('POST','/api/operations/confirm/',{'proposal_id':preview['proposal']['id'],'confirmed':True})
      assert status==200,(status,body[:400])
      import_receipt=json.loads(body);assert import_receipt['state']=='succeeded'
      assert all(row['target_id'] for row in import_receipt['mappings'])
      import_url='/api/erp/import/batches/'+import_package['batch_id']+'/export/'
      status,original_import_export=client.request('GET',import_url);assert status==200
      assert json.loads(original_import_export)['first_commit_receipt']==import_receipt
      check('actual_TLS_import_populated_ledger_and_source_document',batch_id=import_package['batch_id'],mapping_count=len(import_receipt['mappings']),export_sha256=hashlib.sha256(original_import_export).hexdigest())
      # Tasks are part of snapshot.home: populate before freezing the existing B03 whole-snapshot oracle.
      task_proof=populate_tasks(client,import_receipt,report['seed'])
      check('actual_TLS_tasks_FK_result_archive_and_history',tasks=len(task_proof['ids']),receipts=len(task_proof['records']),state_sha256=task_proof['state_sha256'])
      # C03 financial effects precede the unchanged B03 full snapshot oracle.
      statement_proof=populate_statements(client,import_receipt,report['seed'])
      check('actual_TLS_statements_three_currencies_create_link_and_allocate',lines=len(statement_proof['line_ids']),state_sha256=statement_proof['state_sha256'],source_sha256=statement_proof['source_sha256'])
      correction_proof=populate_corrections(client,import_receipt,report['seed'])
      check('actual_TLS_six_populated_correction_ledgers',counts=correction_proof['counts'],snapshot_sha256=correction_proof['snapshot_sha256'])
      lease=owner.quiesce(str(uuid.uuid4()))
      original_db=hashlib.sha256((target/'state/data/bos.sqlite3').read_bytes()).hexdigest()
      original_media=inventory(installer,target/'state/private')
      backup=work/'backup'
      result=capture_backup(ledger=ledger,lease=lease,destination=backup)
      manifest=inspect_backup(installer=installer,source=backup)
      assert B03_TABLES.issubset(set(manifest['proof']['logical']['tables'])) and len(B03_TABLES)==53
      assert set(manifest['proof']['logical']['tables'])==C03_TABLES
      assert len(manifest['proof']['logical']['tables'])==56
      assert hashlib.sha256((target/'state/data/bos.sqlite3').read_bytes()).hexdigest()==original_db
      assert inventory(installer,target/'state/private')==original_media
      check('actual_quiescence_native_capture',**{k:v for k,v in result.items() if k!='complete'})
      # Read-only corrupt-copy test uses a separate new copy, never the source backup.
      import shutil
      corrupt=work/'corrupt-backup';shutil.copytree(backup,corrupt);corrupt.chmod(0o700)
      with (corrupt/'database.sqlite3').open('ab') as stream:stream.write(b'corrupt')
      refused=False
      try:inspect_backup(installer=installer,source=corrupt)
      except ValueError:refused=True
      assert refused;check('corrupt_backup_refused')
      refused=False
      try:restore_new(installer=installer,source=backup,target=target,registry=registry,origin=restore_origin,wheelhouse=wheelhouse)
      except ValueError:refused=True
      assert refused and hashlib.sha256((target/'state/data/bos.sqlite3').read_bytes()).hexdigest()==original_db
      check('existing_installation_restore_refused_without_writes')
      restored=restore_new(installer=installer,source=backup,target=work/'restored-company',registry=registry,origin=restore_origin,wheelhouse=wheelhouse)
      check('new_installation_native_restore',**{k:v for k,v in restored.items() if k!='complete'})
      # Release resumes exactly the original N; this cannot activate another generation.
      lease.release();assert owner.state=='running'
      check('original_same_N_resumed',health=runtime.ready['health'])
     restored_target=work/'restored-company';restored_id=restored['installation_id'];restored_runtime=adapter(restored_target,restored_id,restore_http_port)
     with ManagedSupervisor(installer=installer,target=restored_target,registry=registry,installation_id=restored_id,start_callback=restored_runtime,drain_timeout=15) as owner:
      owner.start();client=HTTPS(restore_origin);restored_cookie_names=client.login()
      assert restored_cookie_names!=source_cookie_names
      code,document=client.request('GET','/api/operations/documents/1/download/')
      assert code==200 and document==original_document
      code,runtime_data=client.request('GET','/api/runtime/status/');assert code==200 and json.loads(runtime_data)['version']==VERSION
      check('restored_real_TLS_login_document_and_version',new_cookie_namespace=True,document_sha256=hashlib.sha256(document).hexdigest(),version=VERSION)
      status,restored_import_export=client.request('GET',import_url)
      assert status==200 and restored_import_export==original_import_export
      status,before_replay_snapshot=client.request('GET','/api/erp/snapshot/');assert status==200
      status,body=client.request('POST','/api/erp/import/preview/',import_package)
      assert status==200,(status,body[:400])
      repeated=json.loads(body);assert repeated['counts']['create']==0 and repeated['first_commit_receipt']==import_receipt
      assert repeated['live_before']==repeated['projected_after']
      status,body=client.request('POST','/api/operations/confirm/',{'proposal_id':repeated['proposal']['id'],'confirmed':True})
      assert status==200 and json.loads(body)==import_receipt
      status,after_replay_snapshot=client.request('GET','/api/erp/snapshot/')
      assert status==200 and json.loads(after_replay_snapshot)==json.loads(before_replay_snapshot)
      status,export_after_replay=client.request('GET',import_url)
      assert status==200 and export_after_replay==original_import_export
      status,restored_source=client.request('GET','/api/operations/documents/'+str(report['seed']['import_document']['document_id'])+'/download/')
      assert status==200 and hashlib.sha256(restored_source).hexdigest()==report['seed']['import_document']['checksum']
      check('restored_import_receipt_identity_replay_and_private_source',export_sha256=hashlib.sha256(restored_import_export).hexdigest(),no_new_business_effects=True)
      restored_corrections=verify_restored_corrections(client,correction_proof)
      check('restored_six_correction_ledgers_source_history_and_intent_replay',**restored_corrections)
      restored_statements=verify_restored_statements(client,statement_proof)
      check('restored_statements_exact_source_ledgers_three_currencies_and_receipts',**restored_statements)
      restored_tasks=verify_restored_tasks(client,task_proof)
      check('restored_Task_legacy_NULL_FK_result_archive_history_and_owner_receipts',**restored_tasks)
      owner.quiesce(str(uuid.uuid4()))
     check('all_owned_processes_stopped_and_source_backup_still_valid',backup_manifest_sha256=hashlib.sha256((backup/'MANIFEST.json').read_bytes()).hexdigest())
     inspect_backup(installer=installer,source=backup)
     # Inject a final owned-resource admission failure only in another NEW restore.
     from unittest.mock import patch
     from scripts import lifecycle_server as baseline
     original_load=baseline.load_owned; admission_calls=[]
     def fail_final(*args,**kwargs):
      admission_calls.append(1)
      if len(admission_calls)==2:raise OSError('synthetic final admission failure')
      return original_load(*args,**kwargs)
     failed_target=work/'late-failed-restore';refused=False
     with patch.object(baseline,'load_owned',fail_final):
      try:restore_new(installer=installer,source=backup,target=failed_target,registry=registry,origin=restore_origin,wheelhouse=wheelhouse)
      except OSError:refused=True
     failed_record=next(r for r in installer.InstallerRegistry(registry).records() if r['root']==str(failed_target))
     assert refused and len(admission_calls)==2
     assert failed_record['runtime']['application_provisioned'] is False
     assert failed_record['runtime']['restore']['complete'] is False
     check('late_admission_failure_keeps_new_target_unlaunchable')
     report['complete']=True;save()
     print(json.dumps(report,ensure_ascii=False));return 0
    except BaseException as exc:
     report['error_type']=type(exc).__name__;report['reason']='Перевірка не завершена; див. останній успішний сценарій.';save();print(json.dumps(report,ensure_ascii=False));return 1

if __name__=='__main__':raise SystemExit(main())
