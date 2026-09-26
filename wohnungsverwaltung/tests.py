from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import (
    AbnahmeStatus,
    Merkmal,
    MerkmalDatentyp,
    Person,
    Protokoll,
    ProtokollStatus,
    ProtokollTyp,
    Schluessel,
    UebergabeStatus,
    Wohnung,
)


class HandoverProtocolViewsTests(TestCase):
    def setUp(self) -> None:
        self.wohnung = Wohnung.objects.create(
            etage=2,
            wohnungsnummer="2.04",
            gebaeudenummer="1",
            zaehlernummer_wasser_kalt="KW-1001",
            zaehlernummer_wasser_warm="WW-1002",
            zaehlernummer_heizung="HZ-1003",
            zaehlernummer_strom="ST-1004",
        )
        self.person = Person.objects.create(
            vorname="Mara",
            nachname="Muster",
            email="mara.muster@example.test",
            wohnung=self.wohnung,
        )
        Schluessel.objects.create(
            wohnung=self.wohnung,
            bezeichnung="Wohnungstür",
            anzahl=2,
            aufschrift="A",
            status="in_use",
        )

    def valid_form_data(self) -> dict[str, str]:
        return {
            "wohnung": str(self.wohnung.pk),
            "person": str(self.person.pk),
            "protokoll_typ": ProtokollTyp.MOVE_IN,
            "uebergabe_zeitpunkt": "2026-09-25T10:30",
            "vermieter_name": "Vertretung des Vermieters",
            "uebergabe_status": UebergabeStatus.RENOVATED,
            "abnahme_status": AbnahmeStatus.ACCEPTED,
            "heizungsablesungen": "IE: 10, IA: 20, Ib: 30",
            "zaehlerstand_wasser_kalt": "12.50",
            "zaehlerstand_wasser_warm": "4.75",
            "zaehlerstand_heizung": "155.00",
            "zaehlerstand_strom": "87.25",
            "kaution_nachweis_vorhanden": "true",
            "erste_miete_nachweis_vorhanden": "true",
            "rooms-TOTAL_FORMS": "1",
            "rooms-INITIAL_FORMS": "0",
            "rooms-MIN_NUM_FORMS": "0",
            "rooms-MAX_NUM_FORMS": "1000",
            "keys-TOTAL_FORMS": "1",
            "keys-INITIAL_FORMS": "0",
            "keys-MIN_NUM_FORMS": "0",
            "keys-MAX_NUM_FORMS": "1000",
        }

    def test_create_page_shows_required_handover_fields(self) -> None:
        response = self.client.get(
            reverse("wohnungsverwaltung:handover_protocol_create"),
            {"wohnung": self.wohnung.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wohnung")
        self.assertContains(response, "Übergabeart")
        self.assertContains(response, "Datum und Uhrzeit")
        self.assertContains(response, "Zählernummer aus den Stammdaten")
        self.assertContains(response, "ST-1004")
        self.assertContains(response, "Zählerstände")
        self.assertContains(response, "Wohnungstür")
        self.assertContains(response, "Gebäude 1, Wohnung 2.04")
        self.assertNotIn("zaehlernummer_strom", response.context["form"].fields)

    def test_create_page_only_lists_people_assigned_to_the_selected_unit(self) -> None:
        other_unit = Wohnung.objects.create(
            etage=1,
            wohnungsnummer="1.03",
            gebaeudenummer="1",
        )
        Person.objects.create(
            vorname="Andere",
            nachname="Person",
            email="andere.person@example.test",
            wohnung=other_unit,
        )

        response = self.client.get(
            reverse("wohnungsverwaltung:handover_protocol_create"),
            {"wohnung": self.wohnung.pk},
        )

        self.assertContains(response, "Mara Muster")
        self.assertNotContains(response, "Andere Person")

    def test_create_rejects_a_person_from_another_unit(self) -> None:
        other_unit = Wohnung.objects.create(
            etage=1,
            wohnungsnummer="1.03",
            gebaeudenummer="1",
        )
        other_person = Person.objects.create(
            vorname="Andere",
            nachname="Person",
            email="andere.person@example.test",
            wohnung=other_unit,
        )
        data = self.valid_form_data()
        data["person"] = str(other_person.pk)

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("person", response.context["form"].errors)
        self.assertFalse(Protokoll.objects.exists())

    def test_create_requires_all_mandatory_meter_readings(self) -> None:
        data = self.valid_form_data()
        data.pop("zaehlerstand_strom")

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "zaehlerstand_strom", "Dieses Feld ist zwingend erforderlich."
        )
        self.assertFalse(Protokoll.objects.exists())

    def test_create_copies_meter_numbers_from_apartment_master_data(self) -> None:
        data = self.valid_form_data()
        data["zaehlernummer_strom"] = "Manipuliert-9999"

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 302)
        protocol = Protokoll.objects.get()
        self.assertEqual(protocol.zaehlernummer_strom, "ST-1004")

    def test_create_assigns_protocol_to_apartment_and_type(self) -> None:
        response = self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )

        protocol = Protokoll.objects.get()
        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            ),
        )
        self.assertEqual(protocol.wohnung, self.wohnung)
        self.assertEqual(protocol.person, self.person)
        self.assertEqual(protocol.protokoll_typ, ProtokollTyp.MOVE_IN)
        self.assertEqual(protocol.status, ProtokollStatus.OPEN)
        self.assertEqual(protocol.zaehlernummer_strom, "ST-1004")
        self.assertEqual(protocol.zaehlerstand_wasser_kalt, Decimal("12.50"))

    def test_move_in_clears_exit_only_fields(self) -> None:
        data = self.valid_form_data()
        data.update(
            {
                "mieter_zukuenftige_anschrift": "Neue Adresse 1, 12345 Beispielstadt",
                "nachbesserung_bis": "2026-10-01",
                "nachbesserung_beschreibung": "Tür einstellen",
            }
        )

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 302)
        protocol = Protokoll.objects.get()
        self.assertEqual(protocol.mieter_zukuenftige_anschrift, "")
        self.assertEqual(protocol.nachbesserung_beschreibung, "")
        self.assertIsNone(protocol.nachbesserung_bis)

    def test_move_out_requires_future_address_and_allows_remediation(self) -> None:
        data = self.valid_form_data()
        data["protokoll_typ"] = ProtokollTyp.MOVE_OUT
        data["kaution_nachweis_vorhanden"] = ""
        data["erste_miete_nachweis_vorhanden"] = ""
        data["nachbesserung_bis"] = "2026-10-01"
        data["nachbesserung_beschreibung"] = "Tür einstellen"

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "mieter_zukuenftige_anschrift",
            "Bitte erfassen Sie die zukünftige Anschrift für den Auszug.",
        )

        data["mieter_zukuenftige_anschrift"] = "Neue Adresse 1, 12345 Beispielstadt"
        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 302)
        protocol = Protokoll.objects.get()
        self.assertEqual(protocol.nachbesserung_beschreibung, "Tür einstellen")
        self.assertFalse(protocol.kaution_nachweis_vorhanden)
        self.assertFalse(protocol.erste_miete_nachweis_vorhanden)

    def test_create_saves_rooms_and_keys_from_the_same_form(self) -> None:
        data = self.valid_form_data()
        data.update(
            {
                "rooms-TOTAL_FORMS": "1",
                "rooms-INITIAL_FORMS": "0",
                "rooms-MIN_NUM_FORMS": "0",
                "rooms-MAX_NUM_FORMS": "1000",
                "rooms-0-raum": "Küche",
                "rooms-0-bezeichnung": "Fenster",
                "rooms-0-wert": "Ohne sichtbare Schäden",
                "keys-TOTAL_FORMS": "1",
                "keys-INITIAL_FORMS": "0",
                "keys-MIN_NUM_FORMS": "0",
                "keys-MAX_NUM_FORMS": "1000",
                "keys-0-anzahl": "2",
                "keys-0-raum_bezeichnung": "Wohnungstür",
                "keys-0-aufschrift": "A",
                "keys-0-schluesselnummer": "S-01",
            }
        )

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 302)
        protocol = Protokoll.objects.get()
        room = protocol.raeume.get()
        self.assertEqual(room.name, "Küche")
        self.assertEqual(room.raum_merkmale.get().merkmal.bezeichnung, "Fenster")
        self.assertEqual(protocol.protokoll_schluessel.get().anzahl, 2)

    def test_detail_shows_the_complete_protocol_for_its_apartment(self) -> None:
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        protocol = Protokoll.objects.get()

        response = self.client.get(
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gebäude 1, Wohnung 2.04")
        self.assertContains(response, "Einzug")
        self.assertContains(response, "In Bearbeitung")
        self.assertContains(response, "12,50")

    def test_edit_keeps_protocol_data_on_the_same_handover(self) -> None:
        protocol = Protokoll.objects.create(
            wohnung=self.wohnung,
            person=self.person,
            protokoll_typ=ProtokollTyp.MOVE_OUT,
            uebergabe_status=UebergabeStatus.UNRENOVATED,
            abnahme_status=AbnahmeStatus.ACCEPTED_WITH_RESERVATION,
            zaehlerstand_wasser_kalt=Decimal("1.00"),
            zaehlerstand_wasser_warm=Decimal("2.00"),
            zaehlerstand_heizung=Decimal("3.00"),
            zaehlerstand_strom=Decimal("4.00"),
        )
        data = self.valid_form_data()
        data["protokoll_typ"] = ProtokollTyp.MOVE_OUT
        data["zaehlerstand_strom"] = "99.90"
        data["mieter_zukuenftige_anschrift"] = "Neue Adresse 1, 12345 Beispielstadt"

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_edit",
                kwargs={"protocol_id": protocol.pk},
            ),
            data,
        )

        protocol.refresh_from_db()
        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            ),
        )
        self.assertEqual(protocol.pk, protocol.protokoll_id)
        self.assertEqual(protocol.zaehlerstand_strom, Decimal("99.90"))

    def test_room_checklist_records_a_detailed_previous_protocol_point(self) -> None:
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        protocol = Protokoll.objects.get()

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_room_create",
                kwargs={"protocol_id": protocol.pk},
            ),
            {"name": "Küche"},
        )

        room = protocol.raeume.get()
        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_room_detail",
                kwargs={"protocol_id": protocol.pk, "room_id": room.pk},
            ),
        )
        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_room_detail",
                kwargs={"protocol_id": protocol.pk, "room_id": room.pk},
            ),
            {
                "bereich": "Küche",
                "bezeichnung": "Fenster",
                "wert": "ohne sichtbare Schäden",
            },
        )

        room_merkmal = room.raum_merkmale.get()
        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_room_detail",
                kwargs={"protocol_id": protocol.pk, "room_id": room.pk},
            ),
        )
        self.assertEqual(room_merkmal.merkmal.bereich, "Küche")
        self.assertEqual(room_merkmal.merkmal.bezeichnung, "Fenster")
        self.assertEqual(room_merkmal.merkmal.datentyp, MerkmalDatentyp.OK)
        self.assertEqual(room_merkmal.wert, {"text": "ohne sichtbare Schäden"})

    def test_confirmation_rejects_incomplete_room_protocols(self) -> None:
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        protocol = Protokoll.objects.get()
        protocol.raeume.create(name="Küche")

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_confirm",
                kwargs={"protocol_id": protocol.pk},
            ),
            {"bestaetigung_erklaert": "on", "schluessel_ueberprueft": "on"},
        )

        protocol.refresh_from_db()
        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            ),
        )
        self.assertEqual(protocol.status, ProtokollStatus.OPEN)

    def test_confirmation_signs_complete_protocol_and_locks_edits(self) -> None:
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        protocol = Protokoll.objects.get()
        room = protocol.raeume.create(name="Küche")
        merkmal = Merkmal.objects.create(
            bereich="Küche",
            bezeichnung="Fenster",
            datentyp=MerkmalDatentyp.OK,
        )
        room.raum_merkmale.create(merkmal=merkmal, wert={"text": "ohne sichtbare Schäden"})
        protocol.protokoll_schluessel.create(
            anzahl=2,
            raum_bezeichnung="Wohnungstür",
        )

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_confirm",
                kwargs={"protocol_id": protocol.pk},
            ),
            {"bestaetigung_erklaert": "on", "schluessel_ueberprueft": "on"},
        )

        protocol.refresh_from_db()
        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            ),
        )
        self.assertEqual(protocol.status, ProtokollStatus.SIGNED)
        self.assertIsNotNone(protocol.bestaetigt_am)
        self.assertTrue(protocol.schluessel_ueberprueft)
        self.assertTrue(protocol.bestaetigung_erklaert)

        response = self.client.get(
            reverse(
                "wohnungsverwaltung:handover_protocol_edit",
                kwargs={"protocol_id": protocol.pk},
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            ),
        )

    def test_confirmation_requires_at_least_one_key_record(self) -> None:
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        protocol = Protokoll.objects.get()
        room = protocol.raeume.create(name="Küche")
        merkmal = Merkmal.objects.create(
            bereich="Küche",
            bezeichnung="Fenster",
            datentyp=MerkmalDatentyp.OK,
        )
        room.raum_merkmale.create(merkmal=merkmal, wert={"text": "ohne sichtbare Schäden"})

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_confirm",
                kwargs={"protocol_id": protocol.pk},
            ),
            {"bestaetigung_erklaert": "on", "schluessel_ueberprueft": "on"},
        )

        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            ),
        )
        protocol.refresh_from_db()
        self.assertEqual(protocol.status, ProtokollStatus.OPEN)

    def test_missing_key_requires_a_reason_for_the_handover_record(self) -> None:
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        protocol = Protokoll.objects.get()

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_key_create",
                kwargs={"protocol_id": protocol.pk},
            ),
            {
                "anzahl": "1",
                "raum_bezeichnung": "Wohnungstür",
                "fehlt": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "fehlgrund", "Bitte begründen Sie den fehlenden Schlüssel."
        )
        self.assertFalse(protocol.protokoll_schluessel.exists())

    def test_key_record_requires_a_positive_key_count(self) -> None:
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        protocol = Protokoll.objects.get()

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_key_create",
                kwargs={"protocol_id": protocol.pk},
            ),
            {"anzahl": "0", "raum_bezeichnung": "Wohnungstür"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "anzahl", "Bitte erfassen Sie mindestens einen Schlüssel."
        )
        self.assertFalse(protocol.protokoll_schluessel.exists())


class SeedStandardDataCommandTests(TestCase):
    def test_command_creates_25_units_and_is_idempotent(self) -> None:
        call_command("seed_standard_data")

        self.assertEqual(Wohnung.objects.count(), 25)
        self.assertEqual(Person.objects.count(), 6)
        self.assertEqual(Protokoll.objects.count(), 2)
        self.assertEqual(Schluessel.objects.count(), 25)
        self.assertEqual(Person.objects.filter(wohnung__isnull=False).count(), 6)

        call_command("seed_standard_data")

        self.assertEqual(Wohnung.objects.count(), 25)
        self.assertEqual(Person.objects.count(), 6)
        self.assertEqual(Protokoll.objects.count(), 2)
        self.assertEqual(Schluessel.objects.count(), 25)
        self.assertEqual(Person.objects.filter(wohnung__isnull=False).count(), 6)
