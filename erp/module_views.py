"""Private authenticated GET for the server-owned module registry."""
from functools import wraps

from django.http import JsonResponse
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_GET

from boss_project.identity import IdentityDenied
from boss_project.policy import Policy
from . import module_registry


def private_response(view):
    @wraps(view)
    def call(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        patch_vary_headers(response, ('Cookie',))
        return response
    return call


@private_response
@require_GET
def registry(request):
    try:
        policy = Policy(request)
        revision = policy.access_revision()
        data = module_registry.build(policy)
        if revision != Policy(request).access_revision():
            return JsonResponse({'code': 'read_state_changed', 'error': 'Права змінилися. Оновіть розділ.'}, status=409)
    except IdentityDenied as exc:
        return JsonResponse({'code': 'identity_denied', 'error': str(exc)}, status=exc.status)
    except module_registry.RegistryConfigurationError:
        return JsonResponse({'code': 'module_configuration_invalid',
            'error': 'Налаштування модулів недоступне. Потрібна перевірка адміністратора.'}, status=503)
    return JsonResponse(data, json_dumps_params={'ensure_ascii': False})
