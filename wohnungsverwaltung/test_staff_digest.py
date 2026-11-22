from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import StringIO
from smtplib import SMTPDataError
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from .access import ROLE_EMPLOYEE
from .models import (
    Bewerbung,
    DecisionNotification,
    NotificationPreference,
    Person,
    ProcessNotification,
    Wohnung,
)
from .staff_digest import DIGEST_KIND, StaffTask, digest_candidates, is_due, queue_digest, send_slot
from .viewings import BERLIN, record_viewing_event

MONDAY = datetime(2026, 3, 30, 9, tzinfo=BERLIN)
TUESDAY = MONDAY + timedelta(days=1)
THURSDAY = MONDAY - timedelta(days=4)


def create_application(unit, username):
    user = get_user_model().objects.create_user(username)
    person = Person.objects.create(
        user=user, vorname="Private", nachname=username, email=f"{username}@example.test"
    )
    application = Bewerbung.objects.create(person=person, wohnung=unit)
    Bewerbung.objects.filter(pk=application.pk).update(created_at=THURSDAY)
    return application


def create_staff(username, *, direct=False):
    staff = get_user_model().objects.create_user(username, email=f"{username}@example.test")
    if direct:
        staff.user_permissions.add(Permission.objects.get(codename="access_employee_area"))
    else:
        staff.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
    return staff


class StaffDigestClockTests(SimpleTestCase):
    def test_weekend_summer_time_and_cutoff(self):
        self.assertIsNone(send_slot(MONDAY - timedelta(seconds=1)))
        self.assertIsNone(send_slot(MONDAY - timedelta(days=1)))
        self.assertEqual(send_slot(datetime(2026, 3, 30, 7, tzinfo=UTC)), MONDAY)
        friday = MONDAY - timedelta(days=3)
        task = StaffTask(None, "Prüfen", friday, "pre")
        self.assertFalse(is_due(task, MONDAY, MONDAY))
        self.assertTrue(is_due(task, TUESDAY, TUESDAY))
        later_task = StaffTask(None, "Prüfen", friday + timedelta(hours=1), "pre")
        self.assertFalse(is_due(later_task, TUESDAY + timedelta(hours=2), TUESDAY))

    def test_deadline_accelerates_task_until_expiry(self):
        task = StaffTask(None, "Planen", MONDAY, "proposal", deadline=TUESDAY)
        self.assertTrue(is_due(task, MONDAY, MONDAY))
        self.assertFalse(is_due(task, TUESDAY, TUESDAY))


@override_settings(
    DEMO_MODE=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DECISION_NOTIFICATION_ORIGIN="https://steimmo.example",
)
class StaffDigestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = create_staff("staff")
        unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="04")
        cls.first = create_application(unit, "First")
        cls.second = create_application(unit, "Second")

    def run_digest(self, *, send=True, now=MONDAY):
        output = StringIO()
        with patch("django.utils.timezone.now", return_value=now):
            with self.captureOnCommitCallbacks(execute=True):
                call_command("remind_open_steps", send=send, stdout=output)
        return output.getvalue()

    def test_preview_and_one_delivery_per_eligible_staff_account(self):
        other = create_staff("direct", direct=True)
        get_user_model().objects.create_user("outsider", email="outsider@example.test")
        NotificationPreference.objects.create(
            account=self.staff, choices={"new_applications": "off"}
        )
        self.assertIn("Erstbewerbung prüfen", self.run_digest(send=False))
        self.assertFalse(DecisionNotification.objects.exists())
        self.assertEqual(mail.outbox, [])
        self.run_digest()
        self.run_digest()
        self.assertCountEqual(
            [item.to for item in mail.outbox], [[self.staff.email], [other.email]]
        )
        self.assertEqual(
            DecisionNotification.objects.filter(kind=DIGEST_KIND, status="sent").count(), 2
        )
        for app in (self.first, self.second):
            self.assertIn(str(app.pk), mail.outbox[0].body)
            self.assertNotIn(app.person.nachname, mail.outbox[0].body)
        self.assertIn("https://steimmo.example/", mail.outbox[0].body)

    def test_successful_instant_mail_excludes_only_matching_task(self):
        notice = ProcessNotification.objects.create(
            application=self.first,
            recipient=self.staff,
            kind="pre_task",
            source="pre",
            status="sent",
        )
        ProcessNotification.objects.filter(pk=notice.pk).update(updated_at=MONDAY)
        self.run_digest()
        self.assertNotIn(str(self.first.pk), mail.outbox[0].body)
        self.assertIn(str(self.second.pk), mail.outbox[0].body)

    def test_retry_prunes_withdrawn_application(self):
        with patch(
            "wohnungsverwaltung.decision_notifications.send_mail",
            side_effect=SMTPDataError(451, b"try later"),
        ):
            self.run_digest()
        self.assertEqual(DecisionNotification.objects.get().status, "retry")
        Bewerbung.objects.filter(pk=self.first.pk).update(interest_withdrawn_at=MONDAY)
        self.run_digest(now=MONDAY + timedelta(hours=1))
        self.assertNotIn(str(self.first.pk), mail.outbox[0].body)
        self.assertEqual(
            list(DecisionNotification.objects.get().task_versions), [str(self.second.pk)]
        )

    def test_opt_out_and_revoked_rights_before_send(self):
        other = create_staff("direct", direct=True)
        with patch("django.utils.timezone.now", return_value=MONDAY):
            with self.captureOnCommitCallbacks(execute=True):
                call_command("remind_open_steps", send=True, stdout=StringIO())
                self.staff.groups.clear()
                NotificationPreference.objects.create(
                    account=other, choices={"staff_digest": "off"}
                )
        self.assertEqual(DecisionNotification.objects.filter(status="suppressed").count(), 2)
        self.assertEqual(mail.outbox, [])

    def test_rollback_and_demo(self):
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                call_command("remind_open_steps", send=True, stdout=StringIO())
                transaction.set_rollback(True)
        self.assertFalse(DecisionNotification.objects.exists())
        self.assertEqual(mail.outbox, [])
        with self.settings(DEMO_MODE=True), self.assertRaises(CommandError):
            self.run_digest()

    def test_blocked_or_declined_work_produces_no_notice(self):
        Bewerbung.objects.filter(pk=self.first.pk).update(status="blocked")
        Bewerbung.objects.filter(pk=self.second.pk).update(status="declined")
        self.run_digest()
        self.assertFalse(DecisionNotification.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_main_review_and_documented_completed_viewing(self):
        Bewerbung.objects.filter(pk=self.first.pk).update(
            main_application_unlocked=True, submitted_at=THURSDAY
        )
        viewing = self.second.viewings.create(
            starts_at=THURSDAY - timedelta(hours=2),
            ends_at=THURSDAY - timedelta(hours=1),
            status="completed",
        )
        with patch("django.utils.timezone.now", return_value=THURSDAY):
            record_viewing_event(viewing, kind="recorded", actor=self.staff)
        self.run_digest()
        self.assertIn("Hauptbewerbung prüfen", mail.outbox[0].body)
        self.assertIn("Über Hauptbewerbungsfreigabe entscheiden", mail.outbox[0].body)

    def test_proposal_prompts_action_but_confirmed_viewing_does_not(self):
        viewing = self.first.viewings.create(
            starts_at=THURSDAY,
            ends_at=THURSDAY + timedelta(hours=1),
            proposed_start=TUESDAY,
            status="applicant_declined",
        )
        with patch("django.utils.timezone.now", return_value=MONDAY):
            record_viewing_event(viewing, kind="proposal_changed", actor=self.first.person.user)
        self.second.viewings.create(
            starts_at=TUESDAY, ends_at=TUESDAY + timedelta(hours=1), status="confirmed"
        )
        self.run_digest()
        self.assertIn("Alternativtermin prüfen", mail.outbox[0].body)
        self.assertNotIn(str(self.second.pk), mail.outbox[0].body)


class ParallelDigestTests(TransactionTestCase):
    def test_concurrent_runs_claim_one_daily_notice(self):
        create_staff("parallel", direct=True)
        create_application(
            Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="04"), "Parallel"
        )
        ready = Barrier(2)

        def claim():
            try:
                candidate = next(digest_candidates(MONDAY))
                ready.wait(timeout=10)
                return queue_digest(*candidate)
            finally:
                connections.close_all()

        with patch("django.utils.timezone.now", return_value=MONDAY):
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs = [pool.submit(claim) for _ in range(2)]
                self.assertCountEqual([job.result() for job in jobs], [True, False])
        self.assertEqual(DecisionNotification.objects.filter(kind=DIGEST_KIND).count(), 1)
