"""C01 proposal-only writer. No raw REST/admin mutation or hidden completion."""
from copy import deepcopy
from datetime import date,timedelta
import hashlib,json
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from boss_project.identity import actor
from boss_project.policy import Policy
from boss_project.data_rules import portable_tree,text_value
from employees.models import Employee
from operations.models import ActionProposal,AuditEvent,Configuration,Document,ProcurementRequest
from erp.models import SalesOrder
from .models import Task
from .queries import as_of,project,source_refs,is_overdue

ACTIONS={'create_task','update_task','handoff_task'}
FIELDS={'title','category','priority','assignee_id','deadline','order_id','status','result','archived'}
LABELS={'title':'Назва','category':'Категорія','priority':'Пріоритет','assignee_id':'Відповідальний','deadline':'Строк','order_id':'Замовлення','status':'Статус','result':'Результат','archived':'В архіві','is_overdue':'Прострочено'}

class ConfirmConflict(Exception):
    def __init__(self,code,message):self.code=code;super().__init__(message)


def clean(payload):
    if not isinstance(payload,dict) or payload.get('action') not in ACTIONS:raise ValueError('Невідома дія доручення.')
    if payload.get('action')=='handoff_task':
        from .handoffs import clean as clean_handoff
        return clean_handoff(payload)
    portable_tree(payload);d=deepcopy(payload);create=d['action']=='create_task'
    required={'action','title','assignee_id','deadline'} if create else {'action','task_id','reason'}
    allowed=required|({'category','priority','order_id','request_code'} if create else FIELDS)
    if not required<=set(d) or set(d)-allowed:raise ValueError('Перевірте обов’язкові та зайві поля доручення.')
    if not create and not set(d)&FIELDS:raise ValueError('Заявлено жодного поля зміни.')
    if not create and 'archived' in d and set(d)!=required|{'archived'}:raise ValueError('Архівування чи відновлення погоджується окремо.')
    for key in ('task_id','assignee_id','order_id'):
        if key in d and not (key=='order_id' and d[key] is None) and (type(d[key]) is not int or d[key]<=0):raise ValueError('Потрібен фактичний позитивний ID: '+key)
    if 'title' in d:
        if not isinstance(d['title'],str) or not 3<=len(d['title'].strip())<=200:raise ValueError('Назва:3–200 символів.')
        d['title']=d['title'].strip()
    if 'category' in d:text_value(d['category'],maximum=50,path='category')
    if 'priority' in d:
        if d['priority'] in ('','none'):d['priority']=None
        if d['priority'] not in ('high','medium','low',None):raise ValueError('Некоректний пріоритет.')
    if 'deadline' in d:
        if not isinstance(d['deadline'],str) or date.fromisoformat(d['deadline']).isoformat()!=d['deadline']:raise ValueError('Потрібна календарна дата YYYY-MM-DD.')
    if 'request_code' in d and (not isinstance(d['request_code'],str) or not d['request_code']):raise ValueError('Потрібен код фактичної вимоги.')
    if 'status' in d and d['status'] not in ('active','process','done'):raise ValueError('Новий статус: active/process/done.')
    if 'result' in d:
        text_value(d['result'],maximum=2000,path='result')
    if 'archived' in d and type(d['archived']) is not bool:raise ValueError('archived має бути boolean.')
    if not create:
        if not isinstance(d['reason'],str) or not 3<=len(d['reason'].strip())<=1000:raise ValueError('Потрібна причина:3–1000 символів.')
        d['reason']=d['reason'].strip()
    else:
        d.setdefault('category','Закупівлі' if d.get('request_code') else 'Загальне');d.setdefault('priority','medium');d.setdefault('order_id',None)
    return d


def locked_references(payload):
    if payload['action']=='handoff_task':
        from .handoffs import locked_references as locked_handoff
        return locked_handoff(payload)
    task=Task.objects.select_for_update().get(pk=payload['task_id']) if payload['action']=='update_task' else None
    ids={pk for pk in (payload.get('assignee_id'),task.assignee_employee_id if task else None) if pk}
    list(Employee.objects.select_for_update().filter(pk__in=sorted(ids)).order_by('pk'))
    return task


def check_sources(policy,refs):
    if refs is None:raise Task.DoesNotExist()
    for ref in refs:
        if 'order_id' in ref:policy.queryset(SalesOrder).get(pk=ref['order_id'])
        else:policy.requests().get(code=ref['request_code'])


def state(task,refs):
    row=project(task);row['branch_id']=row.pop('branch');row.pop('branch_name');row.pop('id');row.pop('created_at');row.pop('archived');row.pop('result_recorded');row.pop('is_overdue')
    row['history_refs']=deepcopy(refs);row['request_code']=next((r['request_code'] for r in refs if 'request_code' in r),None)
    return row


def prepare(request,payload,task=None):
    if payload.get('action')=='handoff_task':
        from .handoffs import prepare as prepare_handoff
        return prepare_handoff(request,payload)
    policy=Policy(request);policy.action(payload);create=payload['action']=='create_task'
    if not create:task=policy.tasks().select_related('assignee_employee','sales_order','branch').get(pk=payload['task_id'])
    if create and date.fromisoformat(payload['deadline'])<as_of():raise ValueError('Дедлайн нового доручення не може бути в минулому.')
    refs=[] if create else source_refs(task);check_sources(policy,refs);before_refs=deepcopy(refs)
    if payload.get('order_id') is not None and {'order_id':payload['order_id']} not in refs:refs.append({'order_id':payload['order_id']})
    if payload.get('request_code') is not None and {'request_code':payload['request_code']} not in refs:refs.append({'request_code':payload['request_code']})
    check_sources(policy,refs)
    assignee=None
    if 'assignee_id' in payload:
        assignee=Employee.objects.get(pk=payload['assignee_id'])
        if assignee.archived_at is not None:raise ValueError('Архівного працівника не можна призначити.')
    before=None if create else state(task,before_refs)
    if create:
        obj=Task(title=payload['title'],assignee='',assignee_employee=assignee,deadline=date.fromisoformat(payload['deadline']),category=payload['category'],priority=payload['priority'],status='active',result='',branch_id=assignee.branch_id,sales_order_id=payload['order_id']);operation='create'
    else:
        obj=deepcopy(task);operation='update'
        if 'archived' in payload:
            desired=payload['archived'];obj.archived_at=timezone.now() if desired and task.archived_at is None else task.archived_at if desired else None;operation='archive' if desired else 'restore'
        else:
            if task.archived_at is not None:raise ValueError('Спочатку відновіть доручення з архіву.')
            for key in set(payload)&FIELDS:
                field={'assignee_id':'assignee_employee_id','order_id':'sales_order_id'}.get(key,key);value=payload[key];setattr(obj,field,date.fromisoformat(value) if key=='deadline' else value)
            completion=obj.status=='done' and task.status!='done';result_correction=task.status=='done' and obj.status=='done' and 'result' in payload
            if task.status=='done' and obj.status in ('active','process') and 'result' in payload and payload['result']!=task.result:raise ValueError('Повторне відкриття зберігає попередній результат; змініть чернетку окремим погодженням.')
            if completion or result_correction:
                if not obj.assignee_employee_id or 'result' not in payload or len(payload['result'].strip())<3:raise ValueError('Завершення потребує явного виконавця та нового змістовного результату.')
                operation='complete' if completion else 'result_correction'
                if completion and 'priority' not in payload:obj.priority=None
            elif task.status=='done' and obj.status in ('active','process'):operation='reopen'
    after=state(obj,refs);changes=[]
    for field,label in LABELS.items():
        if field=='archived':a=bool(task and task.archived_at);b=bool(obj.archived_at)
        elif field=='is_overdue':a=is_overdue(task) if task else False;b=is_overdue(obj)
        elif field=='assignee_id':a={'id':before[field],'name':before['assignee_name']} if before else None;b={'id':after[field],'name':after['assignee_name']}
        elif field=='order_id':a={'id':before[field],'code':before['order_code']} if before else None;b={'id':after[field],'code':after['order_code']}
        else:a=before.get(field) if before else None;b=after[field]
        if a!=b:changes.append({'kind':'tasks','id':task.pk if task else None,'field':field,'label':label,'before':a,'after':b,'code':obj.title})
    return {'object':obj,'before':before,'after':after,'refs':refs,'changes':changes,'operation':operation,'changed':create or bool(changes)}


def fingerprint(payload):
    if payload.get('action')=='handoff_task':
        from .handoffs import fingerprint as handoff_fingerprint
        return handoff_fingerprint(payload)
    task=Task.objects.filter(pk=payload.get('task_id')).first();employee_ids={pk for pk in (payload.get('assignee_id'),task.assignee_employee_id if task else None) if pk}
    data={'as_of':str(as_of()),'payload':payload,'task':list(Task.objects.filter(pk=payload.get('task_id')).values()),'history':list(AuditEvent.objects.filter(task_id=payload.get('task_id')).order_by('pk').values()),
        'employees':list(Employee.objects.filter(pk__in=employee_ids).order_by('pk').values('id','full_name','archived_at','branch_id')),
        'orders':list(SalesOrder.objects.order_by('pk').values()),'requests':list(ProcurementRequest.objects.order_by('pk').values()),'documents':list(Document.objects.order_by('pk').values('id','code','revision','checksum','status','access_level')),
        'items':__import__('erp.service',fromlist=['fingerprint']).fingerprint(),'dataset':list(Configuration.objects.filter(key='dataset').values())}
    return hashlib.sha256(json.dumps(data,cls=DjangoJSONEncoder,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def preview(request,payload):
    from erp.service import write_lock
    request._bos_task_command=True;payload=clean(payload)
    with transaction.atomic():
        write_lock();locked_references(payload);plan=prepare(request,payload);stamp=fingerprint(payload);transaction.set_rollback(True)
    if not plan['changed']:return {'state':'no_change','id':None,'payload':payload,'expires_at':None,'effect':{'entity':'task','task_id':payload['task_id'],'note':'Зміни не потрібні.'},'impact':[]}
    principal=actor(request)
    if not request.session.session_key:request.session.create()
    proposal=ActionProposal.objects.create(user_id=principal.user_id,session_key=request.session.session_key,role=principal.role,payload=payload,fingerprint=stamp,expires_at=timezone.now()+timedelta(minutes=10))
    return {'id':str(proposal.pk),'payload':payload,'expires_at':proposal.expires_at.isoformat(),'effect':{'entity':'task','task_id':payload.get('task_id'),'operation':plan['operation']},'impact':plan['changes']}


def apply(request,payload):
    if payload.get('action')=='handoff_task':
        from .handoffs import apply as apply_handoff
        return apply_handoff(request,payload)
    locked_references(payload);plan=prepare(request,payload)
    if not plan['changed']:raise ConfirmConflict('proposal_stale','Зміни вже не відповідають погодженому стану. Підготуйте новий перегляд.')
    obj=plan['object'];obj.save();principal=actor(request);user=get_user_model().objects.get(pk=principal.user_id)
    display=Employee.objects.filter(user_id=user.pk).values_list('full_name',flat=True).first() or user.get_full_name() or user.get_username()
    changes=[{**row,'id':obj.pk} for row in plan['changes']]
    event=AuditEvent.objects.create(action=payload['action'],task=obj,payload={'schema':'bos.task-change.v1','transition':plan['operation'],'actor_id':principal.user_id,'actor_role':principal.role,'actor':{'id':principal.user_id,'role':principal.role,'display':display},
        'reason':payload.get('reason','Створено погоджене доручення.'),'as_of':str(as_of()),'before':plan['before'],'after':state(obj,plan['refs']),'changes':changes,'source_refs':plan['refs'],'request_code':next((r['request_code'] for r in plan['refs'] if 'request_code' in r),None)})
    return {'state':'succeeded','task_id':obj.pk,'audit_id':str(event.pk),'impact':changes}
