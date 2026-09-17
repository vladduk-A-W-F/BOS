"""Інтеграційні перевірки BoS. Лише тимчасова база в пам’яті; без мережі."""
import os,sys,json,io,hashlib,zipfile
from pathlib import Path
from datetime import timedelta
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));os.environ['DJANGO_SETTINGS_MODULE']='demo_settings';os.environ['BOS_DATA_MODE']='demo'
# Optional local dependency directory for offline CI; never installed or fetched here.
if os.environ.get('BOS_TEST_DEPENDENCIES'):sys.path.append(os.environ['BOS_TEST_DEPENDENCIES'])
import django
from django.conf import settings
from check_support import configure, prove_database, login_test_client
configure(settings)
django.setup();prove_database()
from django.core.management import call_command
from django.test import Client
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from operations.models import *
from tasks.models import Task
from employees.models import Employee
from operations import service
from decimal import Decimal
checks=[]
def test(name,condition):
    assert condition,name
    checks.append(name)
original_hash=hashlib.sha256((ROOT/'db.sqlite3').read_bytes()).hexdigest()
call_command('migrate',verbosity=0);call_command('seed_bos_demo',verbosity=0)
def client():
    c=Client(enforce_csrf_checks=True);login_test_client(c,capabilities=('view_document','download_document','export_workspace'));assert c.get('/api/operations/status/').status_code==200;return c
def post(c,path,data):return c.post('/api/operations/'+path,json.dumps(data),content_type='application/json',HTTP_X_CSRFTOKEN=c.cookies['csrftoken'].value)
def upload(c,code,version,content,name='source.txt'):
    return c.post('/api/operations/documents/upload/',{'code':code,'revision':version,'title':'Тестовий документ','file':SimpleUploadedFile(name,content)},HTTP_X_CSRFTOKEN=c.cookies['csrftoken'].value)
c=client()
test('Навчальні зв’язки й обсяг',Employee.objects.count()==6 and Task.objects.count()==8 and ProcurementRequest.objects.count()==3 and SupplierQuote.objects.count()==9)
call_command('seed_bos_demo',verbosity=0);test('Повторний імпорт без дублів',Task.objects.count()==8)
d=c.get('/api/operations/summary/').json()
test('Заборгованість і залишок',Decimal(d['receivables']['EUR']['open'])==20000 and Decimal(d['receivables']['EUR']['overdue'])==5000 and Decimal(d['cash']['amount'])==24000)
test('Прострочені доручення',sorted(x['id'] for x in d['overdue_tasks'])==[1,3,6])
d=service.compare('R01');test('R01: повна вартість і комплектність',[Decimal(x['total']) for x in d['rows']]==[1110,915,940] and d['recommended']=='Q13')
d=service.compare('R01',25);test('R01: симуляція 25 одиниць',d['recommended']=='Q11' and Decimal(d['rows'][0]['total'])==3510 and d['simulation'])
test('R02: жодної відповідної пропозиції',service.compare('R02')['recommended'] is None)
test('R03: прострочена пропозиція виключена',service.compare('R03')['recommended']=='Q33')
test('Некоректна кількість',c.get('/api/operations/compare/?code=R01&quantity=0').status_code==422)
payload={'action':'create_task','title':'Перевірити покриття','assignee_id':2,'deadline':'2026-09-11','request_code':'R01'}
p=post(c,'preview/',payload).json();test('Попередній перегляд без виконання',Task.objects.count()==8)
test('Відсутність підтвердження',post(c,'confirm/',{'proposal_id':p['id'],'confirmed':False}).status_code==422)
r=post(c,'confirm/',{'proposal_id':p['id'],'confirmed':True});test('Погодження зберігає доручення і журнал',r.status_code==200 and Task.objects.count()==9 and AuditEvent.objects.count()==1)
receipt=r.json();test('Та сама модель доручень',c.get('/api/tasks/'+str(receipt['task_id'])+'/').json()['title']==payload['title'])
test('Повтор не створює дубль',post(c,'confirm/',{'proposal_id':p['id'],'confirmed':True}).json()==receipt and Task.objects.count()==9 and AuditEvent.objects.count()==1)
other=client();test('Чуже погодження недоступне',post(other,'confirm/',{'proposal_id':p['id'],'confirmed':True}).status_code==403)
test('CSRF обов’язковий',c.post('/api/operations/preview/',json.dumps(payload),content_type='application/json').status_code==403)
post(other,'role/',{'role':'observer'})
test('Спостерігач не створює доручення',post(other,'preview/',payload).status_code==403)
test('Спостерігач не обходить через старий API',other.post('/api/tasks/',json.dumps({'title':'Обхід'}),content_type='application/json',HTTP_X_CSRFTOKEN=other.cookies['csrftoken'].value).status_code==403)
test('Спостерігач може читати сценарну відповідь',post(other,'chat/',{'message':'Що потребує уваги?'}).status_code==200)
p=post(c,'preview/',payload).json();ActionProposal.objects.filter(pk=p['id']).update(expires_at=timezone.now()-timedelta(seconds=1))
test('Погодження спливло',post(c,'confirm/',{'proposal_id':p['id'],'confirmed':True}).status_code==409)
p=post(c,'preview/',{'action':'update_task','task_id':1,'status':'done','assignee_id':2,'result':'Синтетичний результат для stale перевірки','reason':'Виконавець підтверджує завершення'}).json();Task.objects.filter(pk=1).update(title='Змінено колегою')
test('Конфлікт версії доручення',post(c,'confirm/',{'proposal_id':p['id'],'confirmed':True}).status_code==409)
p=post(c,'preview/',payload).json();req=ProcurementRequest.objects.get(code='R01');req.quantity=10;req.save()
test('Зміна заявки скасовує погодження',post(c,'confirm/',{'proposal_id':p['id'],'confirmed':True}).status_code==409)
req.quantity=5;req.save()
p=post(c,'preview/',payload).json();new=upload(c,req.document.code,'NEW','Нова унікальна вимога'.encode()).json()
test('Нова версія скасовує погодження',post(c,'confirm/',{'proposal_id':p['id'],'confirmed':True}).status_code==409)
test('Нова версія позначає порівняння',service.compare('R01')['recommended'] is None)
test('Пошук актуальної версії',any(x['id']==new['id'] for x in c.get('/api/operations/documents/?q=унікальна').json()['items']))
test('Старий текст виключений з пошуку',all(x['code']!=req.document.code for x in c.get('/api/operations/documents/?q=Сталь').json()['items']))
test('Історія версій збережена',len(c.get(f"/api/operations/documents/{new['id']}/").json()['versions'])==2)
resp=c.get(f"/api/operations/documents/{new['id']}/download/");test('Завантаження оригіналу',b''.join(resp.streaming_content)=='Нова унікальна вимога'.encode());resp.close()
test('Некоректний PDF повертає помилку',upload(c,'BAD','1',b'bad','broken.pdf').status_code==422)
test('Перевищення розміру',upload(c,'BIG','1',b'x'*(10*1024*1024+1)).status_code==422)
from docx import Document as Word
f=io.BytesIO();w=Word();w.add_paragraph('Кронштейн з покриттям');w.save(f)
test('Читання DOCX',upload(c,'DOCX','1',f.getvalue(),'sample.docx').status_code==201)
from openpyxl import Workbook
f=io.BytesIO();w=Workbook();w.active.append(['Матеріал','Сталь']);w.save(f)
test('Читання XLSX',upload(c,'XLSX','1',f.getvalue(),'sample.xlsx').status_code==201)
from pypdf import PdfWriter
f=io.BytesIO();w=PdfWriter();w.add_blank_page(width=100,height=100);w.write(f)
r=upload(c,'SCAN','1',f.getvalue(),'sample.pdf');test('PDF без тексту потребує OCR',r.status_code==201 and r.json()['status']=='ocr_required')
review=post(c,f"documents/{new['id']}/review/",{'checksum':new['checksum']});test('Перевірка документа людиною',review.status_code==200 and review.json()['status']=='approved')
p=post(c,'preview/',{'action':'update_task','task_id':2,'status':'done','assignee_id':2,'result':'Синтетичний фактичний результат','reason':'Погоджено завершення доручення'}).json();test('Оновлення статусу',post(c,'confirm/',{'proposal_id':p['id'],'confirmed':True}).status_code==200 and Task.objects.get(pk=2).status=='done')
test('Невідомий відповідальний',post(c,'preview/',{**payload,'assignee_id':9999}).status_code==404)
test('Невідомий інструмент заборонено',post(c,'preview/',{'action':'payment','amount':940}).status_code==422)
test('Імпорт не дозволяє додаткових інструментів',post(c,'preview/',{**payload,'shell':'echo BAD'}).status_code==422)
test('Відвертий локальний режим',post(c,'chat/',{'message':'Довільний аналіз'}).json()['mode']=='local_scenario' and not c.get('/api/operations/status/').json()['ai_configured'])
test('Зовнішня відправка відсутня','не входять' in post(c,'chat/',{'message':'Надішли замовлення'}).json()['text'])
rfq=c.get('/api/operations/rfq/R02/');test('RFQ є чернеткою',rfq.status_code==200 and 'Не надіслано'.encode() in rfq.content)
context=c.get('/api/operations/export/').json();test('Контекст містить умови й джерела',len(context['quotes'])==9 and all('sections' in x for x in context['documents']))
create={'code':'R04','part':'Нова деталь','revision':'NEW','quantity':2,'unit':'шт.','currency':'EUR','required_by':'2026-12-01','owner_id':2,'document_id':new['id'],'details':{'project':'Пілот','material':'Сталь'}}
test('Створення власної заявки',post(c,'requests/create/',create).status_code==201)
q=SupplierQuote.objects.get(code='Q13');terms={k:v for k,v in q.terms.items() if k in {'unit_price','setup','shipping','tooling','special_processes','currency','revision','lead_weeks','valid_until','moq','coating_included','material_certificate'}};terms['revision']='NEW'
test('Створення власної пропозиції',post(c,'quotes/create/',{'code':'Q41','request_code':'R04','supplier_id':q.supplier_id,'document_id':new['id'],'terms':terms}).status_code==201)
test('Власна заявка порівнюється',service.compare('R04')['recommended']=='Q41')
q=SupplierQuote.objects.get(code='Q41');q.terms={**q.terms,'currency':'USD'};q.save();test('Валюти не змішуються',service.compare('R04')['recommended'] is None)
test('Сторонній мережевий клієнт заблокований',c.get('/',REMOTE_ADDR='198.51.100.1').status_code==403)
test('Оригінальна база незмінна',hashlib.sha256((ROOT/'db.sqlite3').read_bytes()).hexdigest()==original_hash)
print(json.dumps({'passed':len(checks),'checks':checks,'original_db_sha256':original_hash,'not_tested':['Браузер і мобільний вигляд','Windows','Зовнішня мовна модель','Ізоляція клієнтів на сервері']},ensure_ascii=False,indent=2))
