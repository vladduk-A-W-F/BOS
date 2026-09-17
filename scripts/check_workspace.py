"""Isolated contract checks for BoS guided workspace. Never touches a live database."""
import os,sys,json,hashlib
from pathlib import Path
from decimal import Decimal as D
ROOT=Path(os.environ.get('BOS_PROJECT_ROOT',Path(__file__).resolve().parents[1]))
if not (ROOT/'demo_settings.py').exists():ROOT=Path('/workspace/sites/bos-original-refined')
sys.path.insert(0,str(ROOT));os.environ['DJANGO_SETTINGS_MODULE']='demo_settings';os.environ['BOS_DATA_MODE']='demo'
if os.environ.get('BOS_TEST_DEPENDENCIES'):sys.path.append(os.environ['BOS_TEST_DEPENDENCIES'])
import django
from django.conf import settings
from check_support import configure, prove_database, login_test_client
configure(settings);django.setup();prove_database()
from django.core.management import call_command
from django.test import Client
from django.db import transaction
from django.db.models import Sum
from erp.models import SalesOrder,SalesLine,Lot,Movement,Event,Production,InvoiceLink,Location
from erp import service
from operations.models import Invoice,Document,Configuration,ActionProposal
checks=[];journey=[]
def test(name,condition):
    assert condition,name
    checks.append(name)
original=ROOT/'db.sqlite3';before_hash=hashlib.sha256(original.read_bytes()).hexdigest()
for command in ('migrate','seed_bos_demo','seed_erp_demo','seed_bos_workspace'):call_command(command,verbosity=0)
c=Client(enforce_csrf_checks=True);login_test_client(c,capabilities=('view_document','download_document','export_workspace'));c.get('/api/operations/status/')
def post(path,payload):return c.post(path,json.dumps(payload),content_type='application/json',HTTP_X_CSRFTOKEN=c.cookies['csrftoken'].value)
def snap():
    r=c.get('/api/erp/snapshot/');assert r.status_code==200,r.content
    return r.json()
def home_consistent(data):
    for row in data['home']['financial']:
        currency=row['currency'];costs=[x for x in data['costs'] if x['currency']==currency];invoices=[x for x in data['invoices'] if x['currency']==currency]
        for key in ('order_value','shipped_value','shipped_cost','gross_margin'):
            assert D(row[key])==sum((D(x[key]) for x in costs),D(0)),key
        assert D(row['paid'])==sum((D(x['paid']) for x in invoices),D(0))
        assert D(row['receivable'])==sum((D(x['open']) for x in invoices),D(0))
        assert D(row['stock_value'])==sum((D(x['quantity'])*D(x['unit_cost']) for x in data['lots'] if x['currency']==currency),D(0)).quantize(D('.01'))
        assert D(row['purchase_open'])==sum(((D(x['quantity'])-D(x['received']))*(D(x['price'])+D(x['extras'])/D(x['quantity'])) for x in data['purchases'] if x['currency']==currency),D(0)).quantize(D('.01'))
initial=snap();home_consistent(initial);test('Головний екран звірено з ERP окремо за валютою',True)
example_ids=list(SalesOrder.objects.filter(code__in=['SO-090','SO-091','SO-092']).values_list('id',flat=True))
example_inv=Invoice.objects.filter(pk__in=InvoiceLink.objects.filter(order_id__in=example_ids).values('invoice_id'))
test('Приклади: 3640 EUR рахунків, 2040 оплат, 1600 відкрито',sum((x.amount for x in example_inv),D(0))==3640 and sum((x.paid for x in example_inv),D(0))==2040)
fingerprint=service.fingerprint();n=Event.objects.count();call_command('seed_bos_workspace',verbosity=0)
test('Повторне наповнення не змінює даних',fingerprint==service.fingerprint() and Event.objects.count()==n)
with transaction.atomic():
    lot=Lot.objects.first()
    Lot.objects.create(code='USD-ISOLATED',item=lot.item,location=lot.location,revision=lot.revision,quantity='2',quality='pending',unit_cost='13.40',currency='USD')
    currency_snapshot=snap();home_consistent(currency_snapshot)
    usd=next(x for x in currency_snapshot['home']['financial'] if x['currency']=='USD')
    eur=next(x for x in currency_snapshot['home']['financial'] if x['currency']=='EUR')
    initial_eur=next(x for x in initial['home']['financial'] if x['currency']=='EUR')
    test('USD та EUR зберігаються окремо без прихованої конвертації',D(usd['stock_value'])==D('26.80') and eur==initial_eur)
    transaction.set_rollback(True)
order=SalesOrder.objects.get(code='SO-101');line=order.lines.get();url=f'/api/erp/orders/{order.id}/next/'
seen=set();certificate_checked=False;warehouse_checked=False
for step in range(40):
    before=service.fingerprint();r=c.get(url);assert r.status_code==200,(step,r.status_code,r.content)
    suggestion=r.json();assert before==service.fingerprint(),'GET suggestion mutated state'
    payload=suggestion['payload']
    if payload is None:
        line.refresh_from_db();assert line.shipped==line.quantity,(suggestion,line.shipped,line.quantity)
        links=list(InvoiceLink.objects.filter(order=order).select_related('invoice'));assert links and all(x.invoice.paid==x.invoice.amount for x in links),suggestion
        break
    if payload['action']=='erp_quality' and not certificate_checked:
        lot=Lot.objects.get(pk=payload['lot_id'])
        if 'certificate' in lot.item.required_documents:
            with transaction.atomic():
                lot.documents={};lot.save(update_fields=['documents'])
                suggested=c.get(url);assert suggested.status_code==200,suggested.content
                repair=suggested.json();assert repair['payload'] and repair['payload']['action']=='erp_attach',repair
                repair_preview=post('/api/erp/preview/',repair['payload'])
                test('Підказка відновлює відсутній документ і пояснює вплив',repair_preview.status_code==200 and bool(repair_preview.json().get('impact')))
                Document.objects.filter(code='ERP-CERT').update(status='needs_review')
                blocked=c.get(url)
                test('Без затвердженого джерела підказка просить документ замість непридатної дії',blocked.status_code==200 and blocked.json()['payload'] is None and 'документ' in blocked.json()['title'].lower())
                transaction.set_rollback(True)
            certificate_checked=True
    if payload['action']=='erp_finish' and not warehouse_checked:
        with transaction.atomic():
            Location.objects.filter(kind='warehouse').update(kind='production')
            suggested=c.get(url);assert suggested.status_code==200,suggested.content
            repair=suggested.json()
            test('За відсутності складу пропонується його створення без помилки сервера',repair['payload'] and repair['payload']['action']=='erp_location')
            repair_preview=post('/api/erp/preview/',repair['payload'])
            test('Запропоноване створення складу проходить попередню перевірку',repair_preview.status_code==200)
            transaction.set_rollback(True)
        warehouse_checked=True
    journey.append({'step':step+1,'title':suggestion['title'],'action':payload['action']})
    n=Event.objects.count();r=post('/api/erp/preview/',payload)
    assert r.status_code==200,(step,suggestion,r.status_code,r.content)
    proposal=r.json();assert before==service.fingerprint() and Event.objects.count()==n,'Preview wrote state'
    if payload['action'] not in ('erp_attach',):assert proposal.get('impact'),('No visible impact',payload)
    confirmation={'proposal_id':proposal['id'],'confirmed':True}
    applied=post('/api/operations/confirm/',confirmation);assert applied.status_code==200,(step,payload,applied.status_code,applied.content)
    assert Event.objects.count()==n+1,('Wrong event count',payload)
    again=post('/api/operations/confirm/',confirmation)
    assert again.status_code==200 and again.json()==applied.json() and Event.objects.count()==n+1,'Duplicate confirmation executed twice'
    seen.add(payload['action']);home_consistent(snap())
else:raise AssertionError(('Guided journey failed to terminate within 40 steps',journey))
test('Покрокове виконання SO-101 завершено не більш як за 40 дій',len(journey)<=40)
test('Кожна підказка читає дані без виконання',True)
test('Кожний попередній перегляд не змінює залишків і журналу',True)
test('Кожна суттєва дія показує вплив до і після',True)
test('Повторне підтвердження кожної дії ідемпотентне',True)
test('Показники оновлюються після кожної виконаної дії',True)
required={'erp_ship','erp_transfer','erp_receive','erp_quality','erp_reserve','erp_start','erp_operator','erp_finish','erp_invoice','erp_payment'}
test('Маршрут охоплює постачання, склад, виробництво, якість, рахунок і оплату',required<=seen)
line.refresh_from_db();job=Production.objects.get(code='MO-101');links=list(InvoiceLink.objects.filter(order=order).select_related('invoice'))
test('SO-101: усі 50 виробів поставлено, рахунки на 6000 EUR повністю сплачено',line.shipped==50 and line.invoiced==50 and sum((x.invoice.amount for x in links),D(0))==6000 and sum((x.invoice.paid for x in links),D(0))==6000)
test('MO-101 завершено: 40 виробів і 1544 EUR фактичної собівартості',job.status=='done' and job.produced==40 and job.actual_cost==1544)
for lot in Lot.objects.all():
    net=lot.movements.aggregate(n=Sum('quantity'))['n'] or D(0)
    assert net==lot.quantity and D(0)<=service.reserved(lot)<=lot.quantity,(lot.code,net,lot.quantity)
test('Залишки звірені з рухами; резерви не перевищують кількості',True)
# An approved preview cannot be confirmed after another business action changed state.
po=__import__('erp.models',fromlist=['Purchase']).Purchase.objects.first()
a={'action':'erp_postpone','purchase_id':po.id,'due_date':'2026-10-05','reason':'Тест актуальності'}
b={**a,'due_date':'2026-10-06','reason':'Нова погоджена дата'}
a_r=post('/api/erp/preview/',a);b_r=post('/api/erp/preview/',b)
assert a_r.status_code==b_r.status_code==200,(a_r.content,b_r.content)
b_done=post('/api/operations/confirm/',{'proposal_id':b_r.json()['id'],'confirmed':True});assert b_done.status_code==200,b_done.content
n=Event.objects.count();a_done=post('/api/operations/confirm/',{'proposal_id':a_r.json()['id'],'confirmed':True})
test('Застарілий попередній перегляд не виконується',a_done.status_code==409 and Event.objects.count()==n)
post('/api/operations/role/',{'role':'observer'})
test('Спостерігач бачить підказку і показники',c.get(url).status_code==200 and c.get('/api/erp/snapshot/').status_code==200)
fingerprint=service.fingerprint();r=post('/api/erp/preview/',a)
test('Спостерігач не може виконати підказку',r.status_code==403 and fingerprint==service.fingerprint())
test('Оригінальну базу не змінено',hashlib.sha256(original.read_bytes()).hexdigest()==before_hash)
print(json.dumps({'passed':len(checks),'checks':checks,'guided_steps':len(journey),'journey':journey,'original_db_sha256':before_hash,'not_tested':['Вигляд у браузері','Запуск у Windows','Багатокористувацьке навантаження']},ensure_ascii=False,indent=2))
