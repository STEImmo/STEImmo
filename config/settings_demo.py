"""Explicit demonstration profile: synthetic data and no outbound email (ADR-0019)."""

from .settings_deployment import *  # noqa: F403

DEMO_MODE = True
EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
EMAIL_HOST = ""
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""
DEFAULT_FROM_EMAIL = "noreply@steimmo.test"
