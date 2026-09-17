"""Traceable UI data and suggested single actions; never executes from a read request."""
from decimal import Decimal as D
from django.conf import settings
from .models import *
from .service import usable,free,completed_steps,accepted_documents
from operations.models import Document
from operations.service import as_of
from tasks.models import Task
from .balances import sales_open,purchase_open,invoice_settlement,exact

FIELDS={
'lots':{'quantity':'Фізичний залишок','reserved':'У резерві','available':'Придатно й вільно','quality':'Якість','documents':'Документи партії','missing_documents':'Бракує документів'},
'lines':{'shipped':'Відвантажено','invoiced':'Виставлено в рахунках'},
'jobs':{'status':'Стан роботи','produced':'Випущено','actual_cost':'Фактичні витрати','needs_review':'Потребує перегляду','due_date':'Строк завершення'},
'purchases':{'quantity':'Замовлено','price':'Ціна одиниці','extras':'Додаткові витрати','received':'Отримано','status':'Стан поставки','due_date':'Очікувана дата'},
'invoices':{'amount':'Сума рахунку','paid':'Сплачено','open':'До оплати'},
'reservations':{'quantity':'Кількість резерву'},
'orders':{'status':'Стан замовлення'},
'items':{'revision':'Версія виробу','name':'Назва','bom':'Склад виробу','routing':'Маршрут'},
'locations':{'name':'Назва місця','kind':'Тип місця'},
'changes':{'status':'Стан зміни'},
'operator_entries':{'result':'Результат операції','minutes':'Витрачено хвилин'},
}

FIELDS['lines'].update(cancelled_quantity='Скасовано',open_quantity='Залишилося виконати',returned_quantity='Повернуто')
FIELDS['purchases'].update(cancelled_quantity='Скасовано',open_quantity='Залишилося прийняти',returned_quantity='Повернуто постачальнику',effective_status='Фактичний залишковий стан')
FIELDS['invoices'].update(effective_credit='Діючі кредитові коригування',net_amount='Рахунок після коригувань',receivable='До оплати',customer_credit='Залишок на користь клієнта')
FIELDS.update({'cancellations':{'quantity':'Скасовано'},'cancellation_releases':{'quantity':'Звільнено резерв'},'goods_returns':{'quantity':'Фізично повернуто','allocated_cost':'Джерельна облікова вартість'},'supplier_claims':{'record_kind':'Стан вимоги','agreed_amount':'Погоджена вимога'},'invoice_adjustments':{'kind':'Вид коригування','total':'Погоджена сума'},'invoice_adjustment_lines':{'quantity':'Кредитована кількість','amount':'Кредитована сума'}})

def impact(before,after):
    def display(value,field,source):
        if value is None:return None
        if field=='documents':return '; '.join(k+': '+next((d['code']+' · '+d['revision'] for d in source['documents'] if d['id']==v),str(v)) for k,v in value.items()) or 'Не додано'
        if field=='missing_documents':return ', '.join(value) or 'Комплектно'
        if field=='bom':return '; '.join(next((i['code'] for i in source['items'] if i['id']==v['item_id']),str(v['item_id']))+' × '+str(v['quantity']) for v in value) or 'Без компонентів'
        if field=='routing':return '; '.join(v['name'] for v in value)
        return value
    changes=[]
    for kind,fields in FIELDS.items():
        prev={r.get('id',r.get('invoice_id')):r for r in before.get(kind,[])}
        for r in after.get(kind,[]):
            pk=r.get('id',r.get('invoice_id'));old=prev.get(pk,{})
            code=r.get('code') or (r.get('operation') if kind=='operator_entries' else '')
            if kind=='lines':
                order=next((o for o in after['orders'] if o['id']==r['order_id']),{})
                item=next((i for i in after['items'] if i['id']==r['item_id']),{})
                code=order.get('code','')+' · '+item.get('code','')
            if kind=='reservations':code='Резерв · '+next((l['code'] for l in after['lots'] if l['id']==r['lot_id']),str(pk))
            for field,label in fields.items():
                a=old.get(field);b=r.get(field)
                if str(a)!=str(b):changes.append({'kind':kind,'id':pk,'code':code or str(pk),'field':field,'label':label,'before':display(a,field,before),'after':display(b,field,after),'currency':r.get('currency','')})
    return changes

@exact
def home(snapshot):
    currencies=sorted({x['currency'] for x in snapshot['orders']+snapshot['lots']+snapshot['purchases']}) or ['EUR']
    rows=[]
    for currency in currencies:
        costs=[x for x in snapshot['costs'] if x['currency']==currency];inv=[x for x in snapshot['invoices'] if x['currency']==currency]
        rows.append({'currency':currency,'order_value':str(sum((D(x['order_value']) for x in costs),D(0))),
        'shipped_value':str(sum((D(x['shipped_value']) for x in costs),D(0))),
        'shipped_cost':str(sum((D(x['shipped_cost']) for x in costs),D(0))),
        'gross_margin':str(sum((D(x['gross_margin']) for x in costs),D(0))),
        'receivable':str(sum((D(x['open']) for x in inv),D(0))),
        'paid':str(sum((D(x['paid']) for x in inv),D(0))),
        'purchase_open':str(sum((D(x['open_quantity'])*(D(x['price'])+D(x['extras'])/D(x['quantity'])) for x in snapshot['purchases'] if x['currency']==currency),D(0)).quantize(D('.01'))),
        'stock_value':str(sum((D(x['quantity'])*D(x['unit_cost']) for x in snapshot['lots'] if x['currency']==currency),D(0)).quantize(D('.01')))})
    from tasks.queries import active,project_list
    tasks=project_list(active())
    for t in tasks:t['overdue']=t['is_overdue']
    return {'financial':rows,'tasks':tasks,'sources':'Поточні ERP-записи; суми окремо за валютою. Податки й загальні витрати не включено.'}

@exact
def next_step(order, policy=None):
    """Choose a single meaningful action with editable prefilled fields."""
    visible = policy.filter_queryset if policy else lambda rows: rows
    def result(title,why,action=None,**payload):
        if 'quantity' in payload:payload['quantity']=str(D(payload['quantity']).quantize(D('.001')))
        return {'title':title,'why':why,'payload':{'action':'erp_'+action,**payload} if action else None}
    def code(model,prefix):
        n=1
        while model.objects.filter(code=prefix+'-'+str(n)).exists():n+=1
        return prefix+'-'+str(n)
    def certs(item):
        doc=visible(Document.objects.filter(code='ERP-CERT')).order_by('-id').first() if settings.BOS_DATA_MODE=='demo' else None
        return {'certificate':doc.id} if doc and doc.status=='approved' and 'certificate' in item.required_documents else {}
    if order.status=='quote':return result('Підтвердити замовлення','Перевірте узгоджені кількість, ціну й строк.','confirm_order',order_id=order.id)
    for line in visible(order.lines.all()).select_related('item'):
        left=sales_open(line)
        if left<=0:continue
        for r in visible(line.reservations.filter(quantity__gt=0)).select_related('lot__item'):
            if usable(r.lot,line.revision):return result('Відвантажити зарезервовану партію','Зменшиться складський залишок і невиконана кількість замовлення.','ship',line_id=line.id,lot_id=r.lot_id,quantity=str(min(left,r.quantity)),reference=order.code+'-SHIP-'+str(Movement.objects.filter(line=line,kind='shipment').count()+1))
        own=sum((r.quantity for r in visible(line.reservations.all())),D(0))
        for lot in visible(Lot.objects.filter(item=line.item,revision=line.revision,quantity__gt=0)):
            if usable(lot,line.revision) and free(lot)>0 and left>own:return result('Зарезервувати готову продукцію','Закріпіть доступну партію за цим замовленням.','reserve',lot_id=lot.id,line_id=line.id,quantity=str(min(left-own,free(lot))))
        jobs=visible(Production.objects.filter(line=line))
        # Finished material from this order must pass quality before reservation.
        for lot in visible(Lot.objects.filter(movements__production__in=jobs,movements__kind='production',quantity__gt=0)).distinct():
            if not usable(lot,line.revision):
                missing=next(iter(accepted_documents(lot.item,lot.documents)),None)
                docs=certs(lot.item)
                if missing and missing in docs:return result('Додати документ готової партії','Сертифікат потрібен для перевірки комплектності.','attach',lot_id=lot.id,kind=missing,document_id=docs[missing])
                if missing:return result('Додайте перевірений документ '+missing,'У картці партії відкрийте документи: поточний комплект не дає допуску до відвантаження.')
                owner=jobs.first().owner_id
                return result('Перевірити готову партію','Підтвердьте результат фактичної перевірки перед допуском.','quality',lot_id=lot.id,result='approved',inspector_id=owner,note='Перевірено комплектність та відповідність погодженій специфікації')
        for job in jobs.exclude(status='done'):
            if job.needs_review:return result('Потрібне рішення керівника щодо версії','Відкрийте картку роботи та погодьте подальше виконання.')
            for b in job.bom:
                need=D(b['quantity'])*(job.quantity-job.produced)
                held=sum((r.quantity for r in visible(job.reservations.filter(lot__item_id=b['item_id'])) if usable(r.lot)),D(0))
                if held>=need:continue
                item=Item.objects.get(pk=b['item_id'])
                local=list(visible(Lot.objects.filter(item=item,location=job.location,quantity__gt=0)))
                for lot in local:
                    if usable(lot) and free(lot)>0:return result('Зарезервувати '+item.code,'Матеріал уже у місці виконання. Резерв захистить його від іншого замовлення.','reserve',lot_id=lot.id,production_id=job.id,quantity=str(min(need-held,free(lot))))
                for lot in local:
                    if lot.quality=='pending':
                        missing=next(iter(accepted_documents(lot.item,lot.documents)),None);docs=certs(lot.item)
                        if missing and missing in docs:return result('Додати документ матеріалу','Замінить відсутнє або застаріле джерело перед перевіркою якості.','attach',lot_id=lot.id,kind=missing,document_id=docs[missing])
                        if missing:return result('Потрібен документ '+missing,'Відкрийте партію, додайте та перевірте актуальний документ.')
                        return result('Перевірити прийнятий матеріал','Поки немає дозволу за якістю, матеріал не можна використати.','quality',lot_id=lot.id,result='approved',inspector_id=job.owner_id,note='Перевірено кількість, стан і супровідні документи')
                for lot in visible(Lot.objects.filter(item=item,quantity__gt=0).exclude(location=job.location)):
                    if usable(lot) and free(lot)>0:return result('Передати '+item.code+' до місця виконання','Кількість переміститься між місцями; загальний запас і вартість збережуться.','transfer',lot_id=lot.id,quantity=str(min(need-held,free(lot))),location_id=job.location_id,code=code(Lot,'MOVE-'+lot.code),reason='Матеріали для '+job.code,production_id=job.id)
                po=next((p for p in visible(Purchase.objects.filter(item=item,production=job).exclude(status='received')) if purchase_open(p)>0),None)
                if po:return result('Прийняти поставку '+po.code,'Виконуйте після фактичного отримання. Партія спочатку очікуватиме перевірки.','receive',purchase_id=po.id,code=code(Lot,'RCV-'+po.code),location_id=job.location_id,quantity=str(purchase_open(po)),documents=certs(item))
                return result('Потрібно забезпечити '+item.code,'Створіть закупівлю або уточніть наявність матеріалу у картці виробництва.')
            if job.status=='planned':return result('Розпочати '+job.code,'Матеріали зарезервовано. Старт зафіксує початок роботи.','start',production_id=job.id)
            done=completed_steps(job)
            for step in job.routing:
                if step['name'] not in done:return result('Зафіксувати: '+step['name'],step.get('instruction','Перевірте виконання операції.'),'operator',production_id=job.id,operation=step['name'],operator_id=job.owner_id,result='done',minutes=30 if settings.BOS_DATA_MODE=='demo' else 0,defects='0',note='Операцію виконано за погодженими вимогами')
            warehouse=Location.objects.filter(kind='warehouse').first()
            if not warehouse:return result('Додати місце приймання продукції','Потрібен склад, куди буде оприбутковано готову партію.','location',code=code(Location,'WH'),name='Склад готової продукції',kind='warehouse')
            return result('Випустити продукцію '+job.code,'Матеріали спишуться за специфікацією. Уточніть фактичну вартість робіт.','finish',production_id=job.id,quantity=str(job.quantity-job.produced),code=code(Lot,'OUT-'+job.code),location_id=warehouse.id, labor_cost='1000' if settings.BOS_DATA_MODE=='demo' else '0',documents=certs(job.item))
        return result('Запланувати забезпечення решти замовлення','Відкрийте позицію продажу та створіть виробничу роботу або закупівлю.')
    if any(l.shipped>l.invoiced for l in visible(order.lines.all())):return result('Створити рахунок за відвантаження','До рахунку потрапить лише кількість, за яку його ще не виставлено.','invoice',order_id=order.id,code=code(__import__('operations.models',fromlist=['Invoice']).Invoice,'INV-'+order.code),due_date=str(order.due_date))
    if policy and not policy.ceo:
        return result('Відвантаження завершено', 'Перегляньте доступні записи замовлення. Фінансову звірку виконує керівник.')
    from .corrections import unresolved_returns
    if unresolved_returns(order,policy):return result('Потрібне рішення щодо повернення','Фізичне повернення не змінює рахунок або оплату. Перевірте джерело й кредитове коригування.')
    for link in visible(InvoiceLink.objects.filter(order=order)).select_related('invoice'):
        inv=link.invoice
        if invoice_settlement(inv)['receivable']>0:return result('Зареєструвати отриману оплату','Лише після підтвердження надходження коштів. Зменшиться відкрита сума рахунку.','payment',invoice_id=inv.id,amount=str(invoice_settlement(inv)['receivable']),reference=inv.code+'-PAY-'+str(Event.objects.filter(action='erp_payment',payload__invoice_id=inv.id).count()+1))
    if any(invoice_settlement(link.invoice)['customer_credit']>0 for link in visible(InvoiceLink.objects.filter(order=order)).select_related('invoice')):return result('Потрібне рішення щодо залишку на користь клієнта','Кредитове коригування перевищило неоплачену суму. Узгодьте окреме рішення; кошти автоматично не повернуто.')
    return result('Замовлення виконано й оплати звірено','Перегляньте відвантаження, собівартість, рахунки та журнал у картці замовлення.')
