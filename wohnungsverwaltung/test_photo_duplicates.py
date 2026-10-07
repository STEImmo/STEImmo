"""Legacy photo comparisons and unique upload limits (issues #68–#70)."""

from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from . import tests as fixtures
from .models import RaumMerkmalFoto, calculate_photo_checksum


class PhotoComparisonFixture:
    valid_form_data = fixtures.HandoverProtocolViewsTests.valid_form_data
    checklist_item_for_photo = fixtures.HandoverProtocolViewsTests.checklist_item_for_photo
    photo_upload = staticmethod(fixtures.HandoverProtocolViewsTests.photo_upload)

    def setUp(self):
        fixtures.HandoverProtocolViewsTests.setUp(self)
        self.protocol, self.room, self.item = self.checklist_item_for_photo()
        upload = self.photo_upload()
        self.photo = RaumMerkmalFoto.objects.create(
            raum_merkmal=self.item, datei=upload, content_type="image/png", dateigroesse=upload.size
        )
        self.storage = self.photo.datei.storage
        self.upload_url = reverse(
            "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
            args=[self.protocol.pk, self.room.pk, self.item.pk],
        )
        self.edit_url = reverse(
            "wohnungsverwaltung:handover_protocol_edit", args=[self.protocol.pk]
        )
        self.client.raise_request_exception = False

    def stored_paths(self):
        return {path for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file()}

    def inline_payload(self, uploads):
        data = self.valid_form_data()
        data.update(
            {
                "rooms-0-pruefpunkt": str(self.item.pk),
                "rooms-0-raum": str(self.kitchen.pk),
                "rooms-0-bereich": "Küche",
                "rooms-0-merkmal": str(self.room_feature.pk),
                "rooms-0-wert": "Neue Feststellung",
                "rooms-0-fotos": uploads,
            }
        )
        return data

    def set_original_hash(self):
        self.photo.inhalt_hash_sha256 = calculate_photo_checksum(self.photo.datei)
        self.photo.save(update_fields=["inhalt_hash_sha256"])
        self.photo.datei.close()


class LegacyPhotoReadTests(PhotoComparisonFixture, TestCase):
    def test_unreadable_legacy_photo_reports_error_without_storing_new_files(self):
        before = self.stored_paths()
        for error in (FileNotFoundError, PermissionError):
            with self.subTest(error=error.__name__):
                with patch.object(self.storage, "open", side_effect=error("unavailable original")):
                    response = self.client.post(
                        self.upload_url, {"fotos": self.photo_upload("new.png", "red")}, follow=True
                    )
                self.assertContains(response, "Ein vorhandenes Foto konnte nicht gelesen werden.")
                self.assertEqual(self.stored_paths(), before)
                self.assertEqual(self.item.fotos.count(), 1)
                self.photo.refresh_from_db()
                self.assertEqual(self.photo.inhalt_hash_sha256, "")

    def test_upload_succeeds_after_legacy_photo_becomes_readable_again(self):
        with patch.object(self.storage, "open", side_effect=FileNotFoundError):
            self.client.post(self.upload_url, {"fotos": self.photo_upload("new.png", "red")})
        response = self.client.post(
            self.upload_url, {"fotos": self.photo_upload("new.png", "red")}, follow=True
        )
        self.assertContains(response, "Die Fotos wurden am Prüfpunkt gespeichert.")
        self.assertEqual(self.item.fotos.count(), 2)
        self.photo.refresh_from_db()
        self.assertEqual(self.photo.inhalt_hash_sha256, "")

    def test_photo_with_stored_hash_does_not_need_its_original_for_comparison(self):
        self.set_original_hash()
        with patch.object(self.storage, "open", side_effect=FileNotFoundError) as open_file:
            response = self.client.post(
                self.upload_url, {"fotos": self.photo_upload("new.png", "red")}
            )
            open_file.assert_not_called()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.item.fotos.count(), 2)
