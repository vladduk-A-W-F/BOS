"""Real HTTP login limit across independent processes on a synthetic SQLite."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path('/workspace/sites/bos-original-refined')
TMP = Path('/workspace/scratch/c7b51e996a9f/tmp')


def setup():
    sys.path.insert(0, str(ROOT))
    import django
    django.setup()
    from django.db import connection
    db_path = Path(connection.settings_dict['NAME'])
    assert db_path.name == 'synthetic.sqlite3'
    assert db_path.parent.parent == TMP
    assert db_path.parent.name.startswith('a03_rate_process_')
    return db_path.parent


def client_and_token():
    from django.conf import settings
    from django.test import Client
    client = Client(enforce_csrf_checks=True, REMOTE_ADDR='127.0.0.1')
    assert client.get('/api/auth/csrf/').status_code == 200
    return client, client.cookies[settings.CSRF_COOKIE_NAME].value


def failed_post(client, csrf):
    return client.post('/api/auth/login/', {
        'username': 'a03-rate-process', 'password': 'Synthetic-wrong-A03-password',
    }, content_type='application/json', HTTP_X_CSRFTOKEN=csrf).status_code


if '--worker' in sys.argv:
    isolated = setup()
    client, csrf = client_and_token()
    (isolated / f'ready-{os.getpid()}').touch()
    deadline = time.monotonic() + 30
    while not (isolated / 'release').exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('Worker barrier timed out')
        time.sleep(0.01)
    print(json.dumps({'pid': os.getpid(), 'status': failed_post(client, csrf)}))
    raise SystemExit(0)


with tempfile.TemporaryDirectory(prefix='a03_rate_process_', dir=TMP) as directory:
    isolated = Path(directory)
    (isolated / 'media').mkdir()
    os.environ.update({
        'DJANGO_SETTINGS_MODULE': 'verification_settings',
        'BOS_DATA_MODE': 'working',
        'BOS_VERIFY_DB': 'sqlite',
        'BOS_TEST_DB_NAME': str(isolated / 'synthetic.sqlite3'),
        'BOS_TEST_MEDIA': str(isolated / 'media'),
    })
    assert setup() == isolated
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group
    from django.core.management import call_command
    from django.db import connection
    call_command('migrate', verbosity=0)
    user = get_user_model().objects.create_user(username='a03-rate-process',
        password='Synthetic-valid-A03-password')
    user.groups.add(Group.objects.get_or_create(name='ceo')[0])
    connection.close()

    processes = [subprocess.Popen([sys.executable, '-B', __file__, '--worker'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(6)]
    try:
        deadline = time.monotonic() + 30
        while len(list(isolated.glob('ready-*'))) != len(processes):
            if time.monotonic() >= deadline or any(p.poll() is not None for p in processes):
                raise RuntimeError('Workers did not reach the start barrier')
            time.sleep(0.01)
        started = time.monotonic()
        (isolated / 'release').touch()
        output = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            if process.returncode:
                raise RuntimeError(f'Synthetic worker failed: {stderr[-1000:]}')
            output.append(json.loads(stdout))
        client, csrf = client_and_token()
        following = failed_post(client, csrf)
        elapsed = time.monotonic() - started
        statuses = [item['status'] for item in output]
        result = {
            'scope': 'new synthetic SQLite only; independent processes; real HTTP and CSRF; no mocks',
            'workers': output,
            'following_after_all_processes': following,
            'elapsed_seconds': round(elapsed, 3),
            'shared_limit_holds': statuses.count(401) == 5
                and statuses.count(429) == 1 and following == 429 and elapsed < 60,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        (TMP / 'a03_rate_process_probe_result.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()
        connection.close()
