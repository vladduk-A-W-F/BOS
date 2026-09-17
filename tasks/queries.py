"""One task projection, historical source scope and overdue partition."""
from django.db.models import Q,Count
from .models import Task


def as_of():
    from operations.service import as_of as current
    return current()


def active(rows=None):return (Task.objects.all() if rows is None else rows).filter(archived_at__isnull=True)
def overdue_q():return Q(archived_at__isnull=True,deadline__lt=as_of())&~Q(status='done')
def is_overdue(task):return task.archived_at is None and task.status!='done' and task.deadline is not None and task.deadline<as_of()


def statistics(rows):
    rows=active(rows);overdue=overdue_q()
    values=rows.aggregate(total=Count('pk'),done=Count('pk',filter=Q(status='done')),overdue=Count('pk',filter=overdue),process=Count('pk',filter=Q(status='process')&~overdue))
    values['active']=values['total']-values['done']-values['overdue']-values['process'];values['completion_rate']=round(100*values['done']/values['total']) if values['total'] else 0
    return values


def source_refs(task):
    from operations.models import AuditEvent
    refs=[]
    if task.sales_order_id:refs.append({'order_id':task.sales_order_id})
    for payload in AuditEvent.objects.filter(task_id=task.pk).values_list('payload',flat=True):
        if not isinstance(payload,dict):continue
        if payload.get('request_code') is not None:refs.append({'request_code':payload['request_code']})
        if payload.get('order_id') is not None:refs.append({'order_id':payload['order_id']})
        if payload.get('schema')=='bos.task-change.v1':
            rows=payload.get('source_refs',[])
            if not isinstance(rows,list):return None
            refs.extend(rows)
    normalized=[]
    for ref in refs:
        if not isinstance(ref,dict) or set(ref) not in ({'order_id'},{'request_code'}):return None
        if 'order_id' in ref and (type(ref['order_id']) is not int or ref['order_id']<=0):return None
        if 'request_code' in ref and (not isinstance(ref['request_code'],str) or not ref['request_code']):return None
        if ref not in normalized:normalized.append(ref)
    return normalized


def visible_tasks(policy):
    from operations.models import ProcurementRequest
    rows=Task.objects.all()
    if policy.ceo:return rows
    orders=policy.erp_ids()['order_id'];requests=set(policy.requests().values_list('code',flat=True));allowed=[]
    for task in rows:
        refs=source_refs(task)
        if refs is not None and all((r['order_id'] in orders if 'order_id' in r else r['request_code'] in requests) for r in refs):allowed.append(task.pk)
    return rows.filter(pk__in=allowed)


def project(task):
    return {'id':task.pk,'title':task.title,'priority':task.priority,'status':task.status,'assignee':task.assignee,
        'deadline':task.deadline.isoformat() if task.deadline else None,'category':task.category,'branch':task.branch_id,'branch_name':task.branch.name if task.branch_id else None,'created_at':task.created_at.isoformat() if task.created_at else None,
        'assignee_id':task.assignee_employee_id,'assignee_name':task.assignee_employee.full_name if task.assignee_employee_id else task.assignee,
        'order_id':task.sales_order_id,'order_code':task.sales_order.code if task.sales_order_id else None,'result':task.result,
        'result_recorded':isinstance(task.result,str) and len(task.result.strip())>=3,'archived_at':task.archived_at.isoformat() if task.archived_at else None,'archived':task.archived_at is not None,'is_overdue':is_overdue(task)}


def project_list(rows):return [project(task) for task in rows.select_related('assignee_employee','sales_order','branch')]
