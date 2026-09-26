"""Same-process maintenance capability for an owned foreground supervisor.

No IPC/socket/FIFO/file-command endpoint. The capture callback and this object
must live in the same process; a separately running supervisor is not managed.
"""
from __future__ import annotations
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import threading
import uuid

_ISSUER = object()


class ControlRefused(ValueError):
    pass


def refuse(message='Власний supervisor не підтверджує право на обслуговування.'):
    raise ControlRefused(message)


def canonical_uuid(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            refuse()
    except (ValueError, AttributeError):
        refuse()
    return value


class ManagedSupervisor:
    """The caller supplies trusted startup code, not a serialized success flag."""
    def __init__(self, *, installer, target, registry, installation_id, start_callback, drain_timeout=10):
        if os.name != 'posix':
            refuse('Instance flock цієї ОС не перевірено.')
        if not callable(start_callback) or not 0 < drain_timeout <= 30:
            refuse('Потрібні локальний callback запуску та скінченний timeout.')
        self.installer = installer
        self.target = installer.safe_path(target, must_exist=True)
        registry = installer.safe_path(registry, must_exist=True)
        record = installer.InstallerRegistry(registry).get(installation_id)
        if record['root'] != str(self.target) or record['root_identity'] != installer.identity(self.target):
            refuse('Чужа або замінена інсталяція.')
        if not record.get('runtime', {}).get('application_provisioned'):
            refuse('Керований запуск потребує фактично встановленої програми.')
        logs = self.target / 'runtime-logs'
        installer.private_directory(self.target)
        installer.private_directory(logs)
        if record['runtime']['owned_trees'].get('runtime-logs') != installer.identity(logs):
            refuse('Зареєстрований runtime каталог замінено.')
        self.installation_id = canonical_uuid(installation_id)
        self.root_identity = tuple(record['root_identity'])
        self._logs_identity = tuple(installer.identity(logs))
        self._config = {name: data for name, data in installer.artifacts(record).items()}
        self._record = record
        self._pid = os.getpid()
        # /proc may expose the outer PID namespace while getpid() is namespaced.
        self._kernel_pid = next(line.split()[1] for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('Pid:'))
        self._owner_token = object()
        self._state = 'new'
        self._lock_path = logs / 'INSTANCE.lock'
        self._lock_file = None
        self._lock_identity = None
        self._guard = threading.RLock()
        self._children = []
        self._readers = []
        self._drain = {}
        self._stopped = None
        self._stopped_handles = []
        self._lease = None
        self._start_callback = start_callback
        self._drain_timeout = drain_timeout
        self._generation = 0
        self._operation_id = None
        self._active_pointer = self.target / 'generations/ACTIVE.json'

    @property
    def state(self): return self._state

    def _same_generation(self):
        if self._active_pointer.exists() or self._active_pointer.is_symlink():
            refuse('Same-N supervisor не запускає іншу активовану generation.')

    def _check_owner(self):
        if os.getpid() != self._pid or self._lock_file is None or self._lock_file.closed:
            refuse('Lease потребує живого owner у тому самому процесі.')
        info = os.fstat(self._lock_file.fileno())
        if ((info.st_dev, info.st_ino) != self._lock_identity
                or tuple(self.installer.identity(self._lock_path)) != self._lock_identity
                or tuple(self.installer.identity(self.target)) != self.root_identity
                or tuple(self.installer.identity(self.target / 'runtime-logs')) != self._logs_identity):
            refuse('Lifetime instance fence або root замінено.')
        self.installer.private_regular(self._lock_path)
        for relative, expected in self._config.items():
            path = self.target / relative
            self.installer.private_regular(path)
            if path.read_bytes() != expected:
                refuse('Канонічна конфігурація інсталяції змінена.')
        db = self.target / 'state/data/bos.sqlite3'
        self.installer.private_regular(db)
        if self.installer.identity(db) != self._record['runtime'].get('database'):
            refuse('Власна база інсталяції замінена.')
        # Linux exposes the lock owned by this exact open file description.
        # This rejects an externally unlocked fd even if another process now
        # holds a different lock on the same inode. Never re-lock to fake proof.
        fdinfo = Path('/proc/self/fdinfo') / str(self._lock_file.fileno())
        observed = False
        for line in fdinfo.read_text().splitlines():
            fields = line.split()
            if len(fields) == 9 and fields[:1] == ['lock:'] and fields[2:5] == ['FLOCK', 'ADVISORY', 'WRITE']:
                dev_major, dev_minor, inode = fields[6].split(':')
                observed |= (fields[5] == self._kernel_pid and int(dev_major, 16) == os.major(info.st_dev)
                    and int(dev_minor, 16) == os.minor(info.st_dev) and int(inode) == info.st_ino)
        if not observed:
            refuse('Lifetime instance flock більше не належить цьому fd.')

    def __enter__(self):
        import fcntl
        if self._state != 'new':
            refuse('Supervisor не можна повторно відкрити.')
        self._same_generation()
        if not self._lock_path.exists():
            try:self.installer.new_file(self._lock_path, b'')
            except FileExistsError:pass
        self.installer.private_regular(self._lock_path)
        stream = self._lock_path.open('rb')
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            info = os.fstat(stream.fileno())
            self._lock_identity = (info.st_dev, info.st_ino)
            self._lock_file = stream
            self._state = 'idle'
            self._check_owner()
        except BaseException:
            stream.close()
            self._lock_file = None
            raise
        return self

    def spawn(self, name, *args, **kwargs):
        with self._guard:
            self._check_owner()
            if self._state != 'starting':
                refuse('Own child можна створити лише під час керованого запуску.')
            process = subprocess.Popen(*args, **kwargs)
            self._children.append((name, process))
            return process

    def track_reader(self, thread, *, streams=()):
        with self._guard:
            if self._state != 'starting' or not isinstance(thread, threading.Thread):
                refuse()
            self._readers.append((thread, tuple(streams)))

    def record_drain(self, process, event):
        expected = {'event': 'bos.server.quiescent', 'runtime': 'waitress',
                    'runtime_version': '3.0.2', 'active': 0, 'queued': 0,
                    'workers': 0, 'sockets_closed': True}
        # Reader threads must remain able to record receipts while the owner
        # waits for child exits under the maintenance guard.
        if not any(name == 'waitress' and child is process for name, child in [*self._children, *self._stopped_handles]):
            refuse('Drain receipt не належить власному Waitress child.')
        if (not isinstance(event, dict) or any(event.get(k) != v for k, v in expected.items())
                or any(type(event.get(k)) is not int for k in ('active', 'queued', 'workers'))
                or event.get('sockets_closed') is not True):
            refuse('Потрібне фактичне завершення writers, workers і sockets.')
        self._drain[process] = (self._owner_token, self._generation)

    def start(self):
        with self._guard:
            self._check_owner()
            self._same_generation()
            if self._state not in ('idle', 'resuming'):
                refuse('Інсталяція вже працює або перебуває в обслуговуванні.')
            self._state = 'starting'
            self._generation += 1
            self._drain, self._stopped, self._stopped_handles = {}, None, []
            try:
                self._start_callback(self)  # Real local startup and health, not an imported receipt.
                if not self._children or any(child.poll() is not None for _, child in self._children):
                    refuse('Власні процеси не підтверджені живими.')
                self._state = 'running'
                self._operation_id = None
                return self.status()
            except BaseException:
                self._state = 'failed'
                self._stop_owned()
                raise

    def _stop_owned(self):
        facts = []
        for name, process in reversed(self._children):
            forced = False
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=self._drain_timeout)
            except subprocess.TimeoutExpired:
                forced = True
                process.kill();process.wait(timeout=3)
            facts.append({'runtime': name, 'exit_code': process.returncode, 'forced': forced})
        self._stopped_handles = list(self._children)
        self._children = []
        for reader, streams in self._readers:
            reader.join(timeout=3)
            if reader.is_alive():
                facts.append({'runtime': 'stdout_reader', 'exit_code': 1, 'forced': False})
            for stream in streams:
                if stream is not None:stream.close()
        self._readers = []
        self._stopped = facts
        return facts

    def quiesce(self, operation_id):
        with self._guard:
            self._check_owner()
            operation_id = canonical_uuid(operation_id)
            if self._state != 'running' or self._lease is not None:
                refuse('Немає власної активної generation для quiesce.')
            self._state, self._operation_id = 'quiescing', operation_id
            facts = self._stop_owned()
            runners = [p for name, p in self._stopped_handles if name == 'waitress']
            clean = facts and all(c['exit_code'] == 0 and not c['forced'] for c in facts)
            drained = runners and all(self._drain.get(p) == (self._owner_token, self._generation) for p in runners)
            if not clean or not drained:
                self._state = 'failed'
                refuse('Quiescence не доведена: lease не видано.')
            self._state = 'quiescent'
            self._lease = QuiescenceLease(_ISSUER, self, operation_id)
            self._lease.assert_live()
            return self._lease

    def _assert_lease(self, lease):
        self._check_owner()
        if (self._lease is not lease or lease._owner is not self or lease._token is not self._owner_token
                or self._state != 'quiescent' or self._operation_id != lease.operation_id
                or self._children or not self._stopped
                or any(c['exit_code'] != 0 or c['forced'] for c in self._stopped)
                or any(p.poll() != 0 for _, p in self._stopped_handles)):
            refuse('Живий owner більше не підтверджує quiescent lease.')

    def release(self, lease):
        with self._guard:
            self._assert_lease(lease)
            self._same_generation()
            self._lease = None  # Invalid before the first resumed child is started.
            self._state = 'resuming'
            return self.start()

    def status(self):
        with self._guard:
            self._check_owner()
            return {'state': self._state, 'installation_id': self.installation_id,
                    'generation': self._generation, 'operation_id': self._operation_id,
                    'own_children': len(self._children), 'stopped': self._stopped}

    def close(self):
        import fcntl
        with self._guard:
            self._lease = None
            if self._children:self._stop_owned()
            self._state = 'closed'
            if self._lock_file is not None and not self._lock_file.closed:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                self._lock_file.close()

    def __exit__(self, kind, value, traceback):
        self.close()


class QuiescenceLease:
    __slots__ = ('_owner', '_token', '_binding')
    def __init__(self, issuer, owner, operation_id):
        if issuer is not _ISSUER or not isinstance(owner, ManagedSupervisor):
            refuse('Lease може видати лише живий керований supervisor.')
        self._owner, self._token = owner, owner._owner_token
        self._binding = (owner.installation_id, owner.target, owner.root_identity, operation_id, owner._pid)
    @property
    def installation_id(self):return self._binding[0]
    @property
    def root(self):return self._binding[1]
    @property
    def root_identity(self):return self._binding[2]
    @property
    def operation_id(self):return self._binding[3]
    def assert_for(self, installation_id, root, operation_id):
        with self._owner._guard:
            if (os.getpid() != self._binding[4] or installation_id != self.installation_id
                    or Path(root) != self.root or operation_id != self.operation_id
                    or self._owner.installation_id != self.installation_id or self._owner.target != self.root
                    or self._owner.root_identity != self.root_identity):
                refuse('Lease належить іншій інсталяції, операції або процесу.')
            self._owner._assert_lease(self)
            return self
    def assert_live(self):return self.assert_for(self.installation_id, self.root, self.operation_id)
    @contextmanager
    def fenced_for(self, installation_id, root, operation_id):
        # Lock order for ledger: its existing generation flock, then this guard.
        # This method never acquires the ledger lock or reads/writes its pointer.
        with self._owner._guard:
            self.assert_for(installation_id, root, operation_id)
            yield self
            self.assert_for(installation_id, root, operation_id)
    def release(self):return self._owner.release(self)
