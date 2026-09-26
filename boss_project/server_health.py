"""Public process/dependency status. No private values and no repair or writes."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import stat

from django.conf import settings
from django.db.migrations.loader import MigrationLoader
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


def _response(status, code=200):
    result = JsonResponse({'status': status}, status=code)
    result['Cache-Control'] = 'no-store'
    return result


def _get_only(request):
    if request.method != 'GET':
        result = _response('method_not_allowed', 405)
        result['Allow'] = 'GET'
        return result
    return None


@csrf_exempt
def liveness(request):
    denied = _get_only(request)
    return denied if denied is not None else _response('alive')


def _database_ready(database):
    # mode=ro never creates a missing DB. Health does not use Django's default
    # read-write connection, migrations, ORM saves or a probe INSERT/DELETE.
    if not database.is_file():
        return False
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=0.2)) as reader:
        reader.execute('PRAGMA query_only=ON')
        if reader.execute('SELECT 1').fetchone() != (1,):
            return False
        applied = set(reader.execute('SELECT app, name FROM django_migrations').fetchall())
        required = set(MigrationLoader(None, ignore_no_migrations=True).graph.nodes)
        if not required <= applied:
            return False
        # A real application-table SELECT catches an uninitialized/corrupt core
        # table; complete business reconciliation remains a separate gate.
        reader.execute('SELECT key FROM operations_configuration LIMIT 1').fetchall()
    return True


def _media_ready(media):
    info = media.stat()
    if not stat.S_ISDIR(info.st_mode):
        return False
    # Check mode bits as well as current account access; tests may run as root.
    if os.name == 'posix' and stat.S_IMODE(info.st_mode) & 0o700 != 0o700:
        return False
    if not os.access(media, os.R_OK | os.W_OK | os.X_OK):
        return False
    with os.scandir(media) as entries:
        next(entries, None)  # Actual readable-directory operation, no filename log.
    return True


@csrf_exempt
def readiness(request):
    denied = _get_only(request)
    if denied is not None:
        return denied
    try:
        if (getattr(settings, 'BOS_DATA_MODE', None) != 'working'
                or not getattr(settings, 'BOS_INSTALLATION_ROOT', None)
                or set(settings.DATABASES) != {'default'}
                or settings.DATABASES['default'].get('ENGINE') != 'django.db.backends.sqlite3'):
            return _response('unavailable', 503)
        from boss_project.server_config import _locations
        _, database, media, _ = _locations(settings.BOS_INSTALLATION_ROOT,
            settings.DATABASES['default']['NAME'], settings.MEDIA_ROOT, settings.STATIC_ROOT, settings.BASE_DIR)
        ready = _database_ready(database) and _media_ready(media)
    except Exception:
        # Expose no exception text, SQL, path, migration name or configuration.
        ready = False
    if not ready:
        from boss_project.server_logging import emit
        emit('dependency_unavailable', 503)
    return _response('ready' if ready else 'unavailable', 200 if ready else 503)
