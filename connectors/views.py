from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from boss_project.policy import Policy
from operations.views import errors
from . import sources
from .models import Connector, ConnectorSnapshot

PREVIEW_ROWS = 20


def _writer(request):
    policy = Policy(request)
    if policy.role == 'observer':
        raise PermissionError('Спостерігач не може підключати сервіси.')
    return policy


def _read_source(request):
    """Return (kind, url, table) from an uploaded file or a Google Sheets link."""
    kind = request.POST.get('kind', '')
    if kind == 'csv':
        upload = request.FILES.get('file')
        if upload is None:
            raise ValueError('Додайте файл .xlsx або .csv.')
        if upload.size > sources.MAX_BYTES:
            raise sources.SourceError('Файл більший за 5 МБ.')
        return kind, '', sources.parse_upload(upload.name, upload.read())
    if kind == 'google_sheets':
        url = request.POST.get('url', '').strip()
        return kind, url, sources.fetch_sheet(url)
    raise ValueError('Цей сервіс ще не підключається автоматично.')


def _connector_dict(connector):
    snapshot = connector.snapshots.first()
    return {'id': connector.pk, 'kind': connector.kind, 'name': connector.name,
            'dataset': connector.dataset, 'dataset_label': connector.get_dataset_display(),
            'status': connector.status, 'status_label': connector.get_status_display(),
            'last_error': connector.last_error,
            'last_sync_at': connector.last_sync_at.isoformat() if connector.last_sync_at else None,
            'row_count': snapshot.row_count if snapshot else 0,
            'columns': snapshot.columns if snapshot else []}


def _source_error(fn):
    def wrapped(request, *args, **kwargs):
        try:
            return fn(request, *args, **kwargs)
        except sources.SourceError as exc:
            return JsonResponse({'error': str(exc), 'code': 'source'}, status=422)
    wrapped.__name__ = fn.__name__
    return wrapped


@require_GET
@errors
def index(request):
    Policy(request)
    connectors = Connector.objects.exclude(status='disabled').prefetch_related('snapshots')
    return JsonResponse({'catalog': list(sources.CATALOG),
                         'connectors': [_connector_dict(item) for item in connectors]})


@csrf_protect
@require_POST
@errors
@_source_error
def preview(request):
    _writer(request)
    kind, _url, table = _read_source(request)
    return JsonResponse({'kind': kind, 'columns': table['columns'], 'row_count': table['row_count'],
                         'rows': table['rows'][:PREVIEW_ROWS], 'sha256': table['sha256']})


@csrf_protect
@require_POST
@errors
@_source_error
def create(request):
    policy = _writer(request)
    name = request.POST.get('name', '').strip()[:120]
    dataset = request.POST.get('dataset', 'other')
    if not name:
        raise ValueError('Вкажіть назву підключення.')
    if dataset not in dict(Connector.DATASETS):
        raise ValueError('Невідомий тип даних.')
    kind, url, table = _read_source(request)
    if table['sha256'] != request.POST.get('expected_sha256'):
        return JsonResponse({'error': 'Дані змінилися після попереднього перегляду. Перегляньте ще раз.',
                             'code': 'stale_preview'}, status=409)
    with transaction.atomic():
        connector = Connector.objects.create(kind=kind, name=name, dataset=dataset, source_url=url,
                                             last_sync_at=timezone.now(), created_by=policy.user)
        ConnectorSnapshot.objects.create(connector=connector, columns=table['columns'],
                                         rows=table['rows'], row_count=table['row_count'],
                                         sha256=table['sha256'])
    return JsonResponse(_connector_dict(connector), status=201)


@csrf_protect
@require_POST
@errors
def sync(request, connector_id):
    _writer(request)
    connector = Connector.objects.get(pk=connector_id, kind='google_sheets')
    if connector.status == 'disabled':
        raise ValueError('Підключення вимкнено.')
    try:
        table = sources.fetch_sheet(connector.source_url)
    except sources.SourceError as exc:
        Connector.objects.filter(pk=connector.pk).update(status='error', last_error=str(exc)[:300])
        return JsonResponse({'error': str(exc), 'code': 'source'}, status=422)
    with transaction.atomic():
        latest = connector.snapshots.first()
        if latest is None or latest.sha256 != table['sha256']:
            ConnectorSnapshot.objects.create(connector=connector, columns=table['columns'],
                                             rows=table['rows'], row_count=table['row_count'],
                                             sha256=table['sha256'])
        Connector.objects.filter(pk=connector.pk).update(status='connected', last_error='',
                                                         last_sync_at=timezone.now())
    connector.refresh_from_db()
    return JsonResponse(_connector_dict(connector))


@require_GET
@errors
def rows(request, connector_id):
    Policy(request)
    connector = Connector.objects.exclude(status='disabled').get(pk=connector_id)
    snapshot = connector.snapshots.first()
    return JsonResponse({**_connector_dict(connector), 'rows': snapshot.rows if snapshot else []})


@csrf_protect
@require_POST
@errors
def disable(request, connector_id):
    _writer(request)
    updated = Connector.objects.filter(pk=connector_id).exclude(status='disabled').update(status='disabled')
    if not updated:
        raise Connector.DoesNotExist
    return JsonResponse({'id': connector_id, 'status': 'disabled'})
