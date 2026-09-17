"""End-to-end ERP checks: isolated in-memory DB; no network or live database writes."""
import os,sys,json,hashlib
from pathlib import Path
from decimal import Decimal as D
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE']='demo_settings';os.environ['BOS_DATA_MODE']='demo'
import django
from django.conf import settings
from check_support import configure, prove_database, login_test_client
configure(settings);django.setup();prove_database()
from django.core.management import call_command
from django.test import Client
from django.db.models import Sum
from erp.models import *
from erp import service as s,queries
from operations.models import Document,Invoice,ActionProposal
from employees.models import Employee
checks=[]
def test(name,ok):
    assert ok,name
    checks.append(name)
hash_before=hashlib.sha256((ROOT/'db.sqlite3').read_bytes()).hexdigest()
call_command('migrate',verbosity=0);call_command('seed_bos_demo',verbosity=0);call_command('seed_erp_demo',verbosity=0)
n=Event.objects.count();call_command('seed_erp_demo',verbosity=0)
test('Повторне наповнення зберігає записи',Event.objects.count()==n and Item.objects.count()==3)
c=Client(enforce_csrf_checks=True);login_test_client(c,capabilities=('view_document','download_document','export_workspace'));c.get('/api/operations/status/')
def post(path,payload):return c.post(path,json.dumps(payload),content_type='application/json',HTTP_X_CSRFTOKEN=c.cookies['csrftoken'].value)
def preview(action,**data):return post('/api/erp/preview/',{'action':'erp_'+action,**data})
def act(action,**data):
    r=preview(action,**data);assert r.status_code==200,(action,r.status_code,r.content)
    r=post('/api/operations/confirm/',{'proposal_id':r.json()['id'],'confirmed':True});assert r.status_code==200,(action,r.status_code,r.content)
    return r.json()
def denied(name,action,**data):
    before=s.fingerprint();n=Event.objects.count();r=preview(action,**data)
    test(name,r.status_code in (422,403,404,409) and s.fingerprint()==before and Event.objects.count()==n)
line=SalesLine.objects.get(order__code='SO-101');other=SalesLine.objects.get(order__code='SO-102');job=Production.objects.get(code='MO-101');vendor=Location.objects.get(code='VENDOR-A');main=Location.objects.get(code='WH-01');emp=Employee.objects.get(full_name='Іван Тестовий');cert=Document.objects.get(code='ERP-CERT');raw=Lot.objects.get(code='LOT-MAT');fast=Lot.objects.get(code='LOT-FAST');fg=Lot.objects.get(code='LOT-FG-OK');hold=Lot.objects.get(code='LOT-FG-HOLD')
p=queries.plan_line(line)
test('План: 50 виробів, резерв 10, виготовити 40',D(p['remaining'])==50 and D(p['reserved'])==10 and D(p['shortage'])==40)
test('Матеріальна потреба 32 кг / 80 кріплень; надходження закривають дефіцит',[(D(x['need']),D(x['available']),D(x['expected']),D(x['deficit'])) for x in p['materials']]==[(32,24,8,0),(80,60,20,0)])
test('ERP API та експорт читаються',c.get('/api/erp/snapshot/').status_code==200 and c.get('/api/erp/export/').status_code==200)
denied('Немає подвійного резервування','reserve',lot_id=fg.id,line_id=other.id,quantity='1')
denied('Карантин не відвантажується','ship',lot_id=hold.id,line_id=line.id,quantity='1',reference='BAD')
denied('Не можна передати чужий резерв','transfer',lot_id=fg.id,quantity='1',location_id=vendor.id,code='BAD',reason='Тест')
denied('Виробництво не стартує без матеріалів','start',production_id=job.id)
denied('Від’ємна кількість заборонена','reserve',lot_id=fg.id,line_id=line.id,quantity='-1')
denied('Надмірна точність заборонена','reserve',lot_id=fg.id,line_id=line.id,quantity='0.0001')
denied('Невідомі поля відхилено','start',production_id=job.id,shell='bad')
before=s.fingerprint();n=Event.objects.count();r=preview('postpone',purchase_id=Purchase.objects.get(code='PO-MAT').id,due_date='2026-09-17',reason='Тест перегляду');test('Перегляд не змінює бізнес-дані',r.status_code==200 and s.fingerprint()==before and Event.objects.count()==n)
payload={'proposal_id':r.json()['id'],'confirmed':True};receipt=post('/api/operations/confirm/',payload);again=post('/api/operations/confirm/',payload)
test('Повтор погодження не дублює операцію',receipt.status_code==200 and again.json()==receipt.json() and Event.objects.count()==n+1)
r=preview('postpone_job',production_id=job.id,due_date='2026-09-25',reason='Новий строк')
act('postpone',purchase_id=Purchase.objects.get(code='PO-FAST').id,due_date='2026-09-13',reason='Постачальник підтвердив')
test('Застаріле погодження відхиляється',post('/api/operations/confirm/',{'proposal_id':r.json()['id'],'confirmed':True}).status_code==409)
post('/api/operations/role/',{'role':'observer'})
test('Спостерігач читає ERP',c.get('/api/erp/snapshot/').status_code==200)
denied('Спостерігач не змінює ERP','postpone_job',production_id=job.id,due_date='2026-09-25',reason='Тест')
post('/api/operations/role/',{'role':'manager'})
change=ChangeOrder.objects.get(code='ECO-101')
denied('Зміну версії затверджує лише керівник','apply_change',change_id=change.id,disposition='Перевірити')
post('/api/operations/role/',{'role':'ceo'})
act('apply_change',change_id=change.id,disposition='SO-101 завершуємо за A після погодження відповідального')
job.refresh_from_db();line.refresh_from_db();test('Зміна ставить роботу на перегляд, зберігає версію продажу',job.needs_review and job.revision=='A' and line.revision=='A' and Item.objects.get(code='DEMO-101').revision=='B')
denied('Зміна версії блокує старт до рішення','start',production_id=job.id)
act('resolve_job',production_id=job.id,disposition='Для SO-101 погоджено завершення версії A')
job.refresh_from_db();test('Окреме рішення зберігає стару специфікацію',not job.needs_review and job.revision=='A')
material_lots=[]
for po_code,quantity,doc in [('PO-MAT','8',{'certificate':cert.id}),('PO-FAST','20',{})]:
    po=Purchase.objects.get(code=po_code)
    denied('Немає надлишкового приймання '+po_code,'receive',purchase_id=po.id,code='OVER',location_id=vendor.id,quantity=str(D(quantity)+1))
    out=act('receive',purchase_id=po.id,code='RCV-'+po_code,location_id=vendor.id,quantity=quantity,documents=doc)
    test('Надходження починається з перевірки '+po_code,Lot.objects.get(pk=out['lot_id']).quality=='pending')
    act('quality',lot_id=out['lot_id'],result='approved',inspector_id=emp.id,note='Комплектність навчальних даних перевірено');material_lots.append(out['lot_id'])
for lot in (raw,fast):
    out=act('transfer',lot_id=lot.id,quantity=str(lot.quantity),location_id=vendor.id,code='V-'+lot.code,reason='Передача давальницьких матеріалів',production_id=job.id);material_lots.append(out['lot_id'])
for lot_id in material_lots:
    lot=Lot.objects.get(pk=lot_id);act('reserve',lot_id=lot.id,quantity=str(lot.quantity),production_id=job.id)
act('start',production_id=job.id)
denied('Порядок виробничих операцій перевіряється','operator',production_id=job.id,operation=job.routing[-1]['name'],operator_id=emp.id,result='done',minutes=10,defects='0')
denied('Випуск без завершених операцій заборонений','finish',production_id=job.id,quantity='40',code='BAD',location_id=main.id,labor_cost='1000')
for step in job.routing:act('operator',production_id=job.id,operation=step['name'],operator_id=emp.id,result='done',minutes=30,defects='0',note='Навчальна операція')
act('operator',production_id=job.id,operation=job.routing[-1]['name'],operator_id=emp.id,result='defect',minutes=5,defects='1',note='Повторна перевірка')
denied('Останній дефект скасовує попереднє завершення операції','finish',production_id=job.id,quantity='40',code='OUT-DEFECT',location_id=main.id,labor_cost='1000')
act('operator',production_id=job.id,operation=job.routing[-1]['name'],operator_id=emp.id,result='done',minutes=5,defects='0',note='Зауваження усунено')
denied('Дрібний випуск не губить частки матеріалу','finish',production_id=job.id,quantity='0.001',code='OUT-TINY',location_id=main.id,labor_cost='0')
# Currency failure must roll back every component consumption.
foreign=Lot.objects.get(pk=material_lots[-1]);foreign.currency='USD';foreign.save()
denied('Різні валюти не змішуються в собівартості','finish',production_id=job.id,quantity='40',code='OUT-FAIL',location_id=main.id,labor_cost='1000')
foreign.currency='EUR';foreign.save()
out=act('finish',production_id=job.id,quantity='40',code='OUT-MO-101',location_id=main.id,labor_cost='1000');made=Lot.objects.get(pk=out['lot_id']);job.refresh_from_db()
test('Випуск 40: матеріали 544 + роботи 1000 = 1544 EUR',made.quantity==40 and made.unit_cost==D('38.60') and job.actual_cost==1544 and job.status=='done')
test('Матеріали у підрядника списані рівно за специфікацією',all(Lot.objects.get(pk=i).quantity==0 for i in material_lots))
denied('Без сертифіката якість не погоджується','quality',lot_id=made.id,result='approved',inspector_id=emp.id,note='Перевірено')
act('attach',lot_id=made.id,kind='certificate',document_id=cert.id);act('quality',lot_id=made.id,result='approved',inspector_id=emp.id,note='Комплект повний')
act('reserve',lot_id=made.id,quantity='20',line_id=line.id)
act('ship',lot_id=fg.id,line_id=line.id,quantity='10',reference='SHP-1');act('ship',lot_id=made.id,line_id=line.id,quantity='20',reference='SHP-2');line.refresh_from_db()
test('Часткова поставка зберігає залишок 20',line.shipped==30 and line.quantity-line.shipped==20)
denied('Відвантаження без власного резерву відхиляється','ship',lot_id=made.id,line_id=line.id,quantity='1',reference='BAD')
inv=act('invoice',order_id=line.order_id,code='ERP-INV-101',due_date='2026-10-10')
test('Рахунок лише за відвантажені 30 одиниць',D(inv['amount'])==3600)
denied('Повторного рахунку на те саме відвантаження немає','invoice',order_id=line.order_id,code='ERP-INV-DUP',due_date='2026-10-10')
act('payment',invoice_id=inv['invoice_id'],amount='1200',reference='PAY-101');invoice=Invoice.objects.get(pk=inv['invoice_id'])
test('Часткова оплата залишає 2400 EUR',invoice.amount-invoice.paid==2400)
denied('Повторний номер оплати відхиляється','payment',invoice_id=invoice.id,amount='100',reference='PAY-101')
denied('Переплата відхиляється','payment',invoice_id=invoice.id,amount='2401',reference='PAY-102')
act('return',line_id=line.id,lot_id=made.id,quantity='2',code='RET-101',location_id=main.id,reason='Навчальна невідповідність')
test('Повернення потрапляє до карантину',Lot.objects.get(code='RET-101').quality=='blocked')
denied('Повернення не перевищує факт поставки','return',line_id=line.id,lot_id=made.id,quantity='19',code='RET-BAD',location_id=main.id,reason='Тест')
for lot in Lot.objects.all():
    net=lot.movements.aggregate(n=Sum('quantity'))['n'] or D(0)
    assert net==lot.quantity and D(0)<=s.reserved(lot)<=lot.quantity,(lot.code,net,lot.quantity)
test('Кожний залишок дорівнює сумі рухів; резерви не перевищені',True)
d=queries.snapshot();cost=next(x for x in d['costs'] if x['order_id']==line.order_id)
test('Собівартість відвантажень 1172, управлінська різниця 2428',D(cost['shipped_cost'])==1172 and D(cost['gross_margin'])==2428)
test('Постачальники мають реальну історію приймань',sum(x['receipts'] for x in d['supplier_scores'])==2)
r=post('/api/operations/chat/',{'message':'Поясни SO-101'})
test('Асистент читає поточний залишок замовлення',r.status_code==200 and 'поставити ще 20' in r.json()['text'])
r=post('/api/operations/chat/',{'message':'Де матеріали на складі?'})
test('Асистент називає партії та місця',r.status_code==200 and 'RET-101' in r.json()['text'] and 'фізично' in r.json()['text'])
before=s.fingerprint();r=post('/api/operations/chat/',{'message':'Відвантаж SO-101'})
test('Сценарний асистент не виконує дію з тексту',r.status_code==200 and s.fingerprint()==before and 'ще не виконано' in r.json()['text'])
d=c.get('/api/operations/export/').json()
test('Спільний контекст містить ERP та дозволені інструменти','erp' in d and 'erp_reserve' in d['erp_tools'] and d['erp']['invoices'])
test('Оригінальна база незмінна',hashlib.sha256((ROOT/'db.sqlite3').read_bytes()).hexdigest()==hash_before)
print(json.dumps({'passed':len(checks),'checks':checks,'original_db_sha256':hash_before,'not_tested':['Візуальна перевірка браузера','Запуск у Windows','Виробниче навантаження і багатокористувацький сервер']},ensure_ascii=False,indent=2))
