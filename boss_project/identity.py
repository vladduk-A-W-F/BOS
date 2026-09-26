"""Server-derived identity. Job titles and client role strings grant no rights."""
from dataclasses import dataclass
from django.conf import settings
from django.contrib.auth import get_user_model

ROLES = ('ceo', 'manager', 'observer')


class IdentityDenied(PermissionError):
    def __init__(self, message, status=403):
        self.status = status
        super().__init__(message)


@dataclass(frozen=True)
class Actor:
    user_id: int
    employee_id: int | None
    role: str

    def as_dict(self):
        return {'user_id': self.user_id, 'employee_id': self.employee_id, 'role': self.role}


def actor_for_user(user):
    if not getattr(user, 'is_authenticated', False) or not getattr(user, 'pk', None):
        raise IdentityDenied('Увійдіть до BoS.', 401)
    # Always re-read revocation and groups, including on an old proposal replay.
    user = get_user_model().objects.filter(pk=user.pk, is_active=True).first()
    if user is None:
        raise IdentityDenied('Сесію завершено. Увійдіть знову.', 401)
    from training.access import enforce_training_identity
    try:
        enforce_training_identity(user)
    except PermissionError as exc:
        raise IdentityDenied(str(exc)) from exc
    roles = list(user.groups.filter(name__in=ROLES).values_list('name', flat=True))
    if len(roles) != 1:
        raise IdentityDenied('Для облікового запису потрібна одна призначена роль BoS.')
    from employees.models import Employee
    employee = Employee.objects.filter(user_id=user.pk).only('pk', 'archived_at').first()
    if employee is not None and employee.archived_at is not None:
        raise IdentityDenied('Доступ архівного працівника припинено.')
    return Actor(user.pk, employee.pk if employee else None, roles[0])


def actor(request):
    if request.session.get('bos_demo_identity') and settings.BOS_DATA_MODE != 'demo':
        raise IdentityDenied('Навчальна сесія не дає доступу до робочої бази.', 401)
    return actor_for_user(request.user)
