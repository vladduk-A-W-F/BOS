import uuid

from django.conf import settings
from django.db import models


class TrainingSession(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    role = models.CharField(max_length=20)
    installation_id = models.CharField(max_length=64)
    fixture_id = models.CharField(max_length=64)
    fixture_hash = models.CharField(max_length=64)
    case_id = models.CharField(max_length=40)
    status = models.CharField(max_length=32, default='in_progress')
    current_step = models.CharField(max_length=60, blank=True)
    progress = models.JSONField(default=dict)
    tour_state = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'role', 'installation_id', 'fixture_id', 'fixture_hash', 'case_id'],
                name='bos3_lesson_identity'),
            models.CheckConstraint(condition=models.Q(role__in=['ceo', 'manager', 'observer']),
                                   name='bos3_lesson_role'),
            models.CheckConstraint(condition=models.Q(status__in=[
                'in_progress', 'paused', 'completed', 'needs_recheck']), name='bos3_lesson_status'),
        ]
