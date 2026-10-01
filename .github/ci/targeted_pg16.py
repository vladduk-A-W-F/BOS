"""Один адресний прогін Django-тестів на одноразовому PostgreSQL 16. Без повторів і full suite."""
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABEL = re.compile(r'[a-z_][a-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+')
MAX_LABELS = 5
RUNNER = r'''
import os, sys
import django
django.setup()
from django.db import connection
from django.test.runner import DiscoverRunner

class PG16Runner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        config = super().setup_databases(**kwargs)
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_setting('server_version_num')")
            name, version = cursor.fetchone()
        print(f'BOS_TEST_DATABASE {connection.vendor} {name} {version}', flush=True)
        # Без DB-тестів Django не створює test_-базу; тоді перевіряємо лише СУБД і версію.
        if (connection.vendor != 'postgresql' or not 160000 <= int(version) < 170000
                or (config and name != 'test_' + os.environ['BOS_TEST_DB_NAME'])):
            raise RuntimeError('Неочікувана тестова БД або версія PostgreSQL')
        return config

raise SystemExit(bool(PG16Runner(verbosity=2, interactive=False).run_tests(sys.argv[1:])))
'''


def main(raw):
    labels = raw.split()
    if not labels or len(labels) > MAX_LABELS or not all(LABEL.fullmatch(x) for x in labels):
        print(f'Потрібно 1–{MAX_LABELS} міток виду app.test_module[.Class[.method]]; full suite заборонено.')
        return 2
    spec = importlib.util.spec_from_file_location('bos_verify', ROOT / 'scripts/verify.py')
    verify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify)
    with tempfile.TemporaryDirectory(prefix='bos-targeted-') as directory:
        work = Path(directory)
        (work / 'media').mkdir()
        (work / 'source').mkdir()
        with verify.database('postgres', work) as env:
            for key in ('GITHUB_TOKEN', 'GH_TOKEN'):
                env.pop(key, None)
            env['DJANGO_SETTINGS_MODULE'] = 'verification_settings'
            return subprocess.run([sys.executable, '-B', '-c', RUNNER, *labels], cwd=ROOT, env=env,
                                  timeout=1200).returncode


if __name__ == '__main__':
    sys.exit(main(os.environ.get('BOS_TEST_LABELS', '')))
