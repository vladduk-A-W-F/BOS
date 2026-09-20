import json
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse,HttpResponse
from django.views.decorators.http import require_GET,require_POST
from operations.views import errors,body
from operations import service as approvals
from . import service,queries,experience,adjustment_proposals
from django.db import transaction
from .models import SalesOrder,ChangeOrder,Production
from boss_project.identity import actor
from boss_project.policy import Policy, CEO_ACTIONS
from operations import projections

@require_GET
@errors
def snapshot(request):
    p=Policy(request);data=queries.snapshot(p)
    data['home']=experience.home(data) if p.ceo else {'tasks':[{**row,'overdue':row['is_overdue']} for row in __import__('tasks.queries',fromlist=['project_list']).project_list(p.tasks().filter(archived_at__isnull=True))],'sources':'Доступні операційні записи.'}
    return JsonResponse(data,json_dumps_params={'ensure_ascii':False})

@require_POST
@errors
def preview(request):
    payload=service.clean(body(request))
    from finance.statements import ACTIONS as STATEMENT_ACTIONS,preview as statement_preview
    if payload['action'] in STATEMENT_ACTIONS:return JsonResponse(statement_preview(request,payload))
    p=Policy(request);p.action(payload);role=p.role
    with transaction.atomic():
        service.write_lock()
        token=service.fingerprint();p=Policy(request);p.action(payload)
        context=adjustment_proposals.capture(payload,p)
        current_snapshot=lambda:adjustment_proposals.snapshot(payload,Policy(request)) if context is not None else queries.snapshot(Policy(request))
        before=current_snapshot();effect=service.dispatch(payload,role,log=False,correction_actor=p.actor);after=current_snapshot()
        delta=experience.impact(before,after)
        if payload['action'].removeprefix('erp_') in service.CORRECTION_SCHEMAS:
            from .corrections import prospective
            effect,delta=prospective(effect,delta,before)
        effect=projections.receipt(Policy(request),effect)
        if context is not None:
            if Policy(request).access_revision()!=context['access_revision']:raise approvals.Conflict('Права змінилися під час перегляду.')
            context=adjustment_proposals.finish(context,effect,delta)
        transaction.set_rollback(True)
    proposal=approvals.preview(request,payload,snapshot_fingerprint=token,dependency_context=context);proposal['effect']=effect;proposal['impact']=delta
    return JsonResponse(proposal)


@require_GET
@errors
def workpoints(request):
    from .workpoints import build
    from .order_trace import ReadStateChanged
    try:
        return JsonResponse(build(request), json_dumps_params={'ensure_ascii': False})
    except ReadStateChanged:
        return JsonResponse({'error': 'Дані або права змінилися. Оновіть робочі точки.'}, status=409)

@require_GET
@errors
def change_impact(request,pk):
    p=Policy(request);change=p.queryset(ChangeOrder).get(pk=pk)
    return JsonResponse({'change':change.code,'revision':change.target_revision,'jobs':list(p.queryset(Production).filter(item=change.item).exclude(status='done').values('id','code','revision','status','due_date')),'orders':list(p.queryset(SalesOrder).filter(lines__item=change.item,status='confirmed').distinct().values('id','code','due_date'))})

@require_GET
@errors
def export(request):
    from .assistant import tools_contract,parameter_guide
    p=Policy(request);p.require_export();data=queries.snapshot(p);data['tools']=tools_contract();data['parameter_guide']=parameter_guide();data['instruction']='Відповідай українською, цитуй коди записів. Дати є симуляцією. Запропонуй одну JSON-дію з наведеного переліку; користувач має імпортувати та погодити її у BoS. Не вигадуй ID або виконання.'
    r=JsonResponse(data,json_dumps_params={'ensure_ascii':False,'indent':2});r['Content-Disposition']='attachment; filename="BoS_ERP_Context.json"';return r

@require_GET
@errors
def draft(request,pk):
    p=Policy(request);order=p.queryset(SalesOrder).get(pk=pk);plans=[queries.plan_line(x,p) for x in order.lines.all()]
    text='BoS · Чернетка уточнення щодо '+order.code+'\nНе надіслано\n\nПросимо підтвердити доступність, строк і комплектність документів для замовлення.\n'
    for p in plans:text+='\n'+p['item']+': залишок до поставки '+p['remaining']+'; розрахункова дата '+p['estimated_date']+'; '+('; '.join(p['reasons']) or 'уточнити остаточний графік')
    r=HttpResponse(text,content_type='text/plain; charset=utf-8');r['Content-Disposition']='attachment; filename="BoS_Order_Clarification.txt"';return r

@require_GET
@errors
def next_action(request,pk):
    p=Policy(request);order=p.queryset(SalesOrder).get(pk=pk);data=experience.next_step(order,p)
    payload=data.get('payload')
    if payload and not p.ceo:
        if p.role=='observer' or payload.get('action') in CEO_ACTIONS:
            data={**data,'payload':None}
        else:
            try:p.action(payload)
            except (PermissionError, ObjectDoesNotExist):data={**data,'payload':None}
    return JsonResponse(data,json_dumps_params={'ensure_ascii':False})


@require_GET
@errors
def order_trace(request,pk):
    from boss_project.identity import IdentityDenied
    from .order_trace import build, ReadStateChanged
    try:
        data=build(request,pk)
    except IdentityDenied as exc:
        response=JsonResponse({'error':str(exc),'code':'identity_denied'},status=exc.status)
        response['X-BoS-Identity']='denied'
        return response
    except ReadStateChanged:
        return JsonResponse({'error':'Дані або доступ змінилися. Оновіть картку.','code':'read_state_changed'},status=409)
    return JsonResponse(data,json_dumps_params={'ensure_ascii':False})
