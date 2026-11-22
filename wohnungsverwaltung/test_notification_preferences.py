from importlib import import_module

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from .access import ROLE_APPLICANT, ROLE_EMPLOYEE, ROLE_TENANT
from .models import GlobalSettings, NotificationPreference
from .notification_preferences import USER_GROUPS, USER_MAIL_TYPES, mail_allowed


class NotificationPreferenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = get_user_model().objects.create_user(
            username="applicant", email="abc@example.test"
        )
        cls.account.groups.add(Group.objects.get(name=ROLE_APPLICANT))

    def setUp(self):
        self.url = reverse("profile:notifications")

    def test_user_delivery_matrix(self):
        policy = GlobalSettings.objects.create()
        preference = NotificationPreference.objects.create(account=self.account)
        for enabled in (True, False):
            policy.user_mail_types = {"viewing_invited": enabled}
            policy.save()
            for choice in ("default", "on", "off"):
                with self.subTest(enabled=enabled, choice=choice):
                    preference.choices = {} if choice == "default" else {"viewing_changes": choice}
                    preference.save()
                    self.assertEqual(
                        mail_allowed(self.account, "viewing_invited"), enabled and choice != "off"
                    )
                    self.assertEqual(
                        mail_allowed(self.account, "viewing_cancelled"), choice != "off"
                    )

    def test_secure_self_service_and_role_loss(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.account)
        self.assertContains(self.client.get(self.url), "Verwaltungsstandard")
        self.assertNotContains(self.client.get(self.url), 'name="staff_digest"')
        initial = dict.fromkeys(USER_GROUPS, "default")
        response = self.client.post(self.url, {**initial, "version": 0, "viewing_changes": "off"})
        self.assertRedirects(response, self.url)
        preference = NotificationPreference.objects.get(account=self.account)
        self.assertEqual(preference.choices, {"viewing_changes": "off"})
        for invalid in (
            {"account_id": 999},
            {"staff_digest": "on"},
            {"viewing_changes": ["on", "off"]},
        ):
            self.assertEqual(
                self.client.post(self.url, {**initial, "version": 1, **invalid}).status_code, 400
            )
        response = self.client.post(self.url, {**initial, "version": 0, "viewing_changes": "on"})
        self.assertContains(response, "inzwischen geändert", status_code=409)
        self.assertEqual(response.context["form"]["viewing_changes"].value(), "off")

        self.account.groups.set([Group.objects.get(name=ROLE_EMPLOYEE)])
        self.assertNotContains(self.client.get(self.url), 'name="viewing_changes"')
        self.assertRedirects(
            self.client.post(self.url, {"version": 1, "staff_digest": "on"}), self.url
        )
        preference.refresh_from_db()
        self.assertEqual(preference.choices["viewing_changes"], "off")
        account = get_user_model().objects.get(pk=self.account.pk)
        self.assertFalse(mail_allowed(account, "viewing_invited"))
        self.assertFalse(mail_allowed(account, "viewing_proposal_changed"))
        self.assertTrue(mail_allowed(account, "staff_daily_digest"))

        self.account.groups.add(Group.objects.get(name=ROLE_TENANT))
        response = self.client.get(self.url)
        self.assertContains(response, 'name="staff_digest"')
        self.assertEqual(response.context["form"]["viewing_changes"].value(), "off")

    def test_csrf_is_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.account)
        self.assertEqual(client.post(self.url, {"version": 0}).status_code, 403)
        self.assertFalse(NotificationPreference.objects.exists())


class NotificationPolicyMigrationTests(TransactionTestCase):
    def test_existing_switch_populates_every_mail_type(self):
        # Keep the live test schema at the latest migration for teardown.
        before = ("immobilien", "0038_merge_rental_completion_and_mail_settings")
        after = ("immobilien", "0039_notification_preferences")
        latest = MigrationExecutor(connection).loader.graph.leaf_nodes("immobilien")
        migration = import_module("wohnungsverwaltung.migrations.0039_notification_preferences")
        self.assertEqual(set(migration.MAIL_TYPES), set(USER_MAIL_TYPES))
        try:
            for enabled in (True, False):
                executor = MigrationExecutor(connection)
                executor.migrate([before])
                settings_model = executor.loader.project_state([before]).apps.get_model(
                    "immobilien", "GlobalSettings"
                )
                settings_model.objects.update_or_create(
                    pk=1,
                    defaults={
                        "optional_user_emails_enabled": enabled,
                        "reply_to": "reply@example.test",
                    },
                )
                MigrationExecutor(connection).migrate([after])
                self.assertEqual(GlobalSettings.objects.get().reply_to, "reply@example.test")
                self.assertEqual(
                    GlobalSettings.objects.get().user_mail_types,
                    dict.fromkeys(USER_MAIL_TYPES, enabled),
                )
        finally:
            MigrationExecutor(connection).migrate(latest)
