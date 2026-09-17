"""A07 typed transfer. Synthetic rehearsal only; no production CLI.

The caller supplies the migration-state schema inspector and a trusted fresh
target bootstrapper. Never feed an original installation to this module.
All rows, including auth/system/archive rows and empty tables, are represented.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
from uuid import UUID, uuid4


FORMAT = 'bos-typed-transfer/1'
BOOTSTRAP = frozenset({'django_migrations', 'django_content_type', 'auth_permission'})
_MINTED = {}
_OWNERS = {}
INTEGER_LIMITS = {
    'SmallIntegerField': (-32768, 32767), 'SmallAutoField': (-32768, 32767),
    'PositiveSmallIntegerField': (0, 32767),
    'IntegerField': (-2147483648, 2147483647), 'AutoField': (-2147483648, 2147483647),
    'PositiveIntegerField': (0, 2147483647),
    'BigIntegerField': (-9223372036854775808, 9223372036854775807),
    'BigAutoField': (-9223372036854775808, 9223372036854775807),
    'PositiveBigIntegerField': (0, 9223372036854775807),
}


class TransferRefused(ValueError):
    """Structural diagnosis only; never include a private raw field value."""


class TargetRejected(TransferRefused):
    pass


def refuse(code, *, table=None, column=None):
    raise TransferRefused(':'.join(str(x) for x in (code, table, column) if x))


def q(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe_text(value, maximum=None):
    if not isinstance(value, str):
        refuse('TEXT_TYPE')
    if '\x00' in value or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        refuse('TEXT_UNICODE')
    if maximum is not None and len(value) > maximum:
        refuse('TEXT_LENGTH')
    return value


def json_number(value):
    number = Decimal(value)
    if not number.is_finite():
        refuse('JSON_NONFINITE')
    # PostgreSQL numeric bounds for jsonb, not Python float bounds.
    if number and (number.adjusted() >= 131072 or
                   max(0, -number.as_tuple().exponent) > 16383):
        refuse('JSON_NUMERIC_RANGE')
    return number


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            safe_text(key)
            if key in result:
                refuse('JSON_DUPLICATE_KEY')
            result[key] = value
        return result

    def constant(_):
        refuse('JSON_NONFINITE')

    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_float=json_number,
                            parse_int=lambda x: int(json_number(x)), parse_constant=constant)
    except (ValueError, TypeError, RecursionError, InvalidOperation) as error:
        if isinstance(error, TransferRefused):
            raise
        refuse('JSON_INVALID')

    def checked(value):
        if isinstance(value, str):
            safe_text(value)
        elif isinstance(value, list):
            for child in value:
                checked(child)
        elif isinstance(value, dict):
            for child in value.values():
                checked(child)
    checked(result)
    return result


def decimal_text(value):
    """Canonical mathematical value; never quantize or binary-float convert."""
    if not value:
        return '0'
    text = format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def json_text(value):
    if value is None:
        return 'null'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, str):
        return json.dumps(safe_text(value), ensure_ascii=False)
    if isinstance(value, (int, Decimal)):
        return decimal_text(json_number(str(value)))
    if isinstance(value, list):
        return '[' + ','.join(json_text(v) for v in value) + ']'
    if isinstance(value, dict):
        return '{' + ','.join(json_text(k) + ':' + json_text(value[k])
                              for k in sorted(value)) + '}'
    refuse('JSON_TYPE')


def decimal_field(value, field):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        refuse('DECIMAL_TYPE')
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        refuse('DECIMAL_INVALID')
    if not number.is_finite():
        refuse('DECIMAL_NONFINITE')
    digits, places = field['max_digits'], field['decimal_places']
    if digits is None or places is None:
        refuse('DECIMAL_SCHEMA')
    if number and number.adjusted() >= digits - places:
        refuse('DECIMAL_OVERFLOW')
    # Trailing zeroes do not change scale of the mathematical value.
    coefficient = number.as_tuple().digits
    exponent = number.as_tuple().exponent
    significant = list(coefficient)
    while significant and significant[-1] == 0:
        significant.pop()
        exponent += 1
    if significant and exponent < -places:
        refuse('DECIMAL_SCALE')
    if isinstance(value, float):
        if not math.isfinite(value):
            refuse('DECIMAL_NONFINITE')
        quantum = Decimal(1).scaleb(-places)
        with localcontext() as context:
            context.prec = max(50, digits + 10)
            if float(number) != value or float(number - quantum) == value or float(number + quantum) == value:
                refuse('PRECISION_UNCERTAIN')
    return decimal_text(number)


def cell(value, field):
    """SQL NULL tagged separately from JSON value null; strings never inferred."""
    if value is None:
        if not field['nullable'] or field.get('pk_order'):
            refuse('REQUIRED_NULL')
        return {'t': 'null'}
    kind = field['kind']
    if kind == 'decimal':
        return {'t': kind, 'v': decimal_field(value, field)}
    if kind == 'integer':
        if isinstance(value, bool) or not isinstance(value, int):
            refuse('INTEGER_TYPE')
        low, high = INTEGER_LIMITS.get(field.get('django_type'), INTEGER_LIMITS['BigIntegerField'])
        if not low <= value <= high:
            refuse('INTEGER_RANGE')
        return {'t': kind, 'v': str(value)}
    if kind == 'boolean':
        if type(value) not in (int, bool) or value not in (0, 1):
            refuse('BOOLEAN_TYPE')
        return {'t': kind, 'v': bool(value)}
    if kind == 'float':
        if type(value) not in (int, float) or not math.isfinite(value):
            refuse('FLOAT_NONFINITE_OR_TYPE')
        return {'t': kind, 'v': float(value).hex()}
    if kind in ('char', 'text', 'file'):
        return {'t': kind, 'v': safe_text(value, field.get('max_length'))}
    if kind == 'json':
        if not isinstance(value, str):
            refuse('JSON_RAW_TEXT_REQUIRED')
        return {'t': kind, 'v': json_text(strict_json(value))}
    if kind == 'binary':
        if not isinstance(value, (bytes, bytearray, memoryview)):
            refuse('BINARY_TYPE')
        raw = bytes(value)
        return {'t': kind, 'v': base64.b64encode(raw).decode('ascii'),
                'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    if kind == 'uuid':
        try:
            return {'t': kind, 'v': str(UUID(str(value)))}
        except ValueError:
            refuse('UUID_INVALID')
    if kind == 'date':
        if isinstance(value, datetime):
            refuse('DATE_TYPE')
        try:
            result = value if isinstance(value, date) else date.fromisoformat(safe_text(value))
        except ValueError:
            refuse('DATE_INVALID')
        return {'t': kind, 'v': result.isoformat()}
    if kind == 'datetime':
        try:
            result = value if isinstance(value, datetime) else datetime.fromisoformat(safe_text(value))
        except ValueError:
            refuse('DATETIME_INVALID')
        # Django SQLite stores UTC naive when USE_TZ=True. This must be explicit
        # schema metadata, never guessed from the machine timezone.
        if result.tzinfo is None:
            if not field.get('sqlite_naive_utc'):
                refuse('DATETIME_TIMEZONE_UNKNOWN')
            result = result.replace(tzinfo=timezone.utc)
        return {'t': kind, 'v': result.astimezone(timezone.utc).isoformat(timespec='microseconds')}
    if kind == 'time':
        try:
            result = value if isinstance(value, time) else time.fromisoformat(safe_text(value))
        except ValueError:
            refuse('TIME_INVALID')
        if result.tzinfo is not None:
            refuse('TIME_TIMEZONE_UNSUPPORTED')
        return {'t': kind, 'v': result.isoformat(timespec='microseconds')}
    if kind == 'duration':
        if isinstance(value, timedelta):
            value = (value.days * 86400 + value.seconds) * 1000000 + value.microseconds
        if type(value) is not int:
            refuse('DURATION_TYPE')
        return {'t': kind, 'v': str(value)}
    refuse('FIELD_KIND_UNSUPPORTED')


def strict_path(path, *, root=None):
    candidate = Path(path).absolute()
    for parent in (candidate, *candidate.parents):
        if parent.is_symlink():
            refuse('SYMLINK_REFUSED')
    result = candidate.resolve(strict=True)
    if root is not None and not result.is_relative_to(Path(root).resolve(strict=True)):
        refuse('PATH_OUTSIDE_REHEARSAL')
    return result


def media_path(root, relative):
    safe_text(relative)
    path = PurePosixPath(relative)
    if not relative or '\\' in relative or path.is_absolute() or '..' in path.parts or str(path) != relative:
        refuse('MEDIA_PATH_INVALID')
    return strict_path(Path(root) / relative, root=root)


def media_manifest(root):
    root = strict_path(root)
    if not root.is_dir():
        refuse('MEDIA_ROOT_INVALID')
    files = []
    for path in sorted(root.rglob('*')):
        strict_path(path, root=root)
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            files.append({'path': relative, 'bytes': path.stat().st_size, 'sha256': file_hash(path)})
        elif not path.is_dir():
            refuse('MEDIA_SPECIAL_FILE')
    return files


def logical_schema(schema):
    return {'tables': schema['tables'], 'migration_state_hash': schema['migration_state_hash']}


def checked_schema(path, inspect_schema):
    schema = inspect_schema(path)
    if not schema.get('complete') or not schema.get('can_migrate') or schema.get('findings'):
        refuse('SCHEMA_UNSUPPORTED_OR_DRIFT')
    if not schema.get('sqlite_schema_hash') or not schema.get('migration_state_hash'):
        refuse('SCHEMA_PROOF_MISSING')
    if not schema.get('tables'):
        refuse('SCHEMA_EMPTY')
    return schema


def row_manifest(tables, rows):
    summaries = {}
    for name, spec in sorted(tables.items()):
        cols = spec['columns']
        pk = [i for i, field in sorted(enumerate(cols), key=lambda x: x[1].get('pk_order') or 999)
              if field.get('pk_order')]
        if not pk:
            refuse('PRIMARY_KEY_MISSING', table=name)
        ordered = sorted(rows[name], key=lambda row: canonical([row[i] for i in pk]))
        if len({canonical([row[i] for i in pk]) for row in ordered}) != len(ordered):
            refuse('PRIMARY_KEY_DUPLICATE', table=name)
        ids = [[row[i] for i in pk] for row in ordered]
        fks = {f['name']: [row[i] for row in ordered] for i, f in enumerate(cols) if f.get('fk')}
        sums = {}
        directional_sums = {}
        currency_index = next((i for i, f in enumerate(cols) if f['name'] == 'currency'), None)
        direction_index = next((i for i, f in enumerate(cols) if f['name'] == 'direction'), None)
        for i, field in enumerate(cols):
            if field['kind'] != 'decimal':
                continue
            grouped = {}
            by_direction = {}
            for row in ordered:
                if row[i]['t'] == 'null':
                    continue
                currency = row[currency_index].get('v') if currency_index is not None else '(no currency column)'
                with localcontext() as context:
                    context.prec = max(100, (field.get('max_digits') or 38) + len(str(len(ordered))) + 10)
                    grouped[currency] = grouped.get(currency, Decimal(0)) + Decimal(row[i]['v'])
                    if direction_index is not None:
                        key = (currency, row[direction_index].get('v'))
                        by_direction[key] = by_direction.get(key, Decimal(0)) + Decimal(row[i]['v'])
            sums[field['name']] = {str(k): decimal_text(v) for k, v in sorted(grouped.items(), key=lambda x: str(x[0]))}
            if direction_index is not None:
                directional_sums[field['name']] = [{'currency': currency, 'direction': direction, 'total': decimal_text(total)}
                    for (currency, direction), total in sorted(by_direction.items(), key=lambda x: str(x[0]))]
        summaries[name] = {'count': len(ordered), 'rows_sha256': digest(ordered),
                           'primary_keys_sha256': digest(ids), 'foreign_keys_sha256': digest(fks),
                           'decimal_totals': sums, 'decimal_totals_by_direction': directional_sums}
        rows[name] = ordered
    return summaries


def read_rows(connection, tables, vendor='sqlite'):
    result = {}
    for name, spec in sorted(tables.items()):
        columns = spec['columns']
        expressions = [('CAST(' + q(f['name']) + ' AS TEXT)')
                       if vendor == 'postgresql' and f['kind'] == 'json' else q(f['name'])
                       for f in columns]
        cursor = connection.cursor()
        cursor.execute('SELECT ' + ','.join(expressions) + ' FROM ' + q(name))
        records = []
        for row in cursor.fetchall():
            primary = {}
            for value, field in zip(row, columns):
                if field.get('pk_order'):
                    # IDs/digests only. Never copy descriptions, names or raw blobs.
                    primary[field['name']] = str(value) if isinstance(value, (int, str, UUID)) else '<invalid-primary-key>'
            record = []
            for value, field in zip(row, columns):
                try:
                    record.append(cell(value, field))
                except (ValueError, TypeError, OverflowError) as error:
                    reason = str(error) if isinstance(error, TransferRefused) else type(error).__name__
                    raise TransferRefused(json.dumps({'code': reason, 'table': name,
                        'pk': primary, 'column': field['name']}, ensure_ascii=True)) from None
            records.append(record)
        cursor.close()
        result[name] = records
    return result


def sequences(connection, tables):
    present = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'").fetchone()
    actual = dict(connection.execute('SELECT name, seq FROM sqlite_sequence')) if present else {}
    expected = {name for name, table in tables.items() if any(f.get('auto_increment') for f in table['columns'])}
    if set(actual) - expected:
        refuse('SEQUENCE_SCHEMA_DRIFT')
    output = {}
    for name in sorted(expected):
        auto = [f for f in tables[name]['columns'] if f.get('auto_increment')]
        if len(auto) != 1:
            refuse('SEQUENCE_SCHEMA_INVALID')
        maximum = connection.execute('SELECT MAX(' + q(auto[0]['name']) + ') FROM ' + q(name)).fetchone()[0]
        last = actual.get(name)
        if last is not None and (type(last) is not int or last < (maximum or 0)):
            refuse('SEQUENCE_HIGH_WATER_INVALID', table=name)
        output[name] = {'last_value': last, 'max_pk': maximum, 'column': auto[0]['name'],
                        'high_water': max(last or 0, maximum or 0)}
    return output


def _snapshot(sqlite_path, media_root, *, inspect_schema):
    path = strict_path(sqlite_path)
    if not path.is_file():
        refuse('SNAPSHOT_NOT_FILE')
    if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        refuse('SNAPSHOT_NOT_SEALED')
    before = file_hash(path)
    schema = checked_schema(path, inspect_schema)
    connection = sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True, detect_types=0)
    try:
        connection.execute('PRAGMA query_only=ON')
        if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            refuse('SQLITE_INTEGRITY')
        if connection.execute('PRAGMA foreign_key_check').fetchall():
            refuse('FOREIGN_KEY_CONFLICT')
        rows = read_rows(connection, schema['tables'])
        seq = sequences(connection, schema['tables'])
    finally:
        connection.close()
    files = media_manifest(media_root)
    by_path = {entry['path']: entry for entry in files}
    references = []
    for name, spec in schema['tables'].items():
        fields = spec['columns']
        index = {f['name']: i for i, f in enumerate(fields)}
        for i, field in enumerate(fields):
            if field['kind'] != 'file':
                continue
            for row in rows[name]:
                relative = row[i].get('v')
                if not relative:
                    continue
                media_path(media_root, relative)
                if relative not in by_path:
                    refuse('MEDIA_MISSING', table=name, column=field['name'])
                size_column = field.get('file_size_column')
                if size_column and row[index[size_column]]['t'] == 'null':
                    refuse('MEDIA_SIZE_MISSING', table=name, column=field['name'])
                if size_column and int(row[index[size_column]]['v']) != by_path[relative]['bytes']:
                    refuse('MEDIA_SIZE_CONFLICT', table=name, column=field['name'])
                checksum_column = field.get('file_checksum_column')
                if (checksum_column and row[index[checksum_column]]['t'] != 'null'
                        and row[index[checksum_column]]['v'] != by_path[relative]['sha256']):
                    refuse('MEDIA_CHECKSUM_CONFLICT', table=name, column=field['name'])
                references.append({'table': name, 'column': field['name'], 'path': relative,
                                   'pk': [row[j] for j, f in enumerate(fields) if f.get('pk_order')]})
    summary = row_manifest(schema['tables'], rows)
    if before != file_hash(path):
        refuse('SNAPSHOT_CHANGED_DURING_READ')
    if files != media_manifest(media_root):
        refuse('MEDIA_CHANGED_DURING_READ')
    manifest = {'format': FORMAT, 'source_sha256': before,
                'sqlite_schema_hash': schema['sqlite_schema_hash'],
                'logical_schema_hash': digest(logical_schema(schema)),
                'migration_state': schema['migration_state'],
                'tables': summary, 'sequences': seq, 'media': files,
                'media_references': references,
                'not_checked': ['business_reconciliation', 'target_database', 'post_commit_orm_http']}
    return manifest, schema, rows


def validate_snapshot(sqlite_path, media_root, *, inspect_schema):
    """Raises on any structural/type/file conflict; no source/target writes."""
    manifest, _, _ = _snapshot(sqlite_path, media_root, inspect_schema=inspect_schema)
    return manifest


def export_snapshot(sqlite_path, media_root, bundle_dir, *, inspect_schema):
    manifest, schema, rows = _snapshot(sqlite_path, media_root, inspect_schema=inspect_schema)
    destination = Path(bundle_dir).absolute()
    strict_path(destination.parent)
    destination.mkdir(mode=0o700, exist_ok=False)
    (destination / 'tables').mkdir(mode=0o700)
    (destination / 'media').mkdir(mode=0o700)
    table_files = {}
    for index, (name, records) in enumerate(sorted(rows.items())):
        relative = f'tables/{index:04d}.jsonl'
        path = destination / relative
        with path.open('xb') as stream:
            for row in records:
                stream.write(canonical(row) + b'\n')
        os.chmod(path, 0o600)
        table_files[name] = {'path': relative, 'sha256': file_hash(path)}
    for entry in manifest['media']:
        source = media_path(media_root, entry['path'])
        target = destination / 'media' / entry['path']
        # parents=True applies mode only to the leaf. Every new component in
        # this exclusively owned export must remain readable by private storage.
        parent = destination / 'media'
        for part in target.parent.relative_to(parent).parts:
            parent = parent / part
            parent.mkdir(mode=0o700, exist_ok=True)
        with source.open('rb') as incoming, target.open('xb') as outgoing:
            for block in iter(lambda: incoming.read(1024 * 1024), b''):
                outgoing.write(block)
        os.chmod(target, 0o600)
        if file_hash(target) != entry['sha256'] or target.stat().st_size != entry['bytes']:
            refuse('MEDIA_CHANGED_DURING_COPY')
    manifest['table_files'] = table_files
    manifest['schema_file_sha256'] = digest(schema)
    (destination / 'schema.json').write_bytes(canonical(schema))
    (destination / 'manifest.json').write_bytes(canonical(manifest))
    os.chmod(destination / 'schema.json', 0o600)
    os.chmod(destination / 'manifest.json', 0o600)
    if file_hash(sqlite_path) != manifest['source_sha256'] or media_manifest(media_root) != manifest['media']:
        refuse('SOURCE_CHANGED_DURING_EXPORT')
    # Marker is written last; an interrupted export is never importable.
    (destination / 'COMPLETE').write_text(file_hash(destination / 'manifest.json'), encoding='ascii')
    return manifest


@dataclass
class DisposableTarget:
    connection: object
    vendor: str
    name: str
    schema: dict
    bootstrap_rows_sha256: str
    owned_guard: object = None
    consumed: bool = False


def _mint(target):
    _MINTED[id(target)] = (id(target.connection), target.vendor, target.name,
                          digest(target.schema), target.bootstrap_rows_sha256, id(target.owned_guard))
    return target


@dataclass(frozen=True)
class ConnectionOwnership:
    """In-process capability emitted only after an owned target was created."""
    connection: object
    vendor: str
    name: str

    def assert_owned(self, connection):
        proof = _OWNERS.get(id(self))
        if proof is not self or connection is not self.connection:
            raise TargetRejected('CONNECTION_OWNERSHIP_NOT_ISSUED')
        if _identity(connection, self.vendor) != self.name:
            raise TargetRejected('CONNECTION_OWNERSHIP_CHANGED')
        return self.name


def _own(connection, vendor, name):
    guard = ConnectionOwnership(connection, vendor, name)
    _OWNERS[id(guard)] = guard
    guard.assert_owned(connection)
    return guard


def _identity(connection, vendor):
    cursor = connection.cursor()
    if vendor == 'sqlite':
        cursor.execute('PRAGMA database_list')
        databases = cursor.fetchall()
        if len(databases) != 1 or databases[0][1] != 'main':
            raise TargetRejected('TARGET_ATTACHED_DATABASE')
        name = str(Path(databases[0][2]).resolve())
    else:
        cursor.execute('SELECT current_database(), current_schema(), current_setting(\'server_encoding\')')
        name, schema, encoding = cursor.fetchone()
        if schema != 'public' or encoding != 'UTF8':
            raise TargetRejected('TARGET_POSTGRES_PROFILE')
    cursor.close()
    return name


def new_disposable_sqlite(work_root, *, bootstrap, inspect_schema):
    """Creates a new exclusive file; bootstrap(conn) may create only known schema."""
    root = strict_path(work_root)
    path = root / ('bos_verify_' + uuid4().hex[:16] + '.sqlite3')
    with path.open('xb'):
        pass
    connection = sqlite3.connect(path, isolation_level=None, detect_types=0)
    connection.execute('PRAGMA foreign_keys=ON')
    bootstrap(connection)
    if connection.in_transaction:
        raise TargetRejected('BOOTSTRAP_TRANSACTION_OPEN')
    schema = checked_schema(path, inspect_schema)
    baseline = read_rows(connection, schema['tables'])
    if any(baseline[name] for name in baseline if name not in BOOTSTRAP):
        raise TargetRejected('TARGET_BUSINESS_NOT_EMPTY')
    owned = _own(connection, 'sqlite', str(path.resolve()))
    return _mint(DisposableTarget(connection, 'sqlite', str(path.resolve()), schema, digest(baseline), owned))


def new_disposable_postgres(*, provision, inspect_target):
    """UNVERIFIED here. provision(name) must CREATE this new DB and migrate it.

    The unpredictable name is created here, not accepted from an env variable.
    The provisioner must fail on CREATE DATABASE collision; no connect fallback.
    Connection is a real psycopg connection, autocommit=True, never Django defaults.
    inspect_target(conn, owned_guard=...) verifies actual columns/constraints.
    """
    name = 'bos_verify_' + uuid4().hex[:16]
    connection = provision(name)
    if not connection.autocommit or _identity(connection, 'postgresql') != name:
        raise TargetRejected('TARGET_IDENTITY')
    owned = _own(connection, 'postgresql', name)
    schema = inspect_target(connection, owned_guard=owned)
    if not schema.get('complete') or not schema.get('can_migrate') or schema.get('findings'):
        raise TargetRejected('TARGET_SCHEMA_UNPROVEN')
    baseline = read_rows(connection, schema['tables'], 'postgresql')
    if any(baseline[name] for name in baseline if name not in BOOTSTRAP):
        raise TargetRejected('TARGET_BUSINESS_NOT_EMPTY')
    return _mint(DisposableTarget(connection, 'postgresql', name, schema, digest(baseline), owned))


def _sql_value(value, field, vendor):
    kind = value['t']
    if kind == 'null':
        return None
    raw = value['v']
    if kind in ('integer', 'duration'):
        return timedelta(microseconds=int(raw)) if kind == 'duration' and vendor == 'postgresql' else int(raw)
    if kind == 'decimal':
        return Decimal(raw) if vendor == 'postgresql' else raw
    if kind == 'float':
        return float.fromhex(raw)
    if kind == 'binary':
        return base64.b64decode(raw, validate=True)
    if kind == 'uuid':
        return UUID(raw) if vendor == 'postgresql' else UUID(raw).hex
    if kind == 'datetime':
        parsed = datetime.fromisoformat(raw)
        return parsed if vendor == 'postgresql' else parsed.replace(tzinfo=None).isoformat(' ')
    if kind == 'date':
        return date.fromisoformat(raw) if vendor == 'postgresql' else raw
    if kind == 'time':
        return time.fromisoformat(raw) if vendor == 'postgresql' else raw
    return raw


def _load_bundle(bundle_dir):
    root = strict_path(bundle_dir)
    marker = strict_path(root / 'COMPLETE', root=root)
    manifest_file = strict_path(root / 'manifest.json', root=root)
    if marker.read_text(encoding='ascii') != file_hash(manifest_file):
        refuse('BUNDLE_INCOMPLETE_OR_CHANGED')
    manifest = strict_json(manifest_file.read_text(encoding='utf-8'))
    if manifest.get('format') != FORMAT:
        refuse('BUNDLE_FORMAT')
    schema_file = strict_path(root / 'schema.json', root=root)
    if file_hash(schema_file) != manifest['schema_file_sha256']:
        refuse('BUNDLE_SCHEMA_CHANGED')
    schema = strict_json(schema_file.read_text(encoding='utf-8'))
    if digest(logical_schema(schema)) != manifest['logical_schema_hash']:
        refuse('BUNDLE_SCHEMA_HASH')
    rows = {}
    if set(manifest['table_files']) != set(schema['tables']) or set(manifest['tables']) != set(schema['tables']):
        refuse('BUNDLE_TABLE_SET')
    for name, entry in manifest['table_files'].items():
        path = media_path(root, entry['path'])
        if file_hash(path) != entry['sha256']:
            refuse('BUNDLE_TABLE_CHANGED', table=name)
        records = [strict_json(line) for line in path.read_text(encoding='utf-8').splitlines()]
        fields = schema['tables'][name]['columns']
        for row in records:
            if len(row) != len(fields):
                refuse('BUNDLE_COLUMN_COUNT', table=name)
            for value, field in zip(row, fields):
                if value['t'] not in ('null', field['kind']):
                    refuse('BUNDLE_FIELD_TAG', table=name, column=field['name'])
                raw = _sql_value(value, field, 'sqlite')
                checked = cell(raw, field)
                if checked != value:
                    refuse('BUNDLE_NONCANONICAL_VALUE', table=name, column=field['name'])
        rows[name] = records
    if row_manifest(schema['tables'], rows) != manifest['tables']:
        refuse('BUNDLE_ROW_MANIFEST')
    if media_manifest(root / 'media') != manifest['media']:
        refuse('BUNDLE_MEDIA_CHANGED')
    return manifest, schema, rows


def import_to_disposable(bundle_dir, target, *, verify_actual_schema):
    """Raw typed inserts. Caller retains isolated bundle media; no live promotion.

    Failure consumes the target, including PG sequence state; discard that owned
    disposable DB. There is deliberately no retry onto a partly used target.
    """
    manifest, schema, rows = _load_bundle(bundle_dir)
    if not isinstance(target, DisposableTarget) or target.consumed:
        raise TargetRejected('TARGET_GUARD_REQUIRED_OR_USED')
    identity = (id(target.connection), target.vendor, target.name,
                digest(target.schema), target.bootstrap_rows_sha256, id(target.owned_guard))
    if _MINTED.get(id(target)) != identity:
        raise TargetRejected('TARGET_NOT_CREATED_BY_THIS_RUN')
    if not re.fullmatch(r'bos_verify_[a-f0-9]{16}(?:\.sqlite3)?', Path(target.name).name):
        raise TargetRejected('TARGET_NAME')
    if _identity(target.connection, target.vendor) != target.name:
        raise TargetRejected('TARGET_CONNECTION_CHANGED')
    target.owned_guard.assert_owned(target.connection)
    current = verify_actual_schema(target)
    if not current.get('complete') or not current.get('can_migrate') or current.get('findings'):
        raise TargetRejected('TARGET_SCHEMA_DRIFT')
    if logical_schema(current) != logical_schema(schema):
        raise TargetRejected('TARGET_MIGRATION_OR_FIELD_MISMATCH')
    if target.vendor == 'sqlite' and current['sqlite_schema_hash'] != schema['sqlite_schema_hash']:
        raise TargetRejected('TARGET_SQLITE_SCHEMA_MISMATCH')
    connection = target.connection
    target.consumed = True
    cursor = connection.cursor()
    try:
        cursor.execute('BEGIN IMMEDIATE' if target.vendor == 'sqlite' else 'BEGIN')
        if target.vendor == 'postgresql':
            cursor.execute('LOCK TABLE ' + ','.join(q(name) for name in sorted(schema['tables'])) + ' IN ACCESS EXCLUSIVE MODE')
        baseline = read_rows(connection, schema['tables'], target.vendor)
        if digest(baseline) != target.bootstrap_rows_sha256 or any(baseline[n] for n in baseline if n not in BOOTSTRAP):
            raise TargetRejected('TARGET_CHANGED_AFTER_BOOTSTRAP')
        cursor.execute('PRAGMA defer_foreign_keys=ON' if target.vendor == 'sqlite' else 'SET CONSTRAINTS ALL DEFERRED')
        # All source IDs are retained. No TRUNCATE, CASCADE or natural-key remap.
        for name in sorted(BOOTSTRAP & set(schema['tables']), reverse=True):
            cursor.execute('DELETE FROM ' + q(name))
        placeholder = '?' if target.vendor == 'sqlite' else '%s'
        for name, table in sorted(schema['tables'].items()):
            fields = table['columns']
            expressions = [('CAST(%s AS jsonb)' if f['kind'] == 'json' and target.vendor == 'postgresql' else placeholder)
                           for f in fields]
            sql = 'INSERT INTO ' + q(name) + '(' + ','.join(q(f['name']) for f in fields) + ') VALUES (' + ','.join(expressions) + ')'
            for row in rows[name]:
                cursor.execute(sql, [_sql_value(v, f, target.vendor) for v, f in zip(row, fields)])
        observed = read_rows(connection, schema['tables'], target.vendor)
        if row_manifest(schema['tables'], observed) != manifest['tables']:
            refuse('TARGET_ROWS_OR_TOTALS_DIFFER')
        if target.vendor == 'sqlite':
            if cursor.execute('PRAGMA foreign_key_check').fetchall():
                refuse('TARGET_FOREIGN_KEY_CONFLICT')
            for name, state in manifest['sequences'].items():
                cursor.execute('DELETE FROM sqlite_sequence WHERE name=?', (name,))
                if state['last_value'] is not None:
                    cursor.execute('INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)', (name, state['last_value']))
            if sequences(connection, schema['tables']) != manifest['sequences']:
                refuse('TARGET_SEQUENCE_DIFFER')
        else:
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
            for name, state in manifest['sequences'].items():
                cursor.execute('SELECT pg_get_serial_sequence(%s,%s)', (name, state['column']))
                sequence = cursor.fetchone()[0]
                if sequence is None:
                    refuse('TARGET_SEQUENCE_MISSING', table=name)
                high_water = state['high_water']
                cursor.execute('SELECT setval(%s::regclass,%s,%s)', (sequence, max(1, high_water), high_water >= 1))
        # Rehash the entire sealed bundle before commit, including media.
        if _load_bundle(bundle_dir)[0] != manifest:
            refuse('BUNDLE_CHANGED_DURING_IMPORT')
        cursor.execute('COMMIT')
    except BaseException:
        cursor.execute('ROLLBACK')
        raise
    finally:
        cursor.close()
    after = read_rows(connection, schema['tables'], target.vendor)
    if row_manifest(schema['tables'], after) != manifest['tables']:
        raise TargetRejected('POST_COMMIT_MISMATCH_DISCARD_TARGET')
    return {'format': FORMAT, 'imported': True, 'vendor': target.vendor,
            'source_sha256': manifest['source_sha256'], 'tables': manifest['tables'],
            'media': manifest['media'], 'media_promoted': False,
            'not_checked': ['business_reconciliation', 'post_commit_orm_http', 'sequence_proof_inserts']}
