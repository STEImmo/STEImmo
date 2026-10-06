import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "wohnungsverwaltung.apps.WohnungsverwaltungConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "wohnungsverwaltung.upload_limits.MainApplicationUploadLimitMiddleware",
    "wohnungsverwaltung.export_limits.SignatureRequestLimitMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "steimmo"),
        "USER": os.environ.get("POSTGRES_USER", "steimmo"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "CHANGE_ME"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "de-de"
TIME_ZONE = os.environ.get("TZ", "Europe/Berlin")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
FILE_UPLOAD_PERMISSIONS = 0o600
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o700
HANDOVER_PHOTO_MAX_SIZE = int(os.environ.get("HANDOVER_PHOTO_MAX_SIZE", 8 * 1024 * 1024))
HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM = int(
    os.environ.get("HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM", 10)
)
MAIN_APPLICATION_PROOF_MAX_SIZE = int(
    os.environ.get("MAIN_APPLICATION_PROOF_MAX_SIZE", 8 * 1024 * 1024)
)
MAIN_APPLICATION_MAX_REQUEST_SIZE = int(
    os.environ.get("MAIN_APPLICATION_MAX_REQUEST_SIZE", 25 * 1024 * 1024)
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
LOGIN_ACCOUNT_FAILURE_LIMIT = int(os.environ.get("DJANGO_LOGIN_ACCOUNT_FAILURE_LIMIT", "3"))
LOGIN_ACCOUNT_LOCKOUT_SECONDS = int(os.environ.get("DJANGO_LOGIN_ACCOUNT_LOCKOUT_SECONDS", "900"))
LOGIN_IP_FAILURE_LIMIT = int(os.environ.get("DJANGO_LOGIN_IP_FAILURE_LIMIT", "10"))
LOGIN_IP_FAILURE_WINDOW_SECONDS = int(
    os.environ.get("DJANGO_LOGIN_IP_FAILURE_WINDOW_SECONDS", "900")
)
LOGIN_THROTTLE_TRUSTED_PROXY_IPS = tuple(env_list("DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS"))

EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend",
)
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "noreply@steimmo.local")
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("DJANGO_EMAIL_USE_TLS", default=True)
