from django.db import models
from django.db.models import Q


DEAL_STAGE_VALUES = ('qualification', 'supply', 'fulfillment', 'collection', 'won', 'lost')
ACTIVITY_KIND_VALUES = ('note', 'call', 'meeting', 'follow_up')
ACTIVITY_STATUS_VALUES = ('planned', 'done', 'cancelled')


class CRMDeal(models.Model):
    """A training-only customer handoff. It never records an ERP fact or payment."""

    STAGES = (
        ('qualification', 'Кваліфікація'),
        ('supply', 'Забезпечення'),
        ('fulfillment', 'Виконання'),
        ('collection', 'Контроль оплати'),
        ('won', 'Завершено'),
        ('lost', 'Не завершено'),
    )

    training_session = models.ForeignKey('training.TrainingSession', on_delete=models.PROTECT,
                                         related_name='crm_deals')
    case_id = models.CharField(max_length=40)
    stable_handoff_hash = models.CharField(max_length=64)
    counterparty = models.ForeignKey('finance.Counterparty', on_delete=models.PROTECT,
                                     related_name='crm_deals')
    sales_order = models.ForeignKey('erp.SalesOrder', null=True, blank=True,
                                    on_delete=models.PROTECT, related_name='crm_deals')
    invoice = models.ForeignKey('operations.Invoice', null=True, blank=True,
                                on_delete=models.PROTECT, related_name='crm_deals')
    owner = models.ForeignKey('employees.Employee', on_delete=models.PROTECT,
                              related_name='owned_crm_deals')
    title = models.CharField(max_length=200)
    next_action = models.CharField(max_length=500)
    stage = models.CharField(max_length=20, choices=STAGES)
    contact_name = models.CharField(max_length=120, blank=True)
    contact_role = models.CharField(max_length=120, blank=True)
    contact_email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['training_session', 'case_id', 'stable_handoff_hash'],
                                    name='crm_training_handoff_once'),
            models.CheckConstraint(condition=Q(stage__in=DEAL_STAGE_VALUES),
                                   name='crm_deal_stage'),
        ]
        ordering = ['-updated_at', '-id']


class CRMActivity(models.Model):
    KINDS = (
        ('note', 'Нотатка'),
        ('call', 'Дзвінок'),
        ('meeting', 'Зустріч'),
        ('follow_up', 'Наступний контакт'),
    )
    STATUSES = (
        ('planned', 'Заплановано'),
        ('done', 'Виконано'),
        ('cancelled', 'Скасовано'),
    )

    deal = models.ForeignKey(CRMDeal, on_delete=models.PROTECT, related_name='activities')
    owner = models.ForeignKey('employees.Employee', on_delete=models.PROTECT,
                              related_name='crm_activities')
    kind = models.CharField(max_length=20, choices=KINDS)
    summary = models.CharField(max_length=1000)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUSES, default='planned')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(kind__in=ACTIVITY_KIND_VALUES),
                                   name='crm_activity_kind'),
            models.CheckConstraint(condition=Q(status__in=ACTIVITY_STATUS_VALUES),
                                   name='crm_activity_status'),
        ]
        ordering = ['due_date', '-created_at', '-id']
