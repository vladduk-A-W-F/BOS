"""A08 document migration on an owned rehearsal copy only; no production entrypoint."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat

from django.conf import settings
from django.db import connection, transaction

from operations.private_storage import (
    CHUNK_BYTES, MAX_BYTES, PrivateFileError, _Tree, _check_components,
    legacy_blob_usage, private_document_storage, verified_document_bytes,
)


def _fail(message):
    raise PrivateFileError(message)


def _guard(owned_copy):
    # Import the canonical issuer, not a duck-typed or user-supplied guard.
    from scripts.check_document_migration import OwnedDocumentCopy
    if type(owned_copy) is not OwnedDocumentCopy:
        _fail('Перенесення дозволене лише на щойно створеній власній копії.')
    OwnedDocumentCopy.assert_owned(owned_copy, connection, Path(settings.MEDIA_ROOT))
    return OwnedDocumentCopy.identity_sha256(owned_copy)


def _json(value):
    def encode(item):
        if isinstance(item, (bytes, bytearray, memoryview)):
            return {'binary_sha256': hashlib.sha256(bytes(item)).hexdigest(), 'size': len(item)}
        return str(item)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=encode)


def _digest(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _preserved(model, row, omitted):
    return _digest({field.attname: getattr(row, field.attname)
                    for field in model._meta.concrete_fields if field.name not in omitted})


def _read_chat_file(row):
    """Observe exact legacy bytes; nullable historic SHA is not an authenticity claim."""
    name = row.file.name
    path = PurePosixPath(name)
    if (not name or '\\' in name or path.is_absolute() or '..' in path.parts
            or str(path) != name or path.parts[0] != 'chat_files'):
        _fail('Архівний файл чату має неприпустимий шлях.')
    if type(row.size) is not int or not 0 <= row.size <= MAX_BYTES:
        _fail('Архівний файл чату має неприпустимий збережений розмір.')
    root = Path(settings.MEDIA_ROOT)
    _check_components(root)
    actual = root.joinpath(*path.parts)
    _check_components(actual)
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    directory_fd = None
    try:
        if os.name == 'posix' and hasattr(os, 'O_NOFOLLOW') and os.open in os.supports_dir_fd:
            directory_fd = os.open(root.anchor, os.O_RDONLY | os.O_DIRECTORY)
            for part in root.parts[1:] + path.parts[:-1]:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
                os.close(directory_fd)
                directory_fd = next_fd
            fd = os.open(path.parts[-1], flags, dir_fd=directory_fd)
        else:
            fd = os.open(actual, flags)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != row.size:
                _fail('Розмір або тип архівного файла чату не відповідає запису.')
            content = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
            identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if identity(before) != identity(after) or len(content) != row.size:
                _fail('Архівний файл чату змінився під час перевірки.')
    except OSError as exc:
        raise PrivateFileError('Не вдалося перевірити архівний файл чату.') from exc
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
    checksum = hashlib.sha256(content).hexdigest()
    if row.checksum not in (None, '', checksum):
        _fail('Контрольна сума архівного файла чату не збігається.')
    return checksum


def _plan(*, owned_copy, check_quota=True):
    _guard(owned_copy)
    from operations.models import Document
    from ai_assistant.models import ChatFile
    documents = []
    findings = []
    additional = 0
    for row in Document.objects.order_by('pk'):
        try:
            bound = bool(row.original_file.name)
            if bound and (type(row.size) is not int or row.size < 0):
                _fail('Для приватного документа відсутній перевірений збережений розмір.')
            content = verified_document_bytes(row)
            if len(content) > MAX_BYTES:
                _fail('Історичний документ перевищує 10 МБ; автоматичне перенесення зупинено.')
            if not bound:
                additional += len(content)
            basis = ('private_file' if bound else 'legacy_blob' if bytes(row.content or b'')
                     else 'empty_original' if not content else 'exact_utf8_text')
            documents.append({'id': row.pk, 'source_key': row.original_file.name or '',
                'sha256': row.checksum, 'size': len(content), 'action': 'keep' if bound else 'copy',
                'checksum_basis': basis,
                'preserved_sha256': _preserved(Document, row, {'original_file', 'size'})})
        except PrivateFileError:
            findings.append({'model': 'operations.Document', 'id': row.pk,
                'reason': 'DOCUMENT_BYTES_SIZE_OR_CHECKSUM_INVALID'})
    chats = []
    for row in ChatFile.objects.order_by('pk'):
        try:
            checksum = _read_chat_file(row)
            chats.append({'id': row.pk, 'source_key': row.file.name, 'sha256': checksum, 'size': row.size,
                'declared_sha256': row.checksum or '',
                'action': 'keep' if row.checksum else 'record_observed_checksum',
                'historical_authenticity_verified': False,
                'checksum_basis': 'matched_stored_sha256' if row.checksum else 'observed_current_bytes',
                'preserved_sha256': _preserved(ChatFile, row, {'checksum'})})
        except PrivateFileError:
            findings.append({'model': 'ai_assistant.ChatFile', 'id': row.pk,
                'reason': 'CHAT_BYTES_SIZE_OR_CHECKSUM_INVALID'})
    tree = _Tree(Path(settings.MEDIA_ROOT))
    try:
        physical = tree.physical_bytes()
    finally:
        tree.close()
    legacy = legacy_blob_usage()
    quota = private_document_storage.quota
    if check_quota and physical + legacy + additional > quota:
        findings.append({'model': 'storage', 'id': None, 'reason': 'TOTAL_MIGRATION_QUOTA_EXCEEDED'})
    result = {'format': 'BoS-A08-document-plan-1', 'owned_copy_sha256': _guard(owned_copy),
        'complete': not findings, 'findings': findings,
        'documents': documents, 'chat_files': chats,
        'usage': {'physical_bytes': physical, 'legacy_blob_bytes': legacy,
                  'additional_bytes': additional, 'quota_bytes': quota}}
    result['plan_sha256'] = _digest(result)
    return result


def plan_migration(*, owned_copy):
    """Read only; no repair, mkdir, checksum invention or partial acceptance."""
    return _plan(owned_copy=owned_copy)


def _compatible(expected, current):
    if not isinstance(expected, dict) or expected.get('format') != 'BoS-A08-document-plan-1':
        _fail('План перенесення має неправильний формат.')
    if expected.get('plan_sha256') != _digest({k: v for k, v in expected.items() if k != 'plan_sha256'}):
        _fail('План перенесення змінено після перевірки.')
    if not expected.get('complete') or not current.get('complete'):
        _fail('Передперевірка виявила конфлікти; усе перенесення відхилено.')
    if expected.get('owned_copy_sha256') != current.get('owned_copy_sha256'):
        _fail('План видано для іншої власної копії.')
    for section in ('documents', 'chat_files'):
        old = {row['id']: row for row in expected.get(section, [])}
        new = {row['id']: row for row in current[section]}
        if set(old) != set(new) or len(old) != len(expected.get(section, [])):
            _fail('Склад документів змінився; потрібна нова перевірка.')
        for identity, previous in old.items():
            actual = new[identity]
            if any(actual[field] != previous[field] for field in ('sha256', 'size', 'preserved_sha256')):
                _fail('Дані документа змінилися; старий план не застосовано.')
            if section == 'chat_files' and previous['declared_sha256'] and previous['declared_sha256'] != actual['declared_sha256']:
                _fail('Історична контрольна сума архівного файла змінена або видалена.')
            if previous['source_key'] and previous['source_key'] != actual['source_key']:
                _fail('Прив’язка документа змінилася; старий план не застосовано.')


def apply_plan(plan, *, owned_copy):
    """One durable transaction; only issued new files can be cleaned on rollback."""
    _guard(owned_copy)
    if connection.in_atomic_block:
        _fail('Перенесення потребує власної зовнішньої транзакції.')
    from operations.models import Document
    from ai_assistant.models import ChatFile
    from erp.service import write_lock
    pending = []
    committed = False

    def complete():
        nonlocal committed
        committed = True
        for receipt in pending:
            private_document_storage.finalize(receipt)

    try:
        with transaction.atomic(durable=True):
            _guard(owned_copy)
            write_lock()
            current = _plan(owned_copy=owned_copy)
            _compatible(plan, current)
            bindings = []
            for entry in current['documents']:
                if entry['action'] == 'copy':
                    _guard(owned_copy)
                    row = Document.objects.get(pk=entry['id'])
                    receipt = private_document_storage.save_verified(
                        verified_document_bytes(row), entry['sha256'], legacy_blob_bytes=legacy_blob_usage)
                    pending.append(receipt)
                    bindings.append((entry['id'], receipt))
            # Re-read every source after staging, before the first binding. Staged
            # bytes already consume quota; do not count them a second time here.
            _compatible(plan, _plan(owned_copy=owned_copy, check_quota=False))
            for identity, receipt in bindings:
                _guard(owned_copy)
                Document.objects.filter(pk=identity).update(original_file=receipt.name, size=receipt.size)
            observed = []
            for entry in current['chat_files']:
                if entry['action'] != 'keep':
                    _guard(owned_copy)
                    ChatFile.objects.filter(pk=entry['id']).update(checksum=entry['sha256'])
                    observed.append(entry['id'])
            after = _plan(owned_copy=owned_copy)
            _compatible(plan, after)
            if any(entry['action'] != 'keep' for section in ('documents', 'chat_files') for entry in after[section]):
                _fail('Перенесення не завершило усі прив’язки; транзакцію скасовано.')
            transaction.on_commit(complete)
            result = {'plan_sha256': plan['plan_sha256'], 'new_files': len(bindings),
                'observed_chat_checksums': observed,
                'documents': [dict(id=row['id'], target_key=row['source_key'], sha256=row['sha256'], size=row['size'])
                              for row in after['documents']],
                'historical_blobs_preserved': True, 'historical_chat_authenticity_claimed': False}
        return result
    except BaseException:
        if not committed:
            cleanup_errors = []
            for receipt in reversed(pending):
                try:
                    private_document_storage.discard_new(receipt)
                except Exception as exc:
                    cleanup_errors.append(str(exc))
            if cleanup_errors:
                raise PrivateFileError('Відкат бази виконано; нові файли потребують окремої перевірки очищення.')
        raise
