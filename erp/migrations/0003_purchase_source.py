"""B01: retain historical purchases without inventing source approvals."""
from django.db import migrations, models
import django.db.models.deletion
from boss_project.migration_operations import PreserveSequenceAddField


def refuse_approved_source_loss(apps, schema_editor):
    Purchase = apps.get_model('erp', 'Purchase')
    populated = Purchase.objects.using(schema_editor.connection.alias).filter(
        models.Q(quote_id__isnull=False) | models.Q(approval_snapshot__isnull=False))
    if populated.exists():
        raise RuntimeError('Відкат B01 зупинено: він видалив би збережені джерела або погодження закупівель.')


class Migration(migrations.Migration):
    dependencies = [('erp','0002_row_boundaries'),('operations','0006_private_documents')]

    operations = [
        PreserveSequenceAddField(model_name='purchase',name='quote',
            field=models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.PROTECT,
                                    to='operations.supplierquote')),
        PreserveSequenceAddField(model_name='purchase',name='approval_snapshot',
            field=models.JSONField(blank=True,null=True)),
        # Reverse operations run from the end: refuse before either field is
        # removed. Historical all-null rows remain reversibly migratable.
        migrations.RunPython(migrations.RunPython.noop, reverse_code=refuse_approved_source_loss),
    ]
