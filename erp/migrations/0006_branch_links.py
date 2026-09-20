import django.db.models.deletion
from django.db import migrations, models
from erp.migration_operations_v1 import AssertCompositionEntry, SharedLocationBranch


class Migration(migrations.Migration):
    dependencies = [('erp', '0005_source_corrections'), ('branches', '0003_fill_short_names')]
    operations = [
        SharedLocationBranch(owner='0006_branch_links'),
        migrations.AddField(model_name='salesorder', name='branch', field=models.ForeignKey(
            to='branches.branch', null=True, blank=True, on_delete=django.db.models.deletion.PROTECT)),
    ]
    operations = [AssertCompositionEntry(
        owner='0006_branch_links', forward_operations=operations), *operations]
