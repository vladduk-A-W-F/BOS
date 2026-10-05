"""Stored column mapping and connected sources in «Моніторинг». Synthetic data only."""
import json
from datetime import timedelta
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from boss_project.policy import Policy
from connectors import monitoring
from connectors.models import Connector, ConnectorSnapshot

CSV = 'Замовлення;Клієнт;Сума\nЗМ-1;ТОВ Ліс;12500\nЗМ-2;ФОП Коваль;сто\n'.encode('utf-8')
OWN = {'code': 'Замовлення', 'customer': 'Клієнт', 'amount': 'Сума'}


@override_settings(BOS_DATA_MODE='demo', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class MappingPersistTests(TestCase):
    def user(self, name, role):
        user = get_user_model().objects.create_user(username=name, password='synthetic-pass')
        Group.objects.get_or_create(name=role)[0].user_set.add(user)
        return user

    def setUp(self):
        self.ceo = self.user('synthetic-owner', 'ceo')
        self.client.force_login(self.ceo)

    def connect(self, **extra):
        preview = self.client.post('/api/connectors/preview/', {
            'kind': 'csv', 'file': SimpleUploadedFile('orders.csv', CSV, 'text/csv'), 'dataset': 'orders'}).json()
        return self.client.post('/api/connectors/create/', {
            'kind': 'csv', 'file': SimpleUploadedFile('orders.csv', CSV, 'text/csv'), 'name': 'Замовлення з Excel',
            'dataset': 'orders', 'expected_sha256': preview['sha256'], **extra})

    def legacy(self, dataset='orders', mapping=None, **fields):
        connector = Connector.objects.create(kind='csv', name='Старе джерело', dataset=dataset, mapping=mapping or {},
                                             last_sync_at=timezone.now(), created_by=self.ceo, **fields)
        ConnectorSnapshot.objects.create(connector=connector, columns=['Замовлення', 'Клієнт', 'Сума'],
                                         rows=[['ЗМ-1', 'ТОВ Ліс', '12500'], ['ЗМ-2', 'ФОП Коваль', 'сто']],
                                         row_count=2, sha256='0' * 64)
        return connector

    def test_create_stores_the_confirmed_mapping_and_reports_what_was_read(self):
        body = self.connect(mapping=json.dumps(OWN)).json()
        self.assertEqual(body['mapping'], OWN)
        self.assertEqual(body['mapped_summary'], {'accepted': 1, 'total': 2, 'rejected': 1})
        self.assertEqual(Connector.objects.get().mapping, OWN)

    def test_create_without_mapping_stays_unmapped_and_bad_mapping_creates_nothing(self):
        body = self.connect().json()
        self.assertEqual((body['mapping'], body['mapped_summary']), ({}, None))
        Connector.objects.all().delete()
        response = self.connect(mapping=json.dumps({'code': 'Замовлення'}))
        self.assertEqual(response.status_code, 422)
        self.assertIn('Клієнт', response.json()['error'])
        self.assertFalse(Connector.objects.exists())

    def test_set_mapping_on_a_legacy_source(self):
        connector = self.legacy()
        self.assertIsNone(self.client.get('/api/connectors/').json()['connectors'][0]['mapped_summary'])
        url = f'/api/connectors/{connector.pk}/mapping/'
        for bad in ('', '{', json.dumps({'code': 'Номер', 'customer': 'Клієнт'})):
            self.assertEqual(self.client.post(url, {'mapping': bad}).status_code, 422)
        self.assertEqual(Connector.objects.get().mapping, {})
        body = self.client.post(url, {'mapping': json.dumps(OWN)}).json()
        self.assertEqual(body['mapped_summary']['accepted'], 1)
        self.assertEqual(Connector.objects.get().mapping, OWN)

    def test_set_mapping_rights(self):
        connector = self.legacy()
        payments = self.legacy(dataset='payments')
        other = self.legacy(dataset='other')
        url = '/api/connectors/{}/mapping/'
        self.client.force_login(self.user('synthetic-observer', 'observer'))
        self.assertEqual(self.client.post(url.format(connector.pk), {'mapping': json.dumps(OWN)}).status_code, 403)
        self.client.force_login(self.user('synthetic-manager', 'manager'))
        # Payments are outside the manager's money scope: the source does not exist for them.
        self.assertEqual(self.client.post(url.format(payments.pk), {'mapping': '{}'}).status_code, 404)
        self.assertEqual(self.client.post(url.format(other.pk), {'mapping': '{}'}).status_code, 422)
        Connector.objects.filter(pk=connector.pk).update(status='disabled')
        self.assertEqual(self.client.post(url.format(connector.pk), {'mapping': json.dumps(OWN)}).status_code, 404)
        self.assertEqual(Connector.objects.get(pk=connector.pk).mapping, {})

    def test_mapping_that_no_longer_fits_is_reported_not_replaced(self):
        connector = self.legacy(mapping={**OWN, 'customer': 'Покупець'})
        summary = self.client.get('/api/connectors/').json()['connectors'][0]['mapped_summary']
        self.assertIn('немає колонки «Покупець»', summary['error'])
        self.assertEqual(Connector.objects.get(pk=connector.pk).mapping['customer'], 'Покупець')


@override_settings(BOS_DATA_MODE='demo')
class SourcesMonitoringTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='synthetic-owner')
        self.orders = Connector.objects.create(kind='csv', name='Замовлення з Excel', dataset='orders', mapping=OWN,
                                               last_sync_at=timezone.now(), created_by=self.owner)
        ConnectorSnapshot.objects.create(connector=self.orders, columns=['Замовлення', 'Клієнт', 'Сума'],
                                         rows=[['ЗМ-1', 'ТОВ Ліс', '12500'], ['ЗМ-2', 'ФОП Коваль', 'сто']],
                                         row_count=2, sha256='0' * 64)
        self.payments = Connector.objects.create(
            kind='google_sheets', name='Оплати', dataset='payments', source_url='https://docs.google.com/x',
            mapping={'reference': 'Док', 'counterparty': 'Платник', 'amount': 'Сума'},
            last_sync_at=timezone.now() - timedelta(hours=2), created_by=self.owner)
        ConnectorSnapshot.objects.create(connector=self.payments, columns=['Док', 'Платник', 'Сума'],
                                         rows=[['PD-1', 'ТОВ Ліс', '100,50']], row_count=1, sha256='1' * 64)
        self.unmapped = Connector.objects.create(kind='csv', name='Залишки', dataset='stock',
                                                 last_sync_at=timezone.now(), created_by=self.owner)
        ConnectorSnapshot.objects.create(connector=self.unmapped, columns=['Товар'], rows=[['Кутник']],
                                         row_count=1, sha256='2' * 64)

    def policy(self, role):
        user = get_user_model().objects.create_user(username='synthetic-' + role)
        Group.objects.get_or_create(name=role)[0].user_set.add(user)
        return Policy(SimpleNamespace(user=user, session={}))

    def test_ceo_sees_rows_freshness_and_what_needs_attention(self):
        items = {s['name']: s for s in monitoring.build(self.policy('ceo'))}
        orders = items['Замовлення з Excel']
        self.assertEqual((orders['freshness'], orders['accepted'], orders['total'], orders['rejected']), ('file', 1, 2, 1))
        self.assertEqual(orders['freshness_label'], 'Дані із завантаженого файлу')
        self.assertEqual(orders['table']['columns'], ['Номер замовлення', 'Клієнт', 'Сума', 'Валюта'])
        self.assertEqual(orders['table']['rows'][0]['cells'], ['ЗМ-1', 'ТОВ Ліс', '12500.00', 'UAH'])
        self.assertEqual(items['Оплати']['freshness'], 'stale')
        self.assertEqual(items['Залишки']['problem'], 'Колонки не зіставлено з полями BoS')
        titles = [a['title'] for a in monitoring.attention(list(items.values()))]
        self.assertIn('Джерело «Замовлення з Excel»: 1 з 2 рядків не прочитано', titles)
        self.assertIn('Джерело «Оплати»: дані застаріли, оновіть джерело', titles)
        self.assertIn('Джерело «Залишки» не показується в моніторингу', titles)

    def test_manager_has_no_money_and_observer_only_freshness(self):
        manager = {s['name']: s for s in monitoring.build(self.policy('manager'))}
        self.assertNotIn('Оплати', manager)
        self.assertEqual(manager['Замовлення з Excel']['table']['columns'], ['Номер замовлення', 'Клієнт'])
        observer = monitoring.build(self.policy('observer'))
        self.assertNotIn('Оплати', [s['name'] for s in observer])
        for item in observer:
            self.assertFalse({'table', 'accepted', 'rejected_examples', 'problem'} & set(item))

    def test_error_and_disabled_sources(self):
        Connector.objects.filter(pk=self.orders.pk).update(status='error', last_error='Таблиця недоступна')
        Connector.objects.filter(pk=self.unmapped.pk).update(status='disabled')
        items = {s['name']: s for s in monitoring.build(self.policy('ceo'))}
        self.assertNotIn('Залишки', items)
        self.assertEqual(items['Замовлення з Excel']['freshness_label'], 'Помилка читання: Таблиця недоступна')
        danger = [a for a in monitoring.attention(list(items.values())) if a['level'] == 'danger']
        self.assertEqual([a['ref'] for a in danger], [{'kind': 'connector', 'id': self.orders.pk}])
