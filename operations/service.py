import hashlib,json
from datetime import date,timedelta
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import Document,ProcurementRequest,SupplierQuote,ActionProposal,AuditEvent,Invoice,Configuration
from tasks.models import Task
from employees.models import Employee
from boss_project.identity import actor
from boss_project.policy import Policy
from . import projections

class Conflict(Exception): pass

def as_of():
    c=Configuration.objects.filter(key='dataset').first()
    return date.fromisoformat(c.value['as_of']) if c else date.today()

from erp.balances import exact

@exact
def summary():
    today=as_of();invoices=list(Invoice.objects.all());currencies=sorted({i.currency for i in invoices})
    from erp.balances import invoice_settlement
    totals={c:{'open':str(sum((invoice_settlement(i)['receivable'] for i in invoices if i.currency==c),Decimal(0))),'overdue':str(sum((invoice_settlement(i)['receivable'] for i in invoices if i.currency==c and i.due_date<today),Decimal(0)))} for c in currencies}
    from tasks.queries import overdue_q,project_list
    overdue=project_list(Task.objects.filter(overdue_q()))
    cash=Configuration.objects.filter(key='cash').first()
    return {'as_of':str(today),'overdue_tasks':overdue,'receivables':totals,'cash':cash.value if cash else None,'invoices':[{'code':i.code,'amount':str(i.amount),'paid':str(i.paid),'currency':i.currency,'due_date':str(i.due_date)} for i in invoices],'sources':[i.code for i in invoices]+(['D-CASH'] if cash else [])}

def newest(code):return Document.objects.filter(code=code).defer('content').order_by('-id').first()

@exact
def compare(code,quantity=None):
    from erp.models import Purchase
    from django.db.models import Sum
    r=ProcurementRequest.objects.select_related('owner','document').get(code=code)
    q=r.quantity if quantity is None else quantity
    if type(q)!=int or not 1<=q<=100000:raise ValueError('Кількість: ціле число від 1 до 100000.')
    current=as_of();rows=[]
    spec_current=newest(r.document.code).id==r.document_id
    for item in r.quotes.select_related('supplier','document'):
        t=item.terms;reasons=[]
        if r.document.status not in ('approved','supplier_quote') or item.document.status not in ('approved','supplier_quote'):reasons.append('Документ ще не перевірено')
        if not t.get('coating_included'):reasons.append('Не включено обов’язкове покриття')
        if not t.get('material_certificate'):reasons.append('Немає сертифіката матеріалу')
        if t['revision']!=r.revision:reasons.append('Не відповідає версія')
        if date.fromisoformat(t['valid_until'])<current:reasons.append('Строк пропозиції минув')
        arrival=current+timedelta(weeks=t['lead_weeks'])
        if arrival>r.required_by:reasons.append('Поставка пізніше потрібної дати')
        if t['currency']!=r.currency:reasons.append('Потрібен погоджений валютний курс')
        if q<t.get('moq',1):reasons.append('Менше мінімальної партії')
        if not spec_current or newest(item.document.code).id!=item.document_id:reasons.append('Є нова версія документа: потрібен перегляд')
        total=Decimal(t['unit_price'])*q+sum((Decimal(t.get(x,'0')) for x in ['setup','shipping','tooling','special_processes']),Decimal(0))
        rows.append({'id':item.pk,'code':item.code,'supplier_id':item.supplier_id,'supplier':item.supplier.name,'total':str(total),'currency':t['currency'],'arrival':str(arrival),'reasons':reasons,'terms':t,'document_id':item.document_id})
    eligible=[x for x in rows if not x['reasons']]
    chosen=min(eligible,key=lambda x:Decimal(x['total']))['code'] if eligible else None
    from erp.balances import request_allocated
    allocated=request_allocated(r)
    return {'request':{'id':r.pk,'code':r.code,'part':r.part,'revision':r.revision,'quantity':q,'original_quantity':r.quantity,'allocated_quantity':str(allocated),'remaining_quantity':str(max(Decimal(0),Decimal(r.quantity)-allocated)),'unit':r.unit,'required_by':str(r.required_by),'owner':r.owner.full_name,'owner_id':r.owner_id,'document_id':r.document_id,'details':r.details},'rows':rows,'recommended':chosen,'simulation':quantity is not None,'as_of':str(current)}

def validate(data):
    if not isinstance(data,dict):raise ValueError('Потрібен об’єкт дії.')
    action=data.get('action')
    if isinstance(action,str) and action.startswith('erp_'):
        from erp.service import clean
        return clean(data)
    from tasks.commands import clean
    return clean(data)

def fingerprint(payload):
    if payload.get('action') in ('create_task','update_task'):
        from tasks.commands import fingerprint as task_fingerprint
        return task_fingerprint(payload)
    if payload.get('action')=='erp_import_batch':
        from erp.importing import fingerprint as batch_fingerprint
        return batch_fingerprint()
    if payload.get('action','').startswith('erp_'):
        from erp.service import fingerprint as erp_fingerprint
        return erp_fingerprint()
    state={'payload':payload,'employees':list(Employee.objects.values('id','full_name')),'docs':list(Document.objects.values('id','checksum','status'))}
    if payload.get('task_id'):state['task']=Task.objects.filter(pk=payload['task_id']).values().first()
    if payload.get('request_code'):state['request']=ProcurementRequest.objects.filter(code=payload['request_code']).values().first();state['quotes']=list(SupplierQuote.objects.filter(request__code=payload['request_code']).values())
    return hashlib.sha256(json.dumps(state,sort_keys=True,default=str).encode()).hexdigest()

@transaction.atomic
def preview(request,payload,snapshot_fingerprint=None):
    from finance.statements import ACTIONS as STATEMENT_ACTIONS,preview as statement_preview
    if isinstance(payload,dict) and payload.get('action') in STATEMENT_ACTIONS:return statement_preview(request,payload)
    if isinstance(payload,dict) and payload.get('action') in ('create_task','update_task'):
        from tasks.commands import preview as task_preview
        return task_preview(request,payload)
    if isinstance(payload,dict) and payload.get('action')=='erp_import_batch':
        raise ValueError('Пакет імпорту потребує окремого перегляду файла.')
    principal=actor(request);role=principal.role
    if role not in ('ceo','manager'):raise PermissionError('Спостерігач не може змінювати записи.')
    if not request.session.session_key:request.session.create()
    payload=validate(payload)
    Policy(request).action(payload)
    if payload['action'].startswith('erp_') and snapshot_fingerprint is None:
        from erp.service import write_lock
        write_lock()
    proposal=ActionProposal.objects.create(session_key=request.session.session_key,user_id=principal.user_id,role=role,payload=payload,fingerprint=snapshot_fingerprint or fingerprint(payload),expires_at=timezone.now()+timedelta(minutes=10))
    return {'id':str(proposal.id),'payload':payload,'expires_at':proposal.expires_at.isoformat()}

@transaction.atomic
def execute(request,proposal_id):
    principal=actor(request)
    p=ActionProposal.objects.filter(id=proposal_id,session_key=request.session.session_key).first()
    if not p:raise PermissionError('Погодження недоступне в цій сесії.')
    if p.user_id != principal.user_id or principal.role!=p.role or p.role not in ('ceo','manager'):raise PermissionError('Немає дозволу на виконання. Підготуйте власне нове погодження.')
    if p.payload['action'].startswith('erp_') or p.payload['action'] in ('create_task','update_task'):
        from erp.service import write_lock
        write_lock()
        # A competing confirmation may have completed while acquiring the mutex.
        p.refresh_from_db()
        principal=actor(request)
        if p.user_id != principal.user_id or principal.role != p.role:
            raise PermissionError('Повноваження змінилися. Підготуйте нове погодження.')
    if p.payload.get('action')=='erp_import_batch':
        from erp.importing import locked_references
        locked_references(p.payload['batch'])
    if p.payload['action'] in ('create_task','update_task'):
        request._bos_task_command=True
        from tasks.commands import locked_references
        locked_references(p.payload)
    policy=Policy(request);policy.action(p.payload)
    from finance import statements
    if p.payload['action'] in statements.ACTIONS:
        d=statements.clean(p.payload);statements.lock_selected(d)
        # Verify actual source bytes even on a stored receipt replay.
        current_fingerprint=statements.fingerprint(d,policy)
        if p.receipt:return projections.receipt(policy,p.receipt)
        plan=statements.prepare(d,policy)
        if not plan['no_change'] and (p.expires_at<timezone.now() or p.fingerprint!=current_fingerprint):
            raise Conflict('Дані або строк погодження змінилися. Підготуйте новий перегляд.')
        if not ActionProposal.objects.filter(pk=p.pk,receipt__isnull=True).update(receipt={'state':'running'}):raise Conflict('Дія вже виконується.')
        receipt=statements.apply(d,policy,plan);p.receipt=receipt;p.save(update_fields=['receipt'])
        return projections.receipt(policy,receipt)
    if p.receipt:return projections.receipt(policy,p.receipt)
    from erp.corrections import ACTIONS as CORRECTION_ACTIONS,replay as correction_replay
    if p.payload['action'] in CORRECTION_ACTIONS:
        receipt=correction_replay(validate(p.payload),principal)
        if receipt is not None:
            p.receipt=receipt;p.save(update_fields=['receipt']);return projections.receipt(policy,receipt)
    if p.payload['action'] in ('create_task','update_task'):
        from tasks.commands import ConfirmConflict
        if p.expires_at<timezone.now():raise ConfirmConflict('proposal_expired','Строк погодження минув. Дію не виконано; підготуйте новий перегляд.')
        if p.fingerprint!=fingerprint(p.payload):raise ConfirmConflict('proposal_stale','Дані погодження змінилися. Дію не виконано; підготуйте новий перегляд.')
    elif p.expires_at<timezone.now() or p.fingerprint!=fingerprint(p.payload):raise Conflict('Дані або строк погодження змінилися. Підготуйте новий перегляд.')
    # Compare-and-set claim; task, audit and receipt roll back together on failure.
    if not ActionProposal.objects.filter(pk=p.pk,receipt__isnull=True).update(receipt={'state':'running'}):raise Conflict('Дія вже виконується. Повторіть запит.')
    d=validate(p.payload)
    if d['action']=='erp_import_batch':
        from erp.importing import confirm_batch
        receipt=confirm_batch(request,d);p.receipt=receipt;p.save(update_fields=['receipt'])
        return projections.receipt(Policy(request),receipt)
    if d['action'] in CORRECTION_ACTIONS:
        from erp.service import dispatch
        from erp.queries import snapshot
        from erp.experience import impact
        from erp.models import Event
        before=snapshot(Policy(request));receipt=dispatch(d,p.role,correction_actor=principal);receipt['impact']=impact(before,snapshot(Policy(request)))
        Event.objects.filter(pk=receipt['erp_event_id']).update(result=receipt)
        p.receipt=receipt;p.save(update_fields=['receipt']);return projections.receipt(Policy(request),receipt)
    if d['action'].startswith('erp_'):
        from erp.service import dispatch
        from erp.queries import snapshot
        from erp.experience import impact
        from erp.models import Event
        before=snapshot(Policy(request));result=dispatch(d,p.role);delta=impact(before,snapshot(Policy(request)))
        Event.objects.filter(pk=result['erp_event_id']).update(result={**result,'impact':delta,'actor_id':principal.user_id,'actor_role':principal.role})
        receipt={'state':'succeeded',**result,'impact':delta};p.receipt=receipt;p.save(update_fields=['receipt']);return projections.receipt(Policy(request),receipt)
    from tasks.commands import apply as apply_task
    receipt=apply_task(request,d);p.receipt=receipt;p.save(update_fields=['receipt']);return projections.receipt(Policy(request),receipt)
