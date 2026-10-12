"""Storage failure regressions for protocol photos (issue #65)."""

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse

from . import tests as fixtures
from .models import HandoverPhotoCleanup, Protokoll, ProtokollEntwurf, RaumMerkmalFoto


class PhotoStorageRecoveryTests(TestCase):
    valid_form_data = fixtures.HandoverProtocolViewsTests.valid_form_data
    checklist_item_for_photo = fixtures.HandoverProtocolViewsTests.checklist_item_for_photo
    photo_upload = staticmethod(fixtures.HandoverProtocolViewsTests.photo_upload)

    def setUp(self):
        fixtures.HandoverProtocolViewsTests.setUp(self)
        self.protocol, self.room, self.item = self.checklist_item_for_photo()
        upload = self.photo_upload()
        self.original_photo = RaumMerkmalFoto.objects.create(
            raum_merkmal=self.item, datei=upload, content_type="image/png", dateigroesse=upload.size
        )
        self.storage = self.original_photo.datei.storage
        self.client.raise_request_exception = False

    def stored_paths(self):
        return {path for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file()}

    def two_uploads(self):
        return [self.photo_upload("red.png", "red"), self.photo_upload("blue.png", "blue")]

    @contextmanager
    def fail_second_storage_save(self, *, after_write=False):
        original_save = self.storage.save
        calls = []

        def failing_save(name, content, max_length=None):
            calls.append(name)
            if len(calls) == 2 and not after_write:
                raise OSError("simulated disk full")
            saved_name = original_save(name, content, max_length=max_length)
            if len(calls) == 2:
                raise OSError("simulated failure after writing")
            return saved_name

        with patch.object(self.storage, "save", side_effect=failing_save):
            yield

    def inline_payload(self):
        data = self.valid_form_data()
        data.update(
            {
                "rooms-0-raum": str(self.kitchen.pk),
                "rooms-0-bereich": "Küche",
                "rooms-0-merkmal": str(self.room_feature.pk),
                "rooms-0-wert": "Neue Feststellung",
                "rooms-0-fotos": self.two_uploads(),
            }
        )
        return data

    def test_batch_upload_failure_cleans_written_files_and_preserves_existing_photos(self):
        url = reverse(
            "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
            args=[self.protocol.pk, self.room.pk, self.item.pk],
        )
        before = self.stored_paths()
        for after_write in (False, True):
            with self.subTest(after_write=after_write):
                with self.fail_second_storage_save(after_write=after_write):
                    response = self.client.post(url, {"fotos": self.two_uploads()}, follow=True)
                self.assertContains(response, "Fotos konnten nicht sicher gespeichert werden")
                self.assertEqual(self.stored_paths(), before)
                self.assertEqual(self.item.fotos.count(), 1)
                self.assertTrue(self.storage.exists(self.original_photo.datei.name))

    def test_inline_creation_failure_rolls_back_protocol_and_photo_files(self):
        before = self.stored_paths()
        with self.fail_second_storage_save():
            response = self.client.post(
                reverse("wohnungsverwaltung:handover_protocol_create"), self.inline_payload()
            )
        self.assertContains(response, "Fotos konnten nicht sicher gespeichert werden")
        self.assertEqual(Protokoll.objects.count(), 1)
        self.assertEqual(self.stored_paths(), before)

    def test_inline_edit_failure_preserves_original_protocol_and_photos(self):
        before = self.stored_paths()
        previous_value = self.item.wert
        previous_readings = self.protocol.heizungsablesungen
        data = self.inline_payload()
        data["rooms-0-pruefpunkt"] = str(self.item.pk)
        data["heizungsablesungen"] = "Geänderter Entwurf"
        with self.fail_second_storage_save():
            response = self.client.post(
                reverse("wohnungsverwaltung:handover_protocol_edit", args=[self.protocol.pk]), data
            )
        self.assertContains(response, "Fotos konnten nicht sicher gespeichert werden")
        self.item.refresh_from_db()
        self.protocol.refresh_from_db()
        self.assertEqual(self.item.wert, previous_value)
        self.assertEqual(self.protocol.heizungsablesungen, previous_readings)
        self.assertEqual(self.item.fotos.count(), 1)
        self.assertEqual(self.stored_paths(), before)

    def test_database_failure_after_photo_write_also_cleans_new_files(self):
        before = self.stored_paths()
        url = reverse(
            "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
            args=[self.protocol.pk, self.room.pk, self.item.pk],
        )
        with patch.object(RaumMerkmalFoto, "save", side_effect=DatabaseError("save failed")):
            response = self.client.post(url, {"fotos": self.two_uploads()}, follow=True)
        self.assertContains(response, "Fotos konnten nicht sicher gespeichert werden")
        self.assertEqual(self.stored_paths(), before)
        self.assertEqual(self.item.fotos.count(), 1)
        self.assertFalse(HandoverPhotoCleanup.objects.exists())

    def test_failed_draft_cleanup_rolls_back_inline_uploads(self):
        before = self.stored_paths()
        data = self.inline_payload()
        data["rooms-0-pruefpunkt"] = str(self.item.pk)
        with patch(
            "wohnungsverwaltung.views._delete_draft",
            side_effect=DatabaseError("draft cleanup failed"),
        ):
            response = self.client.post(
                reverse("wohnungsverwaltung:handover_protocol_edit", args=[self.protocol.pk]), data
            )
        self.assertContains(response, "Fotos konnten nicht sicher gespeichert werden")
        self.assertEqual(self.stored_paths(), before)
        self.assertEqual(self.item.fotos.count(), 1)

    def fail_upload_and_cleanup(self, *, inline=False):
        data = self.inline_payload() if inline else {"fotos": self.two_uploads()}
        url = (
            reverse("wohnungsverwaltung:handover_protocol_create")
            if inline
            else reverse(
                "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
                args=[self.protocol.pk, self.room.pk, self.item.pk],
            )
        )
        with (
            self.fail_second_storage_save(),
            patch.object(self.storage, "delete", side_effect=OSError("cleanup unavailable")),
        ):
            return self.client.post(url, data, follow=True)

    def test_failed_cleanup_remains_queued_and_can_be_retried(self):
        before = self.stored_paths()
        response = self.fail_upload_and_cleanup()
        self.assertContains(response, "Fotos konnten nicht sicher gespeichert werden")
        self.assertEqual(HandoverPhotoCleanup.objects.count(), 2)
        self.assertEqual(len(self.stored_paths() - before), 1)
        call_command("retry_handover_photo_cleanup")
        call_command("retry_handover_photo_cleanup")
        self.assertFalse(HandoverPhotoCleanup.objects.exists())
        self.assertEqual(self.stored_paths(), before)

    def test_inline_rollback_keeps_failed_cleanup_jobs_after_protocol_rollback(self):
        before = self.stored_paths()
        response = self.fail_upload_and_cleanup(inline=True)
        self.assertContains(response, "Fotos konnten nicht sicher gespeichert werden")
        self.assertEqual(Protokoll.objects.count(), 1)
        self.assertEqual(HandoverPhotoCleanup.objects.count(), 2)
        call_command("retry_handover_photo_cleanup")
        self.assertEqual(self.stored_paths(), before)

    def test_failed_retry_preserves_cleanup_jobs_for_a_later_attempt(self):
        self.fail_upload_and_cleanup()
        with patch.object(self.storage, "delete", side_effect=OSError("still unavailable")):
            with self.assertRaises(CommandError):
                call_command("retry_handover_photo_cleanup")
        self.assertEqual(HandoverPhotoCleanup.objects.count(), 2)
        call_command("retry_handover_photo_cleanup")
        self.assertFalse(HandoverPhotoCleanup.objects.exists())

    def test_retry_never_deletes_a_referenced_photo(self):
        HandoverPhotoCleanup.objects.create(storage_name=self.original_photo.datei.name)
        with self.assertRaises(CommandError):
            call_command("retry_handover_photo_cleanup")
        self.assertTrue(self.storage.exists(self.original_photo.datei.name))
        self.assertTrue(HandoverPhotoCleanup.objects.exists())

    def test_successful_upload_keeps_no_cleanup_jobs(self):
        url = reverse(
            "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
            args=[self.protocol.pk, self.room.pk, self.item.pk],
        )
        response = self.client.post(url, {"fotos": self.two_uploads()})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.item.fotos.count(), 3)
        self.assertFalse(HandoverPhotoCleanup.objects.exists())

    def test_cleanup_includes_the_name_returned_by_a_renaming_storage(self):
        original_save = self.storage.save
        calls = []
        before = self.stored_paths()

        def renamed_save(name, content, max_length=None):
            calls.append(name)
            if len(calls) == 2:
                raise OSError("second write failed")
            return original_save(name[:-1] + "x", content, max_length=max_length)

        url = reverse(
            "wohnungsverwaltung:handover_protocol_checklist_item_photo_upload",
            args=[self.protocol.pk, self.room.pk, self.item.pk],
        )
        with patch.object(self.storage, "save", side_effect=renamed_save):
            response = self.client.post(url, {"fotos": self.two_uploads()}, follow=True)
        self.assertContains(response, "Fotos konnten nicht sicher gespeichert werden")
        self.assertEqual(self.stored_paths(), before)
        self.assertEqual(self.item.fotos.count(), 1)

    def test_failed_inline_creation_preserves_the_saved_draft(self):
        import json

        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_draft_save"),
            json.dumps(
                {"scope": "create", "draft": fixtures.HandoverProtocolViewsTests.draft_data(self)}
            ),
            content_type="application/json",
        )
        draft = ProtokollEntwurf.objects.get()
        with self.fail_second_storage_save():
            response = self.client.post(
                reverse("wohnungsverwaltung:handover_protocol_create"), self.inline_payload()
            )
        self.assertContains(response, "Fotos konnten nicht sicher gespeichert werden")
        self.assertTrue(ProtokollEntwurf.objects.filter(pk=draft.pk).exists())
