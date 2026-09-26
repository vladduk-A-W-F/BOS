"""A07: zero-price invoices remain permitted; no data updates."""
from decimal import Decimal
from django.db import migrations, models
from boss_project.migration_operations import PreserveSequenceAddConstraint


class Migration(migrations.Migration):
    dependencies = [('operations', '0004_alter_document_options_document_access_level')]

    operations = [
        PreserveSequenceAddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=models.Q(amount__gte=0, amount__lte=Decimal('999999999999.99')),
                name='bos_invoice_amount_range',
            ),
        ),
        PreserveSequenceAddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=models.Q(paid__gte=0, paid__lte=models.F('amount')),
                name='bos_invoice_paid_range',
            ),
        ),
        PreserveSequenceAddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(
                condition=models.Q(currency__in=('EUR', 'USD', 'UAH')),
                name='bos_invoice_currency',
            ),
        ),
    ]
