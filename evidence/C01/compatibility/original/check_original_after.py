import os,sys,re,json,hashlib,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));os.environ['DJANGO_SETTINGS_MODULE']='demo_settings'
from django.conf import settings
from check_support import configure, prove_database, login_test_client
configure(settings)
import django
django.setup();prove_database()
from django.core.management import call_command
from django.test import Client
call_command('migrate',verbosity=0)
c=Client(enforce_csrf_checks=True);login_test_client(c,capabilities=('view_document','download_document','export_workspace'));c.get('/api/operations/status/');checks=[];additional_checks=[]
def test(label,condition):
 assert condition,label
 checks.append(label)
def extra(label,condition):
 assert condition,label
 additional_checks.append(label)
for route in ['/','/assets/app.js','/api/tasks/','/api/employees/','/api/branches/','/api/counterparties/','/api/contracts/','/api/transactions/','/api/salaries/','/api/dashboard/summary/','/api/dashboard/helicopter/','/api/runtime/status/']:
 r=c.get(route);test(route,r.status_code==200);r.close()
def post(route,data):return c.post(route,json.dumps(data),content_type='application/json',HTTP_X_CSRFTOKEN=c.cookies['csrftoken'].value)
e=post('/api/employees/',{'full_name':'Тестова особа','role':'Менеджер','department':'Операції','kpi':80});test('employee create',e.status_code==201)
from operations.service import as_of
from datetime import timedelta
payload={'action':'create_task','title':'Перевірити пропозицію','assignee_id':e.json()['id'],'priority':'medium','deadline':str(as_of()+timedelta(days=5)),'category':'Загальне'}
p=post('/api/operations/preview/',payload);extra('quick task preview',p.status_code==200)
t=post('/api/operations/confirm/',{'proposal_id':p.json()['id'],'confirmed':True});test('quick task contract',t.status_code==200)
pk=t.json()['task_id'];test('task saved',c.get(f'/api/tasks/{pk}/').json()['title']=='Перевірити пропозицію')
p=post('/api/operations/preview/',{'action':'update_task','task_id':pk,'status':'done','result':'Фактично перевірено пропозицію','reason':'Підтверджено результат виконавця'});extra('task edit preview',p.status_code==200)
r=post('/api/operations/confirm/',{'proposal_id':p.json()['id'],'confirmed':True});test('task edit',r.status_code==200 and c.get(f'/api/tasks/{pk}/').json()['status']=='done')
test('empty title rejected',post('/api/operations/preview/',{**payload,'title':''}).status_code==422)
extra('raw task bypass denied',post('/api/tasks/',{'title':'Не погоджено'}).status_code==403)
test('task search',len(c.get('/api/tasks/?search=пропозицію').json())==1)
test('AI status honest',c.get('/api/runtime/status/').json()['ai_configured'] is False)
test('AI missing key controlled',post('/api/chat/',{'message':'test'}).status_code==503)
test('asset traversal blocked',c.get('/assets/settings.py').status_code==404)
test('local only',c.get('/',REMOTE_ADDR='198.51.100.1').status_code==403)
root=Path(__file__).resolve().parents[1];html=(root/'frontend/boss_app_html.html').read_text();src=(root/'frontend/boss_app_source.html').read_text()
test('local scripts',not re.search(r'<script[^>]+src="https?://',html))
test('all original sections',all("id:'"+key+"'" in src for key in ['heli','dash','finance','hr','organizer','ai','info','settings']))
test('no replacement workbench','local_ops' not in settings.INSTALLED_APPS)
test('keyboard search and native dialog',"e.ctrlKey||e.metaKey" in src and 'function ControlledTask(' in src and '<dialog ref={ref} className="bos-dialog c01-dialog"' in src and 'onCancel={e=>' in src)
test('organizer persistence',all("bos.original."+name+".v1" in src for name in ['notes','schedule','settings']))
def lum(h):
 v=[int(h[i:i+2],16)/255 for i in (1,3,5)];v=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in v];return sum(a*b for a,b in zip(v,[.2126,.7152,.0722]))
ratios={}
for name,fg,bg in [('main','#F4F6F8','#171A21'),('muted','#9AA1AC','#1E222B'),('dim','#A7B1BF','#1E222B'),('primary','#0A0C10','#93C5FD'),('error','#FCA5A5','#171A21')]:
 a,b=sorted([lum(fg),lum(bg)],reverse=True);ratio=(a+.05)/(b+.05);ratios[name]=round(ratio,2);test('contrast '+name,ratio>=4.5)
print(json.dumps({'passed':len(checks),'checks':checks,'additional_passed':len(additional_checks),'additional_checks':additional_checks,'palette_contrast':ratios,'not_tested':['browser layout and keyboard end-to-end','Windows execution','external AI','all WCAG criteria']},ensure_ascii=False,indent=2))
