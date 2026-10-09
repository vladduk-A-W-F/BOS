from django.conf import settings
from django.db import models


class Connector(models.Model):
    """A company service connected to BoS. Data is only read and stored as snapshots."""

    KINDS = (('csv', 'Excel / CSV'), ('google_sheets', 'Google Таблиці'), ('url', 'Таблиця за посиланням'))
    DATASETS = (('orders', 'Замовлення'), ('payments', 'Оплати'), ('stock', 'Залишки'),
                ('calls', 'Дзвінки'), ('other', 'Інше'))
    STATUSES = (('connected', 'Підключено'), ('error', 'Помилка'), ('disabled', 'Вимкнено'))

    kind = models.CharField(max_length=20, choices=KINDS)
    name = models.CharField(max_length=120)
    dataset = models.CharField(max_length=20, choices=DATASETS, default='other')
    source_url = models.URLField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=STATUSES, default='connected')
    last_error = models.CharField(max_length=300, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    # {field: source column}; empty for «Інше» and for sources connected before mapping existed.
    mapping = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name='connectors')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name', 'id']


class ConnectorSnapshot(models.Model):
    connector = models.ForeignKey(Connector, on_delete=models.CASCADE, related_name='snapshots')
    fetched_at = models.DateTimeField(auto_now_add=True)
    columns = models.JSONField()
    rows = models.JSONField()
    row_count = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)

    class Meta:
        ordering = ['-fetched_at', '-id']
