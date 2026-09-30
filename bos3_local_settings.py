"""Settings for one owner-managed, loopback-only BoS 3.0 training instance."""
import hashlib
import os
from pathlib import Path

from demo_settings import *


def required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError('Missing local BoS 3.0 setting: ' + name)
    return value


BOS3_LOCAL_ROOT = Path(required('BOS3_LOCAL_ROOT')).resolve()
BOS3_LOCAL_SOURCE = Path(required('BOS3_LOCAL_SOURCE')).resolve()
BOS3_LOCAL_DB = Path(required('BOS3_LOCAL_DB')).resolve()
BOS3_LOCAL_MEDIA = Path(required('BOS3_LOCAL_MEDIA')).resolve()
if BOS3_LOCAL_SOURCE != BASE_DIR.resolve() or BOS3_LOCAL_ROOT == BASE_DIR.resolve():
    raise RuntimeError('Local BoS 3.0 source and instance root must be separate exact paths.')
if BOS3_LOCAL_DB.parent != BOS3_LOCAL_ROOT / 'data' or BOS3_LOCAL_MEDIA != BOS3_LOCAL_ROOT / 'media':
    raise RuntimeError('Local BoS 3.0 data paths do not match the isolated instance layout.')

SECRET_KEY = required('BOS3_LOCAL_SECRET')
if len(SECRET_KEY) < 50:
    raise RuntimeError('Local BoS 3.0 secret is too short.')
DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BOS3_LOCAL_DB,
                         'OPTIONS': {'timeout': 20}}}
MEDIA_ROOT = BOS3_LOCAL_MEDIA
STATIC_ROOT = BOS3_LOCAL_ROOT / 'static'
BOS_DATA_MODE = 'demo'
BOS3_TRAINING_ENABLED = True
ANTHROPIC_API_KEY = ''

# Session cookies are host-scoped, not port-scoped. Keep this local instance's
# authentication separate from the existing review server on 127.0.0.1.
_session_scope = hashlib.sha256(str(BOS3_LOCAL_ROOT).encode('utf-8')).hexdigest()[:16]
SESSION_COOKIE_NAME = 'bos3_session_' + _session_scope
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
