"""Independent A06 spot checks: actual HTTP, native admin and synthetic SQLite only."""
import json,os,sys
from pathlib import Path
from html.parser import HTMLParser
from decimal import Decimal
root=Path('/workspace/sites/bos-original-refined')
sys.path[:0]=[str(root),str(root/'scripts')]
os.environ['DJANGO_SETTINGS_MODULE']='demo_settings'
os.environ['BOS_DATA_MODE']='demo'
os.environ['BOS_TEST_DB_NAME']=':memory:'
os.environ['BOS_TEST_MEDIA']='/workspace/scratch/c7b51e996a9f/tmp/a06_review_media'
os.environ['BOS_TEST_DEPENDENCIES']='/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages'
from django.conf import settings
from check_support import configure,login_test_client
configure(settings)
import django
django.setup()
from django.core.management import call_command
from django.test import Client
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from finance.models import Transaction,Salary,FinancialIntent
from finance.commands import save_transaction
from operations.models import AuditEvent
from employees.models import Employee
call_command('migrate',verbosity=0,interactive=False)
checks=[]
def check(name,value):
 assert value,name
 checks.append(name)
def post(c,path,data,key=None,csrf=True):
 headers={'HTTP_X_CSRFTOKEN':c.cookies['csrftoken'].value} if csrf else {}
 if key is not None:headers['HTTP_IDEMPOTENCY_KEY']=key
 return c.post(path,data,content_type='application/json',**headers)
c=Client(enforce_csrf_checks=True);user=login_test_client(c)
tx={'direction':'in','amount':'100.20','currency':'EUR','date':'2026-09-11','description':'A06 independent synthetic','category':'customer'}
first=post(c,'/api/transactions/',tx,'probe-transaction')
check('HTTP initial create',first.status_code==201)
pk=first.json()['id']
same=post(c,'/api/transactions/',{**tx,'amount':'100.2'},'probe-transaction')
check('canonical numeric replay returns same source',same.status_code==201 and same.json()['id']==pk and Transaction.objects.count()==1)
conflict=post(c,'/api/transactions/',{**tx,'description':'Different business purpose'},'probe-transaction')
check('same key changed description rejects without write',conflict.status_code==409 and Transaction.objects.count()==1 and AuditEvent.objects.filter(action='transaction.create').count()==1)
missing=post(c,'/api/transactions/',tx)
check('no-key HTTP create rejected',missing.status_code==400 and Transaction.objects.count()==1)
no_csrf=post(c,'/api/transactions/',tx,'probe-transaction',False)
check('HTTP replay still requires CSRF',no_csrf.status_code==403 and Transaction.objects.count()==1)
current=save_transaction(instance=Transaction.objects.get(pk=pk),changes={'description':'Current approved description'},actor=user)
replay=post(c,'/api/transactions/',tx,'probe-transaction')
check('replay returns current source, not restoring original payload',replay.status_code==201 and replay.json()['id']==pk and replay.json()['description']=='Current approved description')
other=Client(enforce_csrf_checks=True);other_user=login_test_client(other)
second=post(other,'/api/transactions/',tx,'probe-transaction')
check('same token other actor creates independent source',second.status_code==201 and second.json()['id']!=pk and Transaction.objects.count()==2)
user.groups.set([Group.objects.get_or_create(name='manager')[0]])
revoked=post(c,'/api/transactions/',tx,'probe-transaction')
check('role revoked before replay returns 403',revoked.status_code==403 and Transaction.objects.count()==2)

class Inputs(HTMLParser):
 def __init__(self,html):super().__init__();self.values={};self.feed(html)
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='input' and attrs.get('name'):self.values[attrs['name']]=attrs.get('value','')

User=get_user_model()
technical=User.objects.create_superuser('a06-independent-admin','','synthetic-only-Password-472!')
admin=Client(enforce_csrf_checks=True)
admin.get('/admin/login/')
login=admin.post('/admin/login/',{'username':technical.username,'password':'synthetic-only-Password-472!','next':'/admin/'},HTTP_X_CSRFTOKEN=admin.cookies['csrftoken'].value)
check('technical admin native login',login.status_code==302)
employee=Employee.objects.create(full_name='Synthetic A06 independent employee')
url='/admin/finance/salary/add/'
response=admin.get(url)
check('native salary form readable',response.status_code==200)
token=Inputs(response.content.decode()).values['bos_operation_id']
data={'employee':employee.pk,'amount':'125.20','currency':'USD','period_year':'2026','period_month':'10','status':'pending','payment_date':'','transaction':'','notes':'','bos_operation_id':token,'_save':'Зберегти'}
before_intents=FinancialIntent.objects.count()
for i in range(2):
 response=admin.post(url,data,HTTP_X_CSRFTOKEN=admin.cookies['csrftoken'].value)
 check('native salary '+('first submit' if i==0 else 'same-token replay'),response.status_code==302 and Salary.objects.count()==1)
check('native replay preserves one receipt',FinancialIntent.objects.count()==before_intents+1)
salary=Salary.objects.get();salary.mark_paid('2026-09-11')
before=Salary.objects.values().get(pk=salary.pk)
reply=admin.post(url,data,HTTP_X_CSRFTOKEN=admin.cookies['csrftoken'].value)
check('native accrual replay after pay preserves paid source and ledger',reply.status_code==302 and Salary.objects.count()==1 and Salary.objects.values().get(pk=salary.pk)==before and Transaction.objects.count()==3)
reply=admin.post(url,data)
check('native replay does not bypass CSRF',reply.status_code==403 and Salary.objects.count()==1)
reply=admin.post(url,{**data,'amount':'126.20'},HTTP_X_CSRFTOKEN=admin.cookies['csrftoken'].value)
check('native replay payload mismatch rejected',reply.status_code==409 and Salary.objects.values().get(pk=salary.pk)==before)
User.objects.filter(pk=technical.pk).update(is_staff=False)
reply=admin.post(url,data,HTTP_X_CSRFTOKEN=admin.cookies['csrftoken'].value)
check('native replay rechecks staff permission',reply.status_code==302 and '/admin/login/' in reply['Location'] and Salary.objects.count()==1)
Path('/workspace/scratch/c7b51e996a9f/tmp/a06_intent_repro_result.json').write_text(json.dumps({'passed':len(checks),'checks':checks,'database':'synthetic in-memory SQLite','money_sources':Transaction.objects.count(),'salary_sources':Salary.objects.count(),'receipts':FinancialIntent.objects.count(),'postgres':'not run'},ensure_ascii=False,indent=2))
print(json.dumps({'passed':len(checks),'checks':checks},ensure_ascii=False))
