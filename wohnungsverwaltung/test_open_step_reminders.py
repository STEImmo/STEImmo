from datetime import timedelta
from io import StringIO
from smtplib import SMTPDataError
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .access import ROLE_APPLICANT, ROLE_GLOBAL_SETTINGS
from .models import (
    ApplicationReviewEvent,
    Bewerbung,
    DecisionNotification,
    NotificationPreference,
    Person,
    ViewingAppointment,
    ViewingAppointmentEvent,
    Wohnung,
)
from .notification_preferences import USER_MAIL_TYPES
from .open_step_reminders import MAIN_REMINDER, VIEWING_REMINDER


@override_settings(
    DEMO_MODE=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DECISION_NOTIFICATION_ORIGIN="https://steimmo.example",
)
class OpenStepReminderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = get_user_model().objects.create_user("applicant", email="owner@example.test")
        cls.account.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        person = Person.objects.create(user=cls.account, vorname="Test", nachname="Person")
        unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="04")
        cls.application = Bewerbung.objects.create(
            person=person, wohnung=unit, main_application_unlocked=True
        )
        cls.event = cls.application.review_events.create(
            kind=ApplicationReviewEvent.Kind.MAIN_UNLOCKED
        )
        cls.now = timezone.now()
        cls.application.review_events.filter(pk=cls.event.pk).update(
            created_at=cls.now - timedelta(hours=48)
        )

    def run_command(self, *, send=True, now=None):
        output = StringIO()
        with patch("django.utils.timezone.now", return_value=now or self.now):
            with self.captureOnCommitCallbacks(execute=True):
                call_command("remind_open_steps", send=send, stdout=output)
        return output.getvalue()

    def test_preview_and_send_once_at_due_time(self):
        self.assertIn("0 neue", self.run_command(send=False, now=self.now - timedelta(seconds=1)))
        self.assertIn("1 neue", self.run_command(send=False))
        self.assertFalse(DecisionNotification.objects.exists())
        self.assertEqual(mail.outbox, [])
        self.run_command()
        self.run_command()
        notice = DecisionNotification.objects.get(kind=MAIN_REMINDER)
        self.assertEqual(notice.status, DecisionNotification.Status.SENT)
        self.assertEqual(notice.version, str(self.event.pk))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.account.email])
        path = reverse("wohnungsverwaltung:main_application_status", args=[self.application.pk])
        self.assertIn(f"https://steimmo.example{path}", mail.outbox[0].body)

    def test_submit_after_queue_suppresses_delivery(self):
        with self.captureOnCommitCallbacks(execute=True):
            call_command("remind_open_steps", send=True, stdout=StringIO())
            Bewerbung.objects.filter(pk=self.application.pk).update(submitted_at=self.now)
        self.assertEqual(DecisionNotification.objects.get().status, "suppressed")
        self.assertEqual(mail.outbox, [])

    def test_rollback_cancels_queue_and_delivery(self):
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                call_command("remind_open_steps", send=True, stdout=StringIO())
                transaction.set_rollback(True)
        self.assertFalse(DecisionNotification.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_preference_off_during_retry_suppresses_delivery(self):
        with patch(
            "wohnungsverwaltung.decision_notifications.send_mail",
            side_effect=SMTPDataError(451, b"temporary failure"),
        ):
            self.run_command()
        self.assertEqual(DecisionNotification.objects.get().status, "retry")
        NotificationPreference.objects.create(
            account=self.account, choices={"user_reminders": "off"}
        )
        self.run_command()
        notice = DecisionNotification.objects.get()
        self.assertEqual((notice.status, notice.attempts), ("suppressed", 1))
        self.assertEqual(mail.outbox, [])

    def test_global_disable_then_enable_retires_pending_reminder(self):
        call_command("remind_open_steps", send=True, stdout=StringIO())
        self.assertEqual(DecisionNotification.objects.get().status, "pending")
        manager = get_user_model().objects.create_user("settings-manager")
        manager.groups.add(Group.objects.get(name=ROLE_GLOBAL_SETTINGS))
        self.client.force_login(manager)
        url = reverse("verwaltung:global_settings")
        choices = dict.fromkeys(USER_MAIL_TYPES, "on")
        choices.pop(MAIN_REMINDER)
        self.assertEqual(self.client.post(url, {"version": 0, **choices}).status_code, 302)
        choices[MAIN_REMINDER] = "on"
        self.assertEqual(self.client.post(url, {"version": 1, **choices}).status_code, 302)
        self.run_command()
        notice = DecisionNotification.objects.get()
        self.assertEqual((notice.status, notice.attempts), ("suppressed", 0))
        self.assertEqual(mail.outbox, [])

    def test_enabling_after_due_does_not_backfill_and_role_is_required(self):
        NotificationPreference.objects.create(
            account=self.account, reminders_changed_at=self.now + timedelta(seconds=1)
        )
        self.assertIn("0 neue", self.run_command(send=False, now=self.now + timedelta(hours=1)))
        NotificationPreference.objects.all().update(reminders_changed_at=None)
        self.account.groups.clear()
        self.run_command()
        self.assertEqual(DecisionNotification.objects.get().status, "suppressed")
        self.assertEqual(mail.outbox, [])

    def create_viewing(self, invited_hours_before_start=48):
        Bewerbung.objects.filter(pk=self.application.pk).update(main_application_unlocked=False)
        start = self.now + timedelta(hours=24, minutes=30)
        appointment = ViewingAppointment.objects.create(
            application=self.application, starts_at=start, ends_at=start + timedelta(minutes=30)
        )
        event = appointment.events.create(
            kind=ViewingAppointmentEvent.Kind.CREATED, appointment_version=appointment.version
        )
        appointment.events.filter(pk=event.pk).update(
            created_at=start - timedelta(hours=invited_hours_before_start)
        )
        return appointment

    def test_viewing_cutoff_and_short_notice(self):
        appointment = self.create_viewing(invited_hours_before_start=47)
        self.assertIn("0 neue", self.run_command(send=False))
        appointment.events.update(created_at=appointment.starts_at - timedelta(hours=48))
        self.assertIn("0 neue", self.run_command(send=False, now=self.now + timedelta(minutes=31)))
        self.run_command()
        self.assertEqual(DecisionNotification.objects.get().kind, VIEWING_REMINDER)
        self.assertIn(f"#bewerbung-{self.application.pk}", mail.outbox[0].body)

    def test_viewing_rescheduled_after_queue_is_suppressed(self):
        appointment = self.create_viewing()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("remind_open_steps", send=True, stdout=StringIO())
            appointment.version += 1
            appointment.starts_at += timedelta(hours=72)
            appointment.ends_at += timedelta(hours=72)
            appointment.save()
            appointment.events.create(
                kind=ViewingAppointmentEvent.Kind.RESCHEDULED,
                appointment_version=appointment.version,
            )
        self.assertEqual(DecisionNotification.objects.get().status, "suppressed")
        self.assertEqual(mail.outbox, [])
        self.run_command(now=appointment.starts_at - timedelta(hours=24, minutes=30))
        self.assertEqual(DecisionNotification.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(DEMO_MODE=True)
    def test_demo_allows_preview_only(self):
        self.assertIn("1 neue", self.run_command(send=False))
        with self.assertRaises(CommandError):
            self.run_command()
        self.assertFalse(DecisionNotification.objects.exists())
