"""A07 schema-only admission of an immutable SQLite snapshot.

inspect_schema(path) never migrates, alters or repairs the input. Expected DDL
is created in a new temporary SQLite database from the recorded ProjectState.
The caller must configure Django for the reviewed project before calling.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile
from uuid import uuid4


def file_sha(path):
    out = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            out.update(block)
    return out.hexdigest()


def stable_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), default=str).encode()).hexdigest()


def quoted(name):
    return '"' + str(name).replace('"', '""') + '"'


def tokens(sql):
    """Small SQLite lexer; strings/comments cannot invent CHECK/FK clauses."""
    result = []
    i = 0
    while i < len(sql):
        c = sql[i]
        if c.isspace():
            i += 1
            continue
        if sql.startswith('--', i):
            end = sql.find('\n', i)
            i = len(sql) if end < 0 else end + 1
            continue
        if sql.startswith('/*', i):
            end = sql.find('*/', i + 2)
            if end < 0:
                raise ValueError('Unterminated SQL comment')
            i = end + 2
            continue
        start = i
        if c in ('"', "'", '`', '['):
            close = ']' if c == '[' else c
            i += 1
            value = ''
            while i < len(sql):
                if sql[i] == close:
                    if i + 1 < len(sql) and sql[i + 1] == close:
                        value += close
                        i += 2
                        continue
                    i += 1
                    break
                value += sql[i]
                i += 1
            else:
                raise ValueError('Unterminated SQL quote')
            result.append(('string' if c == "'" else 'identifier', value, start, i))
        elif c.isalpha() or c == '_':
            i += 1
            while i < len(sql) and (sql[i].isalnum() or sql[i] in '_$'):
                i += 1
            result.append(('word', sql[start:i].lower(), start, i))
        elif c.isdigit():
            i += 1
            while i < len(sql) and (sql[i].isdigit() or sql[i] in '.eE+-' and
                                  (sql[i] not in '+-' or sql[i-1] in 'eE')):
                i += 1
            result.append(('number', sql[start:i].lower(), start, i))
        else:
            i += 1
            if i < len(sql) and sql[start:i+1] in ('>=', '<=', '<>', '!=', '==', '||', '->'):
                i += 1
            result.append(('symbol', sql[start:i], start, i))
    return result


def matching(rows, start):
    if rows[start][1] != '(':
        raise ValueError('Expected an opening SQL parenthesis')
    level = 0
    for pos in range(start, len(rows)):
        if rows[pos][0] != 'symbol':
            continue
        if rows[pos][1] == '(':
            level += 1
        elif rows[pos][1] == ')':
            level -= 1
            if level == 0:
                return pos
    raise ValueError('Unbalanced SQL expression')


def normalized(rows, columns=()):
    rows = list(rows)
    while rows and rows[0][1] == '(' and matching(rows, 0) == len(rows) - 1:
        rows = rows[1:-1]
    names = {str(name).lower() for name in columns}
    result = []
    for kind, value, *_ in rows:
        if kind == 'identifier' or (kind == 'word' and value in names):
            result.append(('identifier', value.lower()))
        elif kind == 'symbol':
            result.append((kind, {'==': '=', '!=': '<>'}.get(value, value)))
        else:
            result.append((kind, value))
    return tuple(result)


def ddl_features(sql, columns):
    rows = tokens(sql)
    checks = set()
    deferred = []
    collations = {}
    words = [v for kind, v, *_ in rows if kind == 'word']
    for i, row in enumerate(rows):
        if row[:2] == ('word', 'check'):
            if i + 1 >= len(rows) or rows[i + 1][1] != '(':
                raise ValueError('Unsupported CHECK syntax')
            end = matching(rows, i + 1)
            checks.add(normalized(rows[i + 2:end], columns))
    start = next((i for i, row in enumerate(rows) if row[:2] == ('symbol', '(')), None)
    if start is None:
        raise ValueError('Unsupported table DDL')
    end = matching(rows, start)
    pieces, beginning, depth = [], start + 1, 0
    for i in range(start + 1, end):
        if rows[i][:2] == ('symbol', '('): depth += 1
        if rows[i][:2] == ('symbol', ')'): depth -= 1
        if rows[i][:2] == ('symbol', ',') and depth == 0:
            pieces.append(rows[beginning:i]); beginning = i + 1
    pieces.append(rows[beginning:end])
    for segment in pieces:
        if segment and segment[0][1] in columns:
            level = 0
            for i, row in enumerate(segment):
                if row[:2] == ('symbol', '('): level += 1
                elif row[:2] == ('symbol', ')'): level -= 1
                elif level == 0 and row[:2] == ('word', 'collate'):
                    collations[segment[0][1]] = segment[i+1][1].lower()
        refs = [i for i, row in enumerate(segment) if row[:2] == ('word', 'references')]
        if not refs:
            continue
        if len(refs) != 1:
            raise ValueError('Unsupported multiple REFERENCES in one declaration')
        ref = refs[0]
        foreign = next((i for i, row in enumerate(segment) if row[:2] == ('word', 'foreign')), None)
        if foreign is not None:
            opening = foreign + 2
            closing = matching(segment, opening)
            sources = [r[1].lower() for r in segment[opening+1:closing] if r[0] in ('word', 'identifier')]
        else:
            sources = [segment[0][1].lower()]
        target = segment[ref+1][1].lower()
        opening = ref + 2
        if opening >= len(segment) or segment[opening][1] != '(':
            raise ValueError('REFERENCES without explicit target columns is not accepted')
        closing = matching(segment, opening)
        targets = [r[1].lower() for r in segment[opening+1:closing] if r[0] in ('word', 'identifier')]
        tail = [r[1] for r in segment[closing+1:] if r[0] == 'word']
        deferrable = 'deferrable' in tail and not any(
            tail[i:i+2] == ['not', 'deferrable'] for i in range(len(tail)))
        initially = 'deferred' if 'deferred' in tail else 'immediate'
        deferred.append({'from': sources, 'table': target, 'to': targets,
                         'deferrable': deferrable, 'initially': initially})
    if any(words[i:i+2] == ['on', 'conflict'] for i in range(len(words))):
        raise ValueError('Non-default ON CONFLICT schema needs an explicit reviewed adapter')
    return {'checks': sorted(checks), 'foreign_key_deferral': sorted(deferred, key=lambda x: json.dumps(x, sort_keys=True)),
            'column_collations': collations,
            'autoincrement': 'autoincrement' in words,
            'without_rowid': any(words[i:i+2] == ['without', 'rowid'] for i in range(len(words))),
            'strict': bool(rows[end+1:] and any(
                r[:2] == ('word', 'strict') for r in rows[end+1:]))}


def affinity(declaration):
    value = declaration.upper()
    if 'INT' in value: return 'INTEGER'
    if any(s in value for s in ('CHAR', 'CLOB', 'TEXT')): return 'TEXT'
    if not value or 'BLOB' in value: return 'BLOB'
    if any(s in value for s in ('REAL', 'FLOA', 'DOUB')): return 'REAL'
    return 'NUMERIC'


def read_sqlite_structure(conn):
    objects = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
    tables, extras = {}, []
    sequence = {}
    for kind, name, owner, ddl in objects:
        if kind in ('trigger', 'view'):
            extras.append({'kind': kind, 'name': name, 'table': owner, 'sql': ddl})
        if kind != 'table':
            continue
        if name == 'sqlite_sequence':
            sequence = {str(n): int(v) for n, v in conn.execute('SELECT name,seq FROM sqlite_sequence')}
            continue
        if name in ('sqlite_stat1', 'sqlite_stat4'):
            continue
        raw = conn.execute('PRAGMA table_xinfo(' + quoted(name) + ')').fetchall()
        columns = [r[1] for r in raw]
        features = ddl_features(ddl or '', columns)
        pk = [r[1] for r in sorted(raw, key=lambda x: x[5]) if r[5]]
        rowid_pk = len(pk) == 1 and any(r[1] == pk[0] and r[2].upper() == 'INTEGER' for r in raw)
        values = []
        for row in raw:
            default = normalized(tokens(row[4])) if row[4] is not None else ()
            if default == (('word', 'null'),): default = ()
            values.append({'name': row[1], 'declared_type': row[2], 'affinity': affinity(row[2]),
                'not_null': bool(row[3] or row[5] and (rowid_pk or features['without_rowid'])),
                'default': default, 'pk_order': row[5], 'hidden': row[6],
                'collation': features['column_collations'].get(row[1], 'binary')})
        fks = {}
        for row in conn.execute('PRAGMA foreign_key_list(' + quoted(name) + ')'):
            ident, seq, target, source, dest, update, delete, match = row
            group = fks.setdefault(ident, {'table': target, 'from': [], 'to': [],
                'on_update': update, 'on_delete': delete, 'match': match})
            group['from'].append((seq, source)); group['to'].append((seq, dest))
        for group in fks.values():
            group['from'] = [name for _, name in sorted(group['from'])]
            group['to'] = [name for _, name in sorted(group['to'])]
        unique = []
        for row in conn.execute('PRAGMA index_list(' + quoted(name) + ')'):
            _, index, is_unique, origin, partial = row
            if not is_unique: continue
            terms = []
            for term in conn.execute('PRAGMA index_xinfo(' + quoted(index) + ')'):
                _, cid, column, descending, collate, key = term
                if key:
                    if cid < 0 or column is None:
                        raise ValueError('Expression unique indexes need an explicit reviewed adapter: ' + index)
                    terms.append({'column': column, 'descending': bool(descending), 'collation': collate})
            index_sql = next((obj[3] for obj in objects if obj[0] == 'index' and obj[1] == index), None)
            predicate = ()
            if partial:
                ix = tokens(index_sql or '')
                where = next((i for i, item in enumerate(ix) if item[:2] == ('word', 'where')), None)
                if where is None: raise ValueError('Partial index has no proven WHERE expression')
                predicate = normalized(ix[where+1:], columns)
            unique.append({'terms': terms, 'where': predicate})
        tables[name] = {'columns': values, 'pk': pk,
            'foreign_keys': sorted(fks.values(), key=lambda x: json.dumps(x, sort_keys=True)),
            'unique': sorted(unique, key=lambda x: json.dumps(x, sort_keys=True)), **features}
    return tables, extras, sequence


def field_descriptor(field, model, primary_order):
    from django.conf import settings
    internal = field.get_internal_type()
    effective_field = field.target_field if field.is_relation else field
    effective = effective_field.get_internal_type()
    kinds = {'AutoField': 'integer', 'BigAutoField': 'integer', 'SmallAutoField': 'integer',
        'IntegerField': 'integer', 'BigIntegerField': 'integer', 'SmallIntegerField': 'integer',
        'PositiveIntegerField': 'integer', 'PositiveBigIntegerField': 'integer',
        'PositiveSmallIntegerField': 'integer', 'BooleanField': 'boolean', 'DecimalField': 'decimal',
        'FloatField': 'float', 'CharField': 'char', 'TextField': 'text', 'JSONField': 'json',
        'BinaryField': 'binary', 'FileField': 'file', 'ImageField': 'file', 'DateField': 'date',
        'DateTimeField': 'datetime', 'TimeField': 'time', 'DurationField': 'duration', 'UUIDField': 'uuid',
        'EmailField': 'char', 'URLField': 'char', 'SlugField': 'char', 'GenericIPAddressField': 'char'}
    kind = kinds.get(effective)
    relation = None
    if field.is_relation:
        relation = {'table': field.remote_field.model._meta.db_table, 'column': field.target_field.column}
    choices = [value for value, _ in field.flatchoices] if field.choices else []
    descriptor = {'name': field.column, 'field_name': field.name, 'kind': kind, 'django_type': internal,
        'nullable': field.null, 'pk_order': primary_order.get(field.column, 0),
        'max_length': getattr(effective_field, 'max_length', None), 'max_digits': getattr(effective_field, 'max_digits', None),
        'decimal_places': getattr(effective_field, 'decimal_places', None), 'fk': relation,
        'auto_increment': internal in ('AutoField', 'BigAutoField', 'SmallAutoField'),
        'choices': choices}
    if kind == 'datetime':
        descriptor['sqlite_naive_utc'] = bool(settings.USE_TZ)
    if ((model._meta.label_lower == 'ai_assistant.chatfile' and field.name == 'file')
            or (model._meta.label_lower == 'operations.document' and field.name == 'original_file')):
        descriptor['file_size_column'] = model._meta.get_field('size').column
        if any(f.name == 'checksum' for f in model._meta.fields):
            descriptor['file_checksum_column'] = model._meta.get_field('checksum').column
    return descriptor


def expected_schema(state):
    from django.db.backends.sqlite3.base import DatabaseWrapper
    from django.db.migrations.recorder import MigrationRecorder
    models = [m for m in state.apps.get_models(include_auto_created=True, include_swapped=True)
              if not m._meta.swapped]
    models.append(MigrationRecorder.Migration)
    unmanaged = {m._meta.db_table for m in models if not m._meta.managed}
    models = [m for m in models if m._meta.managed]
    with tempfile.TemporaryDirectory(prefix='a07_expected_schema_') as directory:
        config = {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(Path(directory) / 'expected.sqlite3'),
            'OPTIONS': {}, 'TIME_ZONE': None, 'CONN_MAX_AGE': 0, 'CONN_HEALTH_CHECKS': False,
            'AUTOCOMMIT': True, 'ATOMIC_REQUESTS': False, 'TEST': {}}
        db = DatabaseWrapper(config, alias='a07_expected_' + uuid4().hex)
        try:
            with db.schema_editor(atomic=False) as editor:
                for model in sorted(models, key=lambda m: m._meta.db_table):
                    if not model._meta.auto_created:
                        editor.create_model(model)
            structure, extras, _ = read_sqlite_structure(db.connection)
        finally:
            db.close()
    descriptors = {}
    for model in models:
        name = model._meta.db_table
        primary = {c['name']: c['pk_order'] for c in structure[name]['columns'] if c['pk_order']}
        descriptors[name] = {'model_label': model._meta.label, 'managed': True,
            'columns': [field_descriptor(field, model, primary) for field in model._meta.local_fields],
            'pk': structure[name]['pk']}
    return structure, extras, descriptors, unmanaged


def compare_tables(actual, expected, findings):
    for table in sorted(set(expected) - set(actual)):
        findings.append({'code': 'missing_table', 'table': table})
    for table in sorted(set(actual) - set(expected)):
        findings.append({'code': 'unknown_table', 'table': table})
    for table in sorted(set(actual) & set(expected)):
        a, e = actual[table], expected[table]
        # SQLite ignores declared varchar/decimal precision. The typed model
        # descriptor, not Python defaults or SQL spelling, supplies those bounds.
        ac = {c['name']: {k: v for k, v in c.items() if k != 'declared_type'} for c in a['columns']}
        ec = {c['name']: {k: v for k, v in c.items() if k != 'declared_type'} for c in e['columns']}
        if ac != ec:
            findings.append({'code': 'column_definition_mismatch', 'table': table, 'actual': ac, 'expected': ec})
        for key in ('pk', 'foreign_keys', 'foreign_key_deferral', 'unique', 'checks',
                    'autoincrement', 'without_rowid', 'strict'):
            if a[key] != e[key]:
                findings.append({'code': key + '_mismatch', 'table': table,
                                 'actual': a[key], 'expected': e[key]})


def inspect_schema(path):
    """Return typed descriptors and a fail-closed schema admission decision."""
    path = Path(path).resolve()
    result = {'schema': 1, 'complete': False, 'can_migrate': False, 'profile': 'unknown',
              'known_migrations': False, 'findings': [], 'tables': {}, 'actual_schema': {},
              'expected_schema': {}, 'sqlite_sequence': {}}
    findings = result['findings']
    original_sha = None
    try:
        if not path.is_file(): raise ValueError('Snapshot is not a regular file')
        sidecars = [suffix for suffix in ('-wal', '-shm', '-journal') if Path(str(path) + suffix).exists()]
        if sidecars:
            raise ValueError('Immutable snapshot must not have SQLite sidecars: ' + ', '.join(sidecars))
        original_sha = file_sha(path)
        result['source_sha256'] = original_sha
        uri = path.as_uri() + '?mode=ro&immutable=1'
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.execute('PRAGMA query_only=ON')
            actual, extra, sequence = read_sqlite_structure(conn)
            result.update(actual_schema=actual, sqlite_sequence=sequence,
                          sqlite_schema_hash=stable_sha(actual), extra_schema_objects=extra)
            for obj in extra:
                findings.append({'code': 'unsupported_schema_object', **obj})
            if 'django_migrations' not in actual:
                raise ValueError('Missing migration recorder; profile cannot be inferred from table names')
            rows = conn.execute('SELECT app,name FROM django_migrations ORDER BY app,name').fetchall()
        applied = set(rows)
        if len(rows) != len(applied):
            findings.append({'code': 'duplicate_migration_record', 'records': len(rows), 'unique': len(applied)})
        from django.apps import apps
        from django.conf import settings
        if not apps.ready: raise ValueError('Django must be configured for the reviewed project')
        result['configured_profile'] = {'use_tz': bool(settings.USE_TZ), 'time_zone': settings.TIME_ZONE}
        from django.db.migrations.loader import MigrationLoader
        loader = MigrationLoader(None, ignore_no_migrations=True)
        known = set(loader.disk_migrations)
        unknown = applied - known
        result['known_migrations'] = not unknown
        if unknown:
            findings.append({'code': 'unknown_migrations', 'migrations': sorted(unknown)})
            return result
        unavailable = applied - set(loader.graph.nodes)
        if unavailable:
            findings.append({'code': 'unsupported_replaced_migration_profile', 'migrations': sorted(unavailable)})
            return result
        missing_dependencies = []
        for node in applied:
            missing_dependencies += [parent.key for parent in loader.graph.node_map[node].parents
                                     if parent.key not in applied]
        if missing_dependencies:
            findings.append({'code': 'inconsistent_migration_history', 'missing_dependencies': sorted(set(missing_dependencies))})
            return result
        heads = sorted(node for node in applied if not any(
            child.key in applied for child in loader.graph.node_map[node].children))
        # An empty recorder is a known empty state, not the latest migration state.
        if not applied:
            from django.db.migrations.state import ProjectState
            state = ProjectState(real_apps=loader.unmigrated_apps)
        else:
            state = loader.project_state(nodes=heads)
        expected, expected_extra, tables, unmanaged = expected_schema(state)
        result.update(expected_schema=expected, tables=tables)
        if expected_extra:
            findings.append({'code': 'unsupported_expected_schema_objects', 'objects': expected_extra})
        for table in sorted(unmanaged & set(actual)):
            findings.append({'code': 'unmanaged_table', 'table': table})
        for table, descriptor in tables.items():
            for column in descriptor['columns']:
                if column['kind'] is None:
                    findings.append({'code': 'unsupported_field_kind', 'table': table,
                                     'column': column['name'], 'django_type': column['django_type']})
        compare_tables(actual, expected, findings)
        latest = set(loader.graph.nodes)
        result['profile'] = 'latest' if applied == latest else 'historical'
        migration_state = {'applied': sorted(applied), 'targets': heads,
                           'latest': sorted(loader.graph.leaf_nodes())}
        migration_state['hash'] = stable_sha({'applied': sorted(applied), 'tables': tables,
                                             'expected_schema': expected})
        result['migration_state'] = migration_state
        result['migration_state_hash'] = migration_state['hash']
    except Exception as exc:
        findings.append({'code': 'schema_inspection_error', 'error_type': type(exc).__name__, 'message': str(exc)})
    finally:
        if original_sha is not None:
            try:
                result['source_unchanged'] = original_sha == file_sha(path)
                if not result['source_unchanged']:
                    findings.append({'code': 'source_changed_during_inspection'})
                sidecars = [suffix for suffix in ('-wal', '-shm', '-journal') if Path(str(path) + suffix).exists()]
                if sidecars:
                    findings.append({'code': 'source_sidecars_after_inspection', 'sidecars': sidecars})
            except OSError as exc:
                findings.append({'code': 'source_became_unreadable', 'message': str(exc)})
    result['complete'] = result['can_migrate'] = not findings and bool(result['tables'])
    return result
