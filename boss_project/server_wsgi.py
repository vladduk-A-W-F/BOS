"""Supported server entrypoint. Configuration is checked before Django setup."""
import os

from boss_project.server_config import refuse, validate_effective
from boss_project.server_logging import report_configuration_failure
from django.core.exceptions import ImproperlyConfigured

try:
    if os.environ.get('DJANGO_SETTINGS_MODULE') not in (None, 'server_settings'):
        refuse('DJANGO_SETTINGS_MODULE=server_settings')
    os.environ['DJANGO_SETTINGS_MODULE'] = 'server_settings'

    from django.conf import settings

    validate_effective(settings)

    from django.core.wsgi import get_wsgi_application

    application = get_wsgi_application()
    validate_effective(settings)
except ImproperlyConfigured:
    report_configuration_failure()
    raise
