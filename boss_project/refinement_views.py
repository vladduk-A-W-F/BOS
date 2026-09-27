from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_GET
from .version import VERSION

@require_GET
def asset(request,name):
    types = {'app.js': 'text/javascript', 'react.js': 'text/javascript',
             'react-dom.js': 'text/javascript', 'marked.js': 'text/javascript',
             'purify.js': 'text/javascript', 'network-map.js': 'text/javascript',
             'bos3-fasteners-entry.png': 'image/png'}
    if name not in types: raise Http404
    p=Path(settings.BASE_DIR)/'assets'/name
    if not p.is_file():raise Http404
    return FileResponse(p.open('rb'),content_type=types[name])

@require_GET
def start_guide(request):
    if getattr(settings, 'BOS_DATA_MODE', '') != 'demo' or request.META.get('REMOTE_ADDR') not in ('127.0.0.1', '::1'):
        raise Http404
    path = Path(settings.BASE_DIR) / 'docs' / 'BoS_v18_Start_UA.pdf'
    if not path.is_file():
        raise Http404
    return FileResponse(path.open('rb'), content_type='application/pdf',
                        as_attachment=True, filename='BoS_v18_Start_UA.pdf')

@require_GET
def runtime_status(request):
    from training.access import enabled
    server = getattr(settings, 'WSGI_APPLICATION', '') == 'boss_project.server_wsgi.application'
    return JsonResponse({
        'version': VERSION, 'mode': 'server' if server else 'local',
        'data_mode': getattr(settings, 'BOS_DATA_MODE', 'demo'),
        'training_enabled': enabled(),
        'ai_configured': bool(getattr(settings, 'ANTHROPIC_API_KEY', '')),
        # CEO dashboard KPI and the browser organizer retain their actual scope.
        'dashboard': 'demo_generated', 'organizer': 'browser_local',
    })
