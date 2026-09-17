"""Reserve a password attempt before authentication, across DB connections."""
from datetime import timedelta
import hashlib
import math
import uuid

from django.db import models, transaction
from django.utils import timezone
from operations.models import LoginAttempt


def reserve(username, remote):
    key = hashlib.sha256((username + '\0' + remote).encode()).hexdigest()
    # Creation is outside the read/modify transaction: on SQLite the first
    # statement in that transaction must be a write, not a snapshot read.
    LoginAttempt.objects.get_or_create(key=key, defaults={'expires_at': timezone.now()})
    with transaction.atomic():
        rows = LoginAttempt.objects.filter(pk=key)
        rows.update(attempts=models.F('attempts'))
        bucket = rows.get()
        now = timezone.now()
        if bucket.expires_at <= now:
            bucket.attempts = 0
            bucket.expires_at = now + timedelta(seconds=60)
        if bucket.attempts >= 5:
            return None, max(1, min(60, math.ceil((bucket.expires_at - now).total_seconds())))
        bucket.attempts += 1
        bucket.latest_ticket = uuid.uuid4()
        bucket.save(update_fields=['attempts', 'expires_at', 'latest_ticket'])
        return (key, bucket.latest_ticket), None


def succeeded(ticket):
    key, token = ticket
    # A successful request must not erase failures that arrived after it.
    LoginAttempt.objects.filter(pk=key, latest_ticket=token).update(attempts=0)
