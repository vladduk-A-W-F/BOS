from decimal import Decimal as D
from datetime import timedelta
from django.db.models import Sum
from django.forms.models import model_to_dict
from django.core.serializers.json import DjangoJSONEncoder
import json
from .models import *
from .service import usable,free,reserved,accepted_documents
from operations.service import as_of
from operations.models import Document,Invoice,ProcurementRequest
from employees.models import Employee
from finance.models import Counterparty
from .balances import sales_open,purchase_open,invoice_settlement,settlement_strings,exact

def money_open(invoice):return str(invoice_settlement(invoice)['receivable'])

def textnum(n):return str(n.quantize(D('.001'))).rstrip('0').rstrip('.') if n else '0'

def rows(model):return list(model.objects.order_by('pk').values())

@exact
def plan_line(line,policy=None):
    visible=lambda rows:policy.filter_queryset(rows) if policy else rows
    today=as_of();remaining=sales_open(line)
    own=sum((r.quantity for r in visible(line.reservations.select_related('lot__item')) if usable(r.lot,line.revision)),D(0))
    available=sum((free(lot) for lot in visible(Lot.objects.filter(item=line.item,revision=line.revision).select_related('item')) if usable(lot)),D(0))
    shortage=max(D(0),remaining-own-available)
    incoming=[];dates=[];covered=D(0);reasons=[]
    for job in visible(Production.objects.filter(line=line).exclude(status='done')):
        qty=job.quantity-job.produced;covered+=qty;dates.append(job.due_date);incoming.append({'code':job.code,'quantity':str(qty),'due_date':str(job.due_date),'needs_review':job.needs_review})
        if job.needs_review:reasons.append(job.code+': потрібне рішення щодо версії')
    material=[]
    for b in line.item.bom:
        item=Item.objects.get(pk=b['item_id']);need=shortage*D(b['quantity'])
        stock=sum((free(x) for x in visible(Lot.objects.filter(item=item).select_related('item')) if usable(x)),D(0))
        own_material=sum((r.quantity for r in visible(Reservation.objects.filter(production__line=line,lot__item=item).select_related('lot__item')) if usable(r.lot)),D(0));stock+=own_material
        purchases=[p for p in visible(Purchase.objects.filter(item=item).exclude(status='received').order_by('due_date')) if purchase_open(p)>0]
        pending=sum((purchase_open(p) for p in purchases),D(0));before_due=sum((purchase_open(p) for p in purchases if p.due_date<=line.order.due_date),D(0))
        deficit=max(D(0),need-stock-before_due)
        if need>stock:
            balance=need-stock
            for p in purchases:
                dates.append(p.due_date);balance-=purchase_open(p)
                if balance<=0:break
            if balance>0:dates.append(today+timedelta(days=item.lead_days));reasons.append(item.code+': непокритий дефіцит')
        material.append({'item_id':item.id,'code':item.code,'name':item.name,'unit':item.unit,'need':str(need),'available':str(stock),'expected':str(pending),'before_due':str(before_due),'deficit':str(deficit)})
    if shortage and not line.item.bom:
        pending=list(visible(Purchase.objects.filter(item=line.item,revision=line.revision).exclude(status='received').order_by('due_date')))
        for p in pending:
            if purchase_open(p)>0:dates.append(p.due_date)
        if sum((purchase_open(p) for p in pending),D(0))<shortage:dates.append(today+timedelta(days=line.item.lead_days));reasons.append('Потрібна закупівля готової продукції')
    days=sum(x.get('days',0) for x in line.item.routing) if shortage else 0
    estimate=max([today]+dates)+timedelta(days=days)
    if estimate>line.order.due_date:reasons.append('Розрахункова дата пізніше бажаної')
    return {'line_id':line.id,'item':line.item.code,'remaining':str(remaining),'reserved':str(own),'free':str(available),'shortage':str(shortage),'materials':material,'jobs':incoming,'estimated_date':str(estimate),'reasons':reasons,'simulation':True,'basis':'Календарні дні, наявні залишки та строки. Не враховує завантаження обладнання; інші замовлення можуть використати ще не зарезервовані надходження.'}

@exact
def snapshot(policy=None):
    visible=lambda rows:policy.filter_queryset(rows) if policy else rows
    result={name:list(visible(model.objects.order_by('pk')).values()) for name,model in [('items',Item),('locations',Location),('lots',Lot),('orders',SalesOrder),('lines',SalesLine),('jobs',Production),('reservations',Reservation),('purchases',Purchase),('inspections',Inspection),('changes',ChangeOrder),('operator_entries',OperatorEntry)]}
    from .corrections import snapshot_rows,effective_row,invoice_basis
    result.update(snapshot_rows(policy))
    for row in result['lines']:row.update(effective_row(SalesLine.objects.get(pk=row['id']),policy))
    for row in result['purchases']:row.update(effective_row(Purchase.objects.get(pk=row['id']),policy))
    result['movements']=list(visible(Movement.objects.order_by('-id')).values()[:300]);result['events']=list(Event.objects.order_by('-id').values()[:150])
    result['employees']=list(Employee.objects.values('id','full_name','role'));result['partners']=list(Counterparty.objects.values('id','name','type'))
    result['requests']=list(visible(ProcurementRequest.objects.all()).values('id','code','part'))
    result['documents']=list(visible(Document.objects.all()).values('id','code','revision','title','status'))
    for row in result['lots']:
        lot=Lot.objects.select_related('item').get(pk=row['id']);row.update(reserved=str(reserved(lot)),available=str(free(lot) if usable(lot) else D(0)),missing_documents=accepted_documents(lot.item,lot.documents))
    result['replenishment']=[]
    for item in visible(Item.objects.filter(minimum__gt=0)):
        available=sum((free(x) for x in visible(Lot.objects.filter(item=item).select_related('item')) if usable(x)),D(0))
        incoming=sum((purchase_open(p) for p in visible(Purchase.objects.filter(item=item).exclude(status='received'))),D(0))
        result['replenishment'].append({'item_id':item.id,'code':item.code,'unit':item.unit,'minimum':str(item.minimum),'available':str(available),'incoming':str(incoming),'suggested':str(max(D(0),item.minimum-available-incoming))})
    result['plans']=[plan_line(x,policy) for x in visible(SalesLine.objects.select_related('order','item').filter(order__status='confirmed'))]
    result['invoices']=list(visible(InvoiceLink.objects.all()).values('invoice_id','order_id','lines'))
    for row in result['invoices']:
        inv=Invoice.objects.get(pk=row['invoice_id']);row.update(code=inv.code,amount=str(inv.amount),paid=str(inv.paid),open=money_open(inv),due_date=str(inv.due_date),currency=inv.currency)
    if policy is None or policy.ceo:
        for row in result['invoices']:
            inv=Invoice.objects.get(pk=row['invoice_id']);row.update(settlement_strings(inv))
            try:row['credit_basis']=invoice_basis(inv);row['credit_source_error']=None
            except (ValueError,InvoiceLink.DoesNotExist):row['credit_basis']=None;row['credit_source_error']='Первісний snapshot рахунку не дозволяє автоматичне коригування.'
    result['costs']=[]
    for order in visible(SalesOrder.objects.all()):
        value=sum((l.quantity*l.price for l in order.lines.all()),D(0));shipped=sum((l.shipped*l.price for l in order.lines.all()),D(0));cost=Movement.objects.filter(line__order=order,kind='shipment').aggregate(n=Sum('cost'))['n'] or D(0)
        result['costs'].append({'order_id':order.id,'code':order.code,'order_value':str(value),'shipped_value':str(shipped),'shipped_cost':str(cost),'gross_margin':str(shipped-cost),'currency':order.currency,'basis':'Різниця вартості відвантаження й облікової собівартості; без податків та загальних витрат. Повернення показані окремо.'})
    score=[]
    for supplier in Counterparty.objects.filter(type='supplier'):
        pos=visible(Purchase.objects.filter(supplier=supplier));receipts=visible(Movement.objects.filter(purchase__supplier=supplier,kind='receipt'));count=receipts.count()
        late=0
        for m in receipts:
            if m.created_at.date()>m.purchase.original_due:late+=1
        inspections=Inspection.objects.filter(lot__movements__in=receipts).distinct();quality=inspections.exclude(result='approved').count()
        score.append({'supplier_id':supplier.id,'name':supplier.name,'orders':pos.count(),'receipts':count,'on_time_pct':round(100*(count-late)/count,1) if count else None,'inspections':inspections.count(),'nonconformities':quality,'rescheduled':sum(1 for p in pos if p.due_date!=p.original_due),'basis':'OTD за подіями приймання; невідповідності за записами перевірок. Без історії оцінка не обчислюється.'})
    result['supplier_scores']=score
    result['as_of']=str(as_of());result['summary']={'orders':visible(SalesOrder.objects.filter(status='confirmed')).count(),'jobs':visible(Production.objects.exclude(status='done')).count(),'blocked_lots':sum(1 for l in visible(Lot.objects.filter(quantity__gt=0).select_related('item')) if not usable(l)),'late_purchases':sum(1 for p in visible(Purchase.objects.exclude(status='received').filter(due_date__lt=as_of())) if purchase_open(p)>0),'review_jobs':visible(Production.objects.filter(needs_review=True)).count()}
    result=json.loads(json.dumps(result,cls=DjangoJSONEncoder,ensure_ascii=False))
    if policy:
        from operations.projections import snapshot as project
        result=project(policy,result)
    return result
