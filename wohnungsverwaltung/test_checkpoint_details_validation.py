import json

from django.test import TestCase
from django.urls import reverse

from . import tests as fixtures
from .models import Protokoll, RaumMerkmal, Raumprotokoll


class CheckpointDetailsValidationTests(TestCase):
    valid_form_data = fixtures.HandoverProtocolViewsTests.valid_form_data

    def setUp(self):
        fixtures.HandoverProtocolViewsTests.setUp(self)
        response = self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        self.assertEqual(response.status_code, 302)
        self.protocol = Protokoll.objects.get()
        self.room = Raumprotokoll.objects.create(
            protokoll=self.protocol, raum=self.kitchen, name=self.kitchen.name
        )
        self.item = RaumMerkmal.objects.create(
            raumprotokoll=self.room,
            merkmal=self.room_feature,
            wert={"text": "Gespeicherte Feststellung", "angaben": {"Anzahl": "2"}},
        )
        self.second_room_feature.optionen = ["Anzahl"]
        self.second_room_feature.save()
        self.original_protocol = Protokoll.objects.values().get(pk=self.protocol.pk)
        self.original_room = Raumprotokoll.objects.values().get(pk=self.room.pk)
        self.original_item = RaumMerkmal.objects.values().get(pk=self.item.pk)
        self.client.raise_request_exception = False

    def invalid_details(self):
        return {
            "null_character": json.dumps({"Anzahl": "x\x00y"}),
            "unpaired_high_surrogate": json.dumps({"Anzahl": "\ud800"}),
            "unpaired_low_surrogate": json.dumps({"Anzahl": "\udfff"}),
            "excessive_nesting": "[" * 10000 + "0" + "]" * 10000,
            "oversized_integer": '{"Anzahl":' + "1" * 4301 + "}",
        }

    def inline_payload(self, details, *, edit=False):
        payload = self.valid_form_data() | {
            "rooms-0-raum": str(self.kitchen.pk),
            "rooms-0-bereich": self.room_feature.bereich,
            "rooms-0-merkmal": str(self.room_feature.pk),
            "rooms-0-wert": "Neue Feststellung",
            "rooms-0-zusatzangaben": details,
        }
        if edit:
            payload |= {
                "rooms-INITIAL_FORMS": "1",
                "rooms-0-raumprotokoll": str(self.room.pk),
                "rooms-0-pruefpunkt": str(self.item.pk),
                "zaehlerstand_strom": "99.00",
            }
        return payload

    def assert_stored_data_unchanged(self):
        self.assertEqual(
            Protokoll.objects.values().get(pk=self.protocol.pk), self.original_protocol
        )
        self.assertEqual(Raumprotokoll.objects.values().get(pk=self.room.pk), self.original_room)
        self.assertEqual(RaumMerkmal.objects.values().get(pk=self.item.pk), self.original_item)
        self.assertEqual(Protokoll.objects.count(), 1)
        self.assertEqual(Raumprotokoll.objects.count(), 1)
        self.assertEqual(RaumMerkmal.objects.count(), 1)

    def test_inline_creation_rejects_invalid_details_without_creating_protocol(self):
        for case, details in self.invalid_details().items():
            with self.subTest(case=case):
                response = self.client.post(
                    reverse("wohnungsverwaltung:handover_protocol_create"),
                    self.inline_payload(details),
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("zusatzangaben", response.context["room_formset"].forms[0].errors)
                self.assertContains(response, "Die zusätzlichen Angaben sind ungültig.")
                self.assert_stored_data_unchanged()

    def test_inline_edit_rejects_invalid_details_and_preserves_protocol(self):
        for case, details in self.invalid_details().items():
            with self.subTest(case=case):
                response = self.client.post(
                    reverse("wohnungsverwaltung:handover_protocol_edit", args=[self.protocol.pk]),
                    self.inline_payload(details, edit=True),
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("zusatzangaben", response.context["room_formset"].forms[0].errors)
                self.assertContains(response, "Die zusätzlichen Angaben sind ungültig.")
                self.assert_stored_data_unchanged()

    def test_room_form_rejects_invalid_details_without_changing_checkpoints(self):
        for case, details in self.invalid_details().items():
            with self.subTest(case=case):
                response = self.client.post(
                    reverse(
                        "wohnungsverwaltung:handover_protocol_room_detail",
                        args=[self.protocol.pk, self.room.pk],
                    ),
                    {
                        "bereich": self.second_room_feature.bereich,
                        "merkmal": str(self.second_room_feature.pk),
                        "wert": "Neue Feststellung",
                        "zusatzangaben": details,
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("zusatzangaben", response.context["form"].errors)
                self.assertContains(response, "Die zusätzlichen Angaben sind ungültig.")
                self.assert_stored_data_unchanged()

    def test_valid_unicode_and_literal_escapes_are_preserved_on_all_routes(self):
        value = "Küche, Prüfung 😀 und die Zeichenfolge \\u0000"
        details = json.dumps({"Anzahl": value})
        response = self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.inline_payload(details)
        )
        self.assertEqual(response.status_code, 302)
        created_item = RaumMerkmal.objects.exclude(pk=self.item.pk).get()
        self.assertEqual(created_item.wert["angaben"], {"Anzahl": value})

        response = self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_edit", args=[self.protocol.pk]),
            self.inline_payload(details, edit=True),
        )
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.wert["angaben"], {"Anzahl": value})

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_room_detail",
                args=[self.protocol.pk, self.room.pk],
            ),
            {
                "bereich": self.second_room_feature.bereich,
                "merkmal": str(self.second_room_feature.pk),
                "wert": "Neue Feststellung",
                "zusatzangaben": details,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.room.raum_merkmale.get(merkmal=self.second_room_feature).wert["angaben"],
            {"Anzahl": value},
        )
