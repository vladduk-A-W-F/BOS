"""Six source-bound correction writers; no history repair, cash refund or AP."""
from copy import deepcopy
from datetime import date
from decimal import Decimal as D
from fractions import Fraction
import hashlib,json,re
from types import SimpleNamespace
from uuid import UUID
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Sum
from boss_project.data_rules import portable_tree,field_values
from boss_project.identity import Actor,actor_for_user
from boss_project.policy import Policy
from operations.models import Invoice,Document
from operations.service import as_of,Conflict
from .models import (OrderCancellation,CancellationRelease,GoodsReturn,SupplierClaim,InvoiceAdjustment,
    InvoiceAdjustmentLine,SalesLine,Purchase,Reservation,Production,Movement,Lot,Location,InvoiceLink,Event)
from .balances import exact,money,quantity_text,money_text,cancelled_quantity,sales_open,purchase_open,active_credits,settlement_strings

COMMON='operation_id code reason business_date '
SCHEMAS={
 'cancel_remaining':(COMMON+'quantity','line_id purchase_id'),
 'return_supplier':(COMMON+'receipt_id quantity',''),
 'return_from_shipment':(COMMON+'shipment_id quantity location_id',''),
 'credit_invoice':(COMMON+'invoice_id basis allocations','source_document_id'),
 'reverse_credit':(COMMON+'credit_id',''),
 'confirm_supplier_claim':(COMMON+'claim_id amount currency source_document_id','')}
ACTIONS={'erp_'+name for name in SCHEMAS}
FINANCIAL={'erp_credit_invoice','erp_reverse_credit','erp_confirm_supplier_claim'}
MODELS=(OrderCancellation,CancellationRelease,GoodsReturn,SupplierClaim,InvoiceAdjustment,InvoiceAdjustmentLine)
DOCUMENT_MODELS={'cancel_remaining':OrderCancellation,'return_supplier':GoodsReturn,'return_from_shipment':GoodsReturn,
    'credit_invoice':InvoiceAdjustment,'reverse_credit':InvoiceAdjustment,'confirm_supplier_claim':SupplierClaim}


def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def uuid(value):
    if not isinstance(value,str):raise ValueError('Потрібен canonical UUID4 наміру.')
    parsed=UUID(value)
    if parsed.version!=4 or str(parsed)!=value:raise ValueError('Потрібен canonical UUID4 наміру.')
    return value


def numeric(value,places,positive=False):
    from .service import number
    if not isinstance(value,str) or not re.fullmatch(r'\d+(?:\.\d+)?',value):raise ValueError('Число передається десятковим рядком без exponent.')
    return format(number(value,positive,places),'.'+str(places)+'f')


@exact
def clean(payload):
    portable_tree(payload);name=payload['action'].removeprefix('erp_');required,optional=map(str.split,SCHEMAS[name])
    if set(payload)-set(required+optional+['action']) or not set(required)<=set(payload):raise ValueError('Перевірте обов’язкові й зайві поля коригування.')
    d=deepcopy(payload);uuid(d['operation_id'])
    if not isinstance(d['code'],str) or not 1<=len(d['code'])<=60 or not d['code'].strip():raise ValueError('Код:1–60 символів без прихованого обрізання.')
    if not isinstance(d['reason'],str) or not 3<=len(d['reason'].strip())<=1000:raise ValueError('Потрібна явна причина:3–1000 символів.')
    d['reason']=d['reason'].strip()
    if not isinstance(d['business_date'],str) or date.fromisoformat(d['business_date']).isoformat()!=d['business_date']:raise ValueError('Потрібна ISO дата.')
    for key,value in d.items():
        if key.endswith('_id') and key!='operation_id' and (type(value) is not int or value<=0):raise ValueError('Потрібен фактичний integer ID.')
    if 'quantity' in d:d['quantity']=numeric(d['quantity'],3,True)
    if 'amount' in d:d['amount']=numeric(d['amount'],2)
    if 'currency' in d and d['currency'] not in ('EUR','USD','UAH'):raise ValueError('Валюти не конвертуються автоматично.')
    if name=='cancel_remaining' and (('line_id' in d)==('purchase_id' in d)):raise ValueError('Оберіть рівно одну позицію продажу або закупівлю.')
    if name=='credit_invoice':
        if d['basis'] not in ('return','commercial') or (('source_document_id' in d)!=(d['basis']=='commercial')):raise ValueError('Уточніть підставу credit і джерельний документ.')
        if not isinstance(d['allocations'],list) or not 1<=len(d['allocations'])<=30:raise ValueError('Потрібно1–30 allocations.')
        seen=set();rows=[]
        for row in d['allocations']:
            keys={'return_id','invoice_line_index','quantity'} if d['basis']=='return' else {'invoice_line_index','amount'}
            if not isinstance(row,dict) or set(row)!=keys:raise ValueError('Allocation має невідомі або відсутні поля.')
            if type(row['invoice_line_index']) is not int or row['invoice_line_index']<0:raise ValueError('Потрібен integer ordinal рахунку.')
            if 'return_id' in row and (type(row['return_id']) is not int or row['return_id']<=0):raise ValueError('Потрібен actual ID повернення.')
            key=(row.get('return_id'),row['invoice_line_index'])
            if key in seen:raise ValueError('Allocation source повторено.')
            seen.add(key);row=deepcopy(row);field='quantity' if d['basis']=='return' else 'amount';row[field]=numeric(row[field],3 if field=='quantity' else 2,field=='quantity');rows.append(row)
        d['allocations']=sorted(rows,key=lambda row:(row['invoice_line_index'],row.get('return_id',0)))
    return d


def principal(value,role):
    if type(value) is not Actor:raise PermissionError('Коригування потребує server identity.')
    fresh=actor_for_user(get_user_model().objects.get(pk=value.user_id))
    if fresh!=value or fresh.role!=role:raise PermissionError('Повноваження змінилися.')
    return fresh


def policy_for(who):return Policy(SimpleNamespace(user=get_user_model().objects.get(pk=who.user_id),session={}))


def replay(payload,who):
    policy=policy_for(who);policy.action(payload)
    model=DOCUMENT_MODELS[payload['action'].removeprefix('erp_')]
    row=model.objects.filter(operation_id=payload['operation_id']).select_related('event').first()
    if row is None:return None
    if row.payload_hash!=digest(payload) or row.event.action!=payload['action']:raise Conflict('operation_id вже має інший первісний намір.')
    policy.action(row.event.payload)
    policy.queryset(model).get(pk=row.pk)
    result=row.event.result
    if not isinstance(result,dict) or result.get('state')!='succeeded' or result.get('erp_event_id')!=row.event_id:raise Conflict('Первинний результат коригування не підтверджено.')
    return deepcopy(result)


def source_document(pk,policy):
    from .procurement import document_source
    document=policy.document(pk)
    if document.status!='approved':raise ValueError('Потрібен перевірений актуальний документ.')
    return document,document_source(document)


def source_movement(pk,kind,policy):
    obj=Movement.objects.select_related('lot__item','purchase','line__order').get(pk=pk)
    if obj.kind!=kind or (kind=='receipt' and (obj.quantity<=0 or obj.purchase_id is None)) or (kind=='shipment' and (obj.quantity>=0 or obj.line_id is None)):
        raise ValueError('Оберіть збережений рух потрібного виду з фактичним джерелом.')
    policy.check_reference('receipt_id' if kind=='receipt' else 'shipment_id',pk)
    if kind=='receipt' and (obj.lot.item_id!=obj.purchase.item_id or obj.lot.revision!=obj.purchase.revision or obj.lot.currency!=obj.purchase.currency):raise ValueError('Партія й джерельна закупівля не узгоджені.')
    if kind=='shipment' and (obj.lot.item_id!=obj.line.item_id or obj.lot.revision!=obj.line.revision or obj.lot.currency!=obj.line.order.currency):raise ValueError('Партія й джерельне відвантаження не узгоджені.')
    return obj


def source_snapshot(source):
    lot=source.lot
    return {'movement_id':source.pk,'kind':source.kind,'quantity':quantity_text(source.quantity),'cost':money_text(source.cost),
        'lot_id':lot.pk,'lot_code':lot.code,'item_id':lot.item_id,'revision':lot.revision,'currency':lot.currency,'unit_cost':money_text(lot.unit_cost),
        'documents':deepcopy(lot.documents),'purchase_id':source.purchase_id,'line_id':source.line_id,'reference':source.reference,'created_at':source.created_at.isoformat()}


@exact
def return_cost(source,qty):
    existing=list(GoodsReturn.objects.filter(source=source));prior=sum((r.quantity for r in existing),D(0));prior_cost=sum((r.allocated_cost for r in existing),D(0))
    if qty+prior>abs(source.quantity):raise ValueError('Повернення перевищує фактичне джерело.')
    return money(Fraction(source.cost)*Fraction(qty+prior)/Fraction(abs(source.quantity)))-prior_cost


@exact
def invoice_basis(invoice):
    link=InvoiceLink.objects.select_related('order').get(invoice=invoice)
    if link.order.customer_id!=invoice.customer_id or link.order.currency!=invoice.currency:raise ValueError('Рахунок не відповідає джерельному клієнту або валюті.')
    if not isinstance(link.lines,list) or not link.lines:raise ValueError('Рахунок не має source line snapshot.')
    cumulative=Fraction(0);prior=D(0);rows=[]
    for index,entry in enumerate(link.lines):
        if not isinstance(entry,dict) or set(entry)!={'line_id','quantity','price'} or type(entry['line_id']) is not int:raise ValueError('Неповний первинний snapshot рахунку.')
        line=SalesLine.objects.get(pk=entry['line_id'],order=link.order);quantity=numeric(entry['quantity'],3,True);price=numeric(entry['price'],2)
        raw=Fraction(D(quantity))*Fraction(D(price));cumulative+=raw;rounded=money(cumulative);budget=rounded-prior;prior=rounded
        rows.append({'index':index,'line_id':line.pk,'quantity':quantity,'price':price,'raw_value':format(D(quantity)*D(price),'.5f'),'budget':money_text(budget)})
    if prior!=invoice.amount:raise ValueError('Первісний amount не відповідає source lines; автоматичний credit відхилено.')
    basis={'invoice_id':invoice.pk,'code':invoice.code,'amount':money_text(invoice.amount),'currency':invoice.currency,'customer_id':invoice.customer_id,'lines':rows};basis['hash']=digest(basis)
    for old in InvoiceAdjustment.objects.filter(invoice=invoice):
        if old.basis_hash!=basis['hash'] or old.basis_snapshot!=basis:raise ValueError('Первісна база credit змінилася; історія не ремонтується.')
    return basis


def base_fields(payload,who,event):
    return {'operation_id':payload['operation_id'],'payload_hash':digest(payload),'code':payload['code'],'reason':payload['reason'],
        'business_date':payload['business_date'],'actor_id':who.user_id,'event':event}


@exact
def apply(payload,who,role):
    who=principal(who,role);payload=clean(payload);policy=policy_for(who);policy.action(payload)
    existing=replay(payload,who)
    if existing is not None:return existing
    if date.fromisoformat(payload['business_date'])>as_of():raise ValueError('Дата дії не може бути пізніше поточного зрізу.')
    if DOCUMENT_MODELS[payload['action'].removeprefix('erp_')].objects.filter(code=payload['code']).exists():raise Conflict('Код документа вже зайнято іншим наміром.')
    event=Event.objects.create(action=payload['action'],payload=payload,result={},role=role)
    fields=base_fields(payload,who,event);name=payload['action'].removeprefix('erp_');qty=D(payload.get('quantity','0'))
    from .service import move,newlot,free,reserved,dispatch
    if name=='cancel_remaining':
        is_sale='line_id' in payload;target=SalesLine.objects.get(pk=payload['line_id']) if is_sale else Purchase.objects.get(pk=payload['purchase_id'])
        opened=sales_open(target) if is_sale else purchase_open(target)
        if is_sale and target.order.status!='confirmed':raise ValueError('Скасування потребує підтвердженого замовлення.')
        if (is_sale and Production.objects.filter(line=target).exclude(status='done').exists()) or (not is_sale and target.production_id and target.production.status!='done'):raise ValueError('Незавершене виробництво потребує окремого рішення; залишок не скасовано.')
        if qty>opened:raise ValueError('Скасування перевищує невиконаний залишок.')
        before={'quantity':quantity_text(target.quantity),'executed':quantity_text(target.shipped if is_sale else target.received),'cancelled_quantity':quantity_text(cancelled_quantity(target)),'open_quantity':quantity_text(opened)}
        after={**before,'cancelled_quantity':quantity_text(cancelled_quantity(target)+qty),'open_quantity':quantity_text(opened-qty)}
        row=OrderCancellation.objects.create(**fields,quantity=qty,before_snapshot=before,after_snapshot=after,**{'line' if is_sale else 'purchase':target});released=[]
        if is_sale:
            reservations=list(target.reservations.filter(quantity__gt=0).order_by('-pk'));needed=max(sum((r.quantity for r in reservations),D(0))-(opened-qty),D(0))
            for reservation in reservations:
                amount=min(needed,reservation.quantity)
                if amount<=0:break
                policy.check_reference('reservation_id',reservation.pk);old=reservation.quantity
                dispatch({'action':'erp_release','reservation_id':reservation.pk,'quantity':quantity_text(amount)},role=role,log=False)
                CancellationRelease.objects.create(cancellation=row,reservation=reservation,quantity=amount,before_quantity=old,after_quantity=old-amount)
                released.append({'reservation_id':reservation.pk,'quantity':quantity_text(amount),'before_quantity':quantity_text(old),'after_quantity':quantity_text(old-amount)});needed-=amount
        out={'cancellation_id':row.pk,'line_id' if is_sale else 'purchase_id':target.pk,'cancelled_quantity':after['cancelled_quantity'],'effective_open':after['open_quantity'],'released':released}
    elif name in ('return_supplier','return_from_shipment'):
        supplier=name=='return_supplier';source=source_movement(payload['receipt_id'] if supplier else payload['shipment_id'],'receipt' if supplier else 'shipment',policy);lot=source.lot
        if supplier:
            if lot.movements.filter(quantity__gt=0).exclude(pk=source.pk).exists():raise ValueError('Походження партії неоднозначне: додано інший позитивний рух.')
            negatives=-(lot.movements.filter(quantity__lt=0).aggregate(n=Sum('quantity'))['n'] or D(0))
            if qty>source.quantity-negatives or qty>free(lot):raise ValueError('Повернення зачіпає виконаний рух або поточний резерв.')
        else:
            history=Movement.objects.filter(kind='return',line=source.line,reference=lot.code)
            if history.exclude(pk__in=GoodsReturn.objects.filter(direction='customer').values('result_id')).exists():raise ValueError('Є історичне повернення без точної source allocation; потрібне явне зіставлення.')
            shipped=-(Movement.objects.filter(kind='shipment',lot=lot,line=source.line).aggregate(n=Sum('quantity'))['n'] or D(0));returned=history.aggregate(n=Sum('quantity'))['n'] or D(0)
            if qty>shipped-returned:raise ValueError('Повернення перевищує відвантаження цієї lot/line.')
        cost=return_cost(source,qty);snapshot=source_snapshot(source)
        if supplier:
            result=move(lot,-qty,'supplier_return',payload['code'],payload['reason'],purchase=source.purchase,_source_cost=cost)
        else:
            location=Location.objects.get(pk=payload['location_id']);result_lot=newlot(payload['code'],lot.item,location,qty,lot.unit_cost,lot.currency,lot.revision,lot.documents,'return',lot.code,line=source.line,reason=payload['reason'],_source_cost=cost)
            result_lot.quality='blocked';result_lot.save(update_fields=['quality']);result=result_lot.movements.get(kind='return')
        row=GoodsReturn.objects.create(**fields,direction='supplier' if supplier else 'customer',source=source,result=result,quantity=qty,source_quantity=abs(source.quantity),source_cost=source.cost,currency=lot.currency,unit_cost=lot.unit_cost,allocated_cost=cost,source_snapshot=snapshot)
        out={'goods_return_id':row.pk,'receipt_id' if supplier else 'shipment_id':source.pk,'movement_id':result.pk,'lot_id':result.lot_id,'quantity':quantity_text(qty),'currency':lot.currency,'allocated_cost':money_text(cost)}
        if supplier:
            claim=SupplierClaim.objects.create(record_kind='pending',returned_goods=row,currency=lot.currency,actor_id=who.user_id,event=event,code='CLM-'+UUID(payload['operation_id']).hex,reason=payload['reason'],business_date=payload['business_date'])
            out['claim_id']=claim.pk
    elif name=='confirm_supplier_claim':
        pending=SupplierClaim.objects.select_related('returned_goods').get(pk=payload['claim_id'])
        if pending.record_kind!='pending' or pending.returned_goods.direction!='supplier' or SupplierClaim.objects.filter(parent=pending).exists():raise ValueError('Потрібна ще не підтверджена вимога постачальнику.')
        if payload['currency']!=pending.currency or date.fromisoformat(payload['business_date'])<pending.business_date:raise ValueError('Валюта або дата підтвердження не відповідає вимозі.')
        doc,snapshot=source_document(payload['source_document_id'],policy)
        row=SupplierClaim.objects.create(**fields,record_kind='confirmation',parent=pending,returned_goods=pending.returned_goods,agreed_amount=payload['amount'],currency=pending.currency,source_document=doc,source_snapshot=snapshot)
        out={'supplier_claim_id':row.pk,'parent_claim_id':pending.pk,'goods_return_id':pending.returned_goods_id,'amount':money_text(D(payload['amount'])),'currency':pending.currency}
    else:
        out=credit_action(payload,fields,policy)
    receipt={'state':'succeeded','action':payload['action'],'operation_id':payload['operation_id'],'erp_event_id':event.pk,'actor_id':who.user_id,'actor_role':who.role,'impact':[],**out}
    event.result=receipt;event.save(update_fields=['result']);return receipt


@exact
def credit_action(payload,fields,policy):
    reverse=payload['action']=='erp_reverse_credit'
    if reverse:
        original=InvoiceAdjustment.objects.select_related('invoice').get(pk=payload['credit_id'])
        if original.kind!='credit' or InvoiceAdjustment.objects.filter(reversed_credit=original).exists():raise ValueError('Сторнувати можна тільки один ще не сторнований credit повністю.')
        if date.fromisoformat(payload['business_date'])<original.business_date:raise ValueError('Дата reversal не може передувати credit.')
        invoice=original.invoice;basis=invoice_basis(invoice)
        document=InvoiceAdjustment.objects.create(**fields,kind='reversal',basis='reversal',invoice=invoice,reversed_credit=original,basis_snapshot=basis,basis_hash=basis['hash'],total=original.total,currency=invoice.currency)
        allocations=[]
        for line in original.lines.order_by('pk'):
            allocations.append(InvoiceAdjustmentLine.objects.create(document=document,invoice_line_index=line.invoice_line_index,line_id=line.line_id,returned_goods_id=line.returned_goods_id,quantity=line.quantity,amount=line.amount,source_snapshot=deepcopy(line.source_snapshot)).pk)
        return {'invoice_adjustment_id':document.pk,'invoice_id':invoice.pk,'reversed_credit_id':original.pk,'total':money_text(original.total),'currency':invoice.currency,'allocation_ids':allocations,'settlement':settlement_strings(invoice)}
    invoice=Invoice.objects.get(pk=payload['invoice_id']);basis=invoice_basis(invoice);active=InvoiceAdjustmentLine.objects.filter(document__in=active_credits());planned=[];extra_by_line={};extra_by_return={}
    doc=None;source={}
    if payload['basis']=='commercial':doc,source=source_document(payload['source_document_id'],policy)
    for allocation in payload['allocations']:
        index=allocation['invoice_line_index']
        if index>=len(basis['lines']):raise ValueError('Ordinal не належить джерельним рядкам рахунку.')
        part=basis['lines'][index];budget=D(part['budget']);prior=list(active.filter(document__invoice=invoice,invoice_line_index=index));new=extra_by_line.setdefault(index,{'quantity':D(0),'physical':D(0),'amount':D(0)})
        prior_amount=sum((x.amount for x in prior),D(0));prior_quantity=sum((x.quantity for x in prior),D(0));prior_physical=sum((x.amount for x in prior if x.returned_goods_id),D(0));returned=None;qty=D(0)
        if payload['basis']=='return':
            returned=GoodsReturn.objects.select_related('source__line').get(pk=allocation['return_id']);qty=D(allocation['quantity'])
            if returned.direction!='customer' or returned.source.line_id!=part['line_id'] or returned.currency!=invoice.currency:raise ValueError('Return/source line/currency не відповідають рахунку.')
            used=sum((x.quantity for x in active.filter(returned_goods=returned)),D(0))+extra_by_return.get(returned.pk,D(0))
            if used+qty>returned.quantity or prior_quantity+new['quantity']+qty>D(part['quantity']):raise ValueError('Quantity credit перевищує повернення або джерельний рядок рахунку.')
            amount=money(Fraction(budget)*Fraction(prior_quantity+new['quantity']+qty)/Fraction(D(part['quantity'])))-prior_physical-new['physical']
            extra_by_return[returned.pk]=extra_by_return.get(returned.pk,D(0))+qty;new['quantity']+=qty;new['physical']+=amount
        else:amount=D(allocation['amount'])
        if amount<0 or prior_amount+new['amount']+amount>budget:raise ValueError('Credit перевищує невикористаний грошовий budget рядка; автоматичного clamp немає.')
        new['amount']+=amount
        planned.append({'invoice_line_index':index,'line_id':part['line_id'],'returned_goods':returned,'quantity':qty,'amount':amount,'source_snapshot':{'basis_line':part,'prior_amount':money_text(prior_amount),'prior_quantity':quantity_text(prior_quantity),'allocated_amount':money_text(amount),'allocated_quantity':quantity_text(qty)}})
    total=sum((x['amount'] for x in planned),D(0))
    if total+sum((x.total for x in active_credits(invoice)),D(0))>invoice.amount:raise ValueError('Credit перевищує первісний рахунок.')
    document=InvoiceAdjustment.objects.create(**fields,kind='credit',basis=payload['basis'],invoice=invoice,basis_snapshot=basis,basis_hash=basis['hash'],total=total,currency=invoice.currency,source_document=doc,source_snapshot=source)
    allocations=[InvoiceAdjustmentLine.objects.create(document=document,**row).pk for row in planned]
    return {'invoice_adjustment_id':document.pk,'invoice_id':invoice.pk,'total':money_text(total),'currency':invoice.currency,'allocation_ids':allocations,'settlement':settlement_strings(invoice)}


def prospective(receipt,delta,before):
    keys={'erp_cancel_remaining':('cancellations','cancellation_id'),'erp_return_supplier':('goods_returns','goods_return_id'),
        'erp_return_from_shipment':('goods_returns','goods_return_id'),'erp_credit_invoice':('invoice_adjustments','invoice_adjustment_id'),
        'erp_reverse_credit':('invoice_adjustments','invoice_adjustment_id'),'erp_confirm_supplier_claim':('supplier_claims','supplier_claim_id')}
    collection,key=keys[receipt['action']];persisted=any(row['id']==receipt[key] for row in before.get(collection,[]))
    out=deepcopy(receipt);out['prospective']=not persisted
    if persisted:return out,delta
    for name in ('erp_event_id','cancellation_id','goods_return_id','movement_id','lot_id','claim_id','invoice_adjustment_id','supplier_claim_id'):
        if name in out and not (name=='lot_id' and receipt['action']=='erp_return_supplier'):out[name]=None
    if 'allocation_ids' in out:out['allocation_ids']=[]
    result=[]
    for change in delta:
        oldids={row.get('id',row.get('invoice_id')) for row in before.get(change['kind'],[])}
        result.append({**change,'id':None,'prospective':True} if change['id'] not in oldids else change)
    return out,result


@exact
def snapshot_rows(policy=None):
    visible=policy.filter_queryset if policy else lambda rows:rows
    result={name:list(visible(model.objects.order_by('pk')).values()) for name,model in
        [('cancellations',OrderCancellation),('cancellation_releases',CancellationRelease),('goods_returns',GoodsReturn),('supplier_claims',SupplierClaim),('invoice_adjustments',InvoiceAdjustment),('invoice_adjustment_lines',InvoiceAdjustmentLine)]}
    result['source_movements']=[]
    from django.db.models import Q
    returned_ids=[row['result_id'] for row in result['goods_returns']]
    for movement in visible(Movement.objects.filter(Q(kind__in=['receipt','shipment'])|Q(pk__in=returned_ids)).select_related('lot').order_by('pk')):
        result['source_movements'].append({'id':movement.pk,'kind':movement.kind,'lot_id':movement.lot_id,'lot_code':movement.lot.code,'item_id':movement.lot.item_id,
            'location_id':movement.lot.location_id,'line_id':movement.line_id,'purchase_id':movement.purchase_id,'quantity':quantity_text(movement.quantity),
            'revision':movement.lot.revision,'currency':movement.lot.currency,'reference':movement.reference,'created_at':movement.created_at,'cost':money_text(movement.cost),'unit_cost':money_text(movement.lot.unit_cost)})
    for row in result['goods_returns']:
        obj=GoodsReturn.objects.select_related('source','result').get(pk=row['id']);row.update(lot_id=obj.result.lot_id,source_lot_id=obj.source.lot_id,line_id=obj.source.line_id,purchase_id=obj.source.purchase_id)
    for row in result['supplier_claims']:
        row['return_id']=row.pop('returned_goods_id');row['confirmed_by_id']=next((other['id'] for other in result['supplier_claims'] if other['parent_id']==row['id']),None)
    for row in result['invoice_adjustment_lines']:row['return_id']=row.pop('returned_goods_id')
    event_ids={row['event_id'] for key in ('cancellations','goods_returns','supplier_claims','invoice_adjustments') for row in result[key]}
    result['correction_events']=list(Event.objects.filter(pk__in=event_ids).order_by('pk').values())
    return result


@exact
def effective_row(obj,policy=None):
    is_sale=isinstance(obj,SalesLine);cancelled=cancelled_quantity(obj);opened=sales_open(obj) if is_sale else purchase_open(obj)
    movements=Movement.objects.filter(line=obj,kind='return') if is_sale else Movement.objects.filter(purchase=obj,kind='supplier_return')
    complete=not policy or (not movements.exclude(pk__in=policy.queryset(Movement).values('pk')).exists() and not GoodsReturn.objects.filter(result__in=movements).exclude(pk__in=policy.queryset(GoodsReturn).values('pk')).exists())
    values={'cancelled_quantity':quantity_text(cancelled),'open_quantity':quantity_text(opened),'return_visibility':'complete' if complete else 'restricted',
        'returned_quantity':quantity_text(sum((abs(m.quantity) for m in movements),D(0))) if complete else None,
        'return_allocated_cost':money_text(sum((m.cost for m in movements),D(0))) if complete else None}
    if not is_sale:values['effective_status']='received' if obj.received==obj.quantity else 'closed_cancelled' if opened==0 and cancelled>0 else 'partial' if obj.received>0 else 'open'
    return values


@exact
def unresolved_returns(order,policy=None):
    rows=Movement.objects.filter(line__order=order,kind='return')
    if policy:rows=policy.filter_queryset(rows)
    for movement in rows:
        returned=GoodsReturn.objects.filter(result=movement,direction='customer').first()
        if returned is None:return True
        allocated=InvoiceAdjustmentLine.objects.filter(returned_goods=returned,document__in=active_credits()).aggregate(n=Sum('quantity'))['n'] or D(0)
        if allocated<returned.quantity:return True
    return False
