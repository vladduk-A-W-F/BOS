"""Only the assigned user may use an explicitly isolated training installation."""
import hashlib
import os
from pathlib import Path

from django.conf import settings
from django.db import connection

from operations.models import Configuration

FIXTURE_ID = 'bos3-fasteners-uk-v1'


def enabled():
    return os.environ.get('BOS3_TRAINING_ENABLED') == '1'


def installation():
    if not enabled() or settings.BOS_DATA_MODE != 'demo':
        raise PermissionError('Навчальну установку BoS 3.0 не налаштовано.')
    if (os.environ.get('BOS3_TRAINING_PROFILE') != 'isolated-synthetic'
            or os.environ.get('BOS3_TRAINING_DB_MARKER') != FIXTURE_ID
            or connection.vendor != 'sqlite'):
        raise PermissionError('Потрібна окрема навчальна база.')
    database = Path(str(connection.settings_dict['NAME'])).resolve()
    path = str(database)
    if ('bos3-fasteners' not in database.name.lower()
            or 'online-review' in path.lower() or database.name.lower() in
            {'review.sqlite3', 'db.sqlite3', 'bos_demo.sqlite3', 'bos_working.sqlite3'}):
        raise PermissionError('Цю базу не можна використовувати для навчання.')
    marker = Configuration.objects.filter(key='bos3_fixture').values_list('value', flat=True).first()
    if not isinstance(marker, dict) or marker.get('id') != FIXTURE_ID or marker.get('synthetic') is not True:
        raise PermissionError('Навчальний набір не підтверджено.')
    try:
        manifest = Path(settings.BASE_DIR) / 'erp' / 'seed' / 'bos3_fasteners_uk_v1.json'
        manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
    except OSError as exc:
        raise PermissionError('Маніфест навчальних даних недоступний.') from exc
    if (marker.get('schema') != 1 or not isinstance(marker.get('source_map'), dict)
            or not isinstance(marker.get('hash'), str) or len(marker['hash']) != 64
            or marker['hash'] != manifest_hash
            or marker.get('installation_id') != os.environ.get('BOS3_TRAINING_INSTALLATION_ID')
            or not marker.get('installation_id')
            or marker.get('owner_username') != os.environ.get('BOS3_TRAINING_OWNER_USERNAME')
            or not marker.get('owner_username')
            or marker.get('database_identity_sha256') != hashlib.sha256(path.encode('utf-8')).hexdigest()):
        raise PermissionError('Ідентичність навчальної установки змінилася.')
    return marker


def enforce_training_identity(user):
    if not enabled():
        if Configuration.objects.filter(key='bos3_fixture').exists():
            raise PermissionError('Навчальну установку вимкнено. Перевірте її конфігурацію.')
        return
    marker = installation()
    if marker.get('owner_user_id') != user.pk or marker.get('owner_username') != user.username:
        raise PermissionError('Ця навчальна установка призначена іншому користувачу.')


def require_training(policy):
    marker = installation()
    if (marker.get('owner_user_id') != policy.actor.user_id
            or marker.get('owner_username') != policy.user.username):
        raise PermissionError('Ця навчальна установка призначена іншому користувачу.')
    return marker
