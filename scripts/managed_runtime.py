"""Real BoS + Caddy startup callback for same-process ManagedSupervisor.

The existing A09 loader, profile, proxy renderer, logging and HTTPS health are
reused. No IPC endpoint or original installation mutation is introduced.
"""
import hashlib
import http.client
import importlib.util
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class BoSRuntime:
    def __init__(self, *, installer, target, registry, installation_id, caddy,
                 certificate, private_key, http_port, ca_certificate=None,
                 startup_timeout=20, emit=None):
        self.installer = installer
        self.target, self.registry = Path(target), Path(registry)
        self.installation_id = installation_id
        self.caddy, self.certificate, self.private_key = map(Path, (caddy, certificate, private_key))
        self.ca_certificate = Path(ca_certificate) if ca_certificate is not None else None
        self.http_port, self.startup_timeout = http_port, startup_timeout
        self.emit = emit or (lambda event: print(json.dumps(event, ensure_ascii=False), flush=True))
        self.generations = []
        self.ready = None
        self.events = queue.Queue()
        self._running = None

    def assert_running(self):
        """Check only this generation's actual children and logging drain."""
        from scripts.maintenance_control import ControlRefused
        if self._running is None:
            raise ControlRefused("Власний runtime ще не підтвердив готовність.")
        failed, children = self._running
        if failed.is_set() or any(child.poll() is not None for child in children):
            raise ControlRefused("Власний runtime або його нормалізовані журнали недоступні.")

    def __call__(self, owner):
        self._running = None
        from scripts import lifecycle_server as baseline
        from scripts.maintenance_control import ControlRefused
        if (owner.target != self.target or owner.installation_id != self.installation_id
                or not math.isfinite(self.startup_timeout) or not 0 < self.startup_timeout <= 120):
            raise ControlRefused('Callback не належить цій керованій інсталяції.')
        installer = self.installer
        record, release, python, config = baseline.load_owned(installer, target=self.target,
            registry=self.registry, installation_id=self.installation_id)
        for path in (self.caddy, self.certificate, self.private_key):
            installer.safe_path(path, must_exist=True)
        installer.private_regular(self.private_key)
        if self.ca_certificate is not None:
            installer.safe_path(self.ca_certificate, must_exist=True)
        if (not self.certificate.is_file() or not self.caddy.is_file()
                or hashlib.sha256(self.caddy.read_bytes()).hexdigest() != baseline.CADDY_LINUX_AMD64_SHA256):
            raise ControlRefused('Потрібні TLS та точний перевірений Caddy 2.11.1.')
        env = baseline.child_environment(config)
        version = subprocess.run([str(self.caddy), 'version'], capture_output=True, text=True, env=env, timeout=5)
        if version.returncode != 0 or not version.stdout.startswith('v' + baseline.CADDY_VERSION + ' '):
            raise ControlRefused('Proxy не підтвердив закріплену версію.')
        logging = _module('bos_owned_proxy_logging', release / 'boss_project/proxy_logging.py')
        work = self.target / 'runtime-logs' / ('managed-' + uuid.uuid4().hex)
        work.mkdir(mode=0o700)
        env.update(XDG_DATA_HOME=str(work / 'xdg-data'), XDG_CONFIG_HOME=str(work / 'xdg-config'))
        failed = threading.Event()
        proxy_started = threading.Event()
        bound_events = queue.Queue()
        children = []

        def log(name):
            path = work / name
            installer.new_file(path, b'')
            return path.open('a', encoding='utf-8')

        appout, apperr = log('application.stdout.log'), log('application.stderr.log')
        app = owner.spawn('waitress', [str(python), '-B', str(release / 'scripts/start_server.py'), '--port', '0'],
            cwd=release, env=env, stdout=subprocess.PIPE, stderr=apperr, text=True, bufsize=1)
        children.append(app)

        def read_app():
            for line in app.stdout:
                try:
                    appout.write(line);appout.flush()
                    event = json.loads(line)
                    if not isinstance(event, dict):continue
                    kind = event.get('event')
                    if kind in ('bos.server.bound', 'bos.server.refused'):
                        bound_events.put(event)
                    if kind == 'bos.server.quiescent':
                        owner.record_drain(app, event)
                    if kind in ('bos.server.bound', 'bos.server.draining', 'bos.server.quiescent', 'bos.server.drain_failed'):
                        self.events.put(event)
                except (ValueError, OSError):
                    failed.set()
        reader = threading.Thread(target=read_app, daemon=True)
        owner.track_reader(reader, streams=(app.stdout, appout, apperr))
        reader.start()
        deadline = time.monotonic() + self.startup_timeout
        bound = None
        while bound is None:
            if failed.is_set() or app.poll() is not None or time.monotonic() >= deadline:
                raise ControlRefused('Керований Waitress не підтвердив запуск.')
            try:bound = bound_events.get(timeout=.1)
            except queue.Empty:continue
        if (bound.get('event') != 'bos.server.bound' or bound.get('runtime_version') != '3.0.2'
                or bound.get('host') != '127.0.0.1' or type(bound.get('port')) is not int):
            raise ControlRefused('Невідомий власний WSGI runtime.')
        payload = {'origin': config['BOS_PUBLIC_ORIGIN'], 'http_port': self.http_port,
            'upstream_port': bound['port'], 'certificate': str(self.certificate),
            'private_key': str(self.private_key), 'static_root': str(self.target / 'state/static')}
        rendered = subprocess.run([str(python), '-B', '-c',
            'import json,sys; from boss_project.server_proxy import render; print(render(**json.load(sys.stdin)),end="")'],
            input=json.dumps(payload), cwd=release, env=env, capture_output=True, text=True, timeout=10)
        if rendered.returncode:
            raise ControlRefused('Канонічна конфігурація HTTPS не побудована.')
        caddyfile = work / 'Caddyfile'
        installer.new_file(caddyfile, rendered.stdout.encode('utf-8'))
        proxy = owner.spawn('caddy', [str(self.caddy), 'run', '--config', str(caddyfile), '--adapter', 'caddyfile'],
            cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        children.append(proxy)

        def drain_proxy(stream, output):
            for line in stream:
                if stream is proxy.stderr and len(line) <= 65536:
                    try:entry = json.loads(line)
                    except (ValueError, RecursionError):entry = None
                    if isinstance(entry, dict) and entry.get('msg') == 'serving initial configuration':
                        proxy_started.set()
                try:logging.write_proxy_line(line, output, version=record['source']['version'])
                except Exception:failed.set()  # Never store raw fallback.
        for stream, filename in ((proxy.stdout, 'caddy.stdout.log'), (proxy.stderr, 'caddy.stderr.log')):
            output = log(filename)
            reader = threading.Thread(target=drain_proxy, args=(stream, output), daemon=True)
            owner.track_reader(reader, streams=(stream, output))
            reader.start()
        checked = None
        while checked is None:
            if failed.is_set() or any(child.poll() is not None for child in children) or time.monotonic() >= deadline:
                raise ControlRefused('Власний HTTPS runtime не підтвердив готовність.')
            if not proxy_started.is_set():
                time.sleep(.05)
                continue
            try:checked = baseline.health(config['BOS_PUBLIC_ORIGIN'], self.ca_certificate)
            except (ValueError, OSError, http.client.HTTPException):
                time.sleep(.05)
        if failed.is_set() or any(child.poll() is not None for child in children):
            raise ControlRefused('Власний runtime завершився під час health.')
        self.ready = {'event': 'bos.bundle.ready', 'installation_id': self.installation_id,
            'origin': config['BOS_PUBLIC_ORIGIN'], 'scope': 'loopback-same-process',
            'health': checked, 'source_sha256': record['source']['source_sha256'],
            'runtime': 'waitress 3.0.2', 'proxy': 'caddy 2.11.1', 'upstream_port': bound['port']}
        self.generations.append({'ready': dict(self.ready), 'work': str(work)})
        self._running = (failed, tuple(children))
        self.emit(self.ready)
