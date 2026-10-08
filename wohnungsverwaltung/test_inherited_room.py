"""Final room assignment must precede checkpoint validation (issue #66)."""

from django.test import TestCase
from django.urls import reverse

from . import tests as fixtures
from .models import Raum, RaumMerkmal, RaumMerkmalFoto, Raumprotokoll


class InheritedRoomValidationTests(TestCase):
    valid_form_data = fixtures.HandoverProtocolViewsTests.valid_form_data
    checklist_item_for_photo = fixtures.HandoverProtocolViewsTests.checklist_item_for_photo
    photo_upload = staticmethod(fixtures.HandoverProtocolViewsTests.photo_upload)

    def setUp(self):
        fixtures.HandoverProtocolViewsTests.setUp(self)
        self.protocol, self.room, self.item = self.checklist_item_for_photo()
        photo = self.photo_upload()
        self.original_photo = RaumMerkmalFoto.objects.create(
            raum_merkmal=self.item, datei=photo, content_type="image/png", dateigroesse=photo.size
        )
        self.edit_url = reverse(
            "wohnungsverwaltung:handover_protocol_edit", args=[self.protocol.pk]
        )
        self.client.raise_request_exception = False

    def inherited_payload(self):
        data = self.valid_form_data()
        data.update(
            {
                "rooms-TOTAL_FORMS": "2",
                "rooms-0-raum": str(self.kitchen.pk),
                "rooms-0-bereich": "Küche",
                "rooms-0-merkmal": str(self.second_room_feature.pk),
                "rooms-0-wert": "Boden",
                "rooms-1-raum": "",
                "rooms-1-bereich": "Küche",
                "rooms-1-merkmal": str(self.room_feature.pk),
                "rooms-1-wert": "Neue Feststellung",
            }
        )
        return data

    def test_inherited_room_counts_photos_of_the_matching_old_draft_checkpoint(self):
        data = self.inherited_payload()
        data["rooms-1-fotos"] = self.photo_upload("new.png", "blue")
        previous_value = self.item.wert
        with self.settings(HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM=1):
            response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("fotos", response.context["room_formset"].forms[1].errors)
        self.item.refresh_from_db()
        self.assertEqual(self.item.wert, previous_value)
        self.assertEqual(self.item.fotos.count(), 1)
        self.assertEqual(self.room.raum_merkmale.count(), 1)

    def test_old_draft_with_inherited_room_still_saves_within_the_photo_limit(self):
        data = self.inherited_payload()
        data["rooms-1-fotos"] = self.photo_upload("new.png", "blue")
        with self.settings(HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM=2):
            response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.item.fotos.count(), 2)
        self.assertEqual(self.room.raum_merkmale.count(), 2)
        self.item.refresh_from_db()
        self.assertEqual(self.item.wert["text"], "Neue Feststellung")

    def test_inherited_room_rejects_a_collision_when_moving_an_existing_checkpoint(self):
        other_room_master = Raum.objects.create(wohnung=self.wohnung, name="Andere Küche")
        other_room = Raumprotokoll.objects.create(
            protokoll=self.protocol, raum=other_room_master, name=other_room_master.name
        )
        other_item = RaumMerkmal.objects.create(
            raumprotokoll=other_room,
            merkmal=self.room_feature,
            wert={"text": "Andere Feststellung"},
        )
        data = self.inherited_payload()
        data["rooms-1-pruefpunkt"] = str(other_item.pk)
        response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("merkmal", response.context["room_formset"].forms[1].errors)
        other_item.refresh_from_db()
        self.assertEqual(other_item.raumprotokoll_id, other_room.pk)
        self.assertEqual(other_item.wert["text"], "Andere Feststellung")

    def test_invalid_leading_room_is_not_replaced_by_inherited_assignment(self):
        data = self.inherited_payload()
        data["rooms-0-raum"] = "invalid-uuid"
        response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("raum", response.context["room_formset"].forms[0].errors)
        self.assertIn("raum", response.context["room_formset"].forms[1].errors)
        self.assertEqual(self.room.raum_merkmale.count(), 1)

    def test_other_error_on_leading_checkpoint_preserves_inherited_room(self):
        data = self.inherited_payload()
        data["rooms-0-wert"] = ""
        response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 200)
        forms = response.context["room_formset"].forms
        self.assertIn("wert", forms[0].errors)
        self.assertNotIn("raum", forms[1].errors)
        self.assertEqual(forms[1].cleaned_data["raum"], self.kitchen)
        self.assertEqual(self.room.raum_merkmale.count(), 1)
