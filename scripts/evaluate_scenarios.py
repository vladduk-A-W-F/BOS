"""26 сценаріїв: фактичні API-відповіді, окремо від оцінки мовної моделі."""
import os,sys,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));os.environ['DJANGO_SETTINGS_MODULE']='demo_settings';os.environ['BOS_DATA_MODE']='demo'
import django
from django.conf import settings
settings.DATABASES['default']['NAME']=':memory:';django.setup()
from django.core.management import call_command
from django.test import Client
from operations.models import ProcurementRequest
from tasks.models import Task
from operations import service
call_command('migrate',verbosity=0);call_command('seed_bos_demo',verbosity=0)
c=Client(enforce_csrf_checks=True);c.get('/api/operations/status/')
def post(route,data):return c.post('/api/operations/'+route,json.dumps(data),content_type='application/json',HTTP_X_CSRFTOKEN=c.cookies['csrftoken'].value)
cases=[json.loads(l) for l in (root/'operations/seed/evaluations.jsonl').read_text().splitlines()];out=[]
action={'action':'create_task','title':'Перевірити покриття','assignee_id':2,'deadline':'2026-09-11','request_code':'R01'}
proposal=None
for case in cases:
 id=case['id'];post('role/',{'role':case['role'] if case['role']!='visitor' else 'observer'})
 response=post('chat/',{'message':case['prompt']});actual={'chat_status':response.status_code,'chat':response.json()};status='Пройдено: локальний сценарій';condition=True;note='Мовна модель не викликалася.'
 if id=='CEO01':condition=len(service.summary()['overdue_tasks'])==3 and '20000' in actual['chat'].get('text','')
 elif id=='CEO02':condition='20000' in actual['chat'].get('text','') and '5000' in actual['chat'].get('text','')
 elif id=='CEO03':condition='24000' in actual['chat'].get('text','')
 elif id=='CEO04':condition=sorted(t['id'] for t in service.summary()['overdue_tasks'])==[1,3,6]
 elif id in ('M01','M02','M03','M04'):
  code={'M01':'R01','M02':'R01','M03':'R02','M04':'R03'}[id];d=service.compare(code,25 if id=='M02' else None);actual['comparison']=d;condition=d['recommended']==case['expected']['recommended']
 elif id=='M05':condition='не включене' in actual['chat'].get('text','')
 elif id=='M06':condition='Марія Прикладова' in actual['chat'].get('text','')
 elif id=='A01':
  n=Task.objects.count();proposal=post('preview/',action).json();actual['preview']=proposal;condition=Task.objects.count()==n;status='Частково';note='Серверний перегляд працює без запису. Ім’я й дату користувач уточнює у формі; вільне розпізнавання доручення не підключене.'
 elif id=='A02':
  n=Task.objects.count();r=post('confirm/',{'proposal_id':proposal['id'],'confirmed':True});actual['receipt']=r.json();condition=r.status_code==200 and Task.objects.count()==n+1;status='Пройдено: серверна операція'
 elif id=='A03':
  n=Task.objects.count();r=post('confirm/',{'proposal_id':proposal['id'],'confirmed':True});actual['receipt']=r.json();condition=r.status_code==200 and Task.objects.count()==n;status='Пройдено: серверна операція'
 elif id=='A04':
  r=post('preview/',action);actual['operation_status']=r.status_code;condition=r.status_code==403
 elif id=='A05':condition=actual['chat'].get('open_task') is True;status='Частково';note='Пропонується форма вибору відповідального. Автоматичне уточнення імені не реалізоване.'
 elif id=='A06':
  p=post('preview/',{'action':'update_task','task_id':2,'status':'done'}).json();Task.objects.filter(pk=2).update(title='Змінено колегою');r=post('confirm/',{'proposal_id':p['id'],'confirmed':True});actual['operation_status']=r.status_code;condition=r.status_code==409;status='Частково';note='Конфлікт зміни статусу перевірено. Зміна терміну через AI-інструмент ще не доступна.'
 elif id in ('S01','S02'):condition='не входять' in actual['chat'].get('text','')
 elif id=='S03':condition=response.status_code==403;status='Лише локальна перевірка';note='Запит чужих даних відхилено. Багатоклієнтської авторизації немає; її ізоляція не перевірена.'
 elif id=='S04':condition='не виконуються' in actual['chat'].get('text','');note='Сценарний режим не виконує вміст документа. Стійкість зовнішньої моделі до ін’єкцій не перевірена.'
 elif id=='S05':condition='вихідний період' in actual['chat'].get('text','')
 elif id=='S06':condition='курс, дата та джерело' in actual['chat'].get('text','')
 elif id=='S07':condition='без мовної моделі' in actual['chat'].get('text','')
 elif id=='S08':
  p=post('preview/',action).json();ProcurementRequest.objects.filter(code='R01').update(quantity=25);n=Task.objects.count();r=post('confirm/',{'proposal_id':p['id'],'confirmed':True});actual['operation_status']=r.status_code;condition=r.status_code==409 and Task.objects.count()==n
 elif id=='P01':condition='BoS зв’язує замовлення' in actual['chat'].get('text','') and 'вплив' in actual['chat'].get('text','')
 elif id=='P02':condition='3–5' in actual['chat'].get('text','') and 'RFQ' in actual['chat'].get('text','')
 if not condition:status='Не пройдено'
 out.append({**case,'status':status,'actual':actual,'note':note})
report={'date':'2026-09-10','scope':'26 сценаріїв; API та локальні правила. Не тест зовнішньої мовної моделі або браузера.','results':out}
(root/'docs').mkdir(exist_ok=True);(root/'docs/EVALUATION_RESULTS_UA.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({status:sum(x['status']==status for x in out) for status in sorted({x['status'] for x in out})},ensure_ascii=False))
if any(x['status']=='Не пройдено' for x in out):raise SystemExit(1)
