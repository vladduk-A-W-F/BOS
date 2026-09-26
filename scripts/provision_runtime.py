"""Actual offline application provisioning in installer-owned NEW bundles.

No server or proxy is started. HTTPS acceptance is separately reported incomplete.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys


def provision_install(*, installer, target, registry, source_root, origin, wheelhouse, resume=None):
    wheelhouse = installer.safe_path(wheelhouse, must_exist=True)
    if not wheelhouse.is_dir():
        installer.refuse('Offline wheelhouse має бути наявним локальним каталогом.')
    preliminary = installer.prepare_install(target=target, registry=registry, source_root=source_root,
        origin=origin, resume=resume)
    owner = installer.InstallerRegistry(registry)
    target, source_root, wheelhouse = map(Path, (target, source_root, wheelhouse))
    installer.safe_path(wheelhouse, must_exist=True)
    with owner.lock():
        record = owner.get(preliminary['installation_id'])
        installer.inspect_partial(record)
        source = installer.source_identity(source_root)
        if source != record['source'] or not source.get('full_code_package_verified'):
            installer.refuse('Для runtime потрібен повний незмінний manifest пакета коду.')
        package = json.loads((source_root / 'BOS_PACKAGE.json').read_text(encoding='utf-8'))
        if not (source_root / 'requirements-server.txt').is_file():
            installer.refuse('У пакеті відсутні закріплені server requirements.')
        pins = {}
        for requirements in ('requirements.txt', 'requirements-server.txt'):
            for raw in (source_root / requirements).read_text().splitlines():
                line = raw.strip()
                if not line or line.startswith('#') or line == '-r requirements.txt':
                    continue
                match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)', line)
                if not match:
                    installer.refuse('Усі runtime залежності повинні мати точні версії без URL/options.')
                if match[1].lower() in pins and pins[match[1].lower()] != match[2]:
                    installer.refuse('Версії залежностей суперечать одна одній.')
                pins[match[1].lower()] = match[2]
        if pins.get('waitress') != '3.0.2':
            installer.refuse('Очікується перевірена точна версія waitress 3.0.2.')
        runtime = record.setdefault('runtime', {})
        trees = runtime.setdefault('owned_trees', {})
        release_relative = 'releases/' + source['source_sha256']
        release = target / release_relative
        venv = target / 'venv'
        command_results = []
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('BOS_', 'PIP_', 'ANTHROPIC', 'OPENAI'))
               and key not in ('PYTHONPATH', 'PYTHONHOME', 'DJANGO_SETTINGS_MODULE')}
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
                   PIP_NO_INDEX='1', PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK='1')

        def owned_tree(relative):
            path = target / relative
            if relative not in trees:
                if path.exists():
                    installer.refuse('Runtime каталог існує без попереднього права створення.')
                path.mkdir(mode=0o700)
                trees[relative] = installer.identity(path)
                owner.update(record)
            if installer.identity(path) != trees[relative]:
                installer.refuse('Runtime каталог замінено.')
            return path

        def run(name, command, *, settings_env=None, timeout=180):
            installer.inspect_partial(record)
            child_env = dict(env)
            if settings_env:
                child_env.update(settings_env)
            completed = subprocess.run([str(arg) for arg in command], cwd=release,
                env=child_env, capture_output=True, text=True, encoding='utf-8', timeout=timeout)
            # Logs are private diagnostic metadata; no secret is put in argv.
            logs = owned_tree('runtime-logs')
            counter = len(list(logs.glob(name + '-*.log'))) + 1
            log = logs / (name + '-' + str(counter) + '.log')
            output = completed.stdout + '\n--- STDERR ---\n' + completed.stderr
            if record['secret'] in output:
                output = '[Секрет вилучено з діагностичного виводу]\n'
            installer.new_file(log, output.encode('utf-8'))
            fact = {'step': name, 'returncode': completed.returncode,
                    'stdout_sha256': hashlib.sha256(completed.stdout.encode()).hexdigest(),
                    'stderr_sha256': hashlib.sha256(completed.stderr.encode()).hexdigest(),
                    'log': log.relative_to(target).as_posix()}
            command_results.append(fact)
            runtime.setdefault('commands', []).append(fact)
            owner.update(record)
            if completed.returncode:
                installer.refuse('Крок ' + name + ' не виконано; власну незавершену інсталяцію збережено.')
            return completed.stdout

        owned_tree(release_relative)
        expected_files = dict(package['files'])
        expected_files['BOS_PACKAGE.json'] = hashlib.sha256((source_root / 'BOS_PACKAGE.json').read_bytes()).hexdigest()
        actual = {path.relative_to(release).as_posix() for path in release.rglob('*') if path.is_file()}
        if actual - set(expected_files):
            installer.refuse('Частковий release містить невідомі файли.')
        for relative, checksum in expected_files.items():
            source_file, destination = source_root / relative, release / relative
            if destination.exists():
                if hashlib.sha256(destination.read_bytes()).hexdigest() != checksum:
                    installer.refuse('Раніше скопійований release змінено.')
                continue
            parent = release
            for part in Path(relative).parent.parts:
                parent = parent / part
                if not parent.exists(): parent.mkdir(mode=0o700)
            installer.new_file(destination, source_file.read_bytes())
        if installer.source_identity(release) != source:
            installer.refuse('Повний SHA скопійованого release не збігається.')
        owned_tree('venv')
        run('venv', [sys.executable, '-I', '-m', 'venv', '--copies', str(venv)])
        python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        run('offline-pip', [python, '-I', '-m', 'pip', 'install', '--no-index', '--no-deps', '--only-binary=:all:', '--find-links', wheelhouse,
                           '--disable-pip-version-check', '-r', release / 'requirements-server.txt'])
        run('pip-check', [python, '-I', '-m', 'pip', 'check'])
        pin_probe = "import importlib.metadata as m,json,sys; expected=json.loads(sys.argv[1]); assert sys.prefix!=sys.base_prefix; actual={k:m.version(k) for k in expected}; assert actual==expected,(actual,expected); print(json.dumps({'prefix':sys.prefix,'base_prefix':sys.base_prefix,'versions':actual}))"
        probe = json.loads(run('pinned-runtime', [python, '-I', '-c', pin_probe, json.dumps(pins, sort_keys=True)]))
        runtime['pinned_dependencies'] = probe
        owner.update(record)
        config = json.loads((target / 'config/server.json').read_text(encoding='utf-8'))
        db = target / 'state/data/bos.sqlite3'
        if not runtime.get('database'):
            if db.exists(): installer.refuse('База існує без попереднього права інсталятора.')
            installer.new_file(db, b'')
            runtime['database'] = installer.identity(db)
            owner.update(record)
        run('server-config', [python, '-c', 'from django.conf import settings; from boss_project.server_config import validate_effective; validate_effective(settings); print("canonical_server_config_valid")'], settings_env=config)
        run('django-check', [python, 'manage.py', 'check', '--settings=server_settings'], settings_env=config)
        run('migrate', [python, 'manage.py', 'migrate', '--noinput', '--settings=server_settings'], settings_env=config)
        # This pre-created empty directory now belongs to collectstatic for this installation.
        trees['state/static'] = installer.identity(target / 'state/static')
        owner.update(record)
        run('collectstatic', [python, 'manage.py', 'collectstatic', '--noinput', '--settings=server_settings'], settings_env=config)
        facts_code = """import django,json; django.setup()
from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.conf import settings
from pathlib import Path
executor=MigrationExecutor(connection); assert not executor.migration_plan(executor.loader.graph.leaf_nodes())
labels={'operations','erp','finance','employees','branches','tasks','ai_assistant'}
counts={m._meta.label_lower:m.objects.count() for m in apps.get_models() if m._meta.app_label in labels}
assert not any(counts.values()),counts
assert settings.BOS_DATA_MODE=='working' and settings.DEBUG is False
assert settings.DATABASES['default']['NAME']==Path(settings.BOS_INSTALLATION_ROOT)/'data/bos.sqlite3'
assert (Path(settings.STATIC_ROOT)/'admin/css/base.css').is_file()
print(json.dumps({'vendor':connection.vendor,'business_rows':counts,'pending_migrations':0,'admin_static':True,'mode':settings.BOS_DATA_MODE}))
"""
        facts = json.loads(run('installation-proof', [python, '-c', facts_code], settings_env=config))
        if installer.source_identity(source_root) != source or installer.source_identity(release) != source:
            installer.refuse('Джерело або release змінились під час встановлення.')
        runtime.update(application_provisioned=True, installation_proof=facts, release=release_relative)
        owner.update(record)
        installer.inspect_partial(record)
        return {'complete': False, 'application_provisioned': True, 'exit_code': 2,
                'installation_id': record['id'], 'version': source['version'], 'source_sha256': source['source_sha256'],
                'checks': {'pinned_venv': 'ПРОЙДЕНО', 'canonical_config': 'ПРОЙДЕНО',
                           'actual_migrations': 'ПРОЙДЕНО', 'collectstatic': 'ПРОЙДЕНО',
                           'business_empty': 'ПРОЙДЕНО', 'wsgi_runtime': 'НЕ ЗАПУЩЕНО',
                           'tls_proxy': 'НЕ ЗАПУЩЕНО', 'http_health': 'НЕ ЗАПУЩЕНО'},
                'commands': command_results, 'proof': facts, 'runtime': probe}
