import json
from datetime import date

from django.test import TestCase
from django.urls import reverse

from . import tests as fixtures
from .models import ProtokollSchluessel, RaumMerkmal, RaumMerkmalFoto


class ProtocolEditPreservationTests(TestCase):
    valid_form_data = fixtures.HandoverProtocolViewsTests.valid_form_data
    checklist_item_for_photo = fixtures.HandoverProtocolViewsTests.checklist_item_for_photo
    photo_upload = staticmethod(fixtures.HandoverProtocolViewsTests.photo_upload)

    def setUp(self):
        fixtures.HandoverProtocolViewsTests.setUp(self)
        self.protocol, self.room, self.item = self.checklist_item_for_photo()
        self.item.wert = {"text": "Gespeicherte Feststellung", "angaben": {"Anzahl": "3"}}
        self.item.save()
        self.key = ProtokollSchluessel.objects.create(
            protokoll=self.protocol,
            anzahl=2,
            raum_bezeichnung="Wohnungstür",
            aufschrift="A",
            schluesselnummer="42",
        )
        upload = self.photo_upload()
        self.photo = RaumMerkmalFoto.objects.create(
            raum_merkmal=self.item, datei=upload, content_type="image/png", dateigroesse=upload.size
        )
        self.edit_url = reverse(
            "wohnungsverwaltung:handover_protocol_edit", args=[self.protocol.pk]
        )

    def payload(self):
        data = self.valid_form_data()
        data.update(
            {
                "rooms-INITIAL_FORMS": "1",
                "rooms-0-pruefpunkt": str(self.item.pk),
                "rooms-0-raum": str(self.kitchen.pk),
                "rooms-0-bereich": "Küche",
                "rooms-0-merkmal": str(self.room_feature.pk),
                "rooms-0-wert": "Aktualisierte Feststellung",
                "rooms-0-zusatzangaben": json.dumps({"Anzahl": "4"}),
                "keys-INITIAL_FORMS": "1",
                "keys-0-schluessel": str(self.key.pk),
                "keys-0-anzahl": "3",
                "keys-0-raum_bezeichnung": "Wohnungstür",
                "keys-0-aufschrift": "A",
                "keys-0-schluesselnummer": "42",
            }
        )
        return data

    def test_edit_loads_saved_points_keys_details_and_photos(self):
        response = self.client.get(self.edit_url)
        self.assertContains(response, "Gespeicherte Feststellung")
        self.assertContains(response, str(self.item.pk))
        self.assertContains(response, str(self.key.pk))
        self.assertEqual(response.context["room_formset"].forms[0]["raum"].value(), self.kitchen.pk)
        self.assertEqual(response.context["key_formset"].forms[0]["anzahl"].value(), 2)
        self.assertEqual(
            json.loads(response.context["room_formset"].forms[0]["zusatzangaben"].value()),
            {"Anzahl": "3"},
        )
        self.assertContains(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_checklist_item_photo_view",
                args=[self.protocol.pk, self.room.pk, self.item.pk, self.photo.pk],
            ),
        )

    def test_edit_and_repeated_save_update_existing_rows_preserving_photo_bytes(self):
        with self.photo.datei.open("rb") as stream:
            original = stream.read()
        for _ in range(2):
            response = self.client.post(self.edit_url, self.payload())
            self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.key.refresh_from_db()
        self.assertEqual(self.room.raum_merkmale.count(), 1)
        self.assertEqual(self.protocol.protokoll_schluessel.count(), 1)
        self.assertEqual(
            self.item.wert, {"text": "Aktualisierte Feststellung", "angaben": {"Anzahl": "4"}}
        )
        self.assertEqual(self.key.anzahl, 3)
        self.photo.refresh_from_db()
        with self.photo.datei.open("rb") as stream:
            self.assertEqual(original, stream.read())

    def test_saved_due_dates_render_as_valid_browser_date_values(self):
        self.protocol.protokoll_typ = "move_out"
        self.protocol.mieter_zukuenftige_anschrift = "Neue Adresse 1"
        self.protocol.nachbesserung_beschreibung = "Fenster ausbessern"
        self.protocol.nachbesserung_bis = date(2027, 3, 14)
        self.protocol.save()
        self.key.nachlieferung_am = date(2027, 3, 15)
        self.key.save()
        response = self.client.get(self.edit_url)
        self.assertContains(response, 'value="2027-03-14"')
        self.assertContains(response, 'value="2027-03-15"')

    def test_old_draft_without_checkpoint_id_updates_matching_point(self):
        data = self.payload()
        data.pop("rooms-0-pruefpunkt")
        self.assertEqual(self.client.post(self.edit_url, data).status_code, 302)
        self.assertEqual(self.room.raum_merkmale.count(), 1)
        self.assertTrue(self.item.fotos.filter(pk=self.photo.pk).exists())

    def test_omitted_entries_are_preserved(self):
        self.assertEqual(self.client.post(self.edit_url, self.valid_form_data()).status_code, 302)
        self.assertTrue(RaumMerkmal.objects.filter(pk=self.item.pk).exists())
        self.assertTrue(ProtokollSchluessel.objects.filter(pk=self.key.pk).exists())
        self.assertTrue(self.item.fotos.filter(pk=self.photo.pk).exists())

    def test_foreign_checkpoint_and_key_ids_are_rejected(self):
        other, _, other_item = self.checklist_item_for_photo_without_create()
        other_key = ProtokollSchluessel.objects.create(
            protokoll=other, anzahl=1, raum_bezeichnung="Andere"
        )
        data = self.payload()
        data["rooms-0-pruefpunkt"] = str(other_item.pk)
        data["keys-0-schluessel"] = str(other_key.pk)
        response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("pruefpunkt", response.context["room_formset"].forms[0].errors)
        self.assertIn("schluessel", response.context["key_formset"].forms[0].errors)
        self.item.refresh_from_db()
        self.assertEqual(self.item.wert["text"], "Gespeicherte Feststellung")

    def checklist_item_for_photo_without_create(self):
        from .models import Protokoll, Raumprotokoll

        other = Protokoll.objects.get(pk=self.protocol.pk)
        other.pk = None
        other.save()
        room = Raumprotokoll.objects.create(protokoll=other, raum=self.kitchen, name="Küche")
        item = RaumMerkmal.objects.create(
            raumprotokoll=room, merkmal=self.room_feature, wert={"text": "Andere"}
        )
        return other, room, item

    def test_collision_returns_form_error_instead_of_integrity_error(self):
        RaumMerkmal.objects.create(
            raumprotokoll=self.room, merkmal=self.second_room_feature, wert={"text": "Boden"}
        )
        data = self.payload()
        data["rooms-0-merkmal"] = str(self.second_room_feature.pk)
        data["rooms-0-zusatzangaben"] = "{}"
        response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bereits erfasst")
        self.assertEqual(self.room.raum_merkmale.count(), 2)

    def test_explicit_deletion_only_removes_selected_point_and_key(self):
        data = self.payload()
        data["rooms-0-DELETE"] = "on"
        data["keys-0-DELETE"] = "on"
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(self.edit_url, data).status_code, 302)
        self.assertFalse(RaumMerkmal.objects.filter(pk=self.item.pk).exists())
        self.assertFalse(ProtokollSchluessel.objects.filter(pk=self.key.pk).exists())
        self.assertFalse(self.photo.datei.storage.exists(self.photo.datei.name))

    def test_existing_photos_count_toward_upload_limit(self):
        data = self.payload()
        data["rooms-0-fotos"] = self.photo_upload("extra.png", "black")
        with self.settings(HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM=1):
            response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("fotos", response.context["room_formset"].forms[0].errors)
        self.assertTrue(self.item.fotos.filter(pk=self.photo.pk).exists())
