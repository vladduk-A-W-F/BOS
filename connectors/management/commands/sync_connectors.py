import json

from django.core.management.base import BaseCommand

from connectors import sources
from connectors.models import Connector
from connectors.views import stale_sheets, sync_connector


class Command(BaseCommand):
    help = 'Оновлює опубліковані Google Таблиці, прочитані понад 15 хвилин тому. Лише читання джерел.'

    def handle(self, *args, **options):
        result = {'synced': [], 'failed': []}
        for connector in stale_sheets(Connector.objects.all()):
            try:
                sync_connector(connector)
                result['synced'].append(connector.pk)
            except sources.SourceError as exc:
                result['failed'].append({'id': connector.pk, 'error': str(exc)})
        self.stdout.write(json.dumps(result, ensure_ascii=False))
