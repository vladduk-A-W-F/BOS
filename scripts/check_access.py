"""Gate 4: closed-world resolver catalogue and real role/HTTP access sweep.

No working DB is accepted. Integrate beside access_fixtures.py/access_routes.json.
Every incomplete catalogue, fixture, HTTP case or required field test is red.
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import traceback
from urllib.parse import urlsplit

METHODS = ('GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE', 'TRACE', 'CONNECT')
ROLES = ('anonymous', 'ceo', 'manager', 'observer', 'technical_admin')
DRF = {'tasks', 'employees', 'counterparties', 'contracts', 'transactions', 'salaries'}
LOG_MODELS = {'ai_assistant.chatmessage', 'ai_assistant.chatfile',
              'ai_assistant.taskchangelog', 'ai_assistant.employeechangelog',
              'ai_assistant.claudeusagelog'}
EXTERNAL = {'/api/chat/', '/api/chat/file/', '/api/meeting/protocol/', '/api/dictate/process/'}
EXPORTS = {'/api/erp/network/export/', '/api/erp/export/', '/api/operations/export/'}
DISABLED = {'/api/auth/demo/', '/api/operations/role/'}
PUBLIC_AUTH = {'/api/auth/csrf/', '/api/auth/login/', '/api/auth/logout/', '/api/auth/me/'}
DRF_METADATA = {'/api/branches/', '/api/dashboard/summary/', '/api/dashboard/helicopter/',
                '/api/dashboard/activity/', '/api/chat/', '/api/meeting/protocol/', '/api/dictate/process/'}
IMPORT_ROUTES={'/api/erp/import/preview/','/api/erp/import/template/','/api/erp/import/batches/{batch_id}/','/api/erp/import/batches/{batch_id}/export/'}
C01_HISTORY='/api/tasks/{pk}/history/'
C01_OUTCOME='/api/operations/task-proposals/{proposal_id}/'
C03_SOURCE='/api/statements/sources/'
C03_JOURNAL='/api/transactions/summary/'
C03_READS={'/api/statements/imports/','/api/statements/imports/{pk}/',
    '/api/statements/imports/{pk}/export/','/api/statements/lines/',
    '/api/statements/lines/{pk}/','/api/statements/lines/{pk}/candidates/','/api/statements/summary/'}
RAW_GET = {
    '/api/erp/network/', '/api/erp/network/export/', '/api/erp/modules/',
    '/api/erp/purchases/{pk}/document-match/',
    '/api/erp/orders/{pk}/settlement/', '/api/erp/lines/{pk}/supply-options/',
    '/api/erp/workpoints/',
    '/api/erp/orders/{pk}/trace/',
    '/api/erp/corrections/outcome/',
    '/api/erp/import/template/', '/api/erp/import/batches/{batch_id}/', '/api/erp/import/batches/{batch_id}/export/',
    '/api/erp/orders/{pk}/next/', '/api/erp/snapshot/', '/api/erp/export/',
    '/api/erp/changes/{pk}/impact/', '/api/erp/orders/{pk}/draft/',
    '/api/operations/portfolio/', '/api/operations/status/', '/api/operations/requests/',
    '/api/operations/compare/', '/api/operations/summary/', '/api/operations/documents/',
    '/api/operations/documents/{pk}/', '/api/operations/documents/{pk}/download/',
    '/api/operations/audit/', '/api/operations/export/', '/api/operations/rfq/{code}/',
    '/api/runtime/status/', '/api/branches/', '/api/dashboard/summary/',
    '/api/dashboard/helicopter/', '/api/dashboard/activity/',
}
RAW_POST = {
    '/api/erp/import/preview/',
    '/api/erp/preview/', '/api/operations/requests/create/',
    '/api/operations/quotes/create/', '/api/operations/documents/{pk}/review/',
    '/api/operations/documents/upload/', '/api/operations/preview/',
    '/api/operations/confirm/', '/api/operations/settings/', '/api/operations/chat/',
}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--manifest', type=Path, default=Path(__file__).with_name('access_routes.json'))
    p.add_argument('--fixture-module', default='operations.test_access')
    p.add_argument('--field-tests', nargs='+', default=['operations.test_access', 'operations.test_blind_paths', 'operations.test_remaining_context', 'operations.test_document_contract_visibility', 'operations.test_access_boundaries', 'operations.test_review_response_projection', 'erp.test_order_trace', 'erp.test_workpoints.WorkpointTests', 'erp.test_flow_projection_routes.FlowProjectionRouteTests', 'erp.test_document_match_route.DocumentMatchRouteTests'])
    p.add_argument('--output', type=Path)
    p.add_argument('--catalogue-only', action='store_true', help='Diagnostic only; always incomplete/exit 1.')
    return p.parse_args()


def catalogue():
    from django.urls import URLResolver, get_resolver
    result = []
    def walk(nodes, prefix='', namespace=''):
        for node in nodes:
            full = prefix + str(node.pattern)
            if isinstance(node, URLResolver):
                walk(node.url_patterns, full, namespace + ((node.namespace + ':') if node.namespace else ''))
            else:
                cb = node.callback
                ma = getattr(cb, 'model_admin', None)
                result.append({'pattern': full, 'name': namespace + str(node.name),
                    'callback': getattr(cb, '__module__', '') + '.' + getattr(cb, '__qualname__', str(cb)),
                    'actions': {k: v for k, v in getattr(cb, 'actions', {}).items() if k != 'head'} or None,
                    'model': ma.model._meta.label_lower if ma else None,
                    'converters': {k: type(v).__name__ for k, v in node.pattern.converters.items()},
                    '_node': node})
    walk(get_resolver().url_patterns)
    return result


def public_row(row):
    return {k: v for k, v in row.items() if not k.startswith('_')}


def signature(row):
    return json.dumps(public_row(row), sort_keys=True)


def canonical(path):
    if path == '/api/.json/' or path == '/api/.json':
        return '/api/'
    path = re.sub(r'\.json/?$', '/', path)
    path = re.sub(r'/\d+/', '/{pk}/', path)
    path = re.sub(r'^/api/erp/import/batches/[0-9a-f-]{36}/', '/api/erp/import/batches/{batch_id}/', path)
    path = re.sub(r'^/api/operations/task-proposals/[0-9a-f-]{36}/', C01_OUTCOME, path)
    path = re.sub(r'^(/api/statements/(?:imports|lines)/)[0-9a-f-]{36}/', r'\1{pk}/', path)
    if path.startswith('/api/operations/rfq/'):
        path = '/api/operations/rfq/{code}/'
    return path


def materialize(row, fixtures):
    """Only explicitly known converters/regex are concretized; never use pk=1."""
    pattern = row['pattern']
    values = fixtures.route_values(row)
    known_converters = {'IntConverter', 'StringConverter', 'PathConverter', 'FormatSuffixConverter', 'UUIDConverter'}
    if set(row['converters'].values()) - known_converters:
        raise ValueError('unknown_converter:' + repr(row['converters']))
    choices = [pattern]
    app = re.search(r'\(\?P<app_label>([^)]+)\)', pattern)
    if app:
        labels = app.group(1).split('|')
        if set(labels) != {'auth', 'tasks', 'finance', 'employees', 'ai_assistant', 'branches'}:
            raise ValueError('unknown_admin_app_converter:' + repr(labels))
        choices = [pattern.replace(app.group(0), label) for label in labels]
    paths = []
    for value in choices:
        def convert(match):
            name = match.group(1)
            if name not in values:
                raise ValueError('missing_converter_fixture:' + name)
            return str(values[name])
        for regex, name in ((r'(?P<pk>[^/.]+)', 'pk'), (r'(?P<format>[a-z0-9]+)', 'format'),
                            (r'(?P<url>.*)', 'url')):
            if regex in value:
                if name not in values:
                    raise ValueError('missing_regex_fixture:' + name)
                value = value.replace(regex, str(values[name]))
        value = value.replace('<drf_format_suffix:format>', '.json/')
        value = re.sub(r'<(?:[a-z_]+:)?([a-z_]+)>', convert, value)
        value = value.replace('\\.', '.').replace('^', '').replace('$', '').replace('/?', '/')
        if re.search(r'[<>{}()\[\]?*+\\]', value):
            raise ValueError('unresolved_route_regex:' + value)
        value = '/' + value
        paths.append(value)
        if value.endswith('.json/'):
            paths.append(value[:-1])
    return paths


def contract(row, path, method, role, variant='full'):
    """Accepted policy oracle. It does not import production permissions."""
    route = canonical(path)
    if route in ('/health/live/', '/health/ready/'):
        # This sweep uses the verification DB profile. Real server readiness=200
        # is separately required by gate 8; absent server configuration is 503.
        status = (200 if route == '/health/live/' else 503) if method == 'GET' else 405
        return {status}, 'public_technical_health_read_only'
    if route.startswith('/admin/'):
        return admin_contract(row, path, method, role)
    if route in DISABLED:
        return {404}, 'disabled_in_working'
    if route in PUBLIC_AUTH:
        if route.endswith('/csrf/'):
            return ({200} if method == 'GET' else {405}), 'csrf_bootstrap'
        if route.endswith('/me/'):
            result = 401 if role == 'anonymous' else 403 if role == 'technical_admin' else 200
            return ({result} if method == 'GET' else {405}), 'real_identity'
        if method != 'POST':
            return {405}, 'unsupported_auth_method'
        if route.endswith('/logout/'):
            return {200}, 'logout_own_session'
        # Anonymous login probe supplies the known CEO's valid credentials.
        return ({403} if role == 'technical_admin' else {200}), 'real_login'
    if role == 'anonymous':
        return {401}, 'anonymous_business_denied'
    if role == 'technical_admin':
        return {403}, 'staff_is_not_business_role'
    if route == '/api/erp/purchases/{pk}/document-match/':
        if method != 'GET':
            denied = role == 'observer' and method not in ('HEAD', 'OPTIONS')
            return ({403} if denied else {405}), 'document_match_get_only'
        return ({200} if role == 'ceo' else {403}), 'document_match_ceo_synthetic_read_only'
    if route in ('/api/erp/orders/{pk}/settlement/', '/api/erp/lines/{pk}/supply-options/'):
        if method != 'GET':
            denied = role == 'observer' and method not in ('HEAD', 'OPTIONS')
            return ({403} if denied else {405}), 'flow_projection_get_only'
        if route.endswith('/settlement/'):
            return ({200} if role == 'ceo' else {403}), 'order_settlement_ceo_only'
        if role != 'ceo' and variant == 'no_documents':
            return {404}, 'supply_line_not_admitted'
        return {200}, 'supply_visible_sources_only'
    if route == '/api/erp/workpoints/':
        if method != 'GET':
            denied = role == 'observer' and method not in ('HEAD', 'OPTIONS')
            return ({403} if denied else {405}), 'workpoints_unsupported_read_only'
        return {200}, 'workpoints_visible_sources_read_only'
    if route == '/api/erp/orders/{pk}/trace/':
        if method != 'GET':
            denied = role == 'observer' and method not in ('HEAD', 'OPTIONS')
            return ({403} if denied else {405}), 'order_trace_unsupported_read_only'
        if role != 'ceo' and variant == 'no_documents':
            return {404}, 'order_trace_source_unavailable'
        return {200}, 'order_trace_scoped_read_only'
    if route in C03_READS|{C03_SOURCE,C03_JOURNAL}:
        if role!='ceo':return {403}, 'statement_ceo_only_read_only'
        if route.endswith('/export/') and variant=='no_export' and method=='GET':return {403}, 'statement_export_capability_read_only'
        if route==C03_SOURCE:
            return ({201} if method=='POST' else {405}), ('allowed_raw_create' if method=='POST' else 'statement_source_unsupported_read_only')
        if route==C03_JOURNAL:
            return ({200} if method in ('GET','HEAD','OPTIONS') else {405}), 'journal_summary_read_only'
        return ({200} if method=='GET' else {405}), 'statement_source_scoped_read_only'
    if route == C01_HISTORY:
        if method not in ('GET', 'HEAD', 'OPTIONS'):
            return ({403} if role == 'observer' else {405}), 'task_history_unsupported_read_only'
        if variant == 'no_documents' and method != 'OPTIONS':
            return {404}, 'task_history_source_unavailable'
        return {200}, 'task_history_scoped_read_only'
    if route == C01_OUTCOME:
        if method != 'GET':
            return ({403} if role == 'observer' and method not in ('HEAD','OPTIONS') else {405}), 'task_outcome_unsupported_read_only'
        return ({200} if role == 'ceo' else {404}), 'task_outcome_owner_read_only'
    if route == '/api/erp/corrections/outcome/':
        # Read-only B03 lookup. Explicit method/role oracle, not handler discovery.
        if method != 'GET':
            denied = role == 'observer' and method not in ('HEAD', 'OPTIONS')
            return ({403} if denied else {405}), 'correction_outcome_unsupported_read_only'
        if role == 'observer':
            return {403}, 'correction_outcome_observer_denied'
        if variant == 'no_documents' and role == 'manager':
            return {404}, 'correction_outcome_source_unavailable'
        return {200}, 'correction_outcome_committed_read_only'
    if method == 'OPTIONS' and route in DRF_METADATA:
        return {200}, 'declared_drf_metadata'
    if route in EXTERNAL:
        if method == 'POST':
            return ({403} if role == 'observer' else {503}), 'external_adapter_not_executed'
        return {403, 405}, 'unsupported_external_method'
    if route == '/api/chat/history/':
        if method in ('GET', 'HEAD', 'OPTIONS'):
            return {200}, 'own_history_current_role'
        if method == 'DELETE':
            return ({403} if role == 'observer' else {200, 204}), 'archive_own_history'
        return {403, 405}, 'unsupported_history_method'
    if route == '/api/':
        return ({200} if method in ('GET', 'HEAD', 'OPTIONS') else {403, 405}), 'drf_root'
    parts = route.split('/')
    if len(parts) > 2 and parts[2] in DRF:
        family = parts[2]
        detail = '{pk}' in parts
        pay = 'pay' in parts
        declared = {'POST', 'OPTIONS'} if pay else (
            {'GET', 'HEAD', 'OPTIONS', 'PUT', 'PATCH', 'DELETE'} if detail else
            {'GET', 'HEAD', 'OPTIONS', 'POST'})
        if family == 'salaries' and role != 'ceo':
            return {403}, 'payroll_ceo_only'
        if family == 'transactions' and role == 'observer':
            return {403}, 'observer_finance_denied'
        if method not in declared:
            return {403, 405}, 'unsupported_drf_method'
        writes = method in ('POST', 'PUT', 'PATCH', 'DELETE')
        if family == 'tasks' and writes:
            return {403}, 'task_approval_required_read_only'
        if writes and (role == 'observer' or (role == 'manager' and family in {'employees', 'transactions', 'salaries'})):
            return {403}, 'business_write_denied'
        if method == 'POST':
            return ({200} if pay else {201}), 'allowed_drf_write'
        return ({204} if method == 'DELETE' else {200}), ('allowed_drf_write' if writes else 'allowed_drf_method')
    if route not in RAW_GET | RAW_POST:
        raise ValueError('missing_route_policy:' + route)
    expected_method = 'GET' if route in RAW_GET else 'POST'
    if method != expected_method:
        return {403, 405}, 'unsupported_django_method'
    if route in IMPORT_ROUTES and role != 'ceo':
        return {403}, 'initial_import_ceo_only'
    if route in EXPORTS and (role == 'observer' or variant == 'no_export'):
        return {403}, 'separate_export_capability'
    if route == '/api/operations/settings/' and role != 'ceo':
        return {403}, 'organization_settings_ceo_only'
    if expected_method == 'POST' and role == 'observer' and route != '/api/operations/chat/':
        return {403}, 'observer_business_write_denied'
    if variant == 'no_documents' and role != 'ceo' and 'documents' in route:
        return ({404} if '{pk}' in route else {200, 403}), 'document_capability_missing'
    if route.endswith('/download/') and variant == 'no_download':
        return {403}, 'separate_download_capability'
    if route.endswith(('/requests/create/', '/quotes/create/', '/documents/upload/')):
        return {201}, 'allowed_raw_create'
    return {200}, 'allowed_raw_method'


def admin_contract(row, path, method, role):
    name = row['name'].removeprefix('admin:')
    # An authenticated business identity cannot enter even the admin login form.
    # The technical account has no BoS Group; Django model permissions apply.
    if role in ('ceo', 'manager', 'observer'):
        return {403}, 'business_identity_has_no_admin'
    if role not in ('anonymous', 'technical_admin'):
        raise ValueError('unknown_admin_role:' + str(role))
    if name == 'login':
        if method == 'GET':
            return ({302} if role == 'technical_admin' else {200}), 'staff_login_form'
        if method == 'HEAD':
            # AdminSite's authenticated redirect is explicitly GET-only.
            return {200}, 'staff_login_form'
        if method == 'POST':
            return ({302} if role == 'technical_admin' else {200}), 'staff_login_control'
        if method in ('OPTIONS', 'PUT'):
            # Native FormView: OPTIONS metadata / unbound PUT form. Neither may
            # authenticate, mutate a business record, or expose private data.
            return {200}, 'native_staff_login_read_only'
        return {405}, 'unsupported_staff_login_method'
    if role == 'anonymous':
        return {302, 403}, 'anonymous_admin_denied_read_only'
    if name == 'view_on_site':
        # Explicitly accepted unavailable redirect feature, with existing rows.
        return ({404} if method in ('GET', 'HEAD') else {404, 405}), 'existing_object_has_no_public_url'
    if row['pattern'] == 'admin/(?P<url>.*)$':
        return {404}, 'known_admin_catch_all'
    if row['model'] == 'tasks.task':
        if name.endswith(('_add','_delete')):
            return {403}, 'task_admin_command_required_read_only'
        if method == 'POST':
            return {200,302,403,405}, 'task_admin_command_required_read_only'
    if method in ('TRACE', 'CONNECT', 'PUT', 'PATCH', 'DELETE'):
        return {200, 302, 403, 405}, 'unsupported_admin_method_read_only'
    if row['model'] in LOG_MODELS:
        if name.endswith(('_add', '_delete')) or method == 'POST':
            return {200, 302, 403, 405}, 'admin_logs_read_only'
    if name == 'logout':
        if method == 'OPTIONS':
            return {200}, 'native_staff_logout_read_only'
        return ({200, 302} if method == 'POST' else {405}), 'staff_logout'
    if name == 'autocomplete':
        return ({200} if method in ('GET', 'HEAD', 'OPTIONS') else {405}), 'staff_autocomplete_positive_required'
    if name == 'None':
        return ({302} if method in ('GET', 'HEAD', 'OPTIONS') else {302, 403, 405}), 'staff_object_alias_read_only'
    if method == 'OPTIONS':
        return {200, 405}, 'admin_metadata_no_private_business_role'
    if method == 'POST':
        if name in ('password_change', 'auth_user_password_change') or name.endswith(('_add', '_change', '_delete', '_changelist')):
            return {302}, 'allowed_admin_form'
        return {200, 302, 403, 405}, 'unsupported_admin_post_read_only'
    return {200}, 'staff_read_positive'


def local_redirect_path(location):
    """A denial redirect must stay on an exact local admin path."""
    target = urlsplit(location)
    if target.scheme or target.netloc or target.fragment or '\\' in location:
        return None
    return target.path


def admin_redirect_oracle(response, row, path, role, client, fixtures, variant):
    if not path.startswith('/admin/') or response.status_code != 302 or role == 'technical_admin':
        return True, []
    if role != 'anonymous':
        return False, []
    location = response.get('Location', '')
    target = local_redirect_path(location)
    if target == '/admin/login/':
        return True, []
    # Django AdminSite.admin_view has one explicit unauthenticated-logout
    # redirect through its index. Prove that the second response denies access;
    # never accept an arbitrary 302, external target, or a readable admin index.
    if row['name'] != 'admin:logout' or target != '/admin/' or urlsplit(location).query:
        return False, []
    followup = client.get('/admin/')
    leaks, size = response_oracle(followup, row, '/admin/', 'GET', role, fixtures, variant)
    passed = (followup.status_code == 302 and
              local_redirect_path(followup.get('Location', '')) == '/admin/login/' and not leaks)
    check = {'route': '/admin/', 'method': 'GET', 'role': role,
             'expectation': [302], 'status': followup.status_code,
             'redirect_location': followup.get('Location', ''),
             'leaks': leaks, 'response_bytes': size, 'passed': passed}
    return passed, [check]


def nested_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from nested_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_keys(child)


def response_oracle(response, row, path, method, role, fixtures, variant):
    raw = b''.join(response.streaming_content) if getattr(response, 'streaming', False) else response.content
    headers = json.dumps(dict(response.headers), ensure_ascii=False).encode()
    text = (raw + b'\n' + headers).decode('utf-8', errors='replace')
    # Decode JSON escapes too. A 401/403/404 never exempts its body from checks.
    data = None
    if 'json' in response.get('Content-Type', ''):
        try:
            data = json.loads(raw or b'null')
            text += '\n' + json.dumps(data, ensure_ascii=False, default=str)
        except (ValueError, UnicodeDecodeError):
            return ['invalid_json_body'], len(raw)
    leaks = ['marker:' + marker for marker in fixtures.forbidden_markers(role, path, variant) if marker in text]
    forbidden = {'api_key', 'secret_key', 'password_hash'}
    route = canonical(path)
    if role in ('manager', 'observer') and route.startswith('/api/employees/'):
        forbidden |= {'phone', 'email', 'birthday'}
    if role == 'manager' and route.startswith('/api/transactions/'):
        forbidden |= {'amount', 'description', 'employee_name', 'salary', 'salary_record',
                      'payment_date', 'period_year', 'period_month'}
    scan_data = data
    if method == 'OPTIONS' and isinstance(data, dict) and {'name', 'description', 'renders', 'parses'} <= set(data):
        # DRF's envelope description is view help text, not the financial field.
        # Keep the complete body in the byte/canary oracle and all nested actions.
        scan_data = {key: value for key, value in data.items() if key != 'description'}
    leaks += ['field:' + key for key in sorted(set(nested_keys(scan_data)) & forbidden)]
    if route == '/api/erp/orders/{pk}/trace/' and response.status_code == 200 and method == 'GET':
        leaks += order_trace_oracle(data, role, fixtures)
    if route == '/api/erp/workpoints/' and response.status_code == 200 and method == 'GET':
        leaks += workpoints_oracle(data, role, fixtures, variant)
    if route == '/api/erp/lines/{pk}/supply-options/' and response.status_code == 200 and method == 'GET':
        if data.get('schema') != 'bos.supply-options.v1' or data.get('line', {}).get('id') != fixtures.seed.line.pk:
            leaks.append('supply_positive_line_missing')
        if role != 'ceo':
            restricted = ('reserved_usable', 'quantity_to_cover', 'available_all_locations',
                          'available_target', 'target_gap', 'uncovered_after_stock',
                          'unallocated_expected', 'indicative_after_expected')
            if any(data.get('quantities', {}).get(key) is not None for key in restricted):
                leaks.append('supply_hidden_availability_inference')
            if any(row.get('available') is not None or row.get('eligible') is not None
                   for row in data.get('stock', []) + data.get('waiting', [])):
                leaks.append('supply_hidden_lot_inference')
    if route == '/api/erp/orders/{pk}/settlement/' and response.status_code == 200 and method == 'GET':
        if role != 'ceo' or data.get('schema') != 'bos.order-settlement.v1' or data.get('order', {}).get('id') != fixtures.seed.order.pk:
            leaks.append('settlement_identity_or_scope')
    if route == '/api/erp/purchases/{pk}/document-match/' and response.status_code == 200 and method == 'GET':
        if (role != 'ceo' or data.get('schema') != 'bos.document-match-read.v1'
                or data.get('document_id') != fixtures.seed.public_doc.pk
                or data.get('purchase_id') != fixtures.seed.purchase.pk
                or data.get('draft', {}).get('provider') != 'mock.synthetic-invoice.v1'
                or data.get('draft', {}).get('operation_proposal', 'missing') is not None):
            leaks.append('document_match_identity_or_scope')
    if route == '/api/erp/corrections/outcome/':
        leaks += correction_outcome_oracle(data, response.status_code, method, role, fixtures, variant)
    if route in (C01_HISTORY,C01_OUTCOME) or route.startswith('/api/tasks/'):
        leaks += task_response_oracle(data,response.status_code,method,role,fixtures,variant,route)
    if route in C03_READS|{C03_SOURCE,C03_JOURNAL}:
        leaks += statement_response_oracle(data,response.status_code,method,fixtures,route)
        if route=='/api/statements/imports/{pk}/export/' and method=='GET' and response.status_code==200:
            leaks += statement_export_oracle(raw,fixtures)
    allow = {v.strip().upper() for v in response.get('Allow', '').split(',') if v.strip()}
    leaks += ['unknown_allow_method:' + v for v in sorted(allow - set(METHODS))]
    if response.status_code == 200 and method == 'GET':
        import html
        decoded_text = html.unescape(text)
        for anchor in fixtures.positive_anchors(row, path, role, variant):
            if anchor not in decoded_text:
                leaks.append('missing_positive_anchor:' + anchor)
    return leaks, len(raw)


def workpoints_oracle(data, role, fixtures, variant):
    if not isinstance(data, dict) or data.get('schema') != 'bos.workpoints.v1' or data.get('scope') != 'visible_records':
        return ['workpoints_schema_missing']
    errors = []
    order_ids = set()
    for point in data.get('points', []):
        order_ids.update(point.get('order_ids', []))
        if point.get('movement_scope') != 'latest_300_visible_global':
            errors.append('workpoints_movement_scope_missing')
        if role != 'ceo':
            if point.get('money') is not None or point.get('completeness') != 'restricted':
                errors.append('workpoints_finance_not_restricted')
            if any(row.get('available') is not None for row in point.get('stock', [])):
                errors.append('workpoints_hidden_reservation_inference')
            for key, value in [('order_ids', fixtures.seed.hidden_order.pk),
                    ('lot_ids', fixtures.seed.hidden_lot.pk), ('document_ids', fixtures.seed.hidden_doc.pk)]:
                if value in point.get(key, []):
                    errors.append('workpoints_hidden_' + key)
            if variant == 'no_documents' and point.get('document_ids'):
                errors.append('workpoints_document_capability_leak')
    if (role == 'ceo' or variant != 'no_documents') and fixtures.seed.order.pk not in order_ids:
        errors.append('workpoints_positive_order_missing')
    forbidden = {'phone', 'email', 'birthday', 'payload', 'approval_snapshot', 'hidden_count', 'read_revision'}
    errors += ['workpoints_forbidden_field:' + key for key in sorted(set(nested_keys(data)) & forbidden)]
    return errors


def order_trace_oracle(data, role, fixtures):
    """New route only: exact positive order and nested field/privacy boundaries."""
    if not isinstance(data, dict) or data.get('schema') != 'bos.order-trace.v1':
        return ['trace_schema_missing']
    if data.get('order', {}).get('id') != fixtures.seed.order.pk or not data.get('lines'):
        return ['trace_positive_order_missing']
    errors = []
    forbidden = {'price', 'cost', 'unit_cost', 'amount', 'paid', 'payload', 'result',
                 'approval_snapshot', 'phone', 'email', 'birthday', 'read_revision', 'hidden_count'}
    errors += ['trace_forbidden_field:' + key for key in sorted(set(nested_keys(data)) & forbidden)]
    invoices = {row.get('invoice_id') for row in data.get('linked_invoice_refs', [])}
    if fixtures.trace_hidden_invoice_id in invoices:
        errors.append('trace_unrelated_invoice_link')
    if role != 'ceo':
        line = next((row for row in data['lines'] if row.get('line_id') == fixtures.seed.line.pk), None)
        if line is None or line.get('usable_reserved') is not None or line.get('completeness') != 'restricted':
            errors.append('trace_hidden_reservation_not_restricted')
        elif fixtures.trace_hidden_reservation_id in {r.get('id') for r in line['source_refs']['reservations']}:
            errors.append('trace_hidden_reservation_id')
        if fixtures.trace_hidden_task_id in {row.get('id') for row in data.get('linked_tasks', [])}:
            errors.append('trace_hidden_historical_task')
    return errors


def statement_export_oracle(raw,fixtures):
    """Explicit CSV wire: immutable source references and current ledger state."""
    import csv,io
    f=fixtures
    columns=['external_id','booking_date','direction','amount','currency','counterparty_external_id','invoice_reference','purpose']
    extra=['import_id','line_id','document_id','source_sha256','first_import_id','first_document_id','first_source_sha256','transaction_id','status','allocated','unallocated']
    try:
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8'),newline=''));rows=list(reader)
        if reader.fieldnames!=columns+extra:return ['statement_export_refs_status_header_missing']
        inputs=list(csv.DictReader(io.StringIO(f.c03_csv.decode('utf-8'),newline='')))
        if len(rows)!=len(inputs):return ['statement_export_row_count_mismatch']
        actual={row['external_id']:row for row in rows}
        if len(actual)!=len(rows):return ['statement_export_duplicate_rows']
        errors=[]
        for original in inputs:
            label='salary' if original['direction']=='out' else original['currency'];row=actual.get(original['external_id'])
            expected={**original,'import_id':f.c03_import_id,'line_id':f.c03_lines[label],'document_id':str(f.c03_document_id),'source_sha256':f.c03_sha,
                'first_import_id':f.c03_import_id,'first_document_id':str(f.c03_document_id),'first_source_sha256':f.c03_sha,
                'transaction_id':str(f.c03_receipts[label]['transaction_id']),'status':'cash_recorded' if label=='salary' else 'reconciled',
                'allocated':'0.00' if label=='salary' else original['amount'],'unallocated':'0.00'}
            if row!=expected:errors.append('statement_export_exact_source_or_state_'+label)
        return errors
    except (ValueError,UnicodeDecodeError,KeyError,csv.Error):return ['statement_export_invalid_csv']


def statement_response_oracle(data,status,method,fixtures,route):
    """Independent currency arithmetic and exact first-source read contract."""
    from decimal import Decimal
    from finance.models import Transaction
    f=fixtures;errors=[]
    if method=='POST' and route==C03_SOURCE and status==201:
        if not isinstance(data,dict) or data.get('checksum')!=f.c03_sha or data.get('format')!='bos_statement_csv_v1' or data.get('row_count')!=4:
            errors.append('statement_source_identity_or_bytes_mismatch')
    if method!='GET' or status!=200:return errors
    if route.endswith('/export/'):return errors
    if route==C03_JOURNAL:
        if not isinstance(data,dict) or data.get('includes_archived') is not True or data.get('balance_kind')!='period_movement':
            return ['journal_summary_envelope_mismatch']
        expected={c:{'in':Decimal(0),'out':Decimal(0)} for c in ('EUR','USD','UAH')}
        for row in Transaction._base_manager.values('currency','direction','amount'):expected[row['currency']][row['direction']]+=row['amount']
        actual={r['currency']:r for r in data.get('currencies',[])}
        if set(actual)!=set(expected):return ['journal_currency_partition_mismatch']
        for currency,value in expected.items():
            for key,amount in {**value,'net':value['in']-value['out']}.items():
                if actual[currency].get(key)!=format(amount,'.2f'):errors.append('journal_exact_'+currency+'_'+key)
        return errors
    if route in ('/api/statements/imports/','/api/statements/lines/'):
        if not isinstance(data,dict) or set(data)!={'items','next_cursor'} or not isinstance(data['items'],list) or not data['items']:
            return ['statement_list_envelope_or_positive_rows_missing']
    if route=='/api/statements/imports/{pk}/':
        if data.get('first_commit_receipt')!=f.c03_import_receipt or data.get('first_source',{}).get('checksum')!=f.c03_sha:
            errors.append('statement_original_import_receipt_or_source_changed')
    if route=='/api/statements/lines/{pk}/':
        if data.get('line',{}).get('id')!=f.c03_lines['EUR'] or data.get('first_source',{}).get('checksum')!=f.c03_sha:
            errors.append('statement_line_identity_or_source_changed')
        if data.get('transaction',{}).get('id')!=f.c03_receipts['EUR']['transaction_id']:
            errors.append('statement_line_transaction_missing')
    return errors


def task_response_oracle(data,status,method,role,fixtures,variant,route):
    errors=[]
    raw_writer=(route=='/api/tasks/' and method=='POST') or (route=='/api/tasks/{pk}/' and method in ('PUT','PATCH','DELETE'))
    if raw_writer and role in ('ceo','manager'):
        if status!=403 or not isinstance(data,dict) or data.get('code')!='approval_required':
            errors.append('task_raw_writer_not_explicitly_denied')
    if method!='GET' or status!=200:
        return errors
    if route==C01_OUTCOME:
        keys={'proposal_id','action','state','expires_at','same_session','receipt'}
        if not isinstance(data,dict) or set(data)!=keys:
            return errors+['task_outcome_envelope_mismatch']
        if data['proposal_id']!=fixtures.c01_proposals['outcome'] or data['action']!='update_task' or data['state']!='succeeded' or data['same_session'] is not True:
            errors.append('task_outcome_identity_state_mismatch')
        if data['receipt']!=fixtures.c01_receipts['outcome']:
            errors.append('task_outcome_changed_first_receipt')
        return errors
    if route==C01_HISTORY:
        forbidden={'phone','email','birthday','salary','amount','paid','cost','price','payload','source_snapshot','untyped_private'}
        errors += ['task_history_private_field:'+key for key in sorted(set(nested_keys(data))&forbidden)]
        if not isinstance(data,dict) or set(data)!={'task_id','items','next_cursor'} or data['task_id']!=fixtures.c01_tasks['visible']:
            return errors+['task_history_envelope_or_source_mismatch']
        if not isinstance(data['items'],list) or len(data['items'])<3:
            return errors+['task_history_missing_committed_events']
        for item in data['items']:
            if item.get('legacy'):
                if item.get('before') is not None or item.get('after') is not None or item.get('changes')!=[]:
                    errors.append('task_history_invented_legacy_diff')
            else:
                allowed={'id','action','transition','created_at','actor','reason','before','after','changes','legacy'}
                if set(item)!=allowed or not isinstance(item.get('actor'),dict) or set(item['actor'])!={'id','role','display'}:
                    errors.append('task_history_unknown_or_missing_structured_fields')
                if item.get('transition')=='complete' and (item['after'].get('result')!=fixtures.c01_markers['visible_result'] or item['actor'].get('id')!=fixtures.users['manager'].pk):
                    errors.append('task_history_actual_result_actor_mismatch')
        return errors
    rows=data if isinstance(data,list) else [data]
    fields={'assignee_id','assignee_name','order_id','order_code','result','result_recorded','archived_at','archived','is_overdue'}
    for row in rows:
        if not isinstance(row,dict) or not fields<=set(row):
            errors.append('task_read_missing_explicit_c01_fields')
    if isinstance(data,list) and any(row.get('id')==fixtures.c01_tasks['archived'] for row in data):
        errors.append('task_default_list_includes_archive')
    return errors


C01_CONTROL_IDS=(
    'visible_history_aliases','current_historical_source_scope','archive_restore_retains_source',
    'controlled_writer_alternative','own_foreign_outcomes','revoked_role_outcome',
    'new_session_read_not_execution','pending_expired_read_not_execution','other_action_outcome',
    'history_pagination_cursor_scope','no_document_source_scope','technical_task_admin_read_only')


def run_c01_controls(fixtures):
    """Explicit additional HTTP contracts; keeps all177 routes/57 field tests."""
    from django.conf import settings
    from django.db import transaction
    from django.test import Client
    from django.contrib.auth.models import Group
    from django.utils import timezone as django_timezone
    from datetime import timedelta
    from operations.models import ActionProposal,AuditEvent
    from tasks.models import Task
    from scripts.check_support import login_test_client
    from urllib.parse import urlencode
    f=fixtures;results=[];calls=[]
    def response(client,method,path,expected,payload=None,form=False):
        before=f.state_digest()
        body=urlencode(payload or {},doseq=True).encode() if form else json.dumps(payload or {}).encode()
        r=client.generic(method,path,body,content_type='application/x-www-form-urlencoded' if form else 'application/json',
            HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
        calls.append({'method':method,'route':path,'status':r.status_code})
        assert r.status_code in ({expected} if isinstance(expected,int) else set(expected)),(method,path,r.status_code,r.content[:400])
        if method=='GET' or r.status_code in (400,401,403,404,405,409,422):
            assert f.state_digest()==before,('read_or_denial_mutated_domain',path)
        return json.loads(r.content) if 'json' in r.get('Content-Type','') else r.content.decode(errors='replace')
    def approved(client,payload):
        p=response(client,'POST','/api/operations/preview/',200,payload)
        assert p.get('id'),p
        r=response(client,'POST','/api/operations/confirm/',200,{'proposal_id':p['id'],'confirmed':True})
        return p,r
    def run(name,fn):
        nonlocal calls
        calls=[]
        try:
            with transaction.atomic():
                fn();transaction.set_rollback(True)
            results.append({'id':name,'passed':True,'http':calls})
        except Exception as exc:
            results.append({'id':name,'passed':False,'error':str(exc),'traceback':traceback.format_exc(),'http':calls})
    def aliases(stem):return (stem+'/',stem+'.json',stem+'.json/')
    def visible_history():
        for role in ('ceo','manager','observer'):
            for path in aliases('/api/tasks/'+str(f.c01_tasks['visible'])+'/history'):
                d=response(f.client(role),'GET',path,200)
                assert not task_response_oracle(d,200,'GET',role,f,'full',C01_HISTORY)
                assert f.c01_markers['legacy_raw_payload'] not in json.dumps(d)
    run('visible_history_aliases',visible_history)
    def hidden():
        for role in ('manager','observer'):
            c=f.client(role)
            for name in ('current_hidden','history_hidden'):
                for path in aliases('/api/tasks/'+str(f.c01_tasks[name]))+aliases('/api/tasks/'+str(f.c01_tasks[name])+'/history'):
                    d=response(c,'GET',path,404)
                    assert f.c01_markers[name+'_result'] not in json.dumps(d)
            for path in ('/api/tasks/','/api/tasks.json','/api/tasks/?archived=true','/api/erp/snapshot/','/api/operations/summary/'):
                text=json.dumps(response(c,'GET',path,200))
                for name in ('current_hidden','history_hidden'):
                    assert f.c01_markers[name+'_result'] not in text and 'A04 C01 '+name not in text
        c=f.client('ceo')
        for name in ('current_hidden','history_hidden'):
            d=response(c,'GET','/api/tasks/'+str(f.c01_tasks[name])+'/history/',200)
            assert f.c01_markers[name+'_result'] in json.dumps(d)
        # Relink happened before101 unrelated audit rows; global history limits
        # may never disclose its previously private result.
        assert AuditEvent.objects.filter(action='a04_c01_padding').count()==101
    run('current_historical_source_scope',hidden)
    def archive():
        c=f.client('manager');pk=f.c01_tasks['archived'];original=Task.objects.filter(pk=pk).values().get()
        assert original['archived_at'] is not None
        for path in ('/api/tasks/','/api/tasks.json','/api/tasks.json/'):
            assert pk not in [x['id'] for x in response(c,'GET',path,200)]
        for path in ('/api/tasks/?archived=true','/api/tasks.json?archived=true'):
            row=next(x for x in response(c,'GET',path,200) if x['id']==pk)
            assert row['archived'] and row['result']==f.c01_markers['archive_result'] and row['assignee_id']==f.seed.employee.pk
        history=response(c,'GET',f'/api/tasks/{pk}/history/',200)
        assert f.c01_markers['archive_reason'] in json.dumps(history)
        stats_before=response(c,'GET','/api/dashboard/summary/',200)['tasks']
        home_before=response(c,'GET','/api/erp/snapshot/',200)['home']['tasks']
        assert pk not in [row['id'] for row in home_before]
        p,r=approved(c,{'action':'update_task','task_id':pk,'archived':False,'reason':f.c01_markers['restore_reason']})
        restored=Task.objects.filter(pk=pk).values().get();assert restored.pop('archived_at') is None;original.pop('archived_at');assert restored==original
        stats_after=response(c,'GET','/api/dashboard/summary/',200)['tasks']
        home_after=response(c,'GET','/api/erp/snapshot/',200)['home']['tasks']
        assert pk in [row['id'] for row in home_after]
        assert stats_after['total']==stats_before['total']+1 and stats_after['done']==stats_before['done']+1
        assert all(stats_after[key]==stats_before[key] for key in ('active','process','overdue'))
        assert response(c,'POST','/api/operations/confirm/',200,{'proposal_id':p['id'],'confirmed':True})==r
        before=(Task.objects.count(),AuditEvent.objects.count(),ActionProposal.objects.count())
        nop=response(c,'POST','/api/operations/preview/',200,{'action':'update_task','task_id':pk,'archived':False,'reason':'Уже відновлено без нового ефекту'})
        assert nop['state']=='no_change' and nop['id'] is None
        assert before==(Task.objects.count(),AuditEvent.objects.count(),ActionProposal.objects.count())
    run('archive_restore_retains_source',archive)
    def alternative():
        c=f.client('manager');before=Task.objects.count()
        p,r=approved(c,{**f.task_payload(),'title':'C01 ALTERNATIVE WRITER','order_id':f.seed.order.pk})
        pk=r['task_id'];assert Task.objects.count()==before+1
        approved(c,{'action':'update_task','task_id':pk,'status':'done','result':'C01 ALTERNATIVE RESULT','reason':'Підтверджено завершення доручення'})
        approved(c,{'action':'update_task','task_id':pk,'archived':True,'reason':'Знято завершену задачу з робочого списку'})
        assert Task.objects.get(pk=pk).result=='C01 ALTERNATIVE RESULT'
        for path in aliases('/api/tasks/'+str(pk)):
            d=response(c,'DELETE',path,403,{})
            assert d.get('code')=='approval_required'
        assert Task.objects.count()==before+1
        assert response(c,'POST','/api/operations/confirm/',200,{'proposal_id':p['id'],'confirmed':True})==r
    run('controlled_writer_alternative',alternative)
    def own_foreign():
        c=f.client('manager');path='/api/operations/task-proposals/'+f.c01_proposals['visible']+'/'
        d=response(c,'GET',path,200);assert d['state']=='succeeded' and d['same_session'] is True and d['receipt']==f.c01_receipts['visible']
        for role in ('ceo','observer'):response(f.client(role),'GET',path,404)
        other=Client(enforce_csrf_checks=True);login_test_client(other,'manager',capabilities=('view_document',))
        response(other,'GET',path,404)
    run('own_foreign_outcomes',own_foreign)
    def revoked():
        f.users['manager'].groups.set([Group.objects.get(name='observer')])
        d=response(f.client('manager'),'GET','/api/operations/task-proposals/'+f.c01_proposals['visible']+'/',403)
        assert 'receipt' not in d or d['receipt'] is None
        assert f.c01_markers['visible_result'] not in json.dumps(d)
    run('revoked_role_outcome',revoked)
    def new_session():
        c=Client(enforce_csrf_checks=True);c.get('/api/auth/csrf/')
        login=c.post('/api/auth/login/',{'username':f.users['manager'].username,'password':f.password},content_type='application/json',HTTP_X_CSRFTOKEN=c.cookies[settings.CSRF_COOKIE_NAME].value);assert login.status_code==200
        pid=f.c01_proposals['visible'];d=response(c,'GET','/api/operations/task-proposals/'+pid+'/',200)
        assert d['state']=='succeeded' and d['same_session'] is False and d['receipt']==f.c01_receipts['visible']
        response(c,'POST','/api/operations/confirm/',403,{'proposal_id':pid,'confirmed':True})
    run('new_session_read_not_execution',new_session)
    def pending_expired():
        c=f.client('manager');pid=f.c01_pending_manager;path='/api/operations/task-proposals/'+pid+'/'
        d=response(c,'GET',path,200);assert d['state']=='pending' and d['receipt'] is None
        ActionProposal.objects.filter(pk=pid).update(expires_at=django_timezone.now()-timedelta(minutes=1))
        d=response(c,'GET',path,200);assert d['state']=='expired' and d['receipt'] is None
        denied=response(c,'POST','/api/operations/confirm/',409,{'proposal_id':pid,'confirmed':True})
        assert denied['code']=='proposal_expired'
        assert ActionProposal.objects.get(pk=pid).receipt is None
    run('pending_expired_read_not_execution',pending_expired)
    def other_action():
        p=ActionProposal.objects.get(payload__action='erp_import_batch')
        response(f.client('ceo'),'GET',f'/api/operations/task-proposals/{p.pk}/',404)
    run('other_action_outcome',other_action)
    def pagination():
        c=f.client('manager');path='/api/tasks/'+str(f.c01_tasks['visible'])+'/history/'
        first=response(c,'GET',path+'?limit=1',200);assert len(first['items'])==1 and first['next_cursor']
        cursor=first['next_cursor'];seen={first['items'][0]['id']}
        while cursor:
            d=response(c,'GET',path+'?limit=1&'+urlencode({'cursor':cursor}),200)
            for item in d['items']:assert item['id'] not in seen;seen.add(item['id'])
            cursor=d['next_cursor']
        assert len(seen)==AuditEvent.objects.filter(task_id=f.c01_tasks['visible']).count()
        response(c,'GET',path+'?cursor=invalid',400)
        response(c,'GET',path+'?limit=0',400)
        response(c,'GET',path+'?limit=51',400)
        response(f.client('ceo'),'GET',path+'?'+urlencode({'cursor':first['next_cursor']}),400)
        response(c,'GET','/api/tasks/'+str(f.c01_tasks['archived'])+'/history/?'+urlencode({'cursor':first['next_cursor']}),400)
    run('history_pagination_cursor_scope',pagination)
    def no_documents():
        for role in ('manager','observer'):
            f.limit_capabilities(role,'no_documents');c=f.client(role)
            for path in aliases('/api/tasks/'+str(f.c01_tasks['visible'])+'/history'):
                response(c,'GET',path,404)
            for path in ('/api/tasks/','/api/tasks/?archived=true'):
                text=json.dumps(response(c,'GET',path,200))
                for marker in f.c01_markers.values():assert marker not in text
        response(f.client('manager'),'GET','/api/operations/task-proposals/'+f.c01_proposals['visible']+'/',404)
    run('no_document_source_scope',no_documents)
    def admin_read_only():
        c=f.client('technical_admin');pk=f.admin['tasks.task'].pk
        response(c,'GET',f'/admin/tasks/task/{pk}/change/',200)
        for name,path in [('tasks_task_add','/admin/tasks/task/add/'),('tasks_task_change',f'/admin/tasks/task/{pk}/change/'),('tasks_task_delete',f'/admin/tasks/task/{pk}/delete/'),('tasks_task_changelist','/admin/tasks/task/')]:
            row={'name':'admin:'+name,'model':'tasks.task'};payload,mode=f.admin_payload(row,path,'POST','technical_admin')
            before=f.state_digest();response(c,'POST',path,{200,302,403,405},payload,form=True);assert f.state_digest()==before
    run('technical_task_admin_read_only',admin_read_only)
    assert tuple(row['id'] for row in results)==C01_CONTROL_IDS,'Explicit C01 controls must not shrink'
    return results


C03_CONTROL_IDS=('statement_original_source','statement_marker_permanence','statement_import_history_permanence',
    'statement_historical_task_context','statement_transaction_salary_scope','statement_source_permissions',
    'statement_bound_transaction_protection','statement_archive_currency_totals','statement_exact_replay',
    'statement_summary_layers','statement_scoped_filters_cursors','statement_upload_admission')


def run_c03_controls(fixtures,owner=None):
    """Additional fixed C03 source/access controls; no replacement of C01/57."""
    from decimal import Decimal
    from django.conf import settings
    from django.db import transaction,connection
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.contrib import admin
    from urllib.parse import urlencode
    from finance.models import StatementImport,StatementLine,StatementAllocation,Transaction
    from operations.models import Document
    from erp.models import Event
    from boss_project.archive import restore_record
    f=fixtures;results=[];calls=[]
    def request(role,method,path,expected,payload=None,form=False,multipart=False):
        client=f.client(role);before=f.state_digest();kw={'HTTP_X_CSRFTOKEN':client.cookies[settings.CSRF_COOKIE_NAME].value}
        if multipart:r=client.post(path,payload,**kw)
        else:r=client.generic(method,path,urlencode(payload or {},doseq=True).encode() if form else json.dumps(payload or {}).encode(),content_type='application/x-www-form-urlencoded' if form else 'application/json',**kw)
        raw=b''.join(r.streaming_content) if getattr(r,'streaming',False) else r.content
        calls.append({'role':role,'method':method,'route':path,'status':r.status_code})
        assert r.status_code in ({expected} if isinstance(expected,int) else set(expected)),(method,path,r.status_code,raw[:300])
        if method in ('GET','HEAD','OPTIONS') or r.status_code in (400,401,403,404,405,409,413,422):assert f.state_digest()==before,('unexpected_domain_change',path)
        text=raw.decode(errors='replace')+'\n'+json.dumps(dict(r.headers))
        data=json.loads(raw) if 'json' in r.get('Content-Type','') and raw else raw
        if not isinstance(data,bytes):text+='\n'+json.dumps(data,ensure_ascii=False)
        for marker in f.forbidden_markers(role,path,'full'):assert marker not in text,('forbidden_marker',path,marker)
        return data
    def run(name,fn,durable=False):
        nonlocal calls
        calls=[]
        try:
            if durable and owner is None:raise ValueError('Owned committed source isolation is required')
            with owner.committed_case(connection,settings.MEDIA_ROOT) if durable else transaction.atomic():
                fn()
                if not durable:transaction.set_rollback(True)
            results.append({'id':name,'passed':True,'http':calls})
        except Exception as exc:results.append({'id':name,'passed':False,'error':str(exc),'traceback':traceback.format_exc(),'http':calls})
    def aliases(stem):return (stem+'/',stem+'.json',stem+'.json/')
    def document_hidden(pk):
        for role in ('manager','observer'):
            request(role,'GET',f'/api/operations/documents/{pk}/',404)
            request(role,'GET',f'/api/operations/documents/{pk}/download/',404)
    def original():
        d=request('ceo','GET',f'/api/statements/imports/{f.c03_import_id}/',200)
        assert d['first_commit_receipt']==f.c03_import_receipt and d['first_source']['checksum']==f.c03_sha
        raw=request('ceo','GET',d['first_source']['download_url'],200)
        assert raw==f.c03_csv and hashlib.sha256(raw).hexdigest()==f.c03_sha
        request('ceo','GET','/api/operations/documents/?q=A04-C03',200)
        line=request('ceo','GET',f'/api/statements/lines/{f.c03_lines["EUR"]}/',200)
        assert line['normalized_input']['purpose']==f.c03_markers['purpose']+' EUR\n=synthetic text'
        assert line['transaction']['id']==f.c03_receipts['EUR']['transaction_id']
        assert line['allocations'][0]['payment_event_id'] in f.c03_receipts['EUR']['created_payment_event_ids']
        assert not {StatementImport,StatementLine,StatementAllocation}&set(admin.site._registry)
    run('statement_original_source',original)
    def marker():
        pk=f.c03_unimported_document_id;Document.objects.filter(pk=pk).update(access_level='operational')
        document_hidden(pk)
        for role in ('manager','observer'):request(role,'GET','/api/operations/documents/?q=A04-C03',200)
    run('statement_marker_permanence',marker)
    def imported():
        Document.objects.filter(pk=f.c03_document_id).update(access_level='operational',sections=[])
        document_hidden(f.c03_document_id)
        # Deliberate legacy metadata canary, not a successful generic upload.
        later=f.seed.make_document('A04-C03-SOURCE','operational',revision='Z',marker=f.c03_markers['purpose']+' LATER')
        document_hidden(later.pk)
        for role in ('manager','observer'):request(role,'GET','/api/operations/documents/',200)
    run('statement_import_history_permanence',imported)
    def task_context():
        Document.objects.filter(pk=f.c03_document_id).update(access_level='operational',sections=[])
        for role in ('manager','observer'):
            for path in aliases('/api/tasks/'+str(f.c03_task_id))+aliases('/api/tasks/'+str(f.c03_task_id)+'/history'):request(role,'GET',path,404)
            for path in ('/api/tasks/','/api/tasks/?archived=true','/api/operations/summary/','/api/operations/audit/','/api/erp/snapshot/','/api/dashboard/summary/'):
                request(role,'GET',path,200)
            request(role,'POST','/api/operations/chat/',200,{'message':'Перелічіть джерела і доручення'})
            request(role,'GET','/api/operations/export/',200 if role=='manager' else 403)
            request(role,'GET','/api/erp/export/',200 if role=='manager' else 403)
        visible=request('ceo','GET',f'/api/tasks/{f.c03_task_id}/history/',200)
        assert f.c03_markers['task_result'] in json.dumps(visible,ensure_ascii=False)
    run('statement_historical_task_context',task_context)
    def transaction_scope():
        for role in ('manager','observer'):
            for path in aliases('/api/transactions'):
                d=request(role,'GET',path,200 if role=='manager' else 403)
                if role=='manager':assert not {row['id'] for row in d}&{r['transaction_id'] for r in f.c03_receipts.values()}
            for receipt in f.c03_receipts.values():
                for path in aliases('/api/transactions/'+str(receipt['transaction_id'])):request(role,'GET',path,404 if role=='manager' else 403)
            request(role,'GET','/api/employees/',200)
            request(role,'GET','/admin/finance/transaction/',403)
        salary=request('ceo','GET',f'/api/statements/lines/{f.c03_lines["salary"]}/',200)
        assert salary['transaction']['id']==f.seed.salaries[0].transaction_id
        assert salary['line']['status']=='cash_recorded' and salary['line']['allocated']=='0.00' and salary['allocations']==[]
    run('statement_transaction_salary_scope',transaction_scope)
    def permissions():
        f.limit_capabilities('ceo','no_export');request('ceo','GET',f'/api/statements/imports/{f.c03_import_id}/export/',403)
        f.limit_capabilities('ceo','no_download');request('ceo','GET',f'/api/operations/documents/{f.c03_document_id}/download/',403)
        request('ceo','GET',f'/api/operations/task-proposals/{f.c03_import_proposal["id"]}/',404)
        for role in ('manager','observer'):
            request(role,'POST','/api/erp/preview/',403,f.c03_payloads['EUR'])
            request(role,'POST','/api/operations/confirm/',403,{'proposal_id':f.c03_proposals['EUR']['id'],'confirmed':True})
    run('statement_source_permissions',permissions)
    def protected_transaction():
        pk=f.c03_receipts['EUR']['transaction_id']
        for path in aliases('/api/transactions/'+str(pk)):
            request('ceo','PATCH',path,400,{'description':'Attempt to replace source-bound financial description'})
        from django.test import RequestFactory
        obj=Transaction.objects.get(pk=pk);path=f'/admin/finance/transaction/{pk}/change/'
        native_request=RequestFactory().post(path);native_request.user=f.users['technical_admin']
        form_class=admin.site._registry[Transaction].get_form(native_request,obj=obj)
        initial=form_class(instance=obj);values={key:initial[key].value() if initial[key].value() is not None else '' for key in initial.fields}
        valid=form_class(data=values,instance=obj)
        assert valid.is_valid(),('invalid_unchanged_native_financial_form',str(valid.errors))
        # Validate the unchanged complete form; the intentional forbidden mutation
        # must reach the actual HTTP admin boundary rather than a positive helper.
        values['description']='Attempt from complete native admin form';before=f.state_digest()
        body=request('technical_admin','POST',path,{200,409},values,form=True)
        assert 'незмінним' in body.decode(),('missing_source_immutability_error',body[:200])
        assert f.state_digest()==before
    run('statement_bound_transaction_protection',protected_transaction)
    def archive():
        pk=f.c03_receipts['EUR']['transaction_id'];before=request('ceo','GET',C03_JOURNAL,200);stored=Transaction.objects.filter(pk=pk).values().get()
        request('ceo','DELETE',f'/api/transactions/{pk}/',204)
        now=Transaction.objects.filter(pk=pk).values().get();assert now.pop('archived_at') is not None;stored.pop('archived_at');assert now==stored
        assert request('ceo','GET',C03_JOURNAL,200)==before
        line=request('ceo','GET',f'/api/statements/lines/{f.c03_lines["EUR"]}/',200)
        assert line['line']['cash_recorded'] and line['line']['status']=='reconciled' and line['line']['allocated']=='17.39'
        restore_record(Transaction.objects.get(pk=pk),actor=f.users['ceo'])
        assert Transaction.objects.get(pk=pk).archived_at is None and request('ceo','GET',C03_JOURNAL,200)==before
    run('statement_archive_currency_totals',archive)
    def replay():
        def records():
            return {m._meta.label_lower:list(m._base_manager.order_by(m._meta.pk.name).values()) for m in f.business_models}
        expected=records()
        mutex=[row for row in expected['operations.configuration'] if row['key']=='erp_write']
        assert len(mutex)==1 and set(mutex[0]['value'])=={'revision'}
        for p,r in [(f.c03_import_proposal,f.c03_import_receipt)]+[(f.c03_proposals[c],f.c03_receipts[c]) for c in ('EUR','USD','UAH','salary')]:
            assert request('ceo','POST','/api/operations/confirm/',200,{'proposal_id':p['id'],'confirmed':True})==r
            # Existing ERP mutex is the sole permitted replay delta, proved in
            # REPLAY_DIAGNOSTIC.json; keep every other row and field exact.
            mutex[0]['value']['revision']+=1
            assert records()==expected,'Replay changed more than the one ERP mutex revision'
        before=f.state_digest()
        for payload in (f.c03_import_payload,f.c03_payloads['EUR']):
            d=request('ceo','POST','/api/erp/preview/',200,payload);assert d['state']=='no_change' and d['id'] is None
        assert f.state_digest()==before
    run('statement_exact_replay',replay)
    def summaries():
        expected={c:{'in':Decimal(0),'out':Decimal(0),'allocated':Decimal(0)} for c in ('EUR','USD','UAH')}
        for row in StatementLine.objects.values('currency','direction','amount'):expected[row['currency']][row['direction']]+=row['amount']
        for row in StatementAllocation.objects.values('currency','amount'):expected[row['currency']]['allocated']+=row['amount']
        d=request('ceo','GET','/api/statements/summary/',200);currencies={r['currency']:r for r in d['currencies']};assert set(currencies)==set(expected)
        for currency,t in expected.items():
            actual=currencies[currency]
            for key,value in {'in':t['in'],'out':t['out'],'net':t['in']-t['out']}.items():
                assert actual['imported'][key]==format(value,'.2f') and actual['recorded'][key]==format(value,'.2f')
                assert actual['unposted'][key]=='0.00'
            assert actual['incoming']=={'allocated':format(t['allocated'],'.2f'),'unallocated':format(t['in']-t['allocated'],'.2f')}
        for path in aliases('/api/transactions/summary'):
            d=request('ceo','GET',path,200);assert statement_response_oracle(d,200,'GET',f,C03_JOURNAL)==[]
    run('statement_summary_layers',summaries)
    def filters():
        for url in ('/api/statements/lines/?limit=0','/api/statements/lines/?limit=101','/api/statements/lines/?currency=GBP','/api/statements/summary/?from=2026-02-30','/api/transactions/summary/?currency=GBP'):
            request('ceo','GET',url,400)
        first=request('ceo','GET','/api/statements/lines/?limit=1',200);assert len(first['items'])==1 and first['next_cursor']
        seen={first['items'][0]['id']};cursor=first['next_cursor']
        while cursor:
            d=request('ceo','GET','/api/statements/lines/?limit=1&'+urlencode({'cursor':cursor}),200)
            for row in d['items']:assert row['id'] not in seen;seen.add(row['id'])
            cursor=d['next_cursor']
        assert len(seen)==4
        request('ceo','GET','/api/statements/lines/?currency=EUR&'+urlencode({'cursor':first['next_cursor']}),400)
        for role in ('manager','observer'):request(role,'GET','/api/statements/lines/?'+urlencode({'cursor':first['next_cursor']}),403)
    run('statement_scoped_filters_cursors',filters)
    def admission():
        malformed={'code':'A04-C03-INVALID','revision':'A','title':'Invalid synthetic source','file':SimpleUploadedFile('invalid.csv',b'external_id,external_id\nA,B\n',content_type='text/csv')}
        request('ceo','POST',C03_SOURCE,422,malformed,multipart=True)
        for role in ('manager','observer'):
            invalid={**malformed,'file':SimpleUploadedFile('invalid.csv',b'not csv',content_type='text/csv')};request(role,'POST',C03_SOURCE,403,invalid,multipart=True)
        reused=f.statement_upload_payload('A04-OPEN');request('ceo','POST',C03_SOURCE,{409,422},reused,multipart=True)
        request('ceo','POST','/api/operations/documents/upload/',{409,422},{'code':'A04-C03-SOURCE','revision':'B','title':'Wrong generic source','file':SimpleUploadedFile('ordinary.txt',b'ordinary',content_type='text/plain')},multipart=True)
    run('statement_upload_admission',admission,durable=True)
    assert tuple(row['id'] for row in results)==C03_CONTROL_IDS,'Explicit C03 controls must not shrink'
    return results


def correction_outcome_oracle(data, status, method, role, fixtures, variant):
    """Actual persisted source and exact receipt; never accept an empty 200."""
    errors = []
    private = {'amount', 'paid', 'price', 'extras', 'cost', 'unit_cost', 'allocated_cost', 'source_cost',
               'return_allocated_cost', 'agreed_amount', 'total', 'source_snapshot', 'basis_snapshot',
               'basis_hash', 'payload', 'reason', 'actor_id', 'settlement', 'effective_credit',
               'net_amount', 'receivable', 'customer_credit'}
    if role != 'ceo':
        errors += ['correction_private_field:' + key for key in sorted(set(nested_keys(data)) & private)]
    if method != 'GET':
        return errors
    if status == 404:
        if data != {'state': 'unknown', 'receipt': None}:
            errors.append('correction_unknown_must_not_disclose_source')
        return errors
    if status != 200:
        return errors
    if not isinstance(data, dict) or set(data) != {'state', 'action', 'operation_id', 'receipt'}:
        return errors + ['correction_outcome_envelope_mismatch']
    if data.get('state') != 'succeeded' or data.get('action') != fixtures.correction_action or data.get('operation_id') != fixtures.correction_operation_id:
        errors.append('correction_outcome_identity_mismatch')
    receipt = data.get('receipt')
    if not isinstance(receipt, dict):
        return errors + ['correction_receipt_missing']
    for key in ('state', 'action', 'operation_id', 'quantity', 'currency'):
        if receipt.get(key) != fixtures.correction_receipt.get(key):
            errors.append('correction_receipt_value:' + key)
    for key in ('receipt_id', 'lot_id', 'goods_return_id', 'movement_id', 'claim_id', 'erp_event_id'):
        if receipt.get(key) != fixtures.correction_source_ids[key]:
            errors.append('correction_actual_source_mismatch:' + key)
    if role == 'ceo':
        if receipt != fixtures.correction_receipt:
            errors.append('correction_first_receipt_changed')
    else:
        allowed = {'state', 'action', 'operation_id', 'erp_event_id', 'actor_role', 'impact',
                   'goods_return_id', 'receipt_id', 'movement_id', 'lot_id', 'claim_id', 'quantity', 'currency'}
        errors += ['correction_unknown_receipt_field:' + key for key in sorted(set(receipt) - allowed)]
        permitted_impacts = {('lots', 'quantity'), ('purchases', 'returned_quantity'),
                             ('goods_returns', 'quantity'), ('supplier_claims', 'record_kind')}
        for impact in receipt.get('impact', []):
            if not isinstance(impact, dict) or (impact.get('kind'), impact.get('field')) not in permitted_impacts:
                errors.append('correction_private_or_unknown_impact')
    return errors


def emit(report, output):
    value = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(value + '\n', encoding='utf-8')
    print(value, flush=True)
    return 0 if report.get('complete') else 1


def main():
    args = parse_args()
    report = {'gate': 4, 'date': datetime.now(timezone.utc).isoformat(), 'complete': False,
              'catalogue': [], 'cases': [], 'failures': [], 'field_tests': {}}
    def fail(stage, detail, **fields):
        report['failures'].append({'stage': stage, 'detail': detail, **fields})
    try:
        if not __debug__:
            raise ValueError('Assertions disabled')
        root = args.project_root.resolve()
        sys.path.insert(0, str(root))
        os.environ['DJANGO_SETTINGS_MODULE'] = 'verification_settings'
        os.environ['BOS_DATA_MODE'] = 'working'
        os.environ.pop('ANTHROPIC_API_KEY', None)
        name = os.environ.get('BOS_TEST_DB_NAME', '')
        if os.environ.get('BOS_VERIFY_DB', 'sqlite') == 'sqlite':
            db = Path(name)
            if name != ':memory:' and (not db.is_absolute() or not re.fullmatch(r'check_[a-f0-9]{32}\.sqlite3', db.name) or db.exists() or db.is_relative_to(root)):
                raise ValueError('Refuse non-new/non-verify SQLite path; never open a working DB')
        if not os.environ.get('BOS_TEST_MEDIA'):
            raise ValueError('BOS_TEST_MEDIA is required')
        import django
        django.setup()
        from django.conf import settings
        from django.core.management import call_command
        from django.db import connection, transaction
        from django.test import Client, override_settings
        from django.urls import resolve
        from scripts.check_support import prove_database
        from access_fixtures import SweepFixtures
        # Include the server-only routes in the closed-world catalogue.
        # Original application routes and their accepted oracle remain identical.
        settings.ROOT_URLCONF = 'boss_project.server_urls'
        live = catalogue()
        manifest = json.loads(args.manifest.read_text())
        frozen = manifest['patterns']
        actual_counts, expected_counts = Counter(map(signature, live)), Counter(map(signature, frozen))
        for text, n in (actual_counts - expected_counts).items():
            fail('catalogue', 'unknown_route_definition', definition=json.loads(text), count=n)
        for text, n in (expected_counts - actual_counts).items():
            fail('catalogue', 'missing_expected_definition', definition=json.loads(text), count=n)
        report['catalogue'] = [public_row(row) for row in live]
        report['counts'] = {'resolver_patterns': len(live),
            'api_definitions': sum(row['pattern'].startswith('api/') for row in live),
            'admin_definitions': sum(row['pattern'].startswith('admin/') for row in live)}
        if args.catalogue_only:
            fail('execution', 'catalogue_only_is_not_a_pass')
            return emit(report, args.output)
        # Upload must finish a genuine durable commit. A rollback-only outer
        # atomic block cannot represent that request. Issue ownership BEFORE
        # connecting/migrating; only this newly created synthetic DB may later
        # be restored between committed cases.
        from scripts.access_isolation import OwnedSweepSQLite
        owner = None
        if connection.vendor == 'sqlite':
            if name == ':memory:':
                raise ValueError('Access sweep requires a new owned file-backed SQLite database')
            owner = OwnedSweepSQLite.create_new(name, root)
        prove_database()
        if owner is not None:
            owner.assert_owned(connection)
        if connection.introspection.table_names():
            raise ValueError('Synthetic database must be empty before migrate')
        call_command('migrate', verbosity=0)
        report['backend'] = connection.vendor
        with override_settings(BOS_DATA_MODE='working', DEBUG=False, ANTHROPIC_API_KEY='',
                               PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher']):
            fixtures = SweepFixtures(args.fixture_module)
            fixtures.build()
            for issue in fixtures.issues:
                fail('fixture', issue)
            definitions = defaultdict(list)
            for index, row in enumerate(live):
                if not row['pattern'].startswith(('api/', 'admin/', 'health/')):
                    continue
                try:
                    for path in materialize(row, fixtures):
                        definitions[path].append((index, row))
                except Exception as exc:
                    fail('fixture', str(exc), route=row['pattern'], definition_index=index)
            report['route_coverage'] = []
            for path, defs in definitions.items():
                matched = resolve(path)
                winner = next(((i, row) for i, row in defs if matched.func is row['_node'].callback), None)
                if winner is None:
                    fail('catalogue', 'resolved_to_unexpected_callback', route=path)
                    continue
                index, row = winner
                shadowed = [i for i, other in defs if other['_node'].callback is not matched.func]
                if shadowed and not (row['name'] == 'api-root' and path in ('/api/', '/api/.json', '/api/.json/')):
                    fail('catalogue', 'unknown_route_shadowing', route=path, definitions=shadowed)
                report['route_coverage'].append({'route': path, 'definition_indices': [i for i, _ in defs],
                    'resolved_definition': index, 'shadowed_definitions': shadowed})
                contexts = [(r, 'full') for r in ROLES]
                if canonical(path) == '/api/erp/corrections/outcome/':
                    contexts += [('manager', 'no_documents')]
                if canonical(path) == C01_HISTORY:
                    contexts += [(r,'no_documents') for r in ('manager','observer')]
                if canonical(path) in ('/api/erp/workpoints/', '/api/erp/lines/{pk}/supply-options/'):
                    contexts += [(r,'no_documents') for r in ('manager','observer')]
                if canonical(path)=='/api/statements/imports/{pk}/export/':
                    contexts += [('ceo','no_export')]
                if canonical(path) in EXPORTS:
                    contexts += [(r, 'no_export') for r in ('ceo', 'manager')]
                if '/documents/' in canonical(path) and 'upload' not in path:
                    contexts += [(r, 'no_documents') for r in ('manager', 'observer')]
                if path.endswith('/download/'):
                    contexts += [(r, 'no_download') for r in ('ceo', 'manager', 'observer')]
                for role, variant in contexts:
                    for method in METHODS:
                        case = {'route': path, 'pattern': row['pattern'], 'method': method, 'role': role,
                                'variant': variant, 'status': None, 'passed': False}
                        try:
                            expected, reason = contract(row, path, method, role, variant)
                            case.update(expectation=sorted(expected), policy=reason)
                            committed_upload = method == 'POST' and canonical(path) in ('/api/operations/documents/upload/',C03_SOURCE)
                            if committed_upload and owner is None:
                                raise ValueError('Committed access-case isolation is not implemented for this backend')
                            context = owner.committed_case(connection, settings.MEDIA_ROOT) if committed_upload else transaction.atomic()
                            with context as isolation:
                                if committed_upload:
                                    case['commit_isolation'] = isolation
                                client = fixtures.client(role)
                                fixtures.limit_capabilities(role, variant)
                                # Genuine fixtures and proposals are prepared before the request.
                                data, mode = fixtures.payload(row, path, method, role, client)
                                before = fixtures.state_digest()
                                request_path = path + fixtures.query(row, path)
                                kwargs = {'HTTP_X_CSRFTOKEN': client.cookies[settings.CSRF_COOKIE_NAME].value}
                                if method == 'POST' and canonical(path) in ('/api/transactions/', '/api/salaries/'):
                                    kwargs['HTTP_IDEMPOTENCY_KEY'] = 'a04-positive-financial-intent'
                                if mode == 'multipart' and method == 'POST':
                                    response = client.post(request_path, data, **kwargs)
                                else:
                                    content_type = 'application/json'
                                    if data is None:
                                        body = b''
                                    elif mode == 'form':
                                        from urllib.parse import urlencode
                                        body = urlencode(data, doseq=True).encode()
                                        content_type = 'application/x-www-form-urlencoded'
                                    elif mode == 'multipart':
                                        from django.test.client import encode_multipart, BOUNDARY, MULTIPART_CONTENT
                                        body = encode_multipart(BOUNDARY, data)
                                        content_type = MULTIPART_CONTENT
                                    else:
                                        body = json.dumps(data).encode()
                                    response = client.generic(method, request_path, body, content_type=content_type, **kwargs)
                                case['status'] = response.status_code
                                leaks, size = response_oracle(response, row, path, method, role, fixtures, variant)
                                case.update(leaks=leaks, response_bytes=size)
                                redirect_ok, redirect_checks = admin_redirect_oracle(
                                    response, row, path, role, client, fixtures, variant)
                                if response.status_code == 302 and path.startswith('/admin/'):
                                    case['redirect_location'] = response.get('Location', '')
                                if redirect_checks:
                                    case['redirect_checks'] = redirect_checks
                                if not redirect_ok:
                                    case['invalid_admin_redirect'] = True
                                denied_or_read = response.status_code in (401, 403, 404, 405, 503) or method in ('GET', 'HEAD', 'OPTIONS', 'TRACE', 'CONNECT') or canonical(path) == '/api/operations/chat/' or reason.endswith('_read_only')
                                changed = fixtures.state_digest() != before
                                case['unexpected_business_change'] = denied_or_read and changed
                                case['passed'] = response.status_code in expected and not leaks and not case['unexpected_business_change'] and redirect_ok
                                # Permission-only green must not hide a broken allowed writer.
                                if reason in ('allowed_drf_write', 'allowed_raw_create', 'allowed_admin_form') and response.status_code in expected and not changed:
                                    if canonical(path) not in PUBLIC_AUTH and row['name'] not in ('admin:password_change', 'admin:auth_user_password_change'):
                                        case['passed'] = False
                                        case['missing_positive_effect'] = True
                                if not committed_upload:
                                    transaction.set_rollback(True)
                        except Exception as exc:
                            case['passed'] = False
                            case['error'] = type(exc).__name__ + ': ' + str(exc)
                        report['cases'].append(case)
                        if not case['passed']:
                            fail('http', case.get('error', 'response_oracle_failed'), **case)
                if len(report['route_coverage']) % 15 == 0:
                    print(f"Gate 4: {len(report['route_coverage'])}/{len(definitions)} URL, {len(report['cases'])} HTTP cases", flush=True)
            report['c01_controls']=run_c01_controls(fixtures)
            for control in report['c01_controls']:
                if not control['passed']:
                    fail('c01_controls',control.get('error','failed'),control_id=control['id'])
            report['counts']['c01_control_groups']=len(report['c01_controls'])
            report['counts']['c01_control_http_responses']=sum(len(x['http']) for x in report['c01_controls'])
            report['c03_controls']=run_c03_controls(fixtures,owner)
            for control in report['c03_controls']:
                if not control['passed']:
                    fail('c03_controls',control.get('error','failed'),control_id=control['id'])
            report['counts']['c03_control_groups']=len(report['c03_controls'])
            report['counts']['c03_control_http_responses']=sum(len(x['http']) for x in report['c03_controls'])
            report['counts']['concrete_urls'] = len(definitions)
            report['counts']['executed_cases'] = len(report['cases'])
            report['counts']['http_responses'] = sum(c['status'] is not None for c in report['cases'])
            report['counts']['http_passed'] = sum(c['passed'] for c in report['cases'])
        report['counts']['redirect_http_responses'] = sum(
            len(c.get('redirect_checks', [])) for c in report['cases'])
        # These tests are mandatory additional evidence, not a replacement for catalogue coverage.
        from django.test.runner import DiscoverRunner
        class GateRunner(DiscoverRunner):
            def run_suite(self, suite, **kwargs):
                self.gate_result = super().run_suite(suite, **kwargs)
                return self.gate_result
        runner = GateRunner(verbosity=1, interactive=False, keepdb=False)
        suite = runner.build_suite(args.field_tests)
        count = suite.countTestCases()
        report['field_tests'].update(labels=args.field_tests, discovered=count)
        def test_ids(node):
            if hasattr(node, 'id'):
                yield node.id()
            else:
                for child in node:
                    yield from test_ids(child)
        discovered_ids = set(test_ids(suite))
        required_ids = set(manifest.get('required_field_tests', []))
        missing_ids = sorted(required_ids - discovered_ids)
        report['field_tests'].update(required_ids=sorted(required_ids), missing_ids=missing_ids)
        if len(required_ids) < 57 or missing_ids:
            fail('field_tests', 'missing_explicit_accepted_tests', required=len(required_ids), missing=missing_ids)
        if count < 57:
            fail('field_tests', 'fewer_than_57_accepted_field_context_tests', discovered=count)
        failures = runner.run_tests(args.field_tests)
        report['field_tests']['failures'] = failures
        result = runner.gate_result
        report['field_tests'].update(executed=result.testsRun, skipped=len(result.skipped),
                                    expected_failures=len(result.expectedFailures))
        if result.skipped or result.expectedFailures or result.testsRun < 57:
            fail('field_tests', 'skipped_or_unexecuted_accepted_tests', executed=result.testsRun,
                 skipped=len(result.skipped), expected_failures=len(result.expectedFailures))
        if failures:
            fail('field_tests', 'field_context_suite_failed', failures=failures)
        report['complete'] = not report['failures'] and bool(report['cases']) and count >= 57
    except Exception as exc:
        fail('setup', type(exc).__name__ + ': ' + str(exc))
        report['traceback'] = traceback.format_exc()
    return emit(report, args.output)


if __name__ == '__main__':
    raise SystemExit(main())
