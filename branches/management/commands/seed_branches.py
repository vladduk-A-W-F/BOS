"""Сид оргструктуры.

Структура живёт ЗДЕСЬ, в данных, а не в вёрстке дашборда — фронт рендерит
любое дерево, которое ему пришло. Поменять состав филиалов для другой
организации = поменять таблицы ниже, компоненты трогать не нужно.

Названия узлов — заглушки по географии; реальные наименования подразделений
подставляются позже без изменения кода.

    python manage.py seed_branches          # создать/обновить
    python manage.py seed_branches --reset  # сначала снести всё
"""

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction

from branches.models import Branch

# (code, name, lat, lng, employee_count, status)
KYIV_DEPARTMENTS = [
    ('KY-01', 'Управління організації діяльності',   50.4501, 30.5234, 34, 'green'),
    ('KY-02', 'Фінансово-економічне управління',     50.4430, 30.5180, 28, 'green'),
    ('KY-03', 'Управління персоналу',                50.4560, 30.5290, 19, 'yellow'),
    ('KY-04', 'Управління інформаційних технологій', 50.4390, 30.5410, 41, 'green'),
    ('KY-05', 'Управління правового забезпечення',   50.4620, 30.5150, 16, 'green'),
    ('KY-06', 'Управління матеріального забезпечення', 50.4340, 30.5330, 23, 'red'),
]

UKRAINE_REGIONS = [
    ('UA-05', 'Вінницьке управління',        49.2331, 28.4682, 47, 'green'),
    ('UA-07', 'Волинське управління',        50.7472, 25.3254, 31, 'green'),
    ('UA-12', 'Дніпропетровське управління', 48.4647, 35.0462, 88, 'green'),
    ('UA-14', 'Донецьке управління',         48.0159, 37.8028, 24, 'red'),
    ('UA-18', 'Житомирське управління',      50.2547, 28.6587, 38, 'yellow'),
    ('UA-21', 'Закарпатське управління',     48.6208, 22.2879, 33, 'green'),
    ('UA-23', 'Запорізьке управління',       47.8388, 35.1396, 52, 'yellow'),
    ('UA-26', 'Івано-Франківське управління', 48.9226, 24.7111, 36, 'green'),
    ('UA-32', 'Київське обласне управління', 50.4501, 30.5234, 64, 'green'),
    ('UA-35', 'Кіровоградське управління',   48.5079, 32.2623, 29, 'green'),
    ('UA-44', 'Луганське управління',        48.5740, 39.3078, 18, 'red'),
    ('UA-46', 'Львівське управління',        49.8397, 24.0297, 79, 'green'),
    ('UA-48', 'Миколаївське управління',     46.9750, 31.9946, 35, 'yellow'),
    ('UA-51', 'Одеське управління',          46.4825, 30.7233, 83, 'green'),
    ('UA-53', 'Полтавське управління',       49.5883, 34.5514, 42, 'green'),
    ('UA-56', 'Рівненське управління',       50.6199, 26.2516, 30, 'green'),
    ('UA-59', 'Сумське управління',          50.9077, 34.7981, 27, 'yellow'),
    ('UA-61', 'Тернопільське управління',    49.5535, 25.5948, 26, 'green'),
    ('UA-63', 'Харківське управління',       49.9935, 36.2304, 76, 'yellow'),
    ('UA-65', 'Херсонське управління',       46.6354, 32.6169, 21, 'red'),
    ('UA-68', 'Хмельницьке управління',      49.4229, 26.9871, 32, 'green'),
]

FOREIGN_BRANCHES = [
    ('FR-PL', 'Представництво у Польщі',         52.2297, 21.0122, 22, 'green'),
    ('FR-DE', 'Представництво у Німеччині',      52.5200, 13.4050, 26, 'green'),
    ('FR-CZ', 'Представництво у Чехії',          50.0755, 14.4378, 15, 'green'),
    ('FR-SK', 'Представництво у Словаччині',     48.1486, 17.1077, 11, 'yellow'),
    ('FR-HU', 'Представництво в Угорщині',       47.4979, 19.0402, 12, 'green'),
    ('FR-RO', 'Представництво у Румунії',        44.4268, 26.1025, 14, 'green'),
    ('FR-MD', 'Представництво у Молдові',        47.0105, 28.8638,  9, 'yellow'),
    ('FR-IT', 'Представництво в Італії',         41.9028, 12.4964, 19, 'green'),
    ('FR-ES', 'Представництво в Іспанії',        40.4168, -3.7038, 17, 'green'),
    ('FR-PT', 'Представництво у Португалії',     38.7223, -9.1393, 10, 'green'),
    ('FR-FR', 'Представництво у Франції',        48.8566,  2.3522, 21, 'yellow'),
    ('FR-GB', 'Представництво у Великій Британії', 51.5074, -0.1278, 24, 'green'),
    ('FR-NL', 'Представництво у Нідерландах',    52.3676,  4.9041, 13, 'green'),
    ('FR-SE', 'Представництво у Швеції',         59.3293, 18.0686,  8, 'green'),
    ('FR-CA', 'Представництво у Канаді',         45.4215, -75.6972, 16, 'green'),
    ('FR-US', 'Представництво у США',            38.9072, -77.0369, 28, 'red'),
]


class Command(BaseCommand):
    help = 'Заповнює структуру філій демо-даними (заглушки назв).'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='видалити наявні філії перед сідом')

    @transaction.atomic
    def handle(self, *args, **options):
        if getattr(settings, 'BOS_DATA_MODE', 'working') != 'demo':
            raise CommandError('Демо-структуру можна створювати лише в демонстраційному режимі.')
        from finance.models import Salary, Transaction
        if Salary.objects.exists() or Transaction.objects.exists():
            raise CommandError('Структуру з фінансовою історією не можна перезаповнювати демо-даними.')
        if options['reset']:
            deleted, _ = Branch.objects.all().delete()
            self.stdout.write(f'Видалено записів: {deleted}')

        def upsert(code, name, type_, parent=None, lat=None, lng=None,
                   count=0, status='green'):
            obj, _ = Branch.objects.update_or_create(
                code=code,
                defaults=dict(name=name, type=type_, parent=parent, lat=lat,
                              lng=lng, employee_count=count, status=status),
            )
            return obj

        # ── Корни дерева ──
        hq = upsert('HQ', 'Центральний офіс', 'headquarters',
                    lat=50.4501, lng=30.5234, count=0, status='green')
        foreign_group = upsert('FOREIGN', 'Іноземні філії', 'foreign',
                               count=0, status='green')
        upsert('MOBILE', 'Мобільний офіс', 'mobile',
               lat=49.0, lng=32.0, count=7, status='green')

        # ── Группы под центральным офисом ──
        # Узлы-группы намеренно без координат: это рубрики дерева, а не
        # физические офисы — своя точка на карте у них дублировала бы детей.
        kyiv = upsert('KYIV', 'Київ', 'department', parent=hq,
                      count=0, status='green')
        ukraine = upsert('UKRAINE', 'Україна', 'regional', parent=hq,
                         count=0, status='green')

        for code, name, lat, lng, count, status in KYIV_DEPARTMENTS:
            upsert(code, name, 'department', kyiv, lat, lng, count, status)
        for code, name, lat, lng, count, status in UKRAINE_REGIONS:
            upsert(code, name, 'regional', ukraine, lat, lng, count, status)
        for code, name, lat, lng, count, status in FOREIGN_BRANCHES:
            upsert(code, name, 'foreign', foreign_group, lat, lng, count, status)

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Вузлів у структурі: {Branch.objects.count()}'
        ))
