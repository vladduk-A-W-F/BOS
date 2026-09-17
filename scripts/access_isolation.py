"""Gate-only real commit isolation on an exclusively created SQLite database.

No working database is accepted; no business view or transaction mode is changed.
"""
from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import sqlite3
import tempfile

_ISSUED = {}


class OwnedSweepSQLite:
    def __new__(cls):
        raise TypeError('Only create_new may issue a gate database owner')

    @classmethod
    def create_new(cls, path, project_root):
        from scripts.data_transfer import strict_path
        candidate = Path(path).absolute()
        if '..' in candidate.parts:
            raise ValueError('Gate database path cannot contain parent traversal')
        parent = strict_path(candidate.parent)
        path = parent / candidate.name
        root = Path(project_root).resolve()
        if root == path or root in path.parents:
            raise ValueError('Gate database must be outside the checkout')
        with path.open('xb') as stream:
            os.chmod(path, 0o600)
            info = os.fstat(stream.fileno())
        owner = object.__new__(cls)
        _ISSUED[id(owner)] = {'owner': owner, 'path': path, 'identity': (info.st_dev, info.st_ino)}
        return owner

    def assert_owned(self, connection):
        from scripts.data_transfer import strict_path
        proof = _ISSUED.get(id(self))
        if proof is None or proof['owner'] is not self or type(self) is not OwnedSweepSQLite:
            raise ValueError('No actual new gate database ownership')
        path = strict_path(proof['path'])
        info = path.stat()
        if (info.st_dev, info.st_ino) != proof['identity']:
            raise ValueError('Owned gate database was replaced')
        if connection.vendor != 'sqlite' or str(connection.settings_dict['NAME']) != str(path):
            raise ValueError('Only this actual owned SQLite connection is accepted')
        if connection.in_atomic_block or not connection.get_autocommit():
            raise ValueError('Real commit case requires autocommit outside every atomic block')
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA database_list')
            databases = cursor.fetchall()
        main = [row for row in databases if row[1] == 'main']
        if len(main) != 1 or str(main[0][2]) != str(path) or any(row[1] not in ('main', 'temp') for row in databases):
            raise ValueError('Actual gate database or attached database differs from ownership')

    @contextmanager
    def committed_case(self, connection, source_media):
        from django.test import override_settings
        from scripts.check_document_migration import _rows
        from scripts.data_transfer import media_manifest, strict_path
        self.assert_owned(connection)
        source_media = strict_path(source_media)
        before_rows = _rows(connection)
        before_media = media_manifest(source_media)
        result = {'isolation': 'actual_commit_then_owned_sqlite_restore', 'restored': False}
        with tempfile.TemporaryDirectory(prefix='bos-gate4-owned-case-') as directory:
            root = Path(directory)
            snapshot = root / 'baseline.sqlite3'
            with snapshot.open('xb'):
                pass
            writer = sqlite3.connect(snapshot)
            try:
                connection.connection.backup(writer)
            finally:
                writer.close()
            case_media = root / 'media'
            shutil.copytree(source_media, case_media, copy_function=shutil.copy2)
            if media_manifest(case_media) != before_media:
                raise AssertionError('Copied gate media differs from baseline')
            try:
                with override_settings(MEDIA_ROOT=case_media):
                    self.assert_owned(connection)
                    yield result
                    self.assert_owned(connection)
            finally:
                # Restore only the same file that this issuer created, with no
                # outstanding transaction. Raw SQLite backup preserves all rows,
                # system/session records and sqlite_sequence high-water marks.
                self.assert_owned(connection)
                reader = sqlite3.connect(snapshot.as_uri() + '?mode=ro&immutable=1', uri=True)
                try:
                    reader.backup(connection.connection)
                finally:
                    reader.close()
                self.assert_owned(connection)
                if _rows(connection) != before_rows:
                    raise AssertionError('Gate database rows or high-water marks were not restored')
                if media_manifest(source_media) != before_media:
                    raise AssertionError('Original gate media changed during isolated case')
                result['restored'] = True
