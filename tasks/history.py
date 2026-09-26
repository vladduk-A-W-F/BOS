"""Scoped immutable task history and read-only proposal recovery."""
from uuid import UUID
from datetime import datetime
from django.core import signing
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from boss_project.policy import Policy
from operations.models import AuditEvent,ActionProposal
from operations.views import errors
from operations.projections import receipt as project_receipt
from .commands import ACTIONS

SALT='bos.task-history.v1'
STATE_FIELDS={'handoff','title','assignee','assignee_id','assignee_name','deadline','order_id','order_code','request_code','history_refs','status','priority','category','branch_id','result','archived_at'}
CHANGE_FIELDS={'kind','id','field','label','before','after','code'}


def item(event):
    payload=event.payload;row={'id':str(event.pk),'action':event.action,'created_at':event.created_at.isoformat()}
    if not isinstance(payload,dict) or payload.get('schema')!='bos.task-change.v1':return {**row,'transition':None,'actor':None,'reason':None,'before':None,'after':None,'changes':[],'legacy':True,'note':'Структурований diff раніше не збережено.'}
    def state(value):return {k:v for k,v in value.items() if k in STATE_FIELDS} if isinstance(value,dict) else None
    who=payload.get('actor',{})
    return {**row,'transition':payload.get('transition'),'actor':{k:who[k] for k in ('id','role','display') if k in who},'reason':payload.get('reason'),
        'before':state(payload.get('before')),'after':state(payload.get('after')),'changes':[{k:v for k,v in r.items() if k in CHANGE_FIELDS} for r in payload.get('changes',[]) if isinstance(r,dict) and r.get('kind')=='tasks'],'handoff':__import__('tasks.handoffs',fromlist=['serialize_handoff']).serialize_handoff(payload.get('handoff')) if payload.get('transition')=='handoff' else None,'legacy':False}


def page(request,pk):
    policy=Policy(request);task=policy.tasks().get(pk=pk);raw=request.GET.get('limit','20')
    if not isinstance(raw,str) or not raw.isascii() or not raw.isdigit() or not 1<=int(raw)<=50:raise ValueError('limit: ціле число1–50.')
    limit=int(raw);cursor=request.GET.get('cursor');revision=policy.access_revision();cutoff=timezone.now();last=None
    if cursor:
        try:
            saved=signing.loads(cursor,salt=SALT)
            if set(saved)!={'task_id','actor_id','access_revision','cutoff','last'} or saved['task_id']!=task.pk or saved['actor_id']!=policy.actor.user_id or saved['access_revision']!=revision:raise ValueError
            cutoff=datetime.fromisoformat(saved['cutoff']);last=(datetime.fromisoformat(saved['last'][0]),UUID(saved['last'][1]))
            if timezone.is_naive(cutoff) or timezone.is_naive(last[0]):raise ValueError
        except (signing.BadSignature,ValueError,TypeError,KeyError,IndexError):raise ValueError('Некоректний cursor історії.')
    rows=AuditEvent.objects.filter(task=task,created_at__lte=cutoff)
    if last:rows=rows.filter(Q(created_at__lt=last[0])|Q(created_at=last[0],id__lt=last[1]))
    rows=list(rows.order_by('-created_at','-id')[:limit+1]);has_more=len(rows)>limit;rows=rows[:limit];next_cursor=None
    if has_more:
        final=rows[-1];next_cursor=signing.dumps({'task_id':task.pk,'actor_id':policy.actor.user_id,'access_revision':revision,'cutoff':cutoff.isoformat(),'last':[final.created_at.isoformat(),str(final.pk)]},salt=SALT,compress=True)
    return {'task_id':task.pk,'items':[item(row) for row in rows],'next_cursor':next_cursor}


@require_GET
@errors
def proposal_status(request,proposal_id):
    policy=Policy(request);proposal=ActionProposal.objects.filter(pk=proposal_id,user_id=policy.actor.user_id,payload__action__in=ACTIONS).first()
    if proposal is None:raise ActionProposal.DoesNotExist()
    if policy.role!=proposal.role:raise PermissionError('Повноваження змінилися; погодження не надає доступу.')
    policy.action(proposal.payload)
    if proposal.payload.get('action')=='handoff_task':
        from .handoffs import validate_replay
        validate_replay(request,proposal.payload)
    stored=proposal.receipt;state='unknown';receipt=None
    if isinstance(stored,dict) and stored.get('state')=='succeeded' and stored.get('task_id') and stored.get('audit_id'):
        policy.tasks().get(pk=stored['task_id']);event=AuditEvent.objects.get(pk=stored['audit_id'],task_id=stored['task_id'])
        if event.action!=proposal.payload['action']:raise ActionProposal.DoesNotExist()
        receipt=project_receipt(policy,stored);state='succeeded'
    elif stored is None:state='expired' if proposal.expires_at<timezone.now() else 'pending'
    return JsonResponse({'proposal_id':str(proposal.pk),'action':proposal.payload['action'],'state':state,'expires_at':proposal.expires_at.isoformat(),'same_session':proposal.session_key==request.session.session_key,'receipt':receipt})
