"""Read-only committed outcome lookup; unknown is never proof of no commit."""
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.core.exceptions import ObjectDoesNotExist
from operations.views import errors
from operations import projections
from boss_project.identity import actor
from boss_project.policy import Policy
from . import corrections


@require_GET
@errors
def outcome(request):
    policy=Policy(request)
    if set(request.GET)!={'action','operation_id'} or any(len(request.GET.getlist(k))!=1 for k in request.GET):raise ValueError('Потрібні рівно action та operation_id.')
    action=request.GET['action'];operation=corrections.uuid(request.GET['operation_id'])
    if action not in corrections.ACTIONS:raise ValueError('Невідома дія коригування.')
    policy.action({'action':action})
    model=corrections.DOCUMENT_MODELS[action.removeprefix('erp_')]
    try:
        row=model.objects.select_related('event').get(operation_id=operation,event__action=action)
        policy.action(row.event.payload)
        receipt=corrections.replay(row.event.payload,actor(request))
        if receipt is None:raise ObjectDoesNotExist
        receipt=projections.receipt(policy,receipt)
    except ObjectDoesNotExist:return JsonResponse({'state':'unknown','receipt':None},status=404)
    return JsonResponse({'state':'succeeded','action':action,'operation_id':operation,'receipt':receipt})
