import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from connectors import sources
from connectors.models import Connector, ConnectorSnapshot

CSV = 'Замовлення;Клієнт;Сума\nЗМ-1;ТОВ Ліс;12500\nЗМ-2;ФОП Коваль;3400\n'.encode('utf-8')
SHEET = 'https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit#gid=42'


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class SourcesTests(TestCase):
    def test_csv_semicolon_and_cp1251(self):
        table = sources.parse_csv(CSV.decode().encode('cp1251'))
        self.assertEqual(table['columns'], ['Замовлення', 'Клієнт', 'Сума'])
        self.assertEqual(table['row_count'], 2)
        self.assertEqual(table['rows'][1], ['ЗМ-2', 'ФОП Коваль', '3400'])

    def test_xlsx(self):
        from openpyxl import Workbook
        book = Workbook()
        sheet = book.active
        sheet.append(['Артикул', 'Залишок'])
        sheet.append(['BK-001', 120])
        buffer = io.BytesIO()
        book.save(buffer)
        table = sources.parse_upload('stock.xlsx', buffer.getvalue())
        self.assertEqual(table['rows'], [['BK-001', '120']])

    def test_limits_and_bad_input(self):
        with self.assertRaises(sources.SourceError):
            sources.parse_upload('data.pdf', CSV)
        with self.assertRaises(sources.SourceError):
            sources.parse_csv(b'')
        with self.assertRaises(sources.SourceError):
            sources.parse_csv(b'a;a\n1;2\n')
        with mock.patch.object(sources, 'MAX_ROWS', 1), self.assertRaises(sources.SourceError):
            sources.parse_csv(CSV)

    def test_sheet_url_is_restricted_to_google(self):
        self.assertEqual(sources.sheet_export_url(SHEET),
                         'https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789'
                         '/export?format=csv&gid=42')
        for bad in ('http://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789',
                    'https://evil.example/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789',
                    'https://docs.google.com.evil.example/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789',
                    'https://docs.google.com:8443/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789',
                    'file:///etc/passwd', ''):
            with self.subTest(bad=bad), self.assertRaises(sources.SourceError):
                sources.sheet_export_url(bad)

    def test_unpublished_sheet_html_is_refused(self):
        opener = mock.Mock()
        opener.open.return_value = FakeResponse(b'<!DOCTYPE html><html>login</html>')
        with self.assertRaises(sources.SourceError):
            sources.fetch_sheet(SHEET, opener=opener)


@override_settings(BOS_DATA_MODE='demo', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ConnectorApiTests(TestCase):
    def user(self, name, role):
        user = get_user_model().objects.create_user(username=name, password='synthetic-pass')
        Group.objects.get_or_create(name=role)[0].user_set.add(user)
        return user

    def setUp(self):
        self.ceo = self.user('owner', 'ceo')
        self.observer = self.user('viewer', 'observer')
        self.client.force_login(self.ceo)

    def upload(self, path, **extra):
        data = {'kind': 'csv', 'file': SimpleUploadedFile('orders.csv', CSV, 'text/csv'), **extra}
        return self.client.post(path, data)

    def test_catalog_lists_available_and_planned_services(self):
        body = self.client.get('/api/connectors/').json()
        states = {item['kind']: item['state'] for item in body['catalog']}
        self.assertEqual(states['csv'], 'available')
        self.assertEqual(states['google_sheets'], 'available')
        self.assertEqual(states['binotel'], 'planned')
        self.assertEqual(body['connectors'], [])

    def test_preview_writes_nothing_then_confirm_creates_snapshot(self):
        preview = self.upload('/api/connectors/preview/')
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(preview.json()['row_count'], 2)
        self.assertFalse(Connector.objects.exists())
        created = self.upload('/api/connectors/create/', name='Замовлення з Excel', dataset='orders',
                              expected_sha256=preview.json()['sha256'])
        self.assertEqual(created.status_code, 201, created.content)
        connector = Connector.objects.get()
        self.assertEqual((connector.kind, connector.dataset, connector.created_by), ('csv', 'orders', self.ceo))
        rows = self.client.get(f'/api/connectors/{connector.pk}/rows/').json()
        self.assertEqual(rows['rows'][0], ['ЗМ-1', 'ТОВ Ліс', '12500'])

    def test_stale_preview_is_refused(self):
        response = self.upload('/api/connectors/create/', name='X', dataset='orders', expected_sha256='0' * 64)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(Connector.objects.exists())

    def test_observer_reads_but_cannot_connect(self):
        self.client.force_login(self.observer)
        self.assertEqual(self.client.get('/api/connectors/').status_code, 200)
        self.assertEqual(self.upload('/api/connectors/preview/').status_code, 403)

    def test_payment_rows_follow_money_scope(self):
        payments = Connector.objects.create(kind='csv', name='Оплати', dataset='payments', created_by=self.ceo)
        orders = Connector.objects.create(kind='csv', name='Замовлення', dataset='orders', created_by=self.ceo)
        for connector in (payments, orders):
            ConnectorSnapshot.objects.create(connector=connector, columns=['Сума'], rows=[['12500']],
                                             row_count=1, sha256='0' * 64)
        names = lambda: [c['name'] for c in self.client.get('/api/connectors/').json()['connectors']]
        self.assertEqual(sorted(names()), ['Замовлення', 'Оплати'])
        self.assertEqual(self.client.get(f'/api/connectors/{payments.pk}/rows/').status_code, 200)
        self.client.force_login(self.user('manager', 'manager'))
        self.assertEqual(names(), ['Замовлення'])
        self.assertEqual(self.client.get(f'/api/connectors/{payments.pk}/rows/').status_code, 404)
        self.assertEqual(self.client.post(f'/api/connectors/{payments.pk}/disable/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/connectors/{orders.pk}/rows/').status_code, 200)
        self.client.force_login(self.observer)
        self.assertEqual(names(), ['Замовлення'])
        for connector in (payments, orders):
            self.assertEqual(self.client.get(f'/api/connectors/{connector.pk}/rows/').status_code, 403)
        payments.refresh_from_db()
        self.assertEqual(payments.status, 'connected')

    def test_anonymous_is_refused(self):
        self.client.logout()
        self.assertIn(self.client.get('/api/connectors/').status_code, (401, 403))

    def test_planned_service_cannot_be_connected(self):
        response = self.client.post('/api/connectors/preview/', {'kind': 'binotel'})
        self.assertEqual(response.status_code, 422)

    def test_google_sheet_sync_updates_snapshot_and_records_errors(self):
        with mock.patch.object(sources, 'fetch_sheet', return_value=sources.parse_csv(CSV)):
            preview = self.client.post('/api/connectors/preview/', {'kind': 'google_sheets', 'url': SHEET}).json()
            created = self.client.post('/api/connectors/create/', {
                'kind': 'google_sheets', 'url': SHEET, 'name': 'Оплати', 'dataset': 'payments',
                'expected_sha256': preview['sha256']})
        self.assertEqual(created.status_code, 201, created.content)
        connector = Connector.objects.get()
        changed = sources.parse_csv(CSV + 'ЗМ-3;ТОВ Бук;900\n'.encode())
        with mock.patch.object(sources, 'fetch_sheet', return_value=changed):
            synced = self.client.post(f'/api/connectors/{connector.pk}/sync/').json()
        self.assertEqual(synced['row_count'], 3)
        self.assertEqual(ConnectorSnapshot.objects.filter(connector=connector).count(), 2)
        with mock.patch.object(sources, 'fetch_sheet', side_effect=sources.SourceError('закрито')):
            failed = self.client.post(f'/api/connectors/{connector.pk}/sync/')
        self.assertEqual(failed.status_code, 422)
        connector.refresh_from_db()
        self.assertEqual((connector.status, connector.last_error), ('error', 'закрито'))

    def test_disable_hides_connector(self):
        preview = self.upload('/api/connectors/preview/').json()
        self.upload('/api/connectors/create/', name='X', dataset='other', expected_sha256=preview['sha256'])
        connector = Connector.objects.get()
        self.assertEqual(self.client.post(f'/api/connectors/{connector.pk}/disable/').status_code, 200)
        self.assertEqual(self.client.get('/api/connectors/').json()['connectors'], [])
        self.assertEqual(self.client.get(f'/api/connectors/{connector.pk}/rows/').status_code, 404)


@override_settings(BOS_DATA_MODE='demo', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StaleSheetSyncTests(TestCase):
    """Periodic reading on use: only Google Sheets older than 15 minutes, no scheduler."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        self.ceo = get_user_model().objects.create_user(username='owner', password='synthetic-pass')
        Group.objects.get_or_create(name='ceo')[0].user_set.add(self.ceo)
        now = timezone.now()
        make = lambda name, kind, age: Connector.objects.create(
            kind=kind, name=name, dataset='orders', created_by=self.ceo,
            source_url=SHEET if kind == 'google_sheets' else '',
            last_sync_at=None if age is None else now - timedelta(minutes=age))
        self.stale = make('Стара таблиця', 'google_sheets', 40)
        self.never = make('Ще не читали', 'google_sheets', None)
        self.fresh = make('Свіжа таблиця', 'google_sheets', 5)
        self.file = make('Файл', 'csv', 400)
        self.client.force_login(self.ceo)

    def test_only_stale_sheets_are_read_again(self):
        with mock.patch.object(sources, 'fetch_sheet', return_value=sources.parse_csv(CSV)) as fetch:
            body = self.client.post('/api/connectors/sync-stale/').json()
        self.assertEqual(sorted(x['name'] for x in body['synced']), ['Стара таблиця', 'Ще не читали'])
        self.assertEqual(body['failed'], [])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(ConnectorSnapshot.objects.filter(connector=self.stale).count(), 1)
        self.assertFalse(ConnectorSnapshot.objects.filter(connector__in=[self.fresh, self.file]).exists())
        with mock.patch.object(sources, 'fetch_sheet', return_value=sources.parse_csv(CSV)) as fetch:
            self.assertEqual(self.client.post('/api/connectors/sync-stale/').json()['synced'], [])
        fetch.assert_not_called()

    def test_failure_is_reported_and_marked(self):
        with mock.patch.object(sources, 'fetch_sheet', side_effect=sources.SourceError('закрито')):
            body = self.client.post('/api/connectors/sync-stale/').json()
        self.assertEqual(len(body['failed']), 2)
        self.stale.refresh_from_db()
        self.assertEqual((self.stale.status, self.stale.last_error), ('error', 'закрито'))

    def test_observer_cannot_trigger_and_command_reads_the_same_set(self):
        viewer = get_user_model().objects.create_user(username='viewer', password='synthetic-pass')
        Group.objects.get_or_create(name='observer')[0].user_set.add(viewer)
        self.client.force_login(viewer)
        self.assertEqual(self.client.post('/api/connectors/sync-stale/').status_code, 403)
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        with mock.patch.object(sources, 'fetch_sheet', return_value=sources.parse_csv(CSV)):
            call_command('sync_connectors', stdout=out)
        import json
        self.assertEqual(sorted(json.loads(out.getvalue())['synced']), sorted([self.stale.pk, self.never.pk]))

    def test_failing_sheets_do_not_starve_healthy_ones(self):
        broken = [Connector.objects.create(kind='google_sheets', name='Зламана %d' % i, dataset='orders',
                                           created_by=self.ceo, source_url=SHEET, status='error',
                                           last_error='закрито', last_sync_at=None) for i in range(12)]
        with mock.patch.object(sources, 'fetch_sheet', return_value=sources.parse_csv(CSV)) as fetch:
            body = self.client.post('/api/connectors/sync-stale/').json()
        self.assertEqual(sorted(x['name'] for x in body['synced']), ['Стара таблиця', 'Ще не читали'])
        self.assertEqual(fetch.call_count, 2)
        # Sources in error recover only through the manual sync, then rejoin the automatic reading.
        self.assertTrue(all(Connector.objects.get(pk=c.pk).status == 'error' for c in broken))
        with mock.patch.object(sources, 'fetch_sheet', return_value=sources.parse_csv(CSV)):
            self.assertEqual(self.client.post(f'/api/connectors/{broken[11].pk}/sync/').status_code, 200)
        self.assertEqual(Connector.objects.get(pk=broken[11].pk).status, 'connected')

    def test_older_read_cannot_overwrite_a_newer_one(self):
        from connectors.views import sync_connector
        old_table = sources.parse_csv(CSV)
        new_table = sources.parse_csv(CSV.replace(b'12500', b'99999'))
        calls = []
        def fetch(url):
            calls.append(url)
            if len(calls) == 1:
                # A is still reading the old content when B starts later and applies the new one.
                sync_connector(Connector.objects.get(pk=self.stale.pk))
                return old_table
            return new_table
        with mock.patch.object(sources, 'fetch_sheet', side_effect=fetch):
            sync_connector(Connector.objects.get(pk=self.stale.pk))
        snapshots = ConnectorSnapshot.objects.filter(connector=self.stale)
        self.assertEqual(snapshots.count(), 1)
        self.assertEqual(snapshots.first().sha256, new_table['sha256'])
        calls_b = []
        def fetch_b(url):
            if not calls_b:
                calls_b.append(url)
                with mock.patch.object(sources, 'fetch_sheet', return_value=new_table):
                    sync_connector(Connector.objects.get(pk=self.never.pk))
                raise sources.SourceError('тимчасово недоступна')
            return new_table
        with mock.patch.object(sources, 'fetch_sheet', side_effect=fetch_b), self.assertRaises(sources.SourceError):
            sync_connector(Connector.objects.get(pk=self.never.pk))
        self.assertEqual(Connector.objects.get(pk=self.never.pk).status, 'connected')

    def test_disable_during_fetch_wins_and_nothing_is_stored(self):
        def fetch(url):
            Connector.objects.filter(pk=self.stale.pk).update(status='disabled')
            return sources.parse_csv(CSV)
        from connectors.views import sync_connector
        with mock.patch.object(sources, 'fetch_sheet', side_effect=fetch):
            result = sync_connector(Connector.objects.get(pk=self.stale.pk))
        self.assertEqual(result.status, 'disabled')
        self.assertFalse(ConnectorSnapshot.objects.filter(connector=self.stale).exists())
        def failing(url):
            Connector.objects.filter(pk=self.never.pk).update(status='disabled')
            raise sources.SourceError('закрито')
        with mock.patch.object(sources, 'fetch_sheet', side_effect=failing), self.assertRaises(sources.SourceError):
            sync_connector(Connector.objects.get(pk=self.never.pk))
        self.assertEqual(Connector.objects.get(pk=self.never.pk).status, 'disabled')

    def test_parallel_sync_does_not_duplicate_the_same_snapshot(self):
        table = sources.parse_csv(CSV)
        def fetch(url):
            # Another request stored the same content while this one was reading.
            ConnectorSnapshot.objects.create(connector=self.stale, columns=table['columns'], rows=table['rows'],
                                             row_count=table['row_count'], sha256=table['sha256'])
            return table
        from connectors.views import sync_connector
        with mock.patch.object(sources, 'fetch_sheet', side_effect=fetch):
            sync_connector(Connector.objects.get(pk=self.stale.pk))
        self.assertEqual(ConnectorSnapshot.objects.filter(connector=self.stale).count(), 1)
