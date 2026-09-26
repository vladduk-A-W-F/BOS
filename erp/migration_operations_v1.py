"""Frozen forward-only bridge for the two published ERP 0006 histories.

Do not import live application models here. This module is outside migrations/
so the migration loader cannot mistake it for an additional graph node.
"""
import re

import sqlparse
from sqlparse.sql import Parenthesis
from sqlparse import tokens as SQL

from django.db import models
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.operations.base import Operation
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone


LOCAL = '0006_branch_links'
NETWORK = '0006_network_operations'
TIMING = '0007_request_timing'
COMPOSED = '0008_compose_branch_network'
OWNERS = {LOCAL, NETWORK}
ERP_MODELS = ('item', 'location', 'lot', 'salesorder', 'production', 'purchase',
              'stocktransfer', 'paymentretention')
NETWORK_COLUMNS = {
    'erp_location': ('address', 'lat', 'lng'),
    'erp_salesorder': ('fulfillment_location_id', 'destination_country'),
    'erp_purchase': ('destination_id', 'origin_country'),
}
NETWORK_TABLES = ('erp_stocktransfer', 'erp_paymentretention')


class CompositionSchemaError(RuntimeError):
    """Recorded history and schema must agree before any mutation."""


def _require(condition, category):
    if not condition:
        # Names/categories only: never include business rows or connection data.
        raise CompositionSchemaError('NETWORK-MIGRATION-COMPOSITION: ' + category)


def _branch_field():
    return models.ForeignKey('branches.branch', null=True, blank=True,
                             on_delete=models.PROTECT)


def _signature(field):
    _, path, args, kwargs = field.deconstruct()
    kwargs = dict(kwargs)
    if isinstance(kwargs.get('to'), str):
        kwargs['to'] = kwargs['to'].lower()
    return path, args, kwargs


def _canonical_field(state, model, name, expected):
    actual = state.models[('erp', model)].fields.get(name)
    _require(actual is not None and _signature(actual) == _signature(expected),
             'model-state mismatch: ' + model + '.' + name)


def _supported(connection):
    _require(connection.vendor in ('sqlite', 'postgresql'), 'unsupported backend')
    _require(connection.features.can_rollback_ddl, 'nontransactional DDL backend')


def _router_gate(operation, editor, state):
    """Check the same historical-model eligibility used by Django operations."""
    _supported(editor.connection)
    for app, name in [('branches', 'branch'), *[('erp', n) for n in ERP_MODELS]]:
        if (app, name) in state.models:
            model = state.apps.get_model(app, name)
            _require(operation.allow_migrate_model(editor.connection.alias, model),
                     'router/model ineligible: ' + app + '.' + name)


def _tables(connection):
    with connection.cursor() as cursor:
        return set(connection.introspection.table_names(cursor))


def _columns(connection, table):
    with connection.cursor() as cursor:
        return {row.name: row for row in connection.introspection.get_table_description(cursor, table)}


def _receipts(connection):
    applied = MigrationRecorder(connection).applied_migrations()
    return {name for app, name in applied if app == 'erp'}


def _sqlite_declaration(sql, column):
    """Accept only one Django-style column declaration, not arbitrary SQL.

    sqlparse supplies lexical strings/parentheses so commas inside literals or
    CHECK expressions cannot impersonate another column. We do not interpret
    general SQL or rewrite it; any unsupported shape is a hard failure.
    """
    _require(isinstance(sql, str) and len(sql) <= 1024 * 1024, 'SQLite DDL unavailable')
    statements = sqlparse.parse(sql)
    _require(len(statements) == 1 and statements[0].get_type() == 'CREATE',
             'unsupported SQLite table declaration')
    _require(not any(t.ttype in SQL.Comment for t in statements[0].flatten()),
             'unsupported SQLite commented declaration')
    groups = [t for t in statements[0].tokens if isinstance(t, Parenthesis)]
    _require(len(groups) == 1, 'unsupported SQLite table body')
    chunks, part, depth = [], [], 0
    flat = list(groups[0].flatten())
    _require(flat[0].value == '(' and flat[-1].value == ')', 'SQLite table body')
    for token in flat[1:-1]:
        if token.ttype in SQL.Punctuation:
            if token.value == '(':
                depth += 1
            elif token.value == ')':
                depth -= 1
                _require(depth >= 0, 'SQLite nested declaration')
            elif token.value == ',' and depth == 0:
                chunks.append(part)
                part = []
                continue
        part.append(token)
    chunks.append(part)
    _require(depth == 0, 'SQLite unbalanced declaration')
    matches = []
    for chunk in chunks:
        useful = [token for token in chunk if not token.is_whitespace]
        if useful and useful[0].value == '"' + column + '"':
            matches.append(''.join(token.value for token in chunk).strip())
    _require(len(matches) == 1, 'SQLite FK column declaration ambiguous')
    return matches[0]


def _sqlite_fk(connection, table, field):
    q = connection.ops.quote_name
    column = field.column
    target_table, target_column = field.target_field.model._meta.db_table, field.target_field.column
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA table_xinfo(%s)' % q(table))
        rows = [row for row in cursor.fetchall() if row[1] == column]
        _require(len(rows) == 1, 'SQLite missing/duplicate FK column')
        _, _, kind, notnull, default, pk, hidden = rows[0]
        _require(kind.lower() == field.db_type(connection).lower() and not notnull
                 and default is None and not pk and not hidden, 'SQLite FK column type/null/default')
        cursor.execute('PRAGMA foreign_key_list(%s)' % q(table))
        foreign = [row for row in cursor.fetchall() if row[3] == column]
        _require(len(foreign) == 1, 'SQLite FK count')
        row = foreign[0]
        _require(row[1] == 0 and row[2:5] == (target_table, column, target_column)
                 and row[5:8] == ('NO ACTION', 'NO ACTION', 'NONE'), 'SQLite FK target/actions')
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=%s", [table])
        sql_row = cursor.fetchone()
        declaration = _sqlite_declaration(sql_row[0] if sql_row else None, column)
        expected = (re.escape(q(column)) + r'\s+' + re.escape(field.db_type(connection))
                    + r'\s+NULL\s+REFERENCES\s+' + re.escape(q(target_table))
                    + r'\s*\(\s*' + re.escape(q(target_column))
                    + r'\s*\)\s+DEFERRABLE\s+INITIALLY\s+DEFERRED')
        _require(re.fullmatch(expected, declaration, flags=re.IGNORECASE) is not None,
                 'unsupported SQLite FK declaration/deferral')
        cursor.execute('PRAGMA index_list(%s)' % q(table))
        indexes = cursor.fetchall()
        valid = []
        for _, name, unique, origin, partial in indexes:
            cursor.execute('PRAGMA index_info(%s)' % q(name))
            names = [r[2] for r in cursor.fetchall()]
            if names == [column]:
                _require(not unique, 'SQLite unexpected FK uniqueness')
                if origin == 'c' and not partial:
                    valid.append(name)
        _require(bool(valid), 'SQLite FK nonunique full index missing')


def _postgres_fk(connection, table, field):
    column = field.column
    target_table, target_column = field.target_field.model._meta.db_table, field.target_field.column
    with connection.cursor() as cursor:
        cursor.execute('''SELECT a.attnum, format_type(a.atttypid,a.atttypmod),
            a.attnotnull,a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid)
            FROM pg_attribute a LEFT JOIN pg_attrdef d
            ON d.adrelid=a.attrelid AND d.adnum=a.attnum
            WHERE a.attrelid=to_regclass(%s) AND a.attname=%s AND NOT a.attisdropped''',
            [table, column])
        rows = cursor.fetchall()
        _require(len(rows) == 1, 'PostgreSQL FK column missing/duplicate')
        number, kind, notnull, identity, generated, default = rows[0]
        _require(kind == field.db_type(connection) and not notnull and not identity
                 and not generated and default is None, 'PostgreSQL FK column type/null/default')
        cursor.execute('''SELECT c.conkey, c.confrelid=to_regclass(%s),
            ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY u(n,ord)
                  JOIN pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=u.n ORDER BY u.ord),
            c.confupdtype,c.confdeltype,c.confmatchtype,c.convalidated,c.condeferrable,c.condeferred
            FROM pg_constraint c WHERE c.conrelid=to_regclass(%s)
            AND c.contype='f' AND %s=ANY(c.conkey)''', [target_table, table, number])
        fks = cursor.fetchall()
        _require(len(fks) == 1, 'PostgreSQL FK count')
        key, target, names, update, delete, match, valid, defer, initially = fks[0]
        _require(list(key) == [number] and target and list(names) == [target_column]
                 and (update, delete, match) == ('a', 'a', 's') and valid and defer and initially,
                 'PostgreSQL FK target/actions/validation/deferral')
        cursor.execute('''SELECT i.indkey::text,i.indisunique,i.indisprimary,i.indisvalid,
            i.indisready,i.indpred IS NULL,i.indexprs IS NULL,i.indnkeyatts,i.indnatts,am.amname
            FROM pg_index i JOIN pg_class ix ON ix.oid=i.indexrelid
            JOIN pg_am am ON am.oid=ix.relam
            WHERE i.indrelid=to_regclass(%s) AND %s=ANY(i.indkey)''', [table, number])
        indexes = cursor.fetchall()
        candidates = []
        for keys, unique, primary, valid, ready, full, simple, nkeys, nattrs, method in indexes:
            if [int(n) for n in keys.split()] == [number]:
                _require(not unique and not primary, 'PostgreSQL unexpected FK uniqueness')
                if valid and ready and full and simple and nkeys == nattrs == 1 and method == 'btree':
                    candidates.append(keys)
        _require(bool(candidates), 'PostgreSQL FK nonunique full index missing')


def _assert_fk(connection, model, name):
    field = model._meta.get_field(name)
    _require(isinstance(field, models.ForeignKey) and field.null
             and field.remote_field.on_delete is models.PROTECT and field.db_index
             and not field.unique and not field.primary_key, 'historical FK contract')
    if connection.vendor == 'sqlite':
        _sqlite_fk(connection, model._meta.db_table, field)
    elif connection.vendor == 'postgresql':
        _postgres_fk(connection, model._meta.db_table, field)
    else:
        raise CompositionSchemaError('unsupported backend')


def _shared_decision(connection, owner, from_state, to_state):
    _require(owner in OWNERS, 'unknown owner')
    receipts = _receipts(connection)
    _require(owner not in receipts, 'owner already recorded; direct replay prohibited')
    sibling = NETWORK if owner == LOCAL else LOCAL
    model = to_state.apps.get_model('erp', 'location')
    present = 'branch_id' in _columns(connection, model._meta.db_table)
    if sibling in receipts:
        _require(present, 'sibling receipt without shared column')
        _assert_fk(connection, model, 'branch')
        return 'skip'
    _require(not present, 'shared column without sibling receipt')
    _require('branch' not in from_state.models[('erp', 'location')].fields,
             'unrecorded shared model state')
    return 'add'


def _entry_history(connection, state):
    receipts, tables = _receipts(connection), _tables(connection)
    local, network = LOCAL in receipts, NETWORK in receipts
    _require(TIMING not in receipts or network, 'timing receipt without network')
    _require(COMPOSED not in receipts, 'composition already recorded')
    _require({'erp_location', 'erp_salesorder', 'erp_purchase'} <= tables, 'base tables missing')
    columns = {table: _columns(connection, table) for table in NETWORK_COLUMNS}
    _require(('branch_id' in columns['erp_location']) == (local or network),
             'shared history/column disagreement')
    _require(('branch_id' in columns['erp_salesorder']) == local,
             'organisational branch history/column disagreement')
    if local or network:
        _canonical_field(state, 'location', 'branch', _branch_field())
        _assert_fk(connection, state.apps.get_model('erp', 'location'), 'branch')
    if local:
        _canonical_field(state, 'salesorder', 'branch', _branch_field())
        _assert_fk(connection, state.apps.get_model('erp', 'salesorder'), 'branch')
    for table, names in NETWORK_COLUMNS.items():
        for name in names:
            _require((name in columns[table]) == network, 'network marker history: ' + table + '.' + name)
    for table in NETWORK_TABLES:
        _require((table in tables) == network, 'network table history: ' + table)
    _require(('created_at' in columns['erp_purchase']) == (TIMING in receipts),
             'purchase timing history/column disagreement')
    if network:
        for model, name in [('salesorder', 'fulfillment_location'), ('purchase', 'destination')]:
            _assert_fk(connection, state.apps.get_model('erp', model), name)


class _ForwardBarrier(Operation):
    reversible = False
    reduces_to_sql = False
    elidable = False

    def state_forwards(self, app_label, state):
        _require(app_label == 'erp', 'wrong migration app')

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        raise IrreversibleError('NETWORK-MIGRATION-COMPOSITION is forward-only; no shared FK removal.')

    def reduce(self, operation, app_label):
        # Even an elidable neighbour must not erase this history/schema guard.
        return False


class AssertCompositionEntry(_ForwardBarrier):
    serialization_expand_args = ['forward_operations']

    def __init__(self, owner, forward_operations):
        _require(owner in OWNERS, 'unknown owner')
        self.owner = owner
        self.forward_operations = list(forward_operations)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        _require(app_label == 'erp', 'wrong migration app')
        _require(self.owner not in _receipts(schema_editor.connection), 'owner already recorded')
        # Simulate *state only*. Check historical router hints before and after
        # every upcoming operation, including models created later by network0006.
        state = from_state.clone()
        _router_gate(self, schema_editor, state)
        for operation in self.forward_operations:
            _require(not isinstance(operation, AssertCompositionEntry), 'recursive preflight')
            operation.state_forwards(app_label, state)
            _router_gate(self, schema_editor, state)
        _entry_history(schema_editor.connection, from_state)


class SharedLocationBranch(_ForwardBarrier):
    def __init__(self, owner):
        _require(owner in OWNERS, 'unknown owner')
        self.owner = owner

    def state_forwards(self, app_label, state):
        super().state_forwards(app_label, state)
        expected = _branch_field()
        if 'branch' in state.models[('erp', 'location')].fields:
            _canonical_field(state, 'location', 'branch', expected)
        else:
            state.add_field('erp', 'location', 'branch', expected, preserve_default=True)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        _require(app_label == 'erp', 'wrong migration app')
        _router_gate(self, schema_editor, from_state)
        _router_gate(self, schema_editor, to_state)
        _canonical_field(to_state, 'location', 'branch', _branch_field())
        if _shared_decision(schema_editor.connection, self.owner, from_state, to_state) == 'add':
            before = from_state.apps.get_model('erp', 'location')
            after = to_state.apps.get_model('erp', 'location')
            schema_editor.add_field(before, after._meta.get_field('branch'))
            # No index assertion here: CREATE INDEX may be deferred until exit.


class AssertComposedNetworkSchema(_ForwardBarrier):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        _require(app_label == 'erp', 'wrong migration app')
        connection = schema_editor.connection
        _router_gate(self, schema_editor, to_state)
        _require({LOCAL, NETWORK, TIMING} <= _receipts(connection), 'composition parent receipts missing')
        _require(COMPOSED not in _receipts(connection), 'composition already recorded')
        _entry_history(connection, to_state)
        for model, name, expected in [
            ('location', 'branch', _branch_field()),
            ('salesorder', 'branch', _branch_field()),
            ('salesorder', 'fulfillment_location', models.ForeignKey(
                'erp.location', null=True, blank=True, on_delete=models.PROTECT)),
            ('purchase', 'destination', models.ForeignKey(
                'erp.location', null=True, blank=True, on_delete=models.PROTECT)),
            ('purchase', 'created_at', models.DateTimeField(null=True, default=timezone.now, editable=False)),
        ]:
            _canonical_field(to_state, model, name, expected)
        for name in ('item', 'lot', 'salesorder', 'production', 'purchase'):
            _require(to_state.models[('erp', name)].fields['currency'].default == 'UAH',
                     'currency model default mismatch: ' + name)
        tables = _tables(connection)
        for name in ERP_MODELS:
            _require(('erp', name) in to_state.models, 'composed model missing: ' + name)
            model = to_state.apps.get_model('erp', name)
            table = model._meta.db_table
            _require(table in tables, 'composed table missing: ' + table)
            expected = {field.column for field in model._meta.local_fields}
            _require(set(_columns(connection, table)) == expected, 'composed column set: ' + table)
            # Check named constraint presence/type. Full SQL expression equality
            # is not claimed; new DDL is still authored by the original migration.
            with connection.cursor() as cursor:
                actual = connection.introspection.get_constraints(cursor, table)
            for constraint in model._meta.constraints:
                value = actual.get(constraint.name)
                _require(value is not None, 'composed constraint missing: ' + constraint.name)
                if isinstance(constraint, models.CheckConstraint):
                    _require(value.get('check'), 'composed check type: ' + constraint.name)
                elif isinstance(constraint, models.UniqueConstraint):
                    _require(value.get('unique'), 'composed unique type: ' + constraint.name)
