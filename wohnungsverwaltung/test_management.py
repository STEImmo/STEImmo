from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import MerkmalForm
from .models import (
    Merkmal,
    MerkmalDatentyp,
    Person,
    Protokoll,
    ProtokollTyp,
    Raum,
    Raumprotokoll,
    Schluessel,
    Stellplatz,
    StellplatzTyp,
    StellplatzZuordnung,
    UebergabeStatus,
    Wohnung,
    WohnungStatus,
)


class ManagementViewTests(TestCase):
    def setUp(self) -> None:
        self.staff_user = get_user_model().objects.create_user(
            username="mitarbeiter",
            password="sicheres-passwort",
            is_staff=True,
        )

    def wohnung_payload(self) -> dict[str, str]:
        return {
            "gebaeudenummer": "B",
            "wohnungsnummer": "17",
            "etage": "2",
            "groesse_qm": "51.25",
            "zimmeranzahl": "2.5",
            "kaltmiete": "650.00",
            "warmmiete": "790.00",
            "kaution": "1300.00",
            "barrierefrei": "on",
            "status": WohnungStatus.FREE,
            "zaehlernummer_wasser_kalt": "KW-1",
            "zaehlernummer_wasser_warm": "WW-2",
            "zaehlernummer_heizung": "HZ-3",
            "zaehlernummer_strom": "ST-4",
            "schluessel-TOTAL_FORMS": "0",
            "schluessel-INITIAL_FORMS": "0",
            "schluessel-MIN_NUM_FORMS": "0",
            "schluessel-MAX_NUM_FORMS": "1000",
        }

    def test_management_requires_staff_user(self) -> None:
        url = reverse("verwaltung:wohnung_list")

        response = self.client.get(url)

        self.assertRedirects(response, f"/admin/login/?next={url}")

    def test_apartment_availability_cannot_be_changed_without_staff_access(self) -> None:
        wohnung = Wohnung.objects.create(
            gebaeudenummer="B",
            wohnungsnummer="17",
            status=WohnungStatus.BLOCKED,
        )
        url = reverse("verwaltung:wohnung_edit", args=[wohnung.pk])

        response = self.client.post(url, {"status": WohnungStatus.FREE})

        self.assertRedirects(response, f"/admin/login/?next={url}")
        wohnung.refresh_from_db()
        self.assertEqual(wohnung.status, WohnungStatus.BLOCKED)

    def test_apartment_can_be_created_with_all_master_data(self) -> None:
        self.client.force_login(self.staff_user)

        response = self.client.post(reverse("verwaltung:wohnung_create"), self.wohnung_payload())

        wohnung = Wohnung.objects.get(wohnungsnummer="17")
        self.assertRedirects(response, reverse("verwaltung:wohnung_edit", args=[wohnung.pk]))
        self.assertTrue(wohnung.barrierefrei)
        self.assertEqual(wohnung.zaehlernummer_strom, "ST-4")

    def test_staff_can_change_apartment_availability(self) -> None:
        wohnung = Wohnung.objects.create(
            gebaeudenummer="B",
            wohnungsnummer="17",
            status=WohnungStatus.BLOCKED,
        )
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("verwaltung:wohnung_edit", args=[wohnung.pk]),
            self.wohnung_payload(),
        )

        self.assertRedirects(response, reverse("verwaltung:wohnung_edit", args=[wohnung.pk]))
        wohnung.refresh_from_db()
        self.assertEqual(wohnung.status, WohnungStatus.FREE)

    def test_apartment_edit_shows_availability_choices(self) -> None:
        wohnung = Wohnung.objects.create(
            gebaeudenummer="B",
            wohnungsnummer="17",
            status=WohnungStatus.BLOCKED,
        )
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("verwaltung:wohnung_edit", args=[wohnung.pk]))

        self.assertContains(response, "Verfügbarkeitsstatus")
        self.assertContains(response, "Verfügbar")
        self.assertContains(response, "Vermietet")
        self.assertContains(response, "Gesperrt")

    def test_key_is_managed_with_apartment(self) -> None:
        self.client.force_login(self.staff_user)
        payload = self.wohnung_payload()
        payload.update(
            {
                "schluessel-TOTAL_FORMS": "1",
                "schluessel-0-schluessel_id": "",
                "schluessel-0-bezeichnung": "Haustür",
                "schluessel-0-anzahl": "2",
                "schluessel-0-aufschrift": "H1",
                "schluessel-0-status": "in_use",
            }
        )

        response = self.client.post(reverse("verwaltung:wohnung_create"), payload)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Schluessel.objects.filter(bezeichnung="Haustür", anzahl=2).exists())

    def test_stellplatz_miete_is_independent_from_wohnung_zuordnung(self) -> None:
        wohnung = Wohnung.objects.create(gebaeudenummer="A", wohnungsnummer="1")
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("verwaltung:stellplatz_create"),
            {
                "name": "TG-07",
                "stellplatz_typ": StellplatzTyp.EV,
                "miete": "45.00",
                "wohnung": str(wohnung.pk),
            },
        )

        stellplatz = Stellplatz.objects.get(name="TG-07")
        self.assertRedirects(response, reverse("verwaltung:stellplatz_edit", args=[stellplatz.pk]))
        self.assertEqual(stellplatz.miete, Decimal("45.00"))
        self.assertEqual(StellplatzZuordnung.objects.get(stellplatz=stellplatz).wohnung, wohnung)

    def test_rooms_are_sorted_and_managed_with_an_apartment(self) -> None:
        wohnung = Wohnung.objects.create(gebaeudenummer="A", wohnungsnummer="1")
        Raum.objects.create(wohnung=wohnung, name="Wohnzimmer")
        Raum.objects.create(wohnung=wohnung, name="Bad")
        self.client.force_login(self.staff_user)

        response = self.client.get(reverse("verwaltung:wohnung_edit", args=[wohnung.pk]))

        self.assertContains(response, "Bad")
        self.assertContains(response, "Wohnzimmer")
        self.assertLess(response.content.index(b"Bad"), response.content.index(b"Wohnzimmer"))

        response = self.client.post(
            reverse("verwaltung:raum_create", args=[wohnung.pk]),
            {"name": "Küche"},
        )

        kitchen = Raum.objects.get(wohnung=wohnung, name="Küche")
        self.assertRedirects(response, reverse("verwaltung:wohnung_edit", args=[wohnung.pk]))

        response = self.client.post(
            reverse("verwaltung:raum_edit", args=[wohnung.pk, kitchen.pk]),
            {"name": "Wohnküche"},
        )

        kitchen.refresh_from_db()
        self.assertRedirects(response, reverse("verwaltung:wohnung_edit", args=[wohnung.pk]))
        self.assertEqual(kitchen.name, "Wohnküche")

        response = self.client.post(
            reverse("verwaltung:raum_create", args=[wohnung.pk]),
            {"name": "Bad"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "name",
            "Diese Raumbezeichnung gibt es in der Wohnung bereits.",
        )

    def test_referenced_room_cannot_be_deleted(self) -> None:
        wohnung = Wohnung.objects.create(gebaeudenummer="A", wohnungsnummer="1")
        person = Person.objects.create(
            vorname="Mara",
            nachname="Muster",
            email="mara@example.test",
            wohnung=wohnung,
        )
        room = Raum.objects.create(wohnung=wohnung, name="Küche")
        protocol = Protokoll.objects.create(
            wohnung=wohnung,
            person=person,
            protokoll_typ=ProtokollTyp.MOVE_IN,
            uebergabe_status=UebergabeStatus.RENOVATED,
            abnahme_status="accepted",
        )
        Raumprotokoll.objects.create(protokoll=protocol, raum=room, name="Küche")
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("verwaltung:raum_delete", args=[wohnung.pk, room.pk]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Raum.objects.filter(pk=room.pk).exists())
        self.assertContains(response, "bereits in einem Übergabeprotokoll verwendet")

    def test_global_feature_dashboard_stores_non_technical_option_rows(self) -> None:
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse("verwaltung:merkmal_create"),
            {
                "bereich": "Küche",
                "bezeichnung": "Herdplatten",
                "datentyp": MerkmalDatentyp.OK,
                "optionen-TOTAL_FORMS": "3",
                "optionen-INITIAL_FORMS": "0",
                "optionen-MIN_NUM_FORMS": "0",
                "optionen-MAX_NUM_FORMS": "1000",
                "optionen-0-wert": "Anzahl",
                "optionen-1-wert": "Beschreibung",
                "optionen-2-wert": "",
            },
        )

        feature = Merkmal.objects.get(bezeichnung="Herdplatten")
        self.assertRedirects(response, reverse("verwaltung:merkmal_edit", args=[feature.pk]))
        self.assertEqual(feature.optionen, ["Anzahl", "Beschreibung"])

        response = self.client.get(reverse("verwaltung:merkmal_list"))

        self.assertContains(response, "Küche")
        self.assertContains(response, "Herdplatten")

    def test_feature_form_uses_plain_language_labels(self) -> None:
        form = MerkmalForm()

        self.assertEqual(form.fields["bereich"].label, "Wo wird geprüft?")
        self.assertEqual(form.fields["bezeichnung"].label, "Was wird geprüft?")
        self.assertEqual(form.fields["datentyp"].label, "Vorgegebene Bewertung")
