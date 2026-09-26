"""Authenticated live network projection and exports from the same filtered rows."""
import csv
import hashlib
import io
import json
import re
from functools import wraps

from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from boss_project.identity import IdentityDenied
from boss_project.policy import Policy
from operations.views import errors
from . import network, service


def identity_errors(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except IdentityDenied as exc:
            return JsonResponse({'error': str(exc), 'code': 'identity_denied'}, status=exc.status)
    return call


def access_revision(policy):
    # Include visibility and metadata: document scopes can change independently
    # of the current actor's permissions and the ERP transaction fingerprint.
    docs = list(policy.documents().order_by('pk').values('id', 'code', 'revision',
        'title', 'status', 'access_level', 'contract_id', 'checksum'))
    return hashlib.sha256(json.dumps([policy.access_revision(), docs],
        sort_keys=True, default=str).encode()).hexdigest()


def read(request, export=False):
    policy = Policy(request)
    if export:
        policy.require_export()
    revision = access_revision(policy)
    before = service.fingerprint()
    data = network.build(policy, request.GET)
    fresh = Policy(request)
    if export:
        fresh.require_export()
    if revision != access_revision(fresh) or before != service.fingerprint():
        return None
    return data


def conflict():
    return JsonResponse({'error': 'Дані або права змінилися. Оновіть мережу.', 'code': 'read_state_changed'}, status=409)


@require_GET
@errors
@identity_errors
def snapshot(request):
    data = read(request)
    if data is None:
        return conflict()
    response = JsonResponse(data, json_dumps_params={'ensure_ascii': False})
    response['Cache-Control'] = 'private, no-store'
    return response


@require_GET
@errors
@identity_errors
def export(request):
    data = read(request, export=True)
    if data is None:
        return conflict()
    format_name = request.GET.get('format', 'csv')
    if format_name == 'json':
        response = JsonResponse(data, json_dumps_params={'ensure_ascii': False, 'indent': 2})
        filename = 'BoS-network-' + data['currency'] + '.json'
    elif format_name == 'csv':
        table = request.GET.get('table', 'lots')
        if table not in network.TABLES:
            raise ValueError('Невідома таблиця мережі.')
        rows = data['rows'][table]
        # Derived from server field projection; no client-selected private columns.
        headers = list(dict.fromkeys(key for row in rows for key in row))
        if not headers:
            headers = ['invoice_id' if table == 'invoices' else 'id']
        stream = io.StringIO(newline='')
        stream.write('\ufeff')
        writer = csv.writer(stream, delimiter=';', quoting=csv.QUOTE_ALL)

        def cell(value):
            if value is None:
                return ''
            text = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (list, dict)) else str(value)
            return "'" + text if re.match(r'^[\s]*[=+@-]', text) else text

        writer.writerow(headers)
        writer.writerows([cell(row.get(key)) for key in headers] for row in rows)
        response = HttpResponse(stream.getvalue(), content_type='text/csv; charset=utf-8')
        filename = 'BoS-network-' + table + '-' + data['currency'] + '.csv'
    else:
        raise ValueError('Доступні формати csv та json.')
    response['Content-Disposition'] = 'attachment; filename="' + filename + '"'
    response['Cache-Control'] = 'private, no-store'
    return response
