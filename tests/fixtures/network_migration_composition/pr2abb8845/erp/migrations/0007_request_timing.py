"""Do not fabricate historical purchase creation dates."""
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [('erp', '0006_network_operations'), ('operations', '0009_request_timing')]
    operations = [
        migrations.AddField(model_name='purchase', name='created_at',
                            field=models.DateTimeField(null=True, editable=False)),
        migrations.AlterField(model_name='purchase', name='created_at',
                              field=models.DateTimeField(null=True, default=timezone.now, editable=False)),
    ]
