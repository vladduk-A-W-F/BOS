"""Explicit isolated server settings. No local launcher settings are modified."""
from copy import deepcopy

from demo_settings import (
    INSTALLED_APPS as SHARED_APPS, TEMPLATES as SHARED_TEMPLATES,
    DEFAULT_AUTO_FIELD, LANGUAGE_CODE, TIME_ZONE, USE_TZ, BASE_DIR,
)
from boss_project.server_config import from_environment, SERVER_MIDDLEWARE
from boss_project.server_logging import logging_configuration

_config = from_environment(BASE_DIR)
BOS_INSTALLATION_ROOT = _config['root']
BOS_INSTALLATION_ID = _config['installation_id']
BOS_DATA_MODE = 'working'
BOS_PUBLIC_ORIGIN = _config['origin']
BOS_TRUSTED_PROXY_IPS = _config['peers']
SECRET_KEY = _config['secret']
SECRET_KEY_FALLBACKS = []
DEBUG = False
ALLOWED_HOSTS = _config['hosts']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': _config['database']}}
MEDIA_ROOT = _config['media']
MEDIA_URL = '/media/'
STATIC_ROOT = _config['static_root']
STATIC_URL = '/static/'
INSTALLED_APPS = list(SHARED_APPS)
TEMPLATES = deepcopy(SHARED_TEMPLATES)
ROOT_URLCONF = 'boss_project.server_urls'
WSGI_APPLICATION = 'boss_project.server_wsgi.application'
MIDDLEWARE = list(SERVER_MIDDLEWARE)
REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
}
SESSION_COOKIE_NAME = 'bos_session_' + BOS_INSTALLATION_ID.replace('-', '')
CSRF_COOKIE_NAME = 'csrftoken'  # Existing frontend reads this exact cookie name.
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_DOMAIN = None
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_DOMAIN = None
CSRF_TRUSTED_ORIGINS = [BOS_PUBLIC_ORIGIN]
SECURE_SSL_REDIRECT = True
SECURE_SSL_HOST = BOS_PUBLIC_ORIGIN.removeprefix('https://')
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = False
USE_X_FORWARDED_PORT = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
X_FRAME_OPTIONS = 'DENY'
ANTHROPIC_API_KEY = ''
LOGGING = logging_configuration()
