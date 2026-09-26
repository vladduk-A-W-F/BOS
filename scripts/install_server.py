"""A09 draft: owned NEW installation bootstrap only; no downloads, SQL or server.

The CLI always exits nonzero until real pinned runtime and deployment stages exist.
A private, explicitly selected installer registry is the resume authority; an
installation's own marker or name alone is never accepted as ownership evidence.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
import uuid
from urllib.parse import urlsplit

FORMAT = 'BoS-install-bootstrap-1'
DIRECTORIES = ('config', 'releases', 'state', 'state/data', 'state/private', 'state/static')
UNFINISHED = ('verified_code_package', 'pinned_venv_dependencies', 'canonical_server_validation',
              'actual_schema_migration', 'actual_collectstatic', 'wsgi_runtime', 'tls_proxy', 'http_health')


class InstallRefused(ValueError):
    pass


def refuse(message):
    raise InstallRefused(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8') + b'\n'


def sha(content):
    return hashlib.sha256(content).hexdigest()


def safe_path(value, *, must_exist=False):
    text = str(value)
    path = Path(text)
    if (not path.is_absolute() or '..' in path.parts or '\x00' in text
            or text.startswith(('//', '\\\\'))):
        refuse('Потрібний абсолютний шлях без переходів до батьків або UNC.')
    for item in (*reversed(path.parents), path):
        if item.is_symlink() or bool(getattr(item, 'is_junction', lambda: False)()):
            refuse('Символічні посилання та junction в інсталяції заборонено.')
        if item != path and item.exists() and not item.is_dir():
            refuse('Батьківський шлях не є каталогом.')
    if must_exist and not path.exists():
        refuse('Потрібний наявний перевірений шлях.')
    if not path.parent.is_dir():
        refuse('Батьківський каталог має бути створений оператором.')
    return path


def identity(path):
    info = Path(path).lstat()
    return [info.st_dev, info.st_ino]


def private_regular(path):
    safe_path(path, must_exist=True)
    info = Path(path).lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or (os.name == 'posix' and stat.S_IMODE(info.st_mode) != 0o600)):
        refuse('Контрольний файл має бути окремим приватним звичайним файлом.')
    return info


def private_directory(path):
    safe_path(path, must_exist=True)
    info = Path(path).lstat()
    if not stat.S_ISDIR(info.st_mode) or (os.name == 'posix' and stat.S_IMODE(info.st_mode) != 0o700):
        refuse('Каталог інсталяції має бути приватним та доступним власнику.')


def new_file(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def source_identity(source_root):
    source_root = safe_path(source_root, must_exist=True)
    package = source_root / 'BOS_PACKAGE.json'
    if package.exists():
        manifest = json.loads(package.read_text(encoding='utf-8'))
        body = {k: v for k, v in manifest.items() if k != 'source_sha256'}
        if manifest.get('format') != 'BoS-source-package-1' or sha(canonical(body)) != manifest.get('source_sha256'):
            refuse('Manifest пакета відсутній або змінений.')
        actual = {p.relative_to(source_root).as_posix() for p in source_root.rglob('*') if p.is_file()}
        if actual != set(manifest['files']) | {'BOS_PACKAGE.json'}:
            refuse('Склад файлів пакета не відповідає manifest.')
        for relative, expected in manifest['files'].items():
            path = safe_path(source_root / relative, must_exist=True)
            if source_root not in path.parents or sha(path.read_bytes()) != expected:
                refuse('Файл джерельного пакета змінений або має неприпустимий шлях.')
            if path.suffix.lower() in ('.db', '.sqlite', '.sqlite3') or path.name == '.env':
                refuse('Пакет коду містить робочу базу або секрети.')
        return {'version': manifest['version'], 'source_sha256': manifest['source_sha256'], 'full_code_package_verified': True}
    version_path = safe_path(source_root / 'boss_project/version.py', must_exist=True)
    values = [node.value.value for node in ast.parse(version_path.read_text(encoding='utf-8')).body
              if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'VERSION' for target in node.targets)
              and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)]
    if len(values) != 1:
        refuse('Пакет не має однозначної версії BoS.')
    digest = hashlib.sha256()
    for relative in ('manage.py', 'requirements.txt', 'boss_project/version.py'):
        path = safe_path(source_root / relative, must_exist=True)
        if not path.is_file():
            refuse('Метадані джерельного пакета неповні.')
        digest.update(relative.encode() + b'\0' + path.read_bytes() + b'\0')
    return {'version': values[0], 'bootstrap_metadata_sha256': digest.hexdigest(),
            'full_code_package_verified': False}


def origin_fields(origin):
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except (ValueError, TypeError):
        refuse('Вкажіть коректний HTTPS origin.')
    host = parsed.hostname
    if (parsed.scheme != 'https' or not host or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or port == 0
            or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host)
            or origin != 'https://' + host + (':' + str(port) if port is not None else '')):
        refuse('Вкажіть один точний HTTPS origin без шляху чи облікових даних.')
    return origin, host


class InstallerRegistry:
    """Trusted operator state outside installation targets; never copied from target."""
    def __init__(self, path):
        self.root = safe_path(path)
        if not self.root.exists():
            self.root.mkdir(mode=0o700)
            self.owner = {'format': FORMAT, 'registry_id': str(uuid.uuid4()), 'identity': identity(self.root)}
            new_file(self.root / 'REGISTRY.json', canonical(self.owner))
        private_directory(self.root)
        marker = self.root / 'REGISTRY.json'
        private_regular(marker)
        self.owner = json.loads(marker.read_text(encoding='utf-8'))
        if self.owner.get('format') != FORMAT or self.owner.get('identity') != identity(self.root):
            refuse('Каталог реєстру невідомий або замінений.')
        self.root_identity = identity(self.root)

    @contextmanager
    def lock(self):
        if os.name != 'posix':
            refuse('Блокування інсталятора цієї ОС ще не перевірено.')
        import fcntl
        path = self.root / 'REGISTRY.lock'
        if not path.exists():
            try:
                new_file(path, b'')
            except FileExistsError:
                pass
        private_regular(path)
        with path.open('rb') as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                refuse('Інший процес інсталятора вже працює з цим реєстром.')
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def records(self):
        if identity(self.root) != self.root_identity:
            refuse('Реєстр інсталятора замінено.')
        result = []
        for path in self.root.iterdir():
            private_regular(path)
            if path.name in ('REGISTRY.json', 'REGISTRY.lock'):
                continue
            if path.name.startswith('pending-') and (self.root / path.name.removeprefix('pending-')).is_file():
                continue
            if not re.fullmatch(r'[0-9a-f-]{36}\.json', path.name):
                refuse('Реєстр містить невідомі файли; автоматичне виправлення заборонено.')
            record = json.loads(path.read_text(encoding='utf-8'))
            if record.get('registry_id') != self.owner['registry_id'] or path.stem != record.get('id'):
                refuse('Запис інсталяції належить іншому реєстру.')
            result.append(record)
        return result

    def issue(self, record):
        record['registry_id'] = self.owner['registry_id']
        new_file(self.root / (record['id'] + '.json'), canonical(record))

    def update(self, record):
        existing = self.get(record['id'])
        immutable = ('id', 'root', 'root_identity', 'secret', 'source', 'origin', 'host', 'created_at', 'registry_id')
        if any(existing[key] != record[key] for key in immutable):
            refuse('Незмінні дані інсталяції не можуть бути переписані.')
        destination = self.root / (record['id'] + '.json')
        private_regular(destination)
        temporary = self.root / ('pending-' + record['id'] + '.json')
        if temporary.exists():
            private_regular(temporary)
            temporary.unlink()  # Only known scratch metadata for this registered installation.
        new_file(temporary, canonical(record))
        os.replace(temporary, destination)

    def get(self, installation_id):
        matches = [record for record in self.records() if record['id'] == installation_id]
        if len(matches) != 1:
            refuse('Цей реєстр не створював зазначену інсталяцію.')
        return matches[0]


def artifacts(record):
    bundle = Path(record['root'])
    root = bundle / 'state'
    env = {'DJANGO_SETTINGS_MODULE': 'server_settings', 'BOS_DATA_MODE': 'working',
        'BOS_DATABASE_ENGINE': 'sqlite3', 'BOS_INSTALLATION_ID': record['id'],
        'BOS_INSTALLATION_ROOT': str(root), 'BOS_DATABASE_PATH': str(root / 'data/bos.sqlite3'),
        'BOS_MEDIA_ROOT': str(root / 'private'), 'BOS_PUBLIC_ORIGIN': record['origin'],
        'BOS_ALLOWED_HOSTS': record['host'], 'BOS_TRUSTED_PROXY_IPS': '127.0.0.1,::1',
        'BOS_SECRET_KEY': record['secret']}
    manifest = {'format': FORMAT, 'installation_id': record['id'], **record['source'],
        'status': 'files_prepared_runtime_incomplete', 'complete': False,
        'created_at': record['created_at'], 'unfinished': list(UNFINISHED)}
    return {'config/server.json': canonical(env), 'INSTALLATION.json': canonical(manifest)}


def inspect_partial(record):
    root = safe_path(record['root'], must_exist=True)
    private_directory(root)
    if identity(root) != record['root_identity']:
        refuse('Каталог інсталяції замінено; повтор заборонено.')
    expected = artifacts(record)
    runtime = record.get('runtime', {})
    owned_trees = runtime.get('owned_trees', {})
    for relative, proof in owned_trees.items():
        path = safe_path(root / relative, must_exist=True)
        if root not in path.parents or identity(path) != proof:
            refuse('Власний runtime каталог замінено.')
    allowed = set(DIRECTORIES) | set(expected)
    owned_database = runtime.get('database')
    if owned_database:
        db = safe_path(root / 'state/data/bos.sqlite3', must_exist=True)
        private_regular(db)
        if identity(db) != owned_database:
            refuse('Власна база інсталяції замінена.')
        allowed.add('state/data/bos.sqlite3')
    for path in root.rglob('*'):
        relative = path.relative_to(root).as_posix()
        owned_tree = next((tree for tree in owned_trees if relative == tree or relative.startswith(tree + '/')), None)
        if owned_tree and path.is_symlink() and relative == 'venv/lib64' and os.readlink(path) == 'lib':
            continue  # Exact stdlib venv internal link, never an input/DB/media path.
        safe_path(path, must_exist=True)
        if owned_tree:
            info = path.lstat()
            if not (stat.S_ISDIR(info.st_mode) or (stat.S_ISREG(info.st_mode) and info.st_nlink == 1)):
                refuse('Runtime містить стороннє жорстке посилання або спеціальний файл; повтор заборонено.')
            continue
        if relative not in allowed:
            refuse('Інсталяція містить невідомий вміст; повтор нічого не перезаписує.')
        if relative in DIRECTORIES:
            private_directory(path)
        elif relative in expected:
            private_regular(path)
            if path.read_bytes() != expected[relative]:
                refuse('Раніше створений файл інсталяції змінено або записано не повністю.')
    return expected


def prepare_install(*, target, registry, source_root, origin, resume=None, stop_after=None):
    target, registry, source_root = safe_path(target), safe_path(registry), safe_path(source_root, must_exist=True)
    origin, host = origin_fields(origin)
    source = source_identity(source_root)
    for left, right in ((target, source_root), (target, registry), (source_root, registry)):
        if left == right or right in left.parents or left in right.parents:
            refuse('Інсталяція, джерельний пакет і реєстр мають бути окремими каталогами.')
    if not resume and target.exists():
        refuse('Нова інсталяція потребує відсутнього цільового каталогу, навіть якщо він порожній.')
    if resume and not registry.exists():
        refuse('Для повтору потрібен попередній довірений реєстр інсталятора.')
    owner = InstallerRegistry(registry)
    with owner.lock():
        known = owner.records()
        if resume:
            record = owner.get(resume)
            if (record['root'] != str(target) or record['source'] != source
                    or record['origin'] != origin or record['host'] != host):
                refuse('Повтор потребує тієї самої інсталяції, версії та адреси; це не оновлення.')
            if record.get('runtime', {}).get('application_provisioned'):
                refuse('Для готової інсталяції використовуйте окремий запуск; повторне встановлення заборонено.')
        else:
            for record in known:
                previous = Path(record['root'])
                if target == previous or previous in target.parents or target in previous.parents:
                    refuse('Інсталяції не можуть вкладатися одна в одну або повторно займати зареєстрований шлях.')
            target.mkdir(mode=0o700)
            record = {'format': FORMAT, 'runtime': {}, 'id': str(uuid.uuid4()), 'root': str(target),
                'root_identity': identity(target), 'secret': secrets.token_urlsafe(64),
                'source': source, 'origin': origin, 'host': host,
                'created_at': datetime.now(timezone.utc).isoformat()}
            owner.issue(record)
        expected = inspect_partial(record)
        if stop_after != 'claim':
            for name in DIRECTORIES:
                directory = target / name
                if not directory.exists():
                    directory.mkdir(mode=0o700)
            for relative, content in expected.items():
                if not (target / relative).exists():
                    new_file(target / relative, content)
                if stop_after == 'config':
                    break
        inspect_partial(record)
        return {'complete': False, 'status': 'bootstrap_only', 'exit_code': 2,
            'installation_id': record['id'], 'version': source['version'],
            'prepared_files': sorted(path.relative_to(target).as_posix() for path in target.rglob('*') if path.is_file()),
            'checks': {stage: {'status': 'НЕ ВИКОНАНО'} for stage in UNFINISHED},
            'reason': 'Файли інсталяції підготовлено; pinned runtime, міграції та HTTPS стенд ще не виконані.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, type=Path)
    parser.add_argument('--registry', required=True, type=Path)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--origin', required=True)
    parser.add_argument('--wheelhouse', type=Path, help='Offline wheel directory; no network resolution is allowed')
    parser.add_argument('--resume', help='Installation UUID previously issued by the same private registry')
    args = parser.parse_args()
    try:
        if args.wheelhouse:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            try:
                from scripts.provision_runtime import provision_install
            except ModuleNotFoundError:
                refuse('Пакет не містить повного runtime provisioner; встановлення не завершене.')
            result = provision_install(installer=sys.modules[__name__], target=args.target, registry=args.registry,
                source_root=args.source_root, origin=args.origin, wheelhouse=args.wheelhouse, resume=args.resume)
        else:
            result = prepare_install(target=args.target, registry=args.registry, source_root=args.source_root,
                                     origin=args.origin, resume=args.resume)
    except (InstallRefused, OSError, ValueError) as error:
        print(json.dumps({'complete': False, 'status': 'refused', 'reason': str(error)}, ensure_ascii=False))
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
