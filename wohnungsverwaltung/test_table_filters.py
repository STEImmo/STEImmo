from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from . import test_employee_dashboard
from .access import ROLE_APPLICANT, ROLE_EMPLOYEE
from .models import Stellplatz, StellplatzTyp, StellplatzZuordnung, Wohnung, WohnungStatus


class FilterMarkupParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = {}
        self.form_depth = 0
        self.nested_form = False
        self.forms = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "a" and "data-remove-filter" in attrs:
            self.links[attrs["data-remove-filter"]] = attrs["href"]
        if tag == "form":
            self.forms.append({})
            self.nested_form |= self.form_depth > 0
            self.form_depth += 1
        if self.form_depth and tag in {"input", "select"} and "name" in attrs:
            self.forms[-1][attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.form_depth -= 1


class TableFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = get_user_model().objects.create_user(username="filter-employee")
        cls.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        cls.applicant = get_user_model().objects.create_user(username="filter-applicant")
        cls.applicant.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        cls.free = Wohnung.objects.create(wohnungsnummer="01", etage=0, zimmeranzahl="1.50")
        cls.upstairs = Wohnung.objects.create(wohnungsnummer="02", etage=2, zimmeranzahl="2.00")
        cls.taken = Wohnung.objects.create(
            wohnungsnummer="03", etage=2, zimmeranzahl="3.00", status=WohnungStatus.TAKEN
        )
        cls.car = Stellplatz.objects.create(name="A", stellplatz_typ=StellplatzTyp.CAR)
        cls.assigned_car = Stellplatz.objects.create(name="B", stellplatz_typ=StellplatzTyp.CAR)
        cls.bike = Stellplatz.objects.create(name="C", stellplatz_typ=StellplatzTyp.BIKE)
        StellplatzZuordnung.objects.create(stellplatz=cls.assigned_car, wohnung=cls.free)
        cls.application = test_employee_dashboard.EmployeeDashboardTests.create_application(
            cls.free
        )
        cls.unit_url = reverse("verwaltung:wohnung_list")
        cls.parking_url = reverse("verwaltung:stellplatz_list")
        cls.application_url = reverse("wohnungsverwaltung:employee_application_list")

    def setUp(self):
        self.client.force_login(self.employee)

    def test_apartment_filters_combine_status_and_floor_including_ground_floor(self):
        for params, expected in (
            ({"status": "free", "floor": "2"}, [self.upstairs]),
            ({"floor": "0"}, [self.free]),
            ({"status": "taken"}, [self.taken]),
        ):
            with self.subTest(params=params):
                response = self.client.get(self.unit_url, params)
                self.assertEqual(list(response.context["wohnungen"]), expected)

    def test_invalid_apartment_filter_keeps_other_valid_criteria(self):
        for params, expected in (
            ({"status": "invalid", "floor": "2"}, [self.upstairs, self.taken]),
            ({"status": "taken", "floor": "999"}, [self.taken]),
            ({"status": "taken", "floor": "no", "unknown": "x"}, [self.taken]),
        ):
            with self.subTest(params=params):
                response = self.client.get(self.unit_url, params)
                self.assertEqual(list(response.context["wohnungen"]), expected)
                self.assertTrue(response.context["filters"].errors)
                self.assertContains(response, "Filter enthalten ungültige Angaben")

    def test_parking_filters_use_assignment_and_type(self):
        for params, expected in (
            ({"assignment": "unassigned", "type": "car"}, [self.car]),
            ({"assignment": "assigned", "type": "car"}, [self.assigned_car]),
            ({"assignment": "unassigned", "type": "bike"}, [self.bike]),
            ({"assignment": "bad", "type": "bike"}, [self.bike]),
        ):
            with self.subTest(params=params):
                response = self.client.get(self.parking_url, params)
                self.assertEqual(list(response.context["stellplaetze"]), expected)

    def test_empty_results_keep_table_filters_and_reset_available(self):
        response = self.client.get(self.unit_url, {"status": "taken", "floor": "0"})
        self.assertContains(response, "Keine Wohnungen für diese Filterauswahl")
        self.assertContains(response, "Alle Filter zurücksetzen")
        self.assertContains(response, "Etage filtern")
        self.assertNotContains(response, "Noch keine Wohnungen angelegt")

    def test_active_filters_are_shown_above_without_active_badge_on_filter_buttons(self):
        response = self.client.get(self.unit_url, {"status": "free"})
        self.assertContains(response, 'data-remove-filter="status"')
        self.assertContains(response, "Verfügbarkeitsstatus: Verfügbar")
        self.assertNotContains(response, ">Aktiv</span>")
        self.assertNotContains(response, "table-filter-active")

    def test_application_unit_list_filters_by_floor_and_room_count(self):
        response = self.client.get(self.application_url, {"floor": "2", "rooms": "2.00"})
        self.assertEqual(list(response.context["units"]), [self.upstairs])
        self.assertContains(response, "Etage: Etage 2")
        self.assertContains(response, "Zimmeranzahl: 2 Zimmer")

    def test_application_unit_list_sorts_by_application_count_in_both_directions(self):
        test_employee_dashboard.EmployeeDashboardTests.create_application(self.upstairs)
        for params, expected in (
            ({}, [self.free, self.upstairs, self.taken]),
            ({"application_sort": "asc"}, [self.taken, self.free, self.upstairs]),
            ({"application_sort": "desc"}, [self.free, self.upstairs, self.taken]),
        ):
            with self.subTest(params=params):
                response = self.client.get(self.application_url, params)
                self.assertEqual(list(response.context["units"]), expected)

    def test_invalid_application_unit_filter_keeps_other_valid_criteria(self):
        response = self.client.get(self.application_url, {"floor": "2", "rooms": "invalid"})
        self.assertEqual(list(response.context["units"]), [self.upstairs, self.taken])
        self.assertIn("rooms", response.context["filters"].errors)
        self.assertContains(response, "Filter enthalten ungültige Angaben")

    def test_application_unit_filter_reset_links_preserve_other_filters(self):
        response = self.client.get(
            self.application_url,
            {
                "floor": "2",
                "rooms": "2.00",
                "application_sort": "asc",
                "page": "3",
                "unknown": "ignored",
            },
        )
        parser = FilterMarkupParser()
        parser.feed(response.content.decode())
        self.assertEqual(
            parse_qs(urlsplit(parser.links["floor"]).query),
            {"rooms": ["2.00"], "application_sort": ["asc"]},
        )
        self.assertEqual(
            parse_qs(urlsplit(parser.links["rooms"]).query),
            {"floor": ["2"], "application_sort": ["asc"]},
        )
        self.assertEqual(
            parse_qs(urlsplit(parser.links["application_sort"]).query),
            {"floor": ["2"], "rooms": ["2.00"]},
        )
        self.assertEqual(
            parse_qs(urlsplit(unescape(response.context["reset_filters_url"])).query), {}
        )

    def test_empty_application_unit_filter_results_keep_reset_visible(self):
        response = self.client.get(self.application_url, {"floor": "0", "rooms": "3.00"})
        self.assertContains(response, "Keine Wohnungen für diese Filterauswahl")
        self.assertContains(response, "Alle Filter zurücksetzen")
        self.assertContains(response, "Wohnung filtern")
        self.assertNotContains(response, "Es sind noch keine Wohnungen angelegt")

    def test_individual_reset_preserves_other_filters_and_removes_page(self):
        response = self.client.get(
            self.unit_url, {"status": "free", "floor": "2", "page": "3", "unknown": "x"}
        )
        parser = FilterMarkupParser()
        parser.feed(response.content.decode())
        self.assertEqual(parse_qs(urlsplit(parser.links["status"]).query), {"floor": ["2"]})
        self.assertEqual(parse_qs(urlsplit(parser.links["floor"]).query), {"status": ["free"]})

    def test_dropdown_forms_have_unique_ids_no_nesting_and_mobile_controls(self):
        for url, params in (
            (self.unit_url, {}),
            (self.parking_url, {}),
            (self.application_url, {}),
            (self.application_url, {"wohnung": self.free.pk}),
        ):
            with self.subTest(url=url):
                response = self.client.get(url, params)
                parser = FilterMarkupParser()
                parser.feed(response.content.decode())
                self.assertFalse(parser.nested_form)
                self.assertEqual(len(parser.ids), len(set(parser.ids)))
                self.assertContains(response, "table-filters-mobile")
                self.assertContains(response, "mode: click")

    def test_application_reset_preserves_context_and_sorting(self):
        response = self.client.get(
            self.application_url,
            {
                "wohnung": self.free.pk,
                "segment": "all",
                "sort": "priority",
                "q": "Berta",
                "people": "2",
                "page": "2",
                "unknown": "x",
            },
        )
        parser = FilterMarkupParser()
        parser.feed(response.content.decode())
        self.assertEqual(
            parse_qs(urlsplit(parser.links["people"]).query),
            {
                "wohnung": [str(self.free.pk)],
                "segment": ["all"],
                "sort": ["priority"],
                "q": ["Berta"],
            },
        )
        self.assertEqual(
            parse_qs(urlsplit(unescape(response.context["reset_filters_url"])).query),
            {
                "wohnung": [str(self.free.pk)],
                "segment": ["all"],
                "sort": ["priority"],
            },
        )

    def test_contradictory_application_filters_explain_empty_result_without_mutation(self):
        response = self.client.get(
            self.application_url,
            {
                "wohnung": self.free.pk,
                "segment": "matching",
                "status": "declined",
            },
        )
        self.assertContains(response, "Alle Bewerbungen")
        self.assertContains(response, "aktuelle Ansicht")
        self.assertContains(response, "Anforderungen offen")
        self.assertEqual(response.context["segment"], "matching")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "open")
        self.assertFalse(self.application.review_events.exists())

    def test_filters_do_not_grant_access_to_applicants(self):
        self.client.force_login(self.applicant)
        for url in (self.unit_url, self.parking_url, self.application_url):
            self.assertEqual(self.client.get(url, {"status": "free"}).status_code, 403)

    def test_dropdown_submission_preserves_other_filters_without_page_or_unknown_parameters(self):
        response = self.client.get(
            self.unit_url,
            {
                "status": "free",
                "floor": "2",
                "page": "3",
                "unknown": "ignored",
            },
        )
        parser = FilterMarkupParser()
        parser.feed(response.content.decode())
        filter_forms = [form for form in parser.forms if "floor" in form or "status" in form]
        self.assertEqual(len(filter_forms), 4)
        for form in filter_forms:
            self.assertEqual(set(form), {"status", "floor"})
        self.assertTrue(any(form["floor"] == "2" for form in filter_forms))
        self.assertTrue(any(form["status"] == "free" for form in filter_forms))

    def test_empty_inventory_is_distinguished_from_filtered_results(self):
        Stellplatz.objects.all().delete()
        response = self.client.get(self.parking_url, {"assignment": "assigned"})
        self.assertContains(response, "Noch keine Stellplätze angelegt.")
        self.assertNotContains(response, "Keine Stellplätze für diese Filterauswahl")
        self.assertContains(response, "Zuordnung filtern")

    def test_invalid_application_dates_leave_valid_people_filter_effective(self):
        for dates, error_field in (
            ({"created_from": "invalid"}, "created_from"),
            ({"created_from": "2000-01-02", "created_to": "2000-01-01"}, "created_to"),
        ):
            with self.subTest(dates=dates):
                response = self.client.get(
                    self.application_url,
                    {
                        "wohnung": self.free.pk,
                        "segment": "all",
                        "people": "2",
                        **dates,
                    },
                )
                self.assertIn(error_field, response.context["filters"].errors)
                self.assertEqual(list(response.context["applications"]), [self.application])
                self.assertContains(response, "Filter enthalten ungültige Angaben")
                self.assertContains(response, "Personenanzahl: 2")

    def test_filter_urls_require_login(self):
        self.client.logout()
        for url in (self.unit_url, self.parking_url, self.application_url):
            response = self.client.get(url, {"status": "free"})
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(reverse("login") + "?next="))
