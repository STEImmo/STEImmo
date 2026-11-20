from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from .access import (
    ROLE_APPLICANT,
    ROLE_EMPLOYEE,
    ROLE_GLOBAL_SETTINGS,
    ROLE_TENANT,
    ROLE_USER_MANAGEMENT,
)
from .models import GlobalSettings, GlobalSettingsChange


class GlobalSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = get_user_model().objects.create_user(username="settings-manager")
        cls.account.groups.add(Group.objects.get(name=ROLE_GLOBAL_SETTINGS))
        cls.other = get_user_model().objects.create_user(username="other")

    def setUp(self):
        self.url = reverse("verwaltung:global_settings")

    def test_anonymous_and_ordinary_roles_cannot_read_or_write(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.post(self.url, {"version": 0}).status_code, 302)
        self.client.force_login(self.other)
        for role in (ROLE_EMPLOYEE, ROLE_USER_MANAGEMENT, ROLE_APPLICANT, ROLE_TENANT):
            with self.subTest(role=role):
                self.other.groups.set([Group.objects.get(name=role)])
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.post(self.url, {"version": 0}).status_code, 403)
        self.assertFalse(GlobalSettings.objects.exists())

    def test_default_save_and_audit(self):
        self.client.force_login(self.account)
        response = self.client.get(self.url)
        self.assertTrue(response.context["form"]["optional_user_emails_enabled"].value())
        self.assertContains(response, 'aria-current="page">Einstellungen')
        self.assertFalse(GlobalSettings.objects.exists())

        response = self.client.post(self.url, {"version": 0})
        self.assertRedirects(response, self.url)
        current = GlobalSettings.objects.get()
        self.assertFalse(current.optional_user_emails_enabled)
        self.assertEqual(current.version, 1)
        change = GlobalSettingsChange.objects.get()
        self.assertEqual(change.actor_account_id, self.account.pk)
        self.assertIsNotNone(change.changed_at)
        self.assertEqual(change.changed_fields, ["optional_user_emails_enabled"])

        self.assertRedirects(self.client.post(self.url, {"version": 1}), self.url)
        self.assertEqual(GlobalSettingsChange.objects.count(), 1)
        current.refresh_from_db()
        self.assertEqual(current.version, 1)

    def test_stale_form_keeps_current_value_and_submitted_selection(self):
        self.client.force_login(self.account)
        self.client.post(self.url, {"version": 0})
        response = self.client.post(self.url, {"version": 0, "optional_user_emails_enabled": "on"})
        self.assertContains(response, "Aktuell gespeichert: Deaktiviert", status_code=409)
        self.assertTrue(response.context["form"]["optional_user_emails_enabled"].value())
        self.assertFalse(GlobalSettings.objects.get().optional_user_emails_enabled)
        self.assertEqual(GlobalSettingsChange.objects.count(), 1)

    def test_invalid_values_and_missing_csrf_do_not_write(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.account)
        self.assertEqual(client.post(self.url, {"version": 0}).status_code, 403)
        client.get(self.url)
        token = client.cookies["csrftoken"].value
        for data in (
            {"version": "bad"},
            {"version": [0, 1]},
            {"version": 0, "optional_user_emails_enabled": "bad"},
            {"version": 0, "optional_user_emails_enabled": ["on", "on"]},
        ):
            with self.subTest(data=data):
                response = client.post(self.url, data, HTTP_X_CSRFTOKEN=token)
                self.assertEqual(response.status_code, 400)
        self.assertFalse(GlobalSettings.objects.exists())
        self.assertFalse(GlobalSettingsChange.objects.exists())

    def test_update_rolls_back_when_audit_write_fails(self):
        GlobalSettings.objects.create()
        self.client.force_login(self.account)
        with (
            patch.object(GlobalSettingsChange.objects, "create", side_effect=RuntimeError),
            self.assertRaises(RuntimeError),
        ):
            self.client.post(self.url, {"version": 0})
        current = GlobalSettings.objects.get()
        self.assertTrue(current.optional_user_emails_enabled)
        self.assertEqual(current.version, 0)
        self.assertFalse(GlobalSettingsChange.objects.exists())
