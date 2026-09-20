"""Transactional local ERP. All user mutations pass proposal/confirmation."""
from decimal import Decimal,InvalidOperation
from datetime import date,timedelta
import hashlib,json
from django.db import transaction
from django.db.models import Sum,F
from .models import *
from operations.models import Document,Configuration,Invoice
from operations.service import as_of,newest,Conflict
from employees.models import Employee
from finance.models import Counterparty
from boss_project.data_rules import field_values, portable_tree, decimal_value

D=Decimal
ZERO=D('0')
MODELS=[Item,Location,Lot,SalesOrder,SalesLine,Production,Reservation,Purchase,Movement,Inspection,ChangeOrder,InvoiceLink,OperatorEntry]
# req fields; optional values have explicit defaults, unknown fields rejected.
SCHEMAS={
'import_batch':('batch','source_part_sha256'),
'item':('code name unit kind method revision currency','material external_codes required_documents bom routing minimum lead_days planned_cost document_id'),
'location':('code name kind','supplier_id branch_id address lat lng'),
'order':('code customer_id owner_id due_date currency lines','notes fulfillment_location_id destination_country'),
'confirm_order':('order_id',''),
'opening':('code item_id location_id quantity unit_cost currency revision','documents reason'),
'purchase':('code item_id supplier_id quantity price currency due_date revision','extras production_id request_id quote_id supplier_confirmation direct_reason destination_id origin_country'),
'receive':('purchase_id code location_id quantity','documents'),
'job':('code item_id quantity location_id owner_id due_date','line_id'),
'reserve':('lot_id quantity','line_id production_id'),
'release':('reservation_id quantity',''),
'transfer':('lot_id quantity location_id code reason','production_id'),
'quality':('lot_id result inspector_id note',''),
'attach':('lot_id kind document_id',''),
'start':('production_id',''),
'operator':('production_id operation operator_id result minutes defects','note'),
'finish':('production_id quantity code location_id labor_cost','documents'),
'ship':('line_id lot_id quantity reference',''),
'return':('line_id lot_id quantity code location_id reason',''),
'invoice':('order_id code due_date',''),
'payment':('invoice_id amount reference',''),
'change':('code item_id document_id target_revision reason',''),
'apply_change':('change_id disposition',''),
'resolve_job':('production_id disposition',''),
'postpone':('purchase_id due_date reason',''),
'postpone_job':('production_id due_date reason',''),
'adjust':('lot_id delta reason',''),
}

from .corrections import SCHEMAS as CORRECTION_SCHEMAS, MODELS as CORRECTION_MODELS
SCHEMAS.update(CORRECTION_SCHEMAS)
MODELS += list(CORRECTION_MODELS)
from .network_commands import SCHEMAS as NETWORK_SCHEMAS, MODELS as NETWORK_MODELS
SCHEMAS.update(NETWORK_SCHEMAS)
MODELS += list(NETWORK_MODELS)
from branches.models import Branch
MODELS += [Branch]
SCHEMAS.update({'statement_import':('document_id source_sha256 source_system account_ref format parser_version',''),'statement_reconcile':('line_id transaction matching reason allocations','')})
from .balances import sales_open,purchase_open,invoice_settlement

def number(v,positive=False,places=3):
    try:n=D(str(v))
    except (InvalidOperation,ValueError):raise ValueError('Потрібне число.')
    if not n.is_finite() or n.copy_abs()>D('1000000000') or n.as_tuple().exponent < -places:raise ValueError('Число перевищує дозволену точність або розмір.')
    if positive and n<=0:raise ValueError('Кількість має бути більшою за нуль.')
    if not positive and n<0:raise ValueError('Від’ємне значення заборонене.')
    return n

def clean(payload):
    from finance.statements import ACTIONS as STATEMENT_ACTIONS,clean as statement_clean
    if isinstance(payload,dict) and payload.get('action') in STATEMENT_ACTIONS:return statement_clean(payload)
    if not isinstance(payload,dict):raise ValueError('Очікується об’єкт.')
    portable_tree(payload)
    if not isinstance(payload.get('action'),str) or not payload['action'].startswith('erp_'):raise ValueError('Потрібна назва інструмента erp_.')
    a=payload['action'].removeprefix('erp_')
    if a not in SCHEMAS:raise ValueError('Невідомий інструмент ERP.')
    if a in CORRECTION_SCHEMAS:
        from .corrections import clean as correction_clean
        return correction_clean(payload)
    req,opt=map(str.split,SCHEMAS[a]);fields=set(req+opt+['action'])
    if set(payload)-fields or not set(req).issubset(payload):raise ValueError('Перевірте обов’язкові та зайві поля.')
    d=dict(payload)
    for k in ['name','unit','material','reason','note','notes','disposition','operation','kind','method','result']:
        if k in d and not isinstance(d[k],str):raise ValueError('Поле '+k+' має бути текстом.')
    for k,v in d.items():
        if k.endswith('_id'):
            if v in ('',None) and k in opt:d[k]=None;continue
            if type(v)!=int or v<=0:raise ValueError('Потрібен коректний ідентифікатор запису.')
        if isinstance(v,str) and len(v)>4000:raise ValueError('Текст завеликий.')
    for k in ['quantity','price','unit_cost','extras','labor_cost','amount','minimum','planned_cost','defects']:
        if k in d:d[k]=str(number(d[k],positive=k in ['quantity','amount'],places=2 if k in ['price','unit_cost','extras','labor_cost','amount','planned_cost'] else 3))
    from .network_commands import clean_metadata
    d=clean_metadata(a,d)
    for k in ['due_date']:
        if k in d:date.fromisoformat(d[k])
    if 'currency' in d and d['currency'] not in ('EUR','UAH','USD'):raise ValueError('Доступні EUR, UAH, USD.')
    for k in ['code','reference','revision','target_revision']:
        if k in d and (not isinstance(d[k],str) or not 1<=len(d[k].strip())<=60):raise ValueError('Код або версія: 1–60 символів.')
    target={'item':Item,'location':Location,'order':SalesOrder,'opening':Lot,
        'purchase':Purchase,'receive':Lot,'job':Production,'transfer':Lot,
        'operator':OperatorEntry,'finish':Lot,'ship':Movement,'return':Lot,'invoice':Invoice,
        'change':ChangeOrder}.get(a)
    if target is not None:field_values(target,d)
    return d

def reserved(lot):return lot.reservations.aggregate(n=Sum('quantity'))['n'] or ZERO

def free(lot):return lot.quantity-reserved(lot)

def accepted_documents(item,documents):
    from operations.private_storage import PrivateFileError, verified_document_bytes
    if not isinstance(documents,dict):raise ValueError('Документи мають бути словником тип → ID.')
    missing=[]
    for kind in item.required_documents:
        doc=Document.objects.filter(pk=documents.get(kind)).first()
        if not doc or doc.status!='approved' or newest(doc.code).id!=doc.id:
            missing.append(kind)
            continue
        try:
            verified_document_bytes(doc)
        except PrivateFileError:
            missing.append(kind)
    return missing

def usable(lot,revision=None):
    return lot.quality=='approved' and (revision is None or lot.revision==revision) and not accepted_documents(lot.item,lot.documents)

def money_total(value,digits=15):
    if not value.is_finite() or value.copy_abs()>=D(10)**(digits-2):raise ValueError('Загальна сума перевищує допустимий розмір.')
    total=value.quantize(D('.01'))
    return decimal_value(total,digits=digits,places=2,path='Загальна сума')

def move(lot,delta,kind,reference,reason='',*,_source_cost=None,**links):
    new=lot.quantity+delta
    if new<0:raise ValueError('Недостатньо фізичного залишку.')
    if new<reserved(lot):raise ValueError('Рух зачіпає зарезервовану кількість.')
    field_values(Lot,{'quantity':new})
    lot.quantity=new;lot.save(update_fields=['quantity'])
    cost=money_total(abs(delta)*lot.unit_cost) if _source_cost is None else decimal_value(_source_cost,digits=15,places=2,path='Джерельна вартість повернення')
    if cost<0:raise ValueError('Джерельна вартість не може бути від’ємною.')
    return Movement.objects.create(lot=lot,quantity=delta,kind=kind,reference=reference,reason=reason,cost=cost,**links)

def newlot(code,item,location,qty,cost,currency,revision,documents,kind,reference,**links):
    accepted_documents(item,documents)
    field_values(Lot,{'code':code,'revision':revision,'quantity':qty,'unit_cost':cost,'documents':documents})
    lot=Lot.objects.create(code=code,item=item,location=location,unit_cost=cost,currency=currency,revision=revision,documents=documents)
    move(lot,qty,kind,reference,**links);return lot

def material_need(rate,qty):
    need=D(rate)*qty
    if need!=need.quantize(D('.001')):raise ValueError('Потреба компонента менша за точність обліку 0,001. Уточніть одиницю виміру або кількість випуску.')
    return need

def bom_clean(bom):
    if not isinstance(bom,list) or len(bom)>100:raise ValueError('Специфікація: до 100 рядків.')
    ids=set();out=[]
    for b in bom:
        if not isinstance(b,dict) or set(b)!={'item_id','quantity'}:raise ValueError('Компонент: item_id та quantity.')
        item=Item.objects.get(pk=b['item_id'])
        if item.pk in ids:raise ValueError('Об’єднайте однакові компоненти.')
        ids.add(item.pk);out.append({'item_id':item.pk,'quantity':str(number(b['quantity'],True))})
    return out

def routing_clean(routing):
    if not isinstance(routing,list) or not 1<=len(routing)<=30:raise ValueError('Маршрут: 1–30 операцій.')
    names=set()
    for step in routing:
        if not isinstance(step,dict) or set(step)-{'name','instruction','days'} or not isinstance(step.get('name'),str) or not 1<=len(step['name'])<=120:raise ValueError('Операція потребує назви.')
        if step['name'] in names:raise ValueError('Назви операцій мають відрізнятися.')
        names.add(step['name'])
        if type(step.get('days',0))!=int or not 0<=step.get('days',0)<=365:raise ValueError('Тривалість: 0–365 днів.')
        if not isinstance(step.get('instruction',''),str):raise ValueError('Інструкція має бути текстом.')
    return routing

def completed_steps(job):
    latest={}
    for entry in job.entries.order_by('id'):latest[entry.operation]=entry.result
    return {name for name,result in latest.items() if result=='done'}

def fingerprint():
    state={m.__name__:list(m.objects.order_by('pk').values()) for m in MODELS}
    state['invoices']=list(Invoice.objects.order_by('pk').values())
    state['docs']=list(Document.objects.order_by('pk').values('id','checksum','status'))
    from operations.models import ProcurementRequest, SupplierQuote
    state['procurement_requests']=list(ProcurementRequest.objects.order_by('pk').values())
    state['supplier_quotes']=list(SupplierQuote.objects.order_by('pk').values())
    state['dataset']=list(Configuration.objects.filter(key='dataset').values())
    return hashlib.sha256(json.dumps(state,sort_keys=True,default=str).encode()).hexdigest()

def write_lock():
    """Hold the existing ERP mutex until the enclosing transaction finishes."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError('ERP write lock requires transaction.atomic.')
    lock,_=Configuration.objects.get_or_create(key='erp_write',defaults={'value':{'revision':0}})
    Configuration.objects.filter(pk=lock.pk).update(value={'revision':lock.value.get('revision',0)+1})

@transaction.atomic
def dispatch(payload,role='manager',log=True,*,import_context=None,import_phase=None,correction_actor=None):
    if role not in ('ceo','manager'):raise PermissionError('Недостатньо прав.')
    d=clean(payload);a=d.pop('action').removeprefix('erp_')
    # Serialize ERP writes on SQLite; all work rolls back with the proposal receipt.
    write_lock()
    out={}
    if a in ('statement_import','statement_reconcile'):
        raise ValueError('Виписка потребує перевіреного preview/confirm з поточним CEO; загальний dispatcher її не проводить.')
    if a in CORRECTION_SCHEMAS:
        from .corrections import apply
        return apply({'action':'erp_'+a,**d},correction_actor,role)
    if a in NETWORK_SCHEMAS:
        from .network_commands import apply
        out=apply(a,d,role)
    elif a=='import_batch':
        from .importing import apply_batch
        out=apply_batch(d['batch'],import_context,import_phase)
    elif a=='item':
        if d['kind'] not in ('product','material','component') or d['method'] not in ('buy','make','subcontract'):raise ValueError('Невідомий тип номенклатури.')
        if not isinstance(d['name'],str) or not 1<=len(d['name'])<=200 or not 1<=len(d['unit'])<=20:raise ValueError('Перевірте назву та одиницю.')
        d['bom']=bom_clean(d.get('bom',[]));d['routing']=routing_clean(d.get('routing') or [{'name':'Виготовлення','instruction':'Виконати погоджену операцію','days':1}])
        if not isinstance(d.get('external_codes',{}),dict) or not isinstance(d.get('required_documents',[]),list) or any(not isinstance(x,str) for x in d.get('required_documents',[])):raise ValueError('Неправильний формат кодів або документів.')
        if type(d.get('lead_days',7))!=int or not 0<=d.get('lead_days',7)<=730:raise ValueError('Строк: 0–730 днів.')
        obj=Item.objects.create(**d);out={'item_id':obj.id,'code':obj.code}
    elif a=='location':
        if d['kind'] not in ('warehouse','production','supplier'):raise ValueError('Невідомий тип місця.')
        if d['kind']=='supplier':Counterparty.objects.get(pk=d.get('supplier_id'),type='supplier')
        from .network_commands import check_location_metadata
        check_location_metadata(d)
        obj=Location.objects.create(**d);out={'location_id':obj.id,'code':obj.code}
    elif a=='order':
        lines=d.pop('lines');customer=Counterparty.objects.get(pk=d['customer_id'],type='customer');Employee.objects.get(pk=d['owner_id'])
        if not isinstance(lines,list) or not 1<=len(lines)<=100:raise ValueError('Замовлення потребує 1–100 позицій.')
        obj=SalesOrder.objects.create(**d)
        for line in lines:
            if set(line)!={'item_id','quantity','price'}:raise ValueError('Позиція: item_id, quantity, price.')
            item=Item.objects.get(pk=line['item_id'])
            SalesLine.objects.create(order=obj,item=item,revision=item.revision,quantity=number(line['quantity'],True),price=number(line['price'],places=2))
        out={'order_id':obj.id,'code':obj.code}
    elif a=='confirm_order':
        obj=SalesOrder.objects.get(pk=d['order_id'])
        if obj.status!='quote':raise ValueError('Пропозицію вже підтверджено.')
        obj.status='confirmed';obj.save();out={'order_id':obj.id,'status':obj.status}
    elif a=='opening':
        item=Item.objects.get(pk=d['item_id']);loc=Location.objects.get(pk=d['location_id'])
        obj=newlot(d['code'],item,loc,D(d['quantity']),D(d['unit_cost']),d['currency'],d['revision'],d.get('documents',{}),'opening',d['code'],reason=d.get('reason','Початковий залишок'))
        out={'lot_id':obj.id,'code':obj.code,'quality':obj.quality}
    elif a=='purchase':
        item=Item.objects.get(pk=d['item_id']);Counterparty.objects.get(pk=d['supplier_id'],type='supplier')
        if d.get('production_id'):
            job=Production.objects.get(pk=d['production_id'])
            if item.pk not in [b['item_id'] for b in job.bom]:raise ValueError('Матеріал не входить до специфікації роботи.')
        from .procurement import purchase_source
        if import_context is None:
            d=purchase_source(d,item);original_due=d['due_date']
        else:
            from .importing import historical_purchase
            d,original_due=historical_purchase(d,item,import_context,import_phase)
        obj=Purchase.objects.create(original_due=original_due,**d);out={'purchase_id':obj.id,'code':obj.code}
    elif a=='receive':
        po=Purchase.objects.get(pk=d['purchase_id']);qty=D(d['quantity'])
        if po.destination_id is not None and po.destination_id!=d['location_id']:raise ValueError('Приймання має відбутися в погодженій точці призначення закупівлі.')
        if qty>purchase_open(po):raise ValueError('Надходження перевищує залишок замовлення.')
        unit=(po.price+po.extras/po.quantity).quantize(D('.01'))
        obj=newlot(d['code'],po.item,Location.objects.get(pk=d['location_id']),qty,unit,po.currency,po.revision,d.get('documents',{}),'receipt',po.code,purchase=po)
        po.received+=qty;po.status='received' if po.received==po.quantity else 'partial';po.save();out={'lot_id':obj.id,'code':obj.code,'quality':'pending'}
    elif a=='job':
        item=Item.objects.get(pk=d['item_id']);loc=Location.objects.get(pk=d['location_id']);qty=D(d['quantity'])
        if not item.bom:raise ValueError('Спочатку задайте склад виробу в номенклатурі.')
        for b in item.bom:material_need(b['quantity'],qty)
        if item.method=='subcontract' and loc.kind!='supplier':raise ValueError('Для підрядного виробництва потрібне місце постачальника.')
        if item.method=='make' and loc.kind!='production':raise ValueError('Оберіть виробничу дільницю.')
        if d.get('line_id'):
            line=SalesLine.objects.get(pk=d['line_id'])
            if line.revision!=item.revision:raise ValueError('Версія номенклатури відрізняється від прийнятого продажу. Потрібне окреме узгодження специфікації.')
            if line.item_id!=item.id or line.order.status!='confirmed':raise ValueError('Потрібна підтверджена відповідна позиція продажу.')
            allocated=sum((x.quantity-x.produced for x in Production.objects.filter(line=line).exclude(status='done')),ZERO)
            if qty>sales_open(line)-allocated:raise ValueError('Кількість перевищує невиконану потребу позиції.')
        Employee.objects.get(pk=d['owner_id'])
        obj=Production.objects.create(revision=item.revision,bom=item.bom,routing=item.routing,currency=item.currency,planned_cost=money_total(qty*item.planned_cost),**d);out={'production_id':obj.id,'code':obj.code}
    elif a=='reserve':
        lot=Lot.objects.select_related('item').get(pk=d['lot_id']);qty=D(d['quantity']);line_id=d.get('line_id');job_id=d.get('production_id')
        if bool(line_id)==bool(job_id):raise ValueError('Оберіть або продаж, або виробництво.')
        if not usable(lot) or qty>free(lot):raise ValueError('Недостатньо доступного придатного залишку.')
        if line_id:
            line=SalesLine.objects.get(pk=line_id)
            if line.order.status!='confirmed' or line.item_id!=lot.item_id or line.revision!=lot.revision:raise ValueError('Не відповідає замовлення, виріб або версія.')
            have=line.reservations.aggregate(n=Sum('quantity'))['n'] or ZERO
            if qty>sales_open(line)-have:raise ValueError('Резерв перевищує потребу замовлення.')
        else:
            job=Production.objects.get(pk=job_id)
            if job.status=='done' or job.needs_review or lot.location_id!=job.location_id:raise ValueError('Матеріал має бути на дільниці роботи; робота має бути погоджена.')
            b=next((x for x in job.bom if x['item_id']==lot.item_id),None)
            if not b:raise ValueError('Матеріал не входить до специфікації.')
            have=job.reservations.filter(lot__item=lot.item).aggregate(n=Sum('quantity'))['n'] or ZERO
            if qty>D(b['quantity'])*(job.quantity-job.produced)-have:raise ValueError('Резерв перевищує залишкову потребу виробництва.')
        obj=Reservation.objects.create(lot=lot,line_id=line_id,production_id=job_id,quantity=qty);out={'reservation_id':obj.id,'quantity':str(qty)}
    elif a=='release':
        obj=Reservation.objects.get(pk=d['reservation_id']);qty=D(d['quantity'])
        if qty>obj.quantity:raise ValueError('Звільнення перевищує резерв.')
        obj.quantity-=qty;obj.save();out={'reservation_id':obj.id,'remaining':str(obj.quantity)}
    elif a=='transfer':
        lot=Lot.objects.get(pk=d['lot_id']);qty=D(d['quantity']);loc=Location.objects.get(pk=d['location_id'])
        if qty>free(lot) or loc.pk==lot.location_id:raise ValueError('Переміщення: перевірте вільний залишок та місце.')
        job=Production.objects.get(pk=d['production_id']) if d.get('production_id') else None
        if job and (loc.pk!=job.location_id or lot.item_id not in [x['item_id'] for x in job.bom]):raise ValueError('Місце або матеріал не відповідають роботі.')
        move(lot,-qty,'transfer_out',d['code'],d['reason'],production=job)
        obj=newlot(d['code'],lot.item,loc,qty,lot.unit_cost,lot.currency,lot.revision,lot.documents,'transfer_in',lot.code,production=job);obj.quality=lot.quality;obj.save();out={'lot_id':obj.id,'code':obj.code}
    elif a=='attach':
        lot=Lot.objects.get(pk=d['lot_id']);doc=Document.objects.get(pk=d['document_id']);lot.documents={**lot.documents,d['kind']:doc.id};lot.save();out={'lot_id':lot.id,'document_id':doc.id}
    elif a=='quality':
        lot=Lot.objects.select_related('item').get(pk=d['lot_id']);Employee.objects.get(pk=d['inspector_id'])
        if d['result'] not in ('approved','blocked','rework'):raise ValueError('Невідомий результат перевірки.')
        if not d['note'].strip():raise ValueError('Вкажіть підставу рішення.')
        missing=accepted_documents(lot.item,lot.documents)
        if d['result']=='approved' and missing:raise ValueError('Немає чинних перевірених документів: '+', '.join(missing))
        lot.quality=d['result'];lot.save();obj=Inspection.objects.create(lot=lot,result=d['result'],inspector_id=d['inspector_id'],note=d['note']);out={'inspection_id':obj.id,'lot_id':lot.id,'quality':lot.quality}
    elif a=='start':
        job=Production.objects.get(pk=d['production_id'])
        if job.status!='planned' or job.needs_review:raise ValueError('Роботу не можна розпочати в поточному стані.')
        for b in job.bom:
            available=sum((r.quantity for r in job.reservations.filter(lot__item_id=b['item_id']) if usable(r.lot)),ZERO)
            if available<D(b['quantity'])*job.quantity:raise ValueError('Не всі матеріали зарезервовані й дозволені до використання.')
        job.status='running';job.save();out={'production_id':job.id,'status':job.status}
    elif a=='operator':
        job=Production.objects.get(pk=d['production_id'])
        if job.status!='running' or job.needs_review:raise ValueError('Робота не виконується або потребує погодження.')
        steps=[x['name'] for x in job.routing]
        if d['operation'] not in steps or d['result'] not in ('done','paused','defect'):raise ValueError('Невідома операція або результат.')
        if type(d['minutes'])!=int or not 0<=d['minutes']<=100000:raise ValueError('Перевірте витрачений час.')
        done=completed_steps(job)
        if any(x not in done for x in steps[:steps.index(d['operation'])]):raise ValueError('Спершу завершіть попередні операції.')
        Employee.objects.get(pk=d['operator_id']);obj=OperatorEntry.objects.create(**d);out={'entry_id':obj.id,'production_id':job.id}
    elif a=='finish':
        job=Production.objects.get(pk=d['production_id']);qty=D(d['quantity'])
        if job.status!='running' or job.needs_review or qty>job.quantity-job.produced:raise ValueError('Перевірте стан, погодження й залишок виробництва.')
        done=completed_steps(job)
        if any(x['name'] not in done for x in job.routing):raise ValueError('Не всі операції маршруту завершено.')
        cost=D(d['labor_cost']);lots={}
        for b in job.bom:
            need=material_need(b['quantity'],qty)
            for r in job.reservations.filter(lot__item_id=b['item_id']).select_related('lot__item').order_by('id'):
                # select_related creates a separate stale Lot per reservation.
                lot=lots.setdefault(r.lot_id,r.lot)
                if not usable(lot):continue
                if lot.currency!=job.currency:raise ValueError('Для собівартості потрібен погоджений валютний курс.')
                take=min(need,r.quantity)
                if not take:continue
                r.quantity-=take;r.save();move(lot,-take,'consume',job.code,production=job);cost+=take*lot.unit_cost;need-=take
                if not need:break
            if need:raise ValueError('Бракує зарезервованих матеріалів.')
        obj=newlot(d['code'],job.item,Location.objects.get(pk=d['location_id']),qty,(cost/qty).quantize(D('.01')),job.currency,job.revision,d.get('documents',{}),'production',job.code,production=job)
        job.produced+=qty;job.actual_cost=money_total(job.actual_cost+cost);job.status='done' if job.produced==job.quantity else 'running';job.save();out={'lot_id':obj.id,'production_id':job.id,'cost':str(cost.quantize(D('.01'))),'quality':'pending'}
    elif a=='ship':
        line=SalesLine.objects.get(pk=d['line_id']);lot=Lot.objects.get(pk=d['lot_id']);qty=D(d['quantity'])
        if line.order.fulfillment_location_id is not None and lot.location_id!=line.order.fulfillment_location_id:raise ValueError('Відвантаження має бути з погодженої точки виконання замовлення.')
        if line.order.status!='confirmed' or line.item_id!=lot.item_id or not usable(lot,line.revision):raise ValueError('Позиція або якість/версія партії не дозволяє відвантаження.')
        if lot.currency!=line.order.currency:raise ValueError('Для обліку собівартості потрібна одна валюта або погоджений курс.')
        if qty>sales_open(line):raise ValueError('Перевищено залишок замовлення.')
        need=qty
        for r in line.reservations.filter(lot=lot).order_by('id'):
            take=min(need,r.quantity);r.quantity-=take;r.save();need-=take
        if need:raise ValueError('Спершу зарезервуйте цю партію для замовлення.')
        move(lot,-qty,'shipment',d['reference'],line=line);line.shipped+=qty;line.save();out={'line_id':line.id,'shipped':str(qty),'reference':d['reference']}
    elif a=='return':
        line=SalesLine.objects.get(pk=d['line_id']);lot=Lot.objects.get(pk=d['lot_id']);qty=D(d['quantity'])
        shipped=-(Movement.objects.filter(lot=lot,line=line,kind='shipment').aggregate(n=Sum('quantity'))['n'] or ZERO)
        returned=Movement.objects.filter(line=line,kind='return',reference=lot.code).aggregate(n=Sum('quantity'))['n'] or ZERO
        if qty>shipped-returned:raise ValueError('Повернення перевищує відвантажену кількість цієї партії.')
        obj=newlot(d['code'],line.item,Location.objects.get(pk=d['location_id']),qty,lot.unit_cost,lot.currency,lot.revision,lot.documents,'return',lot.code,line=line,reason=d['reason']);obj.quality='blocked';obj.save()
        # Delivered/invoiced history remains intact; return is a separate event, not a silent credit note.
        out={'lot_id':obj.id,'quality':'blocked','note':'Повернення зареєстровано. Фінансове коригування та заміна потребують окремого рішення.'}
    elif a=='invoice':
        order=SalesOrder.objects.get(pk=d['order_id']);rows=[];total=ZERO
        for line in order.lines.all():
            qty=line.shipped-line.invoiced
            if qty:rows.append({'line_id':line.id,'quantity':str(qty),'price':str(line.price)});total+=qty*line.price;line.invoiced+=qty;line.save()
        if not rows:raise ValueError('Немає відвантажень, за якими ще не створено рахунок.')
        total=money_total(total,digits=Invoice._meta.get_field('amount').max_digits)
        invoice=Invoice.objects.create(code=d['code'],customer=order.customer,amount=total,currency=order.currency,due_date=d['due_date']);InvoiceLink.objects.create(invoice=invoice,order=order,lines=rows);out={'invoice_id':invoice.id,'code':invoice.code,'amount':str(total)}
    elif a=='payment':
        from .payments import post_payment
        out=post_payment(d['invoice_id'],d['amount'],d['reference'],role=role)
    elif a=='change':
        from operations.private_storage import verified_document_bytes
        Item.objects.get(pk=d['item_id']);doc=Document.objects.get(pk=d['document_id'])
        if doc.status!='approved' or newest(doc.code).id!=doc.id or doc.revision!=d['target_revision']:raise ValueError('Оберіть перевірений актуальний документ відповідної версії.')
        verified_document_bytes(doc)
        obj=ChangeOrder.objects.create(**d);out={'change_id':obj.id,'code':obj.code}
    elif a=='apply_change':
        from operations.private_storage import verified_document_bytes
        if role!='ceo':raise PermissionError('Зміну версії затверджує керівник.')
        obj=ChangeOrder.objects.get(pk=d['change_id'])
        if obj.status!='draft' or not d['disposition'].strip():raise ValueError('Потрібне рішення щодо незавершених робіт.')
        if obj.document.status!='approved' or newest(obj.document.code).id!=obj.document_id:raise ValueError('Документ зміни більше не є перевіреною актуальною версією.')
        verified_document_bytes(obj.document)
        obj.item.revision=obj.target_revision;obj.item.document=obj.document;obj.item.save()
        ids=list(Production.objects.filter(item=obj.item).exclude(status='done').values_list('id',flat=True));Production.objects.filter(pk__in=ids).update(needs_review=True)
        obj.status='approved';obj.disposition=d['disposition'];obj.save();out={'change_id':obj.id,'affected_jobs':ids,'note':'Відкриті роботи призупинено до окремого погодження; версію прийнятих продажів автоматично не змінено.'}
    elif a=='resolve_job':
        if role!='ceo':raise PermissionError('Рішення щодо старої версії затверджує керівник.')
        job=Production.objects.get(pk=d['production_id'])
        if not job.needs_review or not d['disposition'].strip():raise ValueError('Потрібна робота на перегляді та обґрунтування.')
        job.needs_review=False;job.save();out={'production_id':job.id,'revision':job.revision,'note':'Дозволено продовження за зафіксованою старою версією: '+d['disposition']}
    elif a in ('postpone','postpone_job'):
        obj=Purchase.objects.get(pk=d['purchase_id']) if a=='postpone' else Production.objects.get(pk=d['production_id'])
        if not d['reason'].strip():raise ValueError('Потрібна причина зміни дати.')
        obj.due_date=date.fromisoformat(d['due_date']);obj.save();out={'id':obj.id,'code':obj.code,'due_date':str(obj.due_date)}
    elif a=='adjust':
        if role!='ceo':raise PermissionError('Коригування залишку затверджує керівник.')
        try:delta=D(str(d['delta']))
        except InvalidOperation:raise ValueError('Некоректна кількість.')
        if not delta.is_finite() or delta.copy_abs()>1000000 or delta.as_tuple().exponent < -3 or not d['reason'].strip():raise ValueError('Потрібні кількість і підстава.')
        lot=Lot.objects.get(pk=d['lot_id']);move(lot,delta,'adjustment',lot.code,d['reason']);out={'lot_id':lot.id,'quantity':str(lot.quantity)}
    if log:
        event=Event.objects.create(action='erp_'+a,payload=payload,result=out,role=role);out['erp_event_id']=event.id
    return out

def preview_effect(payload,role):
    with transaction.atomic():
        out=dispatch(payload,role,log=False)
        transaction.set_rollback(True)
    return out
