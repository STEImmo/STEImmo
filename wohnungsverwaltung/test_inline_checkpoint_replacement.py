from pathlib import Path
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase

from . import test_protocol_edit as fixtures
from . import views
from .models import HandoverPhotoCleanup, RaumMerkmal


class InlineCheckpointReplacementTests(TestCase):
    setUp = fixtures.ProtocolEditPreservationTests.setUp
    valid_form_data = fixtures.ProtocolEditPreservationTests.valid_form_data
    checklist_item_for_photo = fixtures.ProtocolEditPreservationTests.checklist_item_for_photo
    photo_upload = staticmethod(fixtures.ProtocolEditPreservationTests.photo_upload)
    payload = fixtures.ProtocolEditPreservationTests.payload

    def replacement_payload(self, color="white", *, deletion_first=True):
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
                "rooms-1-fotos": self.photo_upload("replacement.png", color),
            }
        )
        if not deletion_first:
            first = {key[8:]: value for key, value in data.items() if key.startswith("rooms-0-")}
            second = {key[8:]: value for key, value in data.items() if key.startswith("rooms-1-")}
            data = {
                key: value
                for key, value in data.items()
                if not key.startswith(("rooms-0-", "rooms-1-"))
            }
            data.update({f"rooms-0-{key}": value for key, value in second.items()})
            data.update({f"rooms-1-{key}": value for key, value in first.items()})
        return data

    def assert_replacement_saved(self, data):
        old_id = self.item.pk
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.edit_url, data)
        self.assertEqual(
            response.status_code, 302, response.context and response.context["room_formset"].errors
        )
        replacement = self.room.raum_merkmale.get()
        self.assertNotEqual(replacement.pk, old_id)
        self.assertEqual(replacement.wert["text"], "Neue Feststellung")
        self.assertEqual(replacement.fotos.count(), 1)
        photo = replacement.fotos.get()
        self.assertTrue(photo.datei.storage.exists(photo.datei.name))
        self.assertFalse(self.photo.datei.storage.exists(self.photo.datei.name))
        self.assertFalse(HandoverPhotoCleanup.objects.exists())
        self.assertTrue(self.protocol.protokoll_schluessel.filter(pk=self.key.pk).exists())

    def assert_original_preserved(self):
        self.item.refresh_from_db()
        self.assertEqual(self.item.wert["text"], "Gespeicherte Feststellung")
        self.assertTrue(self.item.fotos.filter(pk=self.photo.pk).exists())
        self.assertTrue(self.photo.datei.storage.exists(self.photo.datei.name))

    def test_reselected_identical_photo_is_saved_on_replacement(self):
        self.assert_replacement_saved(self.replacement_payload())

    def test_different_photo_is_saved_on_replacement(self):
        self.assert_replacement_saved(self.replacement_payload("black"))

    def test_replacement_before_deleted_row_survives(self):
        self.assert_replacement_saved(self.replacement_payload("black", deletion_first=False))

    def test_identical_replacement_before_deleted_row_survives(self):
        self.assert_replacement_saved(self.replacement_payload(deletion_first=False))

    def test_repeated_new_upload_is_rejected_without_losing_original(self):
        data = self.replacement_payload()
        data["rooms-1-fotos"] = [self.photo_upload("one.png"), self.photo_upload("two.png")]
        with self.settings(HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM=1):
            response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dasselbe Foto kann nur einmal ausgewählt werden.")
        self.assert_original_preserved()

    def test_replacement_limit_counts_only_final_photos(self):
        with self.settings(HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM=1):
            self.assert_replacement_saved(self.replacement_payload("black"))

    def test_exceeding_final_limit_preserves_original_point_and_photo(self):
        data = self.replacement_payload()
        data["rooms-1-fotos"] = [
            self.photo_upload("first.png"),
            self.photo_upload("second.png", "black"),
        ]
        with self.settings(HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM=1):
            response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("fotos", response.context["room_formset"].forms[1].errors)
        self.assert_original_preserved()
        self.assertFalse(HandoverPhotoCleanup.objects.exists())

    def test_persisting_counterpart_still_deduplicates_at_capacity(self):
        data = self.payload()
        data.pop("rooms-0-pruefpunkt")
        data["rooms-0-fotos"] = self.photo_upload("same.png")
        with self.settings(HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM=1):
            response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.item.fotos.count(), 1)
        self.assertTrue(self.item.fotos.filter(pk=self.photo.pk).exists())
        self.assertTrue(self.photo.datei.storage.exists(self.photo.datei.name))

    def test_same_point_cannot_be_deleted_and_updated_explicitly(self):
        data = self.replacement_payload()
        data["rooms-1-pruefpunkt"] = str(self.item.pk)
        response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("pruefpunkt", response.context["room_formset"].forms[1].errors)
        self.assert_original_preserved()

    def test_deleted_legacy_photo_is_not_read_for_replacement_deduplication(self):
        with patch.object(self.photo.datei.storage, "open", side_effect=OSError("unavailable")):
            self.assert_replacement_saved(self.replacement_payload())

    def test_replacement_failure_rolls_back_deletion_and_cleans_new_photo(self):
        original = views._save_inline_protocol_entries
        media_root = Path(self.photo.datei.storage.location)
        original_files = {path for path in media_root.rglob("*") if path.is_file()}

        def fail_after_save(*args, **kwargs):
            original(*args, **kwargs)
            raise DatabaseError("simulated replacement failure")

        with (
            patch(
                "wohnungsverwaltung.views._save_inline_protocol_entries",
                side_effect=fail_after_save,
            ),
            self.captureOnCommitCallbacks(execute=True) as callbacks,
        ):
            response = self.client.post(self.edit_url, self.replacement_payload("black"))
        self.assertEqual(response.status_code, 200)
        self.assert_original_preserved()
        self.assertEqual(self.room.raum_merkmale.count(), 1)
        self.assertFalse(HandoverPhotoCleanup.objects.exists())
        self.assertFalse(callbacks)
        self.assertEqual({path for path in media_root.rglob("*") if path.is_file()}, original_files)

    def test_unchanged_second_checkpoint_survives_replacement(self):
        remaining = RaumMerkmal.objects.create(
            raumprotokoll=self.room, merkmal=self.second_room_feature, wert={"text": "Boden"}
        )
        self.assert_replacement_saved_with_other_point(self.replacement_payload(), remaining)

    def assert_replacement_saved_with_other_point(self, data, remaining):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.room.raum_merkmale.filter(pk=remaining.pk).exists())
        replacement = self.room.raum_merkmale.get(merkmal=self.room_feature)
        self.assertEqual(replacement.fotos.count(), 1)
        self.assertNotEqual(replacement.pk, self.item.pk)
