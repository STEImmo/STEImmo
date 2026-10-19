import json
import os
import subprocess
import sys

from django.test import SimpleTestCase


class ProductionSettingsTests(SimpleTestCase):
    def load_settings(self, **overrides):
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("DJANGO_", "POSTGRES_"))
        }
        environment.update(
            DJANGO_SETTINGS_MODULE="config.settings_production",
            DJANGO_SECRET_KEY="only-for-tests-a-long-and-distinct-secret-with-more-than-fifty-characters",
            DJANGO_ALLOWED_HOSTS="steimmo.example.test",
            DJANGO_CSRF_TRUSTED_ORIGINS="https://steimmo.example.test",
            DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS="172.20.0.1",
            POSTGRES_DB="steimmo",
            POSTGRES_USER="steimmo",
            POSTGRES_PASSWORD="test-only-database-password",
            POSTGRES_HOST="postgres",
            DJANGO_EMAIL_HOST="smtp.example.test",
            DJANGO_DEFAULT_FROM_EMAIL="noreply@example.test",
        )
        environment.update(overrides)
        return subprocess.run(
            [
                sys.executable,
                "-c",
                "import json; from django.conf import settings as s; "
                "print(json.dumps([s.DEBUG, s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, "
                "s.SECURE_SSL_REDIRECT, s.SECURE_HSTS_SECONDS, s.EMAIL_BACKEND]))",
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_production_enforces_https_and_secure_cookies(self):
        result = self.load_settings()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [False, True, True, True, 0, "django.core.mail.backends.smtp.EmailBackend"],
        )

    def test_unsafe_configuration_refuses_to_start(self):
        cases = [
            {"DJANGO_DEBUG": "1"},
            {"DJANGO_CREATE_DEVELOPMENT_EMPLOYEE": "1"},
            {"DJANGO_BOOTSTRAP_ON_START": "1"},
            {"DJANGO_SECRET_KEY": "CHANGE_ME"},
            {"DJANGO_SECRET_KEY": "x" * 60},
            {"POSTGRES_PASSWORD": "CHANGE_ME"},
            {"POSTGRES_PASSWORD": "short"},
            {"DJANGO_ALLOWED_HOSTS": "*"},
            {"DJANGO_CSRF_TRUSTED_ORIGINS": "http://steimmo.example.test"},
            {"DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS": ""},
            {"DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS": "172.20.0.0/16"},
            {"DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS": "0.0.0.0"},
            {"DJANGO_EMAIL_HOST": ""},
        ]
        for values in cases:
            with self.subTest(values=values):
                result = self.load_settings(**values)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ImproperlyConfigured", result.stderr)

    def test_hsts_can_be_enabled_after_https_verification(self):
        result = self.load_settings(DJANGO_SECURE_HSTS_SECONDS="3600")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[4], 3600)
