"""Archive financial history without hiding rows from joins or totals."""
from django.core.exceptions import ValidationError
from django.db import models, router, transaction, IntegrityError, OperationalError
from django.utils import timezone


def archive_records(queryset, actor=None):
    using = queryset.db
    model = queryset.model
    with transaction.atomic(using=using):
        # Take a write lock before deciding which records are still active.
        queryset.update(archived_at=models.F('archived_at'))
        rows = list(queryset.filter(archived_at__isnull=True).order_by('pk').values_list('pk', flat=True))
        if not rows:
            return 0, {model._meta.label: 0}
        timestamp = timezone.now()
        model._base_manager.using(using).filter(pk__in=rows).update(archived_at=timestamp)
        from operations.models import AuditEvent
        AuditEvent.objects.using(using).bulk_create([
            AuditEvent(action=f'{model._meta.model_name}.archive', payload={
                'entity': model._meta.label_lower, 'id': pk,
                'before': {'archived_at': None},
                'after': {'archived_at': timestamp.isoformat()},
                'actor_id': getattr(actor, 'pk', None),
            }) for pk in rows
        ])
        return len(rows), {model._meta.label: len(rows)}


def restore_record(instance, actor=None):
    model = type(instance)
    using = instance._state.db or router.db_for_write(model, instance=instance)
    with transaction.atomic(using=using):
        rows = model._base_manager.using(using).filter(pk=instance.pk)
        if not rows.update(archived_at=models.F('archived_at')):
            raise ValidationError('Запис не знайдено. Новий ID замість історичного не створено.')
        original = rows.get()
        if original.archived_at is not None:
            rows.update(archived_at=None)
            from operations.models import AuditEvent
            AuditEvent.objects.using(using).create(
                action=f'{model._meta.model_name}.restore', payload={
                    'entity': model._meta.label_lower, 'id': original.pk,
                    'before': {'archived_at': original.archived_at.isoformat()},
                    'after': {'archived_at': None}, 'actor_id': getattr(actor, 'pk', None),
                },
            )
    instance.refresh_from_db(using=using)
    return instance


class ArchiveQuerySet(models.QuerySet):
    def delete(self, actor=None):
        return archive_records(self, actor=actor)


class ArchiveModel(models.Model):
    archived_at = models.DateTimeField(null=True, blank=True, editable=False, db_index=True)
    command_fields = ('archived_at',)
    # Neither manager excludes historical records. Salary source joins, unique
    # periods, finance reports and repeat payments must still see archived rows.
    objects = models.Manager.from_queryset(ArchiveQuerySet)()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # Stale forms must not overwrite fields owned by audited commands.
        update_fields = kwargs.get('update_fields')
        protected = {name for field in self._meta.concrete_fields
                     if field.name in self.command_fields
                     for name in (field.name, field.attname)}
        if update_fields is not None and protected.intersection(update_fields):
            raise ValidationError('Захищені поля змінюються лише відповідною командою зі збереженням історії.')
        if not self._state.adding:
            if update_fields is None:
                kwargs['update_fields'] = [field.name for field in self._meta.concrete_fields
                    if not field.primary_key and not field.generated and field.name not in protected
                    and field.attname in self.__dict__ and not getattr(field, 'auto_now_add', False)]
            result = super().save(*args, **kwargs)
            self.refresh_from_db(fields=self.command_fields, using=kwargs.get('using'))
            return result
        if self.archived_at is not None:
            raise ValidationError('Новий запис архівується окремою командою зі збереженням історії.')
        return super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False, actor=None):
        if self.pk is None:
            raise ValueError('Не можна архівувати незбережений запис.')
        using = using or self._state.db or router.db_for_write(type(self), instance=self)
        result = archive_records(type(self)._base_manager.using(using).filter(pk=self.pk), actor=actor)
        self.refresh_from_db(using=using)
        return result


class ArchiveViewSetMixin:
    def perform_destroy(self, instance):
        instance.delete(actor=self.request.user)

    def destroy(self, request, *args, **kwargs):
        from rest_framework.response import Response
        try:
            return super().destroy(request, *args, **kwargs)
        except (ValidationError, IntegrityError, OperationalError):
            return Response({'error': 'Запис не архівовано через конфлікт. Історію збережено; оновіть дані й повторіть дію.'}, status=409)
