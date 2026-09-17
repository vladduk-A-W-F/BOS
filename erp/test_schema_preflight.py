"""A07: actual migrated SQLite fixtures, never a configured working database."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

from django.test import SimpleTestCase

from scripts.schema_preflight import inspect_schema


MIGRATE_FRESH = r'''
import json, os, sqlite3, sys
from pathlib import Path
source = Path(os.environ['BOS_TEST_DB_NAME'])
assert source.parent.is_dir() and not source.exists()
assert source.name in ('latest.sqlite3', 'historical.sqlite3')
import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
executor = MigrationExecutor(connection)
targets = executor.loader.graph.leaf_nodes()
if sys.argv[1] == 'historical':
    # C01 tasks0005 depends on ERP0005; retain the actual pre-C01 graph here.
    old = {'erp':'0001_initial', 'finance':'0006_financialintent',
           'operations':'0004_alter_document_options_document_access_level',
           'tasks':'0004_task_branch'}
    targets = [(app, old.get(app, name)) for app, name in targets]
executor.migrate(targets)
connection.close()
print(json.dumps({'backend':'sqlite','version':sqlite3.sqlite_version,'targets':targets}))
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rebuild_lot(connection, transform):
    source = connection.execute("SELECT sql FROM sqlite_master WHERE name='erp_lot'").fetchone()[0]
    indexes = [row[0] for row in connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='erp_lot' AND sql IS NOT NULL")]
    changed = transform(source)
    if changed == source:
        raise AssertionError('Drift regression did not modify actual SQL')
    connection.execute(changed.replace('CREATE TABLE "erp_lot"', 'CREATE TABLE "a07_lot_rebuilt"', 1))
    connection.execute('INSERT INTO a07_lot_rebuilt SELECT * FROM erp_lot')
    connection.execute('DROP TABLE erp_lot')
    connection.execute('ALTER TABLE a07_lot_rebuilt RENAME TO erp_lot')
    for statement in indexes:
        connection.execute(statement)


class SnapshotSchemaPreflightTests(SimpleTestCase):
    """Subprocess fixtures isolate migration execution from runner-owned DBs."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.storage = tempfile.TemporaryDirectory(prefix='bos_verify_schema_')
        cls.addClassCleanup(cls.storage.cleanup)
        cls.root = Path(cls.storage.name)
        checkout = Path(__file__).resolve().parents[1]
        cls.receipts = {}
        for profile in ('latest', 'historical'):
            path = cls.root / (profile + '.sqlite3')
            env = dict(os.environ, DJANGO_SETTINGS_MODULE='verification_settings',
                       BOS_VERIFY_DB='sqlite', BOS_TEST_DB_NAME=str(path),
                       BOS_TEST_MEDIA=str(cls.root / 'media'), BOS_DATA_MODE='working',
                       PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(checkout))
            process = subprocess.run([sys.executable, '-B', '-c', MIGRATE_FRESH, profile],
                                     cwd=checkout, env=env, text=True, capture_output=True, timeout=90)
            if process.returncode:
                raise AssertionError('Synthetic migration failed:\n' + process.stdout + process.stderr)
            cls.receipts[profile] = json.loads(process.stdout.strip().splitlines()[-1])
            if cls.receipts[profile]['backend'] != 'sqlite':
                raise AssertionError('The required fixture is not an actual SQLite database')
        cls.original_sha = {profile: sha(cls.root / (profile + '.sqlite3')) for profile in cls.receipts}

    def setUp(self):
        self.snapshot = self.root / (self._testMethodName + '.sqlite3')
        shutil.copyfile(self.root / 'latest.sqlite3', self.snapshot)

    def inspect(self, path=None):
        path = path or self.snapshot
        before = sha(path)
        result = inspect_schema(path)
        self.assertEqual(sha(path), before)
        self.assertTrue(result.get('source_unchanged'), result)
        for profile, expected in self.original_sha.items():
            self.assertEqual(sha(self.root / (profile + '.sqlite3')), expected)
        return result

    def mutate(self, callback):
        with closing(sqlite3.connect(self.snapshot)) as connection:
            connection.execute('PRAGMA foreign_keys=OFF')
            callback(connection)
            connection.commit()

    def assert_refused(self, code):
        result = self.inspect()
        self.assertFalse(result['complete'], result)
        self.assertFalse(result['can_migrate'], result)
        self.assertIn(code, [finding['code'] for finding in result['findings']], result)

    def test_latest_schema_from_actual_migrations_is_accepted(self):
        result = self.inspect()
        self.assertTrue(result['complete'], result['findings'])
        self.assertEqual(result['profile'], 'latest')
        self.assertEqual(result['findings'], [])
        self.assertIn('django_migrations', result['tables'])
        self.assertEqual([c['name'] for c in result['tables']['django_migrations']['columns']],
                         ['id', 'app', 'name', 'applied'])
        self.assertEqual(result['migration_state_hash'], result['migration_state']['hash'])
        self.assertEqual(set(result['tables']), set(result['actual_schema']))

    def test_known_historical_state_uses_its_actual_project_state(self):
        result = self.inspect(self.root / 'historical.sqlite3')
        self.assertTrue(result['complete'], result['findings'])
        self.assertEqual(result['profile'], 'historical')
        self.assertEqual(result['findings'], [])
        self.assertIn(('erp', '0001_initial'), map(tuple, result['migration_state']['applied']))
        self.assertNotIn(('erp', '0002_row_boundaries'), map(tuple, result['migration_state']['applied']))

    def test_latest_recorder_does_not_hide_missing_table(self):
        self.mutate(lambda c: c.execute('DROP TABLE erp_lot'))
        self.assert_refused('missing_table')

    def test_missing_nonnegative_check_is_rejected(self):
        self.mutate(lambda c: rebuild_lot(c, lambda sql: sql.replace(
            ', CONSTRAINT "erp_nonnegative_lot" CHECK ("quantity" >= \'0\')', '')))
        self.assert_refused('checks_mismatch')

    def test_weaker_check_is_rejected(self):
        self.mutate(lambda c: rebuild_lot(c, lambda sql: sql.replace('"quantity" >= \'0\'', '"quantity" >= \'-1\'')))
        self.assert_refused('checks_mismatch')

    def test_missing_unique_is_rejected(self):
        self.mutate(lambda c: rebuild_lot(c, lambda sql: sql.replace(
            '"code" varchar(60) NOT NULL UNIQUE', '"code" varchar(60) NOT NULL')))
        self.assert_refused('unique_mismatch')

    def test_wrong_foreign_key_target_is_rejected(self):
        self.mutate(lambda c: rebuild_lot(c, lambda sql: sql.replace('REFERENCES "erp_item"', 'REFERENCES "erp_location"')))
        self.assert_refused('foreign_keys_mismatch')

    def test_foreign_key_deferral_drift_is_rejected(self):
        self.mutate(lambda c: rebuild_lot(c, lambda sql: sql.replace(
            'DEFERRABLE INITIALLY DEFERRED', 'NOT DEFERRABLE INITIALLY IMMEDIATE', 1)))
        self.assert_refused('foreign_key_deferral_mismatch')

    def test_missing_not_null_is_rejected(self):
        self.mutate(lambda c: rebuild_lot(c, lambda sql: sql.replace('"quantity" decimal NOT NULL', '"quantity" decimal NULL')))
        self.assert_refused('column_definition_mismatch')

    def test_type_affinity_drift_is_rejected(self):
        self.mutate(lambda c: rebuild_lot(c, lambda sql: sql.replace('"quantity" decimal', '"quantity" text')))
        self.assert_refused('column_definition_mismatch')

    def test_sql_default_drift_is_rejected(self):
        self.mutate(lambda c: rebuild_lot(c, lambda sql: sql.replace(
            '"quantity" decimal NOT NULL', '"quantity" decimal NOT NULL DEFAULT 0')))
        self.assert_refused('column_definition_mismatch')

    def test_primary_key_drift_is_rejected(self):
        self.mutate(lambda c: rebuild_lot(c, lambda sql: sql.replace(
            '"id" integer NOT NULL PRIMARY KEY AUTOINCREMENT', '"id" integer NOT NULL UNIQUE')))
        self.assert_refused('pk_mismatch')

    def test_unknown_table_is_rejected(self):
        self.mutate(lambda c: c.execute('CREATE TABLE a07_unknown (id INTEGER PRIMARY KEY)'))
        self.assert_refused('unknown_table')

    def test_unknown_migration_is_rejected(self):
        self.mutate(lambda c: c.execute("INSERT INTO django_migrations (app,name,applied) VALUES ('erp','9000_unknown','2026-09-11 00:00:00')"))
        self.assert_refused('unknown_migrations')

    def test_missing_recorder_dependency_is_rejected(self):
        self.mutate(lambda c: c.execute("DELETE FROM django_migrations WHERE app='erp' AND name='0001_initial'"))
        self.assert_refused('inconsistent_migration_history')

    def test_constraint_name_and_identifier_quote_style_are_not_false_drift(self):
        self.mutate(lambda c: rebuild_lot(c, lambda sql: sql.replace(
            'CONSTRAINT "erp_nonnegative_lot" CHECK ("quantity" >= \'0\')',
            'CONSTRAINT "a07_renamed" CHECK ([quantity] >= \'0\')')))
        self.assertTrue(self.inspect()['complete'])

    def test_unknown_trigger_is_not_silently_accepted(self):
        self.mutate(lambda c: c.execute('CREATE TRIGGER a07_unknown AFTER INSERT ON erp_lot BEGIN SELECT 1; END'))
        self.assert_refused('unsupported_schema_object')

    def test_existing_sidecar_is_refused_without_modifying_source(self):
        before = sha(self.snapshot)
        sidecar = Path(str(self.snapshot) + '-wal')
        sidecar.write_bytes(b'caller-sidecar-marker')
        result = inspect_schema(self.snapshot)
        self.assertFalse(result['complete'])
        self.assertFalse(result['can_migrate'])
        self.assertEqual(sha(self.snapshot), before)
        self.assertEqual(sidecar.read_bytes(), b'caller-sidecar-marker')
        self.assertIn('sidecars', str(result['findings']))

    def test_sequence_high_water_is_returned_literally(self):
        def alter_sequence(connection):
            connection.execute("DELETE FROM sqlite_sequence WHERE name='erp_lot'")
            connection.execute("INSERT INTO sqlite_sequence(name,seq) VALUES ('erp_lot',987654)")
        self.mutate(alter_sequence)
        result = self.inspect()
        self.assertTrue(result['complete'], result['findings'])
        self.assertEqual(result['sqlite_sequence']['erp_lot'], 987654)

    def test_datetime_and_file_descriptors_are_explicit(self):
        result = self.inspect()
        columns = {c['name']: c for c in result['tables']['ai_assistant_chatfile']['columns']}
        self.assertEqual(columns['file']['kind'], 'file')
        self.assertEqual(columns['file']['file_size_column'], 'size')
        dates = [c for table in result['tables'].values() for c in table['columns'] if c['kind'] == 'datetime']
        self.assertTrue(dates)
        self.assertTrue(all(c['sqlite_naive_utc'] is result['configured_profile']['use_tz'] for c in dates))
