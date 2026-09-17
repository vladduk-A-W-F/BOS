"""Exact, scoped read models; archived cash is still recorded local cash."""
import csv,io
from datetime import date,datetime
from decimal import Decimal as D
from django.core import signing
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from boss_project.policy import Policy
from erp.balances import exact
from erp.models import Event,ImportIdentity,InvoiceLink
from operations.models import Invoice
from .models import StatementImport,StatementLine,StatementAllocation,Transaction,Salary
from .statement_csv import COLUMNS,CURRENCIES,FORMAT,PARSER_VERSION,StatementError,iso_date,account
from .statements import current_line,original,transaction_fields,settlement,normalize,import_current_summary


def params(request,allowed):
    if set(request.GET)-set(allowed):raise StatementError('Невідомий фільтр.',status=400)
    if any(len(request.GET.getlist(k))!=1 for k in request.GET):raise StatementError('Повторний фільтр.',status=400)
    data=dict(request.GET.items())
    for k in ('from','to'):
        if k in data:
            try:iso_date(data[k])
            except ValueError:raise StatementError('Некоректна дата фільтра.',status=400)
    if 'from' in data and 'to' in data and data['from']>data['to']:raise StatementError('Початок періоду пізніше кінця.',status=400)
    if 'currency' in data and data['currency'] not in CURRENCIES:raise StatementError('Невідома валюта.',status=400)
    if 'direction' in data and data['direction'] not in ('in','out'):raise StatementError('Невідомий напрям.',status=400)
    if 'source_system' in data:
        try:account(data['source_system'],'CHECK')
        except ValueError:raise StatementError('Некоректний source_system.',status=400)
    if 'account_ref' in data:
        try:account('check',data['account_ref'])
        except ValueError:raise StatementError('Некоректний account_ref.',status=400)
    return data


def filtered(rows,data,*,date_field='booking_date'):
    for k in ('source_system','account_ref','currency','direction'):
        if k in data:rows=rows.filter(**{k:data[k]})
    if 'from' in data:rows=rows.filter(**{date_field+'__gte':data['from']})
    if 'to' in data:rows=rows.filter(**{date_field+'__lte':data['to']})
    return rows


def page(request,rows,data,serialize,*,scope,no_created=False):
    p=Policy(request)
    if not p.ceo:raise PermissionError('Доступно лише керівнику.')
    size=data.get('limit','20')
    if not isinstance(size,str) or not size.isascii() or not size.isdigit() or len(size)>3 or not 1<=int(size)<=100:raise StatementError('limit має бути від 1 до 100.',status=400)
    limit=int(size);bind={'actor':p.actor.user_id,'revision':p.access_revision(),'filters':{k:v for k,v in data.items() if k!='cursor'},'scope':scope}
    if 'cursor' in data:
        try:
            cursor=signing.loads(data['cursor'],salt='bos.statement.cursor.v1',max_age=3600)
            if cursor['bind']!=bind:raise ValueError()
            cutoff=datetime.fromisoformat(cursor['cutoff']);position=cursor['position'];max_pk=cursor.get('max_pk')
            after=datetime.fromisoformat(position[0]);after_id=position[1]
        except (signing.BadSignature,ValueError,TypeError,KeyError,IndexError):raise StatementError('Курсор не відповідає актору, фільтрам або строку.',status=400)
    else:
        cutoff=timezone.now();after=None;after_id=None
        max_pk=max((x.pk for x in rows),default=0) if no_created else None
    # Some ledgers use UUID keys; source candidates may use integer keys.
    ordered=lambda x:(datetime.min.replace(tzinfo=cutoff.tzinfo),x.pk) if no_created else (x.created_at,str(x.pk))
    values=sorted((x for x in rows if x.pk<=max_pk) if no_created else (x for x in rows if x.created_at<=cutoff),key=ordered)
    if after is not None:values=[x for x in values if ordered(x)>(after,int(after_id) if no_created else str(after_id))]
    more=len(values)>limit;values=values[:limit]
    cursor=None
    if more:
        last=values[-1];cursor=signing.dumps({'bind':bind,'cutoff':cutoff.isoformat(),'position':[ordered(last)[0].isoformat(),str(last.pk)],'max_pk':max_pk},salt='bos.statement.cursor.v1',compress=True)
    return {'items':[serialize(x) for x in values],'next_cursor':cursor}


def first_source(obj):
    d=obj.document;att=obj.source_snapshot
    return {'document_id':d.pk,'code':att['code'],'revision':att['revision'],'checksum':att['checksum'],'size':att['size'],'status':att['status'],'format':FORMAT,'parser_version':PARSER_VERSION,'download_url':f'/api/operations/documents/{d.pk}/download/'}


def line_row(line):return {'id':str(line.pk),**{k:format(line.amount,'.2f') if k=='amount' else str(getattr(line,k)) for k in COLUMNS},'source_system':line.source_system,'account_ref':line.account_ref,'first_import_id':str(line.first_import_id),'record':line.record,'created_at':line.created_at.isoformat(),'transaction_id':line.transaction_id,**current_line(line)}

def import_row(obj):return {'id':str(obj.pk),'source_system':obj.source_system,'account_ref':obj.account_ref,'document_id':obj.document_id,'source_sha256':obj.source_sha256,'created_at':obj.created_at.isoformat(),'counts':obj.first_commit_receipt['counts']}

@exact
def imports(request):
    d=params(request,('source_system','account_ref','from','to','limit','cursor'))
    rows=filtered(StatementImport.objects.all(),d,date_field='created_at__date')
    return page(request,rows,d,import_row,scope='imports')

@exact
def import_detail(request,pk):
    params(request,());obj=StatementImport.objects.select_related('document').get(pk=pk);original(obj)
    rows=[StatementLine.objects.get(pk=r['line_id']) for r in obj.first_commit_receipt['lines']]
    return {'import':import_row(obj),'first_source':first_source(obj),'first_commit_receipt':obj.first_commit_receipt,'lines':[line_row(x) for x in rows],'current_summary':import_current_summary(obj)}

@exact
def lines(request):
    d=params(request,('source_system','account_ref','currency','direction','status','from','to','limit','cursor'))
    if 'status' in d and d['status'] not in ('unposted','unallocated','partial','reconciled','cash_recorded'):raise StatementError('Невідомий стан рядка.',status=400)
    rows=filtered(StatementLine.objects.all(),d)
    if 'status' in d:rows=[x for x in rows if current_line(x)['status']==d['status']]
    return page(request,rows,d,line_row,scope='lines')

@exact
def line_detail(request,pk):
    params(request,());line=StatementLine.objects.select_related('first_import__document','transaction').get(pk=pk);original(line.first_import)
    allocations=list(line.allocations.select_related('payment_event','invoice').order_by('created_at','pk'))
    invoices={a.invoice_id:a.invoice for a in allocations};events={a.payment_event_id:a.payment_event for a in allocations}
    return {'line':line_row(line),'first_source':first_source(line.first_import),'normalized_input':{k:line_row(line)[k] for k in COLUMNS},'binding':line.binding_snapshot,'transaction':None if line.transaction is None else {'id':line.transaction_id,**transaction_fields(line.transaction)},'allocations':[normalize({k:getattr(a,k) for k in ('id','allocation_key','mode','amount','currency','invoice_id','payment_event_id','created_at','actor_id','source_snapshot','intent_sha256')}) for a in allocations],'invoices':[{'id':v.pk,'code':v.code,'customer_id':v.customer_id,'currency':v.currency,'settlement':settlement(v),'order_ids':list(InvoiceLink.objects.filter(invoice=v).values_list('order_id',flat=True))} for v in invoices.values()],'payments':[normalize({'id':v.pk,'action':v.action,'payload':v.payload,'result':v.result,'created_at':v.created_at}) for v in events.values()],'current_summary':current_line(line)}

@exact
def candidates(request,pk):
    d=params(request,('section','limit','cursor'));section=d.get('section','invoices')
    if section not in ('transactions','payments','invoices','identities','salaries'):raise StatementError('Невідомий розділ кандидатів.',status=400)
    line=StatementLine.objects.select_related('first_import__document').get(pk=pk);original(line.first_import)
    if section=='transactions':
        rows=Transaction.objects.filter(date=line.booking_date,direction=line.direction,amount=line.amount,currency=line.currency).filter(Q(statement_line__isnull=True)|Q(statement_line=line))
        fn=lambda x:{'id':x.pk,**transaction_fields(x)}
    elif section=='invoices':
        rows=Invoice.objects.filter(currency=line.currency)
        fn=lambda x:{'id':x.pk,'code':x.code,'customer_id':x.customer_id,'currency':x.currency,'amount':format(x.amount,'.2f'),'paid':format(x.paid,'.2f'),'settlement':settlement(x),'exact_reference':x.code==line.invoice_reference}
    elif section=='identities':
        rows=ImportIdentity.objects.filter(entity='counterparty',external_id=line.counterparty_external_id)
        fn=lambda x:{**normalize({k:getattr(x,k) for k in ('id','namespace','entity','external_id','first_batch_id','row_sha256')}),'target_id':x.counterparty_id}
    elif section=='salaries':
        rows=Salary.objects.select_related('employee').filter(status='paid',amount=line.amount,currency=line.currency,payment_date=line.booking_date,transaction__isnull=False) if line.direction=='out' else Salary.objects.none()
        fn=lambda x:{**normalize({k:getattr(x,k) for k in ('id','employee_id','transaction_id','amount','currency','payment_date','period_year','period_month')}),'employee_name':x.employee.full_name}
    else:
        rows=[]
        for x in Event.objects.filter(action='erp_payment',statement_allocation__isnull=True):
            inv=Invoice.objects.filter(pk=x.payload.get('invoice_id'),currency=line.currency).first()
            if inv is not None:x._invoice=inv;rows.append(x)
        fn=lambda x:{'id':x.pk,'invoice_id':x._invoice.pk,'invoice_code':x._invoice.code,'customer_id':x._invoice.customer_id,'amount':format(D(str(x.payload['amount'])),'.2f'),'currency':x._invoice.currency,'reference':x.payload['reference'],'created_at':x.created_at.isoformat()}
    return {'line_id':str(line.pk),'section':section,**page(request,rows,d,fn,scope='candidates:'+str(line.pk),no_created=section in ('invoices','identities'))}


@exact
def currency_totals(rows):
    out=[]
    for currency in CURRENCIES:
        selected=[x for x in rows if x.currency==currency]
        def sums(values):
            incoming=sum((x.amount for x in values if x.direction=='in'),D(0));outgoing=sum((x.amount for x in values if x.direction=='out'),D(0))
            return {'in':format(incoming,'.2f'),'out':format(outgoing,'.2f'),'net':format(incoming-outgoing,'.2f')}
        allocated=sum((D(current_line(x)['allocated']) for x in selected if x.direction=='in'),D(0))
        incoming=sum((x.amount for x in selected if x.direction=='in'),D(0))
        out.append({'currency':currency,'imported':sums(selected),'recorded':sums([x for x in selected if x.transaction_id]),'unposted':sums([x for x in selected if not x.transaction_id]),'incoming':{'allocated':format(allocated,'.2f'),'unallocated':format(incoming-allocated,'.2f')}})
    return out

@exact
def summary(request):
    d=params(request,('source_system','account_ref','currency','direction','status','from','to'));rows=list(filtered(StatementLine.objects.all(),d))
    if 'status' in d:
        if d['status'] not in ('unposted','unallocated','partial','reconciled','cash_recorded'):raise StatementError('Невідомий стан рядка.',status=400)
        rows=[x for x in rows if current_line(x)['status']==d['status']]
    out=currency_totals(rows)
    accounts=[{'source_system':s,'account_ref':a} for s,a in StatementImport.objects.order_by('source_system','account_ref').values_list('source_system','account_ref').distinct()]
    return {'accounts':accounts,'filters':d,'currencies':out}

@exact
def transaction_summary(request):
    if not Policy(request).ceo:raise PermissionError('Підсумки доступні лише керівнику.')
    d=params(request,('currency','from','to'));rows=list(filtered(Transaction.objects.all(),d,date_field='date'));out=[]
    def sums(values):
        incoming=sum((x.amount for x in values if x.direction=='in'),D(0));outgoing=sum((x.amount for x in values if x.direction=='out'),D(0))
        return {'in':format(incoming,'.2f'),'out':format(outgoing,'.2f'),'net':format(incoming-outgoing,'.2f')}
    for currency in CURRENCIES:
        selected=[x for x in rows if x.currency==currency]
        out.append({'currency':currency,**sums(selected),'expense_categories':[{'category':c,'amount':format(sum((x.amount for x in selected if x.direction=='out' and x.category==c),D(0)),'.2f')} for c in sorted({x.category for x in selected if x.direction=='out'})],'months':[{'month':m,**sums([x for x in selected if x.date.strftime('%Y-%m')==m])} for m in sorted({x.date.strftime('%Y-%m') for x in selected})]})
    return {'filters':d,'includes_archived':True,'balance_kind':'period_movement','currencies':out}


def export(request,pk):
    Policy(request).require_export();data=import_detail(request,pk)
    extras=('import_id','line_id','document_id','source_sha256','first_import_id','first_document_id','first_source_sha256','transaction_id','status','allocated','unallocated')
    columns=COLUMNS+extras
    stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n');writer.writerow(columns)
    for line in data['lines']:
        first=StatementImport.objects.get(pk=line['first_import_id'])
        fields=[];row={**line,'line_id':line['id'],'import_id':str(pk),'document_id':data['first_source']['document_id'],'source_sha256':data['first_source']['checksum'],'first_document_id':first.document_id,'first_source_sha256':first.source_sha256}
        for column in columns:
            value='' if row.get(column) is None else str(row[column])
            if column not in ('amount','booking_date','currency','direction','allocated','unallocated') and value.lstrip().startswith(('=','+','-','@')):value="'"+value
            fields.append(value)
        writer.writerow(fields)
    response=HttpResponse(stream.getvalue(),content_type='text/csv; charset=utf-8');response['Content-Disposition']='attachment; filename="BoS_statement_export.csv"';return response
