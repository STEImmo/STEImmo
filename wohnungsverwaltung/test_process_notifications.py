from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.management import call_command
from django.db import connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import test_viewings
from . import tests as application_tests
from .access import ROLE_APPLICANT, ROLE_GLOBAL_SETTINGS
from .models import (
    Bewerbung,
    GlobalSettings,
    NotificationPreference,
    ProcessNotification,
    ViewingAppointment,
)
from .notifications import queue_submission_notifications, send_process_notification


class ProcessNotificationTests(TestCase):
    def setUp(self):
        test_viewings.ViewingTests.setUp(self)
        self.application.review_priority = Bewerbung.Priority.UNRATED
        self.application.save()

    def test_submission_sends_receipt_and_individual_staff_task_after_commit_once(self):
        self.employee.email = "staff@example.test"
        self.employee.save()
        with self.captureOnCommitCallbacks(execute=True):
            queue_submission_notifications(self.application, "pre", "https://testserver")
            queue_submission_notifications(self.application, "pre", "https://testserver")
            self.assertEqual(mail.outbox, [])
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(ProcessNotification.objects.count(), 2)
        for message in mail.outbox:
            self.assertEqual(len(message.to), 1)
            self.assertFalse(message.attachments)
            self.assertIn("https://testserver/", message.body)
            self.assertNotIn(self.application.ueber_mich, message.body)
        for notice in ProcessNotification.objects.all():
            self.assertFalse(send_process_notification(notice.pk))
        self.assertEqual(len(mail.outbox), 2)

    def test_rollback_has_no_intent_or_mail(self):
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                queue_submission_notifications(self.application, "pre", "https://testserver")
                transaction.set_rollback(True)
        self.assertFalse(ProcessNotification.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_smtp_failure_does_not_rollback_submission(self):
        with patch(
            "wohnungsverwaltung.notifications.send_repliable_mail", side_effect=TimeoutError
        ):
            with self.captureOnCommitCallbacks(execute=True):
                queue_submission_notifications(self.application, "pre", "https://testserver")
        self.application.refresh_from_db()
        notice = ProcessNotification.objects.get()
        self.assertEqual(notice.status, "uncertain")
        self.assertFalse(send_process_notification(notice.pk))

    def pending(self, stage="pre"):
        with self.captureOnCommitCallbacks(execute=False):
            queue_submission_notifications(self.application, stage, "https://testserver")
        return ProcessNotification.objects.get(recipient=self.user, kind=f"{stage}_receipt")

    def preference(self, account, **values):
        NotificationPreference.objects.update_or_create(
            account=account, defaults={"choices": values}
        )

    def test_personal_off_suppresses_initial_receipt_and_cannot_be_replayed_after_on(self):
        self.preference(self.user, application_receipts="off")
        notice = self.pending()
        self.assertEqual(notice.status, "suppressed")
        self.preference(self.user, application_receipts="on")
        self.assertFalse(send_process_notification(notice.pk))
        self.assertEqual(mail.outbox, [])
        self.assertIn("Die Verwaltung prüft", self.application.get_applicant_next_step())

    def test_pending_receipt_rechecks_personal_selection_and_admin_release(self):
        for cause in ("personal", "type"):
            with self.subTest(cause=cause):
                ProcessNotification.objects.all().delete()
                NotificationPreference.objects.all().delete()
                GlobalSettings.objects.all().delete()
                notice = self.pending()
                if cause == "personal":
                    self.preference(self.user, application_receipts="off")
                elif cause == "type":
                    self.preference(self.user, application_receipts="on")
                    GlobalSettings.objects.create(
                        user_mail_types={"pre_application_received": False}
                    )
                self.assertFalse(send_process_notification(notice.pk))
                notice.refresh_from_db()
                self.assertEqual(notice.status, "suppressed")
                self.assertEqual(notice.attempts, 0)

    def test_selection_changed_after_claim_is_rechecked_before_smtp(self):
        notice = self.pending()

        def prepare_message(*args):
            self.preference(self.user, application_receipts="off")
            return "Eingang", "Geschützter Vorgang"

        with patch("wohnungsverwaltung.notifications._message", side_effect=prepare_message):
            with patch("wohnungsverwaltung.notifications.send_repliable_mail") as send:
                self.assertFalse(send_process_notification(notice.pk))
        send.assert_not_called()
        notice.refresh_from_db()
        self.assertEqual(notice.status, "suppressed")

    def test_each_user_mail_type_is_independent_and_personal_on_requires_release(self):
        GlobalSettings.objects.create(user_mail_types={"pre_application_received": False})
        self.preference(self.user, application_receipts="on")
        notice = self.pending()
        self.assertEqual(notice.status, "suppressed")
        self.application.main_application_unlocked = True
        self.application.submitted_at = timezone.now()
        self.application.save()
        with self.captureOnCommitCallbacks(execute=True):
            queue_submission_notifications(self.application, "main", "https://testserver")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Hauptbewerbung", mail.outbox[0].subject)

    def test_role_loss_inactive_account_and_changed_owner_suppress_waiting_receipt(self):
        for cause in ("role", "inactive", "owner"):
            with self.subTest(cause=cause):
                notice = self.pending()
                if cause == "role":
                    self.user.groups.clear()
                elif cause == "inactive":
                    get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
                else:
                    self.person.user = None
                    self.person.save()
                self.assertFalse(send_process_notification(notice.pk))
                notice.refresh_from_db()
                self.assertEqual(notice.status, "suppressed")
                self.user.groups.add(Group.objects.get(name=ROLE_APPLICANT))
                get_user_model().objects.filter(pk=self.user.pk).update(is_active=True)
                self.person.user = self.user
                self.person.save()
                ProcessNotification.objects.all().delete()
        self.assertEqual(mail.outbox, [])

    def test_staff_opt_out_does_not_reroute_and_direct_grants_are_respected(self):
        self.employee.email = "staff@example.test"
        self.employee.save()
        direct = get_user_model().objects.create_user(
            username="direct", email="direct@example.test"
        )
        direct.user_permissions.add(Permission.objects.get(codename="access_employee_area"))
        self.preference(self.employee, new_applications="off")
        with self.captureOnCommitCallbacks(execute=True):
            queue_submission_notifications(self.application, "pre", "https://testserver")
        self.assertCountEqual([m.to for m in mail.outbox], [[self.person.email], [direct.email]])
        self.assertEqual(
            ProcessNotification.objects.get(recipient=self.employee).status, "suppressed"
        )

    def test_staff_role_loss_before_retry_does_not_send_or_fallback(self):
        self.employee.email = "staff@example.test"
        self.employee.save()
        self.pending()
        notice = ProcessNotification.objects.get(recipient=self.employee)
        self.employee.groups.clear()
        self.assertFalse(send_process_notification(notice.pk))
        notice.refresh_from_db()
        self.assertEqual(notice.status, "suppressed")
        self.assertEqual(mail.outbox, [])

    def test_completed_pre_review_and_main_decision_make_waiting_tasks_obsolete(self):
        self.employee.email = "staff@example.test"
        self.employee.save()
        self.pending()
        notice = ProcessNotification.objects.get(recipient=self.employee)
        Bewerbung.objects.filter(pk=self.application.pk).update(review_priority=2)
        self.assertFalse(send_process_notification(notice.pk))
        notice.refresh_from_db()
        self.assertEqual(notice.status, "obsolete")
        self.application.main_application_unlocked = True
        self.application.submitted_at = timezone.now()
        self.application.save()
        self.pending("main")
        notice = ProcessNotification.objects.get(recipient=self.employee, kind="main_task")
        Bewerbung.objects.filter(pk=self.application.pk).update(accepted_at=timezone.now())
        self.assertFalse(send_process_notification(notice.pk))
        notice.refresh_from_db()
        self.assertEqual(notice.status, "obsolete")

    def test_stale_submission_tasks_are_not_delivered(self):
        for changes in (
            {"interest_withdrawn_at": timezone.now()},
            {"status": "declined"},
            {"status": "blocked"},
            {"main_application_unlocked": True},
        ):
            with self.subTest(changes=changes):
                notice = self.pending()
                Bewerbung.objects.filter(pk=self.application.pk).update(**changes)
                self.assertFalse(send_process_notification(notice.pk))
                notice.refresh_from_db()
                self.assertEqual(notice.status, "obsolete")
                Bewerbung.objects.filter(pk=self.application.pk).update(
                    status="open", interest_withdrawn_at=None, main_application_unlocked=False
                )
                ProcessNotification.objects.all().delete()

    def test_failed_delivery_rechecks_preferences_and_has_three_attempt_limit(self):
        notice = self.pending()
        with patch(
            "wohnungsverwaltung.notifications.send_repliable_mail",
            side_effect=ConnectionRefusedError,
        ):
            for _ in range(5):
                self.assertFalse(send_process_notification(notice.pk))
        notice.refresh_from_db()
        self.assertEqual(notice.attempts, 3)
        self.assertEqual(notice.status, "failed")
        notice.attempts = 1
        notice.save()
        self.preference(self.user, application_receipts="off")
        self.assertFalse(send_process_notification(notice.pk))
        notice.refresh_from_db()
        self.assertEqual(notice.status, "suppressed")

    def test_retry_command_does_not_resend_successes_and_sanitizes_errors(self):
        self.employee.email = "staff@example.test"
        self.employee.save()
        notice = self.pending()
        self.assertTrue(send_process_notification(notice.pk))
        with patch(
            "wohnungsverwaltung.notifications.send_repliable_mail",
            side_effect=ConnectionRefusedError("secret-person@example.test"),
        ):
            with self.assertLogs("wohnungsverwaltung.notifications", level="WARNING") as logs:
                call_command("retry_process_notifications")
        self.assertNotIn("secret-person", str(logs.output))
        call_command("retry_process_notifications")
        self.assertCountEqual(
            [m.to for m in mail.outbox], [[self.person.email], [self.employee.email]]
        )

    @override_settings(DEMO_MODE=True, EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")
    def test_demo_never_calls_mail_transport_even_with_smtp_backend(self):
        notice = self.pending()
        with patch("wohnungsverwaltung.notifications.send_repliable_mail") as send:
            self.assertFalse(send_process_notification(notice.pk))
        send.assert_not_called()
        notice.refresh_from_db()
        self.assertEqual(notice.status, "suppressed")


class SubmissionNotificationTests(TestCase):
    setUp = application_tests.PreApplicationAuthenticationTests.setUp
    valid_form_data = application_tests.PreApplicationAuthenticationTests.valid_form_data

    def test_real_pre_submission_only_sends_after_commit_and_repeat_post_does_not_send(self):
        self.client.force_login(self.user)
        url = reverse("wohnungsverwaltung:pre_application_create")
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.assertEqual(self.client.post(url, self.valid_form_data()).status_code, 302)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(ProcessNotification.objects.count(), 1)
        for callback in callbacks:
            callback()
        self.assertEqual(len(mail.outbox), 1)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, self.valid_form_data())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(ProcessNotification.objects.count(), 1)

    def test_invalid_input_sends_nothing_and_occupancy_rejection_only_sends_decision(self):
        self.client.force_login(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("wohnungsverwaltung:pre_application_create"), {})
            self.assertFalse(Bewerbung.objects.exists())
            self.free_unit.max_occupants = 1
            self.free_unit.save()
            self.client.post(
                reverse("wohnungsverwaltung:pre_application_create"), self.valid_form_data()
            )
        self.assertEqual(
            [message.subject for message in mail.outbox],
            [
                "Entscheidung zu Ihrer Bewerbung",
            ],
        )
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertFalse(ProcessNotification.objects.exists())

    def test_pre_submission_rollback_also_discards_intent(self):
        self.client.force_login(self.user)
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                self.client.post(
                    reverse("wohnungsverwaltung:pre_application_create"), self.valid_form_data()
                )
                transaction.set_rollback(True)
        self.assertFalse(Bewerbung.objects.exists())
        self.assertFalse(ProcessNotification.objects.exists())
        self.assertEqual(mail.outbox, [])


class MainSubmissionNotificationTests(TestCase):
    setUp = application_tests.MainApplicationUploadTests.setUp
    pdf_upload = staticmethod(application_tests.MainApplicationUploadTests.pdf_upload)
    png_upload = staticmethod(application_tests.MainApplicationUploadTests.png_upload)
    complete_upload_data = application_tests.MainApplicationUploadTests.complete_upload_data
    applicant_post = application_tests.MainApplicationUploadTests.applicant_post

    def test_main_submission_sends_two_notices_and_repeat_does_not_send(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.applicant_post(self.complete_upload_data()).status_code, 302)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            set(ProcessNotification.objects.values_list("kind", flat=True)),
            {"main_receipt", "main_task"},
        )
        self.assertTrue(self.application.get_applicant_next_step())
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.applicant_post({"action": "submit"}).status_code, 403)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(ProcessNotification.objects.count(), 2)
        from .dashboard import filter_application_workflow

        self.application.refresh_from_db()
        self.assertIn("Die Verwaltung prüft", self.application.get_applicant_next_step())
        self.assertEqual(self.application.get_next_actor_display(), "Verwaltung")
        self.assertFalse(
            filter_application_workflow(Bewerbung.objects.all(), "waiting", timezone.now()).exists()
        )

    def test_drafts_uploads_and_missing_proofs_have_no_notice(self):
        data = self.complete_upload_data()
        data["action"] = "save_draft"
        with self.captureOnCommitCallbacks(execute=True):
            self.applicant_post({"action": "submit"})
            self.assertEqual(self.applicant_post(data).status_code, 302)
            self.assertEqual(self.applicant_post({"action": "save_draft"}).status_code, 302)
        self.assertFalse(ProcessNotification.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_main_rollback_has_no_mail(self):
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                self.applicant_post(self.complete_upload_data())
                transaction.set_rollback(True)
        self.assertFalse(ProcessNotification.objects.exists())
        self.assertEqual(mail.outbox, [])


class ViewingResponseNotificationTests(TestCase):
    def setUp(self):
        test_viewings.ViewingTests.setUp(self)
        self.employee.email = "staff@example.test"
        self.employee.save()
        self.client.force_login(self.user)
        self.appointment = ViewingAppointment.objects.create(
            application=self.application,
            starts_at=timezone.now() + timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=1, minutes=30),
        )
        self.response_url = reverse(
            "wohnungsverwaltung:applicant_viewing_response",
            args=[self.application.pk, self.appointment.pk],
        )

    def respond(self, action):
        self.appointment.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                self.response_url, {"version": self.appointment.version, "action": action}
            )

    def test_confirmation_and_withdrawal_notify_staff_only_and_keep_application_active(self):
        self.respond("confirm")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.employee.email])
        self.assertIn("Terminzusage berücksichtigen", mail.outbox[0].body)
        self.respond("confirm")
        self.assertEqual(len(mail.outbox), 1)
        self.respond("decline")
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Terminzusage zurückgezogen", mail.outbox[-1].body)
        self.assertIn("neuer Termin", mail.outbox[-1].body)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "open")
        self.assertIsNone(self.application.interest_withdrawn_at)
        self.assertIn(
            "Verwaltung prüft die weitere Terminplanung", self.application.get_applicant_next_step()
        )

    def test_decline_invalid_repeat_and_foreign_applicant(self):
        self.respond("invalid")
        self.assertFalse(ProcessNotification.objects.exists())
        self.respond("decline")
        self.assertIn("Besichtigung abgesagt", mail.outbox[0].body)
        self.respond("decline")
        self.assertEqual(len(mail.outbox), 1)
        self.client.force_login(self.employee)
        self.assertEqual(
            self.client.post(self.response_url, {"version": 1, "action": "confirm"}).status_code,
            403,
        )

    def test_rollback_then_superseded_answer_callbacks_do_not_send(self):
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                self.client.post(self.response_url, {"version": 1, "action": "confirm"})
                transaction.set_rollback(True)
        self.assertFalse(ProcessNotification.objects.exists())
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.client.post(self.response_url, {"version": 1, "action": "confirm"})
        self.respond("decline")
        count = len(mail.outbox)
        for callback in callbacks:
            callback()
        self.assertEqual(len(mail.outbox), count)
        self.assertEqual(ProcessNotification.objects.order_by("pk").first().status, "obsolete")

    def test_staff_selection_is_rechecked_before_answer_delivery(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.client.post(self.response_url, {"version": 1, "action": "confirm"})
        NotificationPreference.objects.create(
            account=self.employee, choices={"viewing_responses": "off"}
        )
        for callback in callbacks:
            callback()
        self.assertEqual(mail.outbox, [])
        self.assertEqual(ProcessNotification.objects.get().status, "suppressed")

    def test_automatic_cancellation_after_response_retains_the_applicant_link(self):
        from .viewings import record_viewing_event

        applicant_url = "http://testserver" + reverse("wohnungsverwaltung:pre_application_list")
        record_viewing_event(self.appointment, kind="created", notification_url=applicant_url)
        self.respond("confirm")
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.unit.max_occupants = 1
            self.unit.save(notification_origin="http://testserver/")
        self.assertEqual(len(mail.outbox), 2)
        cancellation = mail.outbox[-1]
        self.assertEqual(cancellation.to, [self.person.email])
        self.assertIn("Abgesagt", cancellation.body)
        self.assertIn(applicant_url, cancellation.body)
        self.assertNotIn(self.detail_url, cancellation.body)
        self.assertEqual(mail.outbox[0].subject, "Entscheidung zu Ihrer Bewerbung")

    def test_failure_keeps_binding_response_and_retry_sends_only_to_current_staff(self):
        with patch(
            "wohnungsverwaltung.notifications.send_repliable_mail",
            side_effect=ConnectionRefusedError,
        ):
            self.respond("confirm")
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.status, "confirmed")
        notice = ProcessNotification.objects.get()
        self.assertEqual(notice.status, "failed")
        self.assertTrue(send_process_notification(notice.pk))
        self.assertFalse(send_process_notification(notice.pk))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.detail_url, mail.outbox[0].body)
        self.assertEqual(self.client.get(self.detail_url).status_code, 403)


class NotificationSelectionTests(TestCase):
    setUp = test_viewings.ViewingTests.setUp

    def test_switching_off_permanently_suppresses_pending_mail_even_if_reenabled(self):
        from .notification_preferences import USER_GROUPS

        self.client.force_login(self.user)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            queue_submission_notifications(self.application, "pre", "https://testserver")
        url = reverse("profile:notifications")
        for version, selection in ((0, "off"), (1, "on")):
            data = {key: "default" for key in USER_GROUPS}
            data.update(version=version, application_receipts=selection)
            self.assertEqual(self.client.post(url, data).status_code, 302)
        for callback in callbacks:
            callback()
        self.assertEqual(ProcessNotification.objects.get().status, "suppressed")
        self.assertEqual(mail.outbox, [])

    def test_admin_release_change_does_not_replay_suppressed_mail_or_reset_personal_choice(self):
        from .notification_preferences import USER_MAIL_TYPES

        self.employee.groups.add(Group.objects.get(name=ROLE_GLOBAL_SETTINGS))
        self.client.force_login(self.employee)
        NotificationPreference.objects.create(
            account=self.user, choices={"application_receipts": "on"}
        )
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            queue_submission_notifications(self.application, "pre", "https://testserver")
        url = reverse("verwaltung:global_settings")
        data = {key: "on" for key in USER_MAIL_TYPES}
        data.pop("pre_application_received")
        self.assertEqual(self.client.post(url, data | {"version": 0}).status_code, 302)
        data["pre_application_received"] = "on"
        self.assertEqual(self.client.post(url, data | {"version": 1}).status_code, 302)
        for callback in callbacks:
            callback()
        self.assertEqual(ProcessNotification.objects.get().status, "suppressed")
        self.assertEqual(
            NotificationPreference.objects.get(account=self.user).choices["application_receipts"],
            "on",
        )
        self.assertEqual(mail.outbox, [])


class ConcurrentNotificationTests(TransactionTestCase):
    setUp = test_viewings.ViewingTests.setUp
    payload = test_viewings.ViewingTests.payload

    def test_parallel_setting_updates_do_not_silently_overwrite_a_newer_selection(self):
        barrier = Barrier(2)

        def save_selection(enabled):
            try:
                client = Client()
                client.force_login(get_user_model().objects.get(pk=self.employee.pk))
                barrier.wait(timeout=10)
                data = {"version": 0, "viewing_responses": "on"}
                if enabled:
                    data["new_applications"] = "on"
                return client.post(reverse("profile:notifications"), data).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(save_selection, (True, False)))
        self.assertCountEqual(results, [302, 409])
        self.assertEqual(NotificationPreference.objects.get(account=self.employee).version, 1)

    def test_parallel_delivery_claims_send_once_without_open_transaction(self):
        # Persist an intent without firing its callback until the test workers start.
        with patch("wohnungsverwaltung.notifications.send_process_notification"):
            queue_submission_notifications(self.application, "pre", "https://testserver")
        notice = ProcessNotification.objects.get()
        barrier = Barrier(2)
        calls = []

        def transport(*args, **kwargs):
            self.assertFalse(connection.in_atomic_block)
            self.assertTrue(connection.get_autocommit())
            calls.append(args)
            return 1

        def deliver():
            try:
                barrier.wait(timeout=10)
                return send_process_notification(notice.pk)
            finally:
                connections.close_all()

        with patch("wohnungsverwaltung.notifications.send_repliable_mail", side_effect=transport):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: deliver(), range(2)))
        self.assertCountEqual(results, [True, False])
        self.assertEqual(len(calls), 1)

    def test_viewing_handoff_has_no_row_locks_and_serializes_cancellation(self):
        entered = Event()
        finish = Event()
        cancellation_started = Event()
        appointment_id = []

        def transport(*args, **kwargs):
            self.assertFalse(connection.in_atomic_block)
            appointment_id.append(ViewingAppointment.objects.get().pk)
            entered.set()
            self.assertTrue(finish.wait(timeout=15))
            return 1

        def schedule():
            try:
                client = Client()
                client.force_login(self.employee)
                return client.post(self.create_url, self.payload()).status_code
            finally:
                connections.close_all()

        def cancel():
            try:
                client = Client()
                client.force_login(self.employee)
                cancellation_started.set()
                return client.post(
                    reverse(
                        "wohnungsverwaltung:employee_viewing_update",
                        args=[self.application.pk, appointment_id[0]],
                    ),
                    {"action": "cancel", "version": 1, "reason": "Test"},
                ).status_code
            finally:
                connections.close_all()

        with patch("wohnungsverwaltung.notifications.send_repliable_mail", side_effect=transport):
            with ThreadPoolExecutor(max_workers=2) as executor:
                scheduled = executor.submit(schedule)
                try:
                    self.assertTrue(entered.wait(timeout=15))
                    # A separate DB connection can lock both rows while SMTP waits.
                    with transaction.atomic():
                        Bewerbung.objects.select_for_update(nowait=True).get(pk=self.application.pk)
                        ViewingAppointment.objects.select_for_update(nowait=True).get(
                            pk=appointment_id[0]
                        )
                    cancelled = executor.submit(cancel)
                    self.assertTrue(cancellation_started.wait(timeout=10))
                    self.assertFalse(cancelled.done())
                finally:
                    finish.set()
                self.assertEqual(scheduled.result(timeout=15), 302)
                self.assertEqual(cancelled.result(timeout=15), 302)
        self.assertEqual(ViewingAppointment.objects.get().status, "cancelled")
