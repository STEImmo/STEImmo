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


class InlineLegacyPhotoTests(PhotoComparisonFixture, TestCase):
    def test_inline_edit_skips_legacy_duplicate_with_or_without_checkpoint_id(self):
        before = self.stored_paths()
        for with_id in (True, False):
            with self.subTest(with_id=with_id):
                data = self.inline_payload(self.photo_upload("identical.png"))
                if not with_id:
                    data.pop("rooms-0-pruefpunkt")
                response = self.client.post(self.edit_url, data)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(self.item.fotos.count(), 1)
                self.assertEqual(self.stored_paths(), before)
                self.photo.refresh_from_db()
                self.assertEqual(self.photo.inhalt_hash_sha256, "")
                self.item.refresh_from_db()
                self.assertEqual(self.item.wert["text"], "Neue Feststellung")

    def test_inline_edit_stores_only_new_content_from_mixed_legacy_upload(self):
        before = self.stored_paths()
        response = self.client.post(
            self.edit_url,
            self.inline_payload(
                [self.photo_upload("identical.png"), self.photo_upload("new.png", "red")]
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.item.fotos.count(), 2)
        self.assertEqual(len(self.stored_paths() - before), 1)
        self.photo.refresh_from_db()
        self.assertEqual(self.photo.inhalt_hash_sha256, "")

    def test_inline_edit_rejects_unreadable_legacy_comparison_without_changing_protocol(self):
        before = self.stored_paths()
        previous_value = self.item.wert
        for error in (FileNotFoundError, PermissionError):
            with self.subTest(error=error.__name__):
                with patch.object(self.storage, "open", side_effect=error("unavailable original")):
                    response = self.client.post(
                        self.edit_url, self.inline_payload(self.photo_upload("new.png", "red"))
                    )
                self.assertContains(response, "Ein vorhandenes Foto konnte nicht gelesen werden.")
                self.assertIn("fotos", response.context["room_formset"].forms[0].errors)
                self.item.refresh_from_db()
                self.assertEqual(self.item.wert, previous_value)
                self.assertEqual(self.item.fotos.count(), 1)
                self.assertEqual(self.stored_paths(), before)

    def test_inline_edit_without_new_photos_does_not_read_legacy_files(self):
        data = self.inline_payload([])
        data.pop("rooms-0-fotos")
        with patch.object(self.storage, "open", side_effect=FileNotFoundError) as open_file:
            response = self.client.post(self.edit_url, data)
            open_file.assert_not_called()
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.wert["text"], "Neue Feststellung")


class UniquePhotoLimitTests(PhotoComparisonFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.set_original_hash()

    def test_direct_duplicate_at_full_capacity_is_accepted_without_writes(self):
        before = self.stored_paths()
        with self.settings(HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM=1):
            response = self.client.post(
                self.upload_url, {"fotos": self.photo_upload("identical.png")}, follow=True
            )
        self.assertContains(response, "Dieses Foto ist für den Prüfpunkt bereits gespeichert.")
        self.assertEqual(self.item.fotos.count(), 1)
        self.assertEqual(self.stored_paths(), before)

    def test_inline_duplicate_at_full_capacity_does_not_block_other_changes(self):
        before = self.stored_paths()
        with self.settings(HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM=1):
            response = self.client.post(
                self.edit_url, self.inline_payload(self.photo_upload("identical.png"))
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.item.fotos.count(), 1)
        self.assertEqual(self.stored_paths(), before)
        self.item.refresh_from_db()
        self.assertEqual(self.item.wert["text"], "Neue Feststellung")

    def test_direct_mixed_upload_uses_only_one_available_slot(self):
        before = self.stored_paths()
        with self.settings(HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM=2):
            response = self.client.post(
                self.upload_url,
                {
                    "fotos": [
                        self.photo_upload("identical.png"),
                        self.photo_upload("new.png", "red"),
                    ]
                },
                follow=True,
            )
        self.assertContains(response, "Die Fotos wurden am Prüfpunkt gespeichert.")
        self.assertEqual(self.item.fotos.count(), 2)
        self.assertEqual(len(self.stored_paths() - before), 1)

    def test_inherited_room_counts_only_new_content_of_legacy_mixed_upload(self):
        self.photo.inhalt_hash_sha256 = ""
        self.photo.save(update_fields=["inhalt_hash_sha256"])
        before = self.stored_paths()
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
                "rooms-1-fotos": [
                    self.photo_upload("identical.png"),
                    self.photo_upload("new.png", "red"),
                ],
            }
        )
        with self.settings(HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM=2):
            response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.item.fotos.count(), 2)
        self.assertEqual(len(self.stored_paths() - before), 1)
        self.photo.refresh_from_db()
        self.assertEqual(self.photo.inhalt_hash_sha256, "")

    def test_direct_truly_new_upload_over_limit_is_rejected_without_writes(self):
        before = self.stored_paths()
        with self.settings(HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM=2):
            response = self.client.post(
                self.upload_url,
                {
                    "fotos": [
                        self.photo_upload("red.png", "red"),
                        self.photo_upload("blue.png", "blue"),
                    ]
                },
                follow=True,
            )
        self.assertContains(response, "Für einen Prüfpunkt sind höchstens 2 Fotos erlaubt.")
        self.assertEqual(self.item.fotos.count(), 1)
        self.assertEqual(self.stored_paths(), before)

    def test_inline_truly_new_upload_over_limit_preserves_checkpoint_and_files(self):
        before = self.stored_paths()
        previous_value = self.item.wert
        with self.settings(HANDOVER_PHOTO_MAX_PER_CHECKLIST_ITEM=2):
            response = self.client.post(
                self.edit_url,
                self.inline_payload(
                    [self.photo_upload("red.png", "red"), self.photo_upload("blue.png", "blue")]
                ),
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("fotos", response.context["room_formset"].forms[0].errors)
        self.item.refresh_from_db()
        self.assertEqual(self.item.wert, previous_value)
        self.assertEqual(self.item.fotos.count(), 1)
        self.assertEqual(self.stored_paths(), before)
