"""Custom migration operations preserving existing SQLite ID high-water.

Destination: boss_project/migration_operations.py.  This module is part of
the permanent migration API and must retain its import path while migrations
reference it.  PostgreSQL uses Django's ordinary AddConstraint operation.
"""
from contextlib import contextmanager

from django.db import migrations


@contextmanager
def _preserve_sqlite_sequence(schema_editor, table):
    connection = schema_editor.connection
    if connection.vendor != 'sqlite':
        yield
        return
    if schema_editor.collect_sql:
        raise RuntimeError('SQLite sequence preservation requires migrate execution; static SQL cannot capture the source high-water.')

    with connection.cursor() as cursor:
        cursor.execute('SELECT seq FROM sqlite_sequence WHERE name = %s', [table])
        old_rows = cursor.fetchall()
    if len(old_rows) > 1:
        raise RuntimeError('Ambiguous SQLite sequence metadata for ' + table)
    old_value = old_rows[0][0] if old_rows else None
    if old_rows and (not isinstance(old_value, int) or old_value < 0):
        raise RuntimeError('Invalid SQLite sequence metadata for ' + table)

    # A failed DDL operation is left to Django's atomic migration rollback.
    # Do not execute metadata writes while its transaction may be broken.
    yield

    if old_value is None:
        return
    with connection.cursor() as cursor:
        cursor.execute('SELECT seq FROM sqlite_sequence WHERE name = %s', [table])
        current_rows = cursor.fetchall()
        if len(current_rows) > 1:
            raise RuntimeError('Ambiguous SQLite sequence metadata for ' + table)
        if not current_rows:
            cursor.execute('INSERT INTO sqlite_sequence (name, seq) VALUES (%s, %s)', [table, old_value])
        else:
            current_value = current_rows[0][0]
            if not isinstance(current_value, int) or current_value < 0:
                raise RuntimeError('Invalid SQLite sequence metadata for ' + table)
            if current_value < old_value:
                cursor.execute('UPDATE sqlite_sequence SET seq = %s WHERE name = %s', [old_value, table])


class PreserveSequenceAddConstraint(migrations.AddConstraint):
    """AddConstraint with the same state/serialization and safe SQLite DDL."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        if self.allow_migrate_model(schema_editor.connection.alias, model):
            with _preserve_sqlite_sequence(schema_editor, model._meta.db_table):
                super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        if self.allow_migrate_model(schema_editor.connection.alias, model):
            with _preserve_sqlite_sequence(schema_editor, model._meta.db_table):
                super().database_backwards(app_label, schema_editor, from_state, to_state)


class PreserveSequenceAddField(migrations.AddField):
    """Retain historical SQLite sequence high-water if a field rebuilds a table."""
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        if self.allow_migrate_model(schema_editor.connection.alias, model):
            with _preserve_sqlite_sequence(schema_editor, model._meta.db_table):
                super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        model = from_state.apps.get_model(app_label, self.model_name)
        if self.allow_migrate_model(schema_editor.connection.alias, model):
            with _preserve_sqlite_sequence(schema_editor, model._meta.db_table):
                super().database_backwards(app_label, schema_editor, from_state, to_state)
