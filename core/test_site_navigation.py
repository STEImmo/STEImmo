"""Response tests for the shared page frame in issue #46."""

from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase
from django.urls import reverse

from wohnungsverwaltung.access import ROLE_APPLICANT, ROLE_TENANT


class NavigationParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.navigation = {}
        self.current_navigation = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "nav":
            self.current_navigation = attrs.get("aria-label")
            self.navigation[self.current_navigation] = []
        elif tag == "a" and self.current_navigation is not None:
            self.navigation[self.current_navigation].append(
                (attrs.get("href"), attrs.get("aria-current"))
            )

    def handle_endtag(self, tag):
        if tag == "nav":
            self.current_navigation = None


class SiteNavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.resident = get_user_model().objects.create_user(username="resident@example.test")
        cls.resident.groups.add(
            Group.objects.get(name=ROLE_APPLICANT), Group.objects.get(name=ROLE_TENANT)
        )
        cls.manager = get_user_model().objects.create_user(username="manager@example.test")
        cls.manager.user_permissions.add(
            Permission.objects.get(codename="access_employee_area"),
            Permission.objects.get(codename="manage_user_accounts"),
        )

    def parse_navigation(self, response):
        parser = NavigationParser()
        parser.feed(response.content.decode())
        return {
            label: links
            for label, links in parser.navigation.items()
            if label in ("Hauptnavigation", "Mobile Hauptnavigation", "Footernavigation")
        }

    def assert_navigation_destinations(self, response, names):
        navigation = self.parse_navigation(response)
        expected = [reverse(name) for name in names]
        for label in ("Hauptnavigation", "Mobile Hauptnavigation", "Footernavigation"):
            with self.subTest(navigation=label):
                self.assertIn(label, navigation)
                self.assertEqual([href for href, _ in navigation[label]], expected)

    def test_public_pages_use_the_company_name_instead_of_the_project_nickname(self):
        for name in ("home", "login", "wohnungsverwaltung:pre_application_preview"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, "STE Immobilien eGbR")
                self.assertNotContains(response, "STEImmo")

    def test_guest_navigation_keeps_public_links_in_all_three_locations(self):
        response = self.client.get(reverse("home"))
        self.assert_navigation_destinations(
            response,
            (
                "wohnungsverwaltung_public:apartment_search",
                "building_view_pending",
            ),
        )

    def test_combined_applicant_and_tenant_permissions_keep_both_personal_sections(self):
        self.client.force_login(self.resident)
        response = self.client.get(reverse("home"))
        self.assert_navigation_destinations(
            response,
            (
                "wohnungsverwaltung_public:apartment_search",
                "building_view_pending",
                "wohnungsverwaltung:handover_protocol_mine",
                "wohnungsverwaltung:pre_application_list",
            ),
        )

    def test_direct_employee_permissions_keep_internal_links_and_hide_public_sections(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("home"))
        self.assert_navigation_destinations(
            response,
            (
                "verwaltung:wohnung_list",
                "wohnungsverwaltung:handover_protocol_list",
                "wohnungsverwaltung:employee_application_list",
                "verwaltung:user_account_list",
            ),
        )

    def test_current_public_page_is_marked_in_desktop_mobile_and_footer_navigation(self):
        response = self.client.get(reverse("building_view_pending"))
        for label, links in self.parse_navigation(response).items():
            with self.subTest(navigation=label):
                self.assertEqual(
                    [(href, current) for href, current in links if current],
                    [(reverse("building_view_pending"), "page")],
                )
        self.assertEqual(len(self.parse_navigation(response)), 3)

    def test_public_navigation_does_not_offer_the_preview_as_an_active_application(self):
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, ">Bewerbungsvorschau<")
        self.assertNotContains(response, reverse("wohnungsverwaltung:pre_application_preview"))
        self.assertContains(response, "Wohnungsvermietung in Würzburg")
        self.assertNotContains(response, "Studierendenwohnungen")

    def test_building_link_has_a_working_destination_before_the_other_branch_is_merged(self):
        self.assertEqual(reverse("building_view_pending"), "/wohnungen/gebaeude/")
        response = self.client.get(reverse("building_view_pending"))
        self.assertContains(response, "Gebäudeansicht")
        self.assertContains(response, reverse("wohnungsverwaltung_public:apartment_search"))

    def test_legal_drafts_are_public_and_linked_from_every_page(self):
        for name, title in (("imprint", "Impressum"), ("privacy", "Datenschutz")):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, title)
                self.assertContains(response, "Entwurf")
                self.assertContains(response, "Angaben folgen")
                self.assertContains(response, f'href="{reverse(name)}"')

    def test_management_subpage_marks_its_parent_section(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("verwaltung:stellplatz_list"))
        for label, links in self.parse_navigation(response).items():
            with self.subTest(navigation=label):
                self.assertEqual(
                    [(href, current) for href, current in links if current],
                    [(reverse("verwaltung:wohnung_list"), "true")],
                )
        self.assertEqual(len(self.parse_navigation(response)), 3)

    def test_logout_requires_post_and_a_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.resident)
        response = client.get(reverse("home"))
        self.assertContains(response, f'method="post" action="{reverse("logout")}"', count=2)
        self.assertContains(response, 'name="csrfmiddlewaretoken"', count=2)
        self.assertEqual(client.get(reverse("logout")).status_code, 405)
        self.assertEqual(client.post(reverse("logout")).status_code, 403)
        token = client.cookies["csrftoken"].value
        self.assertRedirects(
            client.post(reverse("logout"), {"csrfmiddlewaretoken": token}), reverse("home")
        )
