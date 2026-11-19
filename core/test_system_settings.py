from io import StringIO

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from core.test_auth_revocation import AccountChangesMixin
from wohnungsverwaltung.access import ROLE_USER_MANAGEMENT, SYSTEM_SETTINGS_SESSION_KEY
from wohnungsverwaltung.models import SystemSettings, SystemSettingsChange


class SystemSettingsTests(AccountChangesMixin, TestCase):
    def setUp(self):
        self.admin = self.create_account(ROLE_USER_MANAGEMENT, "settings@example.test")
        call_command("grant_system_settings_access", self.admin.username, stdout=StringIO())
        self.client.force_login(self.admin)
        session = self.client.session
        session[SYSTEM_SETTINGS_SESSION_KEY] = self.admin.pk
        session.save()
        self.url = reverse("verwaltung:system_settings")

    def data(self, **changes):
        data = {"version": SystemSettings.objects.get(pk=1).version}
        data.update(changes)
        return data

    def test_page_limits_scope_and_keeps_account_management_in_existing_area(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Optionale E-Mails an Nutzer aktivieren")
        self.assertContains(response, "Mailadressen und Testversand")
        self.assertContains(response, "Organisations- und Kontaktangaben")
        self.assertNotContains(response, 'name="username"')
        accounts = self.client.get(reverse("verwaltung:user_account_list"))
        self.assertContains(accounts, 'name="username"')
        access_form = (
            accounts.content.decode()
            .split('action="' + reverse("verwaltung:system_settings_access") + '"', 1)[1]
            .split("</form>", 1)[0]
        )
        self.assertIn('name="csrfmiddlewaretoken"', access_form)

    def test_global_switch_is_saved_with_actor_time_and_field_without_account_changes(self):
        self.client.get(self.url)
        before = list(self.admin.user_permissions.values_list("pk", flat=True))
        self.assertRedirects(self.client.post(self.url, self.data()), self.url)
        state = SystemSettings.objects.get(pk=1)
        self.assertFalse(state.optional_user_emails_enabled)
        change = SystemSettingsChange.objects.filter(kind="settings").get()
        self.assertEqual(change.actor, self.admin)
        self.assertIsNotNone(change.created_at)
        self.assertEqual(change.changed_fields, ["optional_user_emails_enabled"])
        self.assertContains(self.client.get(self.url), "Optionale Nutzer-E-Mails")
        self.assertRedirects(
            self.client.post(self.url, self.data(optional_user_emails_enabled="on")), self.url
        )
        self.assertTrue(SystemSettings.objects.get(pk=1).optional_user_emails_enabled)
        self.assertEqual(list(self.admin.user_permissions.values_list("pk", flat=True)), before)

    def test_stale_tab_cannot_overwrite_newer_change(self):
        self.client.get(self.url)
        stale = self.data(optional_user_emails_enabled="on")
        self.client.post(self.url, self.data())
        response = self.client.post(self.url, stale)
        self.assertContains(response, "zwischenzeitlich geändert", status_code=409)
        self.assertFalse(SystemSettings.objects.get(pk=1).optional_user_emails_enabled)
        self.assertEqual(SystemSettingsChange.objects.filter(kind="settings").count(), 1)

    def test_audit_failure_rolls_back_the_effective_value(self):
        from unittest.mock import patch

        with patch(
            "wohnungsverwaltung.system_settings.SystemSettingsChange.objects.create",
            side_effect=RuntimeError("audit unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, self.data())
        self.assertTrue(SystemSettings.objects.get(pk=1).optional_user_emails_enabled)
        self.assertFalse(SystemSettingsChange.objects.filter(kind="settings").exists())

    def test_unchanged_save_does_not_create_a_fictitious_change(self):
        version = SystemSettings.objects.get(pk=1).version
        self.assertRedirects(
            self.client.post(self.url, self.data(optional_user_emails_enabled="on")), self.url
        )
        self.assertEqual(SystemSettings.objects.get(pk=1).version, version)
        self.assertFalse(SystemSettingsChange.objects.filter(kind="settings").exists())

    def test_invalid_version_and_manipulated_fields_leave_values_unchanged(self):
        self.client.get(self.url)
        for data in ({}, {"version": "invalid"}, self.data(smtp_password="secret-canary")):
            response = self.client.post(self.url, data)
            self.assertEqual(response.status_code, 400)
            self.assertNotContains(response, "secret-canary", status_code=400)
        self.assertTrue(SystemSettings.objects.get(pk=1).optional_user_emails_enabled)
        self.assertFalse(SystemSettingsChange.objects.filter(kind="settings").exists())

    def test_settings_write_requires_csrf_and_explicit_permission(self):
        self.client.get(self.url)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.cookies.update(self.client.cookies)
        self.assertEqual(csrf_client.post(self.url, self.data()).status_code, 403)
        ordinary = self.create_account(ROLE_USER_MANAGEMENT, "ordinary@example.test")
        self.client.force_login(ordinary)
        self.assertEqual(self.client.post(self.url, self.data()).status_code, 403)
        self.assertTrue(SystemSettings.objects.get(pk=1).optional_user_emails_enabled)

    def test_access_changes_are_audited_and_reject_stale_revision(self):
        self.client.get(self.url)
        target = self.create_account(email="target@example.test")
        data = self.data(action="grant", username=target.username)
        url = reverse("verwaltung:system_settings_access")
        self.assertRedirects(self.client.post(url, data), reverse("verwaltung:user_account_list"))
        change = SystemSettingsChange.objects.filter(kind="access", actor=self.admin).get()
        self.assertEqual(change.target, target)
        self.assertEqual(change.changed_fields, ["manage_system_settings"])
        self.assertEqual(self.client.post(url, data).status_code, 409)

    def test_globally_disabled_user_mail_does_not_suppress_login_or_registration_codes(self):
        from django.core import mail

        from core.test_auth_revocation import PASSWORD

        self.client.post(self.url, self.data())
        self.client.logout()
        mail.outbox.clear()
        self.assertRedirects(
            self.client.post(
                reverse("login"), {"username": self.admin.username, "password": PASSWORD}
            ),
            reverse("employee_mfa_verify"),
        )
        self.assertEqual(len(mail.outbox), 1)
        self.register_account()
        self.assertEqual(len(mail.outbox), 2)

    def test_settings_only_admin_cannot_manage_other_accounts(self):
        self.admin.groups.clear()
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.get(reverse("verwaltung:user_account_list")).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("verwaltung:system_settings_access"),
                self.data(action="grant", username="missing"),
            ).status_code,
            403,
        )
