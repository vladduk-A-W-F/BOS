"""External settings for this explicitly synthetic, loopback-only review instance."""
from demo_settings import *
from review_secrets import ROOT as REVIEW_ROOT, read_secrets

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3',
                        'NAME': REVIEW_ROOT / 'data/review.sqlite3', 'OPTIONS': {'timeout': 20}}}
MEDIA_ROOT = REVIEW_ROOT / 'media'
SECRET_KEY = read_secrets()['django_secret_key']
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
# 'demo' is used only by explicit synthetic fixture commands. The server and
# real owner login always run in 'working'; no demo-login bypass is enabled.
BOS_DATA_MODE = os.environ.get('BOS_REVIEW_SEED_MODE', 'working')
