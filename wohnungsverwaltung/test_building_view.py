from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .access import ROLE_APPLICANT, ROLE_EMPLOYEE
from .building_plans import APARTMENTS
from .models import ApartmentPhoto, Person, Wohnung, WohnungStatus


class BuildingViewTests(TestCase):
    def create_unit(self, number, floor, status=WohnungStatus.FREE):
        return Wohnung.objects.create(
            wohnungsnummer=number,
            gebaeudenummer="1",
            etage=floor,
            status=status,
            groesse_qm=Decimal("42.50"),
            zimmeranzahl=Decimal("2"),
            kaltmiete=Decimal("600"),
            warmmiete=Decimal("750"),
            kaution=Decimal("1800"),
        )

    def test_building_links_to_separate_floor_pages(self):
        free = self.create_unit("A-17", 2)
        taken = self.create_unit("A-18", 2, WohnungStatus.TAKEN)
        self.create_unit("D-01", 4)
        response = self.client.get(reverse("wohnungsverwaltung_public:building_view"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([floor["number"] for floor in response.context["floors"]], [4, 2])
        self.assertEqual(response.context["total_available"], 2)
        self.assertContains(response, "Das Haus auf einen Blick")
        self.assertNotContains(response, "Wohnung A-17")
        self.assertContains(response, "Westfassade")
        self.assertContains(response, "1 frei")
        self.assertContains(
            response,
            reverse("wohnungsverwaltung_public:floor_view", args=[2]) + "#etagenplan",
            count=1,
        )
        response = self.client.get(reverse("wohnungsverwaltung_public:floor_view", args=[2]))
        self.assertContains(response, 'id="etagenplan"', count=1)
        for floor, _label in response.context["floor_numbers"]:
            self.assertContains(
                response,
                reverse("wohnungsverwaltung_public:floor_view", args=[floor]) + "#etagenplan",
            )
        self.assertContains(response, free.wohnungsnummer)
        self.assertContains(response, taken.wohnungsnummer)
        self.assertContains(response, f"Whg. {free.wohnungsnummer}")
        self.assertNotContains(response, f"Whg. {taken.wohnungsnummer}")
        self.assertContains(response, 'class="plan-apartment is-unavailable"')
        self.assertContains(response, 'class="plan-unavailable-caption"', count=1)
        self.assertContains(response, '<ul id="etagenplan"')
        self.assertNotContains(response, "uk-sticky")
        self.assertNotContains(response, "Auswählbar")
        self.assertNotContains(response, "Ausgegraut")
        self.assertNotContains(response, "D-01")
        self.assertContains(
            response,
            reverse("wohnungsverwaltung_public:apartment_detail_placeholder", args=[free.pk]),
        )
        self.assertNotContains(
            response,
            reverse("wohnungsverwaltung_public:apartment_detail_placeholder", args=[taken.pk]),
        )

    def test_unknown_floor_returns_404(self):
        response = self.client.get(reverse("wohnungsverwaltung_public:floor_view", args=[9]))
        self.assertEqual(response.status_code, 404)

    def test_ground_floor_displays_three_digit_numbers_without_changing_stored_numbers(self):
        units = [self.create_unit(str(number), 0) for number in range(1, 6)]
        floor = self.client.get(reverse("wohnungsverwaltung_public:floor_view", args=[0]))
        search = self.client.get(reverse("wohnungsverwaltung_public:apartment_search"))
        for number, unit in enumerate(units, start=1):
            self.assertContains(floor, f"Whg. {number:03d}")
            self.assertContains(search, f"Wohnung {number:03d}")
            detail = self.client.get(
                reverse("wohnungsverwaltung_public:apartment_detail_placeholder", args=[unit.pk])
            )
            self.assertContains(detail, f"Wohnung {number:03d}")
            unit.refresh_from_db()
            self.assertEqual(unit.wohnungsnummer, str(number))

    def test_upper_floors_share_plan_with_their_own_units(self):
        for floor in (1, 2, 3):
            for number in range(1, 7):
                self.create_unit(str(floor * 100 + number), floor)
        responses = [
            self.client.get(reverse("wohnungsverwaltung_public:floor_view", args=[floor]))
            for floor in (1, 2, 3)
        ]
        for floor, response in zip((1, 2, 3), responses, strict=True):
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.context["plan_units"]), 6)
            self.assertEqual(
                [item["unit"].wohnungsnummer for item in response.context["plan_units"]],
                [str(floor * 100 + number) for number in range(1, 7)],
            )
            self.assertContains(response, "Balkon", count=6)
            self.assertContains(response, "Aufzug")
            self.assertNotContains(response, "Fahrradabstellbereich")
            self.assertNotContains(response, 'class="plan-furniture"')
            positions = response.context["plan_units"]
            self.assertLess(positions[5]["x"], positions[0]["x"])
            self.assertLess(positions[0]["x"], positions[1]["x"])
            self.assertGreater(positions[2]["y"], positions[1]["y"])
            self.assertGreater(positions[2]["x"], positions[3]["x"])
            self.assertGreater(positions[3]["x"], positions[4]["x"])
            self.assertLess(positions[5]["y"], positions[4]["y"])
        for response in responses[1:]:
            self.assertEqual(
                [item["points"] for item in responses[0].context["plan_units"]],
                [item["points"] for item in response.context["plan_units"]],
            )

    def test_header_links_directly_to_building(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, reverse("wohnungsverwaltung_public:building_view"))

    def test_attic_places_401_right_and_402_left(self):
        for number in ("401", "402"):
            self.create_unit(number, 4)
        response = self.client.get(reverse("wohnungsverwaltung_public:floor_view", args=[4]))
        self.assertEqual(response.status_code, 200)
        right, left = response.context["plan_units"]
        self.assertEqual(right["unit"].wohnungsnummer, "401")
        self.assertEqual(left["unit"].wohnungsnummer, "402")
        self.assertGreater(right["x"], left["x"])
        self.assertContains(response, "Aufzug")
        self.assertNotContains(response, 'class="plan-furniture"')
        self.assertNotContains(response, 'class="plan-windows"')

    def test_detail_displays_stored_data_and_existing_application_link(self):
        unit = self.create_unit("A-17", 2)
        response = self.client.get(
            reverse("wohnungsverwaltung_public:apartment_detail_placeholder", args=[unit.pk])
        )
        self.assertContains(response, "A-17")
        self.assertContains(response, "42,50")
        self.assertContains(response, "600,00")
        self.assertContains(response, "750,00")
        self.assertContains(response, "1800,00")
        self.assertContains(response, "Wohnungsfoto folgt")
        self.assertContains(response, "Zur Besichtigung anmelden")
        self.assertNotContains(response, "Für diese Wohnung bewerben")
        self.assertContains(
            response,
            reverse("wohnungsverwaltung_public:viewing_request", args=[unit.pk]),
        )

    def test_unavailable_detail_is_not_public(self):
        unit = self.create_unit("A-18", 2, WohnungStatus.TAKEN)
        response = self.client.get(
            reverse("wohnungsverwaltung_public:apartment_detail_placeholder", args=[unit.pk])
        )
        self.assertEqual(response.status_code, 404)


class ViewingRequestEntryTests(TestCase):
    def setUp(self):
        self.unit = Wohnung.objects.create(wohnungsnummer="1", gebaeudenummer="1")
        self.url = reverse("wohnungsverwaltung_public:viewing_request", args=[self.unit.pk])
        self.user = get_user_model().objects.create_user(username="viewing-entry-test")

    def test_anonymous_entry_preserves_unit_after_login(self):
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")

    def test_employee_receives_explanation_without_applicant_access(self):
        self.user.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertContains(response, "Für diese Anfrage benötigen Sie ein Bewerberkonto")
        protected = reverse(
            "wohnungsverwaltung:pre_application_create_for_unit", args=[self.unit.pk]
        )
        self.assertEqual(self.client.get(protected).status_code, 403)

    def test_applicant_without_profile_receives_profile_explanation(self):
        self.user.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.url), "Personenprofil fehlt")

    def test_complete_applicant_reaches_existing_unit_request(self):
        self.user.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        Person.objects.create(
            user=self.user, vorname="Test", nachname="Person", email="test@example.test"
        )
        self.client.force_login(self.user)
        self.assertRedirects(
            self.client.get(self.url),
            reverse("wohnungsverwaltung:pre_application_create_for_unit", args=[self.unit.pk]),
        )

    def test_unavailable_unit_cannot_be_requested(self):
        self.unit.status = WohnungStatus.TAKEN
        self.unit.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 404)


class ApartmentPhotoTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.unit = Wohnung.objects.create(wohnungsnummer="1.01", gebaeudenummer="1")
        self.employee = get_user_model().objects.create_user(username="employee-photo-test")
        self.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        self.url = reverse("verwaltung:apartment_photos", args=[self.unit.pk])

    def photo(self, name="room.png"):
        output = BytesIO()
        Image.new("RGB", (80, 60), "white").save(output, "PNG")
        return SimpleUploadedFile(name, output.getvalue(), content_type="image/png")

    def upload(self):
        self.client.force_login(self.employee)
        return self.client.post(self.url, {"image": self.photo(), "caption": "Wohnbereich"})

    def test_employee_can_upload_and_public_gallery_displays_photo(self):
        self.assertRedirects(self.upload(), self.url)
        photo = ApartmentPhoto.objects.get(apartment=self.unit)
        self.client.logout()
        response = self.client.get(
            reverse("wohnungsverwaltung_public:apartment_detail_placeholder", args=[self.unit.pk])
        )
        self.assertContains(response, "Wohnbereich")
        self.assertNotContains(response, "Wohnungsfoto folgt")
        photo_url = reverse("wohnungsverwaltung_public:apartment_photo", args=[photo.pk])
        self.assertContains(response, photo_url)
        response = self.client.get(photo_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertTrue(b"".join(response.streaming_content).startswith(b"\xff\xd8"))

    def test_anonymous_and_non_employee_cannot_upload(self):
        self.assertEqual(self.client.post(self.url, {"image": self.photo()}).status_code, 302)
        applicant = get_user_model().objects.create_user(username="applicant-photo-test")
        self.client.force_login(applicant)
        self.assertEqual(self.client.post(self.url, {"image": self.photo()}).status_code, 403)
        self.assertFalse(ApartmentPhoto.objects.exists())

    def test_upload_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.employee)
        self.assertEqual(client.post(self.url, {"image": self.photo()}).status_code, 403)

    def test_rejects_corrupt_or_oversized_upload(self):
        self.client.force_login(self.employee)
        invalid = SimpleUploadedFile("fake.png", b"not an image", content_type="image/png")
        response = self.client.post(self.url, {"image": invalid})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ApartmentPhoto.objects.exists())
        with override_settings(APARTMENT_PHOTO_MAX_SIZE=10):
            response = self.client.post(self.url, {"image": self.photo()})
        self.assertContains(response, "Datei ist zu groß")
        self.assertFalse(ApartmentPhoto.objects.exists())

    def test_photo_of_unavailable_apartment_is_hidden_from_public(self):
        self.upload()
        photo = ApartmentPhoto.objects.get()
        self.unit.status = WohnungStatus.TAKEN
        self.unit.save()
        self.client.logout()
        response = self.client.get(
            reverse("wohnungsverwaltung_public:apartment_photo", args=[photo.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_employee_can_remove_photo_with_post_only(self):
        self.upload()
        photo = ApartmentPhoto.objects.get()
        storage, name = photo.image.storage, photo.image.name
        url = reverse("verwaltung:apartment_photo_delete", args=[self.unit.pk, photo.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url), self.url)
        self.assertFalse(ApartmentPhoto.objects.exists())
        self.assertFalse(storage.exists(name))

    def test_upload_limit_is_enforced(self):
        self.upload()
        with override_settings(APARTMENT_PHOTO_MAX_COUNT=1):
            response = self.client.post(self.url, {"image": self.photo()})
        self.assertEqual(response.status_code, 200)
        self.assertIn("image", response.context["form"].errors)
        self.assertEqual(ApartmentPhoto.objects.count(), 1)

    def test_gif_is_rejected_even_when_it_is_a_valid_image(self):
        self.client.force_login(self.employee)
        output = BytesIO()
        Image.new("RGB", (10, 10)).save(output, "GIF")
        response = self.client.post(
            self.url,
            {
                "image": SimpleUploadedFile(
                    "test.gif", output.getvalue(), content_type="image/gif"
                ),
            },
        )
        self.assertContains(response, "Erlaubt sind JPEG, PNG und WebP")
        self.assertFalse(ApartmentPhoto.objects.exists())

    def test_other_apartment_photo_cannot_be_deleted_through_wrong_apartment(self):
        self.upload()
        other = Wohnung.objects.create(wohnungsnummer="other", gebaeudenummer="1")
        photo = ApartmentPhoto.objects.get()
        response = self.client.post(
            reverse("verwaltung:apartment_photo_delete", args=[other.pk, photo.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ApartmentPhoto.objects.filter(pk=photo.pk).exists())


class BuildingInventoryTests(TestCase):
    @override_settings(DEBUG=True)
    def test_inventory_update_preserves_ids_and_corrects_distribution(self):
        for legacy, _number, _floor, _area in APARTMENTS:
            Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer=legacy)
        original_ids = set(Wohnung.objects.values_list("pk", flat=True))
        call_command("sync_building_inventory", apply=True)
        call_command("sync_building_inventory", apply=True)
        self.assertEqual(set(Wohnung.objects.values_list("pk", flat=True)), original_ids)
        self.assertEqual(
            [Wohnung.objects.filter(etage=f).count() for f in range(5)], [5, 6, 6, 6, 2]
        )
        self.assertEqual(Wohnung.objects.get(wohnungsnummer="401").groesse_qm, Decimal("92.94"))
