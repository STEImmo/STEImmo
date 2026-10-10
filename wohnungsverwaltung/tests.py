import json
import struct
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import mock

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, IntegrityError, close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.fields.files import FieldFile
from django.test import Client, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from PIL import Image
from reportlab.pdfgen import canvas

from . import views as application_views
from .access import ROLE_APPLICANT, ROLE_EMPLOYEE
from .forms import (
    BewerbungForm,
    InlineRoomChecklistFormSet,
    MainApplicationForm,
    RoomChecklistItemForm,
)
from .models import (
    AbnahmeStatus,
    ApplicationProof,
    ApplicationProofCategory,
    ApplicationProofCleanup,
    Bewerbung,
    BewerbungStatus,
    Merkmal,
    MerkmalDatentyp,
    Person,
    Protokoll,
    ProtokollEntwurf,
    ProtokollStatus,
    ProtokollTyp,
    Raum,
    RaumMerkmal,
    RaumMerkmalFoto,
    Schluessel,
    UebergabeStatus,
    Wohnung,
    WohnungStatus,
)
from .test_handover_export import signature_file


class ApartmentSearchViewTests(TestCase):
    def create_unit(self, number: str, **overrides) -> Wohnung:
        defaults = {
            "gebaeudenummer": "1",
            "wohnungsnummer": number,
            "etage": 1,
            "groesse_qm": Decimal("55.00"),
            "zimmeranzahl": Decimal("2.00"),
            "kaltmiete": Decimal("650.00"),
            "barrierefrei": True,
            "status": WohnungStatus.FREE,
        }
        return Wohnung.objects.create(**(defaults | overrides))

    def test_search_shows_only_available_units(self) -> None:
        free_unit = self.create_unit("1.01")
        taken_unit = self.create_unit("1.02", status=WohnungStatus.TAKEN)
        blocked_unit = self.create_unit("1.03", status=WohnungStatus.BLOCKED)

        response = self.client.get(reverse("wohnungsverwaltung_public:apartment_search"))

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["wohnungen"], [free_unit])
        self.assertNotContains(response, taken_unit.wohnungsnummer)
        self.assertNotContains(response, blocked_unit.wohnungsnummer)

    def test_search_result_links_to_apartment_detail_placeholder(self) -> None:
        unit = self.create_unit("1.01")

        response = self.client.get(reverse("wohnungsverwaltung_public:apartment_search"))

        self.assertContains(
            response,
            reverse(
                "wohnungsverwaltung_public:apartment_detail_placeholder",
                args=[unit.pk],
            ),
        )

    def test_apartment_detail_shows_photo_placeholder(self) -> None:
        unit = self.create_unit("1.01")

        response = self.client.get(
            reverse(
                "wohnungsverwaltung_public:apartment_detail_placeholder",
                args=[unit.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, unit.wohnungsnummer)
        self.assertContains(response, "Wohnungsfoto folgt")

    def test_apartment_detail_placeholder_returns_404_for_unavailable_units(self) -> None:
        unavailable_units = (
            self.create_unit("1.02", status=WohnungStatus.TAKEN),
            self.create_unit("1.03", status=WohnungStatus.BLOCKED),
        )

        for unit in unavailable_units:
            with self.subTest(status=unit.status):
                response = self.client.get(
                    reverse(
                        "wohnungsverwaltung_public:apartment_detail_placeholder",
                        args=[unit.pk],
                    )
                )

                self.assertEqual(response.status_code, 404)

    def test_search_filters_available_units_by_apartment_attributes(self) -> None:
        matching_unit = self.create_unit("1.01")
        self.create_unit("1.02", groesse_qm=Decimal("70.00"))
        self.create_unit("1.03", kaltmiete=Decimal("900.00"))
        self.create_unit("1.04", zimmeranzahl=Decimal("3.00"))
        self.create_unit("2.01", etage=2)

        response = self.client.get(
            reverse("wohnungsverwaltung_public:apartment_search"),
            {
                "groesse_min": "50",
                "groesse_max": "60",
                "kaltmiete_max": "700",
                "zimmer_min": "1",
                "zimmer_max": "2",
                "etage": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["wohnungen"], [matching_unit])

    def test_search_omits_accessibility_filter_and_result_attribute(self) -> None:
        self.create_unit("1.01")
        self.create_unit("1.02", barrierefrei=False)

        response = self.client.get(reverse("wohnungsverwaltung_public:apartment_search"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("barrierefrei", response.context["form"].fields)
        self.assertNotContains(response, "Barrierefrei")
        self.assertNotContains(response, "barrierefrei")

    def test_search_ignores_legacy_accessibility_query_parameter(self) -> None:
        first_unit = self.create_unit("1.01")
        second_unit = self.create_unit("1.02", barrierefrei=False)
        self.create_unit("1.03", groesse_qm=Decimal("70.00"))
        self.create_unit("1.04", status=WohnungStatus.BLOCKED)

        for value in ("true", "false", "ungueltig"):
            with self.subTest(value=value):
                response = self.client.get(
                    reverse("wohnungsverwaltung_public:apartment_search"),
                    {"barrierefrei": value, "groesse_max": "60"},
                )

                self.assertEqual(response.status_code, 200)
                self.assertNotIn("barrierefrei", response.context["form"].cleaned_data)
                self.assertQuerySetEqual(response.context["wohnungen"], [first_unit, second_unit])

    def test_empty_search_shows_all_available_units(self) -> None:
        first_unit = self.create_unit("1.01")
        second_unit = self.create_unit("1.02")

        response = self.client.get(reverse("wohnungsverwaltung_public:apartment_search"))

        self.assertQuerySetEqual(response.context["wohnungen"], [first_unit, second_unit])
        self.assertContains(response, "Filter zurücksetzen")

    def test_search_rejects_a_minimum_above_the_maximum(self) -> None:
        self.create_unit("1.01")

        response = self.client.get(
            reverse("wohnungsverwaltung_public:apartment_search"),
            {"groesse_min": "60", "groesse_max": "50"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "groesse_max",
            "Der Höchstwert muss mindestens dem Mindestwert entsprechen.",
        )
        self.assertFalse(response.context["wohnungen"].exists())


class HandoverProtocolViewsTests(TestCase):
    def setUp(self) -> None:
        media_root = self.enterContext(TemporaryDirectory())
        self.enterContext(self.settings(MEDIA_ROOT=media_root))
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
        self.employee_user = get_user_model().objects.create_user(
            username="emil.example@example.test",
            email="emil.example@example.test",
            password="FjordTanne!4826",
        )
        self.employee.user = self.employee_user
        self.employee.save()
        self.employee_user.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        self.client.force_login(self.employee_user)
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
        self.staff_user = get_user_model().objects.create_user(
            username="uebergabe-verwaltung",
            password="sicheres-passwort",
            is_staff=True,
        )
        self.staff_user.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))

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

    def checklist_item_for_photo(self):
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        protocol = Protokoll.objects.get()
        room = protocol.raeume.create(raum=self.kitchen, name=self.kitchen.name)
        checklist_item = room.raum_merkmale.create(
            merkmal=self.room_feature,
            wert={"text": "Kratzer am Fensterrahmen"},
        )
        return protocol, room, checklist_item

    @staticmethod
    def photo_upload(
        name: str = "feststellung.png",
        color: str = "white",
        content_type: str = "image/png",
    ) -> SimpleUploadedFile:
        image_data = BytesIO()
        Image.new("RGB", (1, 1), color).save(image_data, format="PNG")
        return SimpleUploadedFile(
            name,
            image_data.getvalue(),
            content_type=content_type,
        )

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

    def test_create_page_shows_photo_field_to_employee(self) -> None:
        self.assertFalse(self.employee_user.is_staff)
        self.client.force_login(self.employee_user)

        response = self.client.get(
            reverse("wohnungsverwaltung:handover_protocol_create"),
            {"wohnung": self.wohnung.pk},
        )

        self.assertContains(response, "Fotos zur Feststellung")
        self.assertContains(response, 'accept="image/jpeg,image/png,image/webp"')
        self.assertContains(response, "Auswahl entfernen")

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

    def test_create_uses_logged_in_employee_despite_submitted_representative(self) -> None:
        data = self.valid_form_data()
        data["vermieter_name"] = str(self.person)

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Protokoll.objects.get().vermieter_name, str(self.employee))

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
        other_browser.force_login(self.employee_user)

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
        form_response = self.client.get(reverse("wohnungsverwaltung:handover_protocol_create"))
        draft_storage_key = form_response.context["draft_storage_key"]
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
            f'data-draft-key-to-clear="{draft_storage_key}"',
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

    def test_employee_can_add_photos_while_creating_a_protocol(self) -> None:
        data = self.valid_form_data()
        data.update(
            {
                "rooms-0-raum": str(self.kitchen.pk),
                "rooms-0-bereich": "Küche",
                "rooms-0-merkmal": str(self.room_feature.pk),
                "rooms-0-wert": "Kratzer am Fensterrahmen",
            }
        )

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            self.assertFalse(self.employee_user.is_staff)
            self.client.force_login(self.employee_user)
            data["rooms-0-fotos"] = [
                self.photo_upload("eins.png", content_type="text/html"),
                self.photo_upload("zwei.png", "black"),
            ]
            response = self.client.post(
                reverse("wohnungsverwaltung:handover_protocol_create"),
                data,
            )

            self.assertEqual(response.status_code, 302)
            checklist_item = Protokoll.objects.get().raeume.get().raum_merkmale.get()
            self.assertEqual(checklist_item.fotos.count(), 2)
            self.assertEqual(
                list(checklist_item.fotos.values_list("content_type", flat=True)),
                ["image/png", "image/png"],
            )
            self.assertTrue(
                checklist_item.fotos.first().datei.storage.exists(
                    checklist_item.fotos.first().datei.name
                )
            )

    def test_non_employee_cannot_add_photos_while_creating_a_protocol(self) -> None:
        data = self.valid_form_data()
        data.update(
            {
                "rooms-0-raum": str(self.kitchen.pk),
                "rooms-0-bereich": "Küche",
                "rooms-0-merkmal": str(self.room_feature.pk),
                "rooms-0-wert": "Kratzer am Fensterrahmen",
                "rooms-0-fotos": self.photo_upload(),
            }
        )

        self.client.force_login(
            get_user_model().objects.create_user(
                username="ohne-mitarbeiterrolle",
                password="sicheres-passwort",
            )
        )

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Protokoll.objects.exists())

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

    def test_inline_room_checklist_rejects_duplicate_checkpoints(self) -> None:
        data = self.valid_form_data()
        data.update(
            {
                "rooms-TOTAL_FORMS": "2",
                "rooms-0-raum": str(self.kitchen.pk),
                "rooms-0-bereich": "Küche",
                "rooms-0-merkmal": str(self.room_feature.pk),
                "rooms-0-wert": "Kratzer am Fensterrahmen",
                "rooms-1-raum": "",
                "rooms-1-bereich": "Küche",
                "rooms-1-merkmal": str(self.room_feature.pk),
                "rooms-1-wert": "Weiterer Kratzer am Fensterrahmen",
            }
        )

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("merkmal", response.context["room_formset"].forms[1].errors)
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

    def test_room_detail_rejects_a_duplicate_checkpoint(self) -> None:
        protocol, room, checklist_item = self.checklist_item_for_photo()

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_room_detail",
                kwargs={"protocol_id": protocol.pk, "room_id": room.pk},
            ),
            {
                "bereich": "Küche",
                "merkmal": str(checklist_item.merkmal_id),
                "wert": "Weiterer Kratzer am Fensterrahmen",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("merkmal", response.context["form"].errors)
        self.assertEqual(room.raum_merkmale.count(), 1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RaumMerkmal.objects.create(
                    raumprotokoll=room,
                    merkmal=checklist_item.merkmal,
                    wert={"text": "Doppelt erfasst"},
                )

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

    def signing_data(self, protocol):
        page = self.client.get(
            reverse("wohnungsverwaltung:handover_protocol_finalize", args=[protocol.pk])
        )
        return {
            "bestaetigung_erklaert": "on",
            "schluessel_ueberprueft": "on",
            "content_token": page.context["form"].initial["content_token"],
            "tenant_mode": "signed",
            "mitarbeiter": signature_file(),
            "mieter": signature_file(),
        }

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
            self.signing_data(protocol),
        )

        protocol.refresh_from_db()
        self.assertEqual(response.status_code, 400)
        self.assertIn("Prüfpunkt", response.json()["error"])
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
            self.signing_data(protocol),
        )

        protocol.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertIn("redirect", response.json())

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
            self.signing_data(protocol),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Schlüsselposition", response.json()["error"])
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

    def test_employee_can_attach_multiple_photos_to_an_existing_checklist_item(self) -> None:
        protocol, room, checklist_item = self.checklist_item_for_photo()
        upload_url = reverse(
            "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
            kwargs={
                "protocol_id": protocol.pk,
                "room_id": room.pk,
                "item_id": checklist_item.pk,
            },
        )

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            self.assertFalse(self.employee_user.is_staff)
            self.client.force_login(self.employee_user)
            response = self.client.get(
                reverse(
                    "wohnungsverwaltung:handover_protocol_room_detail",
                    kwargs={"protocol_id": protocol.pk, "room_id": room.pk},
                )
            )
            self.assertContains(response, "Fotos speichern")
            response = self.client.post(
                upload_url,
                {
                    "fotos": [
                        self.photo_upload("erstes.png"),
                        self.photo_upload("zweites.png", "black"),
                    ]
                },
            )

            self.assertRedirects(
                response,
                reverse(
                    "wohnungsverwaltung:handover_protocol_room_detail",
                    kwargs={"protocol_id": protocol.pk, "room_id": room.pk},
                ),
            )
            photos = list(checklist_item.fotos.order_by("created_at"))
            self.assertEqual(len(photos), 2)
            self.assertTrue(
                photos[0].datei.name.startswith(f"u/{protocol.pk.hex}/{checklist_item.pk.hex}/")
            )
            self.assertTrue(photos[0].datei.storage.exists(photos[0].datei.name))

            photo_url = reverse(
                "wohnungsverwaltung:handover_protocol_checklist_item_photo_view",
                kwargs={
                    "protocol_id": protocol.pk,
                    "room_id": room.pk,
                    "item_id": checklist_item.pk,
                    "photo_id": photos[0].pk,
                },
            )
            response = self.client.get(photo_url)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "image/png")
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertEqual(photos[0].raum_merkmal_id, checklist_item.pk)

            self.client.logout()
            response = self.client.get(photo_url)
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("login"), response["Location"])

    def test_photo_view_uses_a_verified_mime_type(self) -> None:
        protocol, room, checklist_item = self.checklist_item_for_photo()

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            uploaded_photo = self.photo_upload(content_type="text/html")
            photo = RaumMerkmalFoto.objects.create(
                raum_merkmal=checklist_item,
                datei=uploaded_photo,
                content_type="text/html",
                dateigroesse=uploaded_photo.size,
            )
            self.client.force_login(self.employee_user)
            response = self.client.get(
                reverse(
                    "wohnungsverwaltung:handover_protocol_checklist_item_photo_view",
                    kwargs={
                        "protocol_id": protocol.pk,
                        "room_id": room.pk,
                        "item_id": checklist_item.pk,
                        "photo_id": photo.pk,
                    },
                )
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")

    def test_photo_upload_stores_the_verified_mime_type(self) -> None:
        protocol, room, checklist_item = self.checklist_item_for_photo()
        upload_url = reverse(
            "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
            kwargs={
                "protocol_id": protocol.pk,
                "room_id": room.pk,
                "item_id": checklist_item.pk,
            },
        )

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            self.client.force_login(self.employee_user)
            response = self.client.post(
                upload_url,
                {"fotos": self.photo_upload(content_type="text/html")},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(checklist_item.fotos.get().content_type, "image/png")

    def test_photo_upload_from_overview_returns_to_the_same_checkpoint(self) -> None:
        protocol, room, checklist_item = self.checklist_item_for_photo()
        upload_url = reverse(
            "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
            kwargs={
                "protocol_id": protocol.pk,
                "room_id": room.pk,
                "item_id": checklist_item.pk,
            },
        )

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            self.client.force_login(self.employee_user)
            response = self.client.post(
                upload_url,
                {"fotos": self.photo_upload(), "return_to": "overview"},
            )

        expected_url = (
            f"{reverse('wohnungsverwaltung:handover_protocol_detail', args=[protocol.pk])}"
            f"#pruefpunkt-{checklist_item.pk}"
        )
        self.assertEqual(response["Location"], expected_url)
        self.assertEqual(checklist_item.fotos.count(), 1)

    def test_photo_upload_does_not_store_identical_content_twice(self) -> None:
        protocol, room, checklist_item = self.checklist_item_for_photo()
        upload_url = reverse(
            "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
            kwargs={
                "protocol_id": protocol.pk,
                "room_id": room.pk,
                "item_id": checklist_item.pk,
            },
        )

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            self.client.force_login(self.staff_user)
            self.client.post(upload_url, {"fotos": self.photo_upload("erstes.png")})
            response = self.client.post(
                upload_url,
                {"fotos": self.photo_upload("identisch.png")},
                follow=True,
            )

        self.assertEqual(checklist_item.fotos.count(), 1)
        self.assertContains(response, "Dieses Foto ist für den Prüfpunkt bereits gespeichert.")

    def test_photo_upload_detects_a_duplicate_of_a_legacy_photo_without_a_hash(self) -> None:
        protocol, room, checklist_item = self.checklist_item_for_photo()
        upload_url = reverse(
            "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
            kwargs={
                "protocol_id": protocol.pk,
                "room_id": room.pk,
                "item_id": checklist_item.pk,
            },
        )

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            legacy_upload = self.photo_upload("vorhanden.png")
            RaumMerkmalFoto.objects.create(
                raum_merkmal=checklist_item,
                datei=legacy_upload,
                content_type=legacy_upload.content_type,
                dateigroesse=legacy_upload.size,
            )
            self.client.force_login(self.staff_user)
            response = self.client.post(
                upload_url,
                {"fotos": self.photo_upload("nochmal.png")},
                follow=True,
            )

        self.assertEqual(checklist_item.fotos.count(), 1)
        self.assertContains(response, "Dieses Foto ist für den Prüfpunkt bereits gespeichert.")

    def test_staff_can_remove_one_photo_without_affecting_other_photos(self) -> None:
        protocol, room, checklist_item = self.checklist_item_for_photo()
        self.client.force_login(self.employee_user)
        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            first_upload = self.photo_upload("erstes.png")
            first_photo = RaumMerkmalFoto.objects.create(
                raum_merkmal=checklist_item,
                datei=first_upload,
                content_type=first_upload.content_type,
                dateigroesse=first_upload.size,
            )
            second_upload = self.photo_upload("zweites.png", "black")
            second_photo = RaumMerkmalFoto.objects.create(
                raum_merkmal=checklist_item,
                datei=second_upload,
                content_type=second_upload.content_type,
                dateigroesse=second_upload.size,
            )
            first_stored_name = first_photo.datei.name
            second_stored_name = second_photo.datei.name

            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse(
                        "wohnungsverwaltung:handover_protocol_checklist_item_photo_delete",
                        kwargs={
                            "protocol_id": protocol.pk,
                            "room_id": room.pk,
                            "item_id": checklist_item.pk,
                            "photo_id": first_photo.pk,
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
            self.assertFalse(checklist_item.fotos.filter(pk=first_photo.pk).exists())
            self.assertTrue(checklist_item.fotos.filter(pk=second_photo.pk).exists())
            self.assertFalse(first_photo.datei.storage.exists(first_stored_name))
            self.assertTrue(second_photo.datei.storage.exists(second_stored_name))

    def test_move_out_shows_matching_photos_from_the_latest_signed_move_in(self) -> None:
        move_in, move_in_room, move_in_item = self.checklist_item_for_photo()
        move_in.status = ProtokollStatus.SIGNED
        move_in.save(update_fields=["status"])

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            matching_upload = self.photo_upload("einzug-fenster.png")
            matching_photo = RaumMerkmalFoto.objects.create(
                raum_merkmal=move_in_item,
                datei=matching_upload,
                content_type=matching_upload.content_type,
                dateigroesse=matching_upload.size,
            )
            other_item = move_in_room.raum_merkmale.create(
                merkmal=self.second_room_feature,
                wert={"text": "Boden ohne Schäden"},
            )
            other_upload = self.photo_upload("einzug-boden.png", "black")
            other_photo = RaumMerkmalFoto.objects.create(
                raum_merkmal=other_item,
                datei=other_upload,
                content_type=other_upload.content_type,
                dateigroesse=other_upload.size,
            )
            move_out_data = self.valid_form_data()
            move_out_data.update(
                {
                    "protokoll_typ": ProtokollTyp.MOVE_OUT,
                    "uebergabe_zeitpunkt": "2026-10-01T10:30",
                    "mieter_zukuenftige_anschrift": "Neue Adresse 1, 12345 Beispielstadt",
                    "rooms-0-raum": str(self.kitchen.pk),
                    "rooms-0-bereich": "Küche",
                    "rooms-0-merkmal": str(self.room_feature.pk),
                    "rooms-0-wert": "Kratzer am Fensterrahmen",
                }
            )
            response = self.client.post(
                reverse("wohnungsverwaltung:handover_protocol_create"), move_out_data
            )
            self.assertEqual(response.status_code, 302)
            move_out = Protokoll.objects.exclude(pk=move_in.pk).get()

            self.client.force_login(self.employee_user)
            response = self.client.get(
                reverse(
                    "wohnungsverwaltung:handover_protocol_detail",
                    kwargs={"protocol_id": move_out.pk},
                )
            )

            matching_photo_url = reverse(
                "wohnungsverwaltung:handover_protocol_checklist_item_photo_view",
                kwargs={
                    "protocol_id": move_in.pk,
                    "room_id": move_in_room.pk,
                    "item_id": move_in_item.pk,
                    "photo_id": matching_photo.pk,
                },
            )
            other_photo_url = reverse(
                "wohnungsverwaltung:handover_protocol_checklist_item_photo_view",
                kwargs={
                    "protocol_id": move_in.pk,
                    "room_id": move_in_room.pk,
                    "item_id": other_item.pk,
                    "photo_id": other_photo.pk,
                },
            )
            self.assertContains(response, "Einzug (alt)")
            self.assertContains(response, "Auszug (neu)")
            self.assertContains(response, "Einzug (alt)</th><th>Auszug (neu)")
            self.assertContains(response, "handover-photo-modal")
            self.assertContains(response, "data-handover-photo")
            self.assertContains(response, matching_photo_url)
            self.assertContains(response, "weitere Prüfpunkte in diesem Raum")
            self.assertContains(response, other_photo_url)
            move_out_item = list(
                list(response.context["protocol"].raeume.all())[0].raum_merkmale.all()
            )[0]
            self.assertEqual(move_out_item.einzugsprotokoll.pk, move_in.pk)
            self.assertEqual(move_out_item.einzugspruefpunkt.pk, move_in_item.pk)
            self.assertEqual(
                [photo.pk for photo in move_out_item.einzugsfotos],
                [matching_photo.pk],
            )
            self.assertFalse(move_out_item.fotos.exists())

    def test_move_out_uses_same_person_reference_when_entry_is_documented_later(self) -> None:
        move_in, _move_in_room, _move_in_item = self.checklist_item_for_photo()
        move_in.status = ProtokollStatus.SIGNED
        move_in.uebergabe_zeitpunkt = datetime(2026, 10, 1, 11, 0, tzinfo=UTC)
        move_in.save(update_fields=["status", "uebergabe_zeitpunkt"])
        move_out_data = self.valid_form_data()
        move_out_data.update(
            {
                "protokoll_typ": ProtokollTyp.MOVE_OUT,
                "uebergabe_zeitpunkt": "2026-10-01T10:30",
                "mieter_zukuenftige_anschrift": "Neue Adresse 1, 12345 Beispielstadt",
                "rooms-0-raum": str(self.kitchen.pk),
                "rooms-0-bereich": "Küche",
                "rooms-0-merkmal": str(self.room_feature.pk),
                "rooms-0-wert": "Kratzer am Fensterrahmen",
            }
        )
        self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), move_out_data)
        move_out = Protokoll.objects.exclude(pk=move_in.pk).get()

        self.client.force_login(self.employee_user)
        response = self.client.get(
            reverse("wohnungsverwaltung:handover_protocol_detail", args=[move_out.pk])
        )

        self.assertEqual(response.context["move_in_reference"].pk, move_in.pk)
        self.assertContains(response, "Einzug (alt)</th><th>Auszug (neu)")
        self.assertContains(response, "Einzug (alt)")

    def test_move_out_form_shows_the_signed_move_in_as_a_reference(self) -> None:
        move_in, move_in_room, move_in_item = self.checklist_item_for_photo()
        move_in.status = ProtokollStatus.SIGNED
        move_in.save(update_fields=["status"])

        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            photo_upload = self.photo_upload("einzug-fenster.png")
            photo = RaumMerkmalFoto.objects.create(
                raum_merkmal=move_in_item,
                datei=photo_upload,
                content_type=photo_upload.content_type,
                dateigroesse=photo_upload.size,
            )
            self.client.force_login(self.staff_user)
            response = self.client.get(
                reverse("wohnungsverwaltung:handover_protocol_create"),
                {"wohnung": self.wohnung.pk},
            )

        photo_url = reverse(
            "wohnungsverwaltung:handover_protocol_checklist_item_photo_view",
            kwargs={
                "protocol_id": move_in.pk,
                "room_id": move_in_room.pk,
                "item_id": move_in_item.pk,
                "photo_id": photo.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["move_in_reference"].pk, move_in.pk)
        self.assertContains(response, "Einzugsprotokoll zum Vergleich")
        self.assertContains(response, photo_url)

    def test_move_out_form_compares_meter_readings_with_the_signed_move_in(self) -> None:
        move_in, _move_in_room, _move_in_item = self.checklist_item_for_photo()
        move_in.status = ProtokollStatus.SIGNED
        move_in.save(update_fields=["status"])

        self.client.force_login(self.staff_user)
        response = self.client.get(
            reverse("wohnungsverwaltung:handover_protocol_create"),
            {"wohnung": self.wohnung.pk, "person": self.person.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["move_in_reference"].pk, move_in.pk)
        self.assertContains(response, "Einzug (alt)")
        self.assertContains(response, "Auszug (neu)")
        self.assertContains(response, "Differenz (neu − alt)")
        self.assertContains(response, 'data-old-meter-reading="12,50"')
        self.assertContains(response, "data-meter-difference")
        self.assertEqual(response.context["form"].initial["person"], self.person.pk)

    def test_photo_upload_rejects_non_image_files(self) -> None:
        protocol, room, checklist_item = self.checklist_item_for_photo()
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
                kwargs={
                    "protocol_id": protocol.pk,
                    "room_id": room.pk,
                    "item_id": checklist_item.pk,
                },
            ),
            {"fotos": SimpleUploadedFile("keine-bilddatei.jpg", b"kein Bild", "image/jpeg")},
        )

        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_room_detail",
                kwargs={"protocol_id": protocol.pk, "room_id": room.pk},
            ),
        )
        self.assertFalse(RaumMerkmalFoto.objects.exists())

    def test_photo_upload_enforces_size_and_count_limits(self) -> None:
        protocol, room, checklist_item = self.checklist_item_for_photo()
        upload_url = reverse(
            "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
            kwargs={
                "protocol_id": protocol.pk,
                "room_id": room.pk,
                "item_id": checklist_item.pk,
            },
        )
        self.client.force_login(self.staff_user)

        with self.settings(HANDOVER_PHOTO_MAX_SIZE=1):
            response = self.client.post(upload_url, {"fotos": self.photo_upload()})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(RaumMerkmalFoto.objects.exists())

        with (
            TemporaryDirectory() as media_root,
            self.settings(
                MEDIA_ROOT=media_root,
                HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM=1,
            ),
        ):
            self.client.post(upload_url, {"fotos": self.photo_upload()})
            response = self.client.post(
                upload_url,
                {"fotos": self.photo_upload("zweites.png", "black")},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(checklist_item.fotos.count(), 1)

    def test_confirmed_protocol_rejects_photo_changes(self) -> None:
        protocol, room, checklist_item = self.checklist_item_for_photo()
        self.client.force_login(self.staff_user)
        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            upload_url = reverse(
                "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
                kwargs={
                    "protocol_id": protocol.pk,
                    "room_id": room.pk,
                    "item_id": checklist_item.pk,
                },
            )
            self.client.post(upload_url, {"fotos": self.photo_upload()})
            photo = checklist_item.fotos.get()
            protocol.status = ProtokollStatus.SIGNED
            protocol.save(update_fields=["status"])

            response = self.client.post(upload_url, {"fotos": self.photo_upload("neu.png")})
            self.assertRedirects(
                response,
                reverse(
                    "wohnungsverwaltung:handover_protocol_detail",
                    kwargs={"protocol_id": protocol.pk},
                ),
            )
            self.assertEqual(checklist_item.fotos.count(), 1)

            response = self.client.post(
                reverse(
                    "wohnungsverwaltung:handover_protocol_checklist_item_photo_delete",
                    kwargs={
                        "protocol_id": protocol.pk,
                        "room_id": room.pk,
                        "item_id": checklist_item.pk,
                        "photo_id": photo.pk,
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
            self.assertTrue(checklist_item.fotos.filter(pk=photo.pk).exists())

    def test_deleting_a_checklist_item_removes_its_stored_photos(self) -> None:
        protocol, room, checklist_item = self.checklist_item_for_photo()
        self.client.force_login(self.staff_user)
        with TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            self.client.post(
                reverse(
                    "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
                    kwargs={
                        "protocol_id": protocol.pk,
                        "room_id": room.pk,
                        "item_id": checklist_item.pk,
                    },
                ),
                {"fotos": self.photo_upload()},
            )
            photo = checklist_item.fotos.get()
            stored_name = photo.datei.name

            with self.captureOnCommitCallbacks(execute=True):
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

            self.assertEqual(response.status_code, 302)
            self.assertFalse(RaumMerkmalFoto.objects.filter(pk=photo.pk).exists())
            self.assertFalse(photo.datei.storage.exists(stored_name))


class SeedStandardDataCommandTests(TestCase):
    def test_seed_supplies_sourced_description_without_overwriting_edited_details(self):
        call_command("seed_standard_data")
        unit = Wohnung.objects.get(wohnungsnummer="1")
        self.assertIn("Bestandsgebäudes in Würzburg", unit.description)
        self.assertEqual(unit.planned_move_in, "Voraussichtlich März 2027")
        self.assertEqual(unit.heating_type, "")
        unit.description = "Individuell gepflegte Beschreibung"
        unit.planned_move_in = "Nach Vereinbarung"
        unit.save()
        call_command("seed_standard_data")
        unit.refresh_from_db()
        self.assertEqual(unit.description, "Individuell gepflegte Beschreibung")
        self.assertEqual(unit.planned_move_in, "Nach Vereinbarung")

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


class BewerbungFormTests(TestCase):
    def setUp(self) -> None:
        self.applicant = Person.objects.create(
            vorname="Lena",
            nachname="Interessentin",
            email="lena.interessentin@example.test",
        )
        self.free_unit = Wohnung.objects.create(
            etage=1,
            wohnungsnummer="1.01",
            gebaeudenummer="1",
            status=WohnungStatus.FREE,
        )
        self.second_free_unit = Wohnung.objects.create(
            etage=1,
            wohnungsnummer="1.04",
            gebaeudenummer="1",
            status=WohnungStatus.FREE,
        )
        self.taken_unit = Wohnung.objects.create(
            etage=1,
            wohnungsnummer="1.02",
            gebaeudenummer="1",
            status=WohnungStatus.TAKEN,
        )
        self.blocked_unit = Wohnung.objects.create(
            etage=1,
            wohnungsnummer="1.03",
            gebaeudenummer="1",
            status=WohnungStatus.BLOCKED,
        )

    def valid_form_data(self) -> dict[str, str]:
        return {
            "wohnung": str(self.free_unit.pk),
            "personenanzahl": "2",
            "haustiere": "false",
            "ueber_mich": "Ich suche gemeinsam mit meiner Partnerin ein neues Zuhause.",
        }

    def test_form_only_offers_free_units(self) -> None:
        form = BewerbungForm(applicant=self.applicant)

        self.assertQuerySetEqual(
            form.fields["wohnung"].queryset, [self.free_unit, self.second_free_unit]
        )

    def test_form_saves_the_server_side_applicant_and_selected_unit(self) -> None:
        form = BewerbungForm(self.valid_form_data(), applicant=self.applicant)

        self.assertTrue(form.is_valid(), form.errors)
        application = form.save()

        self.assertEqual(application.person, self.applicant)
        self.assertEqual(application.wohnung, self.free_unit)
        self.assertEqual(application.personenanzahl, 2)
        self.assertFalse(application.haustiere)
        self.assertEqual(application.ueber_mich, self.valid_form_data()["ueber_mich"])

    def test_form_locks_a_preselected_free_unit_against_form_data(self) -> None:
        form = BewerbungForm(
            self.valid_form_data(),
            applicant=self.applicant,
            unit=self.second_free_unit,
        )

        self.assertTrue(form.fields["wohnung"].disabled)
        self.assertEqual(form.fields["wohnung"].initial, self.second_free_unit.pk)
        self.assertTrue(form.is_valid(), form.errors)
        application = form.save()

        self.assertEqual(application.wohnung, self.second_free_unit)

    def test_form_rejects_a_preselected_unavailable_unit(self) -> None:
        form = BewerbungForm(
            self.valid_form_data(),
            applicant=self.applicant,
            unit=self.taken_unit,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("wohnung", form.errors)

    def test_form_rejects_zero_household_size(self) -> None:
        data = self.valid_form_data() | {"personenanzahl": "0"}
        form = BewerbungForm(data, applicant=self.applicant)

        self.assertFalse(form.is_valid())
        self.assertIn("personenanzahl", form.errors)

    def test_form_requires_an_explicit_pet_answer(self) -> None:
        data = self.valid_form_data()
        del data["haustiere"]
        form = BewerbungForm(data, applicant=self.applicant)

        self.assertFalse(form.is_valid())
        self.assertIn("haustiere", form.errors)

    def test_form_rejects_an_empty_about_me_text(self) -> None:
        data = self.valid_form_data() | {"ueber_mich": "   "}
        form = BewerbungForm(data, applicant=self.applicant)

        self.assertFalse(form.is_valid())
        self.assertIn("ueber_mich", form.errors)

    def test_form_rejects_a_taken_unit_submitted_outside_its_queryset(self) -> None:
        data = self.valid_form_data() | {"wohnung": str(self.taken_unit.pk)}
        form = BewerbungForm(data, applicant=self.applicant)

        self.assertFalse(form.is_valid())
        self.assertIn("wohnung", form.errors)

    def test_form_rejects_a_blocked_unit_submitted_outside_its_queryset(self) -> None:
        data = self.valid_form_data() | {"wohnung": str(self.blocked_unit.pk)}
        form = BewerbungForm(data, applicant=self.applicant)

        self.assertFalse(form.is_valid())
        self.assertIn("wohnung", form.errors)


class BewerbungDatabaseConstraintTests(TestCase):
    def setUp(self) -> None:
        self.applicant = Person.objects.create(
            vorname="Jonas",
            nachname="Bewerber",
            email="jonas.bewerber@example.test",
        )
        self.first_unit = Wohnung.objects.create(
            etage=2,
            wohnungsnummer="2.01",
            gebaeudenummer="1",
            status=WohnungStatus.FREE,
        )
        self.second_unit = Wohnung.objects.create(
            etage=2,
            wohnungsnummer="2.02",
            gebaeudenummer="1",
            status=WohnungStatus.FREE,
        )

    def test_database_rejects_a_household_size_below_one(self) -> None:
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Bewerbung.objects.create(
                    person=self.applicant,
                    wohnung=self.first_unit,
                    personenanzahl=0,
                    ueber_mich="Ich suche eine Wohnung.",
                )

    def test_database_allows_only_one_open_application_per_person(self) -> None:
        Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.first_unit,
            personenanzahl=1,
            ueber_mich="Ich suche eine Wohnung.",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Bewerbung.objects.create(
                    person=self.applicant,
                    wohnung=self.second_unit,
                    personenanzahl=1,
                    ueber_mich="Ich suche ebenfalls diese Wohnung.",
                )

    def test_database_allows_a_new_open_application_after_withdrawal(self) -> None:
        Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.first_unit,
            personenanzahl=1,
            ueber_mich="Ich suche eine Wohnung.",
            interest_withdrawn_at=datetime.now(UTC),
        )

        application = Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.second_unit,
            personenanzahl=1,
            ueber_mich="Ich suche erneut eine Wohnung.",
        )

        self.assertEqual(application.person, self.applicant)


class PreApplicationAuthenticationTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="testbewerber@example.test",
            email="testbewerber@example.test",
            password="FjordTanne!4826",
        )
        self.applicant = Person.objects.create(
            user=self.user,
            vorname="Test",
            nachname="Bewerber",
            email="testbewerber@example.test",
        )
        self.user.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        self.free_unit = Wohnung.objects.create(
            etage=4,
            wohnungsnummer="4.01",
            gebaeudenummer="1",
            status=WohnungStatus.FREE,
        )

    def valid_form_data(self) -> dict[str, str]:
        return {
            "wohnung": str(self.free_unit.pk),
            "personenanzahl": "2",
            "haustiere": "false",
            "ueber_mich": "Ich möchte mich für diese Wohnung bewerben.",
        }

    def test_create_page_requires_login(self) -> None:
        application_url = reverse("wohnungsverwaltung:pre_application_create")

        response = self.client.get(application_url)

        self.assertRedirects(response, f"{reverse('login')}?next={application_url}")

    def test_user_without_person_profile_cannot_open_application_form(self) -> None:
        user_without_profile = get_user_model().objects.create_user(
            username="ohneprofil@example.test",
            password="KieselWolke!4826",
        )
        self.client.force_login(user_without_profile)

        response = self.client.get(reverse("wohnungsverwaltung:pre_application_create"))

        self.assertEqual(response.status_code, 403)

    def test_linked_user_can_submit_an_application(self) -> None:
        self.assertTrue(self.client.login(username=self.user.username, password="FjordTanne!4826"))

        response = self.client.post(
            reverse("wohnungsverwaltung:pre_application_create"), self.valid_form_data()
        )

        self.assertRedirects(response, reverse("wohnungsverwaltung:pre_application_list"))
        application = Bewerbung.objects.get()
        self.assertEqual(application.person, self.applicant)
        self.assertEqual(application.wohnung, self.free_unit)

    def test_viewing_request_keeps_selected_unit_and_main_application_locked(self) -> None:
        self.client.force_login(self.user)
        url = reverse(
            "wohnungsverwaltung:pre_application_create_for_unit", args=[self.free_unit.pk]
        )
        form_response = self.client.get(url)
        self.assertContains(form_response, "Zur Besichtigung anmelden")
        self.assertContains(form_response, "Besichtigungsanfrage senden")
        response = self.client.post(url, self.valid_form_data(), follow=True)
        self.assertContains(response, "Ihre Besichtigungsanfrage wurde gespeichert.")
        application = Bewerbung.objects.get()
        self.assertEqual(application.wohnung, self.free_unit)
        self.assertFalse(application.main_application_accessible)
        main_response = self.client.get(
            reverse("wohnungsverwaltung:main_application_status", args=[application.pk])
        )
        self.assertEqual(main_response.status_code, 404)

    def test_linked_user_cannot_submit_for_a_unit_that_became_unavailable(self) -> None:
        self.assertTrue(self.client.login(username=self.user.username, password="FjordTanne!4826"))
        self.free_unit.status = WohnungStatus.BLOCKED
        self.free_unit.save(update_fields=["status"])

        response = self.client.post(
            reverse("wohnungsverwaltung:pre_application_create"), self.valid_form_data()
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("wohnung", response.context["form"].errors)
        self.assertFalse(Bewerbung.objects.exists())

    def test_linked_user_sees_their_submitted_application(self) -> None:
        Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.free_unit,
            personenanzahl=1,
            ueber_mich="Ich möchte mich für diese Wohnung bewerben.",
        )
        self.client.login(username=self.user.username, password="FjordTanne!4826")

        response = self.client.get(reverse("wohnungsverwaltung:pre_application_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Meine Bewerbungen")
        self.assertContains(response, "Gebäude 1, Wohnung 4.01")
        self.assertContains(response, "In Bearbeitung")
        self.assertContains(response, "Warten Sie auf die nächste Rückmeldung")

    def test_linked_user_can_open_the_main_application_status_when_unlocked(self) -> None:
        application = Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.free_unit,
            personenanzahl=1,
            ueber_mich="Ich möchte mich für diese Wohnung bewerben.",
            main_application_unlocked=True,
        )
        self.client.login(username=self.user.username, password="FjordTanne!4826")

        list_response = self.client.get(reverse("wohnungsverwaltung:pre_application_list"))
        main_response = self.client.get(
            reverse("wohnungsverwaltung:main_application_status", args=[application.pk])
        )

        self.assertContains(list_response, "Main-Bewerbung freigeschaltet")
        self.assertContains(
            list_response,
            reverse("wohnungsverwaltung:main_application_status", args=[application.pk]),
        )
        self.assertEqual(main_response.status_code, 200)
        self.assertContains(main_response, "Die Main-Bewerbung ist freigeschaltet.")
        self.assertContains(main_response, "Interesse zurückziehen")

    def test_main_application_access_state_is_scoped_to_each_application(self) -> None:
        previous_application = Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.free_unit,
            personenanzahl=1,
            ueber_mich="Eine frühere Bewerbung.",
            status=BewerbungStatus.DECLINED,
            main_application_unlocked=True,
        )
        active_application = Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.free_unit,
            personenanzahl=1,
            ueber_mich="Meine aktuelle Bewerbung.",
            main_application_unlocked=True,
        )
        self.client.login(username=self.user.username, password="FjordTanne!4826")

        response = self.client.get(reverse("wohnungsverwaltung:pre_application_list"))

        self.assertContains(
            response,
            reverse("wohnungsverwaltung:main_application_status", args=[active_application.pk]),
        )
        self.assertNotContains(
            response,
            reverse(
                "wohnungsverwaltung:main_application_status",
                args=[previous_application.pk],
            ),
        )
        self.assertContains(response, "Abgelehnt")
        self.assertContains(response, "Main-Bewerbung freigeschaltet")

    def test_locked_application_has_no_main_access(self) -> None:
        application = Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.free_unit,
            personenanzahl=1,
            ueber_mich="Ich möchte mich für diese Wohnung bewerben.",
        )
        self.client.login(username=self.user.username, password="FjordTanne!4826")

        response = self.client.get(
            reverse("wohnungsverwaltung:main_application_status", args=[application.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_main_application_status_can_save_a_draft_in_issue_20(self) -> None:
        application = Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.free_unit,
            personenanzahl=1,
            ueber_mich="Ich möchte mich für diese Wohnung bewerben.",
            main_application_unlocked=True,
        )
        self.client.login(username=self.user.username, password="FjordTanne!4826")

        response = self.client.post(
            reverse("wohnungsverwaltung:main_application_status", args=[application.pk]),
            {"action": "save_draft", "ueber_mich": "Geänderte Angaben"},
        )

        self.assertRedirects(
            response,
            reverse("wohnungsverwaltung:main_application_status", args=[application.pk]),
        )
        application.refresh_from_db()
        self.assertEqual(application.ueber_mich, "Ich möchte mich für diese Wohnung bewerben.")

    def test_applicant_cannot_open_another_persons_main_application(self) -> None:
        other_user = get_user_model().objects.create_user(
            username="andere-person@example.test",
            email="andere-person@example.test",
            password="FjordTanne!4826",
        )
        other_applicant = Person.objects.create(
            user=other_user,
            vorname="Andere",
            nachname="Person",
            email="andere-person@example.test",
        )
        other_unit = Wohnung.objects.create(
            etage=4,
            wohnungsnummer="4.02",
            gebaeudenummer="1",
            status=WohnungStatus.FREE,
        )
        other_application = Bewerbung.objects.create(
            person=other_applicant,
            wohnung=other_unit,
            personenanzahl=1,
            ueber_mich="Vertrauliche Angaben einer anderen Person.",
            main_application_unlocked=True,
        )
        self.client.login(username=self.user.username, password="FjordTanne!4826")

        list_response = self.client.get(reverse("wohnungsverwaltung:pre_application_list"))
        detail_response = self.client.get(
            reverse("wohnungsverwaltung:main_application_status", args=[other_application.pk])
        )

        self.assertNotContains(list_response, "Vertrauliche Angaben einer anderen Person.")
        self.assertNotContains(list_response, str(other_unit))
        self.assertEqual(detail_response.status_code, 404)

    def test_declined_application_cannot_open_main_application_even_if_unlocked(self) -> None:
        application = Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.free_unit,
            personenanzahl=1,
            ueber_mich="Die Bewerbung wurde beendet.",
            status=BewerbungStatus.DECLINED,
            main_application_unlocked=True,
        )
        self.client.login(username=self.user.username, password="FjordTanne!4826")

        response = self.client.get(
            reverse("wohnungsverwaltung:main_application_status", args=[application.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_applicant_can_withdraw_an_unlocked_application(self) -> None:
        application = Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.free_unit,
            personenanzahl=1,
            ueber_mich="Ich möchte mich für diese Wohnung bewerben.",
            main_application_unlocked=True,
        )
        self.client.login(username=self.user.username, password="FjordTanne!4826")
        withdraw_url = reverse("wohnungsverwaltung:application_withdraw", args=[application.pk])

        confirmation_response = self.client.get(withdraw_url)
        self.assertEqual(confirmation_response.status_code, 200)
        self.assertIsNone(Bewerbung.objects.get(pk=application.pk).interest_withdrawn_at)

        response = self.client.post(withdraw_url)

        self.assertRedirects(response, reverse("wohnungsverwaltung:pre_application_list"))
        application.refresh_from_db()
        self.assertIsNotNone(application.interest_withdrawn_at)
        self.assertContains(
            self.client.get(reverse("wohnungsverwaltung:pre_application_list")),
            "Zurückgezogen",
        )

    def test_applicant_cannot_withdraw_a_locked_application(self) -> None:
        application = Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.free_unit,
            personenanzahl=1,
            ueber_mich="Ich möchte mich für diese Wohnung bewerben.",
        )
        self.client.login(username=self.user.username, password="FjordTanne!4826")

        response = self.client.post(
            reverse("wohnungsverwaltung:application_withdraw", args=[application.pk])
        )

        self.assertEqual(response.status_code, 404)
        self.assertIsNone(Bewerbung.objects.get(pk=application.pk).interest_withdrawn_at)

    def test_applicant_cannot_withdraw_another_persons_application(self) -> None:
        other_user = get_user_model().objects.create_user(
            username="fremd@example.test",
            email="fremd@example.test",
            password="FjordTanne!4826",
        )
        other_applicant = Person.objects.create(
            user=other_user,
            vorname="Fremde",
            nachname="Person",
            email="fremd@example.test",
        )
        other_application = Bewerbung.objects.create(
            person=other_applicant,
            wohnung=self.free_unit,
            personenanzahl=1,
            ueber_mich="Vertrauliche Angaben einer anderen Person.",
            main_application_unlocked=True,
        )
        self.client.login(username=self.user.username, password="FjordTanne!4826")

        response = self.client.post(
            reverse("wohnungsverwaltung:application_withdraw", args=[other_application.pk])
        )

        self.assertEqual(response.status_code, 404)
        self.assertIsNone(Bewerbung.objects.get(pk=other_application.pk).interest_withdrawn_at)

    def test_withdrawn_application_cannot_be_reactivated_or_withdrawn_again(self) -> None:
        application = Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.free_unit,
            personenanzahl=1,
            ueber_mich="Ich möchte mich für diese Wohnung bewerben.",
            main_application_unlocked=True,
            interest_withdrawn_at=datetime.now(UTC),
        )
        self.client.login(username=self.user.username, password="FjordTanne!4826")

        main_response = self.client.get(
            reverse("wohnungsverwaltung:main_application_status", args=[application.pk])
        )
        withdrawal_response = self.client.post(
            reverse("wohnungsverwaltung:application_withdraw", args=[application.pk])
        )

        self.assertEqual(main_response.status_code, 404)
        self.assertEqual(withdrawal_response.status_code, 404)

    def test_list_disables_new_application_button_for_open_application(self) -> None:
        Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.free_unit,
            personenanzahl=1,
            ueber_mich="Ich möchte mich für diese Wohnung bewerben.",
        )
        self.client.login(username=self.user.username, password="FjordTanne!4826")

        response = self.client.get(reverse("wohnungsverwaltung:pre_application_list"))

        self.assertContains(
            response,
            'type="button" disabled>Neue Pre-Bewerbung</button>',
        )
        self.assertContains(response, "Sie haben bereits eine offene Pre-Bewerbung.")


class MainApplicationUploadTests(TestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        media_settings = self.settings(MEDIA_ROOT=self.media_directory.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)

        self.applicant_user = get_user_model().objects.create_user(
            username="bewerber@example.test",
            email="bewerber@example.test",
            password="FjordTanne!4826",
        )
        self.applicant = Person.objects.create(
            user=self.applicant_user,
            vorname="Berta",
            nachname="Bewerber",
            email="bewerber@example.test",
        )
        self.applicant_user.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        self.employee_user = get_user_model().objects.create_user(
            username="mitarbeiter@example.test",
            email="mitarbeiter@example.test",
            password="KometFjord!4826",
        )
        self.employee_user.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        self.other_user = get_user_model().objects.create_user(
            username="andere@example.test",
            email="andere@example.test",
            password="KieselWolke!4826",
        )
        self.other_user.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        self.other_applicant = Person.objects.create(
            user=self.other_user,
            vorname="Andere",
            nachname="Person",
            email="andere@example.test",
        )
        self.unit = Wohnung.objects.create(
            etage=4,
            wohnungsnummer="4.11",
            gebaeudenummer="1",
            status=WohnungStatus.FREE,
        )
        self.application = Bewerbung.objects.create(
            person=self.applicant,
            wohnung=self.unit,
            personenanzahl=1,
            ueber_mich="Ich möchte mich für diese Wohnung bewerben.",
            main_application_unlocked=True,
        )
        self.main_url = reverse(
            "wohnungsverwaltung:main_application_status", args=[self.application.pk]
        )

    @staticmethod
    def png_upload(name: str = "nachweis.png") -> SimpleUploadedFile:
        image_buffer = BytesIO()
        Image.new("RGB", (2, 2), color="white").save(image_buffer, format="PNG")
        return SimpleUploadedFile(name, image_buffer.getvalue(), content_type="image/png")

    @staticmethod
    def pdf_upload(name: str = "nachweis.pdf", size: int = 36) -> SimpleUploadedFile:
        pdf_buffer = BytesIO()
        document = canvas.Canvas(pdf_buffer)
        document.drawString(72, 720, "Gültiger Testnachweis")
        document.save()
        content = pdf_buffer.getvalue()
        if len(content) < size:
            content += b" " * (size - len(content))
        return SimpleUploadedFile(name, content, content_type="application/pdf")

    @staticmethod
    def broken_png_upload(name: str = "broken.png") -> SimpleUploadedFile:
        def chunk(chunk_type: bytes, data: bytes) -> bytes:
            chunk_data = chunk_type + data
            return (
                struct.pack(">I", len(data))
                + chunk_data
                + struct.pack(">I", zlib.crc32(chunk_data) & 0xFFFFFFFF)
            )

        content = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", b"not a zlib image stream")
            + chunk(b"IEND", b"")
        )
        return SimpleUploadedFile(name, content, content_type="image/png")

    def complete_upload_data(self) -> dict[str, object]:
        return {
            "action": "submit",
            "income_proof": self.pdf_upload("gehaltsabrechnungen.pdf"),
            "identity_proof": self.png_upload("personalausweis.png"),
            "credit_report_proof": self.pdf_upload("schufa.pdf"),
        }

    def applicant_post(self, data: dict[str, object], url: str | None = None):
        self.client.force_login(self.applicant_user)
        return self.client.post(url or self.main_url, data)

    def test_main_application_page_renders_only_the_three_document_uploads(self) -> None:
        self.client.force_login(self.applicant_user)

        response = self.client.get(self.main_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'name="income_proof"')
        self.assertContains(response, 'name="identity_proof"')
        self.assertContains(response, 'name="credit_report_proof"')
        self.assertContains(response, "data-proof-upload-form")
        self.assertContains(response, "data-proof-upload-input")
        self.assertContains(response, 'data-max-files="10"')
        self.assertContains(response, "data-max-file-size=")
        self.assertContains(response, "data-max-total-size=")
        self.assertContains(response, "data-proof-total-size-error")
        self.assertContains(response, "data-proof-upload-modal")
        self.assertEqual(response.content.count(b"data-proof-selection-list"), 3)
        self.assertContains(response, "main_application_uploads.js?v=8")
        self.assertContains(response, "auch nacheinander auswählen")
        self.assertContains(response, "Entwurf speichern")
        self.assertNotContains(response, "Ergänzende Angaben")
        self.assertNotContains(response, "/media/")

    def test_saved_proof_filename_is_available_for_immediate_duplicate_check(self) -> None:
        proof = self.application.proof_files.create(
            category=ApplicationProofCategory.IDENTITY,
            file=self.png_upload("original-file.png"),
            original_name="personalausweis.png",
        )
        self.client.force_login(self.applicant_user)

        response = self.client.get(self.main_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-proof-existing-name>personalausweis.png</span>")
        self.assertContains(response, f"({proof.file.size} B)")

    def test_proof_removal_warns_about_unsaved_file_selections(self) -> None:
        proof = self.application.proof_files.create(
            category=ApplicationProofCategory.IDENTITY,
            file=self.png_upload(),
            original_name="identity.png",
        )
        self.client.force_login(self.applicant_user)
        response = self.client.get(self.main_url)
        self.assertContains(response, "data-proof-remove-form")
        self.assertContains(response, "Noch nicht gespeicherte Dateiauswahlen gehen verloren")
        self.assertContains(response, "Speichern Sie zuerst den Entwurf")
        self.assertTrue(ApplicationProof.objects.filter(pk=proof.pk).exists())

    def test_applicant_can_save_an_incomplete_draft(self) -> None:
        response = self.applicant_post(
            {"action": "save_draft", "identity_proof": self.png_upload("ausweis.png")}
        )

        self.assertRedirects(response, self.main_url, fetch_redirect_response=False)
        self.application.refresh_from_db()
        self.assertIsNone(self.application.submitted_at)
        proof = ApplicationProof.objects.get(
            application=self.application,
            category=ApplicationProofCategory.IDENTITY,
        )
        self.assertEqual(proof.original_name, "ausweis.png")
        self.assertTrue(proof.file.storage.exists(proof.file.name))
        self.assertContains(self.client.get(self.main_url), "Ihr Entwurf wurde gespeichert.")

    def test_applicant_can_submit_all_three_required_proofs(self) -> None:
        response = self.applicant_post(self.complete_upload_data())

        self.assertRedirects(response, self.main_url)
        self.application.refresh_from_db()
        self.assertIsNotNone(self.application.submitted_at)
        expected_proofs = (
            (ApplicationProofCategory.INCOME, "gehaltsabrechnungen.pdf"),
            (ApplicationProofCategory.IDENTITY, "personalausweis.png"),
            (ApplicationProofCategory.CREDIT_REPORT, "schufa.pdf"),
        )
        for category, original_name in expected_proofs:
            proof = ApplicationProof.objects.get(application=self.application, category=category)
            self.assertEqual(proof.original_name, original_name)
            self.assertTrue(proof.file.storage.exists(proof.file.name))
            self.assertNotIn(original_name, proof.file.name)
            self.assertEqual(Path(proof.file.path).stat().st_mode & 0o777, 0o600)
            self.assertEqual(Path(proof.file.path).parent.stat().st_mode & 0o777, 0o700)
        self.assertContains(self.client.get(self.main_url), "Main-Bewerbung eingereicht")

    def test_final_submission_requires_every_proof(self) -> None:
        data = self.complete_upload_data()
        data.pop("credit_report_proof")

        response = self.applicant_post(data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("credit_report_proof", response.context["form"].errors)
        self.application.refresh_from_db()
        self.assertIsNone(self.application.submitted_at)

    def test_applicant_can_add_and_remove_proof_files_while_in_draft(self) -> None:
        self.applicant_post({"action": "save_draft", "identity_proof": self.png_upload("alt.png")})
        previous_identity = ApplicationProof.objects.get(
            application=self.application,
            category=ApplicationProofCategory.IDENTITY,
        )
        previous_identity_name = previous_identity.file.name

        response = self.applicant_post(
            {"action": "save_draft", "identity_proof": self.pdf_upload("neue-datei.pdf")}
        )

        self.assertRedirects(response, self.main_url)
        self.assertEqual(
            ApplicationProof.objects.filter(
                application=self.application,
                category=ApplicationProofCategory.IDENTITY,
            ).count(),
            2,
        )
        replacement = ApplicationProof.objects.get(
            application=self.application,
            category=ApplicationProofCategory.IDENTITY,
            original_name="neue-datei.pdf",
        )
        self.assertTrue(previous_identity.file.storage.exists(previous_identity_name))

        with self.captureOnCommitCallbacks(execute=True):
            removal_response = self.applicant_post({"remove_proof": str(previous_identity.pk)})

        self.assertRedirects(removal_response, self.main_url)
        self.assertFalse(replacement.file.storage.exists(previous_identity_name))
        self.assertTrue(replacement.file.storage.exists(replacement.file.name))
        self.application.refresh_from_db()
        self.assertIsNone(self.application.submitted_at)

    def test_removal_database_failure_preserves_file_and_reference(self) -> None:
        proof = self.application.proof_files.create(
            category=ApplicationProofCategory.IDENTITY,
            file=self.png_upload("identity.png"),
            original_name="identity.png",
        )
        self.client.force_login(self.applicant_user)
        with (
            mock.patch.object(ApplicationProof, "delete", side_effect=DatabaseError("failed")),
            self.assertLogs("wohnungsverwaltung.views", level="ERROR"),
        ):
            response = self.client.post(self.main_url, {"remove_proof": str(proof.pk)}, follow=True)
        self.assertContains(response, "Der Nachweis konnte nicht entfernt werden.")
        self.assertNotContains(response, "Der Nachweis wurde aus dem Entwurf entfernt.")
        self.assertTrue(ApplicationProof.objects.filter(pk=proof.pk).exists())
        self.assertTrue(proof.file.storage.exists(proof.file.name))
        self.assertFalse(ApplicationProofCleanup.objects.exists())

    def test_legacy_removal_database_failure_preserves_file_and_reference(self) -> None:
        self.application.identity_proof.save("identity.png", self.png_upload(), save=True)
        name = self.application.identity_proof.name
        self.client.force_login(self.applicant_user)
        with (
            mock.patch.object(Bewerbung, "save", side_effect=DatabaseError("failed")),
            self.assertLogs("wohnungsverwaltung.views", level="ERROR"),
        ):
            response = self.client.post(
                self.main_url, {"remove_proof": "legacy:identity_proof"}, follow=True
            )
        self.assertContains(response, "Der Nachweis konnte nicht entfernt werden.")
        self.assertNotContains(response, "Der Nachweis wurde aus dem Entwurf entfernt.")
        self.application.refresh_from_db()
        self.assertEqual(self.application.identity_proof.name, name)
        self.assertTrue(self.application.identity_proof.storage.exists(name))
        self.assertFalse(ApplicationProofCleanup.objects.exists())

    def test_removal_is_not_physical_until_commit_and_can_be_rolled_back(self) -> None:
        proof = self.application.proof_files.create(
            category=ApplicationProofCategory.IDENTITY,
            file=self.png_upload(),
            original_name="identity.png",
        )
        self.client.force_login(self.applicant_user)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with transaction.atomic():
                response = self.client.post(self.main_url, {"remove_proof": str(proof.pk)})
                self.assertEqual(response.status_code, 302)
                self.assertFalse(ApplicationProof.objects.filter(pk=proof.pk).exists())
                self.assertTrue(
                    ApplicationProofCleanup.objects.filter(storage_name=proof.file.name).exists()
                )
                self.assertTrue(proof.file.storage.exists(proof.file.name))
                transaction.set_rollback(True)
        self.assertEqual(callbacks, [])
        self.assertTrue(ApplicationProof.objects.filter(pk=proof.pk).exists())
        self.assertTrue(proof.file.storage.exists(proof.file.name))
        self.assertFalse(ApplicationProofCleanup.objects.exists())

    def test_pdf_with_excessive_page_tree_depth_is_rejected(self) -> None:
        from pypdf import PdfWriter
        from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject

        writer = PdfWriter()
        page = writer.add_blank_page(width=72, height=72)
        child = page.indirect_reference
        for _ in range(110):
            node = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Pages"),
                    NameObject("/Kids"): ArrayObject([child]),
                    NameObject("/Count"): NumberObject(1),
                }
            )
            parent = writer._add_object(node)
            child.get_object()[NameObject("/Parent")] = parent
            child = parent
        writer.root_object[NameObject("/Pages")] = child
        buffer = BytesIO()
        writer.write(buffer)
        response = self.applicant_post(
            {
                "action": "save_draft",
                "identity_proof": SimpleUploadedFile(
                    "deep.pdf", buffer.getvalue(), content_type="application/pdf"
                ),
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "gültige PNG- oder PDF-Dateien")
        self.assertFalse(self.application.proof_files.exists())

    def test_pdf_with_unsupported_encryption_is_rejected(self) -> None:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        buffer = BytesIO()
        writer.write(buffer)
        contents = buffer.getvalue().replace(
            b"trailer\n<<",
            b"trailer\n<<\n/Encrypt << /Filter /Unsupported >>",
            1,
        )
        response = self.applicant_post(
            {
                "action": "save_draft",
                "identity_proof": SimpleUploadedFile(
                    "unsupported.pdf", contents, content_type="application/pdf"
                ),
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "verschlüsselte PDF")
        self.assertFalse(self.application.proof_files.exists())

    def test_aes_pdf_without_crypto_support_is_rejected(self) -> None:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        buffer = BytesIO()
        writer.write(buffer)
        encryption = (
            b"/Encrypt << /Filter /Standard /V 5 /R 6 /Length 256 /P -4 /O <"
            + b"00" * 48
            + b"> /U <"
            + b"00" * 48
            + b"> /OE <"
            + b"00" * 32
            + b"> /UE <"
            + b"00" * 32
            + b"> /Perms <"
            + b"00" * 16
            + b"> /CF << /StdCF << /CFM /AESV3 >> >> /StmF /StdCF /StrF /StdCF >>"
        )
        contents = buffer.getvalue().replace(b"trailer\n<<", b"trailer\n<<\n" + encryption, 1)
        response = self.applicant_post(
            {
                "action": "save_draft",
                "identity_proof": SimpleUploadedFile(
                    "aes.pdf", contents, content_type="application/pdf"
                ),
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PDF")
        self.assertFalse(self.application.proof_files.exists())

    def test_pdf_with_incomplete_encryption_metadata_is_rejected(self) -> None:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        buffer = BytesIO()
        writer.write(buffer)
        contents = buffer.getvalue().replace(
            b"trailer\n<<",
            b"trailer\n<<\n/Encrypt << /Filter /Standard >>",
            1,
        )
        response = self.applicant_post(
            {
                "action": "save_draft",
                "identity_proof": SimpleUploadedFile(
                    "incomplete.pdf", contents, content_type="application/pdf"
                ),
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PDF kann nicht verarbeitet werden")
        self.assertFalse(self.application.proof_files.exists())

    def test_cleanup_job_survives_database_failure_after_physical_deletion(self) -> None:
        proof = self.application.proof_files.create(
            category=ApplicationProofCategory.IDENTITY,
            file=self.png_upload(),
            original_name="identity.png",
        )
        with (
            mock.patch.object(
                ApplicationProofCleanup, "delete", side_effect=DatabaseError("failed")
            ),
            self.assertLogs("wohnungsverwaltung.views", level="ERROR"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.applicant_post({"remove_proof": str(proof.pk)})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ApplicationProof.objects.filter(pk=proof.pk).exists())
        self.assertFalse(proof.file.storage.exists(proof.file.name))
        self.assertTrue(
            ApplicationProofCleanup.objects.filter(storage_name=proof.file.name).exists()
        )
        call_command("retry_application_proof_cleanup", stdout=StringIO())
        self.assertFalse(ApplicationProofCleanup.objects.exists())

    def test_pdf_processing_errors_are_form_errors(self) -> None:
        from pypdf.errors import DependencyError, LimitReachedError

        for error_type in (DependencyError, LimitReachedError):
            with self.subTest(error=error_type.__name__):
                with mock.patch(
                    "wohnungsverwaltung.forms.PdfReader", side_effect=error_type("failed")
                ):
                    response = self.applicant_post(
                        {
                            "action": "save_draft",
                            "identity_proof": self.pdf_upload(),
                        }
                    )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "PDF")
                self.assertFalse(self.application.proof_files.exists())

    def test_static_storage_uses_public_permissions(self) -> None:
        from django.core.files.base import ContentFile
        from django.core.files.storage import storages

        with TemporaryDirectory() as directory, self.settings(STATIC_ROOT=directory):
            storage = storages["staticfiles"]
            name = storage.save("nested/probe.css", ContentFile(b"body {}"))
            path = Path(storage.path(name))
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o755)

    def test_proof_cleanup_is_queued_when_storage_delete_fails(self) -> None:
        proof = self.application.proof_files.create(
            category=ApplicationProofCategory.IDENTITY,
            file=self.png_upload("identitaet.png"),
            original_name="identitaet.png",
        )
        storage = proof.file.storage
        self.client.force_login(self.applicant_user)

        with (
            mock.patch.object(storage, "delete", side_effect=OSError("storage unavailable")),
            self.assertLogs("wohnungsverwaltung.views", level="ERROR"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                self.main_url,
                {"remove_proof": str(proof.pk)},
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Der Nachweis wurde aus dem Entwurf entfernt.")
        self.assertFalse(ApplicationProof.objects.filter(pk=proof.pk).exists())
        self.assertTrue(
            ApplicationProofCleanup.objects.filter(storage_name=proof.file.name).exists()
        )
        self.assertTrue(storage.exists(proof.file.name))
        call_command("retry_application_proof_cleanup", stdout=StringIO())
        self.assertFalse(storage.exists(proof.file.name))
        self.assertFalse(ApplicationProofCleanup.objects.exists())

    def test_legacy_proof_cleanup_is_queued_when_storage_delete_fails(self) -> None:
        self.application.identity_proof.save(
            "legacy-identitaet.png",
            self.png_upload("legacy-identitaet.png"),
            save=False,
        )
        self.application.identity_proof_original_name = "legacy-identitaet.png"
        self.application.save(
            update_fields=("identity_proof", "identity_proof_original_name", "updated_at")
        )
        stored_name = self.application.identity_proof.name
        storage = self.application.identity_proof.storage
        self.client.force_login(self.applicant_user)

        with (
            mock.patch.object(storage, "delete", side_effect=OSError("storage unavailable")),
            self.assertLogs("wohnungsverwaltung.views", level="ERROR"),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                self.main_url,
                {"remove_proof": "legacy:identity_proof"},
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Der Nachweis wurde aus dem Entwurf entfernt.")
        self.application.refresh_from_db()
        self.assertFalse(self.application.identity_proof.name)
        self.assertEqual(self.application.identity_proof_original_name, "")
        self.assertTrue(ApplicationProofCleanup.objects.filter(storage_name=stored_name).exists())
        self.assertTrue(storage.exists(stored_name))
        call_command("retry_application_proof_cleanup", stdout=StringIO())
        self.assertFalse(storage.exists(stored_name))
        self.assertFalse(ApplicationProofCleanup.objects.exists())

    def test_storage_failure_cleans_up_files_written_by_the_same_request(self) -> None:
        storage = ApplicationProof._meta.get_field("file").storage
        original_save = storage.save
        save_count = 0

        def save_then_fail_on_second_file(name, content, max_length=None):
            nonlocal save_count
            save_count += 1
            stored_name = original_save(name, content, max_length=max_length)
            if save_count == 2:
                raise OSError("simulated storage failure")
            return stored_name

        with mock.patch.object(storage, "save", side_effect=save_then_fail_on_second_file):
            response = self.applicant_post(
                {
                    "action": "save_draft",
                    "identity_proof": [
                        self.png_upload("erster-nachweis.png"),
                        self.pdf_upload("zweiter-nachweis.pdf"),
                    ],
                }
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dateien konnten nicht sicher gespeichert werden.")
        self.assertEqual(ApplicationProof.objects.filter(application=self.application).count(), 0)
        stored_files = [
            path for path in Path(self.media_directory.name).rglob("*") if path.is_file()
        ]
        self.assertEqual(stored_files, [])

    def test_failed_upload_cleanup_is_persisted_and_can_be_retried(self) -> None:
        storage = ApplicationProof._meta.get_field("file").storage
        original_save = storage.save
        save_count = 0

        def save_then_fail_on_second_file(name, content, max_length=None):
            nonlocal save_count
            save_count += 1
            stored_name = original_save(name, content, max_length=max_length)
            if save_count == 2:
                raise OSError("simulated storage failure")
            return stored_name

        with (
            mock.patch.object(storage, "save", side_effect=save_then_fail_on_second_file),
            mock.patch.object(storage, "delete", side_effect=OSError("storage unavailable")),
        ):
            response = self.applicant_post(
                {
                    "action": "save_draft",
                    "identity_proof": [
                        self.png_upload("erster-nachweis.png"),
                        self.pdf_upload("zweiter-nachweis.pdf"),
                    ],
                }
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dateien konnten nicht sicher gespeichert werden.")
        self.assertEqual(ApplicationProof.objects.filter(application=self.application).count(), 0)
        cleanup_names = set(ApplicationProofCleanup.objects.values_list("storage_name", flat=True))
        self.assertEqual(len(cleanup_names), 2)
        self.assertTrue(all(storage.exists(name) for name in cleanup_names))

        call_command("retry_application_proof_cleanup", stdout=StringIO())

        self.assertFalse(ApplicationProofCleanup.objects.exists())
        self.assertTrue(all(not storage.exists(name) for name in cleanup_names))

    def test_cleanup_retry_failure_keeps_job_and_returns_nonzero_status(self) -> None:
        cleanup = ApplicationProofCleanup.objects.create(storage_name="orphaned/opaque-file")

        with (
            mock.patch(
                "wohnungsverwaltung.management.commands.retry_application_proof_cleanup.default_storage.delete",
                side_effect=OSError("storage unavailable"),
            ),
            self.assertLogs(
                "wohnungsverwaltung.management.commands.retry_application_proof_cleanup",
                level="ERROR",
            ),
        ):
            with self.assertRaises(CommandError):
                call_command("retry_application_proof_cleanup", stdout=StringIO())

        self.assertTrue(ApplicationProofCleanup.objects.filter(pk=cleanup.pk).exists())

    def test_submitted_main_application_is_read_only_for_applicant(self) -> None:
        self.applicant_post(self.complete_upload_data())
        proof = ApplicationProof.objects.get(
            application=self.application,
            category=ApplicationProofCategory.IDENTITY,
        )
        self.client.force_login(self.applicant_user)

        page_response = self.client.get(self.main_url)
        upload_response = self.client.post(
            self.main_url,
            {"action": "save_draft", "identity_proof": self.pdf_upload("nachtrag.pdf")},
        )
        remove_response = self.client.post(self.main_url, {"remove_proof": str(proof.pk)})

        self.assertEqual(page_response.status_code, 200)
        self.assertNotContains(page_response, 'type="file"')
        self.assertContains(page_response, "nicht mehr geändert werden")
        self.assertContains(page_response, "Bitte warten Sie auf die Rückmeldung des Mitarbeiters.")
        self.assertNotContains(page_response, "Nachweise bis zum Ende der Freigabe korrigieren")
        self.assertEqual(upload_response.status_code, 403)
        self.assertEqual(remove_response.status_code, 403)
        self.assertEqual(
            ApplicationProof.objects.filter(application=self.application).count(),
            3,
        )
        self.assertTrue(proof.file.storage.exists(proof.file.name))

    def test_employee_sees_pre_data_but_cannot_view_or_download_main_draft(self) -> None:
        self.applicant_post(
            {"action": "save_draft", "identity_proof": self.png_upload("entwurf.png")}
        )
        proof = ApplicationProof.objects.get(application=self.application)
        self.client.force_login(self.employee_user)

        list_response = self.client.get(
            reverse("wohnungsverwaltung:employee_application_list"), {"wohnung": self.unit.pk}
        )
        detail_response = self.client.get(
            reverse("wohnungsverwaltung:employee_application_detail", args=[self.application.pk])
        )
        download_response = self.client.get(
            reverse(
                "wohnungsverwaltung:employee_application_proof_download",
                args=[self.application.pk, proof.pk],
            )
        )

        self.assertContains(list_response, "Berta Bewerber")
        self.assertEqual(detail_response.status_code, 200)
        self.assertNotContains(detail_response, proof.original_name)
        self.assertNotContains(detail_response, "Sicher herunterladen")
        self.assertEqual(download_response.status_code, 404)

    def test_accepted_pdf_with_trailing_whitespace_can_be_downloaded(self) -> None:
        upload = self.pdf_upload("gehalt.pdf")
        contents = upload.read() + b"\n" * 2048
        data = self.complete_upload_data()
        data["income_proof"] = SimpleUploadedFile(
            "gehalt.pdf", contents, content_type="application/pdf"
        )
        self.assertRedirects(self.applicant_post(data), self.main_url)
        proof = self.application.proof_files.get(category=ApplicationProofCategory.INCOME)
        for user, view in (
            (self.applicant_user, "applicant_application_proof_download"),
            (self.employee_user, "employee_application_proof_download"),
        ):
            with self.subTest(view=view):
                self.client.force_login(user)
                response = self.client.get(
                    reverse(f"wohnungsverwaltung:{view}", args=[self.application.pk, proof.pk])
                )
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(b"".join(response.streaming_content), contents)
                    self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                    self.assertEqual(response["Cache-Control"], "private, no-store")
                    self.assertIn("attachment", response["Content-Disposition"])
                finally:
                    if getattr(response, "file_to_stream", None) is not None:
                        response.file_to_stream.close()

    def test_legacy_pdf_with_trailing_whitespace_can_be_downloaded(self) -> None:
        contents = self.pdf_upload().read() + b"\n" * 2048
        self.application.income_proof.save(
            "legacy.pdf", SimpleUploadedFile("legacy.pdf", contents), save=True
        )
        data = self.complete_upload_data()
        del data["income_proof"]
        self.assertRedirects(self.applicant_post(data), self.main_url)
        for user, view in (
            (self.applicant_user, "applicant_application_document"),
            (self.employee_user, "employee_application_document"),
        ):
            with self.subTest(view=view):
                self.client.force_login(user)
                response = self.client.get(
                    reverse(
                        f"wohnungsverwaltung:{view}", args=[self.application.pk, "income_proof"]
                    )
                )
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(b"".join(response.streaming_content), contents)
                finally:
                    if getattr(response, "file_to_stream", None) is not None:
                        response.file_to_stream.close()

    def test_download_uses_open_stream_when_file_is_removed_on_close(self) -> None:
        self.assertRedirects(self.applicant_post(self.complete_upload_data()), self.main_url)
        proof = self.application.proof_files.get(category=ApplicationProofCategory.INCOME)
        storage = proof.file.storage
        with storage.open(proof.file.name, "rb") as stream:
            contents = stream.read()
        real_close = FieldFile.close

        def remove_after_close(field_file):
            real_close(field_file)
            if field_file.name == proof.file.name:
                storage.delete(field_file.name)

        self.client.force_login(self.employee_user)
        with mock.patch.object(FieldFile, "close", autospec=True, side_effect=remove_after_close):
            response = self.client.get(
                reverse(
                    "wohnungsverwaltung:employee_application_proof_download",
                    args=[self.application.pk, proof.pk],
                )
            )
            try:
                self.assertEqual(response.status_code, 200)
                self.assertTrue(storage.exists(proof.file.name))
                self.assertEqual(b"".join(response.streaming_content), contents)
            finally:
                if getattr(response, "file_to_stream", None) is not None:
                    response.file_to_stream.close()
        self.assertFalse(storage.exists(proof.file.name))

    def test_download_continues_after_file_path_is_removed(self) -> None:
        self.assertRedirects(self.applicant_post(self.complete_upload_data()), self.main_url)
        proof = self.application.proof_files.get(category=ApplicationProofCategory.INCOME)
        storage = proof.file.storage
        with storage.open(proof.file.name, "rb") as stream:
            contents = stream.read()
        real_open = FieldFile.open
        removed = False

        def remove_after_open(field_file, *args, **kwargs):
            nonlocal removed
            stream = real_open(field_file, *args, **kwargs)
            if field_file.name == proof.file.name and not removed:
                storage.delete(field_file.name)
                removed = True
            return stream

        self.client.force_login(self.applicant_user)
        with mock.patch.object(FieldFile, "open", autospec=True, side_effect=remove_after_open):
            response = self.client.get(
                reverse(
                    "wohnungsverwaltung:applicant_application_proof_download",
                    args=[self.application.pk, proof.pk],
                )
            )
            try:
                self.assertEqual(response.status_code, 200)
                self.assertFalse(storage.exists(proof.file.name))
                self.assertEqual(b"".join(response.streaming_content), contents)
            finally:
                if getattr(response, "file_to_stream", None) is not None:
                    response.file_to_stream.close()

    def test_missing_stored_proof_returns_not_found(self) -> None:
        self.assertRedirects(self.applicant_post(self.complete_upload_data()), self.main_url)
        proof = self.application.proof_files.get(category=ApplicationProofCategory.INCOME)
        proof.file.storage.delete(proof.file.name)
        self.client.force_login(self.applicant_user)
        response = self.client.get(
            reverse(
                "wohnungsverwaltung:applicant_application_proof_download",
                args=[self.application.pk, proof.pk],
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_applicant_can_upload_multiple_files_for_one_category(self) -> None:
        response = self.applicant_post(
            {
                "action": "submit",
                "income_proof": [
                    self.pdf_upload("gehalt-januar.pdf"),
                    self.pdf_upload("gehalt-februar.pdf"),
                ],
                "identity_proof": self.png_upload("personalausweis.png"),
                "credit_report_proof": self.pdf_upload("schufa.pdf"),
            }
        )

        self.assertRedirects(response, self.main_url)
        income_proofs = ApplicationProof.objects.filter(
            application=self.application,
            category=ApplicationProofCategory.INCOME,
        )
        self.assertEqual(income_proofs.count(), 2)
        self.assertSetEqual(
            set(income_proofs.values_list("original_name", flat=True)),
            {"gehalt-januar.pdf", "gehalt-februar.pdf"},
        )

    def test_applicant_cannot_upload_a_filename_already_used_on_the_application(self) -> None:
        first_response = self.applicant_post(
            {"action": "save_draft", "identity_proof": self.png_upload("Ausweis.png")}
        )
        self.assertRedirects(first_response, self.main_url)

        duplicate_response = self.applicant_post(
            {"action": "save_draft", "identity_proof": self.png_upload("ausweis.PNG")}
        )

        self.assertEqual(duplicate_response.status_code, 200)
        self.assertIn("identity_proof", duplicate_response.context["form"].errors)
        self.assertContains(duplicate_response, "bereits in dieser Main-Bewerbung verwendet")
        self.assertContains(duplicate_response, "wird dabei nicht unterschieden.")
        self.assertEqual(ApplicationProof.objects.filter(application=self.application).count(), 1)

    def test_applicant_cannot_upload_duplicate_filenames_in_one_submission(self) -> None:
        response = self.applicant_post(
            {
                "action": "save_draft",
                "income_proof": [
                    self.pdf_upload("gehalt.pdf"),
                    self.pdf_upload("GEHALT.PDF"),
                ],
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("income_proof", response.context["form"].errors)
        self.assertEqual(ApplicationProof.objects.filter(application=self.application).count(), 0)

    def test_applicant_cannot_reuse_a_filename_in_another_proof_category(self) -> None:
        response = self.applicant_post(
            {
                "action": "save_draft",
                "identity_proof": self.pdf_upload("scan.pdf"),
                "credit_report_proof": self.pdf_upload("SCAN.PDF"),
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("credit_report_proof", response.context["form"].errors)
        self.assertEqual(ApplicationProof.objects.filter(application=self.application).count(), 0)

    def test_invalid_or_tampered_file_contents_are_rejected(self) -> None:
        data = self.complete_upload_data()
        data["identity_proof"] = SimpleUploadedFile(
            "personalausweis.png", b"<html>kein PNG</html>", content_type="image/png"
        )

        response = self.applicant_post(data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("identity_proof", response.context["form"].errors)
        self.application.refresh_from_db()
        self.assertIsNone(self.application.submitted_at)

    def test_pdf_without_a_valid_header_and_end_marker_is_rejected(self) -> None:
        data = self.complete_upload_data()
        data["credit_report_proof"] = SimpleUploadedFile(
            "schufa.pdf",
            b"%PDF-1.4\nkein vollstaendiges PDF",
            content_type="application/pdf",
        )

        response = self.applicant_post(data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("credit_report_proof", response.context["form"].errors)
        self.application.refresh_from_db()
        self.assertIsNone(self.application.submitted_at)

    def test_png_with_valid_chunk_checksums_but_invalid_image_data_is_rejected(self) -> None:
        response = self.applicant_post(
            {
                "action": "save_draft",
                "identity_proof": self.broken_png_upload(),
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("identity_proof", response.context["form"].errors)
        self.assertFalse(self.application.proof_files.exists())

    def test_pdf_with_header_and_eof_markers_but_invalid_structure_is_rejected(self) -> None:
        response = self.applicant_post(
            {
                "action": "save_draft",
                "credit_report_proof": SimpleUploadedFile(
                    "kein-pdf.pdf",
                    b"%PDF-1.4\nwillkuerliche datei-inhalte\n%%EOF",
                    content_type="application/pdf",
                ),
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("credit_report_proof", response.context["form"].errors)
        self.assertFalse(self.application.proof_files.exists())

    def test_proof_larger_than_eight_mib_is_rejected(self) -> None:
        data = self.complete_upload_data()
        data["income_proof"] = self.pdf_upload(size=8 * 1024 * 1024 + 1)

        response = self.applicant_post(data)

        self.assertEqual(response.status_code, 413)
        self.assertContains(response, "8 MiB", status_code=413)
        self.application.refresh_from_db()
        self.assertIsNone(self.application.submitted_at)
        self.assertFalse(self.application.proof_files.exists())

    def test_total_request_size_is_limited_before_multipart_fields_are_read(self) -> None:
        with self.settings(MAIN_APPLICATION_MAX_REQUEST_SIZE=1024):
            response = self.applicant_post(
                {
                    "action": "save_draft",
                    "income_proof": self.pdf_upload(size=2048),
                }
            )

        self.assertEqual(response.status_code, 413)
        self.assertContains(response, "Gesamtgröße des Uploads", status_code=413)

    def test_locked_application_cannot_be_edited_or_have_documents_downloaded(self) -> None:
        proof = ApplicationProof.objects.create(
            application=self.application,
            category=ApplicationProofCategory.IDENTITY,
            file=self.png_upload("personalausweis.png"),
            original_name="personalausweis.png",
        )
        self.application.main_application_unlocked = False
        self.application.save(update_fields=["main_application_unlocked"])
        self.client.force_login(self.applicant_user)

        response = self.client.get(self.main_url)
        download_response = self.client.get(
            reverse(
                "wohnungsverwaltung:applicant_application_proof_download",
                args=[self.application.pk, proof.pk],
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(download_response.status_code, 404)

    def test_applicant_cannot_access_another_applicants_form_or_files(self) -> None:
        other_application = Bewerbung.objects.create(
            person=self.other_applicant,
            wohnung=self.unit,
            personenanzahl=1,
            ueber_mich="Private Angaben.",
            main_application_unlocked=True,
        )
        foreign_proof = ApplicationProof.objects.create(
            application=other_application,
            category=ApplicationProofCategory.INCOME,
            file=self.pdf_upload("gehalt.pdf"),
            original_name="gehalt.pdf",
        )
        self.applicant_post(self.complete_upload_data())
        self.client.force_login(self.applicant_user)

        foreign_form = self.client.get(
            reverse("wohnungsverwaltung:main_application_status", args=[other_application.pk])
        )
        foreign_document = self.client.get(
            reverse(
                "wohnungsverwaltung:employee_application_document",
                args=[other_application.pk, "income_proof"],
            )
        )
        foreign_proof_download = self.client.get(
            reverse(
                "wohnungsverwaltung:applicant_application_proof_download",
                args=[other_application.pk, foreign_proof.pk],
            )
        )

        self.assertEqual(foreign_form.status_code, 404)
        self.assertEqual(foreign_document.status_code, 403)
        self.assertEqual(foreign_proof_download.status_code, 404)

    def test_applicant_can_download_their_own_saved_proof(self) -> None:
        self.applicant_post({"action": "save_draft", "identity_proof": self.png_upload()})
        proof = ApplicationProof.objects.get(
            application=self.application,
            category=ApplicationProofCategory.IDENTITY,
        )
        self.client.force_login(self.applicant_user)

        response = self.client.get(
            reverse(
                "wohnungsverwaltung:applicant_application_proof_download",
                args=[self.application.pk, proof.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_applicant_cannot_download_proofs_after_withdrawal(self) -> None:
        self.applicant_post({"action": "save_draft", "identity_proof": self.png_upload()})
        proof = ApplicationProof.objects.get(
            application=self.application,
            category=ApplicationProofCategory.IDENTITY,
        )
        self.application.interest_withdrawn_at = datetime.now(UTC)
        self.application.save(update_fields=["interest_withdrawn_at"])
        self.client.force_login(self.applicant_user)

        response = self.client.get(
            reverse(
                "wohnungsverwaltung:applicant_application_proof_download",
                args=[self.application.pk, proof.pk],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_only_employees_can_list_review_and_download_submitted_proofs(self) -> None:
        self.applicant_post(self.complete_upload_data())
        proof = ApplicationProof.objects.get(
            application=self.application,
            category=ApplicationProofCategory.IDENTITY,
        )
        list_url = reverse("wohnungsverwaltung:employee_application_list")
        detail_url = reverse(
            "wohnungsverwaltung:employee_application_detail", args=[self.application.pk]
        )
        download_url = reverse(
            "wohnungsverwaltung:employee_application_proof_download",
            args=[self.application.pk, proof.pk],
        )

        applicant_list = self.client.get(list_url)
        applicant_download = self.client.get(download_url)
        self.client.force_login(self.other_user)
        other_applicant_list = self.client.get(list_url)
        self.client.force_login(self.employee_user)
        employee_list = self.client.get(list_url, {"wohnung": self.unit.pk})
        employee_detail = self.client.get(detail_url)
        employee_download = self.client.get(download_url)

        self.assertEqual(applicant_list.status_code, 403)
        self.assertEqual(applicant_download.status_code, 403)
        self.assertEqual(other_applicant_list.status_code, 403)
        self.assertContains(employee_list, "Berta Bewerber")
        self.assertEqual(employee_detail.status_code, 200)
        self.assertContains(employee_detail, "Gehaltsnachweise")
        self.assertContains(employee_detail, f"({proof.file.size} B)")
        self.assertNotContains(employee_detail, "/media/")
        self.assertEqual(employee_download.status_code, 200)
        self.assertEqual(employee_download["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", employee_download["Content-Disposition"])
        self.assertIn("application/octet-stream", employee_download["Content-Type"])

    def test_employee_can_still_view_and_download_proofs_after_withdrawal(self) -> None:
        self.applicant_post(self.complete_upload_data())
        proof = ApplicationProof.objects.get(
            application=self.application,
            category=ApplicationProofCategory.CREDIT_REPORT,
        )
        self.application.refresh_from_db()
        self.application.interest_withdrawn_at = datetime.now(UTC)
        self.application.save(update_fields=["interest_withdrawn_at"])
        self.client.force_login(self.employee_user)

        list_response = self.client.get(
            reverse("wohnungsverwaltung:employee_application_list"), {"wohnung": self.unit.pk}
        )
        download_response = self.client.get(
            reverse(
                "wohnungsverwaltung:employee_application_proof_download",
                args=[self.application.pk, proof.pk],
            )
        )

        self.assertContains(list_response, "Zurückgezogen")
        self.assertEqual(download_response.status_code, 200)


class MainApplicationMutationLockTests(TransactionTestCase):
    def setUp(self) -> None:
        self.media_directory = TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        media_settings = self.settings(MEDIA_ROOT=self.media_directory.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)

        self.applicant_user = get_user_model().objects.create_user(
            username="lock-test@example.test",
            email="lock-test@example.test",
            password="FjordTanne!4826",
        )
        self.applicant_user.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        self.applicant = Person.objects.create(
            user=self.applicant_user,
            vorname="Lock",
            nachname="Test",
            email="lock-test@example.test",
        )
        unit = Wohnung.objects.create(
            etage=5,
            wohnungsnummer="5.01",
            gebaeudenummer="1",
            status=WohnungStatus.FREE,
        )
        self.application = Bewerbung.objects.create(
            person=self.applicant,
            wohnung=unit,
            personenanzahl=1,
            ueber_mich="Parallelzugriff testen.",
            main_application_unlocked=True,
        )
        self.main_url = reverse(
            "wohnungsverwaltung:main_application_status", args=[self.application.pk]
        )
        self.identity_proof = ApplicationProof.objects.create(
            application=self.application,
            category=ApplicationProofCategory.IDENTITY,
            file=MainApplicationUploadTests.png_upload("identitaet.png"),
            original_name="identitaet.png",
        )
        ApplicationProof.objects.create(
            application=self.application,
            category=ApplicationProofCategory.INCOME,
            file=MainApplicationUploadTests.pdf_upload("gehalt.pdf"),
            original_name="gehalt.pdf",
        )
        ApplicationProof.objects.create(
            application=self.application,
            category=ApplicationProofCategory.CREDIT_REPORT,
            file=MainApplicationUploadTests.pdf_upload("schufa.pdf"),
            original_name="schufa.pdf",
        )

    def post_in_thread(self, data, lock_requested=None):
        close_old_connections()
        client = Client()
        client.force_login(self.applicant_user)

        def observe_lock(execute, sql, params, many, context):
            if "FOR UPDATE" in sql.upper() and lock_requested is not None:
                lock_requested.set()
            return execute(sql, params, many, context)

        try:
            with connection.execute_wrapper(observe_lock):
                return client.post(self.main_url, data)
        finally:
            close_old_connections()

    @skipUnlessDBFeature("has_select_for_update")
    def test_upload_and_removal_wait_until_submission_commits(self) -> None:
        submission_is_saving = Event()
        allow_submission_to_finish = Event()
        upload_lock_requested = Event()
        removal_lock_requested = Event()
        original_save = MainApplicationForm.save_uploaded_proofs

        def pause_submission(form):
            submission_is_saving.set()
            if not allow_submission_to_finish.wait(timeout=10):
                raise TimeoutError("submission test synchronization timed out")
            return original_save(form)

        with ThreadPoolExecutor(max_workers=3) as executor:
            with mock.patch(
                "wohnungsverwaltung.views.MainApplicationForm.save_uploaded_proofs",
                new=pause_submission,
            ):
                try:
                    submission = executor.submit(self.post_in_thread, {"action": "submit"})
                    self.assertTrue(submission_is_saving.wait(timeout=5))
                    upload = executor.submit(
                        self.post_in_thread,
                        {
                            "action": "save_draft",
                            "identity_proof": MainApplicationUploadTests.png_upload("nachtrag.png"),
                        },
                        upload_lock_requested,
                    )
                    removal = executor.submit(
                        self.post_in_thread,
                        {"remove_proof": str(self.identity_proof.pk)},
                        removal_lock_requested,
                    )
                    self.assertTrue(upload_lock_requested.wait(timeout=5))
                    self.assertTrue(removal_lock_requested.wait(timeout=5))
                finally:
                    allow_submission_to_finish.set()

                self.assertEqual(submission.result(timeout=10).status_code, 302)
                self.assertEqual(upload.result(timeout=10).status_code, 403)
                self.assertEqual(removal.result(timeout=10).status_code, 403)

        self.application.refresh_from_db()
        self.assertIsNotNone(self.application.submitted_at)
        self.assertTrue(ApplicationProof.objects.filter(pk=self.identity_proof.pk).exists())
        self.assertEqual(ApplicationProof.objects.filter(application=self.application).count(), 3)

    @skipUnlessDBFeature("has_select_for_update")
    def test_submission_checks_required_proofs_after_concurrent_removal(self) -> None:
        removal_is_saving = Event()
        allow_removal_to_finish = Event()
        submission_lock_requested = Event()
        original_remove = application_views._remove_application_proof

        def pause_removal(request, application, application_id):
            removal_is_saving.set()
            if not allow_removal_to_finish.wait(timeout=10):
                raise TimeoutError("removal test synchronization timed out")
            return original_remove(request, application, application_id)

        with ThreadPoolExecutor(max_workers=2) as executor:
            with mock.patch(
                "wohnungsverwaltung.views._remove_application_proof",
                new=pause_removal,
            ):
                try:
                    removal = executor.submit(
                        self.post_in_thread,
                        {"remove_proof": str(self.identity_proof.pk)},
                    )
                    self.assertTrue(removal_is_saving.wait(timeout=5))
                    submission = executor.submit(
                        self.post_in_thread,
                        {"action": "submit"},
                        submission_lock_requested,
                    )
                    self.assertTrue(submission_lock_requested.wait(timeout=5))
                finally:
                    allow_removal_to_finish.set()

                self.assertEqual(removal.result(timeout=10).status_code, 302)
                submission_response = submission.result(timeout=10)
                self.assertEqual(submission_response.status_code, 200)
                self.assertIn("identity_proof", submission_response.context["form"].errors)

        self.application.refresh_from_db()
        self.assertIsNone(self.application.submitted_at)
        self.assertFalse(ApplicationProof.objects.filter(pk=self.identity_proof.pk).exists())


class CreateTestApplicantCommandTests(TestCase):
    def test_command_creates_a_linked_test_user_and_person(self) -> None:
        call_command(
            "create_test_applicant",
            email="testbewerber@example.test",
            password="FjordTanne!4826",
            stdout=StringIO(),
        )

        user = get_user_model().objects.get(username="testbewerber@example.test")
        person = Person.objects.get(email="testbewerber@example.test")

        self.assertTrue(user.check_password("FjordTanne!4826"))
        self.assertEqual(person.user, user)
        self.assertTrue(user.groups.filter(name=ROLE_APPLICANT).exists())
        self.assertFalse(person.is_employee)
        self.assertIsNone(person.wohnung)


class BewerbungPreviewViewTests(TestCase):
    def setUp(self) -> None:
        self.free_unit = Wohnung.objects.create(
            etage=3,
            wohnungsnummer="3.01",
            gebaeudenummer="1",
            status=WohnungStatus.FREE,
        )
        self.taken_unit = Wohnung.objects.create(
            etage=3,
            wohnungsnummer="3.02",
            gebaeudenummer="1",
            status=WohnungStatus.TAKEN,
        )

    def test_preview_shows_the_application_form_for_free_units(self) -> None:
        response = self.client.get(reverse("wohnungsverwaltung:pre_application_preview"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "wohnungsverwaltung/pre_application_preview.html")
        self.assertContains(response, "Bewerbungsformular – Vorschau")
        self.assertContains(response, "Gewünschte Wohnung")
        self.assertContains(response, "Personen im Haushalt")
        self.assertContains(response, "Ziehen Haustiere mit ein?")
        self.assertContains(response, "Über mich")
        self.assertContains(response, "Abgabe wird mit Registrierung aktiviert")
        self.assertContains(response, "Ja")
        self.assertContains(response, "Nein")
        self.assertContains(response, "enforceMinimumHouseholdSize")
        apartment_queryset = response.context["form"].fields["wohnung"].queryset
        self.assertQuerySetEqual(apartment_queryset, [self.free_unit])
        self.assertEqual(response.context["form"].fields["personenanzahl"].initial, 1)
        self.assertEqual(response.context["form"].fields["personenanzahl"].widget.attrs["min"], 1)

    def test_preview_accepts_only_get_requests(self) -> None:
        response = self.client.post(reverse("wohnungsverwaltung:pre_application_preview"))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers["Allow"], "GET")


class HouseholdSizeMigrationTests(TransactionTestCase):
    migrate_from = [("immobilien", "0007_protokollentwurf")]
    migrate_to = [("immobilien", "0008_alter_bewerbung_personenanzahl_and_more")]

    def setUp(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        executor = MigrationExecutor(connection)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        person = old_apps.get_model("immobilien", "Person").objects.create(
            vorname="Alte",
            nachname="Bewerbung",
            email="alte.bewerbung@example.test",
        )
        apartment = old_apps.get_model("immobilien", "Wohnung").objects.create(
            etage=1,
            wohnungsnummer="1.99",
            gebaeudenummer="1",
        )
        self.application_id = (
            old_apps.get_model("immobilien", "Bewerbung")
            .objects.create(
                person=person,
                wohnung=apartment,
                personenanzahl=0,
            )
            .pk
        )

    def tearDown(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_migration_normalizes_existing_household_size_before_constraint(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        executor = MigrationExecutor(connection)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        application = new_apps.get_model("immobilien", "Bewerbung").objects.get(
            pk=self.application_id
        )

        self.assertEqual(application.personenanzahl, 1)
