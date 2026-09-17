"""Private immutable Document files. No DB writes and no public URL.

All writes must run under the existing ERP database mutex. ``legacy_blob_bytes``
means the byte total of every stored Document.content BLOB, including archived or
file-bound rows; it must not be replaced with zero during a storage migration.
The caller owns authorization, Document version uniqueness and DB transaction.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
import hashlib
import io
import os
from pathlib import Path
import re
import stat
import threading
from typing import Callable
import uuid

from django.conf import settings
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

MAX_BYTES = 10 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
DEFAULT_QUOTA_BYTES = 1024 * 1024 * 1024
_KEY = re.compile(r"documents/([0-9a-f]{2})/([0-9a-f]{32})\.blob\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class PrivateFileError(ValueError):
    """Expected refusal; its Ukrainian message is safe for the existing API."""


class PrivateFileMissing(PrivateFileError):
    pass


def _io_guard(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except PrivateFileError:
            raise
        except FileNotFoundError as exc:
            raise PrivateFileMissing('Файл документа або приватне сховище відсутні.') from exc
        except OSError as exc:
            raise PrivateFileError('Не вдалося безпечно відкрити приватне сховище документа.') from exc
    return guarded


def _error(message):
    raise PrivateFileError(message)


def _checksum(value):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        _error('Контрольна сума документа відсутня або має неправильний формат.')
    return value


def _integer(value, message):
    if type(value) is not int or value < 0:
        _error(message)
    return value


def _key_parts(name):
    if not isinstance(name, str):
        _error('Некоректний приватний ключ документа.')
    match = _KEY.fullmatch(name)
    if not match or match[1] != match[2][:2]:
        _error('Некоректний приватний ключ документа.')
    return tuple(name.split('/'))


def _link(path):
    return path.is_symlink() or bool(getattr(path, 'is_junction', lambda: False)())


def _check_components(path):
    """Portable check for a service-owned tree; never resolve away a link."""
    for component in reversed((path, *path.parents)):
        if _link(component):
            _error('Сховище документа містить символічне посилання або junction.')


def _private_mode(info, wanted):
    # On Windows chmod does not establish an ACL. The deployment owner must
    # configure a private service-owned directory; actual ACL acceptance is A11.
    if os.name == 'posix' and stat.S_IMODE(info.st_mode) != wanted:
        _error('Права доступу до приватного сховища не відповідають налаштуванню.')


def _regular(info):
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        _error('Очікувався окремий звичайний файл документа.')
    _private_mode(info, 0o600)


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


@dataclass(frozen=True)
class StoredDocument:
    name: str
    size: int
    checksum: str


class _Tree:
    """Anchored POSIX handles; checked exclusive paths on other platforms.

    The portable branch assumes that another local process cannot freely write
    to the private service-owned MEDIA_ROOT. It does not promise an OS security
    boundary against an attacker who already controls that filesystem account.
    """
    def __init__(self, root, *, create=False):
        self.root = Path(root)
        if not self.root.is_absolute() or '..' in self.root.parts:
            _error('Приватне сховище потребує абсолютного шляху без переходів до батьків.')
        _check_components(self.root)
        if create and not self.root.exists():
            # Only this exact configured leaf is created; no existing parent is
            # chmod-ed and no recursive creation outside the private root occurs.
            self.root.mkdir(mode=0o700)
        _check_components(self.root)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode):
            _error('Приватне сховище документів не є каталогом.')
        # MEDIA_ROOT may already contain ordinary Django ChatFile directories.
        # Only our private documents/hash descendants require mode 0700.
        self.root_identity = (info.st_dev, info.st_ino)
        self.anchored = (os.name == 'posix' and hasattr(os, 'O_NOFOLLOW') and
                         os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd)
        self.fd = None
        if self.anchored:
            # Anchor every ancestor too, not just the final MEDIA_ROOT component.
            fd = os.open(self.root.anchor, os.O_RDONLY | os.O_DIRECTORY)
            try:
                for name in self.root.parts[1:]:
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(fd)
                    fd = child
                if (os.fstat(fd).st_dev, os.fstat(fd).st_ino) != (info.st_dev, info.st_ino):
                    _error('Каталог сховища змінився під час відкриття.')
                self.fd = fd
            except BaseException:
                os.close(fd)
                raise

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    @contextmanager
    def directory(self, parts, *, create=False):
        if self.anchored:
            fd = os.dup(self.fd)
            try:
                for part in parts:
                    if create:
                        try:
                            os.mkdir(part, mode=0o700, dir_fd=fd)
                        except FileExistsError:
                            pass
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(fd)
                    fd = child
                    _private_mode(os.fstat(fd), 0o700)
                yield fd
            finally:
                os.close(fd)
        else:
            path = self.root
            _check_components(path)
            for part in parts:
                path = path / part
                if create:
                    try:
                        path.mkdir(mode=0o700)
                    except FileExistsError:
                        pass
                _check_components(path)
                info = path.lstat()
                if not stat.S_ISDIR(info.st_mode):
                    _error('Приватний шлях документа не є каталогом.')
                _private_mode(info, 0o700)
            yield path

    def open_file(self, directory, name, *, create=False):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL if create else os.O_RDONLY
        flags |= getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        if self.anchored:
            fd = os.open(name, flags, mode=0o600, dir_fd=directory)
        else:
            path = directory / name
            _check_components(path)
            fd = os.open(path, flags, mode=0o600)
        try:
            _regular(os.fstat(fd))
        except BaseException:
            os.close(fd)
            raise
        return fd

    def remove_failed_new_file(self, directory, name, opened_info):
        # Only the exact inode exclusively created by this save may be removed.
        if self.anchored:
            current = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (opened_info.st_dev, opened_info.st_ino):
                _error('Новий файл змінився; автоматичне видалення заборонено.')
            os.unlink(name, dir_fd=directory)
        else:
            path = directory / name
            _check_components(path)
            current = path.lstat()
            if (current.st_dev, current.st_ino) != (opened_info.st_dev, opened_info.st_ino):
                _error('Новий файл змінився; автоматичне видалення заборонено.')
            path.unlink()

    def physical_bytes(self):
        """All files, including orphans and other media; no DB-based filtering."""
        def scan_fd(fd):
            total = 0
            for name in os.listdir(fd):
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        total += scan_fd(child)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    total += info.st_size
                else:
                    _error('Сховище містить посилання або нестандартний файл.')
            return total
        def scan_path(path):
            total = 0
            _check_components(path)
            for child in path.iterdir():
                _check_components(child)
                info = child.lstat()
                if stat.S_ISDIR(info.st_mode):
                    total += scan_path(child)
                elif stat.S_ISREG(info.st_mode):
                    total += info.st_size
                else:
                    _error('Сховище містить посилання або нестандартний файл.')
            return total
        return scan_fd(self.fd) if self.anchored else scan_path(self.root)


def legacy_blob_usage(*, using='default'):
    """Read-only byte SUM; all rows, all BLOBs, no migration-time deduction."""
    from django.db.models import BigIntegerField, Sum
    from django.db.models.functions import Length
    from operations.models import Document
    value = Document.objects.using(using).aggregate(
        value=Sum(Length('content'), output_field=BigIntegerField()))['value']
    return _integer(0 if value is None else value, 'Не вдалося визначити обсяг історичних документів.')


@deconstructible
class PrivateDocumentStorage(Storage):
    def __init__(self, *, root=None, quota_bytes=None):
        # Settings are read lazily so migrations and test override_settings work.
        self._root = root
        self._quota = quota_bytes
        self._pending = {}
        self._pending_lock = threading.RLock()

    @property
    def root(self):
        return Path(self._root if self._root is not None else settings.MEDIA_ROOT)

    @property
    def quota(self):
        return _integer(self._quota if self._quota is not None else
                        getattr(settings, 'BOS_DOCUMENT_QUOTA_BYTES', DEFAULT_QUOTA_BYTES),
                        'Квота документів має бути цілим невід’ємним числом байтів.')

    def url(self, name):
        _error('Приватний документ доступний лише через перевірений маршрут завантаження.')

    def path(self, name):
        _error('Прямий шлях приватного документа не видається.')

    def _owned_receipt(self, receipt):
        # Equal/serialized/forged dataclasses are not capabilities. Keep a strong
        # reference so Python cannot recycle the object ID while still pending.
        proof = self._pending.get(id(receipt))
        if proof is None or proof['receipt'] is not receipt or type(receipt) is not StoredDocument:
            _error('Немає права очищати цей файл після скасованого запису.')
        if (receipt.name, receipt.size, receipt.checksum) != proof['values']:
            _error('Дані квитанції нового файла змінилися; очищення заборонено.')
        return proof

    def finalize(self, receipt):
        """Revoke cleanup only after the DB commit (transaction.on_commit).

        No file write/read here: a committed file can never again be deleted
        through this transient receipt. This is not a general storage delete.
        """
        with self._pending_lock:
            self._owned_receipt(receipt)
            del self._pending[id(receipt)]

    @_io_guard
    def discard_new(self, receipt):
        """Remove only our still-pending exact file after a confirmed DB rollback.

        Caller must establish that the DB transaction rolled back. The module
        deliberately never deletes DB records or queries an unrelated database.
        Crash orphans lack this in-memory capability and remain quota-counted.
        """
        with self._pending_lock:
            proof = self._owned_receipt(receipt)
            tree = _Tree(proof['root'])
            try:
                if tree.root_identity != proof['root_identity']:
                    _error('Корінь сховища змінився; очищення нового файла заборонено.')
                parts = _key_parts(receipt.name)
                with tree.directory(parts[:-1]) as directory:
                    fd = tree.open_file(directory, parts[-1])
                    with os.fdopen(fd, 'rb') as content:
                        before = os.fstat(content.fileno())
                        if (before.st_dev, before.st_ino) != proof['inode']:
                            _error('Новий файл було підмінено; очищення заборонено.')
                        if before.st_size != receipt.size:
                            _error('Новий файл змінився; очищення заборонено.')
                        digest = hashlib.sha256()
                        size = 0
                        while True:
                            block = content.read(CHUNK_BYTES)
                            if not block:
                                break
                            size += len(block)
                            if size > receipt.size:
                                _error('Новий файл змінився; очищення заборонено.')
                            digest.update(block)
                        if (_identity(before) != _identity(os.fstat(content.fileno())) or
                                size != receipt.size or digest.hexdigest() != receipt.checksum):
                            _error('Новий файл змінився; очищення заборонено.')
                    # Rechecks inode through the same anchored directory handle.
                    tree.remove_failed_new_file(directory, parts[-1], before)
                    del self._pending[id(receipt)]
                    if tree.anchored:
                        os.fsync(directory)
            finally:
                tree.close()

    def delete(self, name):
        _error('Видалення незмінного документа через сховище заборонено.')

    def save(self, name, content, max_length=None):
        _error('Збереження документа потребує перевіреної контрольної суми.')

    def _open(self, name, mode='rb'):
        _error('Читання документа потребує перевіреної контрольної суми.')

    def _save(self, name, content):
        _error('Збереження документа потребує перевіреної контрольної суми.')

    def exists(self, name):
        # Safe lookup for FileField consumers, without returning unverified bytes.
        try:
            self.size(name)
            return True
        except PrivateFileMissing:
            return False

    @_io_guard
    def size(self, name):
        parts = _key_parts(name)
        tree = _Tree(self.root)
        try:
            with tree.directory(parts[:-1]) as directory:
                fd = tree.open_file(directory, parts[-1])
                try:
                    return os.fstat(fd).st_size
                finally:
                    os.close(fd)
        finally:
            tree.close()

    @_io_guard
    def usage(self, *, legacy_blob_bytes: int | Callable[[], int]):
        tree = _Tree(self.root, create=True)
        try:
            legacy = legacy_blob_bytes() if callable(legacy_blob_bytes) else legacy_blob_bytes
            legacy = _integer(legacy, 'Обсяг історичних документів не визначено; запис заборонено.')
            physical = tree.physical_bytes()
            return {'physical_bytes': physical, 'legacy_blob_bytes': legacy,
                    'total_bytes': physical + legacy, 'quota_bytes': self.quota}
        finally:
            tree.close()

    @_io_guard
    def save_verified(self, content, checksum, *, legacy_blob_bytes: int | Callable[[], int]):
        """Exclusive write. Caller holds ERP mutex; never supply an old usage total.

        ``content`` is binary bytes or a binary stream at its current position.
        Successful bytes are immutable. On a DB rollback call discard_new(receipt);
        after commit call finalize(receipt). A process crash may leave an orphan,
        which remains charged to quota until separately reviewed maintenance.
        """
        checksum = _checksum(checksum)
        if isinstance(content, (bytes, bytearray, memoryview)):
            content = io.BytesIO(bytes(content))
        if not callable(getattr(content, 'read', None)):
            _error('Очікувався двійковий вміст документа.')
        tree = _Tree(self.root, create=True)
        try:
            legacy = legacy_blob_bytes() if callable(legacy_blob_bytes) else legacy_blob_bytes
            legacy = _integer(legacy, 'Обсяг історичних документів не визначено; запис заборонено.')
            available = self.quota - tree.physical_bytes() - legacy
            if available < 0:
                _error('Квоту сховища документів вичерпано.')
            token = uuid.uuid4().hex
            name = f'documents/{token[:2]}/{token}.blob'
            parts = _key_parts(name)
            with tree.directory(parts[:-1], create=True) as directory:
                fd = tree.open_file(directory, parts[-1], create=True)
                created = os.fstat(fd)
                try:
                    total = 0
                    digest = hashlib.sha256()
                    with os.fdopen(fd, 'wb') as output:
                        while True:
                            block = content.read(CHUNK_BYTES)
                            if not isinstance(block, bytes):
                                _error('Потік документа повинен повертати двійкові байти.')
                            if not block:
                                break
                            total += len(block)
                            if total > MAX_BYTES:
                                _error('Файл перевищує 10 МБ.')
                            if total > available:
                                _error('Квоту сховища документів вичерпано.')
                            digest.update(block)
                            output.write(block)
                        if digest.hexdigest() != checksum:
                            _error('Контрольна сума документа не збігається; файл не збережено.')
                        output.flush()
                        os.fsync(output.fileno())
                    if tree.anchored:
                        os.fsync(directory)
                    # Confirm the actual persisted bytes before any DB binding.
                    with self.open_verified(name, checksum, expected_size=total):
                        pass
                    receipt = StoredDocument(name, total, checksum)
                    with self._pending_lock:
                        self._pending[id(receipt)] = {
                            'receipt': receipt, 'values': (name, total, checksum),
                            'root': tree.root, 'root_identity': tree.root_identity,
                            'inode': (created.st_dev, created.st_ino),
                        }
                    return receipt
                except BaseException:
                    tree.remove_failed_new_file(directory, parts[-1], created)
                    raise
        finally:
            tree.close()

    @_io_guard
    def open_verified(self, name, checksum, *, expected_size=None):
        """Hash the actually opened bytes into a private buffer before returning.

        No lazy iterator reaches the response before SHA validation. The returned
        BytesIO cannot be changed by subsequent filesystem edits.
        """
        checksum = _checksum(checksum)
        parts = _key_parts(name)
        tree = _Tree(self.root)
        try:
            with tree.directory(parts[:-1]) as directory:
                fd = tree.open_file(directory, parts[-1])
                with os.fdopen(fd, 'rb') as source:
                    before = os.fstat(source.fileno())
                    if expected_size is not None:
                        _integer(expected_size, 'Збережений розмір документа має неправильний формат.')
                        if expected_size != before.st_size:
                            _error('Розмір документа не збігається зі збереженим значенням.')
                    if before.st_size > MAX_BYTES:
                        _error('Збережений файл перевищує дозволений розмір; потрібна перевірка.')
                    digest = hashlib.sha256()
                    buffer = io.BytesIO()
                    total = 0
                    while True:
                        block = source.read(CHUNK_BYTES)
                        if not block:
                            break
                        total += len(block)
                        if total > MAX_BYTES:
                            _error('Збережений файл змінився або перевищує дозволений розмір.')
                        digest.update(block)
                        buffer.write(block)
                    if _identity(before) != _identity(os.fstat(source.fileno())) or total != before.st_size:
                        _error('Документ змінився під час читання; видачу зупинено.')
                    if digest.hexdigest() != checksum:
                        _error('Контрольна сума документа не збігається; видачу зупинено.')
                    buffer.seek(0)
                    return buffer
        finally:
            tree.close()

    def read_verified(self, name, checksum, *, expected_size=None):
        with self.open_verified(name, checksum, expected_size=expected_size) as content:
            return content.read()


private_document_storage = PrivateDocumentStorage()


def verified_document_bytes(document, *, storage=None):
    """Current FileField wins; absence/corruption never falls back to legacy data.

    For legacy rows only: a nonempty BLOB must itself match SHA; an empty BLOB
    with SHA(empty) is truly empty; otherwise exact UTF-8 text may be used only
    when its SHA matches. Missing/corrupt checksums never infer or repair bytes.
    """
    checksum = _checksum(document.checksum)
    field = getattr(document, 'original_file', None)
    name = getattr(field, 'name', field) if field is not None else ''
    if name:
        size = _integer(getattr(document, 'size', None),
                        'Приватний документ не має точного збереженого розміру; потрібна перевірка.')
        selected = storage or getattr(field, 'storage', None) or private_document_storage
        try:
            return selected.read_verified(name, checksum, expected_size=size)
        except PrivateFileMissing as exc:
            raise PrivateFileError('Файл документа відсутній; потрібне відновлення з перевіреної копії.') from exc
    raw = getattr(document, 'content', b'')
    if raw is None:
        raw = b''
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        _error('Історичний двійковий вміст документа має неправильний формат.')
    raw = bytes(raw)
    if raw:
        if hashlib.sha256(raw).hexdigest() != checksum:
            _error('Контрольна сума історичного документа не збігається; видачу зупинено.')
        return raw
    if hashlib.sha256(b'').hexdigest() == checksum:
        return b''
    text = getattr(document, 'text', '')
    if not isinstance(text, str):
        _error('Історичний текст документа має неправильний формат.')
    try:
        encoded = text.encode('utf-8')
    except UnicodeError as exc:
        raise PrivateFileError('Історичний текст документа не кодується у UTF-8.') from exc
    if hashlib.sha256(encoded).hexdigest() != checksum:
        _error('Оригінал документа відсутній або його контрольна сума не збігається.')
    return encoded
