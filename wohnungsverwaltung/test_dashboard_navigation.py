"""Dashboard links keep staff in the existing application and handover workflows."""

from datetime import timedelta
from html.parser import HTMLParser
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import test_employee_dashboard as fixtures
from .models import Protokoll, ViewingAppointment, Wohnung


class Links(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.hrefs = []
        self.feed(response.content.decode())

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.append(dict(attrs).get("href", ""))


class DashboardNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = get_user_model().objects.create_user(username="dashboard-navigation")
        cls.employee.groups.add(Group.objects.get(name="Mitarbeiter"))
        cls.unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="1")
        cls.other = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="2")
        cls.empty = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="3")

    def setUp(self):
        self.client.force_login(self.employee)
        self.now = timezone.now()
        self.clock = patch("wohnungsverwaltung.dashboard.timezone.now", return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.dashboard = reverse("verwaltung:dashboard")
        self.applications = reverse("wohnungsverwaltung:employee_application_list")

    def application(self, unit=None, **values):
        return fixtures.EmployeeDashboardTests.create_application(unit or self.unit, **values)

    def viewing(self, application, *, status="planned", days=2):
        start = self.now + timedelta(days=days)
        return ViewingAppointment.objects.create(
            application=application,
            starts_at=start,
            ends_at=start + timedelta(minutes=30),
            status=status,
        )

    def test_kpi_links_target_existing_workspaces_and_inline_calendar(self):
        response = self.client.get(self.dashboard)
        metrics = {metric["section"]: metric["href"] for metric in response.context["metrics"]}
        for key, workflow in (("bewerbungen", "open"), ("rueckmeldungen", "waiting")):
            self.assertEqual(urlsplit(metrics[key]).path, self.applications)
            self.assertEqual(
                parse_qs(urlsplit(metrics[key]).query), {"workflow": [workflow], "segment": ["all"]}
            )
        self.assertEqual(
            metrics["uebergaben"],
            reverse("wohnungsverwaltung:handover_protocol_list") + "?status=open",
        )
        self.assertEqual(metrics["termine"], self.dashboard + "#dashboard-calendar-title")
        self.assertContains(response, 'href="' + self.dashboard + '#dashboard-calendar-title"')

    def test_open_counts_follow_unit_selection_and_include_suitability_exceptions(self):
        first = self.application(haustiere=True)
        second = self.application(self.other)
        self.application(status="declined")
        self.application(status="blocked")
        self.application(interest_withdrawn_at=self.now)
        Wohnung.objects.filter(pk=self.unit.pk).update(pet_review_required=True)
        response = self.client.get(self.applications, {"workflow": "open", "segment": "all"})
        self.assertEqual(
            {unit.pk: unit.application_count for unit in response.context["units"]},
            {self.unit.pk: 1, self.other.pk: 1},
        )
        links = [
            link
            for link in Links(response).hrefs
            if parse_qs(urlsplit(link).query).get("wohnung") == [str(self.unit.pk)]
        ]
        self.assertEqual(len(links), 1)
        self.assertEqual(parse_qs(urlsplit(links[0]).query)["workflow"], ["open"])
        selected = self.client.get(self.applications + links[0])
        self.assertEqual(list(selected.context["applications"]), [first])
        self.assertEqual(selected.context["segment"], "all")
        self.assertIn(self.applications + "?workflow=open", Links(selected).hrefs)
        self.assertNotContains(selected, str(second.pk))

    def test_waiting_filter_matches_kpi_and_displays_both_reasons_once(self):
        both = self.application(main_application_unlocked=True)
        self.viewing(both, days=20)
        confirmation = self.application(self.other, submitted_at=self.now)
        self.viewing(confirmation)
        self.viewing(self.application(), status="confirmed")
        self.viewing(self.application(), days=-2)
        self.application(main_application_unlocked=True, submitted_at=self.now)
        self.viewing(self.application(status="declined"))
        overview = self.client.get(self.dashboard)
        response = self.client.get(self.applications, {"workflow": "waiting"})
        self.assertEqual(
            sum(unit.application_count for unit in response.context["units"]),
            overview.context["counts"]["waiting"],
        )
        self.assertEqual(overview.context["counts"]["waiting"], 2)
        response = self.client.get(
            self.applications, {"workflow": "waiting", "wohnung": self.unit.pk}
        )
        self.assertEqual(list(response.context["applications"]), [both])
        self.assertContains(response, "Warten auf Hauptbewerbung")
        self.assertContains(response, "Warten auf Terminbestätigung")
        response = self.client.get(
            self.applications, {"workflow": "waiting", "wohnung": self.other.pk}
        )
        self.assertEqual(list(response.context["applications"]), [confirmation])
        self.assertNotContains(response, "Warten auf Hauptbewerbung")

    def test_workflow_persists_in_pagination_and_can_be_removed(self):
        for _ in range(21):
            self.application(main_application_unlocked=True)
        response = self.client.get(
            self.applications, {"workflow": "waiting", "wohnung": self.unit.pk}
        )
        self.assertEqual(response.context["page_obj"].paginator.count, 21)
        pages = [
            link
            for link in Links(response).hrefs
            if parse_qs(urlsplit(link).query).get("page") == ["2"]
        ]
        self.assertEqual(len(pages), 1)
        self.assertEqual(parse_qs(urlsplit(pages[0]).query)["workflow"], ["waiting"])
        next_page = self.client.get(self.applications + pages[0])
        self.assertEqual(len(next_page.context["applications"]), 1)
        workflow_chip = next(
            item for item in response.context["active_filters"] if item["name"] == "workflow"
        )
        self.assertNotIn("workflow", parse_qs(urlsplit(workflow_chip["remove_url"]).query))

    def test_protocol_link_with_zero_open_protocols_does_not_show_closed_ones(self):
        application = self.application()
        Protokoll.objects.create(
            wohnung=self.unit,
            person=application.person,
            status="signed",
            protokoll_typ="move_in",
            uebergabe_status="renovated",
            abnahme_status="accepted",
        )
        response = self.client.get(
            reverse("wohnungsverwaltung:handover_protocol_list"), {"status": "open"}
        )
        self.assertTrue(response.context["filters"].is_valid())
        self.assertEqual(list(response.context["protocols"]), [])

    def test_legacy_dashboard_lists_redirect_to_the_existing_workspaces(self):
        for section, path, query in (
            ("bewerbungen", self.applications, {"workflow": ["open"], "segment": ["all"]}),
            ("rueckmeldungen", self.applications, {"workflow": ["waiting"], "segment": ["all"]}),
            (
                "uebergaben",
                reverse("wohnungsverwaltung:handover_protocol_list"),
                {"status": ["open"]},
            ),
        ):
            response = self.client.get(self.dashboard, {"bereich": section})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(urlsplit(response.url).path, path)
            self.assertEqual(parse_qs(urlsplit(response.url).query), query)

    def test_invalid_workflow_does_not_crash_or_hide_validation_feedback(self):
        self.application()
        response = self.client.get(self.applications, {"workflow": "unknown"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("workflow", response.context["filters"].errors)

    def test_application_filters_still_require_employee_access(self):
        applicant = get_user_model().objects.create_user(username="navigation-applicant")
        applicant.groups.add(Group.objects.get(name="Bewerber"))
        self.client.force_login(applicant)
        for workflow in ("open", "waiting"):
            self.assertEqual(
                self.client.get(self.applications, {"workflow": workflow}).status_code, 403
            )
