"""Prevent the unused Django admin from bypassing employee MFA (PR #88)."""

from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

from core.test_auth_revocation import PASSWORD, AccountChangesMixin
from wohnungsverwaltung.access import ROLE_APPLICANT, ROLE_EMPLOYEE, ROLE_USER_MANAGEMENT
from wohnungsverwaltung.models import EmployeeLoginVerification


class AdminLoginSecurityTests(AccountChangesMixin, TestCase):
    def privileged_accounts(self):
        for role, superuser in (
            (ROLE_EMPLOYEE, False),
            (ROLE_USER_MANAGEMENT, False),
            (ROLE_APPLICANT, True),
        ):
            account = self.create_account(role, email=f"{role.lower()}@example.test")
            account.is_staff = True
            account.is_superuser = superuser
            account.save(update_fields=["is_staff", "is_superuser"])
            yield account

    def test_admin_password_login_cannot_open_the_management_area(self):
        target = reverse("verwaltung:wohnung_list")
        for account in self.privileged_accounts():
            with self.subTest(role=account.groups.get().name, superuser=account.is_superuser):
                client = Client()
                response = client.post(
                    "/admin/login/",
                    {"username": account.username, "password": PASSWORD, "next": target},
                )
                management_response = client.get(target)
                self.assertEqual(management_response.status_code, 302)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn("_auth_user_id", client.session)
                self.assertFalse(EmployeeLoginVerification.objects.filter(user=account).exists())
                self.assertEqual(len(mail.outbox), 0)
                self.assertRedirects(
                    management_response,
                    f"{reverse('login')}?next={target}",
                    fetch_redirect_response=False,
                )

    def test_privileged_staff_can_only_log_in_after_confirming_the_email_code(self):
        target = reverse("verwaltung:wohnung_list")
        for account in self.privileged_accounts():
            with self.subTest(role=account.groups.get().name, superuser=account.is_superuser):
                client = Client()
                response = client.post(
                    reverse("login"),
                    {"username": account.username, "password": PASSWORD, "next": target},
                )
                self.assertRedirects(response, reverse("employee_mfa_verify"))
                self.assertNotIn("_auth_user_id", client.session)
                self.assertTrue(EmployeeLoginVerification.objects.filter(user=account).exists())
                self.assertRedirects(
                    client.get(target),
                    f"{reverse('login')}?next={target}",
                    fetch_redirect_response=False,
                )
                response = client.post(reverse("employee_mfa_verify"), {"code": self.mailed_code()})
                self.assertRedirects(response, target)
                self.assertEqual(client.session["_auth_user_id"], str(account.pk))

    def test_admin_routes_are_unavailable(self):
        for url in ("/admin/", "/admin/login/", "/admin/logout/", "/admin/auth/user/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
