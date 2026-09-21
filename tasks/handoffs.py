"""Guarded handoff of one existing linked Task; no model, migration or acceptance flow."""
from copy import deepcopy
from datetime import date
import hashlib,json
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from employees.models import Employee
from branches.models import Branch
from .models import Task
from .queries import as_of,source_refs,is_overdue
from boss_project.policy import Policy
from boss_project.identity import actor
from operations.models import AuditEvent,Configuration,Document,ProcurementRequest
from erp.models import SalesOrder
ACTION='handoff_task';KEYS={'action','task_id','assignee_id','expected_result','deadline','reason'}

def clean(payload):
 if not isinstance(payload,dict) or set(payload)!=KEYS or payload.get('action')!=ACTION:raise ValueError('Потрібен точний payload передавання доручення.')
 d=deepcopy(payload)
 for key in ('task_id','assignee_id'):
  if type(d[key]) is not int or d[key]<=0:raise ValueError('Потрібен фактичний позитивний ID: '+key)
 for key,lo,hi in (('expected_result',3,2000),('reason',3,1000)):
  if not isinstance(d[key],str) or not lo<=len(d[key].strip())<=hi:raise ValueError('Некоректний '+key+'.')
  d[key]=d[key].strip()
 if not isinstance(d['deadline'],str) or date.fromisoformat(d['deadline']).isoformat()!=d['deadline'] or date.fromisoformat(d['deadline'])<as_of():raise ValueError('Потрібна дата не раніше server as_of.')
 return d

def locked_references(payload):
 task=Task.objects.select_for_update().get(pk=payload['task_id']);ids={payload.get('assignee_id'),task.assignee_employee_id};ids.discard(None)
 list(Employee.objects.select_for_update().filter(pk__in=sorted(ids)).order_by('pk'));return task

def _dept(employee):
 if employee is None:return {'id':None,'name':None}
 branch=employee.branch
 return {'id':branch.pk if branch and branch.type=='department' else None,'name':branch.name if branch and branch.type=='department' else None}

def _recipient(employee):
 if employee.archived_at is not None or employee.user_id is None:raise PermissionError('Отримувач повинен мати активний пов’язаний обліковий запис.')
 if not employee.branch_id or employee.branch.type!='department':raise PermissionError('Отримувач не має явної належності до підрозділу.')
 user=get_user_model().objects.filter(pk=employee.user_id,is_active=True).first()
 if user is None:raise PermissionError('Обліковий запис отримувача неактивний.')
 policy=Policy.for_user(user)
 if policy.role not in ('ceo','manager'):raise PermissionError('Роль отримувача не може приймати доручення.')
 return user,policy

def _check_sources(policy,refs):
 if not refs:raise ValueError('Передавання потребує непорожніх валідних накопичених джерел.')
 for ref in refs:
  if 'order_id' in ref:policy.queryset(SalesOrder).get(pk=ref['order_id'])
  else:policy.requests().get(code=ref['request_code'])

def _state(task,refs):
 from .commands import state
 return state(task,refs)

def _validated(request,payload,*,replay=False):
 sender=Policy(request);sender.action(payload);task=sender.tasks().select_related('assignee_employee','branch','sales_order').get(pk=payload['task_id']);refs=source_refs(task);_check_sources(sender,refs)
 recipient=Employee.objects.select_related('branch','user').get(pk=payload['assignee_id']);recipient_user,recipient_policy=_recipient(recipient);_check_sources(recipient_policy,refs)
 if not replay:
  if task.archived_at is not None or task.status=='done':raise ValueError('Передавати можна лише неархівне незавершене доручення.')
  if not sender.ceo and sender.actor.employee_id!=task.assignee_employee_id:raise PermissionError('Менеджер передає лише власне поточне доручення.')
  if task.assignee_employee_id==recipient.pk:raise ValueError('Отримувач має відрізнятися від поточного виконавця.')
 return sender,task,refs,recipient,recipient_user

def prepare(request,payload):
 sender,task,refs,recipient,user=_validated(request,payload);before=_state(task,refs);obj=deepcopy(task);obj.assignee_employee=recipient;obj.assignee='';obj.status='active';obj.deadline=date.fromisoformat(payload['deadline']);after=_state(obj,refs)
 handoff={'schema':'bos.task-handoff.v1','state':'sent','sender':{'user_id':sender.actor.user_id,'employee_id':sender.actor.employee_id,'role':sender.role,'department':_dept(Employee.objects.select_related('branch').filter(pk=sender.actor.employee_id).first())},'previous_assignee':{'employee_id':task.assignee_employee_id},'recipient':{'user_id':user.pk,'employee_id':recipient.pk,'role':Policy.for_user(user).role,'department':_dept(recipient)},'expected_result':payload['expected_result'],'deadline':payload['deadline'],'source_refs':deepcopy(refs),'as_of':str(as_of())}
 changes=[]
 for field,label,b,a in [('assignee_id','Передано відповідальному',before['assignee_id'],after['assignee_id']),('deadline','Строк передавання',before['deadline'],after['deadline']),('status','Статус передавання',before['status'],after['status'])]:
  if b!=a:changes.append({'kind':'tasks','id':task.pk,'field':field,'label':label,'before':b,'after':a,'code':task.title})
 return {'object':obj,'before':before,'after':after,'refs':refs,'handoff':handoff,'changes':changes,'operation':'handoff','changed':True}

def validate_replay(request,payload):
 """Fresh server-side source/recipient checks for confirm replay and status."""
 return _validated(request,payload,replay=True)

def fingerprint(payload):
 task=Task.objects.filter(pk=payload.get('task_id')).first();ids={payload.get('assignee_id'),task.assignee_employee_id if task else None};ids.discard(None)
 employees=list(Employee.objects.filter(pk__in=ids).values('id','user_id','archived_at','branch_id'));branches=list(Branch.objects.filter(employees__id__in=ids).distinct().values('id','type','name'));users=list(get_user_model().objects.filter(employee__id__in=ids).order_by('pk').values('id','is_active'));permissions={r['id']:sorted(get_user_model().objects.get(pk=r['id']).get_all_permissions()) for r in users};roles={r['id']:sorted(get_user_model().objects.get(pk=r['id']).groups.values_list('name',flat=True)) for r in users}
 refs=source_refs(task) if task else None;data={'as_of':str(as_of()),'payload':payload,'task':list(Task.objects.filter(pk=payload.get('task_id')).values()),'history':list(AuditEvent.objects.filter(task_id=payload.get('task_id')).order_by('pk').values()),'refs':refs,'employees':employees,'branches':branches,'users':users,'roles':roles,'permissions':permissions,'orders':list(SalesOrder.objects.values()),'requests':list(ProcurementRequest.objects.values()),'documents':list(Document.objects.values('id','code','revision','checksum','status','access_level')),'dataset':list(Configuration.objects.filter(key='dataset').values())}
 return hashlib.sha256(json.dumps(data,cls=DjangoJSONEncoder,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def apply(request,payload):
 plan=prepare(request,payload);obj=plan['object'];obj.save(update_fields=['assignee_employee','assignee','status','deadline']);event=AuditEvent.objects.create(action=ACTION,task=obj,payload={'schema':'bos.task-change.v1','transition':'handoff','actor_id':plan['handoff']['sender']['user_id'],'actor_role':plan['handoff']['sender']['role'],'actor':{'id':plan['handoff']['sender']['user_id'],'role':plan['handoff']['sender']['role']},'reason':payload['reason'],'as_of':str(as_of()),'before':plan['before'],'after':plan['after'],'changes':plan['changes'],'source_refs':plan['refs'],'handoff':plan['handoff']})
 return {'state':'succeeded','action':ACTION,'task_id':obj.pk,'audit_id':str(event.pk),'handoff':serialize_handoff(plan['handoff']),'impact':plan['changes']}

def serialize_handoff(value):
 if not isinstance(value,dict):return None
 def person(v):
  return {k:v.get(k) for k in ('user_id','employee_id','role','department') if k in v} if isinstance(v,dict) else None
 refs=value.get('source_refs') if isinstance(value.get('source_refs'),list) else []
 return {'schema':value.get('schema'),'state':value.get('state'),'sender':person(value.get('sender')),'previous_assignee':person(value.get('previous_assignee')),'recipient':person(value.get('recipient')),'expected_result':value.get('expected_result'),'deadline':value.get('deadline'),'source_refs':[r for r in refs if isinstance(r,dict) and set(r) in ({'order_id'},{'request_code'})],'as_of':value.get('as_of')}

def latest(task):
 events=list(AuditEvent.objects.filter(task_id=task.pk).order_by('-created_at','-id').values('action','payload'))
 for index,row in enumerate(events):
  if row['action']!=ACTION:continue
  h=row['payload'].get('handoff') if isinstance(row['payload'],dict) else None
  if not isinstance(h,dict):continue
  later=events[:index];superseded=any(e['action']!=ACTION and isinstance(e['payload'],dict) and isinstance(e['payload'].get('after'),dict) and e['payload']['after'].get('assignee_id')!=h.get('recipient',{}).get('employee_id') for e in later)
  current=not superseded and task.assignee_employee_id==h.get('recipient',{}).get('employee_id')
  result=serialize_handoff(h);result.update({'state':'sent' if current else 'superseded','current':current});return result
 return None
