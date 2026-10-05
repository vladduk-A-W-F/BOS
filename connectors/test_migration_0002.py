"""Migration connectors 0002 adds `mapping` without lowering the id high-water on SQLite. Synthetic rows only."""
from unittest import skipUnless

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [('connectors', '0001_initial')]
AFTER = [('connectors', '0002_connector_mapping')]


@skipUnless(connection.vendor == 'sqlite', 'sqlite_sequence is SQLite-specific')
class MappingMigrationTests(TransactionTestCase):
    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)

    def tearDown(self):
        self.migrate(AFTER)

    def seq(self):
        with connection.cursor() as c:
            row = c.execute("SELECT seq FROM sqlite_sequence WHERE name='connectors_connector'").fetchone()
        return row[0] if row else None

    def insert(self, user_id, count):
        with connection.cursor() as c:
            for _ in range(count):
                c.execute("INSERT INTO connectors_connector (kind, name, dataset, source_url, status, last_error,"
                          " created_by_id, created_at) VALUES ('csv', 'Синтетичне', 'other', '', 'connected', '',"
                          " %s, datetime('now'))", [user_id])

    def test_high_water_and_rows_survive(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create(username='synthetic-migration')
        self.migrate(BEFORE)
        self.insert(user.pk, 3)
        with connection.cursor() as c:
            c.execute('DELETE FROM connectors_connector WHERE id = (SELECT MAX(id) FROM connectors_connector)')
        high = self.seq()
        self.migrate(AFTER)
        self.assertEqual(self.seq(), high)
        with connection.cursor() as c:
            self.assertEqual(c.execute('SELECT mapping FROM connectors_connector ORDER BY id').fetchall(), [('{}',), ('{}',)])
        # A new connector continues after the high-water, never reusing the deleted id.
        from connectors.models import Connector
        self.assertEqual(Connector.objects.create(kind='csv', name='Нове', created_by=user).pk, high + 1)

    def test_emptied_table_keeps_its_high_water(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create(username='synthetic-migration')
        self.migrate(BEFORE)
        self.insert(user.pk, 2)
        with connection.cursor() as c:
            c.execute('DELETE FROM connectors_connector')
        high = self.seq()
        self.migrate(AFTER)
        self.assertEqual(self.seq(), high)

    def test_rollback_removes_the_column_and_keeps_the_high_water(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create(username='synthetic-migration')
        self.migrate(BEFORE)
        self.insert(user.pk, 2)
        self.migrate(AFTER)
        high = self.seq()
        self.migrate(BEFORE)
        with connection.cursor() as c:
            columns = [r[1] for r in c.execute('PRAGMA table_info(connectors_connector)').fetchall()]
        self.assertNotIn('mapping', columns)
        self.assertEqual(self.seq(), high)
