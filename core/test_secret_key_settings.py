import json
import os
import secrets
import subprocess
import sys

from django.test import SimpleTestCase


class SecretKeySettingsTests(SimpleTestCase):
    def load_settings(self, *, debug=None, secret_key=None):
        environment = {
            name: value for name, value in os.environ.items() if not name.startswith("DJANGO_")
        }
        environment["DJANGO_SETTINGS_MODULE"] = "config.settings"
        if debug is not None:
            environment["DJANGO_DEBUG"] = debug
        if secret_key is not None:
            environment["DJANGO_SECRET_KEY"] = secret_key
        return subprocess.run(
            [
                sys.executable,
                "-c",
                "import json; from django.conf import settings; "
                "print(json.dumps([settings.DEBUG, settings.SECRET_KEY]))",
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_non_debug_start_rejects_missing_or_unsafe_secret_without_disclosing_it(self):
        unsafe_keys = (
            None,
            "",
            " " * 60,
            "dev-only-insecure-key-change-me",
            "change-this-for-local-development",
            "ci-only-secret",
            "short-private-value",
            "a" * 60,
            "abcd" * 20,
            "django-insecure-" + secrets.token_urlsafe(48),
            "CHANGE_ME-" + secrets.token_urlsafe(48),
            "change-this-" + secrets.token_urlsafe(48),
            " " * 50 + "short-private-value",
        )
        for debug in (None, "0", "false"):
            for secret_key in unsafe_keys:
                with self.subTest(debug=debug, secret_key=secret_key):
                    result = self.load_settings(debug=debug, secret_key=secret_key)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("ImproperlyConfigured", result.stderr)
                    self.assertIn("DJANGO_SECRET_KEY", result.stderr)
                    self.assertEqual(result.stdout, "")
                    if secret_key and secret_key.strip():
                        self.assertNotIn(secret_key, result.stderr)

    def test_non_debug_start_accepts_secure_key_unchanged(self):
        secret_key = secrets.token_urlsafe(48)
        result = self.load_settings(debug="0", secret_key=secret_key)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [False, secret_key])

    def test_secret_key_minimum_length_and_character_variety(self):
        # Deliberately synthetic boundary values, never deployment credentials.
        for secret_key, accepted in (("abcde" * 10, True), ("abcde" * 9 + "abcd", False)):
            with self.subTest(accepted=accepted):
                result = self.load_settings(debug="0", secret_key=secret_key)
                self.assertEqual(result.returncode == 0, accepted, result.stderr)

    def test_explicit_development_mode_remains_usable(self):
        for secret_key in (None, "", "change-this-for-local-development"):
            with self.subTest(secret_key=secret_key):
                result = self.load_settings(debug="1", secret_key=secret_key)
                self.assertEqual(result.returncode, 0, result.stderr)
                debug, loaded_key = json.loads(result.stdout)
                self.assertTrue(debug)
                self.assertTrue(loaded_key)
                if secret_key:
                    self.assertEqual(loaded_key, secret_key)
