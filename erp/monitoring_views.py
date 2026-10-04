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


@require_GET
def showcase(request):
    """Public first screen: only the synthetic demo cases of a demo database."""
    from django.conf import settings
    from operations.models import Configuration
    from training.access import enabled
    cases = Configuration.objects.filter(key='demo_cases').first()
    if (settings.BOS_DATA_MODE != 'demo' or enabled() or cases is None
            or not isinstance(cases.value, dict) or cases.value.get('synthetic') is not True):
        return JsonResponse({'cases': []})
    company = Configuration.objects.filter(key='organization').first()
    name = company.value.get('name', '') if company and isinstance(company.value, dict) else ''
    return JsonResponse({'company': name, 'cases': cases.value.get('cases', [])})
