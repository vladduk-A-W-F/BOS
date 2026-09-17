"""A07: local row bounds; signed movements and zero reserves retained."""
from django.db import migrations, models
from boss_project.migration_operations import PreserveSequenceAddConstraint


class Migration(migrations.Migration):
    dependencies = [('erp', '0001_initial')]

    operations = [
        PreserveSequenceAddConstraint(
            model_name='purchase',
            constraint=models.CheckConstraint(
                condition=models.Q(quantity__gt=0, received__gte=0, received__lte=models.F('quantity')),
                name='erp_purchase_quantity',
            ),
        ),
        PreserveSequenceAddConstraint(
            model_name='purchase',
            constraint=models.CheckConstraint(
                condition=models.Q(price__gte=0, extras__gte=0), name='erp_purchase_costs',
            ),
        ),
        PreserveSequenceAddConstraint(
            model_name='production',
            constraint=models.CheckConstraint(
                condition=models.Q(quantity__gt=0, produced__gte=0, produced__lte=models.F('quantity')),
                name='erp_production_quantity',
            ),
        ),
        PreserveSequenceAddConstraint(
            model_name='production',
            constraint=models.CheckConstraint(
                condition=models.Q(planned_cost__gte=0, actual_cost__gte=0), name='erp_production_costs',
            ),
        ),
        PreserveSequenceAddConstraint(
            model_name='salesline',
            constraint=models.CheckConstraint(
                condition=models.Q(invoiced__gte=0, invoiced__lte=models.F('shipped')),
                name='erp_line_invoiced',
            ),
        ),
        PreserveSequenceAddConstraint(
            model_name='salesline',
            constraint=models.CheckConstraint(condition=models.Q(price__gte=0), name='erp_line_price'),
        ),
        PreserveSequenceAddConstraint(
            model_name='lot',
            constraint=models.CheckConstraint(condition=models.Q(unit_cost__gte=0), name='erp_lot_unit_cost'),
        ),
        PreserveSequenceAddConstraint(
            model_name='movement',
            constraint=models.CheckConstraint(condition=models.Q(cost__gte=0), name='erp_movement_cost'),
        ),
        *[
            PreserveSequenceAddConstraint(
                model_name=model_name,
                constraint=models.CheckConstraint(
                    condition=models.Q(currency__in=('EUR', 'USD', 'UAH')),
                    name='erp_' + model_name + '_currency',
                ),
            )
            for model_name in ('item', 'lot', 'salesorder', 'production', 'purchase')
        ],
    ]
