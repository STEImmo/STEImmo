"""One PostgreSQL advisory key per application, shared by mutations and mail handoff."""

import hashlib
from contextlib import contextmanager

from django.db import connection


def _key(application_id):
    return int.from_bytes(
        hashlib.sha256(f"steimmo-application-mail:{application_id}".encode()).digest()[:8],
        signed=True,
    )


def lock_application_notifications(application_id):
    # Acquire before the application row lock, after the apartment lock (if any).
    # Mutations already run inside atomic(); PostgreSQL releases this at commit.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_key(application_id)])


@contextmanager
def application_notification_handoff(application_id):
    # A session lock retains stale-message protection across the short claim commit
    # and bounded SMTP call, without keeping a transaction or row lock open.
    key = _key(application_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", [key])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
