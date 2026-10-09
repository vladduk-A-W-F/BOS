from datetime import timedelta
import json

from django.db import transaction
from django.db.models import F, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from boss_project.policy import Policy
from operations.views import errors
from . import mapping, sources
from .models import Connector, ConnectorSnapshot

PREVIEW_ROWS = 20
STALE_AFTER = timedelta(minutes=15)
STALE_BATCH = 10
LINKED = ('google_sheets', 'url')   # sources read again by their link; uploaded files are not
MAX_MAPPING_CHARS = 20000


def _writer(request):
    policy = Policy(request)
    if policy.role == 'observer':
        raise PermissionError('Спостерігач не може підключати сервіси.')
    return policy


def _visible(policy):
    """Connector rows follow the existing money scope: payments only for the CEO."""
    rows = Connector.objects.exclude(status='disabled')
    return rows if policy.ceo else rows.exclude(dataset='payments')


def _read_source(request):
    """Return (kind, url, table) from an uploaded file, a Google Sheets link or a link to another server."""
    kind = request.POST.get('kind', '')
    if kind == 'csv':
        upload = request.FILES.get('file')
        if upload is None:
            raise ValueError('Додайте файл .xlsx або .csv.')
        if upload.size > sources.MAX_BYTES:
            raise sources.SourceError('Файл більший за 5 МБ.')
        return kind, '', sources.parse_upload(upload.name, upload.read())
    if kind in LINKED:
        url = request.POST.get('url', '').strip()
        if len(url) > 500:
            raise sources.SourceError('Посилання задовге: максимум 500 символів.')
        return kind, url, sources.fetch(kind, url)
    raise ValueError('Цей сервіс ще не підключається автоматично.')


def read_mapped(connector, snapshot):
    """The latest snapshot read with the stored mapping, or None when the source has no mapping.

    A mapping that no longer fits the table (a column was renamed in the sheet) is reported as an
    error, never silently replaced by a new guess.
    """
    if connector.dataset not in mapping.FIELDS or not connector.mapping or snapshot is None:
        return None
    try:
        used = mapping.validate(connector.dataset, snapshot.columns, connector.mapping)
    except mapping.MappingError as exc:
        return {'error': str(exc)}
    return mapping.normalize(connector.dataset, snapshot.columns, snapshot.rows, used)


def _connector_dict(connector):
    snapshot = connector.snapshots.first()
    read = read_mapped(connector, snapshot)
    summary = read if read is None or 'error' in read else {
        'accepted': read['accepted'], 'total': read['total'], 'rejected': read['total'] - read['accepted']}
    return {'id': connector.pk, 'kind': connector.kind, 'name': connector.name,
            'dataset': connector.dataset, 'dataset_label': connector.get_dataset_display(),
            'status': connector.status, 'status_label': connector.get_status_display(),
            'last_error': connector.last_error,
            'last_sync_at': connector.last_sync_at.isoformat() if connector.last_sync_at else None,
            'row_count': snapshot.row_count if snapshot else 0,
            'columns': snapshot.columns if snapshot else [],
            'mapping': connector.mapping, 'fields': mapping.fields(connector.dataset), 'mapped_summary': summary}


def _chosen_mapping(raw, guess):
    """The `mapping` form field: a JSON object {field: column}; absent means the suggested one."""
    if raw is None or raw == '':
        return guess
    if len(raw) > MAX_MAPPING_CHARS:
        raise mapping.MappingError('Відповідність колонок передано в неправильному форматі.')
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError):
        # Deeply nested JSON exhausts the parser's recursion; it is a malformed mapping, not a server error.
        raise mapping.MappingError('Відповідність колонок передано в неправильному форматі.')
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise mapping.MappingError('Відповідність колонок передано в неправильному форматі.')
    return value


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
    policy = Policy(request)
    connectors = _visible(policy).prefetch_related('snapshots')
    out = {'catalog': list(sources.CATALOG), 'connectors': [_connector_dict(item) for item in connectors]}
    if policy.ceo:
        # Read access for AI clients (MCP): state and key labels only; keys are issued on the server.
        from . import mcp
        out['mcp'] = mcp.summary()
    return JsonResponse(out)


@csrf_protect
@require_POST
@errors
@_source_error
def preview(request):
    _writer(request)
    kind, _url, table = _read_source(request)
    body = {'kind': kind, 'columns': table['columns'], 'row_count': table['row_count'],
            'rows': table['rows'][:PREVIEW_ROWS], 'sha256': table['sha256']}
    dataset = request.POST.get('dataset', '')
    if dataset in mapping.FIELDS:
        # What the mapping step offers: the fields of this dataset, a guess from the headers, and how
        # the whole table reads with that guess or with the person's own choice (nothing is stored by a preview).
        guess = mapping.suggest(dataset, table['columns'])
        body.update(fields=mapping.fields(dataset), suggested_mapping=guess)
        try:
            chosen = _chosen_mapping(request.POST.get('mapping'), guess)
            used = mapping.validate(dataset, table['columns'], chosen)
            read = mapping.normalize(dataset, table['columns'], table['rows'], used)
            body['mapped'] = {**read, 'rows': read['rows'][:PREVIEW_ROWS], 'mapping': used}
        except mapping.MappingError as exc:
            body['mapped'] = {'error': str(exc)}
    return JsonResponse(body)


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
    # The mapping the person confirmed in the preview. Without one the source is stored unmapped,
    # exactly as before; a guess is never stored on the person's behalf.
    raw = request.POST.get('mapping')
    chosen = mapping.validate(dataset, table['columns'], _chosen_mapping(raw, {})) if raw else {}
    with transaction.atomic():
        connector = Connector.objects.create(kind=kind, name=name, dataset=dataset, source_url=url, mapping=chosen,
                                             last_sync_at=timezone.now(), created_by=policy.user)
        ConnectorSnapshot.objects.create(connector=connector, columns=table['columns'],
                                         rows=table['rows'], row_count=table['row_count'],
                                         sha256=table['sha256'])
    return JsonResponse(_connector_dict(connector), status=201)


def _locked(connector_id):
    """Serialize with other connector writes (the existing ERP mutex), then re-read the row."""
    from erp.service import write_lock
    write_lock()
    return Connector.objects.select_for_update().get(pk=connector_id)


def sync_connector(connector):
    """Read a linked source (published Google Sheet or a link to another server) again; store a new snapshot
    only when its content changed.

    The fetch runs outside the transaction and the lock. last_sync_at is the moment the data
    was read, so a slower fetch that started earlier cannot overwrite a newer applied result
    or mark the source as failed after it; a disable during the fetch always wins.
    """
    started = timezone.now()
    try:
        table = sources.fetch(connector.kind, connector.source_url)
    except sources.SourceError as exc:
        with transaction.atomic():
            current = _locked(connector.pk)
            if current.status != 'disabled' and not _newer(current, started):
                Connector.objects.filter(pk=current.pk).update(status='error', last_error=str(exc)[:300])
        raise
    with transaction.atomic():
        current = _locked(connector.pk)
        if current.status == 'disabled' or _newer(current, started):
            return current
        latest = current.snapshots.first()
        if latest is None or latest.sha256 != table['sha256']:
            ConnectorSnapshot.objects.create(connector=current, columns=table['columns'],
                                             rows=table['rows'], row_count=table['row_count'],
                                             sha256=table['sha256'])
        Connector.objects.filter(pk=current.pk).update(status='connected', last_error='', last_sync_at=started)
    connector.refresh_from_db()
    return connector


def _newer(current, started):
    """A read that started at or after ours has already been applied."""
    return current.last_sync_at is not None and current.last_sync_at >= started


def stale_sheets(rows, now=None):
    """Healthy linked sources (Google Sheets and links to other servers) read more than STALE_AFTER ago,
    oldest first.

    A source in error is not retried automatically: it keeps its last successful time, and
    retrying it would let broken sources hold the batch. It recovers through the manual
    «Оновити» (sync), after which it is healthy and joins the automatic reading again.
    """
    cutoff = (now or timezone.now()) - STALE_AFTER
    return (rows.filter(kind__in=LINKED, status='connected')
            .filter(Q(last_sync_at__isnull=True) | Q(last_sync_at__lt=cutoff))
            .order_by(F('last_sync_at').asc(nulls_first=True), 'pk')[:STALE_BATCH])


@csrf_protect
@require_POST
@errors
def sync(request, connector_id):
    connector = _visible(_writer(request)).get(pk=connector_id, kind__in=LINKED)
    if connector.status == 'disabled':
        raise ValueError('Підключення вимкнено.')
    try:
        connector = sync_connector(connector)
    except sources.SourceError as exc:
        return JsonResponse({'error': str(exc), 'code': 'source'}, status=422)
    return JsonResponse(_connector_dict(connector))


@csrf_protect
@require_POST
@errors
def sync_stale(request):
    """Periodic reading on use: refresh healthy Google Sheets older than 15 minutes, no scheduler."""
    synced, failed = [], []
    for connector in stale_sheets(_visible(_writer(request))):
        try:
            synced.append(_connector_dict(sync_connector(connector)))
        except sources.SourceError as exc:
            failed.append({'id': connector.pk, 'name': connector.name, 'error': str(exc)})
    return JsonResponse({'synced': synced, 'failed': failed})


@require_GET
@errors
def rows(request, connector_id):
    policy = Policy(request)
    if policy.role == 'observer':
        raise PermissionError('Рядки підключених джерел недоступні спостерігачу.')
    connector = _visible(policy).get(pk=connector_id)
    snapshot = connector.snapshots.first()
    return JsonResponse({**_connector_dict(connector), 'rows': snapshot.rows if snapshot else []})


@csrf_protect
@require_POST
@errors
def disable(request, connector_id):
    rows = _visible(_writer(request))
    with transaction.atomic():
        if rows.filter(pk=connector_id).exclude(status='disabled').exists():
            _locked(connector_id)
        updated = rows.filter(pk=connector_id).exclude(status='disabled').update(status='disabled')
    if not updated:
        raise Connector.DoesNotExist
    return JsonResponse({'id': connector_id, 'status': 'disabled'})


@csrf_protect
@require_POST
@errors
def set_mapping(request, connector_id):
    """Store which columns of this source mean which BoS fields; checked against its latest table."""
    rows = _visible(_writer(request))
    with transaction.atomic():
        if not rows.filter(pk=connector_id).exclude(status='disabled').exists():
            raise Connector.DoesNotExist
        connector = _locked(connector_id)
        if connector.status == 'disabled':
            raise Connector.DoesNotExist
        snapshot = connector.snapshots.first()
        if connector.dataset not in mapping.FIELDS or snapshot is None:
            raise ValueError('Для цього джерела відповідність колонок не задається.')
        chosen = mapping.validate(connector.dataset, snapshot.columns,
                                  _chosen_mapping(request.POST.get('mapping', ''), None))
        Connector.objects.filter(pk=connector.pk).update(mapping=chosen)
    connector.refresh_from_db()
    return JsonResponse(_connector_dict(connector))
