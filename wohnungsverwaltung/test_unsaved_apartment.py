from django.test import TestCase
from django.urls import reverse

from . import test_management as fixtures
from .models import Wohnung


class UnsavedApartmentRoomTests(TestCase):
    setUp = fixtures.ManagementViewTests.setUp
    wohnung_payload = fixtures.ManagementViewTests.wohnung_payload

    def test_new_apartment_waits_for_save_before_offering_room_actions(self):
        self.client.force_login(self.employee_user)

        response = self.client.get(reverse("verwaltung:wohnung_create"))

        self.assertContains(response, "Speichern Sie die Wohnung zuerst")
        self.assertNotContains(response, "Raum hinzufügen")
        self.assertNotContains(response, "Wohnungsfotos verwalten")
        self.assertFalse(
            '<p class="uk-text-muted uk-margin-small-top">Status:' in response.content.decode(),
            "An unsaved apartment must not display a persisted status.",
        )
        self.assertFalse(Wohnung.objects.exists())

    def test_invalid_creation_does_not_offer_room_actions(self):
        self.client.force_login(self.employee_user)
        payload = self.wohnung_payload() | {"wohnungsnummer": ""}

        response = self.client.post(reverse("verwaltung:wohnung_create"), payload)

        self.assertContains(response, "Speichern Sie die Wohnung zuerst")
        self.assertNotContains(response, "Raum hinzufügen")
        self.assertNotContains(response, "Wohnungsfotos verwalten")
        self.assertFalse(
            '<p class="uk-text-muted uk-margin-small-top">Status:' in response.content.decode(),
            "An invalid creation must not display a persisted status.",
        )
        self.assertFalse(Wohnung.objects.exists())

    def test_saved_apartment_offers_an_existing_room_creation_destination(self):
        self.client.force_login(self.employee_user)

        response = self.client.post(
            reverse("verwaltung:wohnung_create"), self.wohnung_payload(), follow=True
        )

        apartment = Wohnung.objects.get()
        destination = reverse("verwaltung:raum_create", args=[apartment.pk])
        photos_destination = reverse("verwaltung:apartment_photos", args=[apartment.pk])
        self.assertContains(response, f'href="{destination}"')
        self.assertContains(response, f'href="{photos_destination}"')
        self.assertContains(response, '<p class="uk-text-muted uk-margin-small-top">Status:')
        self.assertNotContains(response, "Speichern Sie die Wohnung zuerst")
        self.assertEqual(self.client.get(destination).status_code, 200)
        self.assertEqual(self.client.get(photos_destination).status_code, 200)
