import io
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core import test_production_settings
from wohnungsverwaltung.access import (
    APPLICANT_ACCESS_PERMISSION,
    USER_MANAGEMENT_PERMISSION,
)
from wohnungsverwaltung.models import EmployeeLoginVerification, Person, Wohnung, WohnungStatus


class DemoSettingsTests(SimpleTestCase):
    load_settings = test_production_settings.ProductionSettingsTests.load_settings

    def test_demo_starts_without_smtp_and_keeps_https(self):
        result = self.load_settings(
            DJANGO_SETTINGS_MODULE="config.settings_demo",
            DJANGO_EMAIL_HOST="CHANGE_ME",
            DJANGO_DEFAULT_FROM_EMAIL="CHANGE_ME",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [False, True, True, True, 0, "django.core.mail.backends.dummy.EmailBackend"],
        )

    def test_demo_keeps_debug_and_database_guards(self):
        for overrides in ({"DJANGO_DEBUG": "1"}, {"POSTGRES_PASSWORD": "user"}):
            with self.subTest(overrides=overrides):
                result = self.load_settings(
                    DJANGO_SETTINGS_MODULE="config.settings_demo", **overrides
                )
                self.assertNotEqual(result.returncode, 0)


@override_settings(DEMO_MODE=True, EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend")
class DemoSetupTests(TestCase):
    def seed(self):
        call_command("setup_demo", stdout=io.StringIO())

    def test_demo_accounts_and_initial_inventory(self):
        self.seed()
        user = get_user_model().objects.get(username="user")
        manager = get_user_model().objects.get(username="verwaltung")
        self.assertTrue(user.check_password("user"))
        self.assertTrue(manager.check_password("verwaltung"))
        self.assertTrue(user.has_perm(APPLICANT_ACCESS_PERMISSION))
        self.assertTrue(manager.has_perm(USER_MANAGEMENT_PERMISSION))
        self.assertFalse(manager.is_superuser)
        self.assertFalse(manager.is_staff)
        self.assertEqual(Wohnung.objects.count(), 25)
        self.assertTrue(Wohnung.objects.filter(status=WohnungStatus.FREE).exists())
        self.assertTrue(Person.objects.filter(user=user).exists())

    def test_redeploy_preserves_edited_inventory_and_passwords(self):
        self.seed()
        unit = Wohnung.objects.first()
        unit.description = "Beim Test bearbeitet"
        unit.save()
        user = get_user_model().objects.get(username="user")
        user.set_password("changed-for-test")
        user.save()
        self.seed()
        unit.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(unit.description, "Beim Test bearbeitet")
        self.assertTrue(user.check_password("changed-for-test"))
        self.assertEqual(Wohnung.objects.count(), 25)

    @override_settings(DEMO_MODE=False)
    def test_seed_refuses_outside_demo_without_creating_accounts(self):
        with self.assertRaises(CommandError):
            self.seed()
        self.assertFalse(get_user_model().objects.filter(username="user").exists())
        self.assertFalse(Wohnung.objects.exists())

    def test_applicant_login_and_management_code_work_without_mail(self):
        self.seed()
        response = self.client.post(reverse("login"), {"username": "user", "password": "user"})
        self.assertRedirects(response, reverse("wohnungsverwaltung:pre_application_list"))
        self.client.logout()
        response = self.client.post(
            reverse("login"), {"username": "verwaltung", "password": "verwaltung"}
        )
        self.assertRedirects(response, reverse("employee_mfa_verify"))
        self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.post(reverse("employee_mfa_verify"), {"code": "000000"})
        self.assertRedirects(response, reverse("verwaltung:wohnung_list"))
        self.assertEqual(self.client.get(reverse("verwaltung:user_account_list")).status_code, 200)

    def test_reissued_demo_code_finishes_and_gets_new_challenge(self):
        self.seed()
        user = get_user_model().objects.get(username="verwaltung")
        verification = EmployeeLoginVerification(user=user)
        self.assertEqual(verification.issue_code(), "000000")
        previous = verification.code_hash
        self.assertEqual(verification.issue_code(), "000000")
        self.assertNotEqual(verification.code_hash, previous)

    def test_registration_accepts_demo_code_without_smtp(self):
        self.client.post(
            reverse("register"),
            {
                "vorname": "Demo",
                "nachname": "Registrierung",
                "email": "neu@example.test",
                "password1": "DemoRegistration!4826",
                "password2": "DemoRegistration!4826",
            },
        )
        response = self.client.post(
            reverse("register_verify"), {"email": "neu@example.test", "code": "000000"}
        )
        self.assertRedirects(response, reverse("wohnungsverwaltung:pre_application_list"))
        self.assertTrue(get_user_model().objects.get(email="neu@example.test").is_active)

    def test_demo_login_shows_test_accounts_and_code(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, "Testumgebung mit Beispieldaten")
        self.assertContains(response, "<code>user</code>", html=True)
        self.assertContains(response, "Benutzername oder E-Mail-Adresse")
        self.assertContains(response, "000000")

    @override_settings(DEMO_MODE=False)
    def test_regular_login_has_no_demo_notice(self):
        response = self.client.get(reverse("login"))
        self.assertNotContains(response, "Testumgebung mit Beispieldaten")
        self.assertNotContains(response, "000000")

    @override_settings(DEMO_MODE=False)
    def test_regular_codes_stay_random_outside_demo(self):
        verification = EmployeeLoginVerification()
        with patch("wohnungsverwaltung.models.secrets.randbelow", return_value=123456):
            self.assertEqual(verification.issue_code(), "123456")
