from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0006_private_documents")]
    operations = [migrations.AddField(
        model_name="actionproposal", name="dependency_context",
        field=models.JSONField(blank=True, null=True),
    )]
