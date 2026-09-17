"""C03 confirmed local statements. One ERP mutex; cash and AR remain separate axes."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal as D
from uuid import UUID
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from boss_project.policy import Policy
from operations.models import Document,ActionProposal,Invoice
from operations.private_storage import verified_document_bytes
from erp.balances import exact,invoice_settlement
from erp.models import Event,ImportIdentity
from .models import StatementImport,StatementLine,StatementAllocation,Transaction,Counterparty,Salary
from .statement_csv import FORMAT,PARSER_VERSION,COLUMNS,CURRENCIES,StatementError,parse,marker,money,safe_text,account,digest

ACTIONS={'erp_statement_import','erp_statement_reconcile'}
TX_FIELDS=('direction','amount','currency','date','description','category','counterparty_id','contract_id','branch_id','archived_at')


def fields(value,required):
    if not isinstance(value,dict) or set(value)!=set(required.split()):raise StatementError('Поля дії мають точно відповідати схемі.')
    return value

def pk(value):
    if type(value)!=int or not 1<=value<=9223372036854775807:raise StatementError('Потрібен додатний ID запису.')
    return value

def uuid(value,version=None):
    if not isinstance(value,str):raise StatementError('Потрібен канонічний UUID.')
    try:u=UUID(value)
    except (ValueError,TypeError,AttributeError):raise StatementError('Некоректний UUID.')
    if str(u)!=value or version is not None and u.version!=version:raise StatementError('Потрібен канонічний UUID відповідної версії.')
    return value

def reason(value,maximum=1000):return safe_text(value,maximum,minimum=3)

def clean(raw):
    d=deepcopy(raw)
    if not isinstance(d,dict) or d.get('action') not in ACTIONS:raise StatementError('Невідома дія виписки.')
    if d['action']=='erp_statement_import':
        fields(d,'action document_id source_sha256 source_system account_ref format parser_version');pk(d['document_id']);account(d['source_system'],d['account_ref'])
        import re
        if not isinstance(d['source_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',d['source_sha256']) or d['format']!=FORMAT or d['parser_version']!=PARSER_VERSION:raise StatementError('Не відповідає SHA або версія схеми CSV.')
        return d
    fields(d,'action line_id transaction matching reason allocations');uuid(d['line_id']);reason(d['reason'])
    tx=d['transaction'];match=d['matching']
    if not isinstance(tx,dict) or tx.get('mode') not in ('create_transaction','existing_transaction'):raise StatementError('Оберіть спосіб грошового запису.')
    if tx['mode']=='create_transaction':
        fields(tx,'mode category description');reason(tx['description'],300)
        if tx['category'] not in ('supplier','customer','utility','rent','tax','other'):raise StatementError('Категорія не підтримує створення транзакції з виписки.')
    else:fields(tx,'mode transaction_id');pk(tx['transaction_id'])
    if not isinstance(match,dict) or match.get('kind') not in ('manual','import_identity','salary_source'):raise StatementError('Потрібне явне зіставлення джерела.')
    keys='kind counterparty_id counterparty_external_id'+(' identity_id' if match['kind']=='import_identity' else ' salary_id' if match['kind']=='salary_source' else '')
    fields(match,keys);safe_text(match['counterparty_external_id'],120)
    if match['counterparty_id'] is not None:pk(match['counterparty_id'])
    if match['kind']=='import_identity':pk(match['identity_id']);pk(match['counterparty_id'])
    if match['kind']=='salary_source':pk(match['salary_id'])
    if not isinstance(d['allocations'],list) or len(d['allocations'])>50:raise StatementError('Максимум 50 погоджених розподілів.')
    seen=set();payment_ids=set()
    for a in d['allocations']:
        if not isinstance(a,dict) or a.get('mode') not in ('new_payment','existing_payment'):raise StatementError('Оберіть спосіб оплати.')
        fields(a,'allocation_key mode invoice_id amount currency invoice_match reason'+(' payment_event_id' if a['mode']=='existing_payment' else ''))
        uuid(a['allocation_key'],4);pk(a['invoice_id']);reason(a['reason']);a['amount']=money(a['amount'])
        if a['allocation_key'] in seen:raise StatementError('Повторний allocation_key у дії.')
        seen.add(a['allocation_key'])
        if a['currency'] not in CURRENCIES or a['invoice_match'] not in ('exact_reference','manual'):raise StatementError('Некоректна валюта або спосіб зіставлення рахунку.')
        if a['mode']=='existing_payment':
            pk(a['payment_event_id'])
            if a['payment_event_id'] in payment_ids:raise StatementError('Одну первинну оплату не можна розподілити двічі.')
            payment_ids.add(a['payment_event_id'])
    return d


def source(document,*,checksum=None,current=False):
    m=marker(document)
    if document.access_level!='ceo' or document.status!='approved' or not m or m.get('format')!=FORMAT or m.get('parser_version')!=PARSER_VERSION or document.contract_id is not None:raise StatementError('Потрібне перевірене приватне джерело CSV.')
    if current and Document.objects.filter(code=document.code).order_by('-pk').first().pk!=document.pk:raise StatementError('Є нова версія; перегляньте джерело.')
    if checksum is not None and document.checksum!=checksum:raise StatementError('SHA джерела змінився.',status=409,code='statement_source_changed')
    raw=verified_document_bytes(document);parsed=parse(raw)
    if parsed['row_count']!=m.get('row_count') or parsed['source_totals']!=m.get('source_totals'):raise StatementError('Маркер не відповідає первинним bytes.')
    return parsed


def original(imported):
    d=imported.document;att=imported.source_snapshot
    parsed=source(d,checksum=imported.source_sha256)
    if any(att.get(k)!=v for k,v in {'document_id':d.pk,'code':d.code,'revision':d.revision,'checksum':d.checksum,'size':d.size,'status':'approved','format':FORMAT,'parser_version':PARSER_VERSION,'row_count':parsed['row_count'],'source_totals':parsed['source_totals']}.items()):raise StatementError('Первинне погоджене джерело змінилося.',status=409,code='statement_source_changed')
    return parsed


def lock_selected(d):
    if d['action']!='erp_statement_reconcile':return
    line=StatementLine.objects.get(pk=d['line_id']);ids={line.transaction_id}
    if d['transaction']['mode']=='existing_transaction':ids.add(d['transaction']['transaction_id'])
    for identity in sorted(x for x in ids if x is not None):
        if not Transaction._base_manager.filter(pk=identity).update(direction=F('direction')):raise Transaction.DoesNotExist()
    cp=d['matching'].get('counterparty_id')
    if cp is not None:Counterparty.objects.select_for_update().get(pk=cp)


@exact
def fingerprint(d,p):
    from erp.service import fingerprint as erp_fingerprint
    model_rows={m._meta.label:list(m.objects.order_by('pk').values()) for m in (StatementImport,StatementLine,StatementAllocation,Transaction,Counterparty,ImportIdentity,Salary)}
    if d['action']=='erp_statement_import':
        doc=Document.objects.get(pk=d['document_id']);source(doc,checksum=d['source_sha256'],current=True)
    else:
        line=StatementLine.objects.select_related('first_import__document').get(pk=d['line_id']);original(line.first_import);doc=line.first_import.document
    model_rows['document']={'id':doc.pk,'checksum':doc.checksum,'size':doc.size,'status':doc.status,'sections':doc.sections,'access_level':doc.access_level,'revision':doc.revision,'code':doc.code}
    return digest(normalize({'erp':erp_fingerprint(),'state':model_rows,'actor':p.actor.as_dict(),'access_revision':p.access_revision(),'payload':d}))


def normalize(value):
    import json
    return json.loads(json.dumps(value,default=str))


def current_line(line):
    allocated=sum(line.allocations.values_list('amount',flat=True),D(0))
    incoming=line.direction=='in';unallocated=line.amount-allocated if incoming else D(0)
    status='unposted' if line.transaction_id is None else 'cash_recorded' if not incoming else 'unallocated' if not allocated else 'reconciled' if unallocated==0 else 'partial'
    return {'allocated':format(allocated,'.2f'),'unallocated':format(unallocated,'.2f'),'cash_recorded':line.transaction_id is not None,'status':status}


def prepare_import(d,p):
    doc=Document.objects.get(pk=d['document_id']);parsed=source(doc,checksum=d['source_sha256'],current=True)
    known=StatementImport.objects.filter(source_system=d['source_system'],account_ref=d['account_ref'],source_sha256=d['source_sha256']).first()
    if known:
        original(known)
        return {'no_change':True,'known':known,'effect':{'id':None,'state':'no_change','first_commit_receipt':known.first_commit_receipt,'current_summary':import_current_summary(known)}}
    rows=[]
    for row in parsed['rows']:
        old=StatementLine.objects.filter(source_system=d['source_system'],account_ref=d['account_ref'],external_id=row['external_id']).first()
        if old:
            actual={k:format(old.amount,'.2f') if k=='amount' else str(getattr(old,k)) for k in COLUMNS}
            if old.semantic_sha256!=row['semantic_sha256'] or digest(actual)!=row['semantic_sha256']:raise StatementError('Ідентичність рядка вже має інші первинні поля.',code='statement_identity_conflict',status=409)
        rows.append({'row':row,'old':old})
    counts={'create':sum(x['old'] is None for x in rows),'reuse':sum(x['old'] is not None for x in rows),'total':len(rows)}
    effect={'schema':'bos.statement-import.v1','source':{k:d[k] for k in ('document_id','source_sha256','source_system','account_ref')},'counts':counts,'lines':[{'external_id':x['row']['external_id'],'decision':'reuse' if x['old'] else 'create','line_id':str(x['old'].pk) if x['old'] else None,'record':x['row']['record']} for x in rows],'source_totals':parsed['source_totals'],'transaction_delta':0,'payment_delta':0}
    snapshot={'document_id':doc.pk,'code':doc.code,'revision':doc.revision,'checksum':doc.checksum,'size':doc.size,'status':'approved','format':FORMAT,'parser_version':PARSER_VERSION,'row_count':parsed['row_count'],'source_totals':parsed['source_totals']}
    return {'no_change':False,'doc':doc,'rows':rows,'snapshot':snapshot,'effect':effect}


def apply_import(d,p,plan):
    if plan['no_change']:return {'state':'succeeded',**plan['known'].first_commit_receipt}
    obj=StatementImport.objects.create(document=plan['doc'],source_sha256=d['source_sha256'],format=FORMAT,parser_version=PARSER_VERSION,source_system=d['source_system'],account_ref=d['account_ref'],actor_id=p.actor.user_id,source_snapshot=plan['snapshot'],first_commit_receipt={})
    mapped=[]
    for x in plan['rows']:
        line=x['old'] or StatementLine.objects.create(first_import=obj,source_system=d['source_system'],account_ref=d['account_ref'],**x['row'])
        mapped.append({'line_id':str(line.pk),'external_id':line.external_id,'record':x['row']['record'],'decision':'reuse' if x['old'] else 'create'})
    receipt={'state':'succeeded','schema':'bos.statement-import.v1','import_id':str(obj.pk),'document_id':obj.document_id,'source_sha256':obj.source_sha256,'source_system':obj.source_system,'account_ref':obj.account_ref,'counts':plan['effect']['counts'],'lines':mapped,'source_totals':plan['effect']['source_totals']}
    event=Event.objects.create(action=d['action'],payload=d,result=receipt,role=p.role);receipt['erp_event_id']=event.pk
    obj.first_commit_receipt=receipt;obj.save(update_fields=['first_commit_receipt']);Event.objects.filter(pk=event.pk).update(result=receipt)
    return receipt


def transaction_fields(tx):return normalize({k:getattr(tx,k) for k in TX_FIELDS})


def settlement(invoice):return {k:format(v,'.2f') if isinstance(v,D) else v for k,v in {**invoice_settlement(invoice),'amount':invoice.amount,'paid':invoice.paid,'currency':invoice.currency}.items()}


def matching_source(line,d,tx):
    m=d['matching'];cp=m['counterparty_id']
    if m['counterparty_external_id']!=line.counterparty_external_id:raise StatementError('Зовнішній код контрагента не збігається з CSV.')
    if cp is None and d['allocations']:raise StatementError('Для рахунків потрібен явний контрагент.')
    counterparty=Counterparty.objects.get(pk=cp) if cp is not None else None
    if tx is None and counterparty is not None and not counterparty.is_active:raise StatementError('Новий грошовий запис потребує активного контрагента.')
    snapshot={'matching':m,'counterparty':None if counterparty is None else {'id':cp,'name':counterparty.name,'type':counterparty.type,'is_active':counterparty.is_active}}
    if m['kind']=='import_identity':
        identity=ImportIdentity.objects.get(pk=m['identity_id'])
        if identity.entity!='counterparty' or identity.counterparty_id!=cp or identity.external_id!=line.counterparty_external_id:raise StatementError('ImportIdentity не підтверджує обраного контрагента.')
        snapshot['import_identity']={**normalize({k:getattr(identity,k) for k in ('id','namespace','entity','external_id','first_batch_id','row_sha256')}),'target_id':identity.counterparty_id}
    if m['kind']=='salary_source':
        salary=Salary.objects.select_related('employee').get(pk=m['salary_id'])
        if d['transaction']['mode']!='existing_transaction' or tx is None or cp is not None or line.direction!='out' or d['allocations'] or salary.status!='paid' or salary.transaction_id!=tx.pk or tx.category!='salary' or salary.amount!=line.amount or salary.currency!=line.currency or salary.payment_date!=line.booking_date:raise StatementError('Зарплатне джерело не відповідає проведеній історичній транзакції.')
        snapshot['salary']=normalize({k:getattr(salary,k) for k in ('id','employee_id','transaction_id','amount','currency','payment_date','period_year','period_month')});snapshot['salary']['employee_name']=salary.employee.full_name
    elif tx is not None and (tx.category=='salary' or Salary.objects.filter(transaction=tx).exists()):raise StatementError('Зарплатна транзакція потребує явного salary_source.')
    return snapshot


@exact
def prepare_reconcile(d,p):
    line=StatementLine.objects.select_related('first_import__document','transaction').get(pk=d['line_id']);original(line.first_import)
    t=d['transaction'];tx=line.transaction
    if tx is None and t['mode']=='existing_transaction':tx=Transaction._base_manager.get(pk=t['transaction_id'])
    matching=matching_source(line,d,tx)
    if tx is not None:
        if t['mode']=='existing_transaction' and tx.pk!=t['transaction_id']:raise StatementError('Рядок вже має інший грошовий запис.',status=409)
        if any(getattr(tx,k)!=v for k,v in {'direction':line.direction,'amount':line.amount,'currency':line.currency,'date':line.booking_date,'counterparty_id':d['matching']['counterparty_id']}.items()):raise StatementError('Грошовий запис не відповідає сумі, даті, валюті, напряму чи контрагенту рядка.')
        if StatementLine.objects.filter(transaction=tx).exclude(pk=line.pk).exists():raise StatementError('Транзакцію вже зв’язано з іншим рядком.',status=409,code='statement_transaction_bound')
    if line.transaction_id:
        if (line.binding_snapshot['transaction_intent']!=t and not (t['mode']=='existing_transaction' and t['transaction_id']==line.transaction_id)) or line.binding_snapshot['matching']!=d['matching']:raise StatementError('Перше погоджене зіставлення є незмінним.',status=409,code='statement_binding_conflict')
        # Archive is an allowed lifecycle change, all business fields remain exact.
        stored=line.binding_snapshot['transaction_fields'];actual=transaction_fields(tx)
        if any(stored[k]!=actual[k] for k in TX_FIELDS if k!='archived_at'):raise StatementError('Пов’язаний грошовий запис змінився.',status=409)
    tx_fields=transaction_fields(tx) if tx is not None else {'direction':line.direction,'amount':format(line.amount,'.2f'),'currency':line.currency,'date':str(line.booking_date),'description':t['description'],'category':t['category'],'counterparty_id':d['matching']['counterparty_id'],'contract_id':None,'branch_id':None,'archived_at':None}
    if line.direction!='in' and d['allocations']:raise StatementError('Вихідна транзакція не розподіляється на дебіторські рахунки.')
    allocations=[];invoice_states={};total=sum(line.allocations.values_list('amount',flat=True),D(0))
    for a in d['allocations']:
        identity=digest({'line_id':str(line.pk),'allocation':a});existing=StatementAllocation.objects.select_related('invoice','payment_event').filter(allocation_key=a['allocation_key']).first()
        if existing:
            if existing.line_id!=line.pk or existing.intent_sha256!=identity:raise StatementError('allocation_key вже має інший погоджений зміст.',code='statement_allocation_conflict',status=409)
            allocations.append({'payload':a,'old':existing,'invoice':existing.invoice,'event':existing.payment_event,'intent':identity});continue
        invoice=Invoice.objects.get(pk=a['invoice_id']);amount=D(a['amount'])
        if invoice.currency!=line.currency or a['currency']!=line.currency or invoice.customer_id!=d['matching']['counterparty_id']:raise StatementError('Рахунок, контрагент і валюта мають точно збігатися.')
        if a['invoice_match']=='exact_reference' and invoice.code!=line.invoice_reference:raise StatementError('Посилання CSV не збігається з повним кодом рахунку.')
        if invoice.pk not in invoice_states:invoice_states[invoice.pk]={'invoice_id':invoice.pk,'code':invoice.code,'before':settlement(invoice),'after':settlement(invoice)}
        state=invoice_states[invoice.pk];event=None
        if a['mode']=='new_payment':
            if amount>D(state['after']['receivable']):raise StatementError('Оплата перевищує чинну відкриту суму рахунку.')
            after=state['after'];after['paid']=format(D(after['paid'])+amount,'.2f');after['receivable']=format(max(D(0),D(after['net_amount'])-D(after['paid'])),'.2f');after['customer_credit']=format(max(D(0),D(after['paid'])-D(after['net_amount'])),'.2f')
            if Event.objects.filter(action='erp_payment',payload__reference='STMT-'+UUID(a['allocation_key']).hex).exists():raise StatementError('Посилання оплати вже зареєстроване.',status=409)
        else:
            event=Event.objects.get(pk=a['payment_event_id']);ed=event.payload
            if event.action!='erp_payment' or type(ed.get('invoice_id'))!=int or ed['invoice_id']!=invoice.pk or not isinstance(ed.get('reference'),str) or not ed['reference'].strip() or D(str(ed.get('amount')))!=amount:raise StatementError('Потрібна повна сума точного первинного ERP payment.')
            if StatementAllocation.objects.filter(payment_event=event).exists():raise StatementError('Оплату вже повністю зіставлено.',status=409)
            payment_total=sum((D(str(e.payload['amount'])) for e in Event.objects.filter(action='erp_payment',payload__invoice_id=invoice.pk)),D(0))
            if payment_total>invoice.paid:raise StatementError('Первинні оплати суперечать збереженій paid; зіставлення зупинено.')
        total+=amount;allocations.append({'payload':a,'old':None,'invoice':invoice,'event':event,'intent':identity})
    if total>line.amount:raise StatementError('Розподіл перевищує повну суму первинного рядка.')
    new=[a for a in allocations if a['old'] is None];binding=line.transaction_id is None
    if not binding and not new:return {'no_change':True,'line':line,'effect':{'id':None,'state':'no_change','first_commit_receipt':line.binding_snapshot['first_commit_receipt'],'current_summary':current_line(line)},'allocations':allocations}
    effect={'schema':'bos.statement-reconcile.v1','line_id':str(line.pk),'amount':format(line.amount,'.2f'),'currency':line.currency,'transaction':{'mode':t['mode'],'transaction_id':tx.pk if tx else None,'created':tx is None,'fields':tx_fields},'binding_created':binding,'allocations':[{'allocation_key':a['payload']['allocation_key'],'decision':'reuse' if a['old'] else 'create','allocation_id':str(a['old'].pk) if a['old'] else None,'mode':a['payload']['mode'],'invoice_id':a['invoice'].pk,'payment_event_id':a['event'].pk if a['event'] else None,'amount':a['payload']['amount'],'currency':line.currency,'reference':a['event'].payload['reference'] if a['event'] else 'STMT-'+UUID(a['payload']['allocation_key']).hex} for a in allocations],'allocated':format(total,'.2f'),'unallocated':format(line.amount-total if line.direction=='in' else D(0),'.2f'),'invoices':list(invoice_states.values()),'deltas':{'transactions':int(tx is None),'financial_intents':int(tx is None),'finance_audits':int(tx is None),'allocations':len(new),'payment_events':sum(a['payload']['mode']=='new_payment' for a in new),'reconcile_events':1}}
    return {'no_change':False,'line':line,'tx':tx,'matching':matching,'allocations':allocations,'effect':effect,'transaction_fields':tx_fields}


@exact
def apply_reconcile(d,p,plan):
    if plan['no_change']:
        line=plan['line'];return {'state':'succeeded','schema':'bos.statement-reconcile.v1','no_change':True,'line_id':str(line.pk),'transaction_id':line.transaction_id,'allocation_ids':[str(x['old'].pk) for x in plan['allocations']],'current_summary':current_line(line)}
    from .commands import save_transaction
    from erp.payments import post_payment
    line=plan['line'];tx=plan['tx'];new_tx=tx is None;new_binding=line.transaction_id is None
    if tx is None:
        changes={k:v for k,v in plan['transaction_fields'].items() if k!='archived_at'}
        changes['amount']=D(changes['amount'])
        from datetime import date
        changes['date']=date.fromisoformat(changes['date'])
        tx=save_transaction(changes=changes,actor=p.user,operation_id='stmt-tx:'+line.pk.hex)
    if new_binding:
        line.transaction=tx;line.bound_by_id=p.actor.user_id;line.bound_at=timezone.now()
        line.binding_snapshot={**plan['matching'],'transaction_intent':d['transaction'],'transaction_fields':transaction_fields(tx),'reason':d['reason'],'source':line.first_import.source_snapshot}
        line.save(update_fields=['transaction','bound_by','bound_at','binding_snapshot'])
    new_ids=[];reused_ids=[];new_payments=[];old_payments=[]
    for a in plan['allocations']:
        if a['old']:
            reused_ids.append(str(a['old'].pk));old_payments.append(a['old'].payment_event_id);continue
        payload=a['payload'];payment=a['event']
        if payment is None:
            result=post_payment(payload['invoice_id'],payload['amount'],'STMT-'+UUID(payload['allocation_key']).hex,role=p.role,log=True)
            payment=Event.objects.get(pk=result['erp_event_id']);new_payments.append(payment.pk)
        else:old_payments.append(payment.pk)
        obj=StatementAllocation.objects.create(line=line,allocation_key=payload['allocation_key'],invoice=a['invoice'],payment_event=payment,amount=payload['amount'],currency=line.currency,mode=payload['mode'],actor_id=p.actor.user_id,intent_sha256=a['intent'],source_snapshot={'source':line.first_import.source_snapshot,'matching':plan['matching'],'allocation':payload,'payment':normalize({'id':payment.pk,'payload':payment.payload,'result':payment.result,'created_at':payment.created_at})})
        new_ids.append(str(obj.pk))
    line.refresh_from_db();tx.refresh_from_db();actual=current_line(line)
    if line.transaction_id!=tx.pk or any(transaction_fields(tx)[k]!=plan['transaction_fields'][k] for k in TX_FIELDS):
        raise StatementError('Фактична транзакція не відповідає погодженим первинним полям.',status=409)
    for expected in plan['effect']['invoices']:
        if settlement(Invoice.objects.get(pk=expected['invoice_id']))!=expected['after']:
            raise StatementError('Фактичне рознесення рахунку не відповідає погодженому.',status=409)
    if actual['allocated']!=plan['effect']['allocated'] or actual['unallocated']!=plan['effect']['unallocated']:raise StatementError('Фактичний розподіл не відповідає погодженому.',status=409)
    receipt={'state':'succeeded','schema':'bos.statement-reconcile.v1','line_id':str(line.pk),'transaction_id':tx.pk,'transaction_created':new_tx,'binding_created':new_binding,'new_allocation_ids':new_ids,'reused_allocation_ids':reused_ids,'created_payment_event_ids':new_payments,'reused_payment_event_ids':old_payments,'amount':format(line.amount,'.2f'),'currency':line.currency,'allocated':actual['allocated'],'unallocated':actual['unallocated'],'invoices':plan['effect']['invoices'],'actor_id':p.actor.user_id,'impact':[]}
    event=Event.objects.create(action=d['action'],payload=d,result=receipt,role=p.role);receipt['erp_event_id']=event.pk;event.result=receipt;event.save(update_fields=['result'])
    if new_binding:
        line.binding_snapshot={**line.binding_snapshot,'first_commit_receipt':receipt};line.save(update_fields=['binding_snapshot'])
    return receipt


@exact
def prepare(d,p):
    if not p.ceo:raise PermissionError('Виписки погоджує лише керівник.')
    return prepare_import(d,p) if d['action']=='erp_statement_import' else prepare_reconcile(d,p)

@exact
def apply(d,p,plan):return apply_import(d,p,plan) if d['action']=='erp_statement_import' else apply_reconcile(d,p,plan)

@exact
def preview(request,payload):
    from erp.service import write_lock
    d=clean(payload)
    with transaction.atomic():
        write_lock();p=Policy(request);p.action(d);lock_selected(d);token=fingerprint(d,p);plan=prepare(d,p)
        if plan['no_change']:result=plan['effect']
        else:result=None
        transaction.set_rollback(True)
    if result is not None:return result
    proposal=ActionProposal.objects.create(user_id=p.actor.user_id,session_key=request.session.session_key,role=p.role,payload=d,fingerprint=token,expires_at=timezone.now()+timedelta(minutes=10))
    return {'id':str(proposal.pk),'payload':d,'expires_at':proposal.expires_at.isoformat(),'effect':plan['effect'],'impact':[]}


@exact
def import_current_summary(imported):
    from .statement_reads import currency_totals
    rows=[StatementLine.objects.get(pk=r['line_id']) for r in imported.first_commit_receipt['lines']]
    return {'lines':[{'line_id':str(x.pk),**current_line(x)} for x in rows],'currencies':currency_totals(rows)}
