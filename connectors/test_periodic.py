"""M3 §7: connected sources are read by the running server itself, without opening «Підключення».

Synthetic only: the published-sheet fetch is replaced by a local function; no network, no owner data.
"""
from datetime import timedelta
import sys
import threading
import time
import types
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone

from . import periodic, sources
from .models import Connector, ConnectorSnapshot

TABLE = {'columns': ['Номер', 'Сума'], 'rows': [['1', '10']], 'row_count': 1, 'sha256': 'b' * 64}


class PeriodicReadingTests(TransactionTestCase):
    def setUp(self):
        self.addCleanup(periodic.stop)
        self.user = get_user_model().objects.create_user(username='synthetic-owner', password='synthetic-pass')
        old = timezone.now() - timedelta(hours=1)
        self.due = self.source('Замовлення', 'connected', old)
        self.fresh = self.source('Свіжа', 'connected', timezone.now() - timedelta(minutes=5))
        self.broken = self.source('Зламана', 'error', old, error='Таблиця недоступна.')
        self.off = self.source('Вимкнена', 'disabled', old)
        self.file = self.source('Файл', 'connected', old, kind='csv')
        self.calls = []

    def source(self, name, status, last, kind='google_sheets', error=''):
        connector = Connector.objects.create(kind=kind, name=name, dataset='other', status=status, last_error=error,
            source_url='https://docs.google.com/spreadsheets/d/synthetic/edit' if kind == 'google_sheets' else '',
            created_by=self.user)
        Connector.objects.filter(pk=connector.pk).update(last_sync_at=last)
        ConnectorSnapshot.objects.create(connector=connector, columns=['A'], rows=[['old']], row_count=1, sha256='a' * 64)
        connector.refresh_from_db()
        return connector

    def fetch(self, url):
        self.calls.append(url)
        return TABLE

    def test_one_check_reads_only_due_healthy_sheets_through_the_same_sync(self):
        with mock.patch.object(sources, 'fetch_sheet', side_effect=self.fetch):
            result = periodic.run_once()
        self.assertEqual(result, {'synced': [self.due.pk], 'failed': []})
        self.assertEqual(len(self.calls), 1)
        self.due.refresh_from_db()
        self.assertEqual((self.due.status, self.due.snapshots.count()), ('connected', 2))
        self.assertGreater(self.due.last_sync_at, timezone.now() - timedelta(minutes=1))
        # Fresh, failed, disabled and uploaded sources are left exactly as they were.
        for connector in (self.fresh, self.broken, self.off, self.file):
            before = (connector.status, connector.last_error, connector.last_sync_at)
            connector.refresh_from_db()
            self.assertEqual((connector.status, connector.last_error, connector.last_sync_at), before)
            self.assertEqual(connector.snapshots.count(), 1)

    def test_a_failed_read_keeps_the_last_successful_time_and_is_not_retried(self):
        last = self.due.last_sync_at
        with mock.patch.object(sources, 'fetch_sheet', side_effect=sources.SourceError('Таблиця недоступна.')):
            result = periodic.run_once()
        self.assertEqual(result['failed'], [{'id': self.due.pk, 'error': 'Таблиця недоступна.'}])
        self.due.refresh_from_db()
        self.assertEqual((self.due.status, self.due.last_error, self.due.last_sync_at),
                         ('error', 'Таблиця недоступна.', last))
        with mock.patch.object(sources, 'fetch_sheet', side_effect=self.fetch):
            self.assertEqual(periodic.run_once(), {'synced': [], 'failed': []})
        self.assertEqual(self.calls, [])

    def test_a_disable_during_the_read_wins(self):
        def disable_then_fetch(url):
            Connector.objects.filter(pk=self.due.pk).update(status='disabled')
            return TABLE
        with mock.patch.object(sources, 'fetch_sheet', side_effect=disable_then_fetch):
            periodic.run_once()
        self.due.refresh_from_db()
        self.assertEqual((self.due.status, self.due.snapshots.count()), ('disabled', 1))

    def test_the_server_process_has_one_reader_that_keeps_reading_and_stops_with_it(self):
        failures = iter([RuntimeError('синтетичний збій циклу')])

        def flaky(now=None):
            for error in failures:
                raise error
            return original(now)
        original = periodic.run_once
        with mock.patch.object(sources, 'fetch_sheet', side_effect=self.fetch), \
                mock.patch.object(periodic, 'run_once', side_effect=flaky), \
                self.assertLogs('bos.connectors', 'ERROR'):
            reader = periodic.start(interval=0.02)
            self.assertIs(periodic.start(interval=0.02), reader)
            deadline = time.monotonic() + 10
            while reader.cycles < 3 and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertGreaterEqual(reader.cycles, 3)        # the failed first cycle did not end reading
            self.assertTrue(periodic.stop())
        self.assertFalse(reader.thread.is_alive())
        self.assertEqual(sum(t.name == 'bos-connectors' for t in threading.enumerate()), 0)
        self.due.refresh_from_db()
        self.assertEqual((self.due.status, self.due.snapshots.count()), ('connected', 2))
        self.assertEqual(len(self.calls), 1)                 # read once; due again only after 15 minutes
        self.assertIsNot(periodic.start(interval=60), reader)

    def test_the_supported_server_entry_starts_the_reader_and_stops_it_on_exit(self):
        from scripts import start_server
        seen = {}

        def run_application(application, **kwargs):
            seen['alive'] = periodic._reader is not None and periodic._reader.thread.is_alive()
            return 0
        fake = types.ModuleType('boss_project.server_wsgi')
        fake.application = object()
        with mock.patch.dict(sys.modules, {'boss_project.server_wsgi': fake}), \
                mock.patch.object(start_server.metadata, 'version', return_value='3.0.2'), \
                mock.patch.object(start_server, 'run_application', side_effect=run_application), \
                mock.patch.object(periodic, 'run_once', return_value={'synced': [], 'failed': []}):
            self.assertEqual(start_server.serve(0, 5), 0)
        self.assertTrue(seen['alive'])
        self.assertIsNone(periodic._reader)
        self.assertEqual(sum(t.name == 'bos-connectors' for t in threading.enumerate()), 0)
