"""Owned detached server entry point. Never launches an existing installation."""
import os
from pathlib import Path
import sys
from review_process import child_gate
from review_secrets import ROOT

root = ROOT
sys.path.insert(0, str(root / 'source'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'review_settings'
os.environ.pop('BOS_REVIEW_SEED_MODE', None)
child_gate(root)  # nonce + actual PID/creation time/exe, verified before any Django import
from django.core.management import execute_from_command_line
execute_from_command_line([str(root / 'source/manage.py'), 'runserver', '127.0.0.1:8876', '--noreload'])
