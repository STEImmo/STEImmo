from django.test import TestCase, override_settings
from django.urls import reverse

from wohnungsverwaltung.models import Wohnung, WohnungStatus


class HomePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for number, floor, status in (
            ("001", 0, WohnungStatus.FREE),
            ("101", 1, WohnungStatus.TAKEN),
            ("401", 4, WohnungStatus.BLOCKED),
        ):
            Wohnung.objects.create(
                wohnungsnummer=number, gebaeudenummer="1", etage=floor, status=status
            )

    def test_home_introduces_rental_company_and_links_to_search_and_building(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Wohnen in Würzburg.")
        self.assertContains(response, "STE Immobilien eGbR")
        self.assertContains(response, "So kommen Sie zur Besichtigung")
        self.assertContains(response, reverse("wohnungsverwaltung_public:apartment_search"))
        self.assertContains(response, reverse("wohnungsverwaltung_public:building_view"))

    def test_home_uses_current_inventory_and_links_to_real_floors(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["total_units"], 3)
        self.assertEqual(response.context["total_available"], 1)
        self.assertContains(response, "1 Wohnung verfügbar")
        for floor in (0, 1, 4):
            self.assertContains(
                response, reverse("wohnungsverwaltung_public:floor_view", args=[floor])
            )

    def test_chosen_company_design_is_used_without_comparison_even_with_old_links(self):
        for debug in (True, False):
            with self.subTest(debug=debug), override_settings(DEBUG=debug):
                response = self.client.get(reverse("home"), {"entwurf": "gebaeude"})
                self.assertContains(response, "Wohnen in Würzburg.")
                self.assertNotContains(response, 'aria-label="Startseitenentwürfe"')
                self.assertNotContains(response, "Ein Haus. Viele Möglichkeiten.")

    def test_empty_inventory_offers_search_without_advertising_available_apartments(self):
        Wohnung.objects.all().delete()
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Aktuell sind keine Wohnungen verfügbar.")
        self.assertContains(response, reverse("wohnungsverwaltung_public:apartment_search"))
        self.assertNotContains(response, 'class="facade-floor"')

    def test_fully_occupied_building_remains_explorable_without_free_apartment_claim(self):
        Wohnung.objects.available().update(status=WohnungStatus.TAKEN)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Aktuell sind keine Wohnungen verfügbar.")
        self.assertContains(response, reverse("wohnungsverwaltung_public:floor_view", args=[0]))
        self.assertEqual(response.context["total_units"], 3)
        self.assertEqual(response.context["total_available"], 0)
