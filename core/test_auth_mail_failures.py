"""Public feedback and safe diagnostics for authentication mail failures (#189)."""

from smtplib import SMTPAuthenticationError
from unittest.mock import patch

from django.contrib.messages import INFO, SUCCESS, get_messages
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.test_auth_revocation import PASSWORD, AccountChangesMixin
from wohnungsverwaltung.access import ROLE_EMPLOYEE
from wohnungsverwaltung.models import EmployeeLoginVerification, RegistrationVerification


class RegistrationResendFeedbackTests(AccountChangesMixin, TestCase):
    def test_resend_feedback_is_informational_and_identical_for_all_delivery_outcomes(self):
        account = self.create_account()
        account.is_active = False
        account.save(update_fields=["is_active"])
        verification = RegistrationVerification(user=account)
        verification.issue_code()
        verification.save()
        feedback = []
        for outcome in ("sent", "smtp_error", "timeout", "zero", "throttled", "unknown", "active"):
            with self.subTest(outcome=outcome):
                verification.last_sent_at = timezone.now() - verification.RESEND_DELAY
                if outcome == "throttled":
                    verification.last_sent_at = timezone.now()
                verification.save(update_fields=["last_sent_at"])
                if outcome == "active":
                    account.is_active = True
                    account.save(update_fields=["is_active"])
                email = "unknown@example.test" if outcome == "unknown" else account.email
                error = {
                    "smtp_error": SMTPAuthenticationError(535, b"private relay details"),
                    "timeout": TimeoutError("private relay details"),
                }.get(outcome)
                with patch(
                    "core.views.send_mail", return_value=0 if outcome == "zero" else 1
                ) as send:
                    send.side_effect = error
                    if error or outcome == "zero":
                        with self.assertLogs("core.views", level="WARNING"):
                            response = Client().post(
                                reverse("resend_registration_code"), {"email": email}
                            )
                    else:
                        response = Client().post(
                            reverse("resend_registration_code"), {"email": email}
                        )
                self.assertRedirects(
                    response, reverse("register_verify"), fetch_redirect_response=False
                )
                notices = list(get_messages(response.wsgi_request))
                self.assertEqual(len(notices), 1)
                self.assertEqual(notices[0].level, INFO)
                self.assertNotIn("private relay details", str(notices[0]))
                feedback.append(str(notices[0]))
                self.assertEqual(
                    send.call_count, int(outcome not in {"throttled", "unknown", "active"})
                )
        self.assertEqual(len(set(feedback)), 1)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthenticationMailDiagnosticsTests(AccountChangesMixin, TestCase):
    def post_code_request(self, flow):
        if flow == "registration":
            return self.client.post(
                reverse("register"),
                {
                    "vorname": "Konto",
                    "nachname": "Test",
                    "email": "new@example.test",
                    "password1": PASSWORD,
                    "password2": PASSWORD,
                },
            )
        if flow == "registration_resend":
            account = self.create_account(email="resend@example.test")
            account.is_active = False
            account.save(update_fields=["is_active"])
            verification = RegistrationVerification(user=account)
            verification.issue_code()
            verification.last_sent_at = timezone.now() - verification.RESEND_DELAY
            verification.save()
            return self.client.post(reverse("resend_registration_code"), {"email": account.email})
        account = self.create_account(ROLE_EMPLOYEE, email="employee@example.test")
        return self.client.post(
            reverse("login"), {"username": account.username, "password": PASSWORD}
        )

    def test_smtp_diagnostics_identify_the_flow_without_exposing_private_details(self):
        for flow in ("registration", "registration_resend", "employee_mfa"):
            with self.subTest(flow=flow):

                def fail_delivery(**kwargs):
                    # A relay can echo the entire submitted message in its error.
                    private_details = repr(kwargs)
                    raise SMTPAuthenticationError(535, private_details.encode())

                with (
                    self.assertLogs("core.views", level="WARNING") as logs,
                    patch("core.views.send_mail", side_effect=fail_delivery),
                ):
                    response = self.post_code_request(flow)
                self.assertEqual(
                    logs.output,
                    [
                        "WARNING:core.views:Verification email delivery failed "
                        f"({flow}: SMTPAuthenticationError)."
                    ],
                )
                self.assertIsNone(logs.records[0].exc_info)
                notices = list(get_messages(response.wsgi_request))
                self.assertFalse(any(message.level == SUCCESS for message in notices))
                if flow != "employee_mfa":
                    response = self.client.get(reverse("register_verify"))
                self.assertNotContains(response, "535")
                self.assertNotContains(response, PASSWORD)
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_zero_delivery_diagnostics_identify_the_flow_without_claiming_success(self):
        for flow in ("registration", "registration_resend", "employee_mfa"):
            with self.subTest(flow=flow):
                with (
                    self.assertLogs("core.views", level="WARNING") as logs,
                    patch("core.views.send_mail", return_value=0),
                ):
                    response = self.post_code_request(flow)
                self.assertEqual(
                    logs.output,
                    [
                        "WARNING:core.views:Verification email delivery failed "
                        f"({flow}: no delivery)."
                    ],
                )
                self.assertFalse(
                    any(message.level == SUCCESS for message in get_messages(response.wsgi_request))
                )
                self.assertNotIn("_auth_user_id", self.client.session)
                if flow == "employee_mfa":
                    self.assertContains(response, "konnte nicht gesendet werden")
                    self.assertFalse(EmployeeLoginVerification.objects.exists())
