from pathlib import Path
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.db import DatabaseError, connection
from django.test import TestCase
from django.urls import reverse

from . import test_building_view as fixtures
from .models import ApartmentPhoto, HandoverPhotoCleanup


class ApartmentPhotoRecoveryTests(TestCase):
    setUp = fixtures.ApartmentPhotoTests.setUp
    photo = fixtures.ApartmentPhotoTests.photo
    upload = fixtures.ApartmentPhotoTests.upload

    def fail_next_commit(self):
        commit = connection.savepoint_commit
        failed = False

        def fail_once(sid):
            nonlocal failed
            if not failed:
                failed = True
                raise DatabaseError("simulated commit failure")
            return commit(sid)

        return patch.object(connection, "savepoint_commit", side_effect=fail_once)

    def assert_no_photo_files(self):
        self.assertFalse([path for path in Path(self.media.name).rglob("*") if path.is_file()])

    def test_failed_delete_commit_preserves_row_and_original_file(self):
        self.upload()
        photo = ApartmentPhoto.objects.get()
        storage, name = photo.image.storage, photo.image.name
        url = reverse("verwaltung:apartment_photo_delete", args=[self.unit.pk, photo.pk])
        with self.fail_next_commit(), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ApartmentPhoto.objects.filter(pk=photo.pk).exists())
        self.assertTrue(storage.exists(name))

    def test_failed_upload_commit_cleans_file_and_allows_retry(self):
        self.client.force_login(self.employee)
        with self.fail_next_commit():
            response = self.client.post(self.url, {"image": self.photo()})
        self.assertEqual(response.status_code, 200)
        self.assertIn("image", response.context["form"].errors)
        self.assertFalse(ApartmentPhoto.objects.exists())
        self.assert_no_photo_files()
        self.assertEqual(self.upload().status_code, 302)

    def test_storage_failure_after_writing_is_cleaned(self):
        self.client.force_login(self.employee)
        storage = ApartmentPhoto._meta.get_field("image").storage
        save = storage.save

        def write_then_fail(*args, **kwargs):
            save(*args, **kwargs)
            raise OSError("simulated failure after writing")

        with patch.object(storage, "save", side_effect=write_then_fail):
            response = self.client.post(self.url, {"image": self.photo()})
        self.assertEqual(response.status_code, 200)
        self.assertIn("image", response.context["form"].errors)
        self.assertFalse(ApartmentPhoto.objects.exists())
        self.assert_no_photo_files()

    def test_failed_cleanup_after_upload_rollback_is_retryable(self):
        self.client.force_login(self.employee)
        storage = ApartmentPhoto._meta.get_field("image").storage
        with (
            patch.object(ApartmentPhoto, "save", side_effect=DatabaseError("failed insert")),
            patch.object(storage, "delete", side_effect=OSError("unavailable")),
        ):
            response = self.client.post(self.url, {"image": self.photo()})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ApartmentPhoto.objects.exists())
        cleanup = HandoverPhotoCleanup.objects.get()
        self.assertTrue(storage.exists(cleanup.storage_name))
        call_command("retry_handover_photo_cleanup")
        self.assertFalse(HandoverPhotoCleanup.objects.exists())
        self.assert_no_photo_files()

    def test_retry_does_not_delete_a_file_referenced_by_an_apartment_photo(self):
        self.upload()
        photo = ApartmentPhoto.objects.get()
        storage, name = photo.image.storage, photo.image.name
        HandoverPhotoCleanup.objects.create(storage_name=name)
        with self.assertRaises(CommandError):
            call_command("retry_handover_photo_cleanup")
        self.assertTrue(storage.exists(name))
        self.assertTrue(HandoverPhotoCleanup.objects.filter(storage_name=name).exists())

    def test_removing_a_shared_photo_does_not_delete_another_reference(self):
        self.upload()
        photo = ApartmentPhoto.objects.get()
        storage, name = photo.image.storage, photo.image.name
        remaining = ApartmentPhoto.objects.create(apartment=self.unit, image=name)
        url = reverse("verwaltung:apartment_photo_delete", args=[self.unit.pk, photo.pk])
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(url).status_code, 302)
        self.assertTrue(storage.exists(name))
        remaining.refresh_from_db()
        url = reverse("verwaltung:apartment_photo_delete", args=[self.unit.pk, remaining.pk])
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(storage.exists(name))
        self.assertFalse(HandoverPhotoCleanup.objects.exists())
