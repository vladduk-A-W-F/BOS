"""Server logs use an allowlist, never a redaction pass over private payloads."""
from contextvars import ContextVar
import json
import logging
import re
import sys
import uuid

from boss_project.version import VERSION

_CORRELATION = ContextVar('bos_server_correlation', default=None)
_ID = re.compile(r'[0-9a-f]{32}\Z')
_EVENTS = frozenset({'request', 'application_error', 'security_rejection',
                     'configuration_refused', 'dependency_unavailable', 'application_log'})


def correlation_id(record=None):
    value = _CORRELATION.get()
    if value is None and record is not None:
        from django.http import HttpRequest
        request = getattr(record, 'request', None)
        if isinstance(request, HttpRequest):
            # Django emits some status logs after outer middleware returns. Read
            # only our server-issued field, never META, headers, body or query.
            value = request.__dict__.get('_bos_server_correlation_id')
    return value if isinstance(value, str) and _ID.fullmatch(value) else uuid.uuid4().hex


class SafeJSONFormatter(logging.Formatter):
    def format(self, record):
        # Do not call super().format(), getMessage(), repr(args), formatException
        # or inspect private request fields: they contain passwords, bytes or paths.
        event = getattr(record, 'bos_event', '')
        if not isinstance(event, str) or event not in _EVENTS:
            event = ('application_error' if record.levelno >= logging.ERROR else
                     'security_rejection' if record.levelno >= logging.WARNING else 'application_log')
        status = getattr(record, 'status_code', None)
        if type(status) is not int or not 100 <= status <= 599:
            status = 500 if record.levelno >= logging.ERROR else 400 if record.levelno >= logging.WARNING else 200
        return json.dumps({'event': event, 'status': status, 'version': VERSION,
                           'correlation_id': correlation_id(record)}, separators=(',', ':'))


def logging_configuration():
    """One canonical configuration; raw Django messages/tracebacks are discarded."""
    return {'version': 1, 'disable_existing_loggers': True,
        'formatters': {'safe_json': {'()': 'boss_project.server_logging.SafeJSONFormatter'}},
        'handlers': {'safe_console': {'class': 'logging.StreamHandler', 'stream': 'ext://sys.stderr',
            'formatter': 'safe_json', 'level': 'INFO'}},
        'root': {'handlers': ['safe_console'], 'level': 'INFO'},
        'loggers': {
            'django': {'handlers': [], 'level': 'INFO', 'propagate': True},
            'django.server': {'handlers': [], 'level': 'INFO', 'propagate': True},
            'django.request': {'handlers': [], 'level': 'INFO', 'propagate': True},
            'django.security': {'handlers': [], 'level': 'INFO', 'propagate': True},
            'bos.server': {'handlers': [], 'level': 'INFO', 'propagate': True},
        }}


def emit(event, status):
    if event not in _EVENTS or type(status) is not int or not 100 <= status <= 599:
        raise ValueError('Некоректна внутрішня подія журналу BoS.')
    level = logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO
    logging.getLogger('bos.server').log(level, '', extra={'bos_event': event, 'status_code': status})


class CorrelationLoggingMiddleware:
    """Outermost: includes rejected peers, redirects and Django-generated errors."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        identity = uuid.uuid4().hex
        request.__dict__['_bos_server_correlation_id'] = identity
        token = _CORRELATION.set(identity)
        try:
            response = self.get_response(request)
            response['X-BoS-Request-ID'] = identity
            emit('request', response.status_code)
            return response
        except Exception:
            emit('application_error', 500)
            raise
        finally:
            _CORRELATION.reset(token)


def report_configuration_failure():
    """Safe standalone line even when Django settings/logging cannot initialize."""
    logger = logging.Logger('bos.configuration', level=logging.ERROR)
    logger.propagate = False
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(SafeJSONFormatter())
    logger.addHandler(handler)
    try:
        logger.error('', extra={'bos_event': 'configuration_refused', 'status_code': 503})
    finally:
        logger.removeHandler(handler)
        handler.close()
