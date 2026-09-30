from django.db import transaction
from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_GET, require_POST

from boss_project.policy import Policy
from operations.views import body, errors
from .access import require_training
from . import service


def response(value):
    result = JsonResponse(value, json_dumps_params={'ensure_ascii': False})
    result['Cache-Control'] = 'no-store'
    return result


@require_GET
@errors
@transaction.atomic
def content(request):
    return response(service.content(request))


@require_GET
@errors
def brochure(request):
    require_training(Policy(request))
    path = Path(settings.BASE_DIR) / 'docs' / 'BoS_3_0_Start_UA.pdf'
    if not path.is_file():
        raise Http404
    result = FileResponse(path.open('rb'), content_type='application/pdf',
                          as_attachment=True, filename=path.name)
    result['Cache-Control'] = 'private, no-store'
    return result


@require_GET
@errors
@transaction.atomic
def state(request, case_id):
    policy = Policy(request)
    marker = require_training(policy)
    return response(service.session_state(policy, marker, case_id))


@require_POST
@errors
def change(request, case_id, action):
    return response(service.change(request, case_id, action, body(request)))
