"""A05 shared financial commands; intended destination: finance/commands.py.

No data repair and no payment creation here: Salary.mark_paid remains the A02
payment command. Model.clean may call validate_* without calling full_clean
recursively. All command decisions use a fresh row after a real write lock.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID
import hashlib
import json
import re

from django.core.exceptions import ValidationError
from django.db import models, router, transaction, IntegrityError, OperationalError


SALARY_FIELDS = (
    'employee', 'amount', 'currency', 'period_year', 'period_month',
    'payment_date', 'status', 'notes', 'transaction',
)
SALARY_CORE = (
    'employee', 'amount', 'currency', 'period_year', 'period_month',
    'payment_date', 'status', 'transaction',
)
TRANSACTION_FIELDS = (
    'direction', 'amount', 'currency', 'date', 'description', 'category',
    'counterparty', 'contract', 'branch',
)
TRANSACTION_CORE = (
    'direction', 'amount', 'currency', 'date', 'category',
    'counterparty', 'contract', 'branch',
)
CURRENCIES = ('EUR', 'USD', 'UAH')


class FinancialIntentConflict(ValidationError):
    """Explicit retry/conflicting-intent result shared by all adapters."""


def intent_key(value, *, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', value):
        raise ValidationError({'operation_id': 'Потрібен ключ операції: 1–128 латинських літер, цифр або символів _ . : -.'})
    return value


def _intent_spec(model, candidate, actor, operation_id):
    token = intent_key(operation_id)
    if token is None:
        return None
    fields = SALARY_FIELDS if model._meta.model_name == 'salary' else TRANSACTION_FIELDS
    values = {}
    for name in fields:
        field = model._meta.get_field(name)
        value = _value(candidate, name)
        value = (field.target_field if field.is_relation else field).to_python(value)
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ValidationError({name: 'Потрібна скінченна сума.'})
            value = format(value.normalize(), 'f')
        values[field.attname] = _json_value(value)
    identity = [model._meta.label_lower, getattr(actor, 'pk', None), token]
    digest = lambda obj: hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return digest(identity), digest(values)


def _intent_result(receipt, model, payload_hash, using):
    if receipt.payload_hash != payload_hash:
        raise FinancialIntentConflict('Ключ уже використано для інших даних. Для нового наміру створіть новий ключ.')
    result_id = getattr(receipt, model._meta.model_name + '_id')
    if result_id is None:
        raise FinancialIntentConflict('Операція ще не завершена. Повторіть запит із тим самим ключем.')
    # Read the present record; never restore an old status, amount or archive flag.
    return model._base_manager.using(using).get(pk=result_id)


def replay_create(model, changes, *, actor, operation_id):
    """Read-only native form replay, before duplicate-period form validation."""
    from .models import FinancialIntent
    allowed = SALARY_FIELDS if model._meta.model_name == 'salary' else TRANSACTION_FIELDS
    candidate = model()
    for name, value in _normalized_changes(model, None, changes, allowed).items():
        setattr(candidate, model._meta.get_field(name).attname, value)
    key, payload_hash = _intent_spec(model, candidate, actor, intent_key(operation_id, required=True))
    using = router.db_for_write(model)
    receipt = FinancialIntent.objects.using(using).filter(pk=key).first()
    return _intent_result(receipt, model, payload_hash, using) if receipt else None


def _database(instance):
    return instance._state.db or router.db_for_write(type(instance), instance=instance)


def _persisted(instance):
    if instance.pk is None:
        return None
    return type(instance)._base_manager.using(_database(instance)).filter(pk=instance.pk).first()


def _value(instance, name):
    field = instance._meta.get_field(name)
    return getattr(instance, field.attname)


def _changed(instance, original, fields):
    return [name for name in fields if _value(instance, name) != _value(original, name)]


def _money_errors(instance):
    errors = {}
    try:
        amount = Decimal(str(instance.amount))
        if not amount.is_finite() or amount <= 0:
            errors['amount'] = 'Потрібна додатна скінченна сума.'
    except (InvalidOperation, ValueError, TypeError):
        errors['amount'] = 'Потрібна коректна десяткова сума.'
    if instance.currency not in CURRENCIES:
        errors['currency'] = 'Оберіть валюту EUR, USD або UAH.'
    return errors


def validate_salary(instance, original=None):
    """Validate a candidate against persisted history; do not call full_clean.

    Forms may pass only their modified instance. Commands pass the original
    they have just read under lock; callers must not pass an old ORM snapshot
    as authoritative original.
    """
    from .models import Transaction

    if original is None:
        original = _persisted(instance)
    errors = _money_errors(instance)
    if original is None or original.employee_id != instance.employee_id:
        from employees.models import Employee
        if Employee._base_manager.using(_database(instance)).filter(pk=instance.employee_id, archived_at__isnull=False).exists():
            errors['employee'] = 'Для нового нарахування потрібен активний працівник.'
    if not isinstance(instance.period_month, int) or not 1 <= instance.period_month <= 12:
        errors['period_month'] = 'Місяць має бути від 1 до 12.'
    if not isinstance(instance.period_year, int) or not 1 <= instance.period_year <= 9999:
        errors['period_year'] = 'Потрібен коректний календарний рік.'

    if original is not None and original.status == 'paid':
        for name in _changed(instance, original, SALARY_CORE):
            errors[name] = 'Проведену виплату змінювати не можна; її історію збережено.'
        expense = None
        if original.transaction_id is not None:
            expense = Transaction._base_manager.using(_database(instance)).filter(
                pk=original.transaction_id,
            ).first()
        if expense is None or (
            expense.direction != 'out' or expense.category != 'salary'
            or expense.amount != original.amount or expense.currency != original.currency
            or expense.date != original.payment_date
        ):
            errors['__all__'] = 'Історія виплати неузгоджена. Потрібна звірка; записи не змінено.'
    else:
        if original is not None and original.transaction_id is not None:
            errors['__all__'] = 'Стан і джерело нарахування неузгоджені. Потрібна звірка; зв’язок збережено.'
        if instance.status == 'paid':
            errors['status'] = 'Виплату виконуйте дією «Виплатити», яка створює пов’язану витрату.'
        if instance.transaction_id is not None:
            errors['transaction'] = 'Джерело виплати задає лише команда виплати.'
        if instance.payment_date is not None:
            errors['payment_date'] = 'Дата виплати задається під час проведення виплати.'
        if original is not None and getattr(original, 'archived_at', None) is not None:
            if _changed(instance, original, SALARY_FIELDS):
                errors['__all__'] = 'Архівне непроведене нарахування змінювати не можна.'
    if errors:
        raise ValidationError(errors)


def validate_transaction(instance, original=None):
    """Protect an actual salary source, not category/amount/date guesses."""
    from .models import Salary,StatementLine

    if original is None:
        original = _persisted(instance)
    errors = _money_errors(instance)
    if original is not None:
        from .models import StatementLine
        if StatementLine._base_manager.using(_database(instance)).filter(transaction_id=original.pk).exists():
            for name in _changed(instance,original,TRANSACTION_FIELDS):
                errors[name]='Первинний грошовий запис виписки є незмінним.'
        linked = Salary._base_manager.using(_database(instance)).filter(
            transaction_id=original.pk,
        ).exists()
        if linked:
            for name in _changed(instance, original, TRANSACTION_CORE):
                errors[name] = 'Пов’язану із зарплатою витрату змінювати не можна; джерело збережено.'
        if getattr(original, 'archived_at', None) is not None:
            if _changed(instance, original, TRANSACTION_FIELDS):
                errors['__all__'] = 'Архівну транзакцію змінювати не можна.'
    if errors:
        raise ValidationError(errors)


def _normalized_changes(model, instance, changes, allowed):
    """Normalize relation names without reading related objects from the DB."""
    if changes is None:
        if instance is None:
            return {}
        # A ModelForm's complete edited instance is a payload, not an original.
        return {name: _value(instance, name) for name in allowed}
    aliases = {}
    for name in allowed:
        field = model._meta.get_field(name)
        aliases[name] = name
        aliases[field.attname] = name
    result = {}
    for key, value in dict(changes).items():
        name = aliases.get(key)
        if name is None:
            raise ValidationError({'__all__': f'Поле «{key}» не можна змінювати цією командою.'})
        field = model._meta.get_field(name)
        if field.is_relation and isinstance(value, models.Model):
            if not isinstance(value, field.remote_field.model) or value.pk is None:
                raise ValidationError({name: 'Оберіть збережений запис належного довідника.'})
            value = value.pk
        if name in result and result[name] != value:
            raise ValidationError({name: 'Надано суперечливі значення одного поля.'})
        result[name] = value
    return result


def _clone(original):
    candidate = type(original)(**{
        field.attname: getattr(original, field.attname)
        for field in original._meta.concrete_fields
    })
    candidate._state.adding = False
    candidate._state.db = original._state.db
    return candidate


def _json_value(value):
    if isinstance(value, Decimal):
        return format(value, 'f')
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _audit(candidate, original, changed, actor, using):
    if not changed:
        return
    from operations.models import AuditEvent

    def snapshot(row):
        if row is None:
            return {}
        return {
            row._meta.get_field(name).attname: _json_value(_value(row, name))
            for name in changed
        }

    AuditEvent.objects.using(using).create(
        action=f'{candidate._meta.model_name}.{"create" if original is None else "update"}',
        payload={
            'entity': candidate._meta.label_lower,
            'id': _json_value(candidate.pk),
            'before': snapshot(original),
            'after': snapshot(candidate),
            'actor_id': _json_value(getattr(actor, 'pk', None)),
        },
    )


def _reflect(candidate, instance):
    """Admin keeps the supplied object's identity for save_related/logging."""
    if instance is None:
        return candidate
    for field in candidate._meta.concrete_fields:
        setattr(instance, field.attname, getattr(candidate, field.attname))
    instance._state.db = candidate._state.db
    instance._state.adding = candidate._state.adding
    instance._state.fields_cache.clear()
    return instance


def _save(model, validator, allowed, lock_field, instance, changes, actor, operation_id):
    if instance is not None and not isinstance(instance, model):
        raise ValidationError('Команда отримала запис іншого типу.')
    if instance is not None and instance.pk is not None and instance._state.adding:
        raise ValidationError('Не можна задавати ID нового фінансового запису вручну.')
    wanted = _normalized_changes(model, instance, changes, allowed)
    from boss_project.data_rules import field_values
    try:
        field_values(model, {model._meta.get_field(name).attname:value for name,value in wanted.items()})
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    using = _database(instance) if instance is not None else router.db_for_write(model)
    pk = instance.pk if instance is not None else None

    proposed = model()
    for name, value in wanted.items():
        setattr(proposed, model._meta.get_field(name).attname, value)
    spec = _intent_spec(model, proposed, actor, operation_id) if pk is None else None

    with transaction.atomic(using=using):
        intent = None
        if spec is not None:
            from .models import FinancialIntent
            key, payload_hash = spec
            intent, created = FinancialIntent.objects.using(using).get_or_create(
                key=key, defaults={'payload_hash': payload_hash})
            if not created:
                return _reflect(_intent_result(intent, model, payload_hash, using), instance)
        original = None
        if pk is not None:
            # First SQL in this command's atomic block: a real write lock on
            # PostgreSQL AND SQLite, before reading money or reverse links.
            rows = model._base_manager.using(using).filter(pk=pk).update(
                **{lock_field: models.F(lock_field)},
            )
            if not rows:
                raise ValidationError('Фінансовий запис не знайдено; зміни не виконано.')
            original = model._base_manager.using(using).get(pk=pk)
            candidate = _clone(original)
        else:
            candidate = model()
            candidate._state.db = using

        for name, value in wanted.items():
            setattr(candidate, model._meta.get_field(name).attname, value)

        if model._meta.model_name == 'salary' and (original is None or original.employee_id != candidate.employee_id):
            from employees.models import Employee
            # Serialize new accruals with employee archive on both databases,
            # including PostgreSQL where an unrelated Salary insert is no lock.
            Employee._base_manager.using(using).filter(pk=candidate.employee_id).update(full_name=models.F('full_name'))

        # Runs normal field/choice/FK/unique validation. Model.clean may call
        # validator again; validator itself never calls full_clean.
        candidate.full_clean()
        validator(candidate, original=original)
        changed = list(allowed) if original is None else _changed(candidate, original, allowed)
        if original is None:
            candidate.save(using=using, force_insert=True)
        elif changed:
            candidate.save(using=using, update_fields=changed)
        _audit(candidate, original, changed, actor, using)
        if intent is not None:
            source = model._meta.model_name
            setattr(intent, source + '_id', candidate.pk)
            intent.save(using=using, update_fields=[source])

    # Reflect only after the atomic block successfully exits, not on rollback.
    return _reflect(candidate, instance)


def save_salary(instance=None, changes=None, actor=None, operation_id=None):
    from .models import Salary
    try:
        return _save(Salary, validate_salary, SALARY_FIELDS, 'status', instance, changes, actor, operation_id)
    except (IntegrityError, OperationalError) as exc:
        if operation_id is None:
            raise
        raise FinancialIntentConflict('Конфлікт запису. Повторіть той самий намір після оновлення даних.') from exc


def save_transaction(instance=None, changes=None, actor=None, operation_id=None):
    from .models import Transaction
    try:
        return _save(Transaction, validate_transaction, TRANSACTION_FIELDS, 'direction', instance, changes, actor, operation_id)
    except (IntegrityError, OperationalError) as exc:
        if operation_id is None:
            raise
        raise FinancialIntentConflict('Конфлікт запису. Повторіть той самий намір після оновлення даних.') from exc
