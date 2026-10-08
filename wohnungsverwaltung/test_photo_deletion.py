"""Durable cleanup when existing protocol photos are removed (issue #67)."""

from unittest.mock import patch

from django.core.management import call_command
from django.db import DatabaseError, transaction
from django.test import TransactionTestCase
from django.urls import reverse

from . import tests as fixtures
from .models import HandoverPhotoCleanup, RaumMerkmalFoto
from .views import _delete_checklist_photos


class PhotoDeletionRecoveryTests(TransactionTestCase):
    valid_form_data = fixtures.HandoverProtocolViewsTests.valid_form_data
    checklist_item_for_photo = fixtures.HandoverProtocolViewsTests.checklist_item_for_photo
    photo_upload = staticmethod(fixtures.HandoverProtocolViewsTests.photo_upload)

    def setUp(self):
        fixtures.HandoverProtocolViewsTests.setUp(self)
        self.protocol, self.room, self.item = self.checklist_item_for_photo()
        self.photo = self.add_photo()
        self.storage = self.photo.datei.storage
        self.client.raise_request_exception = False

    def add_photo(self, color="white"):
        upload = self.photo_upload(color=color)
        return RaumMerkmalFoto.objects.create(
            raum_merkmal=self.item, datei=upload, content_type="image/png", dateigroesse=upload.size
        )

    def assert_failed_delete_is_recoverable(self, url, data=None):
        photo_id = self.photo.pk
        stored_name = self.photo.datei.name
        with patch.object(self.storage, "delete", side_effect=OSError("storage unavailable")):
            response = self.client.post(url, data or {})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RaumMerkmalFoto.objects.filter(pk=photo_id).exists())
        self.assertTrue(self.storage.exists(stored_name))
        self.assertEqual(HandoverPhotoCleanup.objects.get().storage_name, stored_name)
        call_command("retry_handover_photo_cleanup")
        self.assertFalse(self.storage.exists(stored_name))
        self.assertFalse(HandoverPhotoCleanup.objects.exists())

    def test_failed_photo_delete_remains_queued_and_can_be_retried(self):
        self.assert_failed_delete_is_recoverable(
            reverse(
                "wohnungsverwaltung:handover_protocol_checklist_item_photo_delete",
                args=[self.protocol.pk, self.room.pk, self.item.pk, self.photo.pk],
            )
        )

    def test_failed_item_delete_remains_queued_and_can_be_retried(self):
        self.assert_failed_delete_is_recoverable(
            reverse(
                "wohnungsverwaltung:handover_protocol_checklist_item_delete",
                args=[self.protocol.pk, self.room.pk, self.item.pk],
            )
        )

    def test_failed_room_delete_remains_queued_and_can_be_retried(self):
        self.assert_failed_delete_is_recoverable(
            reverse(
                "wohnungsverwaltung:handover_protocol_room_delete",
                args=[self.protocol.pk, self.room.pk],
            )
        )

    def test_failed_inline_item_delete_remains_queued_and_can_be_retried(self):
        data = self.valid_form_data()
        data.update({"rooms-0-pruefpunkt": str(self.item.pk), "rooms-0-DELETE": "on"})
        self.assert_failed_delete_is_recoverable(
            reverse("wohnungsverwaltung:handover_protocol_edit", args=[self.protocol.pk]), data
        )

    def test_one_failed_delete_does_not_stop_other_photo_cleanup(self):
        other_photo = self.add_photo("red")
        failed_name = self.photo.datei.name
        original_delete = self.storage.delete

        def failing_delete(name):
            if name == failed_name:
                raise OSError("one file unavailable")
            original_delete(name)

        with patch.object(self.storage, "delete", side_effect=failing_delete):
            response = self.client.post(
                reverse(
                    "wohnungsverwaltung:handover_protocol_room_delete",
                    args=[self.protocol.pk, self.room.pk],
                )
            )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.storage.exists(other_photo.datei.name))
        self.assertEqual(HandoverPhotoCleanup.objects.get().storage_name, failed_name)
        call_command("retry_handover_photo_cleanup")
        self.assertFalse(self.storage.exists(failed_name))

    def test_rollback_preserves_photo_and_discards_cleanup_job(self):
        photo_id = self.photo.pk
        stored_name = self.photo.datei.name
        with patch.object(self.storage, "delete") as delete:
            with self.assertRaisesMessage(RuntimeError, "rollback"):
                with transaction.atomic():
                    _delete_checklist_photos([self.photo])
                    raise RuntimeError("rollback")
            delete.assert_not_called()
        self.assertTrue(RaumMerkmalFoto.objects.filter(pk=photo_id).exists())
        self.assertTrue(self.storage.exists(stored_name))
        self.assertFalse(HandoverPhotoCleanup.objects.exists())

    def test_successful_delete_removes_photo_file_and_cleanup_job(self):
        photo_id = self.photo.pk
        stored_name = self.photo.datei.name
        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_checklist_item_photo_delete",
                args=[self.protocol.pk, self.room.pk, self.item.pk, photo_id],
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RaumMerkmalFoto.objects.filter(pk=photo_id).exists())
        self.assertFalse(self.storage.exists(stored_name))
        self.assertFalse(HandoverPhotoCleanup.objects.exists())

    def test_failed_queue_creation_preserves_photo_and_never_deletes_file(self):
        photo_id = self.photo.pk
        stored_name = self.photo.datei.name
        with (
            patch.object(HandoverPhotoCleanup.objects, "get_or_create", side_effect=DatabaseError),
            patch.object(self.storage, "delete") as delete,
        ):
            response = self.client.post(
                reverse(
                    "wohnungsverwaltung:handover_protocol_checklist_item_photo_delete",
                    args=[self.protocol.pk, self.room.pk, self.item.pk, photo_id],
                )
            )
            delete.assert_not_called()
        self.assertEqual(response.status_code, 500)
        self.assertTrue(RaumMerkmalFoto.objects.filter(pk=photo_id).exists())
        self.assertTrue(self.storage.exists(stored_name))

    def test_immediate_cleanup_preserves_file_referenced_by_another_photo(self):
        stored_name = self.photo.datei.name
        other_photo = RaumMerkmalFoto.objects.create(
            raum_merkmal=self.item,
            datei=stored_name,
            content_type="image/png",
            dateigroesse=self.photo.dateigroesse,
        )
        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_checklist_item_photo_delete",
                args=[self.protocol.pk, self.room.pk, self.item.pk, self.photo.pk],
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(RaumMerkmalFoto.objects.filter(pk=other_photo.pk).exists())
        self.assertTrue(self.storage.exists(stored_name))
        self.assertEqual(HandoverPhotoCleanup.objects.get().storage_name, stored_name)
