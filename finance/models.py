from decimal import Decimal
from datetime import date

from django.db import models, transaction
from django.db.models import Q, Sum, Value, UniqueConstraint
from django.db.models.functions import Coalesce
from boss_project.archive import ArchiveModel


class CounterpartyManager(models.Manager):
    """Суммы по транзакциям одним запросом (аннотация) — без этого N+1 и падение
    CounterpartySerializer на объекте без total_debit/total_credit."""

    def with_totals(self):
        return self.get_queryset().annotate(
            total_debit=Coalesce(
                Sum('transactions__amount', filter=Q(transactions__direction='in')),
                Value(0, output_field=models.DecimalField()),
            ),
            total_credit=Coalesce(
                Sum('transactions__amount', filter=Q(transactions__direction='out')),
                Value(0, output_field=models.DecimalField()),
            ),
        )


class Counterparty(models.Model):
    """Контрагент — юр/физ лицо. Клиент, поставщик, коммуналка, etc."""
    TYPE_CHOICES = [
        ('supplier', 'Постачальник'),
        ('customer', 'Клієнт'),
        ('service',  'Послуги'),
        ('utility',  'Комунальні'),
        ('other',    'Інше'),
    ]
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='other')
    edrpou = models.CharField(max_length=20, blank=True, help_text='ЄДРПОУ / ІПН')
    phone = models.CharField(max_length=50, blank=True)
    email = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CounterpartyManager()

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Contract(models.Model):
    STATUS_CHOICES = [
        ('active', 'Активний'),
        ('closed', 'Закритий'),
        ('draft',  'Чернетка'),
    ]
    CATEGORY_CHOICES = [
        ('services', 'Послуги'),
        ('goods',    'Товари'),
        ('utility',  'Комунальні'),
        ('rent',     'Оренда'),
        ('supply',   'Закупівля'),
        ('other',    'Інше'),
    ]
    number = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    counterparty = models.ForeignKey(Counterparty, on_delete=models.CASCADE, related_name='contracts')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='UAH')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.number} — {self.name}'


class Transaction(ArchiveModel):
    DIRECTION_CHOICES = [
        ('in',  'Дохід'),
        ('out', 'Витрата'),
    ]
    CATEGORY_CHOICES = [
        ('salary',   'Зарплата'),
        ('supplier', 'Постачальник'),
        ('customer', 'Клієнт'),
        ('utility',  'Комунальні'),
        ('rent',     'Оренда'),
        ('tax',      'Податки'),
        ('other',    'Інше'),
    ]
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='UAH')
    date = models.DateField(db_index=True)
    description = models.CharField(max_length=300)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    # Опциональная связь — платёж может быть без контрагента (например, налог)
    counterparty = models.ForeignKey(Counterparty, null=True, blank=True, on_delete=models.PROTECT, related_name='transactions')
    contract = models.ForeignKey(Contract, null=True, blank=True, on_delete=models.PROTECT, related_name='transactions')

    # Branch assignment — nullable for backward compatibility with existing data
    branch = models.ForeignKey(
        'branches.Branch', null=True, blank=True,
        on_delete=models.PROTECT, related_name='transactions',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        constraints = [
            models.CheckConstraint(condition=models.Q(('amount__gt', 0), ('amount__lte', Decimal('999999999999.99'))), name='finance_transaction_amount'),
            models.CheckConstraint(condition=models.Q(('currency__in', ('EUR', 'USD', 'UAH'))), name='finance_transaction_currency'),
        ]

    def __str__(self):
        return f'{self.date} {self.direction} {self.amount} {self.currency}'

    def clean(self):
        from .commands import validate_transaction
        validate_transaction(self)


class Salary(ArchiveModel):
    """История начислений зарплат. Одно начисление на сотрудника в месяц (unique_together)."""
    STATUS_CHOICES = [
        ('pending',   'Очікує'),
        ('paid',      'Виплачено'),
        ('cancelled', 'Скасовано'),
    ]
    employee = models.ForeignKey('employees.Employee', on_delete=models.PROTECT, related_name='salaries')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='UAH')
    period_year = models.IntegerField()
    period_month = models.IntegerField()   # 1-12
    payment_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)
    # Опциональная связь с транзакцией — если зарплату уже оплатили через банк
    transaction = models.OneToOneField(Transaction, null=True, blank=True, on_delete=models.PROTECT, related_name='salary_record')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=['employee', 'period_year', 'period_month'],
                name='unique_salary_period',
            ),
        ]
        ordering = ['-period_year', '-period_month', 'employee__full_name']
        constraints += [
            models.CheckConstraint(condition=models.Q(('amount__gt', 0), ('amount__lte', Decimal('9999999999.99'))), name='finance_salary_amount'),
            models.CheckConstraint(condition=models.Q(('currency__in', ('EUR', 'USD', 'UAH'))), name='finance_salary_currency'),
        ]

    def clean(self):
        from .commands import validate_salary
        validate_salary(self)

    def mark_paid(self, payment_date=None):
        """Atomically record one expense, or return the same completed payment."""
        with transaction.atomic():
            # First SQL statement takes a row write-lock on PostgreSQL and a
            # database write-lock on SQLite, before reading payment state.
            if not Salary.objects.filter(pk=self.pk).update(status=models.F('status')):
                raise Salary.DoesNotExist('Нарахування не знайдено.')
            self.refresh_from_db()
            if self.status == 'paid':
                tx = self.transaction
                if (tx is None or tx.direction != 'out' or tx.category != 'salary'
                        or tx.amount != self.amount or tx.currency != self.currency
                        or tx.date != self.payment_date):
                    raise ValueError('Історія виплати неузгоджена. Потрібна звірка; записи не змінено.')
                return self, tx
            if self.archived_at is not None:
                raise ValueError('Архівне нарахування виплачувати не можна.')
            if self.status != 'pending' or self.transaction_id is not None:
                raise ValueError('Стан нарахування не дозволяє нову виплату. Потрібна звірка.')
            if self.currency not in ('EUR', 'USD', 'UAH') or self.amount <= 0:
                raise ValueError('Потрібна додатна сума та валюта EUR, USD або UAH.')
            if payment_date is None:
                pay_date = date.today()
            elif isinstance(payment_date, str):
                try:
                    pay_date = date.fromisoformat(payment_date)
                except ValueError as e:
                    raise ValueError(f"Невірний формат дати: {payment_date!r}. Очікується YYYY-MM-DD.") from e
            elif type(payment_date) is date:
                pay_date = payment_date
            else:
                raise ValueError('Потрібна дата у форматі YYYY-MM-DD.')
            tx = Transaction.objects.create(
                direction='out',
                amount=self.amount,
                currency=self.currency,
                date=pay_date,
                description=(
                    f'Зарплата {self.employee.full_name} '
                    f'{self.period_year}-{self.period_month:02d}'
                ),
                category='salary',
                branch=self.employee.branch,
            )
            self.status = 'paid'
            self.payment_date = pay_date
            self.transaction = tx
            self.save(update_fields=['status', 'payment_date', 'transaction'])
        return self, tx

    def __str__(self):
        return f'{self.employee.full_name} {self.period_year}-{self.period_month:02d}: {self.amount}'


class FinancialIntent(models.Model):
    """Durable creation receipt; committed together with its financial source."""
    key = models.CharField(max_length=64, primary_key=True, editable=False)
    payload_hash = models.CharField(max_length=64, editable=False)
    transaction = models.ForeignKey(Transaction, null=True, on_delete=models.PROTECT,
                                    related_name='creation_intents', editable=False)
    salary = models.ForeignKey(Salary, null=True, on_delete=models.PROTECT,
                               related_name='creation_intents', editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(
            condition=models.Q(transaction__isnull=True) | models.Q(salary__isnull=True),
            name='financial_intent_single_source',
        )]


# C03 immutable source ledgers. The authenticated confirmed writer owns mutation.
import uuid
from django.conf import settings

class StatementImport(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    document=models.ForeignKey('operations.Document',on_delete=models.PROTECT,related_name='statement_imports')
    source_sha256=models.CharField(max_length=64)
    format=models.CharField(max_length=40)
    parser_version=models.CharField(max_length=10)
    source_system=models.CharField(max_length=48)
    account_ref=models.CharField(max_length=120)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='statement_imports')
    source_snapshot=models.JSONField()
    first_commit_receipt=models.JSONField()
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['source_system','account_ref','source_sha256'],name='statement_import_source')]

class StatementLine(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    first_import=models.ForeignKey(StatementImport,on_delete=models.PROTECT,related_name='first_lines')
    source_system=models.CharField(max_length=48)
    account_ref=models.CharField(max_length=120)
    external_id=models.CharField(max_length=120)
    record=models.PositiveIntegerField()
    booking_date=models.DateField()
    direction=models.CharField(max_length=3)
    amount=models.DecimalField(max_digits=14,decimal_places=2)
    currency=models.CharField(max_length=3)
    counterparty_external_id=models.CharField(max_length=120,blank=True)
    invoice_reference=models.CharField(max_length=120,blank=True)
    purpose=models.TextField(max_length=2000,blank=True)
    semantic_sha256=models.CharField(max_length=64)
    transaction=models.OneToOneField(Transaction,null=True,blank=True,on_delete=models.PROTECT,related_name='statement_line')
    bound_at=models.DateTimeField(null=True,blank=True)
    bound_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT,related_name='bound_statement_lines')
    binding_snapshot=models.JSONField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['source_system','account_ref','external_id'],name='statement_line_identity'),
            models.CheckConstraint(condition=Q(amount__gt=0,amount__lte=Decimal('999999999999.99')),name='statement_line_amount'),
            models.CheckConstraint(condition=Q(currency__in=('EUR','UAH','USD')),name='statement_line_currency'),
            models.CheckConstraint(condition=Q(direction__in=('in','out')),name='statement_line_direction'),
            models.CheckConstraint(condition=(Q(transaction__isnull=True,bound_at__isnull=True,bound_by__isnull=True,binding_snapshot__isnull=True)|Q(transaction__isnull=False,bound_at__isnull=False,bound_by__isnull=False,binding_snapshot__isnull=False)),name='statement_binding_complete')]

class StatementAllocation(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    line=models.ForeignKey(StatementLine,on_delete=models.PROTECT,related_name='allocations')
    allocation_key=models.UUIDField(unique=True)
    invoice=models.ForeignKey('operations.Invoice',on_delete=models.PROTECT,related_name='statement_allocations')
    payment_event=models.OneToOneField('erp.Event',on_delete=models.PROTECT,related_name='statement_allocation')
    amount=models.DecimalField(max_digits=14,decimal_places=2)
    currency=models.CharField(max_length=3)
    mode=models.CharField(max_length=30)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='statement_allocations')
    intent_sha256=models.CharField(max_length=64)
    source_snapshot=models.JSONField()
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['line','allocation_key'],name='statement_allocation_identity'),
            models.CheckConstraint(condition=Q(amount__gt=0,amount__lte=Decimal('999999999999.99')),name='statement_allocation_amount'),
            models.CheckConstraint(condition=Q(currency__in=('EUR','UAH','USD')),name='statement_allocation_currency'),
            models.CheckConstraint(condition=Q(mode__in=('new_payment','existing_payment')),name='statement_allocation_mode')]
