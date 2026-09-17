"""Database bootstrap for real checks; never redirects business operations."""
import json
import os
import re
import sys
from pathlib import Path


def database_config():
    if not __debug__ or os.environ.get('PYTHONOPTIMIZE', '') not in ('', '0'):
        raise RuntimeError('Перевірки не можна запускати з вимкненими assert.')
    dependency_path = os.environ.get('BOS_TEST_DEPENDENCIES')
    if dependency_path and dependency_path not in sys.path:
        sys.path.append(dependency_path)
    backend = os.environ.get('BOS_VERIFY_DB', 'sqlite')
    if backend == 'sqlite':
        config = {'ENGINE': 'django.db.backends.sqlite3',
                  'NAME': os.environ.get('BOS_TEST_DB_NAME', ':memory:'),
                  'OPTIONS': {'timeout': 20}}
        if os.environ.get('BOS_TEST_DB_NAME') not in (None, ':memory:'):
            # Real file locking for concurrent requests; Django otherwise uses
            # shared in-memory SQLite even when the configured NAME is a file.
            config['TEST'] = {'NAME': os.environ['BOS_TEST_DB_NAME'] + '_django_test'}
        return config
    if backend != 'postgres':
        raise RuntimeError('Невідома СУБД перевірки: ' + backend)
    name = os.environ.get('BOS_TEST_DB_NAME', '')
    if os.environ.get('BOS_PG_DISPOSABLE') != '1' or not re.fullmatch(r'bos_verify_[a-f0-9]{16}', name):
        raise RuntimeError('PostgreSQL дозволений лише для створеної verify тимчасової бази.')
    return {'ENGINE': 'django.db.backends.postgresql', 'NAME': name,
            'HOST': os.environ['BOS_PGHOST'], 'PORT': os.environ.get('BOS_PGPORT', '5432'),
            'USER': os.environ['BOS_PGUSER'], 'PASSWORD': os.environ['BOS_PGPASSWORD'],
            'OPTIONS': {'connect_timeout': 5}}


def configure(settings):
    settings.DATABASES = {'default': database_config()}
    if os.environ.get('BOS_TEST_MEDIA'):
        settings.MEDIA_ROOT = Path(os.environ['BOS_TEST_MEDIA'])


def prove_database():
    from django.db import connection
    expected = 'postgresql' if os.environ.get('BOS_VERIFY_DB') == 'postgres' else 'sqlite'
    connection.ensure_connection()
    if connection.vendor != expected:
        raise RuntimeError(f'Очікувалася {expected}, фактично {connection.vendor}')
    with connection.cursor() as cursor:
        cursor.execute('SHOW server_version' if expected == 'postgresql' else 'SELECT sqlite_version()')
        version = str(cursor.fetchone()[0])
    print('BOS_DATABASE ' + json.dumps({'vendor': connection.vendor, 'version': version}))


def login_test_client(client, role='ceo', *, capabilities=()):
    """Explicit synthetic HTTP login; never authenticates an anonymous oracle.

    No Employee is created: the legacy business fixtures and assertions keep
    their original row counts. Each client is a different actual Django User.
    """
    from uuid import uuid4
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group, Permission
    if role not in ('ceo', 'manager', 'observer'):
        raise ValueError('Unknown synthetic role')
    user = get_user_model().objects.create_user(username='bos-test-' + uuid4().hex,
                                               password='synthetic-test-login-only')
    user.groups.set([Group.objects.get_or_create(name=role)[0]])
    for name in capabilities:
        user.user_permissions.add(Permission.objects.get(content_type__app_label='operations',content_type__model='document',codename=name))
    response = client.get('/api/auth/csrf/')
    assert response.status_code == 200, response.content
    response = client.post('/api/auth/login/', {'username': user.username, 'password': 'synthetic-test-login-only'},
                           content_type='application/json', HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
    assert response.status_code == 200, response.content
    assert client.session.get('_auth_user_id') == str(user.pk)
    return user
