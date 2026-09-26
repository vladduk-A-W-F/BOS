"""Foreground supervisor for one owned BoS bundle on loopback.

Only child Popen handles created by this process are stopped. No PID-file kill,
background daemon, public bind, dependency install or database migration occurs.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import http.client
import json
import os
import math
import stat
from pathlib import Path
import queue
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import urlsplit

CADDY_VERSION = '2.11.1'
CADDY_LINUX_AMD64_SHA256 = 'ebadd69d2faf96cfc5f002765d9e0f2d1f37d9c55c74c37878187a77d6629b38'


class LifecycleRefused(ValueError):
    pass


def refuse(message):
    raise LifecycleRefused(message)


def load_owned(installer, *, target, registry, installation_id):
    """Read only runtime identity, code and config; business files stay mutable."""
    target = installer.safe_path(target, must_exist=True)
    registry = installer.safe_path(registry, must_exist=True)
    owner = installer.InstallerRegistry(registry)
    record = owner.get(installation_id)
    if record['root'] != str(target) or installer.identity(target) != record['root_identity']:
        refuse('Це інша інсталяція або її каталог замінено.')
    installer.private_directory(target)
    runtime = record.get('runtime', {})
    if not runtime.get('application_provisioned'):
        refuse('Програму ще не встановлено; запуск потребує завершеного provision.')
    for relative, expected in installer.artifacts(record).items():
        path = target / relative
        installer.private_regular(path)
        if path.read_bytes() != expected:
            refuse('Конфігурація інсталяції не відповідає довіреному реєстру.')
    owned_trees = runtime.get('owned_trees', {})
    required_trees = {'venv', 'runtime-logs', 'state/static', 'releases/' + record['source']['source_sha256']}
    if not required_trees <= set(owned_trees):
        refuse('Реєстр не підтверджує всі каталоги встановленого runtime.')
    for relative, proof in owned_trees.items():
        path = installer.safe_path(target / relative, must_exist=True)
        if target not in path.parents or installer.identity(path) != proof:
            refuse('Зареєстрований каталог runtime замінено.')
    for relative in ('state', 'state/data', 'state/private', 'state/static', 'runtime-logs'):
        installer.private_directory(target / relative)
    database = target / 'state/data/bos.sqlite3'
    installer.private_regular(database)
    if installer.identity(database) != runtime.get('database'):
        refuse('Зареєстровану базу даних замінено.')
    expected_release = 'releases/' + record['source']['source_sha256']
    if runtime.get('release') != expected_release:
        refuse('Шлях release не відповідає manifest інсталяції.')
    release = installer.safe_path(target / expected_release, must_exist=True)
    if installer.source_identity(release) != record['source']:
        refuse('Повний manifest release змінився.')
    for relative in ('scripts/start_server.py', 'boss_project/server_proxy.py', 'boss_project/proxy_logging.py'):
        if not (release / relative).is_file():
            refuse('У release відсутній перевірений серверний компонент.')
    # The venv is executable code, never mutable business storage. A foreign
    # hardlink or symlink must not become the program selected by this launcher.
    for path in (target / 'venv').rglob('*'):
        relative = path.relative_to(target).as_posix()
        if path.is_symlink() and relative == 'venv/lib64' and os.readlink(path) == 'lib':
            continue
        installer.safe_path(path, must_exist=True)
        info = path.lstat()
        if not (stat.S_ISDIR(info.st_mode) or (stat.S_ISREG(info.st_mode) and info.st_nlink == 1)):
            refuse('Приватний runtime містить стороннє посилання або спеціальний файл.')
    python = installer.safe_path(target / 'venv/bin/python', must_exist=True)
    if not python.is_file() or not os.access(python, os.X_OK):
        refuse('Приватний Python runtime недоступний.')
    config = json.loads((target / 'config/server.json').read_bytes())
    return record, release, python, config


@contextmanager
def instance_lock(installer, target):
    if os.name != 'posix':
        refuse('Блокування та завершення процесів цієї ОС ще не перевірено.')
    import fcntl
    path = target / 'runtime-logs/INSTANCE.lock'
    if not path.exists():
        try:
            installer.new_file(path, b'')
        except FileExistsError:
            pass
    installer.private_regular(path)
    with path.open('rb') as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            refuse('Ця інсталяція вже працює; другий запуск відхилено.')
        try:
            # An inode replaced while opening is not the instance authority.
            if installer.identity(path) != [os.fstat(stream.fileno()).st_dev, os.fstat(stream.fileno()).st_ino]:
                refuse('Файл блокування інсталяції замінено.')
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def child_environment(config):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('BOS_', 'PIP_', 'OPENAI', 'ANTHROPIC', 'CADDY_'))
           and k not in ('PYTHONPATH', 'PYTHONHOME', 'DJANGO_SETTINGS_MODULE', 'LD_PRELOAD', 'LD_LIBRARY_PATH')}
    env.update(config)
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONUTF8='1')
    return env


class LoopbackHTTPS(http.client.HTTPSConnection):
    def connect(self):
        raw = socket.create_connection(('127.0.0.1', self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def health(origin, ca_certificate=None):
    parsed = urlsplit(origin)
    context = ssl.create_default_context(cafile=str(ca_certificate) if ca_certificate else None)
    result = {}
    for name, expected in (('live', 'alive'), ('ready', 'ready')):
        conn = LoopbackHTTPS(parsed.hostname, parsed.port or 443, context=context, timeout=1)
        try:
            conn.request('GET', '/health/' + name + '/', headers={'Host': parsed.netloc})
            response = conn.getresponse()
            body = response.read(4097)
            if response.status != 200 or len(body) > 4096 or json.loads(body) != {'status': expected}:
                refuse('HTTPS health ще не підтвердив готовність інсталяції.')
            result[name] = response.status
        finally:
            conn.close()
    return result


def serve(*, installer, target, registry, installation_id, caddy, certificate, private_key,
          http_port, ca_certificate=None, startup_timeout=20, emit=None):
    """Block until SIGINT/SIGTERM, then stop only this supervisor's children."""
    if not math.isfinite(startup_timeout) or not 0 < startup_timeout <= 120:
        refuse('Строк очікування має бути скінченним і не перевищувати 120 секунд.')
    emit = emit or (lambda event: print(json.dumps(event, ensure_ascii=False), flush=True))
    record, release, python, config = load_owned(installer, target=target, registry=registry,
                                                installation_id=installation_id)
    target = Path(target)
    caddy, certificate, private_key = (installer.safe_path(p, must_exist=True)
                                      for p in (caddy, certificate, private_key))
    if ca_certificate is not None:
        ca_certificate = installer.safe_path(ca_certificate, must_exist=True)
    installer.private_regular(private_key)
    if not certificate.is_file() or (ca_certificate is not None and not ca_certificate.is_file()):
        refuse('TLS потребує наявного сертифіката та довіреного CA.')
    if not caddy.is_file() or hashlib.sha256(caddy.read_bytes()).hexdigest() != CADDY_LINUX_AMD64_SHA256:
        refuse('SHA Caddy не відповідає перевіреному Linux amd64 2.11.1.')
    https_port = urlsplit(config['BOS_PUBLIC_ORIGIN']).port or 443
    if type(http_port) is not int or not 1 <= http_port <= 65535 or http_port == https_port:
        refuse('HTTP та HTTPS потребують різних коректних портів.')
    env = child_environment(config)
    logging_path = release / 'boss_project/proxy_logging.py'
    logging_spec = importlib.util.spec_from_file_location('bos_owned_proxy_logging', logging_path)
    proxy_logging = importlib.util.module_from_spec(logging_spec)
    logging_spec.loader.exec_module(proxy_logging)
    version = subprocess.run([str(caddy), 'version'], capture_output=True, text=True, timeout=5, env=env)
    if version.returncode != 0 or not version.stdout.startswith('v' + CADDY_VERSION + ' '):
        refuse('Caddy не підтвердив закріплену версію.')
    stopped = threading.Event()
    children, handles, readers = [], [], []
    logging_failed = threading.Event()
    proxy_started = threading.Event()
    previous = {}
    result = {'event': 'bos.bundle.stopped', 'installation_id': record['id'], 'children': []}
    with instance_lock(installer, target):
        # Recheck the same authority after winning the process lock.
        load_owned(installer, target=target, registry=registry, installation_id=installation_id)
        work = target / 'runtime-logs' / ('lifecycle-' + uuid.uuid4().hex)
        work.mkdir(mode=0o700)
        env.update(XDG_DATA_HOME=str(work / 'xdg-data'), XDG_CONFIG_HOME=str(work / 'xdg-config'))
        def log(name):
            path = work / name
            installer.new_file(path, b'')
            handle = path.open('a', encoding='utf-8')
            handles.append(handle)
            return handle
        def on_stop(signum, frame):
            stopped.set()
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, on_stop)
        try:
            events = queue.Queue()
            app_stdout = log('application.stdout.log')
            app = subprocess.Popen([str(python), '-B', str(release / 'scripts/start_server.py'), '--port', '0'],
                cwd=release, env=env, stdout=subprocess.PIPE, stderr=log('application.stderr.log'), text=True, bufsize=1)
            children.append(('waitress', app))
            def read_app():
                for line in app.stdout:
                    app_stdout.write(line)
                    app_stdout.flush()
                    try:
                        event = json.loads(line)
                        if event.get('event') in ('bos.server.bound', 'bos.server.refused'):
                            events.put(event)
                    except (ValueError, AttributeError):
                        pass
            reader = threading.Thread(target=read_app, daemon=True)
            reader.start()
            readers.append(reader)
            deadline = time.monotonic() + startup_timeout
            bound = None
            while bound is None and not stopped.is_set():
                if app.poll() is not None or time.monotonic() >= deadline:
                    refuse('Waitress не підтвердив запуск у відведений час.')
                try:
                    bound = events.get(timeout=.1)
                except queue.Empty:
                    continue
            if stopped.is_set():
                return result
            if (bound.get('event') != 'bos.server.bound' or bound.get('host') != '127.0.0.1'
                    or bound.get('runtime_version') != '3.0.2' or type(bound.get('port')) is not int):
                refuse('Waitress не підтвердив очікуваний приватний runtime.')
            payload = dict(origin=config['BOS_PUBLIC_ORIGIN'], http_port=http_port, upstream_port=bound['port'],
                certificate=str(certificate), private_key=str(private_key), static_root=str(target / 'state/static'))
            render = subprocess.run([str(python), '-B', '-c',
                'import json,sys; from boss_project.server_proxy import render; print(render(**json.load(sys.stdin)), end="")'],
                input=json.dumps(payload), cwd=release, env=env, capture_output=True, text=True, timeout=10)
            if render.returncode:
                refuse('Канонічну конфігурацію HTTPS не побудовано.')
            caddyfile = work / 'Caddyfile'
            installer.new_file(caddyfile, render.stdout.encode('utf-8'))
            proxy = subprocess.Popen([str(caddy), 'run', '--config', str(caddyfile), '--adapter', 'caddyfile'],
                cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            children.append(('caddy', proxy))
            def drain_proxy(stream, destination):
                for line in stream:
                    # Only the verified child can provide this startup event.
                    # Inspect in memory; never retain raw msg/request fields.
                    if stream is proxy.stderr and len(line) <= 65536:
                        try:
                            entry = json.loads(line)
                        except (ValueError, RecursionError):
                            entry = None
                        if isinstance(entry, dict) and entry.get('msg') == 'serving initial configuration':
                            proxy_started.set()
                    try:
                        proxy_logging.write_proxy_line(line, destination, version=record['source']['version'])
                    except Exception:
                        # Continue draining; the supervisor fails closed. Raw input
                        # is never substituted into logs even on parser/IO failure.
                        logging_failed.set()
            for stream, filename in ((proxy.stdout, 'caddy.stdout.log'), (proxy.stderr, 'caddy.stderr.log')):
                reader = threading.Thread(target=drain_proxy, args=(stream, log(filename)), daemon=True)
                reader.start()
                readers.append(reader)
            checked = None
            while not stopped.is_set():
                if logging_failed.is_set():
                    refuse('Нормалізований журнал proxy недоступний; запуск зупинено.')
                if any(p.poll() is not None for _, p in children):
                    refuse('Сервер або HTTPS proxy завершився до підтвердження готовності.')
                if not proxy_started.is_set():
                    if time.monotonic() >= deadline:
                        refuse('Власний Caddy не підтвердив успішне відкриття портів.')
                    stopped.wait(.05)
                    continue
                try:
                    checked = health(config['BOS_PUBLIC_ORIGIN'], ca_certificate)
                    if any(p.poll() is not None for _, p in children) or logging_failed.is_set():
                        refuse('Власний сервер завершився під час перевірки HTTPS.')
                    break
                except (LifecycleRefused, OSError, ssl.SSLError, ValueError, http.client.HTTPException):
                    if time.monotonic() >= deadline:
                        refuse('Готовність через перевірений HTTPS не підтверджено.')
                    stopped.wait(.1)
            if checked is not None:
                if stopped.is_set() or any(p.poll() is not None for _, p in children) or logging_failed.is_set():
                    refuse('Власний сервер більше не готовий; ready подію не оприлюднено.')
                emit({'event': 'bos.bundle.ready', 'installation_id': record['id'], 'origin': record['origin'],
                    'scope': 'loopback', 'health': checked, 'source_sha256': record['source']['source_sha256'],
                    'runtime': 'waitress 3.0.2', 'proxy': 'caddy 2.11.1', 'upstream_port': bound['port']})
            while not stopped.wait(.1):
                if logging_failed.is_set():
                    refuse('Нормалізований журнал proxy недоступний; запуск зупинено.')
                if any(p.poll() is not None for _, p in children):
                    refuse('Власний дочірній сервер завершився; інсталяцію зупинено.')
        finally:
            # Popen tracks its actual child; no external PID or marker can select a victim.
            for name, process in reversed(children):
                forced = False
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    forced = True
                    process.kill()
                    process.wait(timeout=3)
                result['children'].append({'runtime': name, 'exit_code': process.returncode, 'forced': forced})
            for reader in readers:
                reader.join(timeout=2)
            for _, process in children:
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
            for handle in handles:
                handle.close()
            for signum, handler in previous.items():
                signal.signal(signum, handler)
            emit(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('target', 'registry', 'caddy', 'certificate', 'private-key'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--installation-id', required=True)
    parser.add_argument('--http-port', required=True, type=int)
    parser.add_argument('--ca-certificate', type=Path)
    parser.add_argument('--startup-timeout', type=float, default=20)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts import install_server as installer
    try:
        result = serve(installer=installer, **vars(args))
    except (LifecycleRefused, installer.InstallRefused, OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps({'event': 'bos.bundle.refused', 'complete': False,
            'reason': 'Запуск не підтверджено. Перевірте власність інсталяції, приватний runtime та TLS.'}, ensure_ascii=False), flush=True)
        return 3
    return 0 if all(not c['forced'] and c['exit_code'] == 0 for c in result['children']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
