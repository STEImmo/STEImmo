from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse

from wohnungsverwaltung import test_viewings
from wohnungsverwaltung.access import SYSTEM_SETTINGS_SESSION_KEY
from wohnungsverwaltung.models import SystemSettings
from wohnungsverwaltung.viewings import send_viewing_notification
from wohnungsverwaltung.views import _send_application_invitation


class GlobalUserMailTests(TestCase):
    setUp = test_viewings.ViewingTests.setUp
    payload = test_viewings.ViewingTests.payload
    post = test_viewings.ViewingTests.post
    schedule = test_viewings.ViewingProposalTests.schedule
    response_url = test_viewings.ViewingTests.response_url
    decline = test_viewings.ViewingProposalTests.decline
    proposal_url = test_viewings.ViewingProposalTests.proposal_url
    proposal_data = test_viewings.ViewingProposalTests.proposal_data

    def toggle_globally(self, enabled):
        admin, created = get_user_model().objects.get_or_create(username="global-admin")
        if created:
            admin.user_permissions.add(Permission.objects.get(codename="manage_system_settings"))
        client = Client()
        client.force_login(admin)
        session = client.session
        session[SYSTEM_SETTINGS_SESSION_KEY] = admin.pk
        session.save()
        state, _ = SystemSettings.objects.get_or_create(pk=1)
        data = {"version": state.version}
        if enabled:
            data["optional_user_emails_enabled"] = "on"
        self.assertRedirects(
            client.post(reverse("verwaltung:system_settings"), data),
            reverse("verwaltung:system_settings"),
        )

    def test_global_off_on_suppresses_waiting_mail_even_without_an_attempt_while_off(self):
        from wohnungsverwaltung.models import ApplicationReviewEvent

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.client.post(self.create_url, self.payload())
        event = self.application.viewings.first().events.get(kind="created")
        self.application.main_application_unlocked = True
        self.application.save(update_fields=["main_application_unlocked"])
        ApplicationReviewEvent.objects.create(
            application=self.application, kind="invitation_failed"
        )
        self.toggle_globally(False)
        self.toggle_globally(True)
        for callback in callbacks:
            callback()
        event.refresh_from_db()
        self.assertEqual(event.notification_status, "suppressed")
        self.assertIsNone(
            _send_application_invitation(self.application, self.employee, "https://example.test")
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_disabled_user_mail_keeps_appointment_and_never_replays_after_reenabling(self):
        state = SystemSettings.objects.update_or_create(
            pk=1, defaults={"optional_user_emails_enabled": False}
        )[0]
        appointment = self.schedule()
        event = appointment.events.get(kind="created")
        self.assertEqual(event.notification_status, "suppressed")
        self.assertEqual(len(mail.outbox), 0)
        state.optional_user_emails_enabled = True
        state.save()
        self.assertFalse(send_viewing_notification(event.pk))
        self.assertEqual(len(mail.outbox), 0)
        self.post(
            test_viewings.ViewingTests.update_url(self, appointment),
            self.payload(days=2, version=1, action="reschedule"),
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_pending_mail_checks_current_global_value_at_first_attempt(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.client.post(self.create_url, self.payload())
        SystemSettings.objects.update_or_create(
            pk=1, defaults={"optional_user_emails_enabled": False}
        )[0]
        for callback in callbacks:
            callback()
        self.assertEqual(len(mail.outbox), 0)
        event = self.application.viewings.first().events.get(kind="created")
        self.assertEqual(event.notification_status, "suppressed")

    def test_global_user_switch_preserves_staff_notification_for_multi_role_recipient(self):
        SystemSettings.objects.update_or_create(
            pk=1, defaults={"optional_user_emails_enabled": False}
        )[0]
        self.employee.email = "staff@example.test"
        self.employee.save(update_fields=["email"])
        self.employee.groups.add(self.user.groups.first())
        appointment = self.decline()
        self.post(self.proposal_url(appointment), self.proposal_data(appointment))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.employee.email])

    def test_main_invitation_suppression_is_distinct_from_failure_and_does_not_replay(self):
        state = SystemSettings.objects.update_or_create(
            pk=1, defaults={"optional_user_emails_enabled": False}
        )[0]
        self.assertIsNone(
            _send_application_invitation(self.application, self.employee, "https://example.test")
        )
        self.assertTrue(
            self.application.review_events.filter(kind="invitation_suppressed").exists()
        )
        self.assertFalse(self.application.review_events.filter(kind="invitation_failed").exists())
        state.optional_user_emails_enabled = True
        state.save()
        self.assertIsNone(
            _send_application_invitation(self.application, self.employee, "https://example.test")
        )
        self.assertEqual(len(mail.outbox), 0)
