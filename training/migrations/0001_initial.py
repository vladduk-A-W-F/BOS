import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='TrainingSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('public_id', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('role', models.CharField(max_length=20)),
                ('installation_id', models.CharField(max_length=64)),
                ('fixture_id', models.CharField(max_length=64)),
                ('fixture_hash', models.CharField(max_length=64)),
                ('case_id', models.CharField(max_length=40)),
                ('status', models.CharField(default='in_progress', max_length=32)),
                ('current_step', models.CharField(blank=True, max_length=60)),
                ('progress', models.JSONField(default=dict)),
                ('tour_state', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={'constraints': [
                models.UniqueConstraint(fields=('user', 'role', 'installation_id', 'fixture_id', 'fixture_hash', 'case_id'), name='bos3_lesson_identity'),
                models.CheckConstraint(condition=models.Q(role__in=['ceo', 'manager', 'observer']), name='bos3_lesson_role'),
                models.CheckConstraint(condition=models.Q(status__in=['in_progress', 'paused', 'completed', 'needs_recheck']), name='bos3_lesson_status'),
            ]},
        ),
    ]
