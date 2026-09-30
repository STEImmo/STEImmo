import json
from decimal import Decimal

from django import forms
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from .forms import InlineRoomChecklistFormSet, RoomChecklistItemForm
from .models import (
    AbnahmeStatus,
    Merkmal,
    MerkmalDatentyp,
    Person,
    Protokoll,
    ProtokollEntwurf,
    ProtokollStatus,
    ProtokollTyp,
    Raum,
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
        self.employee = Person.objects.create(
            vorname="Emil",
            nachname="Example",
            email="emil.example@example.test",
            is_employee=True,
        )
        self.room_feature = Merkmal.objects.create(
            bereich="Küche",
            bezeichnung="Fenster",
            datentyp=MerkmalDatentyp.OK,
            optionen=["Anzahl"],
        )
        self.second_room_feature = Merkmal.objects.create(
            bereich="Küche",
            bezeichnung="Boden",
            datentyp=MerkmalDatentyp.OK,
        )
        self.living_room_feature = Merkmal.objects.create(
            bereich="Wohnzimmer",
            bezeichnung="Boden",
            datentyp=MerkmalDatentyp.OK,
        )
        self.kitchen = Raum.objects.create(wohnung=self.wohnung, name="Küche")
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
            "vermieter_name": str(self.employee),
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

    def draft_data(self) -> dict[str, object]:
        return {
            "version": 1,
            "savedAt": 1_790_000_000_000,
            "fields": {
                "wohnung": {"value": str(self.wohnung.pk), "checked": None},
                "protokoll_typ": {"value": ProtokollTyp.MOVE_IN, "checked": None},
            },
            "rooms": [],
            "keys": [],
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
        heating_readings_field = response.context["form"].fields["heizungsablesungen"]
        self.assertIsInstance(heating_readings_field.widget, forms.TextInput)
        self.assertEqual(heating_readings_field.widget.attrs["class"], "uk-input")

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

    def test_room_names_are_unique_per_apartment_only(self) -> None:
        other_unit = Wohnung.objects.create(etage=1, wohnungsnummer="1.03", gebaeudenummer="1")
        Raum.objects.create(wohnung=other_unit, name="Küche")

        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Raum.objects.create(wohnung=self.wohnung, name="Küche")

    def test_room_protocol_uses_only_rooms_from_its_apartment_and_keeps_a_name_snapshot(
        self,
    ) -> None:
        other_unit = Wohnung.objects.create(etage=1, wohnungsnummer="1.03", gebaeudenummer="1")
        other_room = Raum.objects.create(wohnung=other_unit, name="Bad")
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        protocol = Protokoll.objects.get()
        room_url = reverse(
            "wohnungsverwaltung:handover_protocol_room_create",
            kwargs={"protocol_id": protocol.pk},
        )

        response = self.client.get(room_url)

        self.assertContains(response, "Küche")
        self.assertNotContains(response, "Bad")

        response = self.client.post(room_url, {"raum": str(other_room.pk)})

        self.assertEqual(response.status_code, 200)
        self.assertIn("raum", response.context["form"].errors)
        self.assertFalse(protocol.raeume.exists())

        response = self.client.post(room_url, {"raum": str(self.kitchen.pk)})

        room_protocol = protocol.raeume.get()
        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_room_detail",
                kwargs={"protocol_id": protocol.pk, "room_id": room_protocol.pk},
            ),
        )
        self.assertEqual(room_protocol.raum, self.kitchen)
        self.assertEqual(room_protocol.name, "Küche")

        self.kitchen.name = "Wohnküche"
        self.kitchen.save(update_fields=["name"])
        room_protocol.refresh_from_db()
        self.assertEqual(room_protocol.name, "Küche")

        response = self.client.post(room_url, {"raum": str(self.kitchen.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertIn("raum", response.context["form"].errors)

    def test_create_page_lists_only_employees_as_landlord_representatives(self) -> None:
        response = self.client.get(
            reverse("wohnungsverwaltung:handover_protocol_create"),
            {"wohnung": self.wohnung.pk},
        )

        landlord_field = response.context["form"].fields["vermieter_name"]
        landlord_choices = landlord_field.choices

        self.assertIsInstance(landlord_field, forms.ChoiceField)
        self.assertIn((str(self.employee), str(self.employee)), landlord_choices)
        self.assertNotIn((str(self.person), str(self.person)), landlord_choices)

    def test_create_rejects_a_non_employee_as_landlord_representative(self) -> None:
        data = self.valid_form_data()
        data["vermieter_name"] = str(self.person)

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("vermieter_name", response.context["form"].errors)
        self.assertFalse(Protokoll.objects.exists())

    def test_create_page_updates_people_without_a_full_page_reload(self) -> None:
        response = self.client.get(reverse("wohnungsverwaltung:handover_protocol_create"))

        self.assertContains(response, 'id="handover-protocol-form"')
        self.assertNotContains(response, "window.location.assign")

    def test_create_page_offers_draft_recovery(self) -> None:
        response = self.client.get(reverse("wohnungsverwaltung:handover_protocol_create"))

        self.assertContains(response, 'data-draft-scope="create"')
        self.assertContains(response, "Entwurf wiederherstellen")
        self.assertContains(response, "Entwurf verwerfen")
        self.assertContains(response, "Zwischengespeichert")

    def test_server_draft_is_listed_and_can_be_continued(self) -> None:
        response = self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_draft_save"),
            data=json.dumps({"scope": "create", "draft": self.draft_data()}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        draft = ProtokollEntwurf.objects.get()
        response = self.client.get(reverse("wohnungsverwaltung:handover_protocol_list"))

        self.assertContains(response, "Gespeicherte Entwürfe")
        self.assertContains(response, "Gebäude 1, Wohnung 2.04")
        self.assertContains(response, "Entwurf fortsetzen")
        self.assertContains(response, f"?draft={draft.pk}")

        response = self.client.get(
            reverse("wohnungsverwaltung:handover_protocol_create"), {"draft": draft.pk}
        )

        self.assertContains(response, 'id="server-protocol-draft"')

    def test_server_draft_is_only_visible_to_its_browser_session(self) -> None:
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_draft_save"),
            data=json.dumps({"scope": "create", "draft": self.draft_data()}),
            content_type="application/json",
        )
        draft = ProtokollEntwurf.objects.get()
        other_browser = Client()

        response = other_browser.get(reverse("wohnungsverwaltung:handover_protocol_list"))

        self.assertNotContains(response, "Gespeicherte Entwürfe")
        response = other_browser.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_draft_delete",
                kwargs={"draft_id": draft.pk},
            )
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ProtokollEntwurf.objects.filter(pk=draft.pk).exists())

    def test_server_draft_can_be_deleted_from_the_overview(self) -> None:
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_draft_save"),
            data=json.dumps({"scope": "create", "draft": self.draft_data()}),
            content_type="application/json",
        )
        draft = ProtokollEntwurf.objects.get()

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_draft_delete",
                kwargs={"draft_id": draft.pk},
            )
        )

        self.assertRedirects(response, reverse("wohnungsverwaltung:handover_protocol_list"))
        self.assertFalse(ProtokollEntwurf.objects.exists())

    def test_successful_creation_clears_local_and_server_drafts(self) -> None:
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_draft_save"),
            data=json.dumps({"scope": "create", "draft": self.draft_data()}),
            content_type="application/json",
        )
        self.assertTrue(ProtokollEntwurf.objects.exists())

        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        protocol = Protokoll.objects.get()

        self.assertFalse(ProtokollEntwurf.objects.exists())

        response = self.client.get(
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            )
        )

        self.assertContains(
            response,
            'data-draft-key-to-clear="handover-protocol-draft:create"',
        )

    def test_room_checklist_uses_a_large_finding_field_and_supports_deletion(self) -> None:
        finding_field = InlineRoomChecklistFormSet().empty_form.fields["wert"]

        self.assertTrue(InlineRoomChecklistFormSet.can_delete)
        self.assertEqual(finding_field.widget.attrs["rows"], 5)

    def test_create_page_has_controls_to_remove_rooms_keys_and_checklist_items(self) -> None:
        response = self.client.get(reverse("wohnungsverwaltung:handover_protocol_create"))

        self.assertContains(response, "data-remove-room")
        self.assertContains(response, "data-remove-room-checklist")
        self.assertContains(response, "data-remove-key")

    def test_room_checklist_separates_area_from_feature_name(self) -> None:
        fields = InlineRoomChecklistFormSet().empty_form.fields
        feature_field = fields["merkmal"]

        self.assertIsInstance(feature_field, forms.ModelChoiceField)
        self.assertEqual(
            list(fields["bereich"].choices),
            [("", "Bereich wählen"), ("Küche", "Küche"), ("Wohnzimmer", "Wohnzimmer")],
        )
        self.assertCountEqual(
            feature_field.queryset,
            [self.room_feature, self.second_room_feature, self.living_room_feature],
        )
        self.assertEqual(feature_field.label_from_instance(self.room_feature), "Fenster")

    def test_room_checklist_rejects_a_feature_from_another_area(self) -> None:
        form = RoomChecklistItemForm(
            data={"bereich": "Wohnzimmer", "merkmal": str(self.room_feature.pk), "wert": "Geprüft"}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("merkmal", form.errors)

    def test_room_checklist_rejects_an_additional_detail_not_defined_by_the_feature(self) -> None:
        form = RoomChecklistItemForm(
            data={
                "bereich": "Küche",
                "merkmal": str(self.room_feature.pk),
                "wert": "Geprüft",
                "zusatzangaben": '{"Farbe": "weiß"}',
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("zusatzangaben", form.errors)

    def test_person_defaults_to_not_being_an_employee(self) -> None:
        person = Person.objects.create(
            vorname="Eva",
            nachname="Example",
            email="eva.example@example.test",
        )

        self.assertFalse(person.is_employee)

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

    def test_create_saves_multiple_checklist_items_for_one_room(self) -> None:
        data = self.valid_form_data()
        data.update(
            {
                "rooms-TOTAL_FORMS": "2",
                "rooms-INITIAL_FORMS": "0",
                "rooms-MIN_NUM_FORMS": "0",
                "rooms-MAX_NUM_FORMS": "1000",
                "rooms-0-raum": str(self.kitchen.pk),
                "rooms-0-bereich": "Küche",
                "rooms-0-merkmal": str(self.room_feature.pk),
                "rooms-0-wert": "Ohne sichtbare Schäden",
                "rooms-0-zusatzangaben": '{"Anzahl": "2"}',
                "rooms-1-raum": str(self.kitchen.pk),
                "rooms-1-bereich": "Küche",
                "rooms-1-merkmal": str(self.second_room_feature.pk),
                "rooms-1-wert": "Boden ohne Schäden",
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
        self.assertCountEqual(
            room.raum_merkmale.values_list("merkmal__bezeichnung", flat=True), ["Fenster", "Boden"]
        )
        self.assertEqual(
            room.raum_merkmale.get(merkmal=self.room_feature).wert,
            {"text": "Ohne sichtbare Schäden", "angaben": {"Anzahl": "2"}},
        )
        self.assertEqual(protocol.protokoll_schluessel.get().anzahl, 2)

    def test_inline_room_checklist_rejects_a_room_from_another_apartment(self) -> None:
        other_unit = Wohnung.objects.create(etage=1, wohnungsnummer="1.03", gebaeudenummer="1")
        other_room = Raum.objects.create(wohnung=other_unit, name="Bad")
        data = self.valid_form_data()
        data.update(
            {
                "rooms-0-raum": str(other_room.pk),
                "rooms-0-bereich": "Küche",
                "rooms-0-merkmal": str(self.room_feature.pk),
                "rooms-0-wert": "Ohne sichtbare Schäden",
            }
        )

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("raum", response.context["room_formset"].forms[0].errors)
        self.assertFalse(Protokoll.objects.exists())

    def test_create_skips_rooms_and_keys_marked_for_removal(self) -> None:
        data = self.valid_form_data()
        data.update(
            {
                "rooms-TOTAL_FORMS": "1",
                "rooms-INITIAL_FORMS": "0",
                "rooms-MIN_NUM_FORMS": "0",
                "rooms-MAX_NUM_FORMS": "1000",
                "rooms-0-raum": str(self.kitchen.pk),
                "rooms-0-bereich": "Küche",
                "rooms-0-merkmal": str(self.room_feature.pk),
                "rooms-0-wert": "Ohne sichtbare Schäden",
                "rooms-0-DELETE": "on",
                "keys-TOTAL_FORMS": "1",
                "keys-INITIAL_FORMS": "0",
                "keys-MIN_NUM_FORMS": "0",
                "keys-MAX_NUM_FORMS": "1000",
                "keys-0-anzahl": "2",
                "keys-0-raum_bezeichnung": "Wohnungstür",
                "keys-0-aufschrift": "A",
                "keys-0-DELETE": "on",
            }
        )

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 302)
        protocol = Protokoll.objects.get()
        self.assertFalse(protocol.raeume.exists())
        self.assertFalse(protocol.protokoll_schluessel.exists())

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
            {"raum": str(self.kitchen.pk)},
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
                "merkmal": str(self.room_feature.pk),
                "wert": "ohne sichtbare Schäden",
                "zusatzangaben": '{"Anzahl": "3"}',
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
        self.assertEqual(
            room_merkmal.wert,
            {"text": "ohne sichtbare Schäden", "angaben": {"Anzahl": "3"}},
        )
        response = self.client.get(
            reverse(
                "wohnungsverwaltung:handover_protocol_room_detail",
                kwargs={"protocol_id": protocol.pk, "room_id": room.pk},
            )
        )
        self.assertContains(response, "Anzahl")
        self.assertContains(response, "3")

    def test_open_protocol_allows_removing_rooms_and_key_positions(self) -> None:
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        protocol = Protokoll.objects.get()
        room = protocol.raeume.create(raum=self.kitchen, name=self.kitchen.name)
        checklist_item = room.raum_merkmale.create(
            merkmal=self.room_feature,
            wert={"text": "Ohne sichtbare Schäden"},
        )
        key = protocol.protokoll_schluessel.create(
            anzahl=2,
            raum_bezeichnung="Wohnungstür",
        )

        response = self.client.get(
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            )
        )
        self.assertContains(response, "Prüfpunkt löschen")

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_checklist_item_delete",
                kwargs={
                    "protocol_id": protocol.pk,
                    "room_id": room.pk,
                    "item_id": checklist_item.pk,
                },
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_room_detail",
                kwargs={"protocol_id": protocol.pk, "room_id": room.pk},
            ),
        )
        self.assertFalse(room.raum_merkmale.filter(pk=checklist_item.pk).exists())

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_room_delete",
                kwargs={"protocol_id": protocol.pk, "room_id": room.pk},
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            ),
        )
        self.assertFalse(protocol.raeume.filter(pk=room.pk).exists())

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_key_delete",
                kwargs={"protocol_id": protocol.pk, "key_id": key.pk},
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            ),
        )
        self.assertFalse(protocol.protokoll_schluessel.filter(pk=key.pk).exists())

    def test_confirmation_rejects_incomplete_room_protocols(self) -> None:
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        protocol = Protokoll.objects.get()
        protocol.raeume.create(raum=self.kitchen, name=self.kitchen.name)

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
        room = protocol.raeume.create(raum=self.kitchen, name=self.kitchen.name)
        merkmal = Merkmal.objects.create(
            bereich="Küche",
            bezeichnung="Fenster",
            datentyp=MerkmalDatentyp.OK,
        )
        checklist_item = room.raum_merkmale.create(
            merkmal=merkmal,
            wert={"text": "ohne sichtbare Schäden"},
        )
        key = protocol.protokoll_schluessel.create(
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

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_checklist_item_delete",
                kwargs={
                    "protocol_id": protocol.pk,
                    "room_id": room.pk,
                    "item_id": checklist_item.pk,
                },
            )
        )
        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            ),
        )
        self.assertTrue(room.raum_merkmale.filter(pk=checklist_item.pk).exists())

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_room_delete",
                kwargs={"protocol_id": protocol.pk, "room_id": room.pk},
            )
        )
        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            ),
        )
        self.assertTrue(protocol.raeume.filter(pk=room.pk).exists())

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_key_delete",
                kwargs={"protocol_id": protocol.pk, "key_id": key.pk},
            )
        )
        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            ),
        )
        self.assertTrue(protocol.protokoll_schluessel.filter(pk=key.pk).exists())
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
        room = protocol.raeume.create(raum=self.kitchen, name=self.kitchen.name)
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
        self.assertEqual(Person.objects.count(), 8)
        self.assertEqual(Protokoll.objects.count(), 2)
        self.assertEqual(Schluessel.objects.count(), 25)
        self.assertEqual(Person.objects.filter(wohnung__isnull=False).count(), 6)
        self.assertEqual(Person.objects.filter(is_employee=False).count(), 6)
        self.assertEqual(Person.objects.filter(is_employee=True).count(), 2)
        self.assertEqual(Merkmal.objects.filter(bereich="Wände").count(), 21)
        self.assertEqual(
            Merkmal.objects.get(bereich="Wände", bezeichnung="Gestrichen in Farbe").optionen,
            ["Farbe"],
        )
        self.assertEqual(
            Merkmal.objects.get(
                bereich="Wände", bezeichnung="Anzahl der Bohr- und Nagellöcher"
            ).optionen,
            ["Anzahl"],
        )

        call_command("seed_standard_data")

        self.assertEqual(Wohnung.objects.count(), 25)
        self.assertEqual(Person.objects.count(), 8)
        self.assertEqual(Protokoll.objects.count(), 2)
        self.assertEqual(Schluessel.objects.count(), 25)
        self.assertEqual(Person.objects.filter(wohnung__isnull=False).count(), 6)
        self.assertEqual(Person.objects.filter(is_employee=False).count(), 6)
        self.assertEqual(Person.objects.filter(is_employee=True).count(), 2)
        self.assertEqual(Merkmal.objects.filter(bereich="Wände").count(), 21)
