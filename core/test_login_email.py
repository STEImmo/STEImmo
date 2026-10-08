"""Email identifier regressions for issue #64."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.test_auth_revocation import PASSWORD, AccountChangesMixin
from wohnungsverwaltung.access import ROLE_EMPLOYEE
from wohnungsverwaltung.models import AccountLoginThrottle


class EmailLoginTests(AccountChangesMixin, TestCase):
    def test_registration_unicode_domain_spelling_can_be_used_for_login(self):
        email = "Mara@İ.example"
        self.client.post(
            reverse("register"),
            {
                "vorname": "Mara",
                "nachname": "Muster",
                "email": email,
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        account = get_user_model().objects.get(email=email.lower())
        self.client.post(
            reverse("register_verify"), {"email": account.email, "code": self.mailed_code()}
        )
        self.client.logout()
        response = self.client.post(reverse("login"), {"username": email, "password": PASSWORD})
        self.assertRedirects(response, reverse("wohnungsverwaltung:pre_application_list"))
        self.assertEqual(self.client.session["_auth_user_id"], str(account.pk))

    def test_legacy_unicode_domain_spelling_remains_usable(self):
        account = self.create_account(email="Mara@İ.example")
        response = self.client.post(
            reverse("login"), {"username": account.username, "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("wohnungsverwaltung:pre_application_list"))
        self.assertEqual(self.client.session["_auth_user_id"], str(account.pk))

    def test_ambiguous_raw_unicode_identifier_does_not_authenticate(self):
        first = self.create_account(email="Mara@İ.example")
        self.create_account(email=first.email.lower())
        response = self.client.post(
            reverse("login"), {"username": first.username, "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_registration_email_spelling_can_be_used_for_login(self):
        email = "Mara.Muster@Example.Test"
        self.client.post(
            reverse("register"),
            {
                "vorname": "Mara",
                "nachname": "Muster",
                "email": email,
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        self.client.post(reverse("register_verify"), {"email": email, "code": self.mailed_code()})
        account = get_user_model().objects.get(email=email.lower())
        self.client.logout()
        response = self.client.post(reverse("login"), {"username": email, "password": PASSWORD})
        self.assertRedirects(response, reverse("wohnungsverwaltung:pre_application_list"))
        self.assertEqual(self.client.session["_auth_user_id"], str(account.pk))

    def test_employee_email_case_variants_still_require_mfa(self):
        account = self.create_account(ROLE_EMPLOYEE)
        response = self.client.post(
            reverse("login"), {"username": account.username.upper(), "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("employee_mfa_verify"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.client.post(reverse("employee_mfa_verify"), {"code": self.mailed_code()})
        self.assertEqual(self.client.session["_auth_user_id"], str(account.pk))

    def test_selected_person_email_with_uppercase_remains_usable(self):
        account = self.create_account(email="Mara.Muster@Example.Test")
        response = self.client.post(
            reverse("login"), {"username": account.username.lower(), "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("wohnungsverwaltung:pre_application_list"))
        self.assertEqual(self.client.session["_auth_user_id"], str(account.pk))

    def test_email_case_variants_share_the_account_failure_limit(self):
        account = self.create_account()
        for email in (account.email, account.email.upper(), "Account@Example.Test"):
            response = self.client.post(
                reverse("login"), {"username": email, "password": "incorrect"}
            )
            self.assertEqual(response.status_code, 200)
        throttle = AccountLoginThrottle.objects.get(user=account)
        self.assertEqual(throttle.failed_attempts, 3)
        self.assertIsNotNone(throttle.locked_until)
        response = self.client.post(
            reverse("login"), {"username": account.email.upper(), "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_ambiguous_case_variants_do_not_authenticate_either_account(self):
        first = self.create_account()
        second = self.create_account(email=first.email.upper())
        for account in (first, second):
            with self.subTest(email=account.email):
                self.client.logout()
                response = self.client.post(
                    reverse("login"), {"username": account.email, "password": PASSWORD}
                )
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("_auth_user_id", self.client.session)
