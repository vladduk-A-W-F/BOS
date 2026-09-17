"""Fail-closed server configuration; no database calls or filesystem writes."""
import ipaddress
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit
import uuid

from django.core.exceptions import ImproperlyConfigured


def refuse(field):
    # Never include configuration values, paths, credentials or parser errors.
    error = ImproperlyConfigured('Сервер BoS не запущено: перевірте ' + field + '.')
    error.bos_controlled_configuration_error = True
    raise error


def _secret(value):
    if (not isinstance(value, str) or len(value) < 50 or len(set(value)) < 12
            or not value.isascii() or any(c.isspace() for c in value)
            or any(marker in value.lower() for marker in
                   ('local-demo', 'synthetic-verification', 'django-insecure'))):
        refuse('BOS_SECRET_KEY')
    return value


def _absolute(value, field):
    if (not isinstance(value, str) or not value or '\x00' in value
            or value.startswith(('//', '\\\\'))):
        refuse(field)
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        refuse(field)
    # Do not resolve a symlink and then mistake its destination for authorization.
    for item in (*reversed(path.parents), path):
        try:
            if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
                refuse(field)
            if item != path and item.exists() and not item.is_dir():
                refuse(field)
        except OSError:
            refuse(field)
    return path


def _within(path, parent):
    return path != parent and parent in path.parents


def _locations(root, database, media, static_root, source_root):
    root = _absolute(str(root), 'BOS_INSTALLATION_ROOT')
    source_root = Path(source_root).resolve()
    if root == source_root or _within(root, source_root) or _within(source_root, root):
        refuse('BOS_INSTALLATION_ROOT')
    try:
        mode = root.stat().st_mode
        if (not stat.S_ISDIR(mode) or (os.name == 'posix'
                and (mode & 0o077 or mode & 0o500 != 0o500))):
            refuse('BOS_INSTALLATION_ROOT')
    except OSError:
        refuse('BOS_INSTALLATION_ROOT')
    database = _absolute(str(database), 'BOS_DATABASE_PATH')
    media = _absolute(str(media), 'BOS_MEDIA_ROOT')
    static_root = _absolute(str(static_root), 'STATIC_ROOT')
    if any(not _within(p, root) for p in (database, media, static_root)):
        refuse('шляхи окремої інсталяції')
    if (media == static_root or _within(media, static_root) or _within(static_root, media)
            or database in (media, static_root) or _within(database, media)
            or _within(database, static_root) or _within(media, database)
            or _within(static_root, database)):
        refuse('відокремлення бази, приватних файлів і статики')
    for directory, field in ((media, 'BOS_MEDIA_ROOT'), (static_root, 'STATIC_ROOT')):
        if directory.exists() and not directory.is_dir():
            refuse(field)
    if database.exists():
        metadata = database.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            refuse('BOS_DATABASE_PATH')
    return root, database, media, static_root


def _origin_and_hosts(origin, hosts):
    try:
        parsed = urlsplit(origin)
        hostname = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError):
        refuse('BOS_PUBLIC_ORIGIN')
    if (parsed.scheme != 'https' or not hostname or parsed.username is not None
            or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
            or not isinstance(hosts, (list, tuple)) or len(hosts) != 1):
        refuse('BOS_PUBLIC_ORIGIN / BOS_ALLOWED_HOSTS')
    # One canonical hostname per isolated installation, explicit optional TLS port.
    if (not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', hostname)
            or any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-')
                   for label in hostname.split('.')) or len(hostname) > 253
            or hosts[0] != hostname or port == 0):
        refuse('BOS_PUBLIC_ORIGIN / BOS_ALLOWED_HOSTS')
    canonical = 'https://' + hostname + ((':' + str(port)) if port is not None else '')
    if origin != canonical:
        refuse('BOS_PUBLIC_ORIGIN')
    return origin, [hostname]


def _proxy_peers(peers):
    if not isinstance(peers, (list, tuple)) or not peers:
        refuse('BOS_TRUSTED_PROXY_IPS')
    result = []
    for value in peers:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            refuse('BOS_TRUSTED_PROXY_IPS')
        if address.is_unspecified or address.is_multicast or str(address) != value:
            refuse('BOS_TRUSTED_PROXY_IPS')
        result.append(value)
    if len(set(result)) != len(result):
        refuse('BOS_TRUSTED_PROXY_IPS')
    return tuple(result)


def from_environment(source_root, environ=None):
    env = os.environ if environ is None else environ
    if env.get('BOS_DATA_MODE') != 'working':
        refuse('BOS_DATA_MODE=working')
    if env.get('BOS_DATABASE_ENGINE') != 'sqlite3':
        refuse('BOS_DATABASE_ENGINE: перевірений профіль sqlite3')
    try:
        installation_id = str(uuid.UUID(env.get('BOS_INSTALLATION_ID', '')))
    except (ValueError, AttributeError):
        refuse('BOS_INSTALLATION_ID')
    if env.get('BOS_INSTALLATION_ID') != installation_id:
        refuse('BOS_INSTALLATION_ID')
    root = _absolute(env.get('BOS_INSTALLATION_ROOT'), 'BOS_INSTALLATION_ROOT')
    database = _absolute(env.get('BOS_DATABASE_PATH'), 'BOS_DATABASE_PATH')
    media = _absolute(env.get('BOS_MEDIA_ROOT'), 'BOS_MEDIA_ROOT')
    root, database, media, static_root = _locations(root, database, media, root / 'static', source_root)
    origin, hosts = _origin_and_hosts(env.get('BOS_PUBLIC_ORIGIN', ''), env.get('BOS_ALLOWED_HOSTS', '').split(','))
    peers = _proxy_peers(env.get('BOS_TRUSTED_PROXY_IPS', '').split(','))
    return dict(root=root, database=database, media=media, static_root=static_root,
                origin=origin, hosts=hosts, peers=peers, secret=_secret(env.get('BOS_SECRET_KEY')),
                installation_id=installation_id)


def validate_effective(settings):
    """The sole validator used immediately before Django application creation."""
    if getattr(settings, 'BOS_DATA_MODE', None) != 'working' or settings.DEBUG is not False:
        refuse('робочий режим / DEBUG')
    from boss_project.server_logging import logging_configuration
    if settings.LOGGING != logging_configuration():
        refuse('LOGGING')
    _secret(settings.SECRET_KEY)
    try:
        installation_id = str(uuid.UUID(settings.BOS_INSTALLATION_ID))
    except (ValueError, AttributeError, TypeError):
        refuse('BOS_INSTALLATION_ID')
    if (settings.BOS_INSTALLATION_ID != installation_id
            or settings.SESSION_COOKIE_NAME != 'bos_session_' + installation_id.replace('-', '')
            or settings.CSRF_COOKIE_NAME != 'csrftoken'):
        refuse('ідентифікатор інсталяції та назви session/CSRF cookies')
    if getattr(settings, 'SECRET_KEY_FALLBACKS', []):
        refuse('SECRET_KEY_FALLBACKS')
    if (set(settings.DATABASES) != {'default'}
            or settings.DATABASES['default'].get('ENGINE') != 'django.db.backends.sqlite3'):
        refuse('DATABASES')
    _locations(settings.BOS_INSTALLATION_ROOT, settings.DATABASES['default'].get('NAME', ''),
               settings.MEDIA_ROOT, settings.STATIC_ROOT, settings.BASE_DIR)
    origin, hosts = _origin_and_hosts(settings.BOS_PUBLIC_ORIGIN, settings.ALLOWED_HOSTS)
    _proxy_peers(settings.BOS_TRUSTED_PROXY_IPS)
    expected = {
        'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
        'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    }
    if any(settings.REST_FRAMEWORK.get(key) != value for key, value in expected.items()):
        refuse('REST_FRAMEWORK: автентифікація та права')
    if list(settings.MIDDLEWARE) != list(SERVER_MIDDLEWARE):
        refuse('MIDDLEWARE: серверний захист і права BoS')
    for key in ('SESSION_COOKIE_SECURE', 'SESSION_COOKIE_HTTPONLY', 'CSRF_COOKIE_SECURE',
                'SECURE_SSL_REDIRECT', 'SECURE_CONTENT_TYPE_NOSNIFF'):
        if getattr(settings, key, None) is not True:
            refuse(key)
    if (settings.SECURE_PROXY_SSL_HEADER != ('HTTP_X_FORWARDED_PROTO', 'https')
            or settings.SECURE_SSL_HOST != origin.removeprefix('https://')
            or settings.USE_X_FORWARDED_HOST or settings.USE_X_FORWARDED_PORT
            or settings.CSRF_TRUSTED_ORIGINS != [origin]
            or settings.SESSION_COOKIE_SAMESITE != 'Lax' or settings.CSRF_COOKIE_SAMESITE != 'Lax'
            or settings.SESSION_COOKIE_DOMAIN is not None or settings.CSRF_COOKIE_DOMAIN is not None
            or settings.X_FRAME_OPTIONS != 'DENY'):
        refuse('TLS, proxy, cookies або CSRF')


SERVER_MIDDLEWARE = (
    'boss_project.server_logging.CorrelationLoggingMiddleware',
    'boss_project.server_config.TrustedProxyMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'operations.middleware.LocalRoleGuard',
)


class TrustedProxyMiddleware:
    """The upstream accepts only configured exact peers and single proxy values."""
    def __init__(self, get_response):
        from django.conf import settings
        self.get_response = get_response
        self.peers = _proxy_peers(settings.BOS_TRUSTED_PROXY_IPS)

    def __call__(self, request):
        from django.http import JsonResponse
        peer = request.META.get('REMOTE_ADDR', '')
        proto = request.META.get('HTTP_X_FORWARDED_PROTO', '')
        client = request.META.get('HTTP_X_FORWARDED_FOR', '')
        for name in list(request.META):
            if name.startswith('HTTP_X_FORWARDED_') or name == 'HTTP_FORWARDED':
                del request.META[name]
        if peer not in self.peers:
            return JsonResponse({'error': 'Пряме підключення до сервера BoS заборонено.'}, status=403)
        try:
            address = ipaddress.ip_address(client)
        except ValueError:
            return JsonResponse({'error': 'Некоректні параметри проксі.'}, status=400)
        if proto not in ('http', 'https') or str(address) != client or address.is_unspecified or address.is_multicast:
            return JsonResponse({'error': 'Некоректні параметри проксі.'}, status=400)
        request.META['BOS_PROXY_PEER'] = peer
        request.META['REMOTE_ADDR'] = client
        request.META['HTTP_X_FORWARDED_PROTO'] = proto
        from boss_project.import_request_body import capture_import_body
        rejected = capture_import_body(request)
        if rejected is not None:
            return rejected
        return self.get_response(request)
