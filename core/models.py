from django.db import models


class CallbackThrottle(models.Model):
    """Short-lived abuse counter; never stores callback details or plain IP addresses."""

    client_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
