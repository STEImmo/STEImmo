from decimal import Decimal

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
    UebergabeStatus,
    Wohnung,
)


class HandoverProtocolViewsTests(TestCase):
    def setUp(self) -> None:
        self.person = Person.objects.create(
            vorname="Mara",
            nachname="Muster",
            email="mara.muster@example.test",
        )
        self.wohnung = Wohnung.objects.create(
            etage=2,
            wohnungsnummer="2.04",
            gebaeudenummer="1",
        )

    def valid_form_data(self) -> dict[str, str]:
        return {
            "wohnung": str(self.wohnung.pk),
            "person": str(self.person.pk),
            "protokoll_typ": ProtokollTyp.MOVE_IN,
            "uebergabe_zeitpunkt": "2026-09-25T10:30",
            "vermieter_name": "Vertretung des Vermieters",
            "mieter_zukuenftige_anschrift": "Beispielweg 12, 12345 Musterstadt",
            "uebergabe_status": UebergabeStatus.RENOVATED,
            "abnahme_status": AbnahmeStatus.ACCEPTED,
            "zaehlernummer_wasser_kalt": "KW-1001",
            "zaehlernummer_wasser_warm": "WW-1002",
            "zaehlernummer_heizung": "HZ-1003",
            "zaehlernummer_strom": "ST-1004",
            "heizungsablesungen": "IE: 10, IA: 20, Ib: 30",
            "zaehlerstand_wasser_kalt": "12.50",
            "zaehlerstand_wasser_warm": "4.75",
            "zaehlerstand_heizung": "155.00",
            "zaehlerstand_strom": "87.25",
            "anlagenblaetter_anzahl": "1",
            "kaution_nachweis_vorhanden": "true",
            "erste_miete_nachweis_vorhanden": "true",
        }

    def test_create_page_shows_required_handover_fields(self) -> None:
        response = self.client.get(reverse("wohnungsverwaltung:handover_protocol_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wohnung")
        self.assertContains(response, "Übergabeart")
        self.assertContains(response, "Datum und Uhrzeit")
        self.assertContains(response, "Zählernummer Strom")
        self.assertContains(response, "Zählerstände")

    def test_create_requires_all_mandatory_meter_readings(self) -> None:
        data = self.valid_form_data()
        data.pop("zaehlerstand_strom")

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "zaehlerstand_strom", "Dieses Feld ist zwingend erforderlich."
        )
        self.assertFalse(Protokoll.objects.exists())

    def test_create_requires_meter_numbers_from_the_previous_protocol(self) -> None:
        data = self.valid_form_data()
        data.pop("zaehlernummer_strom")

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "zaehlernummer_strom",
            "Dieses Feld ist zwingend erforderlich.",
        )
        self.assertFalse(Protokoll.objects.exists())

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
