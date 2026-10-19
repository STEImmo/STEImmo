"""Fail-closed production profile with real SMTP and no demo accounts."""

from .settings_deployment import *  # noqa: F403
from .settings_deployment import required

DEMO_MODE = False
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = required("DJANGO_EMAIL_HOST")
DEFAULT_FROM_EMAIL = required("DJANGO_DEFAULT_FROM_EMAIL")
