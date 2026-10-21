"""Observable dashboard behaviour for issue #147."""

from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .access import ROLE_APPLICANT, ROLE_EMPLOYEE, ROLE_TENANT, ROLE_USER_MANAGEMENT
from .models import (
    AbnahmeStatus,
    ApplicationReviewEvent,
    Bewerbung,
    Person,
    Protokoll,
    ProtokollTyp,
    UebergabeStatus,
    ViewingAppointment,
    Wohnung,
)

BERLIN = ZoneInfo("Europe/Berlin")


class ManagementDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = get_user_model().objects.create_user(username="overview-employee")
        cls.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        cls.unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="1")

    def setUp(self):
        self.client.force_login(self.employee)
        self.now = datetime(2026, 10, 21, 12, tzinfo=BERLIN)
        self.clock = patch("wohnungsverwaltung.dashboard.timezone.now", return_value=self.now)
        self.url = "/verwaltung/"

    def application(self, **values):
        person = Person.objects.create(
            vorname="Test", nachname="Person", email=f"{uuid4()}@example.test"
        )
        return Bewerbung.objects.create(
            person=person, wohnung=self.unit, ueber_mich="Test", **values
        )

    def viewing(self, application, *, start=None, status="planned"):
        start = start or self.now + timedelta(days=1)
        return ViewingAppointment.objects.create(
            application=application,
            starts_at=start,
            ends_at=start + timedelta(minutes=30),
            status=status,
        )

    def get(self, **query):
        with self.clock:
            return self.client.get(self.url, query)

    def test_dashboard_is_registered_and_requires_employee_permission(self):
        self.assertEqual(reverse("verwaltung:dashboard"), self.url)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        for role, allowed in (
            (ROLE_APPLICANT, False),
            (ROLE_TENANT, False),
            (ROLE_USER_MANAGEMENT, True),
        ):
            user = get_user_model().objects.create_user(username=role)
            user.groups.add(Group.objects.get(name=role))
            self.client.force_login(user)
            self.assertEqual(self.get().status_code, 200 if allowed else 403)
        user = get_user_model().objects.create_user(username="direct", is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.get().status_code, 403)
        user.user_permissions.add(Permission.objects.get(codename="access_employee_area"))
        self.assertEqual(self.get().status_code, 200)
        manager_only = get_user_model().objects.create_user(username="accounts-only")
        manager_only.user_permissions.add(Permission.objects.get(codename="manage_user_accounts"))
        self.client.force_login(manager_only)
        self.assertEqual(self.get().status_code, 403)

    def test_empty_dashboard_explains_zero_counts_and_rejects_post(self):
        response = self.get()
        self.assertEqual(
            response.context["counts"],
            {
                "applications": 0,
                "appointments": 0,
                "waiting": 0,
                "handovers": 0,
            },
        )
        self.assertContains(response, "Aktuell keine Aufgaben")
        self.assertContains(response, "Keine ausstehenden Rückmeldungen")
        self.assertContains(response, "Keine Besichtigungen", count=7)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn("private", response.headers["Cache-Control"])
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_inactive_applications_and_their_appointments_are_excluded(self):
        self.application()
        for values in (
            {"status": "declined"},
            {"status": "blocked"},
            {"interest_withdrawn_at": self.now},
        ):
            self.viewing(self.application(**values))
        response = self.get()
        self.assertEqual(response.context["counts"]["applications"], 1)
        self.assertEqual(response.context["counts"]["appointments"], 0)

    def test_next_steps_follow_workflow_and_do_not_duplicate_applications(self):
        review = self.application()
        schedule = self.application(review_priority=2)
        unlock = self.application()
        self.viewing(unlock, start=self.now - timedelta(days=1), status="completed")
        result = self.application()
        self.viewing(result, start=self.now - timedelta(hours=1))
        decision = self.application(submitted_at=self.now)
        waiting = self.application(main_application_unlocked=True)
        confirmed = self.application()
        self.viewing(confirmed, status="confirmed")
        response = self.get(bereich="aufgaben")
        entries = {entry["id"]: entry["label"] for entry in response.context["entries"]}
        self.assertEqual(
            entries,
            {
                review.pk: "Bewerbung bewerten",
                schedule.pk: "Besichtigung planen",
                unlock.pk: "Freischaltung der Hauptbewerbung prüfen",
                result.pk: "Besichtigungsergebnis nachtragen",
                decision.pk: "Hauptbewerbung prüfen und final entscheiden",
            },
        )
        self.assertNotIn(waiting.pk, entries)
        self.assertEqual(
            [entry["id"] for entry in response.context["entries"]][:2], [result.pk, decision.pk]
        )

    def test_current_pet_approval_and_occupancy_are_respected(self):
        Wohnung.objects.filter(pk=self.unit.pk).update(pet_review_required=True, max_occupants=2)
        pet = self.application(haustiere=True, review_priority=2)
        occupancy = self.application(personenanzahl=3, review_priority=2)
        response = self.get(bereich="aufgaben")
        self.assertContains(response, "Tierhaltung muss geprüft werden")
        self.assertContains(response, "Personenhöchstzahl")
        ApplicationReviewEvent.objects.create(
            application=pet, kind="eligibility_approved", requirements_version=1
        )
        response = self.get(bereich="aufgaben")
        entries = {entry["id"]: entry["label"] for entry in response.context["entries"]}
        self.assertEqual(entries[pet.pk], "Besichtigung planen")
        self.assertEqual(entries[occupancy.pk], "Auswahlvoraussetzungen prüfen")
        Wohnung.objects.filter(pk=self.unit.pk).update(requirements_version=2)
        self.assertContains(self.get(bereich="aufgaben"), "Tierhaltung muss geprüft werden")

    def test_waiting_counts_applications_once_and_has_no_seven_day_limit(self):
        both = self.application(main_application_unlocked=True)
        self.viewing(both, start=self.now + timedelta(days=20))
        self.viewing(self.application(), start=self.now + timedelta(days=15))
        self.viewing(self.application(), status="confirmed")
        self.viewing(self.application(), start=self.now - timedelta(minutes=10))
        self.viewing(self.application(main_application_unlocked=True, submitted_at=self.now))
        response = self.get(bereich="rueckmeldungen")
        self.assertEqual(response.context["counts"]["waiting"], 3)
        self.assertEqual(response.context["page_obj"].paginator.count, 3)

    def test_open_protocols_are_tasks_but_signed_and_blocked_protocols_are_not(self):
        application = self.application(main_application_unlocked=True)
        for status in ("open", "signed", "blocked"):
            Protokoll.objects.create(
                wohnung=self.unit,
                person=application.person,
                protokoll_typ=ProtokollTyp.MOVE_IN,
                status=status,
                uebergabe_status=UebergabeStatus.RENOVATED,
                abnahme_status=AbnahmeStatus.ACCEPTED,
            )
        response = self.get(bereich="aufgaben")
        self.assertEqual(response.context["counts"]["handovers"], 1)
        self.assertEqual(
            [entry["label"] for entry in response.context["entries"]],
            ["Übergabeprotokoll fortsetzen"],
        )

    def test_calendar_keeps_simultaneous_and_running_appointments_and_limits_preview(self):
        appointments = [
            self.viewing(self.application(), start=self.now - timedelta(minutes=10))
            for _ in range(4)
        ]
        self.viewing(self.application(), status="cancelled")
        self.viewing(self.application(), status="completed")
        self.viewing(self.application(), start=self.now - timedelta(hours=1))
        response = self.get()
        today = next(day for day in response.context["calendar_days"] if day["is_today"])
        self.assertEqual(today["count"], 4)
        self.assertEqual(len(today["entries"]), 3)
        self.assertContains(response, "Alle 4 Termine")
        day_list = self.get(bereich="termine", datum=self.now.date().isoformat())
        self.assertEqual(
            {entry["id"] for entry in day_list.context["entries"]},
            {appointment.pk for appointment in appointments},
        )

    def test_calendar_navigation_does_not_change_fixed_metric_period(self):
        self.viewing(self.application(), start=datetime(2026, 10, 28, 23, 30, tzinfo=BERLIN))
        self.viewing(self.application(), start=datetime(2026, 10, 29, 0, tzinfo=BERLIN))
        response = self.get(woche="2026-10-28")
        self.assertEqual(response.context["week_start"].isoformat(), "2026-10-26")
        self.assertEqual(response.context["counts"]["appointments"], 1)
        self.assertEqual(self.get(bereich="termine").context["page_obj"].paginator.count, 1)

    def test_invalid_extreme_and_past_week_parameters_fall_back_safely(self):
        for value in ("invalid", "2026-02-30", "9999-12-31", "0001-01-01", "2026-10-01"):
            with self.subTest(value=value):
                response = self.get(woche=value, datum=value, bereich="termine")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["week_start"].isoformat(), "2026-10-19")

    def test_calendar_uses_berlin_day_boundaries_across_dst_and_year_change(self):
        for now in (
            datetime(2026, 10, 24, 12, tzinfo=BERLIN),
            datetime(2026, 12, 31, 12, tzinfo=BERLIN),
        ):
            self.now = now
            with patch("wohnungsverwaltung.dashboard.timezone.now", return_value=now):
                self.client.force_login(self.employee)
                appointment = self.viewing(self.application(), start=now + timedelta(days=2))
                response = self.client.get(self.url)
                self.assertEqual(response.context["counts"]["appointments"], 1)
                response = self.client.get(
                    self.url,
                    {"bereich": "termine", "datum": appointment.starts_at.date().isoformat()},
                )
                self.assertEqual(response.context["page_obj"].paginator.count, 1)
            ViewingAppointment.objects.all().delete()

    def test_lists_paginate_and_preview_is_bounded(self):
        for _ in range(21):
            self.application()
        response = self.get()
        self.assertEqual(len(response.context["task_entries"]), 5)
        response = self.get(bereich="bewerbungen", page=2)
        self.assertEqual(len(response.context["entries"]), 1)
        self.assertEqual(response.context["page_obj"].paginator.count, 21)

    def test_query_count_does_not_grow_with_calendar_or_task_rows(self):
        self.viewing(self.application())
        self.application()
        with CaptureQueriesContext(connection) as small:
            self.get()
        for _ in range(8):
            self.viewing(self.application())
            self.application()
        with CaptureQueriesContext(connection) as large:
            self.get()
        self.assertEqual(len(small), len(large))

    def test_completed_action_moves_application_to_next_task(self):
        application = self.application()
        self.assertContains(self.get(), "Bewerbung bewerten")
        self.client.post(
            reverse(
                "wohnungsverwaltung:employee_application_priority_update", args=[application.pk]
            ),
            {"priority": "2", "reason": "Geprüft"},
        )
        self.assertNotContains(self.get(), "Bewerbung bewerten")
        self.assertContains(self.get(), "Besichtigung planen")

    def test_exact_start_and_end_boundaries_move_between_waiting_running_and_result(self):
        application = self.application()
        appointment = self.viewing(application, start=self.now)
        response = self.get()
        self.assertEqual(response.context["counts"]["waiting"], 0)
        self.assertEqual(response.context["counts"]["appointments"], 1)
        self.assertEqual(response.context["task_count"], 0)
        ViewingAppointment.objects.filter(pk=appointment.pk).update(
            starts_at=self.now - timedelta(minutes=30), ends_at=self.now
        )
        response = self.get()
        self.assertEqual(response.context["counts"]["appointments"], 0)
        self.assertEqual(response.context["task_count"], 1)
        self.assertContains(response, "Besichtigungsergebnis nachtragen")

    def test_pagination_keeps_day_and_section_and_detail_links_are_reachable(self):
        appointments = [self.viewing(self.application()) for _ in range(21)]
        day = appointments[0].starts_at.date().isoformat()
        response = self.get(bereich="termine", datum=day, page=2)
        self.assertEqual(len(response.context["entries"]), 1)
        self.assertContains(response, "bereich=termine&amp;datum=" + day + "&amp;page=1")
        entry = response.context["entries"][0]
        self.assertEqual(self.client.get(entry["url"]).status_code, 200)

    def test_permission_revocation_denies_counts_and_all_list_modes(self):
        self.employee.groups.clear()
        for section in ("", "bewerbungen", "aufgaben", "termine", "rueckmeldungen", "uebergaben"):
            self.assertEqual(self.get(bereich=section).status_code, 403)

    def test_next_week_day_list_is_not_limited_by_the_metric_horizon(self):
        appointment = self.viewing(self.application(), start=self.now + timedelta(days=15))
        day = appointment.starts_at.date().isoformat()
        response = self.get(bereich="termine", datum=day)
        self.assertEqual(response.context["counts"]["appointments"], 0)
        self.assertEqual([entry["id"] for entry in response.context["entries"]], [appointment.pk])

    def test_calendar_links_stop_at_current_week_and_highlight_today(self):
        response = self.get()
        self.assertIsNone(response.context["previous_week"])
        self.assertContains(response, 'aria-current="date"', count=1)
        self.assertContains(response, "?woche=2026-10-26")
        response = self.get(woche="2026-10-26")
        self.assertContains(response, "?woche=2026-10-19")
        self.assertNotContains(response, 'aria-current="date"')

    @override_settings(TIME_ZONE="UTC")
    def test_calendar_groups_berlin_dates_across_the_clock_change_independent_of_server_timezone(
        self,
    ):
        now = datetime(2026, 10, 24, 12, tzinfo=BERLIN)
        appointments = [
            self.viewing(self.application(), start=datetime(2026, 10, 25, hour, 15, tzinfo=BERLIN))
            for hour in (0, 3)
        ]
        with patch("wohnungsverwaltung.dashboard.timezone.now", return_value=now):
            response = self.client.get(self.url)
            sunday = response.context["calendar_days"][-1]
            self.assertEqual(sunday["date"].isoformat(), "2026-10-25")
            self.assertEqual(sunday["count"], 2)
            self.assertEqual(
                {entry["id"] for entry in sunday["entries"]},
                {appointment.pk for appointment in appointments},
            )
