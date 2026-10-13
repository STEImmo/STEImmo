from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.db import IntegrityError, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .access import ROLE_APPLICANT, ROLE_EMPLOYEE
from .forms import ViewingAppointmentForm
from .models import (
    ApplicationReviewEvent,
    Bewerbung,
    BewerbungStatus,
    Person,
    ViewingAppointment,
    ViewingAppointmentEvent,
    Wohnung,
)


class ViewingTests(TestCase):
    def setUp(self):
        self.employee = get_user_model().objects.create_user(username="viewing-employee")
        self.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        self.user = get_user_model().objects.create_user(username="viewing-applicant")
        self.user.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        self.unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="1.01")
        self.person = Person.objects.create(
            user=self.user, vorname="Ada", nachname="Termin", email="ada@example.test"
        )
        self.application = Bewerbung.objects.create(
            person=self.person,
            wohnung=self.unit,
            personenanzahl=2,
            ueber_mich="Test",
            review_priority=Bewerbung.Priority.NORMAL,
        )
        self.client.force_login(self.employee)
        self.create_url = reverse(
            "wohnungsverwaltung:employee_viewing_create", args=[self.application.pk]
        )
        self.detail_url = reverse(
            "wohnungsverwaltung:employee_application_detail", args=[self.application.pk]
        )
        self.list_url = reverse("wohnungsverwaltung:employee_application_list")

    def payload(self, days=1, **overrides):
        data = {
            "date": (timezone.localdate() + timedelta(days=days)).isoformat(),
            "start_time": "10:00",
            "end_time": "10:30",
            "action": "schedule",
            "reason": "Interne Terminnotiz",
        }
        return data | overrides

    def post(self, url, data):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(url, data)

    def schedule(self):
        self.post(self.create_url, self.payload())
        return ViewingAppointment.objects.get(application=self.application)

    def update_url(self, appointment):
        return reverse(
            "wohnungsverwaltung:employee_viewing_update", args=[self.application.pk, appointment.pk]
        )

    def response_url(self, appointment):
        return reverse(
            "wohnungsverwaltung:applicant_viewing_response",
            args=[self.application.pk, appointment.pk],
        )

    def test_schedule_assigns_only_selected_application_and_sends_after_commit(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            response = self.client.post(self.create_url, self.payload())
        self.assertEqual(response.status_code, 302)
        appointment = ViewingAppointment.objects.get()
        self.assertEqual(appointment.application, self.application)
        self.assertEqual(appointment.application.wohnung, self.unit)
        self.assertEqual(appointment.status, "planned")
        self.assertEqual(timezone.localtime(appointment.starts_at).hour, 10)
        self.assertEqual(appointment.ends_at - appointment.starts_at, timedelta(minutes=30))
        self.assertEqual(len(mail.outbox), 0)
        for callback in callbacks:
            callback()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(reverse("wohnungsverwaltung:pre_application_list"), mail.outbox[0].body)
        self.assertNotIn("Interne Terminnotiz", mail.outbox[0].body)
        event = appointment.events.get(kind="created")
        self.assertEqual(event.actor, self.employee)
        self.assertEqual(event.after["status"], "planned")
        self.assertEqual(event.notification_status, "sent")

    def test_unrated_inactive_and_unapproved_pet_applications_cannot_be_scheduled(self):
        cases = [
            {"review_priority": 0},
            {"status": BewerbungStatus.DECLINED},
            {"status": BewerbungStatus.BLOCKED},
            {"interest_withdrawn_at": timezone.now()},
            {"haustiere": True},
        ]
        self.unit.pet_review_required = True
        self.unit.pet_review_reason = "Einzelprüfung"
        self.unit.save()
        for overrides in cases:
            with self.subTest(overrides=overrides):
                Bewerbung.objects.filter(pk=self.application.pk).update(
                    review_priority=2,
                    status=BewerbungStatus.OPEN,
                    interest_withdrawn_at=None,
                    haustiere=False,
                )
                Bewerbung.objects.filter(pk=self.application.pk).update(**overrides)
                self.post(self.create_url, self.payload())
                self.assertFalse(ViewingAppointment.objects.exists())

    def test_unconfigured_pet_rule_does_not_block_an_applicant_with_a_pet(self):
        self.application.haustiere = True
        self.application.save(update_fields=("haustiere",))

        appointment = self.schedule()

        self.assertEqual(appointment.status, ViewingAppointment.Status.PLANNED)

    def test_application_above_occupancy_limit_cannot_be_scheduled_by_direct_post(self):
        Bewerbung.objects.filter(pk=self.application.pk).update(personenanzahl=1)
        self.unit.max_occupants = 1
        self.unit.occupancy_requirement_reason = "Grundriss"
        self.unit.save()
        Bewerbung.objects.filter(pk=self.application.pk).update(personenanzahl=2)

        response = self.post(self.create_url, self.payload())

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ViewingAppointment.objects.exists())
        detail = self.client.get(self.detail_url)
        self.assertContains(detail, "Die Personenhöchstzahl der Wohnung wird überschritten")

    def test_low_priority_application_can_be_scheduled(self):
        self.application.review_priority = Bewerbung.Priority.LOW
        self.application.save(update_fields=("review_priority",))

        appointment = self.schedule()

        self.assertEqual(appointment.status, ViewingAppointment.Status.PLANNED)

    def test_current_pet_approval_allows_schedule_but_stale_approval_does_not(self):
        self.unit.pet_review_required = True
        self.unit.pet_review_reason = "Einzelprüfung"
        self.unit.save()
        self.application.haustiere = True
        self.application.save()
        approval = ApplicationReviewEvent.objects.create(
            application=self.application,
            kind="eligibility_approved",
            actor=self.employee,
            requirements_version=self.unit.requirements_version - 1,
            reason="Geprüft",
        )
        self.post(self.create_url, self.payload())
        self.assertFalse(ViewingAppointment.objects.exists())
        approval.requirements_version = self.unit.requirements_version
        approval.save()
        self.schedule()

    def test_duplicate_open_appointment_is_rejected_but_shared_times_are_allowed(self):
        appointment = self.schedule()
        self.post(self.create_url, self.payload(days=2))
        self.assertEqual(ViewingAppointment.objects.count(), 1)
        other_person = Person.objects.create(
            vorname="Andere", nachname="Person", email="other@example.test"
        )
        other = Bewerbung.objects.create(
            person=other_person, wohnung=self.unit, ueber_mich="Test", review_priority=2
        )
        self.post(
            reverse("wohnungsverwaltung:employee_viewing_create", args=[other.pk]), self.payload()
        )
        self.assertEqual(ViewingAppointment.objects.count(), 2)
        self.assertEqual(
            ViewingAppointment.objects.exclude(pk=appointment.pk).get().starts_at,
            appointment.starts_at,
        )

    def test_database_rejects_invalid_time_status_and_multiple_open_appointments(self):
        appointment = self.schedule()
        for updates in ({"ends_at": appointment.starts_at}, {"status": "invalid"}):
            with (
                self.subTest(updates=updates),
                self.assertRaises(IntegrityError),
                transaction.atomic(),
            ):
                ViewingAppointment.objects.filter(pk=appointment.pk).update(**updates)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ViewingAppointment.objects.create(
                application=self.application,
                starts_at=appointment.starts_at,
                ends_at=appointment.ends_at,
            )

    def test_form_rejects_past_reversed_missing_and_dst_ambiguous_times(self):
        for data in (
            self.payload(days=-1),
            self.payload(end_time="09:00"),
            self.payload(end_time=""),
            self.payload(date="2030-03-31", start_time="02:15", end_time="03:30"),
            self.payload(date="2030-10-27", start_time="02:15", end_time="03:30"),
        ):
            with self.subTest(data=data):
                self.assertFalse(ViewingAppointmentForm(data).is_valid())

    def test_edit_form_uses_berlin_times_even_in_another_active_timezone(self):
        appointment = self.schedule()
        with timezone.override("UTC"):
            form = ViewingAppointmentForm(appointment=appointment)
        self.assertEqual(form.initial["start_time"].hour, 10)
        self.assertEqual(form.initial["end_time"].minute, 30)

    def test_form_sets_native_date_limits_for_planning_and_historical_records(self):
        with timezone.override("Europe/Berlin"):
            today = timezone.localdate().isoformat()
            planned = ViewingAppointmentForm()
            record = ViewingAppointmentForm(self.payload(days=-1, action="record"))
        self.assertEqual(planned.fields["date"].widget.attrs["min"], today)
        self.assertNotIn("max", planned.fields["date"].widget.attrs)
        self.assertEqual(record.fields["date"].widget.attrs["max"], today)
        self.assertNotIn("min", record.fields["date"].widget.attrs)
        self.assertEqual(planned.fields["start_time"].widget.attrs["step"], "60")
        self.assertEqual(planned.fields["end_time"].widget.attrs["step"], "60")

    def test_direct_post_cannot_bypass_time_validation(self):
        for data in (self.payload(days=-1), self.payload(end_time="09:00")):
            with self.subTest(data=data):
                response = self.client.post(self.create_url, data)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(ViewingAppointment.objects.exists())
                self.assertFalse(ViewingAppointmentEvent.objects.exists())

    def test_employee_forms_offer_live_validation_for_create_and_reschedule(self):
        response = self.client.get(self.detail_url)
        self.assertContains(response, "data-viewing-time-form", count=1)
        self.assertContains(response, "js/viewing-time-validation.js")
        appointment = self.schedule()
        response = self.client.get(self.detail_url)
        self.assertContains(response, "data-viewing-time-form", count=1)
        self.assertContains(response, f'id="id_viewing_{appointment.pk}_date"')

    def test_applicant_can_confirm_and_decline_without_ending_application(self):
        appointment = self.schedule()
        self.client.force_login(self.user)
        self.post(
            self.response_url(appointment), {"action": "confirm", "version": appointment.version}
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "confirmed")
        self.post(
            self.response_url(appointment), {"action": "decline", "version": appointment.version}
        )
        appointment.refresh_from_db()
        self.application.refresh_from_db()
        self.assertEqual(appointment.status, "applicant_declined")
        self.assertEqual(self.application.status, BewerbungStatus.OPEN)
        self.assertEqual(len(mail.outbox), 1)

    def test_reschedule_resets_confirmation_and_rejects_stale_responses(self):
        appointment = self.schedule()
        old_version = appointment.version
        self.client.force_login(self.user)
        self.post(self.response_url(appointment), {"action": "confirm", "version": old_version})
        appointment.refresh_from_db()
        self.client.force_login(self.employee)
        self.post(
            self.update_url(appointment),
            self.payload(days=2, action="reschedule", version=appointment.version),
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "planned")
        self.assertEqual(len(mail.outbox), 2)
        self.client.force_login(self.user)
        self.post(self.response_url(appointment), {"action": "decline", "version": old_version})
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "planned")

    def test_staff_cancel_requires_reason_and_closed_appointments_cannot_be_reopened(self):
        appointment = self.schedule()
        self.post(
            self.update_url(appointment),
            {"action": "cancel", "version": appointment.version, "reason": " "},
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "planned")
        self.post(
            self.update_url(appointment),
            {"action": "cancel", "version": appointment.version, "reason": "Termin entfällt"},
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "cancelled")
        self.post(
            self.update_url(appointment),
            self.payload(days=3, action="reschedule", version=appointment.version),
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "cancelled")

    def test_results_require_ended_appointment_and_applicant_cannot_respond_after_start(self):
        appointment = self.schedule()
        self.post(
            self.update_url(appointment), {"action": "complete", "version": appointment.version}
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "planned")
        with patch(
            "django.utils.timezone.now", return_value=appointment.ends_at + timedelta(minutes=1)
        ):
            self.client.force_login(self.user)
            self.post(
                self.response_url(appointment),
                {"action": "confirm", "version": appointment.version},
            )
            self.client.force_login(self.employee)
            self.post(
                self.update_url(appointment), {"action": "complete", "version": appointment.version}
            )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "completed")

    def test_historical_record_requires_reason_and_sends_no_invitation(self):
        self.post(self.create_url, self.payload(days=-1, action="record", reason=""))
        self.assertFalse(ViewingAppointment.objects.exists())
        self.post(
            self.create_url,
            self.payload(days=-1, action="record", reason="Vor Einführung besichtigt"),
        )
        appointment = ViewingAppointment.objects.get()
        self.assertEqual(appointment.status, "completed")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(appointment.events.get().actor, self.employee)

    def test_main_unlock_requires_completed_viewing_of_this_application(self):
        url = reverse("wohnungsverwaltung:employee_application_invite", args=[self.application.pk])
        data = {"confirm_positive_decision": "on", "reason": "Positive Entscheidung"}
        self.client.post(url, data)
        self.application.refresh_from_db()
        self.assertFalse(self.application.main_application_unlocked)
        self.post(self.create_url, self.payload(days=-1, action="record", reason="Besichtigt"))
        self.client.post(url, data)
        self.application.refresh_from_db()
        self.assertTrue(self.application.main_application_unlocked)

    def test_existing_main_unlock_remains_accessible_without_viewing(self):
        self.application.main_application_unlocked = True
        self.application.save()
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(
                reverse("wohnungsverwaltung:main_application_status", args=[self.application.pk])
            ).status_code,
            200,
        )

    def test_withdrawal_cancels_open_viewing_without_another_email(self):
        appointment = self.schedule()
        self.application.main_application_unlocked = True
        self.application.save()
        self.client.force_login(self.user)
        self.post(
            reverse("wohnungsverwaltung:application_withdraw", args=[self.application.pk]), {}
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "cancelled")
        self.assertEqual(len(mail.outbox), 1)

    def test_occupancy_decline_cancels_and_notifies_but_keeps_past_records(self):
        appointment = self.schedule()
        with self.captureOnCommitCallbacks(execute=True):
            self.unit.max_occupants = 1
            self.unit.occupancy_requirement_reason = "Grundriss"
            self.unit.save()
        appointment.refresh_from_db()
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, BewerbungStatus.DECLINED)
        self.assertEqual(appointment.status, "cancelled")
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Abgesagt", mail.outbox[-1].body)
        self.assertNotIn("Grundriss", mail.outbox[-1].body)

    def test_mail_failure_keeps_appointment_and_retry_only_sends_current_notice(self):
        with patch("wohnungsverwaltung.viewings.send_mail", side_effect=OSError("smtp down")):
            appointment = self.schedule()
        notice = appointment.events.get(kind="created")
        self.assertEqual(notice.notification_status, "failed")
        resend = reverse(
            "wohnungsverwaltung:employee_viewing_resend", args=[self.application.pk, appointment.pk]
        )
        self.post(resend, {"event": notice.pk})
        notice.refresh_from_db()
        self.assertEqual(notice.notification_status, "sent")
        self.post(
            self.update_url(appointment),
            self.payload(days=2, action="reschedule", version=appointment.version),
        )
        previous_count = len(mail.outbox)
        self.post(resend, {"event": notice.pk})
        self.assertEqual(len(mail.outbox), previous_count)

    def test_applicant_pages_show_only_own_times_and_no_internal_history(self):
        appointment = self.schedule()
        other = get_user_model().objects.create_user(username="other-viewing-applicant")
        other.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        Person.objects.create(
            user=other, vorname="Andere", nachname="Person", email="other@example.test"
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("wohnungsverwaltung:pre_application_list"))
        self.assertContains(response, "Besichtigung")
        self.assertContains(response, "10:30")
        self.assertNotContains(response, "Interne Terminnotiz")
        self.assertIn("no-store", response["Cache-Control"])
        self.client.force_login(other)
        self.assertNotContains(
            self.client.get(reverse("wohnungsverwaltung:pre_application_list")), "10:30"
        )
        self.assertEqual(
            self.client.post(
                self.response_url(appointment), {"action": "confirm", "version": 1}
            ).status_code,
            404,
        )

    def test_actions_require_correct_role_post_csrf_and_application_assignment(self):
        appointment = self.schedule()
        staff_urls = [
            self.create_url,
            self.update_url(appointment),
            reverse(
                "wohnungsverwaltung:employee_viewing_resend",
                args=[self.application.pk, appointment.pk],
            ),
        ]
        for url in staff_urls:
            self.assertEqual(self.client.get(url).status_code, 405)
            secure = Client(enforce_csrf_checks=True)
            secure.force_login(self.employee)
            self.assertEqual(secure.post(url, {}).status_code, 403)
            self.client.force_login(self.user)
            self.assertEqual(self.client.post(url, {}).status_code, 403)
            self.client.force_login(self.employee)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.response_url(appointment)).status_code, 405)
        wrong_url = reverse(
            "wohnungsverwaltung:applicant_viewing_response", args=[uuid4(), appointment.pk]
        )
        self.assertEqual(
            self.client.post(wrong_url, {"action": "confirm", "version": 1}).status_code, 404
        )

    def test_dashboard_displays_and_filters_latest_appointment_without_extra_queries(self):
        appointment = self.schedule()
        params = {"wohnung": self.unit.pk, "viewing_status": "planned"}
        response = self.client.get(self.list_url, params)
        self.assertContains(response, "Geplant")
        self.assertContains(response, "10:30")
        self.assertEqual(
            [item.pk for item in response.context["applications"]], [self.application.pk]
        )
        response = self.client.get(
            self.list_url, {"wohnung": self.unit.pk, "viewing_status": "none"}
        )
        self.assertEqual(list(response.context["applications"]), [])
        with CaptureQueriesContext(connection) as before:
            self.client.get(self.list_url, params)
        self.post(
            self.update_url(appointment),
            {"action": "cancel", "version": appointment.version, "reason": "Termin entfällt"},
        )
        for number in range(5):
            person = Person.objects.create(
                vorname="Test", nachname=str(number), email=f"{number}@example.test"
            )
            app = Bewerbung.objects.create(person=person, wohnung=self.unit, ueber_mich="Test")
            ViewingAppointment.objects.create(
                application=app, starts_at=appointment.starts_at, ends_at=appointment.ends_at
            )
        with CaptureQueriesContext(connection) as after:
            self.client.get(self.list_url, params)
        self.assertEqual(len(before), len(after))

    def test_no_show_and_replacement_preserve_history(self):
        appointment = self.schedule()
        with patch(
            "django.utils.timezone.now", return_value=appointment.ends_at + timedelta(minutes=1)
        ):
            self.post(
                self.update_url(appointment), {"action": "no_show", "version": appointment.version}
            )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "no_show")
        self.post(self.create_url, self.payload(days=2))
        self.assertEqual(ViewingAppointment.objects.count(), 2)
        response = self.client.get(self.detail_url)
        self.assertContains(response, "Nicht erschienen")
        self.assertContains(response, "Geplant")

    def test_stale_staff_changes_cannot_overwrite_applicant_confirmation(self):
        appointment = self.schedule()
        old_version = appointment.version
        self.client.force_login(self.user)
        self.post(self.response_url(appointment), {"action": "confirm", "version": old_version})
        self.client.force_login(self.employee)
        self.post(
            self.update_url(appointment),
            self.payload(days=2, action="reschedule", version=old_version),
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "confirmed")
        self.assertEqual(len(mail.outbox), 1)

    def test_rule_changes_warn_without_cancelling_and_block_rescheduling(self):
        appointment = self.schedule()
        self.application.haustiere = True
        self.application.save()
        self.unit.pet_review_required = True
        self.unit.pet_review_reason = "Neue Tierhaltungsregel"
        self.unit.save()
        response = self.client.get(self.detail_url)
        self.assertContains(response, "Bitte geben Sie zuerst die aktuelle Haustierprüfung frei")
        self.post(
            self.update_url(appointment),
            self.payload(days=2, action="reschedule", version=appointment.version),
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "planned")
        self.assertEqual(len(mail.outbox), 1)

    def test_historical_records_survive_automatic_decline(self):
        self.post(self.create_url, self.payload(days=-1, action="record", reason="Nachgetragen"))
        appointment = ViewingAppointment.objects.get()
        self.unit.max_occupants = 1
        self.unit.occupancy_requirement_reason = "Grundriss"
        self.unit.save()
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "completed")
        self.assertEqual(len(mail.outbox), 0)

    def test_completed_viewing_of_another_application_does_not_allow_main_unlock(self):
        other = Bewerbung.objects.create(
            person=Person.objects.create(
                vorname="Andere", nachname="Person", email="other@example.test"
            ),
            wohnung=self.unit,
            ueber_mich="Test",
        )
        start = timezone.now() - timedelta(days=1)
        ViewingAppointment.objects.create(
            application=other,
            starts_at=start,
            ends_at=start + timedelta(minutes=30),
            status="completed",
        )
        self.client.post(
            reverse("wohnungsverwaltung:employee_application_invite", args=[self.application.pk]),
            {"confirm_positive_decision": "on", "reason": "Geprüft"},
        )
        self.application.refresh_from_db()
        self.assertFalse(self.application.main_application_unlocked)

    def test_appointment_and_notification_are_rolled_back_together(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with transaction.atomic():
                self.client.post(self.create_url, self.payload())
                transaction.set_rollback(True)
        self.assertFalse(ViewingAppointment.objects.exists())
        self.assertFalse(ViewingAppointmentEvent.objects.exists())
        self.assertEqual(callbacks, [])
        self.assertEqual(len(mail.outbox), 0)

    def test_old_invitation_callback_cannot_send_after_cancellation(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.client.post(self.create_url, self.payload())
        appointment = ViewingAppointment.objects.get()
        self.post(
            self.update_url(appointment), {"action": "cancel", "version": 1, "reason": "Entfällt"}
        )
        for callback in callbacks:
            callback()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Abgesagt", mail.outbox[0].body)
        self.assertEqual(appointment.events.get(kind="created").notification_status, "obsolete")

    def test_staff_cannot_mix_application_and_appointment_ids(self):
        appointment = self.schedule()
        other = Bewerbung.objects.create(
            person=Person.objects.create(
                vorname="Andere", nachname="Person", email="other@example.test"
            ),
            wohnung=self.unit,
            ueber_mich="Test",
        )
        for name in ("employee_viewing_update", "employee_viewing_resend"):
            url = reverse(f"wohnungsverwaltung:{name}", args=[other.pk, appointment.pk])
            self.assertEqual(
                self.client.post(
                    url, {"action": "cancel", "version": 1, "reason": "Entfällt"}
                ).status_code,
                404,
            )

    def test_replacement_obsoletes_old_cancellation_notice(self):
        appointment = self.schedule()
        self.post(
            self.update_url(appointment), {"action": "cancel", "version": 1, "reason": "Entfällt"}
        )
        notice = appointment.events.get(kind="status_changed")
        self.post(self.create_url, self.payload(days=2))
        previous_count = len(mail.outbox)
        self.post(
            reverse(
                "wohnungsverwaltung:employee_viewing_resend",
                args=[self.application.pk, appointment.pk],
            ),
            {"event": notice.pk},
        )
        self.assertEqual(len(mail.outbox), previous_count)

    def test_read_pages_do_not_load_proof_files_and_applicant_response_requires_csrf(self):
        appointment = self.schedule()
        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.detail_url)
        self.assertFalse(any('FROM "application_proof"' in item["sql"] for item in queries))
        self.client.force_login(self.user)
        with CaptureQueriesContext(connection) as queries:
            self.client.get(reverse("wohnungsverwaltung:pre_application_list"))
        self.assertFalse(any('FROM "viewing_appointment_event"' in item["sql"] for item in queries))
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.user)
        self.assertEqual(
            secure.post(
                self.response_url(appointment), {"action": "confirm", "version": 1}
            ).status_code,
            403,
        )


class ConcurrentViewingTests(TransactionTestCase):
    setUp = ViewingTests.setUp
    payload = ViewingTests.payload

    def test_concurrent_scheduling_creates_only_one_open_appointment(self):
        barrier = Barrier(2)

        def schedule():
            try:
                client = Client()
                client.force_login(get_user_model().objects.get(pk=self.employee.pk))
                barrier.wait(timeout=10)
                return client.post(self.create_url, self.payload()).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: schedule(), range(2)))
        self.assertEqual(responses, [302, 302])
        self.assertEqual(ViewingAppointment.objects.count(), 1)
        self.assertEqual(ViewingAppointmentEvent.objects.filter(kind="created").count(), 1)
