from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from smtplib import SMTPException
from unittest.mock import patch

from django.core import mail
from django.db import close_old_connections
from django.test import (
    Client,
    SimpleTestCase,
    TestCase,
    TransactionTestCase,
    override_settings,
)
from django.urls import reverse
from django.utils import timezone

from .forms import CallbackForm


class CallbackPhoneTests(SimpleTestCase):
    def test_rejects_text_injection_and_numbers_outside_length_limits(self):
        for value in (
            "Hallo",
            "abc123456",
            "123456@example.test",
            "<script>alert(1)</script>",
            "12345",
            "1234567890123456",
            "+49\nBcc: other@example.test",
            "+49+1234567",
            "１２３４５６７８９",
            "---() /.",
        ):
            with self.subTest(value=value):
                form = CallbackForm({"phone": value, "availability": "Abends"})
                self.assertFalse(form.is_valid())
                self.assertIn("phone", form.errors)

    def test_accepts_usual_local_and_international_formats(self):
        for value in ("0931 5550123", "+49 (931) 555-0123", "0049/931/5550123", "(0931) 5550123"):
            with self.subTest(value=value):
                form = CallbackForm({"phone": value, "availability": "Abends"})
                self.assertTrue(form.is_valid(), form.errors)


@override_settings(
    CALLBACK_RECIPIENTS=["verwaltung@example.test"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class ConcurrentCallbackThrottleTests(TransactionTestCase):
    def test_parallel_bot_requests_cannot_exceed_five_reserved_attempts(self):
        def attempt(_):
            close_old_connections()
            try:
                return (
                    Client()
                    .post(
                        reverse("contact"),
                        {"phone": "+49 931 5550123", "availability": "Abends"},
                        REMOTE_ADDR="192.0.2.100",
                    )
                    .status_code
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=8) as workers:
            results = list(workers.map(attempt, range(12)))
        self.assertEqual(results.count(302), 5)
        self.assertEqual(results.count(429), 7)
        self.assertEqual(len(mail.outbox), 5)


@override_settings(
    CALLBACK_RECIPIENTS=["verwaltung@example.test"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class ContactTests(TestCase):
    data = {"phone": "+49 (931) 555-0123", "availability": "Montag bis Freitag ab 17 Uhr"}

    def setUp(self):
        self.url = reverse("contact")

    def test_contact_is_public_and_linked_in_navigation(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Rückruf wünschen")
        self.assertContains(response, 'name="phone"')
        self.assertContains(response, 'name="availability"')
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, reverse("privacy"))
        self.assertIn("no-store", response.headers["Cache-Control"])
        home = self.client.get(reverse("home"))
        self.assertContains(home, f'href="{self.url}"')
        self.assertNotContains(home, "tel:")
        self.assertNotContains(response, "tel:")

    def test_valid_request_emails_only_configured_recipient_and_redirects(self):
        response = self.client.post(self.url, self.data)
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["verwaltung@example.test"])
        self.assertIn(self.data["phone"], message.body)
        self.assertIn(self.data["availability"], message.body)
        self.assertNotIn(self.data["phone"], message.subject)
        self.assertContains(self.client.get(self.url), "Ihr Rückrufwunsch wurde versendet.")
        self.client.get(self.url)
        self.assertEqual(len(mail.outbox), 1)

    def test_required_fields_and_invalid_phone_do_not_send_mail(self):
        for data, field in (
            ({}, "phone"),
            ({"phone": self.data["phone"]}, "availability"),
            ({"phone": "abc123", "availability": "Abends"}, "phone"),
            ({"phone": "123", "availability": "Abends"}, "phone"),
        ):
            with self.subTest(data=data):
                response = self.client.post(self.url, data)
                self.assertFormError(
                    response.context["form"], field, response.context["form"].errors[field]
                )
                self.assertEqual(len(mail.outbox), 0)

    def test_overlong_values_are_rejected(self):
        response = self.client.post(self.url, {"phone": "1" * 41, "availability": "x" * 501})
        self.assertEqual(set(response.context["form"].errors), {"phone", "availability"})
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_submission_preserves_user_input(self):
        response = self.client.post(self.url, {"phone": self.data["phone"]})
        self.assertContains(response, self.data["phone"])
        self.assertTrue(response.context["form"].errors)

    def test_smtp_failure_preserves_input_and_allows_retry(self):
        with patch("core.contact.send_mail", side_effect=SMTPException("private details")):
            with self.assertLogs("core.contact", level="WARNING") as logs:
                response = self.client.post(self.url, self.data)
        self.assertContains(response, "Bitte versuchen Sie es erneut.", status_code=503)
        self.assertContains(response, self.data["phone"], status_code=503)
        self.assertNotIn("private details", " ".join(logs.output))
        self.assertNotIn(self.data["phone"], " ".join(logs.output))
        self.assertRedirects(self.client.post(self.url, self.data), self.url)

    def test_zero_delivery_count_is_not_reported_as_success(self):
        with patch("core.contact.send_mail", return_value=0):
            response = self.client.post(self.url, self.data)
        self.assertContains(response, "Bitte versuchen Sie es erneut.", status_code=503)
        self.assertNotContains(response, "Ihr Rückrufwunsch wurde versendet.", status_code=503)

    @override_settings(CALLBACK_RECIPIENTS=[])
    def test_missing_recipient_fails_without_sending(self):
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_console_backend_cannot_write_private_callback_details_to_logs(self):
        with patch("core.contact.send_mail") as send:
            response = self.client.post(self.url, self.data)
        send.assert_not_called()
        self.assertEqual(response.status_code, 503)

    def test_post_without_any_fields_is_bound_and_shows_required_errors(self):
        response = self.client.post(self.url, {})
        self.assertEqual(set(response.context["form"].errors), {"phone", "availability"})

    def test_invalid_requests_are_also_limited(self):
        for _ in range(5):
            self.client.post(self.url, {})
        self.assertEqual(self.client.post(self.url, {}).status_code, 429)

    def test_contact_navigation_is_current_and_privacy_mentions_callback_data(self):
        response = self.client.get(self.url)
        self.assertContains(response, f'href="{self.url}" aria-current="page"', count=3)
        privacy = self.client.get(reverse("privacy"))
        self.assertContains(privacy, 'id="rueckruf"')
        self.assertContains(privacy, "Telefonnummer")
        self.assertContains(privacy, "Erreichbarkeit")

    def test_footer_lists_contact_only_under_company_information(self):
        from .test_site_navigation import NavigationParser

        parser = NavigationParser()
        parser.feed(self.client.get(self.url).content.decode())
        self.assertNotIn(self.url, [href for href, _ in parser.navigation["Footernavigation"]])
        self.assertEqual(
            [href for href, _ in parser.navigation["Unternehmensinformationen"]].count(self.url), 1
        )

    @override_settings(DEMO_MODE=True)
    def test_demo_simulates_request_without_sending_real_mail(self):
        with patch("core.contact.send_mail") as send:
            response = self.client.post(self.url, self.data, follow=True)
        send.assert_not_called()
        self.assertContains(response, "Demo: Ihr Rückrufwunsch wurde nur simuliert.")
        self.assertNotContains(response, "Ihr Rückrufwunsch wurde versendet.")

    def test_csrf_is_required(self):
        response = Client(enforce_csrf_checks=True).post(self.url, self.data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_honeypot_rejects_automated_submission(self):
        response = self.client.post(self.url, self.data | {"website": "https://example.test"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(len(mail.outbox), 0)

    def test_sixth_attempt_is_limited_even_across_new_sessions(self):
        for _ in range(5):
            response = Client().post(self.url, self.data)
            self.assertEqual(response.status_code, 302)
        response = Client().post(self.url, self.data)
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)
        self.assertEqual(len(mail.outbox), 5)

    def test_throttle_stores_no_plain_ip_or_form_contents_and_expires(self):
        from .models import CallbackThrottle

        self.client.post(self.url, self.data, REMOTE_ADDR="192.0.2.10")
        row = CallbackThrottle.objects.get()
        self.assertNotIn("192.0.2.10", row.client_hash)
        self.assertEqual(len(row.client_hash), 64)
        CallbackThrottle.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertRedirects(
            self.client.post(self.url, self.data, REMOTE_ADDR="192.0.2.10"), self.url
        )
        self.assertEqual(CallbackThrottle.objects.get().attempts, 1)

    def test_untrusted_forwarded_header_cannot_bypass_limit(self):
        for _ in range(5):
            self.client.post(self.url, self.data, REMOTE_ADDR="192.0.2.10")
        response = self.client.post(
            self.url, self.data, REMOTE_ADDR="192.0.2.10", HTTP_X_FORWARDED_FOR="192.0.2.99"
        )
        self.assertEqual(response.status_code, 429)

    @override_settings(LOGIN_THROTTLE_TRUSTED_PROXY_IPS=("192.0.2.1",))
    def test_trusted_proxy_keeps_different_clients_separate(self):
        for _ in range(5):
            self.client.post(
                self.url, self.data, REMOTE_ADDR="192.0.2.1", HTTP_X_FORWARDED_FOR="192.0.2.10"
            )
        response = self.client.post(
            self.url, self.data, REMOTE_ADDR="192.0.2.1", HTTP_X_FORWARDED_FOR="192.0.2.99"
        )
        self.assertRedirects(response, self.url)
