from django.test import TestCase

from . import test_protocol_edit as fixtures


class CheckpointPhotoReplacementTests(TestCase):
    setUp = fixtures.ProtocolEditPreservationTests.setUp
    valid_form_data = fixtures.ProtocolEditPreservationTests.valid_form_data
    checklist_item_for_photo = fixtures.ProtocolEditPreservationTests.checklist_item_for_photo
    photo_upload = staticmethod(fixtures.ProtocolEditPreservationTests.photo_upload)
    payload = fixtures.ProtocolEditPreservationTests.payload

    def test_reselected_identical_photo_survives_checkpoint_replacement(self):
        data = self.payload()
        data["rooms-TOTAL_FORMS"] = "2"
        data["rooms-0-raumprotokoll"] = str(self.room.pk)
        data["rooms-0-DELETE"] = "on"
        data.update(
            {
                "rooms-1-raumprotokoll": str(self.room.pk),
                "rooms-1-raum": str(self.kitchen.pk),
                "rooms-1-bereich": "Küche",
                "rooms-1-merkmal": str(self.room_feature.pk),
                "rooms-1-wert": "Neue Feststellung",
                "rooms-1-fotos": self.photo_upload("replacement.png"),
            }
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 302)
        replacement = self.room.raum_merkmale.get()
        self.assertNotEqual(replacement.pk, self.item.pk)
        self.assertEqual(replacement.fotos.count(), 1)
        photo = replacement.fotos.get()
        self.assertTrue(photo.datei.storage.exists(photo.datei.name))
        self.assertFalse(self.photo.datei.storage.exists(self.photo.datei.name))
