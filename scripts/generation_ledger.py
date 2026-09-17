"""A10 generation authority, filesystem scope only.

The original A09 installer registry is read-only. No SQL, migration, backup,
process management or HTTP acceptance is implemented here. Activation requires
an actual maintenance-control QuiescenceLease in addition to an issued sealed
filesystem capability. Partial receipts fail closed and are never repaired.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid
from weakref import WeakKeyDictionary

FORMAT = 'BoS-generation-ledger-1'
_LEDGERS = WeakKeyDictionary()
_CANDIDATES = WeakKeyDictionary()
_SEALED = WeakKeyDictionary()
_ACTIVES = WeakKeyDictionary()
_DIRECTORIES = ('operations', 'candidates', 'descriptors', 'sealed', 'activations')


class LedgerRefused(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__('Операцію покоління відхилено: ' + code)


def refuse(code):
    raise LedgerRefused(code)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(',', ':'), allow_nan=False).encode('utf-8') + b'\n'
    except (TypeError, ValueError, UnicodeError):
        refuse('INVALID_METADATA')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def operation(value):
    try:
        if str(uuid.UUID(value)) != value:
            refuse('INVALID_OPERATION_ID')
    except (ValueError, TypeError, AttributeError):
        refuse('INVALID_OPERATION_ID')
    return value


def new_receipt(path, body):
    """Write once, binding the receipt to the actual exclusively created inode."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as handle:
        info = os.fstat(handle.fileno())
        handle.write(canonical({'body': body, 'sha256': digest(body),
                                'identity': [info.st_dev, info.st_ino]}))
        handle.flush()
        os.fsync(handle.fileno())


@dataclass(frozen=True, eq=False)
class CandidateGeneration:
    root: Path
    operation_id: str


@dataclass(frozen=True, eq=False)
class SealedGeneration:
    generation_hash: str
    operation_id: str
    validation_scope: str = 'filesystem'


@dataclass(frozen=True, eq=False)
class ActiveGeneration:
    installation_id: str
    version: str
    generation_hash: str
    target: Path
    code_root: Path
    config_path: Path
    database_path: Path
    media_root: Path
    static_root: Path
    python_path: Path

    def assert_owned(self):
        proof = _ACTIVES.get(self)
        if proof is None or proof[1] != tuple(vars(self).values()):
            refuse('UNISSUED_ACTIVE_CAPABILITY')
        ledger = proof[0]
        with ledger._lock():
            if ledger._active_values() != tuple(vars(self).values()):
                refuse('STALE_ACTIVE_CAPABILITY')


class GenerationLedger:
    @classmethod
    def _original(cls, installer, target, registry, installation_id):
        from scripts.lifecycle_server import load_owned
        if not Path(registry).exists():
            refuse('REGISTRY_MISSING')
        record, release, _, config = load_owned(installer, target=target, registry=registry,
                                               installation_id=installation_id)
        target = installer.safe_path(target, must_exist=True)
        anchor = {'format': FORMAT, 'kind': 'original', 'installation_id': installation_id,
            'root': str(target), 'root_identity': installer.identity(target),
            'registry': str(installer.safe_path(registry, must_exist=True)),
            'registry_record_sha256': digest(record), 'source': record['source'],
            'code_root_identity': installer.identity(release),
            'config_identity': installer.identity(target/'config/server.json'),
            'config_sha256': hashlib.sha256((target/'config/server.json').read_bytes()).hexdigest(),
            'state_identity': installer.identity(target/'state'),
            'database_identity': installer.identity(target/'state/data/bos.sqlite3')}
        return record, config, anchor

    @classmethod
    def create(cls, *, installer, target, registry, installation_id):
        record, config, anchor = cls._original(installer, target, registry, installation_id)
        root = Path(target)/'generations'
        if root.exists():
            refuse('LEDGER_ALREADY_EXISTS')
        root.mkdir(mode=0o700)
        for name in _DIRECTORIES:
            (root/name).mkdir(mode=0o700)
        anchor['ledger_identity'] = installer.identity(root)
        installer.new_file(root/'LOCK', b'')
        anchor['control_identities'] = {name: installer.identity(root/name) for name in (*_DIRECTORIES, 'LOCK')}
        new_receipt(root/'ANCHOR.json', anchor)
        return cls.open(installer=installer, target=target, registry=registry,
                        installation_id=installation_id)

    @classmethod
    def open(cls, *, installer, target, registry, installation_id):
        _, _, expected = cls._original(installer, target, registry, installation_id)
        root = installer.safe_path(Path(target)/'generations', must_exist=True)
        installer.private_directory(root)
        expected['ledger_identity'] = installer.identity(root)
        expected['control_identities'] = {name: installer.identity(root/name) for name in (*_DIRECTORIES, 'LOCK')}
        self = cls()
        self.installer, self.target, self.registry = installer, Path(target), Path(registry)
        self.installation_id, self.root = installation_id, root
        self.anchor = expected
        self.anchor_hash = digest(expected)
        _LEDGERS[self] = (str(root), self.anchor_hash, tuple(expected['ledger_identity']))
        self._guard()
        return self

    def _read(self, path):
        self.installer.private_regular(path)
        raw = path.read_bytes()
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            refuse('TORN_RECEIPT')
        if (type(value) is not dict or set(value) != {'body', 'sha256', 'identity'} or type(value['body']) is not dict
                or value['identity'] != self.installer.identity(path)
                or value['sha256'] != digest(value['body']) or raw != canonical(value)):
            refuse('CHANGED_RECEIPT')
        return value['body']

    def _new(self, path, value):
        self._guard()
        new_receipt(path, value)

    def _guard(self):
        if _LEDGERS.get(self) != (str(self.root), self.anchor_hash,
                                tuple(self.anchor.get('ledger_identity', []))):
            refuse('UNISSUED_LEDGER')
        self.installer.private_directory(self.root)
        if self.installer.identity(self.root) != self.anchor['ledger_identity']:
            refuse('REPLACED_LEDGER')
        _, _, expected = self._original(self.installer, self.target, self.registry, self.installation_id)
        expected['ledger_identity'] = self.installer.identity(self.root)
        expected['control_identities'] = {name: self.installer.identity(self.root/name) for name in (*_DIRECTORIES, 'LOCK')}
        if expected != self.anchor or self._read(self.root/'ANCHOR.json') != self.anchor:
            refuse('CHANGED_ORIGINAL_AUTHORITY')
        allowed = {'ANCHOR.json', 'LOCK', 'operations', 'candidates', 'descriptors',
                   'sealed', 'activations', 'ACTIVE.json'}
        if any(path.name not in allowed for path in self.root.iterdir()):
            refuse('UNKNOWN_LEDGER_CONTENT')
        for name in _DIRECTORIES:
            self.installer.private_directory(self.root/name)
        self.installer.private_regular(self.root/'LOCK')

    @contextmanager
    def _lock(self):
        if os.name != 'posix':
            refuse('PLATFORM_UNVERIFIED')
        import fcntl
        self._guard()
        path = self.root/'LOCK'
        with path.open('rb') as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                refuse('LEDGER_BUSY')
            try:
                if self.installer.identity(path) != [os.fstat(handle.fileno()).st_dev,
                                                      os.fstat(handle.fileno()).st_ino]:
                    refuse('REPLACED_LOCK')
                self._guard()
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _file(self, path):
        self.installer.safe_path(path, must_exist=True)
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            refuse('FILE_OWNERSHIP')
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as handle:
            observed = os.fstat(handle.fileno())
            checksum = hashlib.file_digest(handle, 'sha256').hexdigest()
            after = os.fstat(handle.fileno())
        attributes = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if attributes(before) != attributes(observed) or attributes(observed) != attributes(after) or attributes(after) != attributes(path.lstat()):
            refuse('FILE_CHANGED_DURING_READ')
        return {'identity': [after.st_dev, after.st_ino], 'bytes': after.st_size, 'sha256': checksum}

    def _inventory(self, root):
        self.installer.private_directory(root)
        result = {'directories': {'.': self.installer.identity(root)}, 'files': {}, 'links': {}}
        for path in sorted(root.rglob('*')):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() and relative == 'runtime/lib64' and os.readlink(path) == 'lib':
                self.installer.safe_path(root/'runtime/lib', must_exist=True)
                if not (root/'runtime/lib').is_dir():
                    refuse('RUNTIME_LINK_INVALID')
                result['links'][relative] = {'target': 'lib', 'identity': self.installer.identity(path)}
                continue
            self.installer.safe_path(path, must_exist=True)
            if path.is_dir():
                result['directories'][relative] = self.installer.identity(path)
            else:
                result['files'][relative] = self._file(path)
        return result

    def _source(self, root):
        try:
            return self.installer.source_identity(root)
        except (OSError, ValueError):
            refuse('CODE_SOURCE_INVALID')

    def _descriptor(self, generation_hash):
        if not re.fullmatch('[0-9a-f]{64}', generation_hash):
            refuse('INVALID_GENERATION_HASH')
        path = self.root/'descriptors'/(generation_hash+'.json')
        descriptor = self._read(path)
        if digest(descriptor) != generation_hash or descriptor.get('anchor_hash') != self.anchor_hash:
            refuse('DESCRIPTOR_BINDING')
        claim = self._claim(descriptor.get('operation_id'))
        receipt = self._read(self.root/'sealed'/(descriptor['operation_id']+'.json'))
        if (descriptor.get('operation_receipt_sha256') != digest(claim)
                or descriptor.get('candidate') != claim['candidate']
                or descriptor.get('root_identity') != claim['root_identity']
                or receipt != {'generation_hash': generation_hash,
                               'descriptor_identity': self.installer.identity(path)}):
            refuse('DESCRIPTOR_OWNERSHIP')
        return descriptor

    def _current(self):
        pointer = self.root/'ACTIVE.json'
        history = []
        for path in (self.root/'activations').iterdir():
            entry = self._read(path)
            if path.name != digest(entry)+'.json' or entry.get('anchor_hash') != self.anchor_hash:
                refuse('ACTIVATION_RECEIPT')
            history.append(entry)
        history.sort(key=lambda entry: entry['sequence'])
        previous, generation = self.anchor_hash, self.anchor_hash
        for sequence, entry in enumerate(history, 1):
            if entry['sequence'] != sequence or entry['previous_activation_hash'] != previous or entry['parent_hash'] != generation:
                refuse('ACTIVATION_CHAIN')
            descriptor = self._descriptor(entry['generation_hash'])
            if descriptor['parent_hash'] != generation:
                refuse('GENERATION_CHAIN')
            previous, generation = digest(entry), entry['generation_hash']
        if not history:
            if pointer.exists():
                self._read(pointer)
                refuse('UNISSUED_ACTIVE_POINTER')
            return {'kind': 'original', 'generation_hash': self.anchor_hash,
                    'sequence': 0, 'activation_hash': self.anchor_hash}
        if not pointer.exists() or self._read(pointer) != {'generation_hash': generation, 'activation_hash': previous}:
            refuse('TORN_OR_STALE_ACTIVE_POINTER')
        descriptor = self._descriptor(generation)
        self._check_descriptor_files(descriptor, state_bytes=False)
        return {'kind': 'candidate', 'generation_hash': generation,
                'sequence': len(history), 'activation_hash': previous}

    def current(self):
        with self._lock():
            return self._current()

    def _active_values(self):
        current = self._current()
        if current['kind'] == 'original':
            code = self.target/'releases'/self.anchor['source']['source_sha256']
            config, state, runtime = self.target/'config/server.json', self.target/'state', self.target/'venv'
            version = self.anchor['source']['version']
        else:
            descriptor = self._descriptor(current['generation_hash'])
            root = self.root/descriptor['candidate']
            code, config, state, runtime = root/'code', root/'config/server.json', root/'state', root/'runtime'
            version = descriptor['source']['version']
        python = self.installer.safe_path(runtime/'bin/python', must_exist=True)
        if not python.is_file() or not os.access(python, os.X_OK):
            refuse('GENERATION_PYTHON_UNAVAILABLE')
        return (self.installation_id, version, current['generation_hash'], self.target,
                code, config, state/'data/bos.sqlite3', state/'private', state/'static', python)

    def current_owned(self):
        with self._lock():
            values = self._active_values()
            active = ActiveGeneration(*values)
            _ACTIVES[active] = (self, values)
            return active

    def _claim(self, operation_id):
        claim = self._read(self.root/'operations'/(operation(operation_id)+'.json'))
        if (claim.get('operation_id') != operation_id or claim.get('anchor_hash') != self.anchor_hash
                or claim.get('candidate') != 'candidates/'+operation_id):
            refuse('OPERATION_BINDING')
        root = self.installer.safe_path(self.root/claim['candidate'], must_exist=True)
        self.installer.private_directory(root)
        if self.installer.identity(root) != claim['root_identity']:
            refuse('REPLACED_CANDIDATE')
        return claim

    def _candidate(self, candidate):
        if type(candidate) is not CandidateGeneration or candidate not in _CANDIDATES:
            refuse('UNISSUED_CANDIDATE')
        proof = _CANDIDATES[candidate]
        if proof[:3] != (self, str(candidate.root), candidate.operation_id):
            refuse('WRONG_CANDIDATE_CAPABILITY')
        claim = self._claim(candidate.operation_id)
        if digest(claim) != proof[3]:
            refuse('CHANGED_CANDIDATE_RECEIPT')
        return claim

    def begin(self, *, operation_id, payload, parent_hash):
        operation(operation_id)
        if type(payload) is not dict:
            refuse('INVALID_PAYLOAD')
        with self._lock():
            record_path = self.root/'operations'/(operation_id+'.json')
            if record_path.exists():
                claim = self._claim(operation_id)
                if claim['payload_sha256'] != digest(payload) or claim['parent_hash'] != parent_hash:
                    refuse('OPERATION_PAYLOAD_CONFLICT')
            else:
                if parent_hash != self._current()['generation_hash']:
                    refuse('STALE_PARENT')
                if not isinstance(payload.get('source_sha256'), str) or not re.fullmatch('[0-9a-f]{64}', payload['source_sha256']):
                    refuse('EXPECTED_CODE_HASH_REQUIRED')
                root = self.root/'candidates'/operation_id
                if root.exists():
                    refuse('UNISSUED_CANDIDATE_ROOT')
                self._guard()
                root.mkdir(mode=0o700)
                for name in ('code', 'config', 'state', 'state/data', 'state/private', 'state/static', 'runtime', 'runtime/bin'):
                    (root/name).mkdir(mode=0o700)
                claim = {'format': FORMAT, 'anchor_hash': self.anchor_hash,
                    'operation_id': operation_id, 'payload_sha256': digest(payload),
                    'source_sha256': payload['source_sha256'],
                    'parent_hash': parent_hash, 'candidate': 'candidates/'+operation_id,
                    'root_identity': self.installer.identity(root)}
                self._new(record_path, claim)
            candidate = CandidateGeneration(self.root/claim['candidate'], operation_id)
            _CANDIDATES[candidate] = (self, str(candidate.root), operation_id, digest(claim))
            return candidate

    def expected_config(self, candidate):
        self._guard()
        self._candidate(candidate)
        _, config, _ = self._original(self.installer, self.target, self.registry, self.installation_id)
        state = candidate.root/'state'
        config.update(BOS_INSTALLATION_ROOT=str(state), BOS_DATABASE_PATH=str(state/'data/bos.sqlite3'),
                      BOS_MEDIA_ROOT=str(state/'private'))
        return self.installer.canonical(config)

    def _candidate_descriptor(self, candidate):
        claim = self._candidate(candidate)
        inventory = self._inventory(candidate.root)
        if set(path.name for path in candidate.root.iterdir()) != {'code', 'config', 'state', 'runtime'}:
            refuse('UNKNOWN_CANDIDATE_COMPONENT')
        self.installer.private_regular(candidate.root/'config/server.json')
        self.installer.private_regular(candidate.root/'state/data/bos.sqlite3')
        if (candidate.root/'config/server.json').read_bytes() != self.expected_config(candidate):
            refuse('CONFIG_BINDING')
        source = self._source(candidate.root/'code')
        if not source.get('full_code_package_verified') or source.get('source_sha256') != claim['source_sha256']:
            refuse('FULL_CODE_PACKAGE_REQUIRED')
        python = candidate.root/'runtime/bin/python'
        self._file(python)
        if not os.access(python, os.X_OK):
            refuse('GENERATION_PYTHON_UNAVAILABLE')
        if inventory != self._inventory(candidate.root):
            refuse('CANDIDATE_CHANGED_DURING_VALIDATION')
        return {'format': FORMAT, 'kind': 'candidate', 'validation_scope': 'filesystem',
            'not_checked': ['database_integrity', 'business_reconciliation', 'runtime', 'http'],
            'anchor_hash': self.anchor_hash, 'operation_id': candidate.operation_id,
            'operation_receipt_sha256': digest(claim), 'payload_sha256': claim['payload_sha256'],
            'parent_hash': claim['parent_hash'], 'candidate': claim['candidate'],
            'root_identity': claim['root_identity'], 'source': source, 'inventory': inventory}

    def _check_descriptor_files(self, descriptor, *, state_bytes):
        root = self.root/descriptor['candidate']
        self.installer.private_directory(root)
        if self.installer.identity(root) != descriptor['root_identity']:
            refuse('REPLACED_GENERATION')
        if self._source(root/'code') != descriptor['source']:
            refuse('CHANGED_GENERATION_CODE')
        expected = descriptor['inventory']
        if state_bytes:
            if self._inventory(root) != expected:
                refuse('CHANGED_SEALED_GENERATION')
        else:
            for name in ('code', 'config', 'state', 'state/data', 'state/private', 'state/static', 'runtime', 'runtime/bin'):
                path = self.installer.safe_path(root/name, must_exist=True)
                if self.installer.identity(path) != expected['directories'][name]:
                    refuse('REPLACED_COMPONENT')
            for name in ('config/server.json', 'state/data/bos.sqlite3'):
                path = root/name
                self.installer.private_regular(path)
                if self.installer.identity(path) != expected['files'][name]['identity']:
                    refuse('REPLACED_BOUND_FILE')
            if self._file(root/'config/server.json') != expected['files']['config/server.json']:
                refuse('CHANGED_ACTIVE_CONFIG')
            if self._file(root/'runtime/bin/python') != expected['files']['runtime/bin/python']:
                refuse('CHANGED_ACTIVE_PYTHON')

    def seal(self, candidate):
        with self._lock():
            descriptor = self._candidate_descriptor(candidate)
            generation_hash = digest(descriptor)
            path = self.root/'descriptors'/(generation_hash+'.json')
            sealed_path = self.root/'sealed'/(candidate.operation_id+'.json')
            if sealed_path.exists():
                receipt = self._read(sealed_path)
                if (receipt.get('generation_hash') != generation_hash
                        or self._descriptor(generation_hash) != descriptor
                        or receipt.get('descriptor_identity') != self.installer.identity(path)):
                    refuse('CHANGED_SEALED_RECEIPT')
            else:
                if path.exists():
                    refuse('UNISSUED_DESCRIPTOR')
                self._new(path, descriptor)
                self._new(sealed_path, {'generation_hash': generation_hash,
                    'descriptor_identity': self.installer.identity(path)})
            sealed = SealedGeneration(generation_hash, candidate.operation_id)
            _SEALED[sealed] = (self, generation_hash, candidate.operation_id, 'filesystem')
            return sealed

    def activate(self, sealed, *, lease, operation_id, payload, expected_parent_hash):
        operation(operation_id)
        if (type(sealed) is not SealedGeneration or _SEALED.get(sealed)
                != (self, sealed.generation_hash, sealed.operation_id, 'filesystem')):
            refuse('UNISSUED_SEALED_CAPABILITY')
        try:
            from scripts.maintenance_control import QuiescenceLease
        except ImportError:
            refuse('CONTROL_NOT_IMPLEMENTED')
        if type(lease) is not QuiescenceLease:
            refuse('UNISSUED_QUIESCENCE_LEASE')
        with self._lock(), lease.fenced_for(self.installation_id, self.target, operation_id):
            lease.assert_for(self.installation_id, self.target, operation_id)
            descriptor = self._descriptor(sealed.generation_hash)
            if (operation_id != descriptor['operation_id'] or digest(payload) != descriptor['payload_sha256']
                    or expected_parent_hash != descriptor['parent_hash']):
                refuse('ACTIVATION_PAYLOAD_CONFLICT')
            current = self._current()
            if current['generation_hash'] == sealed.generation_hash:
                return {**current, 'replay': True, 'validation_scope': 'filesystem'}
            if current['generation_hash'] != expected_parent_hash:
                refuse('STALE_PARENT')
            self._check_descriptor_files(descriptor, state_bytes=True)
            receipt = {'format': FORMAT, 'anchor_hash': self.anchor_hash,
                'operation_id': operation_id, 'payload_sha256': digest(payload),
                'sequence': current['sequence']+1, 'previous_activation_hash': current['activation_hash'],
                'parent_hash': expected_parent_hash, 'generation_hash': sealed.generation_hash}
            receipt_hash = digest(receipt)
            lease.assert_for(self.installation_id, self.target, operation_id)
            self._new(self.root/'activations'/(receipt_hash+'.json'), receipt)
            pointer = {'generation_hash': sealed.generation_hash, 'activation_hash': receipt_hash}
            temporary = self.root/('pending-active-'+operation_id+'.json')
            # All source receipts are immutable. A crash before replace leaves
            # an explicit incomplete ledger, not an automatic rollback/repair.
            new_receipt(temporary, pointer)
            lease.assert_for(self.installation_id, self.target, operation_id)
            self._check_descriptor_files(descriptor, state_bytes=True)
            if self.installer.identity(self.root) != self.anchor['ledger_identity']:
                refuse('REPLACED_LEDGER')
            os.replace(temporary, self.root/'ACTIVE.json')
            directory = os.open(self.root, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return {**self._current(), 'replay': False, 'validation_scope': 'filesystem'}
