"""Read-only MCP endpoint: an AI client the owner chooses reads BoS through the same Policy as the screens.

Model Context Protocol over Streamable HTTP with plain JSON responses (no event stream, no sessions). The
endpoint is off until the owner issues an access key on the server itself (manage.py mcp_access create);
each key acts as one BoS user and sees exactly what that user sees on «Моніторинг», money only for the CEO.
Tools only read: no writes, no SQL, no actions or previews. Keys are kept as SHA-256 hashes in Configuration
and shown once; a request carrying a browser Origin is refused, and a session cookie alone never authenticates.
"""
import hashlib
import hmac
import json
import logging
import secrets

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

LOG = logging.getLogger('bos.connectors')
KEY = 'mcp_access'
PREFIX = 'bos_mcp_'
VERSIONS = ('2025-06-18', '2025-03-26', '2024-11-05')
MAX_BODY = 64 * 1024
STATUS = {'quote': 'Пропозиція', 'confirmed': 'Підтверджено'}
INSTRUCTIONS = ('BoS — моніторинг компанії. Лише читання: числа, що потребує уваги, стандартні запити й стан '
                'замовлень у межах прав користувача ключа. Суми бачить лише керівник.')


# --- access keys -------------------------------------------------------------------------------------------

def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def keys():
    from operations.models import Configuration
    row = Configuration.objects.filter(key=KEY).first()
    value = row.value if row is not None and isinstance(row.value, dict) else {}
    return [k for k in value.get('keys', []) if isinstance(k, dict) and isinstance(k.get('sha256'), str)]


def _store(change):
    from operations.models import Configuration
    with transaction.atomic():
        row, _ = Configuration.objects.select_for_update().get_or_create(key=KEY, defaults={'value': {'keys': []}})
        current = row.value.get('keys', []) if isinstance(row.value, dict) else []
        Configuration.objects.filter(pk=row.pk).update(value={'keys': change(list(current))})


def issue(user, label):
    """A new key for one BoS user; the token is returned once and only its hash is kept."""
    from boss_project.policy import Policy
    Policy.for_user(user)     # refuses users without exactly one BoS role, archived or inactive
    token = PREFIX + secrets.token_urlsafe(32)
    entry = {'id': secrets.token_hex(4), 'sha256': _digest(token), 'user_id': user.pk,
             'label': (label or '').strip()[:80], 'created_at': timezone.now().isoformat()}
    _store(lambda current: current + [entry])
    return token, entry


def revoke(key_id):
    found = []

    def drop(current):
        found.extend(k for k in current if k.get('id') == key_id)
        return [k for k in current if k.get('id') != key_id]
    _store(drop)
    return bool(found)


def summary():
    """What «Підключення» may show the CEO: whether MCP is on and which keys exist — never the hashes."""
    from django.contrib.auth import get_user_model
    entries = keys()
    users = dict(get_user_model().objects.filter(pk__in=[k.get('user_id') for k in entries]).values_list('pk', 'username'))
    return {'enabled': bool(entries), 'path': '/mcp/',
            'keys': [{'id': k.get('id'), 'label': k.get('label', ''), 'user': users.get(k.get('user_id'), ''),
                      'created_at': k.get('created_at')} for k in entries]}


def _holder(request, entries):
    header = request.META.get('HTTP_AUTHORIZATION', '')
    if not header.startswith('Bearer '):
        return None
    digest = _digest(header[len('Bearer '):].strip())
    match = None
    for entry in entries:
        if hmac.compare_digest(entry['sha256'], digest):
            match = entry
    return match


# --- tools -------------------------------------------------------------------------------------------------

def _queries(policy):
    from erp import monitoring
    return [(k, title) for k, title, ceo in monitoring.QUERIES if policy.ceo or not ceo]


def tools(policy):
    read_only = {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False}
    return [
        {'name': 'monitoring_overview', 'title': 'Стан компанії',
         'description': 'Головні числа, що потребує уваги, плитки моніторингу (замовлення, виробництво, постачання, '
                        'гроші для керівника, доручення, джерела, наступні 14 днів) і перелік стандартних запитів.',
         'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
         'annotations': read_only},
        {'name': 'standard_query', 'title': 'Стандартний запит',
         'description': 'Таблиця за одним із готових запитів: ' +
                        '; '.join(f'{k} — {t}' for k, t in _queries(policy)) + '.',
         'inputSchema': {'type': 'object', 'additionalProperties': False, 'required': ['key'],
                         'properties': {'key': {'type': 'string', 'enum': [k for k, _ in _queries(policy)]}}},
         'annotations': read_only},
        {'name': 'order_status', 'title': 'Стан замовлення',
         'description': 'Позиції замовлення: замовлено, відвантажено, залишок, а також наступний крок словами. '
                        'Номер, наприклад ZM-0150.',
         'inputSchema': {'type': 'object', 'additionalProperties': False, 'required': ['code'],
                         'properties': {'code': {'type': 'string', 'minLength': 1, 'maxLength': 60}}},
         'annotations': read_only},
    ]


def _overview(policy, arguments):
    from erp import monitoring
    data = monitoring.build(policy)
    sources = [{'name': s['name'], 'dataset': s['dataset_label'], 'freshness': s['freshness_label'],
                'last_sync_at': s['last_sync_at']} for s in data['sources']]
    return {'as_of': data['as_of'], 'numbers': data['numbers'], 'attention': data['attention'] + data['source_attention'],
            'bento': data['bento'], 'sources': sources, 'queries': data['queries']}


def _query(policy, arguments):
    from erp import monitoring
    key = arguments.get('key')
    if key not in dict(_queries(policy)):
        raise LookupError('Невідомий або недоступний запит.')
    table = monitoring.query(policy, key)
    return {'as_of': table['as_of'], 'key': table['key'], 'title': table['title'], 'columns': table['columns'],
            'rows': [r['cells'] for r in table['rows']], 'total': table['total']}


def _order(policy, arguments):
    from erp import experience
    from erp.balances import sales_open
    from erp.models import SalesOrder
    code = str(arguments.get('code', '')).strip()
    order = policy.queryset(SalesOrder).select_related('customer').filter(code=code).first()
    if order is None:
        raise LookupError('Замовлення не знайдено або воно недоступне.')
    lines = []
    for line in policy.filter_queryset(order.lines.all()).select_related('item').order_by('pk'):
        left = sales_open(line)
        row = {'item': line.item.name, 'unit': line.item.unit, 'ordered': str(line.quantity.normalize()),
               'shipped': str(line.shipped.normalize()), 'open': str(left.normalize())}
        if policy.ceo:
            row['price'] = str(line.price)
        lines.append(row)
    step = experience.next_step(order, policy)
    out = {'code': order.code, 'customer': order.customer.name, 'status': STATUS.get(order.status, order.status),
           'due_date': order.due_date.isoformat(), 'lines': lines,
           'next_step': {'title': step['title'], 'why': step['why']} if step else None}
    if policy.ceo:
        out['currency'] = order.currency
    return out


CALLS = {'monitoring_overview': _overview, 'standard_query': _query, 'order_status': _order}


# --- JSON-RPC over HTTP ------------------------------------------------------------------------------------

def _reply(message_id, result=None, error=None):
    body = {'jsonrpc': '2.0', 'id': message_id}
    body.update({'error': error} if error else {'result': result})
    return JsonResponse(body, encoder=DjangoJSONEncoder, json_dumps_params={'ensure_ascii': False})


def _fail(message_id, code, text):
    return _reply(message_id, error={'code': code, 'message': text})


def _call(policy, params):
    name, arguments = params.get('name'), params.get('arguments') or {}
    if name not in CALLS or not isinstance(arguments, dict):
        return None
    try:
        data = CALLS[name](policy, arguments)
    except (LookupError, PermissionError, ValueError) as exc:
        return {'content': [{'type': 'text', 'text': str(exc)}], 'isError': True}
    text = json.dumps(data, cls=DjangoJSONEncoder, ensure_ascii=False)
    return {'content': [{'type': 'text', 'text': text}], 'structuredContent': json.loads(text), 'isError': False}


@csrf_exempt
def endpoint(request):
    entries = keys()
    if not entries:
        return JsonResponse({'error': 'Доступ через MCP вимкнено.'}, status=404)
    if request.META.get('HTTP_ORIGIN'):
        return JsonResponse({'error': 'Запити з браузера до MCP не приймаються.'}, status=403)
    if request.method != 'POST':
        response = HttpResponse(status=405)
        response['Allow'] = 'POST'
        return response
    entry = _holder(request, entries)
    if entry is None:
        response = JsonResponse({'error': 'Потрібен чинний ключ доступу MCP.'}, status=401)
        response['WWW-Authenticate'] = 'Bearer'
        return response
    from django.contrib.auth import get_user_model
    from boss_project.identity import IdentityDenied
    from boss_project.policy import Policy
    try:
        policy = Policy.for_user(get_user_model().objects.get(pk=entry['user_id']))
    except (IdentityDenied, get_user_model().DoesNotExist):
        return JsonResponse({'error': 'Користувач ключа більше не має доступу до BoS.'}, status=403)
    try:
        size = int(request.META.get('CONTENT_LENGTH') or 0)
    except ValueError:
        size = MAX_BODY + 1
    if size > MAX_BODY:
        return _fail(None, -32600, 'Запит завеликий.')
    try:
        message = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return _fail(None, -32700, 'Некоректний JSON.')
    if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
        return _fail(message.get('id') if isinstance(message, dict) else None, -32600, 'Очікується один запит JSON-RPC 2.0.')
    if 'id' not in message:
        return HttpResponse(status=202)       # notifications (e.g. notifications/initialized) need no answer
    method, params, message_id = message['method'], message.get('params') or {}, message['id']
    if not isinstance(params, dict):
        return _fail(message_id, -32602, 'Некоректні параметри.')
    if method == 'initialize':
        from boss_project.version import VERSION
        asked = params.get('protocolVersion')
        return _reply(message_id, {'protocolVersion': asked if asked in VERSIONS else VERSIONS[0],
                                   'capabilities': {'tools': {'listChanged': False}},
                                   'serverInfo': {'name': 'bos', 'title': 'BoS', 'version': VERSION},
                                   'instructions': INSTRUCTIONS})
    if method == 'ping':
        return _reply(message_id, {})
    if method == 'tools/list':
        return _reply(message_id, {'tools': tools(policy)})
    if method == 'tools/call':
        try:
            result = _call(policy, params)
        except Exception:   # a client gets a protocol error, never a server page or a traceback
            LOG.exception('MCP tools/call failed')
            return _fail(message_id, -32603, 'Внутрішня помилка сервера.')
        if result is None:
            return _fail(message_id, -32602, 'Невідомий інструмент або некоректні аргументи.')
        return _reply(message_id, result)
    return _fail(message_id, -32601, 'Метод не підтримується.')
