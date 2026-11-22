"""Public feedback and safe diagnostics for authentication mail failures (#189)."""

from smtplib import SMTPAuthenticationError
from unittest.mock import patch

from django.contrib.messages import INFO, get_messages
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.test_auth_revocation import AccountChangesMixin
from wohnungsverwaltung.models import RegistrationVerification


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
