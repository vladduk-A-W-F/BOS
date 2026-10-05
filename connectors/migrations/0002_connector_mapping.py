from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('connectors', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='connector',
            name='mapping',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
