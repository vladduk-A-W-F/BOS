"""New bounded source-composition regression. Not an activation/upgrade runner.

Requires an already reviewed composition source tree and explicitly named NEW
synthetic temp parent (BOS_COMPOSITION_TEST_ROOT). No configured default DB is
opened. Frozen original migration fixtures are SHA-checked, never faked.
"""
from contextlib import contextmanager
from datetime import date
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from django.apps import apps
from django.db import connections, migrations
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.db.migrations.state import ModelState
from django.db.migrations.writer import MigrationWriter
from django.test.utils import CaptureQueriesContext

from . import migration_operations_v1 as bridge


FIXTURES = {
    bridge.LOCAL: ('local646/erp/migrations/0006_branch_links.py',
                  '77f54cffecd28e0188fcff937295c0e6ccc5ba9be191f9f193a1ab268c74a8c3'),
    bridge.NETWORK: ('pr2abb8845/erp/migrations/0006_network_operations.py',
                    '040e15b35fd2d87840e9eecad494b192ccfd4625c2ff94a2ca89c9c22a72a1ef'),
    bridge.TIMING: ('pr2abb8845/erp/migrations/0007_request_timing.py',
                   '529a8f24cc8ad817806a0ec990222936be336c256baea6c1a831110dfe433060'),
}


def _original(name):
    root = Path(os.environ.get('BOS_COMPOSITION_ORIGINALS',
                              str(Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' /
                                  'network_migration_composition'))).resolve()
    relative, expected = FIXTURES[name]
    path = root / relative
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise AssertionError('Original migration fixture hash mismatch: ' + name)
    spec = importlib.util.spec_from_file_location('bos_original_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Migration(name, 'erp')


class _OriginalHistoryLoader(MigrationLoader):
    def __init__(self, connection, history):
        self.history = history
        super().__init__(connection)

    def load_disk(self):
        super().load_disk()
        allowed = {bridge.LOCAL} if self.history == 'local' else {bridge.NETWORK, bridge.TIMING}
        for name in (bridge.LOCAL, bridge.NETWORK, bridge.TIMING, bridge.COMPOSED):
            self.disk_migrations.pop(('erp', name), None)
        for name in allowed:
            self.disk_migrations[('erp', name)] = _original(name)


def _loader():
    if not apps.ready:
        raise AssertionError('Use an explicitly configured Django test runner; no implicit setup.')
    return MigrationLoader(None)


def _base_state():
    return _loader().project_state([
        ('erp', '0005_source_corrections'),
        ('branches', '0003_fill_short_names'),
        ('operations', '0009_request_timing'),
    ])


def _normal_state(state):
    return {name: ({key: bridge._signature(field)
                   for key, field in state.models[('erp', name)].fields.items()},
                  state.models[('erp', name)].options)
            for name in bridge.ERP_MODELS}


@contextmanager
def _owned_database():
    parent = Path(os.environ['BOS_COMPOSITION_TEST_ROOT'])
    if not parent.is_absolute() or not parent.is_dir():
        raise AssertionError('Explicit existing absolute synthetic temp parent is required.')
    parent = parent.resolve()
    source = Path(__file__).resolve().parents[1]
    if parent == source or source in parent.parents:
        raise AssertionError('Synthetic temp parent must be outside the source checkout.')
    owned = Path(tempfile.mkdtemp(prefix='bos-migration-compose-', dir=parent)).resolve()
    if owned.parent != parent or not owned.name.startswith('bos-migration-compose-'):
        raise AssertionError('Unexpected owned temp directory.')
    alias = 'bos_composition_' + uuid4().hex
    config = {
        'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(owned / 'synthetic.sqlite3'),
        'OPTIONS': {}, 'TIME_ZONE': None, 'ATOMIC_REQUESTS': False, 'AUTOCOMMIT': True,
        'CONN_MAX_AGE': 0, 'CONN_HEALTH_CHECKS': False,
        'USER': '', 'PASSWORD': '', 'HOST': '', 'PORT': '',
        'TEST': {'CHARSET': None, 'COLLATION': None, 'MIGRATE': True, 'MIRROR': None, 'NAME': None},
    }
    connection = None
    try:
        connections.databases[alias] = config
        connection = connections[alias]
        yield connection
    finally:
        if connection is not None:
            connection.close()
            del connections[alias]
        connections.databases.pop(alias, None)
        # This code never removes the supplied parent or any pre-existing path.
        if owned.resolve().parent != parent or not owned.name.startswith('bos-migration-compose-'):
            raise AssertionError('Refuse cleanup outside newly owned directory.')
        shutil.rmtree(owned)


def _seed(state, alias):
    def create(app, model, **kwargs):
        return state.apps.get_model(app, model).objects.using(alias).create(**kwargs)
    a = create('branches', 'Branch', code='MIG-A', name='Synthetic A')
    b = create('branches', 'Branch', code='MIG-B', name='Synthetic B')
    location_a = create('erp', 'Location', code='MIG-LA', name='A', branch_id=a.pk)
    location_b = create('erp', 'Location', code='MIG-LB', name='B', branch_id=b.pk)
    create('erp', 'Location', code='MIG-LNULL', name='Null', branch_id=None)
    customer = create('finance', 'Counterparty', name='Synthetic customer', type='customer')
    supplier = create('finance', 'Counterparty', name='Synthetic supplier', type='supplier')
    owner = create('employees', 'Employee', full_name='Synthetic owner', role='test')
    fields = state.models[('erp', 'salesorder')].fields
    links = {}
    if 'branch' in fields:
        links['branch_id'] = a.pk
    if 'fulfillment_location' in fields:
        links['fulfillment_location_id'] = location_b.pk
    order = create('erp', 'SalesOrder', code='MIG-ORDER', customer_id=customer.pk,
                   owner_id=owner.pk, due_date=date(2026, 9, 30), currency='EUR', **links)
    create('erp', 'SalesOrder', code='MIG-NULL', customer_id=customer.pk,
           owner_id=owner.pk, due_date=date(2026, 9, 30), currency='EUR')
    item = create('erp', 'Item', code='MIG-ITEM', name='Synthetic item', currency='EUR')
    purchase = create('erp', 'Purchase', code='MIG-PO', item_id=item.pk, supplier_id=supplier.pk,
                      quantity='3', price='5', currency='EUR', revision='A',
                      due_date=date(2026, 9, 30), original_due=date(2026, 9, 30))
    if ('erp', 'stocktransfer') in state.models:
        lot = create('erp', 'Lot', code='MIG-LOT', item_id=item.pk, location_id=location_a.pk,
                     quantity='2', unit_cost='5', currency='EUR', revision='A', quality='approved')
        move = create('erp', 'Movement', lot_id=lot.pk, quantity='-1', cost='5',
                      kind='transfer_dispatch', reference='MIG-T', reason='synthetic')
        create('erp', 'StockTransfer', code='MIG-T', source_lot_id=lot.pk,
               source_location_id=location_a.pk, destination_id=location_b.pk, item_id=item.pk,
               quantity='1', revision='A', documents={}, unit_cost='5', total_cost='5',
               currency='EUR', dispatch_movement_id=move.pk, reason='synthetic')
        invoice = create('operations', 'Invoice', code='MIG-I', customer_id=customer.pk,
                         amount='50', currency='EUR', due_date=date(2026, 9, 30))
        create('erp', 'PaymentRetention', code='MIG-H', invoice_id=invoice.pk,
               amount='7', currency='EUR', reason='synthetic')
    return {'a': a.pk, 'b_location': location_b.pk, 'order': order.pk, 'purchase': purchase.pk}


def _rows(state, alias):
    names = [('branches', 'branch'), ('finance', 'counterparty'), ('employees', 'employee'),
             ('operations', 'invoice'), *[('erp', name) for name in bridge.ERP_MODELS],
             ('erp', 'movement')]
    return {(app, name): list(state.apps.get_model(app, name).objects.using(alias).order_by('pk').values())
            for app, name in names if (app, name) in state.models}


class NetworkMigrationCompositionTests(unittest.TestCase):
    """Seven methods; the real forward method has exactly three history cases."""

    def test_state_orders_and_model_union(self):
        loader, states = _loader(), []
        for sequence in ((bridge.LOCAL, bridge.NETWORK), (bridge.NETWORK, bridge.LOCAL)):
            state = _base_state()
            for name in (*sequence, bridge.TIMING, bridge.COMPOSED):
                state = loader.get_migration('erp', name).mutate_state(state)
            states.append(state)
        self.assertEqual(_normal_state(states[0]), _normal_state(states[1]))
        for name in bridge.ERP_MODELS:
            historical = states[0].models[('erp', name)]
            current = ModelState.from_model(apps.get_model('erp', name))
            self.assertEqual({k: bridge._signature(v) for k, v in historical.fields.items()},
                             {k: bridge._signature(v) for k, v in current.fields.items()})
            self.assertEqual(historical.options.get('constraints', []), current.options.get('constraints', []))

    def test_three_original_histories_converge_and_replay(self):
        for history in ('fresh', 'local', 'network'):
            with self.subTest(history=history), _owned_database() as connection:
                alias = connection.alias
                before = None
                if history != 'fresh':
                    original = MigrationExecutor(connection)
                    original.loader = _OriginalHistoryLoader(connection, history)
                    target = bridge.LOCAL if history == 'local' else bridge.TIMING
                    original.migrate([('erp', target)])
                    old_state = original.loader.project_state([('erp', target)])
                    ids = _seed(old_state, alias)
                    before = _rows(old_state, alias)
                executor = MigrationExecutor(connection)
                executor.loader.check_consistent_history(connection)
                state = executor.migrate([('erp', bridge.COMPOSED)])
                if history == 'fresh':
                    ids = _seed(state, alias)
                after = _rows(state, alias)
                if before is not None:
                    for key, rows in before.items():
                        self.assertEqual(rows, [{name: row[name] for name in original_row}
                                               for original_row, row in zip(rows, after[key])])
                        self.assertEqual(len(rows), len(after[key]))
                Order = state.apps.get_model('erp', 'SalesOrder')
                order = Order.objects.using(alias).get(pk=ids['order'])
                if history == 'local':
                    self.assertIsNone(order.fulfillment_location_id)
                    self.assertIsNone(state.apps.get_model('erp', 'Purchase').objects.using(alias)
                                      .get(pk=ids['purchase']).created_at)
                if history == 'network':
                    self.assertIsNone(order.branch_id)
                # Explicit NEW test intent, never a migration backfill.
                order.branch_id, order.fulfillment_location_id = ids['a'], ids['b_location']
                order.save(using=alias, update_fields=['branch', 'fulfillment_location'])
                self.assertNotEqual(order.branch_id, order.fulfillment_location.branch_id)
                null_order = Order.objects.using(alias).get(code='MIG-NULL')
                self.assertIsNone(null_order.branch_id)
                self.assertIsNone(null_order.fulfillment_location_id)
                expected = _rows(state, alias)
                replay = MigrationExecutor(connection)
                self.assertEqual(replay.migration_plan([('erp', bridge.COMPOSED)]), [])
                receipts = set(MigrationRecorder(connection).applied_migrations())
                with CaptureQueriesContext(connection) as queries:
                    replay.migrate([('erp', bridge.COMPOSED)])
                self.assertEqual(receipts, set(MigrationRecorder(connection).applied_migrations()))
                self.assertEqual(expected, _rows(state, alias))
                self.assertFalse(any(q['sql'].lstrip().upper().startswith(
                    ('INSERT', 'UPDATE', 'DELETE', 'ALTER', 'CREATE', 'DROP')) for q in queries))
                with connection.cursor() as cursor:
                    columns = connection.introspection.get_table_description(cursor, 'erp_location')
                self.assertEqual(sum(row.name == 'branch_id' for row in columns), 1)

    def test_shared_field_refuses_unowned_missing_and_mismatched(self):
        before, operation = _base_state(), bridge.SharedLocationBranch(bridge.LOCAL)
        after = before.clone()
        operation.state_forwards('erp', after)
        connection = Mock()
        cases = [(set(), {'branch_id': object()}, None),
                 ({bridge.NETWORK}, {}, None),
                 ({bridge.NETWORK}, {'branch_id': object()}, bridge.CompositionSchemaError('drift'))]
        for receipts, columns, error in cases:
            with self.subTest(receipts=receipts, column=bool(columns)), \
                 patch.object(bridge, '_receipts', return_value=receipts), \
                 patch.object(bridge, '_columns', return_value=columns), \
                 patch.object(bridge, '_assert_fk', side_effect=error), \
                 self.assertRaises(bridge.CompositionSchemaError):
                bridge._shared_decision(connection, bridge.LOCAL, before, after)

    def test_router_rejection_precedes_schema_work_including_new_models(self):
        migration = _loader().get_migration('erp', bridge.NETWORK)
        preflight = migration.operations[0]
        editor = Mock()
        editor.connection.vendor = 'sqlite'
        editor.connection.features.can_rollback_ddl = True
        editor.connection.alias = 'default'
        for denied in ('location', 'stocktransfer'):
            with self.subTest(denied=denied), \
                 patch.object(preflight, 'allow_migrate_model',
                              side_effect=lambda alias, model: model._meta.model_name != denied), \
                 patch.object(bridge, '_receipts', return_value=set()), \
                 patch.object(bridge, '_entry_history') as inspect, \
                 self.assertRaises(bridge.CompositionSchemaError):
                preflight.database_forwards('erp', editor, _base_state(), _base_state())
            inspect.assert_not_called()
            editor.add_field.assert_not_called()
            editor.execute.assert_not_called()

    def test_sqlite_declaration_is_one_exact_column(self):
        sql = ('CREATE TABLE "erp_location" ("id" integer NOT NULL PRIMARY KEY, '
               '"note" text DEFAULT \'comma, (not a column)\', '
               '"branch_id" bigint NULL REFERENCES "branches_branch" ("id") DEFERRABLE INITIALLY DEFERRED)')
        self.assertTrue(bridge._sqlite_declaration(sql, 'branch_id').startswith('"branch_id" bigint'))
        for invalid in ('CREATE TABLE x ("other" text)', sql + '; SELECT 1', sql.replace('CREATE TABLE', '--x\nCREATE TABLE')):
            with self.subTest(sql=invalid), self.assertRaises(bridge.CompositionSchemaError):
                bridge._sqlite_declaration(invalid, 'branch_id')
        state = _base_state()
        bridge.SharedLocationBranch(bridge.LOCAL).state_forwards('erp', state)
        field = state.apps.get_model('erp', 'Location')._meta.get_field('branch')
        column = [(0, 'branch_id', 'bigint', 0, None, 0, 0)]
        fk = [(0, 0, 'branches_branch', 'branch_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
        index = [(0, 'branch_lookup', 0, 'c', 0)]
        cases = [
            (column, fk, index, sql, True),
            ([(0, 'branch_id', 'bigint', 1, None, 0, 0)], fk, index, sql, False),
            (column, [(0, 0, 'branches_branch', 'branch_id', 'id', 'NO ACTION', 'CASCADE', 'NONE')], index, sql, False),
            (column, fk, [], sql, False),
            (column, fk, [(0, 'branch_lookup', 1, 'c', 0)], sql, False),
            (column, fk, index, sql.replace('INITIALLY DEFERRED', 'INITIALLY IMMEDIATE'), False),
        ]
        for columns, fks, indexes, declaration, succeeds in cases:
            with self.subTest(sqlite_schema=succeeds):
                connection, cursor = Mock(), Mock()
                connection.ops.quote_name.side_effect = lambda value: '"' + value + '"'
                connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
                connection.cursor.return_value.__exit__ = Mock(return_value=False)
                cursor.fetchall.side_effect = [columns, fks, indexes, [(0, 0, 'branch_id')]]
                cursor.fetchone.return_value = (declaration,)
                with patch.object(field, 'db_type', return_value='bigint'):
                    if succeeds:
                        bridge._sqlite_fk(connection, 'erp_location', field)
                    else:
                        with self.assertRaises(bridge.CompositionSchemaError):
                            bridge._sqlite_fk(connection, 'erp_location', field)

    def test_barriers_serialization_and_deferred_index(self):
        loader = _loader()
        for name in (bridge.LOCAL, bridge.NETWORK, bridge.COMPOSED):
            migration = loader.get_migration('erp', name)
            rendered = MigrationWriter(migration).as_string()
            self.assertIn('erp.migration_operations_v1', rendered)
            for operation in migration.operations:
                if isinstance(operation, bridge._ForwardBarrier):
                    self.assertFalse(operation.reversible)
                    neighbour = migrations.RunPython(migrations.RunPython.noop, elidable=True)
                    self.assertIs(operation.reduce(neighbour, 'erp'), False)
        before, op = _base_state(), bridge.SharedLocationBranch(bridge.LOCAL)
        after = before.clone()
        op.state_forwards('erp', after)
        editor = Mock()
        editor.deferred_sql = ['CREATE INDEX later']
        with patch.object(bridge, '_router_gate'), \
             patch.object(bridge, '_shared_decision', return_value='add'), \
             patch.object(bridge, '_assert_fk') as inspect:
            op.database_forwards('erp', editor, before, after)
        editor.add_field.assert_called_once()
        inspect.assert_not_called()
        self.assertEqual(editor.deferred_sql, ['CREATE INDEX later'])

    def test_postgres_catalog_rejects_incorrect_constraint_or_index(self):
        state = _base_state()
        bridge.SharedLocationBranch(bridge.LOCAL).state_forwards('erp', state)
        field = state.apps.get_model('erp', 'Location')._meta.get_field('branch')
        column = [(4, 'bigint', False, '', '', None)]
        fk = [([4], True, ['id'], 'a', 'a', 's', True, True, True)]
        good_index = [('4', False, False, True, True, True, True, 1, 1, 'btree')]
        for fks, indexes, succeeds in [(fk, good_index, True), ([], good_index, False),
                                       (fk, [], False), (fk, [('4', True, False, True, True, True, True, 1, 1, 'btree')], False)]:
            with self.subTest(fks=bool(fks), index=bool(indexes), succeeds=succeeds):
                connection, cursor = Mock(), Mock()
                connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
                connection.cursor.return_value.__exit__ = Mock(return_value=False)
                cursor.fetchall.side_effect = [column, fks, indexes]
                with patch.object(field, 'db_type', return_value='bigint'):
                    if succeeds:
                        bridge._postgres_fk(connection, 'erp_location', field)
                    else:
                        with self.assertRaises(bridge.CompositionSchemaError):
                            bridge._postgres_fk(connection, 'erp_location', field)
