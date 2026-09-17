from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [('operations', '0002_actionproposal_user')]

    operations = [migrations.CreateModel(
        name='LoginAttempt',
        fields=[
            ('key', models.CharField(max_length=64, primary_key=True, serialize=False)),
            ('attempts', models.PositiveIntegerField(default=0)),
            ('expires_at', models.DateTimeField()),
            ('latest_ticket', models.UUIDField(default=uuid.uuid4)),
        ],
    )]
