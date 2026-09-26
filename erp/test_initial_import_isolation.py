"""Fixture-boundary regressions; fake connections never contact a source DB."""
from contextlib import contextmanager, ExitStack
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase as AssertionCase
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from erp import test_initial_import as fixture_module


class InitialImportIsolationTests(SimpleTestCase):
    @contextmanager
    def fixture_boundary(self, backend='postgres', source=None, active=None,
                         actual=None, vendor=None, environment=None,
                         loaded_profile=None):
        if source is None:
            source = ('bos_verify_0123456789abcdef' if backend == 'postgres'
                      else '/synthetic/check_0123456789abcdef0123456789abcdef.sqlite3')
        if active is None:
            active = ('test_' + source if backend == 'postgres'
                      else source + '_django_test')
        if actual is None:
            actual = active
        engine = 'postgresql' if backend == 'postgres' else 'sqlite3'
        cursor = MagicMock()
        cursor.fetchone.return_value = (actual,)
        cursor.fetchall.return_value = [(0, 'main', actual)]
        connection = SimpleNamespace(
            vendor=vendor or ('postgresql' if backend == 'postgres' else 'sqlite'),
            alias='default', settings_dict={
                'ENGINE': 'django.db.backends.' + engine, 'NAME': active},
            cursor=MagicMock())
        connection.cursor.return_value.__enter__.return_value = cursor
        env = dict(DJANGO_SETTINGS_MODULE='verification_settings',
                   BOS_VERIFY_DB=backend, BOS_TEST_DB_NAME=source,
                   BOS_PG_DISPOSABLE='1', BOS_PGHOST='synthetic.invalid',
                   BOS_PGUSER='synthetic', BOS_PGPASSWORD='synthetic')
        env.update(environment or {})
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, env))
            if loaded_profile is not None:
                stack.enter_context(override_settings(SETTINGS_MODULE=loaded_profile))
            stack.enter_context(patch.object(fixture_module, 'connection', connection))
            writes = [stack.enter_context(patch.object(fixture_module, name))
                      for name in ('Client', 'login_test_client', 'Employee', 'Configuration')]
            yield AssertionCase(), connection, cursor, writes

    def assert_refused_before_writes(self, **kwargs):
        with self.fixture_boundary(**kwargs) as (fixture, connection, cursor, writes):
            with self.assertRaises((AssertionError, RuntimeError)):
                fixture_module.InitialImportFixture.setUp(fixture)
            for writer in writes:
                self.assertEqual(writer.mock_calls, [], 'Fixture ran before isolation was proved')

    def test_accepts_exact_postgres_test_database(self):
        with self.fixture_boundary() as (fixture, connection, cursor, writes):
            fixture_module.InitialImportFixture.setUp(fixture)
            writes[1].assert_called_once()
            writes[2].objects.create.assert_called_once()

    def test_accepts_exact_file_sqlite_test_database(self):
        with self.fixture_boundary(backend='sqlite') as (fixture, connection, cursor, writes):
            fixture_module.InitialImportFixture.setUp(fixture)
            writes[1].assert_called_once()

    def test_accepts_django_memory_sqlite_database(self):
        with self.fixture_boundary(backend='sqlite', source=':memory:',
                active='file:memorydb_default?mode=memory&cache=shared',
                actual='') as (fixture, connection, cursor, writes):
            fixture_module.InitialImportFixture.setUp(fixture)
            writes[1].assert_called_once()

    def test_rejects_environment_or_loaded_working_profile(self):
        self.assert_refused_before_writes(backend='sqlite',
            environment={'DJANGO_SETTINGS_MODULE': 'demo_settings'})
        self.assert_refused_before_writes(backend='sqlite', loaded_profile='demo_settings')

    def test_rejects_source_and_unrelated_databases(self):
        for backend, source in (
                ('postgres', 'bos_verify_0123456789abcdef'),
                ('sqlite', '/synthetic/check_0123456789abcdef0123456789abcdef.sqlite3')):
            for active in (source, 'test_unrelated', source + '_other'):
                with self.subTest(backend=backend, active=active):
                    self.assert_refused_before_writes(backend=backend, source=source, active=active)

    def test_rejects_unknown_or_mismatched_backend(self):
        self.assert_refused_before_writes(backend='sqlite', environment={'BOS_VERIFY_DB': 'unknown'})
        self.assert_refused_before_writes(backend='sqlite', vendor='postgresql')

    def test_postgres_requires_disposable_marker_and_exact_source_name(self):
        self.assert_refused_before_writes(environment={'BOS_PG_DISPOSABLE': '0'})
        self.assert_refused_before_writes(source='bos_verify_arbitrary')

    def test_rejects_unissued_sqlite_source_name(self):
        self.assert_refused_before_writes(backend='sqlite', source='/synthetic/check_working.sqlite3')

    def test_rejects_live_connection_to_source_despite_test_settings(self):
        self.assert_refused_before_writes(actual='bos_verify_0123456789abcdef')
        self.assert_refused_before_writes(backend='sqlite',
            actual='/synthetic/check_0123456789abcdef0123456789abcdef.sqlite3')
        self.assert_refused_before_writes(backend='sqlite', source=':memory:',
            active='file:memorydb_default?mode=memory&cache=shared', actual='/synthetic/working.sqlite3')

    def test_rejects_sqlite_source_aliases_without_changing_source_bytes(self):
        with tempfile.TemporaryDirectory(prefix='bos-import-guard-') as directory:
            source = Path(directory) / 'check_0123456789abcdef0123456789abcdef.sqlite3'
            source.write_bytes(b'synthetic unchanged source canary')
            test_path = Path(str(source) + '_django_test')
            for kind in ('symlink', 'hardlink'):
                with self.subTest(kind=kind):
                    if kind == 'symlink':
                        test_path.symlink_to(source)
                    else:
                        test_path.hardlink_to(source)
                    try:
                        self.assert_refused_before_writes(backend='sqlite', source=str(source))
                        self.assertEqual(source.read_bytes(), b'synthetic unchanged source canary')
                    finally:
                        test_path.unlink()
