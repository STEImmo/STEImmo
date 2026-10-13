from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Wohnung, WohnungStatus


class ApartmentSearchUITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.unit = Wohnung.objects.create(
            wohnungsnummer="1", gebaeudenummer="1", etage=0, groesse_qm=Decimal("25.27")
        )
        Wohnung.objects.create(wohnungsnummer="999", gebaeudenummer="1", status=WohnungStatus.TAKEN)

    @override_settings(DEBUG=False)
    def test_selected_design_and_filter_title_are_live_outside_debug(self):
        response = self.client.get(reverse("wohnungsverwaltung_public:apartment_search"))
        self.assertContains(response, 'id="apartment-filter-title">Filter</h2>')
        self.assertContains(response, "apartment-search-filter-panel")
        self.assertContains(response, "Wohnung 001")
        self.assertContains(response, "Noch nicht angegeben")
        self.assertContains(response, "1 Wohnung verfügbar")
        self.assertNotContains(response, "Designvergleich")
        self.assertNotContains(response, "Ihre Wünsche")
        self.assertNotContains(response, "Wohnung 999")

    def test_filters_keep_values_and_offer_reset_when_no_results_match(self):
        response = self.client.get(
            reverse("wohnungsverwaltung_public:apartment_search"), {"groesse_min": "100"}
        )
        self.assertContains(response, "Keine verfügbaren Wohnungen passen")
        self.assertContains(response, 'value="100"')
        self.assertNotContains(response, 'name="variante"')

    def test_invalid_filter_has_linked_error_and_no_results(self):
        response = self.client.get(
            reverse("wohnungsverwaltung_public:apartment_search"), {"groesse_min": "-1"}
        )
        self.assertContains(response, 'id="id_groesse_min_error"')
        self.assertNotContains(response, "Wohnung 001")

    def test_empty_inventory_offers_building_link(self):
        Wohnung.objects.update(status=WohnungStatus.TAKEN)
        response = self.client.get(reverse("wohnungsverwaltung_public:apartment_search"))
        self.assertContains(response, "Zurzeit sind keine Wohnungen verfügbar.")
        self.assertContains(response, reverse("wohnungsverwaltung_public:building_view"))

    def test_card_links_to_real_details(self):
        response = self.client.get(reverse("wohnungsverwaltung_public:apartment_search"))
        self.assertContains(
            response,
            reverse("wohnungsverwaltung_public:apartment_detail_placeholder", args=[self.unit.pk]),
        )

    def test_preview_route_is_removed(self):
        self.assertEqual(self.client.get("/wohnungen/design/suche/").status_code, 404)

    def test_search_rejects_post(self):
        self.assertEqual(
            self.client.post(reverse("wohnungsverwaltung_public:apartment_search")).status_code,
            405,
        )
