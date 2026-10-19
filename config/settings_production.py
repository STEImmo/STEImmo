"""Fail-closed settings for the GHCR deployment; local settings stay independent."""

import ipaddress
import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403
from .settings import DATABASES, env_bool, env_list


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value or "change_me" in value.lower() or "change-this" in value.lower():
        raise ImproperlyConfigured(f"Produktionswert {name} fehlt oder ist ein Platzhalter.")
    return value


if env_bool("DJANGO_DEBUG") or env_bool("DJANGO_CREATE_DEVELOPMENT_EMPLOYEE"):
    raise ImproperlyConfigured("DEBUG und Entwicklungskonten sind in Produktion unzulässig.")
if env_bool("DJANGO_BOOTSTRAP_ON_START"):
    raise ImproperlyConfigured("Produktionsmigrationen müssen als Release-Schritt laufen.")

DEBUG = False
SECRET_KEY = required("DJANGO_SECRET_KEY")
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY muss ein unabhängiges starkes Geheimnis sein.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS or any("*" in host for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS muss konkrete Hostnamen enthalten.")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
if not CSRF_TRUSTED_ORIGINS or any(
    not origin.startswith("https://") or "*" in origin for origin in CSRF_TRUSTED_ORIGINS
):
    raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS benötigt konkrete HTTPS-Ursprünge.")

for key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST"):
    required(key)
if len(required("POSTGRES_PASSWORD")) < 16:
    raise ImproperlyConfigured("POSTGRES_PASSWORD muss mindestens 16 Zeichen enthalten.")
# Copy the base configuration so importing this module cannot mutate local settings.
DATABASES = {"default": DATABASES["default"].copy()}

LOGIN_THROTTLE_TRUSTED_PROXY_IPS = tuple(env_list("DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS"))
if not LOGIN_THROTTLE_TRUSTED_PROXY_IPS:
    raise ImproperlyConfigured("Die geprüfte Proxy-Quelladresse muss konfiguriert sein.")
for proxy_ip in LOGIN_THROTTLE_TRUSTED_PROXY_IPS:
    try:
        address = ipaddress.ip_address(proxy_ip)
    except ValueError as error:
        raise ImproperlyConfigured("Proxy-Vertrauen erlaubt nur einzelne IP-Adressen.") from error
    if address.is_unspecified or address.is_multicast:
        raise ImproperlyConfigured("Ungültige Proxy-Quelladresse.")

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = required("DJANGO_EMAIL_HOST")
DEFAULT_FROM_EMAIL = required("DJANGO_DEFAULT_FROM_EMAIL")
EMAIL_TIMEOUT = 15
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0"))
if SECURE_HSTS_SECONDS < 0:
    raise ImproperlyConfigured("DJANGO_SECURE_HSTS_SECONDS darf nicht negativ sein.")
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
# ADR-0018: opt in to HSTS after the first successful public HTTPS check.
SILENCED_SYSTEM_CHECKS = ["security.W004"] if SECURE_HSTS_SECONDS == 0 else []
