import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('erp', '0005_source_corrections'), ('branches', '0003_fill_short_names')]
    operations = [
        migrations.AddField(model_name=model, name='branch', field=models.ForeignKey(
            to='branches.branch', null=True, blank=True, on_delete=django.db.models.deletion.PROTECT))
        for model in ('location', 'salesorder')
    ]
