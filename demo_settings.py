import os
from pathlib import Path
BASE_DIR=Path(__file__).resolve().parent
SECRET_KEY='local-demo-only'
DEBUG=False
ALLOWED_HOSTS=['testserver','localhost','127.0.0.1']
INSTALLED_APPS=['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','rest_framework','django_filters','tasks','finance','employees','ai_assistant','branches','operations','erp']
MIDDLEWARE=['django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware']
ROOT_URLCONF='boss_project.urls'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'frontend'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR/('BoS_Demo.sqlite3' if os.environ.get('BOS_DATA_MODE','demo')=='demo' else 'BoS_Working.sqlite3')}}
REST_FRAMEWORK={'DEFAULT_FILTER_BACKENDS':['django_filters.rest_framework.DjangoFilterBackend'],'DEFAULT_AUTHENTICATION_CLASSES':['rest_framework.authentication.SessionAuthentication'],'DEFAULT_PERMISSION_CLASSES':['rest_framework.permissions.IsAuthenticated']}
USE_TZ=True
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
STATIC_URL='/static/'
MEDIA_ROOT=BASE_DIR/'rehearsal-media'
MEDIA_URL='/media/'
ANTHROPIC_API_KEY=''
MIDDLEWARE = ['boss_project.demo_middleware.LocalDemoGuard'] + MIDDLEWARE

LANGUAGE_CODE='uk'
TIME_ZONE='Europe/Vienna'
BOS_DATA_MODE=os.environ.get('BOS_DATA_MODE','demo')
MIDDLEWARE += ['operations.middleware.LocalRoleGuard']
