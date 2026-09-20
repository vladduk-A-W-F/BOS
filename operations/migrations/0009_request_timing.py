"""Keep historical creation times unknown; timestamp only newly created rows."""
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [('operations', '0008_procurement_currency_default')]
    operations = [
        migrations.AddField(model_name=name, name='created_at',
                            field=models.DateTimeField(null=True, editable=False))
        for name in ('procurementrequest', 'supplierquote')
    ] + [
        migrations.AlterField(model_name=name, name='created_at',
                              field=models.DateTimeField(null=True, default=timezone.now, editable=False))
        for name in ('procurementrequest', 'supplierquote')
    ]
