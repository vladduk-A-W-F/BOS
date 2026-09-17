from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, models, IntegrityError, OperationalError
from employees.models import Employee
from operations.models import AuditEvent


class Command(BaseCommand):
    help = 'Явно пов’язує наявні User та Employee без зміни історичних ID або ролі.'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int, required=True)
        parser.add_argument('--employee-id', type=int, required=True)

    def handle(self, *args, **options):
        user_id, employee_id = options['user_id'], options['employee_id']
        try:
            with transaction.atomic():
                users = get_user_model().objects.filter(pk=user_id)
                if not users.update(is_active=models.F('is_active')):
                    raise CommandError('Обліковий запис не знайдено.')
                employees = Employee.objects.filter(pk=employee_id)
                if not employees.update(full_name=models.F('full_name')):
                    raise CommandError('Працівника не знайдено; новий запис не створено.')
                employee = employees.get()
                if employee.user_id == user_id:
                    self.stdout.write('Цей зв’язок уже існує; ID та історію збережено.')
                    return
                if employee.user_id is not None or Employee.objects.filter(user_id=user_id).exists():
                    raise CommandError('Є інше зіставлення. Автоматична переприв’язка заборонена.')
                employees.update(user_id=user_id)
                AuditEvent.objects.create(action='identity.link', payload={
                    'employee_id': employee_id, 'user_id': user_id,
                    'before': {'user_id': None}, 'after': {'user_id': user_id}, 'source': 'management_command',
                })
        except (IntegrityError, OperationalError) as exc:
            raise CommandError('Зв’язок не створено через конфлікт; попередні дані збережено.') from exc
        self.stdout.write(self.style.SUCCESS('Обліковий запис пов’язано з працівником. Історичні ID збережено.'))
