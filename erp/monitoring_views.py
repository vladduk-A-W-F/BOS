"""Read-only BoS 4 monitoring API over Policy-scoped rows."""
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from boss_project.policy import Policy
from operations.views import errors
from . import monitoring
from .network_views import identity_errors


@identity_errors
@errors
@require_GET
def overview(request):
    return JsonResponse(monitoring.build(Policy(request)))


@identity_errors
@errors
@require_GET
def standard_query(request, key):
    return JsonResponse(monitoring.query(Policy(request), key))
