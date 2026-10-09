import json

from django.core.management.base import BaseCommand

from connectors.periodic import run_once


class Command(BaseCommand):
    help = ('Одноразово оновлює опубліковані Google Таблиці, прочитані понад 15 хвилин тому. Лише читання джерел. '
            'Запущений сервер BoS робить це сам щохвилини; команда — для ручної перевірки.')

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(run_once(), ensure_ascii=False))
