"""Synthetic verification profile; never a production server configuration."""
from demo_settings import *
from scripts.check_support import database_config

DATABASES = {'default': database_config()}
MEDIA_ROOT = Path(os.environ['BOS_TEST_MEDIA'])
SECRET_KEY = 'synthetic-verification-only'
