import json

from django.core.management.base import BaseCommand, CommandError

from erp.bos4_demo import VERSION, VERSIONS, seed_bos4_demo


class Command(BaseCommand):
    help = 'Створює демо-компанію BoS 4 у порожній демобазі, без заміни даних і без створення паролів.'

    def add_arguments(self, parser):
        parser.add_argument('--dataset-version', default=VERSION, choices=VERSIONS,
                            help='1.1 додає каталог і велике замовлення з AdventureWorks; лише для нової бази.')

    def handle(self, *args, **options):
        try:
            receipt = seed_bos4_demo(options['dataset_version'])
        except CommandError:
            raise
        except (ValueError, TypeError) as exc:
            raise CommandError('Демо-компанію не створено; транзакцію скасовано: ' + str(exc)) from exc
        self.stdout.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
