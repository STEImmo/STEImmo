from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core.mail_settings import callback_recipients, get_mail_settings

from .access import ROLE_GLOBAL_SETTINGS
from .models import GlobalSettings, GlobalSettingsChange


@override_settings(CALLBACK_RECIPIENTS=["old@example.test"])
class MailSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = get_user_model().objects.create_user(
            username="mail-admin", email="admin@example.test"
        )
        cls.account.groups.add(Group.objects.get(name=ROLE_GLOBAL_SETTINGS))

    def setUp(self):
        self.url = reverse("verwaltung:mail_settings")
        self.test_url = reverse("verwaltung:test_mail")
        self.client.force_login(self.account)

    def test_mail_settings_requires_permission_and_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.account)
        self.assertEqual(client.post(self.url).status_code, 403)
        self.assertEqual(client.post(self.test_url).status_code, 403)
        self.assertEqual(client.get(self.test_url).status_code, 405)
        self.account.groups.clear()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.test_url).status_code, 403)

    def test_first_save_replaces_legacy_recipients_and_audits_field_names(self):
        self.assertContains(self.client.get(self.url), "old@example.test")
        self.assertEqual(callback_recipients(get_mail_settings()), ["old@example.test"])
        data = {
            "version": 0,
            "callback_recipients": "one@example.test\r\ntwo@example.test",
            "reply_to": "reply@example.test",
        }
        self.assertRedirects(self.client.post(self.url, data), self.url)
        self.assertEqual(
            callback_recipients(get_mail_settings()), ["one@example.test", "two@example.test"]
        )
        self.assertEqual(self.client.post(self.url, data).status_code, 409)
        change = GlobalSettingsChange.objects.get()
        self.assertEqual(change.actor_account_id, self.account.pk)
        self.assertEqual(change.changed_fields, ["callback_recipients", "reply_to"])

    def test_invalid_addresses_do_not_write(self):
        for recipients, reply_to in (
            ("", ""),
            ("invalid", ""),
            ("one@example.test", "reply@example.test\n"),
        ):
            with self.subTest(recipients=recipients, reply_to=reply_to):
                response = self.client.post(
                    self.url,
                    {"version": 0, "callback_recipients": recipients, "reply_to": reply_to},
                )
                self.assertEqual(response.status_code, 400)
        self.assertFalse(GlobalSettings.objects.exists())
        self.assertFalse(GlobalSettingsChange.objects.exists())

    def test_test_mail_uses_account_and_saved_reply_to_and_is_limited(self):
        GlobalSettings.objects.create(reply_to="reply@example.test")
        data = {"recipient": "ignored@example.test", "reply_to": "ignored@example.test"}
        response = self.client.post(self.test_url, data, follow=True)
        self.assertContains(response, "Mail-Backend hat die Testmail verarbeitet")
        self.assertEqual(mail.outbox[0].to, ["admin@example.test"])
        self.assertEqual(mail.outbox[0].reply_to, ["reply@example.test"])
        self.assertTrue(mail.outbox[0].subject.startswith("[STEImmo-Test]"))
        response = self.client.post(self.test_url, follow=True)
        self.assertContains(response, "Bitte warten Sie eine Minute")
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(DEMO_MODE=True)
    def test_demo_uses_no_backend(self):
        with patch("wohnungsverwaltung.settings_views.get_connection") as connection:
            response = self.client.post(self.test_url, follow=True)
        connection.assert_not_called()
        self.assertContains(response, "Der Testversand wurde simuliert")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")
    def test_smtp_acceptance(self):
        with patch("django.core.mail.backends.smtp.EmailBackend.send_messages", return_value=1):
            response = self.client.post(self.test_url, follow=True)
        self.assertContains(response, "vom Mailserver angenommen")

    def test_backend_timeout_is_sanitized_and_counts_as_attempt(self):
        with patch(
            "wohnungsverwaltung.settings_views.send_repliable_mail",
            side_effect=TimeoutError("private detail"),
        ) as send:
            response = self.client.post(self.test_url, follow=True)
            self.assertContains(response, "Die Testmail konnte nicht versendet werden")
            self.assertNotContains(response, "private detail")
            self.client.post(self.test_url)
        send.assert_called_once()

    def test_zero_backend_result_is_a_failure(self):
        with patch("wohnungsverwaltung.settings_views.send_repliable_mail", return_value=0):
            response = self.client.post(self.test_url, follow=True)
        self.assertContains(response, "Die Testmail konnte nicht versendet werden")
