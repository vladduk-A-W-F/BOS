"""Focused actual SQLite probes for draft transport. All data synthetic.

These are negative-case assertions, not a claimed pre-implementation red run.
The fixed miniature schema probe does not replace ProjectState integration.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import UUID

import scripts.data_transfer as transfer


def field(name, kind, **options):
    return dict(name=name, field_name=name, kind=kind, django_type='BigIntegerField' if kind == 'integer' else kind,
                nullable=False, pk_order=0, max_length=None, max_digits=None,
                decimal_places=None, fk=None, auto_increment=False, **options)


def f(name, kind, **options):
    value = field(name, kind)
    value.update(options)
    return value


DDL = '''
CREATE TABLE django_migrations(id INTEGER PRIMARY KEY AUTOINCREMENT, app VARCHAR(255) NOT NULL, name VARCHAR(255) NOT NULL, applied DATETIME NOT NULL);
CREATE TABLE django_content_type(id INTEGER PRIMARY KEY AUTOINCREMENT, app_label VARCHAR(100) NOT NULL, model VARCHAR(100) NOT NULL, UNIQUE(app_label,model));
CREATE TABLE auth_permission(id INTEGER PRIMARY KEY AUTOINCREMENT, content_type_id INTEGER NOT NULL REFERENCES django_content_type(id) DEFERRABLE INITIALLY DEFERRED, codename VARCHAR(100) NOT NULL, UNIQUE(content_type_id,codename));
CREATE TABLE demo_record(id INTEGER PRIMARY KEY AUTOINCREMENT, content_type_id INTEGER NOT NULL REFERENCES django_content_type(id) DEFERRABLE INITIALLY DEFERRED, code VARCHAR(20) NOT NULL, amount DECIMAL NOT NULL, quantity DECIMAL NOT NULL, currency VARCHAR(3) NOT NULL, payload TEXT NULL, content BLOB NOT NULL, checksum VARCHAR(64) NOT NULL, day DATE NOT NULL, stamp DATETIME NOT NULL, archived_at DATETIME NULL, enabled BOOL NOT NULL, proposal CHAR(32) NOT NULL, ratio REAL NOT NULL, file VARCHAR(255) NOT NULL, size INTEGER NOT NULL, direction VARCHAR(3) NOT NULL DEFAULT 'in');
CREATE TABLE empty_record(id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(30) NOT NULL);
CREATE TRIGGER reject_block BEFORE INSERT ON demo_record WHEN NEW.code='BLOCK' BEGIN SELECT RAISE(ABORT,'synthetic late import rejection'); END;
'''


def spec():
    pk = f('id', 'integer', pk_order=1, auto_increment=True, django_type='BigAutoField')
    utc = {'sqlite_naive_utc': True}
    tables = {
        'django_migrations': {'columns': [pk, f('app', 'char', max_length=255), f('name', 'char', max_length=255), f('applied', 'datetime', **utc)]},
        'django_content_type': {'columns': [pk, f('app_label', 'char', max_length=100), f('model', 'char', max_length=100)]},
        'auth_permission': {'columns': [pk, f('content_type_id', 'integer', fk={'table': 'django_content_type', 'column': 'id'}), f('codename', 'char', max_length=100)]},
        'demo_record': {'columns': [pk,
            f('content_type_id', 'integer', fk={'table': 'django_content_type', 'column': 'id'}),
            f('code', 'char', max_length=20), f('amount', 'decimal', max_digits=14, decimal_places=2),
            f('quantity', 'decimal', max_digits=15, decimal_places=3), f('currency', 'char', max_length=3),
            f('payload', 'json', nullable=True), f('content', 'binary'), f('checksum', 'char', max_length=64),
            f('day', 'date'), f('stamp', 'datetime', **utc), f('archived_at', 'datetime', nullable=True, **utc),
            f('enabled', 'boolean'), f('proposal', 'uuid'), f('ratio', 'float'),
            f('file', 'file', max_length=255, file_size_column='size'), f('size', 'integer'), f('direction', 'char', max_length=3)]},
        'empty_record': {'columns': [pk, f('name', 'char', max_length=30)]},
    }
    return {'tables': copy.deepcopy(tables), 'migration_state_hash': transfer.digest(['demo.0001']),
            'migration_state': {'applied': [['demo', '0001']], 'latest': True},
            'profile': 'latest', 'complete': True, 'can_migrate': True, 'findings': []}


def shape(conn):
    return transfer.digest(conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall())


class SyntheticTransfer(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='a07_transport_')
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.snapshot.sqlite3'
        self.media = self.root / 'source-media'
        (self.media / 'chat_files').mkdir(parents=True)
        self.relative = 'chat_files/технічний-файл.bin'
        (self.media / self.relative).write_bytes(bytes(range(256)))
        conn = sqlite3.connect(self.source)
        conn.executescript(DDL)
        self.expected_shape = shape(conn)
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('INSERT INTO django_migrations VALUES (7,?,?,?)', ('demo', '0001', '2025-02-03 04:05:06.123456'))
        conn.execute('INSERT INTO django_content_type VALUES (7,?,?)', ('demo', 'record'))
        conn.execute('INSERT INTO auth_permission VALUES (19,7,?)', ('view_record',))
        for index, key in enumerate((7, 1001, 90001)):
            payload = (None, 'null', '{"точно":12345678901234567.1234567890123456789,"id":90001,"ok":false,"list":[null,"0.10"]}')[index]
            conn.execute('INSERT INTO demo_record VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (key, 7, 'R' + str(index), ('0.10', '0.20', '999999999999.99')[index],
                          ('0.100', '0.200', '-0.300')[index], 'EUR', payload, bytes(range(256)) if index == 2 else b'',
                          'legacy-declared-digest', '2026-09-11', '2025-02-03 04:05:06.123456',
                          '2025-02-04 00:00:00.000001' if index == 2 else None, index % 2,
                          UUID(int=key).hex, 0.12345678901234568, self.relative if index == 2 else '', 256 if index == 2 else 0,
                          'out' if index == 1 else 'in'))
        conn.execute("UPDATE sqlite_sequence SET seq=99001 WHERE name='demo_record'")
        conn.execute("INSERT INTO sqlite_sequence(name,seq) VALUES ('empty_record',340003)")
        conn.commit()
        conn.close()
        self.original = transfer.file_hash(self.source)
        self.targets = []

    def tearDown(self):
        for target in self.targets:
            target.connection.close()
        self.temp.cleanup()

    def inspector(self, path):
        conn = sqlite3.connect(Path(path).as_uri() + '?mode=ro&immutable=1', uri=True)
        try:
            actual = shape(conn)
        finally:
            conn.close()
        result = spec()
        result['sqlite_schema_hash'] = actual
        if actual != self.expected_shape:
            result.update(can_migrate=False, findings=[{'code': 'SCHEMA_DRIFT'}])
        return result

    def target(self):
        def bootstrap(conn):
            conn.executescript(DDL)
            conn.execute('INSERT INTO django_migrations VALUES (999,?,?,?)', ('demo', '0001', '2026-01-01 00:00:00'))
            conn.execute('INSERT INTO django_content_type VALUES (999,?,?)', ('demo', 'record'))
            conn.execute('INSERT INTO auth_permission VALUES (999,999,?)', ('view_record',))
        target = transfer.new_disposable_sqlite(self.root, bootstrap=bootstrap, inspect_schema=self.inspector)
        self.targets.append(target)
        return target

    def export(self):
        bundle = self.root / 'bundle'
        result = transfer.export_snapshot(self.source, self.media, bundle, inspect_schema=self.inspector)
        self.assertEqual(transfer.file_hash(self.source), self.original)
        return bundle, result

    def mutate(self, sql, args=()):
        conn = sqlite3.connect(self.source)
        conn.execute(sql, args)
        conn.commit()
        conn.close()
        self.original = transfer.file_hash(self.source)

    def assert_refused(self, code):
        with self.assertRaisesRegex(transfer.TransferRefused, code):
            transfer.validate_snapshot(self.source, self.media, inspect_schema=self.inspector)
        self.assertEqual(transfer.file_hash(self.source), self.original)

    def test_exact_round_trip_system_ids_types_and_empty_sequences(self):
        bundle, manifest = self.export()
        self.assertEqual(manifest['tables']['demo_record']['decimal_totals']['amount'], {'EUR': '1000000000000.29'})
        self.assertEqual(manifest['tables']['demo_record']['decimal_totals']['quantity'], {'EUR': '0'})
        self.assertEqual(manifest['tables']['demo_record']['decimal_totals_by_direction']['amount'],
                         [{'currency': 'EUR', 'direction': 'in', 'total': '1000000000000.09'},
                          {'currency': 'EUR', 'direction': 'out', 'total': '0.2'}])
        self.assertEqual(manifest['tables']['empty_record']['count'], 0)
        target = self.target()
        result = transfer.import_to_disposable(bundle, target, verify_actual_schema=lambda t: self.inspector(t.name))
        self.assertTrue(result['imported'])
        conn = target.connection
        self.assertEqual(conn.execute('SELECT id FROM django_content_type').fetchall(), [(7,)])
        self.assertEqual(conn.execute('SELECT id,content_type_id FROM auth_permission').fetchall(), [(19, 7)])
        self.assertEqual(conn.execute('SELECT id,applied FROM django_migrations').fetchall(), [(7, '2025-02-03 04:05:06.123456')])
        self.assertEqual(conn.execute('SELECT content,checksum,archived_at FROM demo_record WHERE id=90001').fetchone(),
                         (bytes(range(256)), 'legacy-declared-digest', '2025-02-04 00:00:00.000001'))
        payloads = dict(conn.execute('SELECT id,payload FROM demo_record'))
        self.assertIsNone(payloads[7])
        self.assertEqual(payloads[1001], 'null')
        self.assertIn('12345678901234567.1234567890123456789', payloads[90001])
        self.assertEqual(manifest['media'], transfer.media_manifest(bundle / 'media'))
        # Actual ordinary inserts: performed after manifest comparison only.
        self.assertEqual(conn.execute('INSERT INTO empty_record(name) VALUES (?)', ('proof 1',)).lastrowid, 340004)
        self.assertEqual(conn.execute('INSERT INTO empty_record(name) VALUES (?)', ('proof 2',)).lastrowid, 340005)
        conn.execute("INSERT INTO demo_record(content_type_id,code,amount,quantity,currency,payload,content,checksum,day,stamp,archived_at,enabled,proposal,ratio,file,size) SELECT content_type_id,'PROOF',amount,quantity,currency,payload,content,checksum,day,stamp,archived_at,enabled,proposal,ratio,file,size FROM demo_record WHERE id=7")
        self.assertEqual(conn.execute("SELECT id FROM demo_record WHERE code='PROOF'").fetchone()[0], 99002)

    def test_schema_drift_is_refused_before_values(self):
        self.mutate('ALTER TABLE demo_record ADD COLUMN hidden TEXT')
        self.assert_refused('SCHEMA_UNSUPPORTED_OR_DRIFT')

    def test_duplicate_json_keys(self):
        self.mutate('UPDATE demo_record SET payload=? WHERE id=7', ('{"id":7,"id":9}',))
        self.assert_refused('JSON_DUPLICATE_KEY')

    def test_json_nul_surrogate_nonfinite_huge_numeric(self):
        for raw in ('"\\u0000"', '"\\ud800"', 'NaN', '1e9999999'):
            with self.subTest(raw=raw):
                self.mutate('UPDATE demo_record SET payload=? WHERE id=7', (raw,))
                self.assert_refused('TEXT_UNICODE|JSON_NONFINITE|JSON_NUMERIC_RANGE')

    def test_decimal_scale_overflow_nonfinite_no_rounding(self):
        for amount, code in [('1.005', 'DECIMAL_SCALE'), ('1000000000000', 'DECIMAL_OVERFLOW'), (float('inf'), 'DECIMAL_NONFINITE')]:
            with self.subTest(amount=amount):
                self.mutate('UPDATE demo_record SET amount=? WHERE id=7', (amount,))
                self.assert_refused(code)
        with self.assertRaisesRegex(transfer.TransferRefused, 'DECIMAL_OVERFLOW'):
            transfer.decimal_field('1e9999999', f('amount', 'decimal', max_digits=14, decimal_places=2))

    def test_text_nul_and_length_preserve_source(self):
        for value, code in [('a\0b', 'TEXT_UNICODE'), ('Ї' * 21, 'TEXT_LENGTH')]:
            with self.subTest(code=code):
                self.mutate('UPDATE demo_record SET code=? WHERE id=7', (value,))
                self.assert_refused(code)
        try:
            transfer.validate_snapshot(self.source, self.media, inspect_schema=self.inspector)
        except transfer.TransferRefused as error:
            facts = json.loads(str(error))
            self.assertEqual((facts['table'], facts['pk'], facts['column']), ('demo_record', {'id': '7'}, 'code'))
            self.assertNotIn('Ї', str(error))

    def test_dangling_fk(self):
        self.mutate('UPDATE demo_record SET content_type_id=99999 WHERE id=7')
        self.assert_refused('FOREIGN_KEY_CONFLICT')

    def test_media_missing_and_wrong_size(self):
        (self.media / self.relative).write_bytes(b'short')
        self.assert_refused('MEDIA_SIZE_CONFLICT')
        (self.media / self.relative).unlink()
        with self.assertRaises((transfer.TransferRefused, FileNotFoundError)):
            transfer.validate_snapshot(self.source, self.media, inspect_schema=self.inspector)
        self.assertEqual(transfer.file_hash(self.source), self.original)

    def test_snapshot_sidecar_refused(self):
        Path(str(self.source) + '-wal').write_bytes(b'')
        self.assert_refused('SNAPSHOT_NOT_SEALED')

    def test_real_late_trigger_rolls_back_all_rows_and_bootstrap(self):
        self.mutate("UPDATE demo_record SET code='BLOCK' WHERE id=90001")
        bundle, _ = self.export()
        target = self.target()
        before = transfer.read_rows(target.connection, target.schema['tables'])
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'synthetic late import rejection'):
            transfer.import_to_disposable(bundle, target, verify_actual_schema=lambda t: self.inspector(t.name))
        self.assertEqual(transfer.read_rows(target.connection, target.schema['tables']), before)
        self.assertTrue(target.consumed)
        self.assertEqual(transfer.file_hash(self.source), self.original)

    def test_changed_target_refused_without_erasing_new_rows(self):
        bundle, _ = self.export()
        target = self.target()
        target.connection.execute("INSERT INTO empty_record(name) VALUES ('new row')")
        with self.assertRaisesRegex(transfer.TargetRejected, 'TARGET_CHANGED_AFTER_BOOTSTRAP'):
            transfer.import_to_disposable(bundle, target, verify_actual_schema=lambda t: self.inspector(t.name))
        self.assertEqual(target.connection.execute('SELECT name FROM empty_record').fetchall(), [('new row',)])

    def test_media_tampering_before_import_leaves_target_bootstrap(self):
        bundle, _ = self.export()
        (bundle / 'media' / self.relative).write_bytes(b'corrupt')
        target = self.target()
        with self.assertRaisesRegex(transfer.TransferRefused, 'BUNDLE_MEDIA_CHANGED'):
            transfer.import_to_disposable(bundle, target, verify_actual_schema=lambda t: self.inspector(t.name))
        self.assertEqual(target.connection.execute('SELECT id FROM django_content_type').fetchall(), [(999,)])

    def test_forged_target_guard_and_reuse_refused(self):
        bundle, _ = self.export()
        actual = self.target()
        forged = transfer.DisposableTarget(actual.connection, actual.vendor, actual.name, actual.schema, actual.bootstrap_rows_sha256)
        with self.assertRaisesRegex(transfer.TargetRejected, 'TARGET_NOT_CREATED_BY_THIS_RUN'):
            transfer.import_to_disposable(bundle, forged, verify_actual_schema=lambda t: self.inspector(t.name))
        transfer.import_to_disposable(bundle, actual, verify_actual_schema=lambda t: self.inspector(t.name))
        with self.assertRaisesRegex(transfer.TargetRejected, 'TARGET_GUARD_REQUIRED_OR_USED'):
            transfer.import_to_disposable(bundle, actual, verify_actual_schema=lambda t: self.inspector(t.name))

    def test_media_symlink_and_traversal_refused(self):
        (self.media / 'bad').symlink_to(self.source)
        self.assert_refused('SYMLINK_REFUSED')
        (self.media / 'bad').unlink()
        self.mutate('UPDATE demo_record SET file=? WHERE id=90001', ('../source.snapshot.sqlite3',))
        self.assert_refused('MEDIA_PATH_INVALID')


if __name__ == '__main__':
    unittest.main(verbosity=2)
