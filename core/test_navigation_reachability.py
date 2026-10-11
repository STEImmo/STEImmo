"""Check actual rendered click paths, including context-dependent pages."""

from html.parser import HTMLParser
from urllib.parse import urldefrag, urlencode, urljoin

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from wohnungsverwaltung.access import ROLE_APPLICANT, ROLE_TENANT
from wohnungsverwaltung.models import (
    AbnahmeStatus,
    Bewerbung,
    Merkmal,
    MerkmalDatentyp,
    Person,
    Protokoll,
    ProtokollTyp,
    Raum,
    Raumprotokoll,
    Stellplatz,
    StellplatzTyp,
    UebergabeStatus,
    Wohnung,
)


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a" and (href := dict(attrs).get("href")):
            self.hrefs.append(href)


class NavigationReachabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="1", etage=0)
        for floor in range(1, 5):
            Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer=f"{floor}01", etage=floor)
        cls.room = Raum.objects.create(wohnung=cls.unit, name="Küche")
        cls.feature = Merkmal.objects.create(
            bereich="Wand", bezeichnung="Oberfläche", datentyp=MerkmalDatentyp.REIBEPUTZ
        )
        cls.parking = Stellplatz.objects.create(name="Testplatz", stellplatz_typ=StellplatzTyp.CAR)
        cls.applicant = get_user_model().objects.create_user(username="applicant@example.test")
        cls.applicant.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        cls.person = Person.objects.create(
            user=cls.applicant, vorname="Test", nachname="Bewerber", email="applicant@example.test"
        )
        cls.tenant = get_user_model().objects.create_user(username="tenant@example.test")
        cls.tenant.groups.add(Group.objects.get(name=ROLE_TENANT))
        cls.tenant_person = Person.objects.create(
            user=cls.tenant, vorname="Test", nachname="Mieter", email="tenant@example.test"
        )
        cls.employee = get_user_model().objects.create_user(username="employee@example.test")
        cls.employee.user_permissions.add(Permission.objects.get(codename="access_employee_area"))
        cls.protocol = Protokoll.objects.create(
            wohnung=cls.unit,
            person=cls.tenant_person,
            protokoll_typ=ProtokollTyp.MOVE_IN,
            uebergabe_status=UebergabeStatus.RENOVATED,
            abnahme_status=AbnahmeStatus.ACCEPTED,
        )
        cls.protocol_room = Raumprotokoll.objects.create(
            protokoll=cls.protocol, raum=cls.room, name=cls.room.name
        )

    def assert_click_path(self, *destinations):
        """Every step must be a real link; redirects do not add another click."""
        self.assertLessEqual(len(destinations), 3)
        response = self.client.get(reverse("home"))
        current_url = reverse("home")
        for destination in destinations:
            parser = LinkParser()
            parser.feed(response.content.decode())
            self.assertIn(
                destination,
                [urldefrag(urljoin(current_url, href))[0] for href in parser.hrefs],
                msg=f"Missing click from {current_url} to {destination}",
            )
            response = self.client.get(destination, follow=True)
            self.assertEqual(response.status_code, 200)
            current_url = response.redirect_chain[-1][0] if response.redirect_chain else destination

    def test_public_pages_and_viewing_request_are_reachable_within_three_clicks(self):
        search = reverse("wohnungsverwaltung_public:apartment_search")
        building = reverse("wohnungsverwaltung_public:building_view")
        detail = reverse(
            "wohnungsverwaltung_public:apartment_detail_placeholder", args=[self.unit.pk]
        )
        for name in ("login", "register", "imprint", "privacy"):
            self.assert_click_path(reverse(name))
        for floor in range(5):
            self.assert_click_path(
                building, reverse("wohnungsverwaltung_public:floor_view", args=[floor])
            )
        self.assert_click_path(
            building, reverse("wohnungsverwaltung_public:floor_view", args=[0]), detail
        )
        self.assert_click_path(
            search,
            detail,
            reverse("wohnungsverwaltung_public:viewing_request", args=[self.unit.pk]),
        )

    def test_applicant_can_start_a_viewing_request_in_three_clicks(self):
        self.client.force_login(self.applicant)
        self.assert_click_path(
            reverse("wohnungsverwaltung:pre_application_list"),
            reverse("wohnungsverwaltung:pre_application_create"),
        )
        self.assert_click_path(
            reverse("wohnungsverwaltung_public:apartment_search"),
            reverse("wohnungsverwaltung_public:apartment_detail_placeholder", args=[self.unit.pk]),
            reverse("wohnungsverwaltung_public:viewing_request", args=[self.unit.pk]),
        )

    def test_applicant_can_open_and_withdraw_their_unlocked_main_application(self):
        application = Bewerbung.objects.create(
            person=self.person, wohnung=self.unit, main_application_unlocked=True
        )
        self.client.force_login(self.applicant)
        self.assert_click_path(
            reverse("wohnungsverwaltung:pre_application_list"),
            reverse("wohnungsverwaltung:main_application_status", args=[application.pk]),
            reverse("wohnungsverwaltung:application_withdraw", args=[application.pk]),
        )

    def test_tenant_can_reach_their_protocols_directly(self):
        self.client.force_login(self.tenant)
        self.assert_click_path(reverse("wohnungsverwaltung:handover_protocol_mine"))

    def test_employee_can_reach_management_forms_in_at_most_three_clicks(self):
        self.client.force_login(self.employee)
        units = reverse("verwaltung:wohnung_list")
        edit = reverse("verwaltung:wohnung_edit", args=[self.unit.pk])
        self.assert_click_path(units, reverse("verwaltung:wohnung_create"))
        for name, args in (
            ("raum_create", [self.unit.pk]),
            ("raum_edit", [self.unit.pk, self.room.pk]),
            ("apartment_photos", [self.unit.pk]),
        ):
            self.assert_click_path(units, edit, reverse(f"verwaltung:{name}", args=args))
        for section, record in (("stellplatz", self.parking), ("merkmal", self.feature)):
            listing = reverse(f"verwaltung:{section}_list")
            for action, args in (("create", []), ("edit", [record.pk])):
                self.assert_click_path(
                    units, listing, reverse(f"verwaltung:{section}_{action}", args=args)
                )

    def test_employee_can_reach_protocol_forms_in_at_most_three_clicks(self):
        self.client.force_login(self.employee)
        listing = reverse("wohnungsverwaltung:handover_protocol_list")
        detail = reverse("wohnungsverwaltung:handover_protocol_detail", args=[self.protocol.pk])
        self.assert_click_path(listing, reverse("wohnungsverwaltung:handover_protocol_create"))
        for action, args in (
            ("edit", [self.protocol.pk]),
            ("room_create", [self.protocol.pk]),
            ("room_detail", [self.protocol.pk, self.protocol_room.pk]),
            ("key_create", [self.protocol.pk]),
            ("finalize", [self.protocol.pk]),
        ):
            self.assert_click_path(
                listing,
                detail,
                reverse(f"wohnungsverwaltung:handover_protocol_{action}", args=args),
            )

    def test_employee_can_reach_an_application_detail_in_three_clicks(self):
        application = Bewerbung.objects.create(person=self.person, wohnung=self.unit)
        self.client.force_login(self.employee)
        listing = reverse("wohnungsverwaltung:employee_application_list")
        self.assert_click_path(
            listing,
            f"{listing}?wohnung={self.unit.pk}",
            reverse("wohnungsverwaltung:employee_application_detail", args=[application.pk]),
        )

    def test_account_manager_can_reach_account_forms_in_two_clicks(self):
        self.employee.user_permissions.add(Permission.objects.get(codename="manage_user_accounts"))
        self.client.force_login(self.employee)
        listing = reverse("verwaltung:user_account_list")
        self.assert_click_path(listing, reverse("verwaltung:user_account_create"))
        self.assert_click_path(
            listing, reverse("verwaltung:user_account_edit", args=[self.applicant.pk])
        )

    def test_header_account_links_preserve_the_selected_apartment(self):
        destination = reverse("wohnungsverwaltung_public:viewing_request", args=[self.unit.pk])
        query = urlencode({"next": destination})
        for page in ("login", "register"):
            response = self.client.get(f"{reverse(page)}?{query}")
            # Both the desktop header and mobile menu must keep the same destination.
            for account_page in ("login", "register"):
                href = f'href="{reverse(account_page)}?{query}"'
                self.assertGreaterEqual(response.content.decode().count(href), 2)
