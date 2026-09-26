"""A07: refuse invalid rows; never repair historical money values."""
from decimal import Decimal
from django.db import migrations, models
from boss_project.migration_operations import PreserveSequenceAddConstraint


class Migration(migrations.Migration):
    dependencies = [('finance', '0006_financialintent')]

    operations = [
        PreserveSequenceAddConstraint(
            model_name='transaction',
            constraint=models.CheckConstraint(
                condition=models.Q(amount__gt=0, amount__lte=Decimal('999999999999.99')),
                name='finance_transaction_amount',
            ),
        ),
        PreserveSequenceAddConstraint(
            model_name='transaction',
            constraint=models.CheckConstraint(
                condition=models.Q(currency__in=('EUR', 'USD', 'UAH')),
                name='finance_transaction_currency',
            ),
        ),
        PreserveSequenceAddConstraint(
            model_name='salary',
            constraint=models.CheckConstraint(
                condition=models.Q(amount__gt=0, amount__lte=Decimal('9999999999.99')),
                name='finance_salary_amount',
            ),
        ),
        PreserveSequenceAddConstraint(
            model_name='salary',
            constraint=models.CheckConstraint(
                condition=models.Q(currency__in=('EUR', 'USD', 'UAH')),
                name='finance_salary_currency',
            ),
        ),
    ]
