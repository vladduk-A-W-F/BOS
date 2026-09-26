from django.http import JsonResponse
from django.views.decorators.http import require_GET

from boss_project.policy import Policy
from operations.views import errors
from . import projections


@require_GET
@errors
def index(request):
    return JsonResponse({'items': projections.rows(Policy(request))})


@require_GET
@errors
def deal(request, deal_id):
    return JsonResponse(projections.detail(Policy(request), deal_id))


@require_GET
@errors
def handoff(request, training_public_id):
    return JsonResponse(projections.draft(Policy(request), training_public_id, request.GET.get('case_id')))
