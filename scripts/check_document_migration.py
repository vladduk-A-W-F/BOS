"""A08 SQLite rehearsal: read explicit input copies; write only newly owned copies."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if __name__ == '__main__':
    sys.modules['scripts.check_document_migration'] = sys.modules[__name__]

_ISSUED = {}


def _identity(path):
    info = Path(path).lstat()
    return info.st_dev, info.st_ino


def _path(path, *, directory=False):
    from scripts.data_transfer import strict_path
    result = strict_path(path)
    for item in (result, *result.parents):
        if bool(getattr(item, 'is_junction', lambda: False)()):
            raise ValueError('Junction у шляху репетиції заборонено.')
    if ROOT == result or ROOT in result.parents:
        raise ValueError('Репетиція не використовує файли всередині checkout.')
    if directory != result.is_dir():
        raise ValueError('Шлях репетиції має неправильний тип.')
    return result


class OwnedDocumentCopy:
    """In-process capability issued only after actual exclusive DB/media creation."""
    def __new__(cls, *args, **kwargs):
        raise TypeError('Дозвіл створює лише new_owned_copy після створення власних файлів.')

    def assert_owned(self, connection, media_root):
        issued = _ISSUED.get(id(self))
        if issued is None or issued['capability'] is not self or type(self) is not OwnedDocumentCopy:
            raise ValueError('Дозвіл власної копії відсутній або підроблений.')
        db = _path(issued['database'])
        media = _path(issued['media'], directory=True)
        if _identity(db) != issued['database_identity'] or _identity(media) != issued['media_identity']:
            raise ValueError('Власний файл бази або каталог сховища замінено.')
        if connection.vendor != 'sqlite' or str(connection.settings_dict['NAME']) != str(db):
            raise ValueError('Django підключений до іншої бази; запис заборонено.')
        if Path(media_root) != media:
            raise ValueError('Django використовує інше сховище; запис заборонено.')
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA database_list')
            attached = cursor.fetchall()
        main = [row for row in attached if row[1] == 'main']
        if (len(main) != 1 or str(main[0][2]) != str(db)
                or any(row[1] not in ('main', 'temp') for row in attached)):
            raise ValueError('Фактична SQLite база або attached database не відповідає дозволу.')

    def identity_sha256(self):
        issued = _ISSUED.get(id(self))
        if issued is None or issued['capability'] is not self:
            raise ValueError('Дозвіл копії не видано.')
        return hashlib.sha256(repr((str(issued['database']), issued['database_identity'],
            str(issued['media']), issued['media_identity'])).encode()).hexdigest()


def new_owned_copy(source_db, source_media, work):
    """No caller-provided token/name authorizes existing DBs; every target is new."""
    from scripts.data_transfer import media_manifest
    from scripts.reconcile_data import make_snapshot, source_files
    source_db = _path(source_db)
    source_media = _path(source_media, directory=True)
    work = Path(work).absolute()
    _path(work.parent, directory=True)
    if work == source_media or source_media in work.parents or '..' in work.parts:
        raise ValueError('Каталог результатів не може міститися всередині джерельного сховища.')
    if work.exists() or work.is_symlink() or ROOT in work.parents:
        raise ValueError('Каталог нової репетиції вже існує або не ізольований.')
    source_before = {'database': source_files(source_db), 'media': media_manifest(source_media)}
    for item in source_media.rglob('*'):
        if item.is_file() and item.stat().st_nlink != 1:
            raise ValueError('Пов’язаний hardlink файл джерела не підтримується.')
    work.mkdir(mode=0o700)
    database = work / ('check_' + uuid.uuid4().hex + '.sqlite3')
    media = work / 'media'
    capture = make_snapshot(source_db, database)
    os.chmod(database, 0o600)  # Only this just-created copy, never an existing input.
    shutil.copytree(source_media, media, copy_function=shutil.copy2)
    # copytree preserves source modes (including private 0700/0600 subdirectories).
    # The newly created service root itself is owned by this rehearsal.
    os.chmod(media, 0o700)
    if media_manifest(media) != source_before['media']:
        raise ValueError('Скопійовані файли не відповідають джерелу.')
    after = {'database': source_files(source_db), 'media': media_manifest(source_media)}
    if source_before != after or not capture['source_main_unchanged']:
        raise ValueError('Джерело змінилося; копія не отримала дозволу на запис.')
    capability = object.__new__(OwnedDocumentCopy)
    _ISSUED[id(capability)] = {'capability': capability, 'database': database,
        'database_identity': _identity(database), 'media': media, 'media_identity': _identity(media)}
    return capability, database, media, source_before


def _encode(value):
    if isinstance(value, bytes):
        return {'blob_size': len(value), 'blob_sha256': hashlib.sha256(value).hexdigest()}
    if value is None or type(value) in (str, int, float, bool):
        return value
    return {'python_type': type(value).__name__, 'value': str(value)}


def _rows(connection):
    quote = lambda value: '"' + value.replace('"', '""') + '"'
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        result = {}
        for table in tables:
            cursor.execute('SELECT * FROM ' + quote(table))
            columns = [column[0] for column in cursor.description]
            rows = [dict(zip(columns, [_encode(value) for value in row])) for row in cursor.fetchall()]
            result[table] = sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False))
        cursor.execute('SELECT name, seq FROM sqlite_sequence ORDER BY name')
        sequence = dict(cursor.fetchall())
    return result, sequence


def _preserve(before, after, *, schema=False, mutex_steps=0):
    old, old_sequence = before
    new, new_sequence = after
    if set(old) != set(new):
        raise AssertionError('Склад таблиць змінився.')
    allowed = {'operations_document': {'original_file', 'size'}, 'ai_assistant_chatfile': {'checksum'}}
    for table in old:
        if schema and table == 'django_migrations':
            expected = {(row['app'], row['name']) for row in old[table]}
            actual = {(row['app'], row['name']) for row in new[table]}
            if actual - expected != {('operations', '0006_private_documents'), ('ai_assistant', '0009_private_documents')} - expected:
                raise AssertionError('Застосовано не лише очікувані A08 міграції.')
            if not expected <= actual or any(row not in new[table] for row in old[table]):
                raise AssertionError('Втрачено або змінено історію міграцій, ID чи applied timestamp.')
            continue
        def normalized(rows):
            result = []
            for original in rows:
                row = dict(original)
                if table in allowed:
                    for field in allowed[table]:
                        if schema and old[table] and field in old[table][0]:
                            continue
                        row.pop(field, None)
                if not schema and table == 'operations_configuration' and row.get('key') == 'erp_write':
                    value = json.loads(row['value'])
                    if set(value) != {'revision'}:
                        raise AssertionError('ERP mutex має неочікувані поля.')
                    continue
                result.append(row)
            return sorted(result, key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False))
        if normalized(old[table]) != normalized(new[table]):
            raise AssertionError('Зміни історичних рядків: ' + table)
        if schema and table in allowed:
            old_columns = set(old[table][0]) if old[table] else set()
            for row in new[table]:
                for field in allowed[table] - old_columns:
                    if row[field] is not None:
                        raise AssertionError('Нові поля отримали вигадані історичні значення.')
    if not schema:
        def revision(state):
            rows = [row for row in state['operations_configuration'] if row['key'] == 'erp_write']
            return json.loads(rows[0]['value'])['revision'] if rows else 0
        if revision(new) != revision(old) + mutex_steps:
            raise AssertionError('Неочікувана зміна mutex revision.')
    if not schema:
        old_mutex = [row for row in old['operations_configuration'] if row['key'] == 'erp_write']
        new_mutex = [row for row in new['operations_configuration'] if row['key'] == 'erp_write']
        if old_mutex:
            without_value = lambda rows: [{k: v for k, v in row.items() if k != 'value'} for row in rows]
            if len(old_mutex) != 1 or len(new_mutex) != 1 or without_value(old_mutex) != without_value(new_mutex):
                raise AssertionError('Змінено історичний ID або поля наявного ERP mutex.')
        if not old_mutex:
            expected_id = max(old_sequence.get('operations_configuration', 0),
                max((row['id'] for row in old['operations_configuration']), default=0)) + 1
            if len(new_mutex) != 1 or new_mutex[0]['id'] != expected_id or new_sequence.get('operations_configuration') != expected_id:
                raise AssertionError('Новий mutex має неочікуваний ID або sequence.')
    for table, value in old_sequence.items():
        if schema and table == 'django_migrations':
            continue
        if not schema and table == 'operations_configuration' and not old_mutex:
            continue
        if new_sequence.get(table) != value:
            raise AssertionError('Змінено історичну верхню межу ID: ' + table)


def configure(database, media):
    os.environ.update(DJANGO_SETTINGS_MODULE='verification_settings', BOS_VERIFY_DB='sqlite',
        BOS_TEST_DB_NAME=str(database), BOS_TEST_MEDIA=str(media), PYTHONDONTWRITEBYTECODE='1')
    import django
    from django.conf import settings
    from django.db import connections
    if not settings.configured:
        django.setup()
    else:
        connections.close_all()
        settings.DATABASES['default']['NAME'] = str(database)
        connections['default'].settings_dict['NAME'] = str(database)
        settings.MEDIA_ROOT = str(media)


def rehearse(source_db, source_media, work):
    from scripts.data_transfer import media_manifest
    from scripts.reconcile_data import source_files
    owned, db, media, original = new_owned_copy(source_db, source_media, work)
    configure(db, media)
    from django.core.management import call_command
    from django.db import connection, connections
    from operations.document_migration import plan_migration, apply_plan
    owned.assert_owned(connection, media)
    before_schema = _rows(connection)
    owned.assert_owned(connection, media)
    call_command('migrate', verbosity=0, interactive=False)
    after_schema = _rows(connection)
    _preserve(before_schema, after_schema, schema=True)
    plan = plan_migration(owned_copy=owned)
    (Path(work) / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    if not plan['complete']:
        refusal = {'complete': False, 'stage': 'document_preflight', 'findings': plan['findings'],
            'plan': plan, 'input_unchanged': {'database': source_files(source_db), 'media': media_manifest(source_media)} == original}
        (Path(work) / 'report.json').write_text(json.dumps(refusal, ensure_ascii=False, indent=2), encoding='utf-8')
        connections.close_all()
        raise ValueError('Передперевірка відхилила все перенесення; дивіться report.json із model/ID/reason.')
    first = apply_plan(plan, owned_copy=owned)
    second = apply_plan(plan, owned_copy=owned)
    assert second['new_files'] == 0 and second['observed_chat_checksums'] == []
    _preserve(after_schema, _rows(connection), mutex_steps=2)
    final_rows = _rows(connection)
    connections.close_all()
    restored, restored_db, restored_media, _ = new_owned_copy(db, media, Path(work) / 'restore')
    configure(restored_db, restored_media)
    restored.assert_owned(connection, restored_media)
    assert _rows(connection) == final_rows
    restored_plan = plan_migration(owned_copy=restored)
    assert restored_plan['complete']
    assert all(row['action'] == 'keep' for key in ('documents', 'chat_files') for row in restored_plan[key])
    assert media_manifest(media) == media_manifest(restored_media)
    connections.close_all()
    assert {'database': source_files(source_db), 'media': media_manifest(source_media)} == original
    result = {'complete': True, 'format': 'BoS-A08-document-rehearsal-1', 'backend': 'actual SQLite',
        'input_unchanged': True, 'input_database_files': original['database'],
        'target_database_files': source_files(db), 'restored_database_files': source_files(restored_db),
        'table_count': len(final_rows[0]), 'schema_rows_and_high_water_preserved': True,
        'all_business_rows_preserved': True, 'restore_rows_files_ids_access_preserved': True,
        'first': first, 'replay': second, 'plan': plan,
        'postgres': 'НЕ ЗАПУЩЕНО', 'windows': 'НЕ ЗАПУЩЕНО'}
    (Path(work) / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db', required=True, type=Path)
    parser.add_argument('--source-media', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(rehearse(args.source_db, args.source_media, args.output_dir), ensure_ascii=False))


if __name__ == '__main__':
    main()
