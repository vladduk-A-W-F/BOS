import json

from django.core.management.base import BaseCommand, CommandError

from erp.network_demo import DATASETS, seed_network_demo


class Command(BaseCommand):
    help = 'Створює зв’язану навчальну мережу у порожній демобазі, без заміни даних і без створення паролів.'

    def add_arguments(self, parser):
        parser.add_argument('--dataset', choices=tuple(DATASETS), default='workday')

    def handle(self, *args, **options):
        try:
            receipt = seed_network_demo(options['dataset'])
        except CommandError:
            raise
        except (ValueError, TypeError) as exc:
            raise CommandError('Навчальну мережу не створено; транзакцію скасовано: ' + str(exc)) from exc
        self.stdout.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
