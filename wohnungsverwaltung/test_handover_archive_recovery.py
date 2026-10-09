from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections
from django.test import TestCase, TransactionTestCase

from . import test_handover_export as fixtures
from .models import ProtokollStatus


class HandoverArchiveRecoveryTests(TestCase):
    setUp = fixtures.HandoverExportTests.setUp
    url = fixtures.HandoverExportTests.url
    signing_data = fixtures.HandoverExportTests.signing_data
    finalize = fixtures.HandoverExportTests.finalize

    def files(self):
        return sorted(path for path in Path(self.directory.name).rglob("*") if path.is_file())

    def cleanup_model(self):
        return apps.get_model("immobilien", "HandoverArchiveCleanup")

    def assert_open_without_archive(self):
        self.protocol.refresh_from_db()
        self.assertEqual(self.protocol.status, ProtokollStatus.OPEN)
        self.assertFalse(self.protocol.dokument_pfad)
        self.assertFalse(self.protocol.export_snapshot)
        self.assertFalse(self.protocol.unterschriften.exists())

    def fail_after_write(self, name, content, *args, **kwargs):
        saved = self.original_save(name, content, *args, **kwargs)
        if name.endswith(self.failed_suffix):
            raise OSError("Storage failed after writing.")
        return saved

    def test_signature_written_before_failure_is_removed(self):
        data = self.signing_data()
        self.original_save = default_storage.save
        self.failed_suffix = "mitarbeiter.png"
        with patch.object(default_storage, "save", side_effect=self.fail_after_write):
            response = self.client.post(self.url("confirm"), data)
        self.assertEqual(response.status_code, 503)
        self.assert_open_without_archive()
        self.assertEqual(self.files(), [])

    def test_pdf_written_before_failure_is_removed(self):
        data = self.signing_data()
        self.original_save = default_storage.save
        self.failed_suffix = "protokoll.pdf"
        with patch.object(default_storage, "save", side_effect=self.fail_after_write):
            response = self.client.post(self.url("confirm"), data)
        self.assertEqual(response.status_code, 503)
        self.assert_open_without_archive()
        self.assertEqual(self.files(), [])

    def test_legacy_pdf_written_before_failure_is_removed(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.save()
        self.original_save = default_storage.save
        self.failed_suffix = "protokoll.pdf"
        with patch.object(default_storage, "save", side_effect=self.fail_after_write):
            response = self.client.post(self.url("pdf_create"))
        self.assertEqual(response.status_code, 503)
        self.protocol.refresh_from_db()
        self.assertEqual(self.protocol.status, ProtokollStatus.SIGNED)
        self.assertFalse(self.protocol.dokument_pfad)
        self.assertFalse(self.protocol.export_snapshot)
        self.assertEqual(self.files(), [])

    def test_cleanup_failure_retains_jobs_until_retry_succeeds(self):
        data = self.signing_data()
        self.original_save = default_storage.save
        self.failed_suffix = "protokoll.pdf"
        with (
            patch.object(default_storage, "save", side_effect=self.fail_after_write),
            patch.object(default_storage, "delete", side_effect=OSError("Storage unavailable.")),
        ):
            response = self.client.post(self.url("confirm"), data)
        self.assertEqual(response.status_code, 503)
        self.assert_open_without_archive()
        self.assertEqual(len(self.files()), 3)
        self.assertEqual(self.cleanup_model().objects.count(), 3)
        call_command("retry_handover_archive_cleanup", stdout=StringIO())
        self.assertEqual(self.files(), [])
        self.assertFalse(self.cleanup_model().objects.exists())
        call_command("retry_handover_archive_cleanup", stdout=StringIO())

    def test_failed_retry_preserves_files_and_jobs(self):
        path = default_storage.save("private/handovers/test/pending.pdf", fixtures.signature_file())
        self.cleanup_model().objects.create(storage_name=path)
        with patch.object(default_storage, "delete", side_effect=OSError("Storage unavailable.")):
            with self.assertRaises(CommandError):
                call_command("retry_handover_archive_cleanup", stdout=StringIO())
        self.assertTrue(default_storage.exists(path))
        self.assertTrue(self.cleanup_model().objects.filter(storage_name=path).exists())

    def test_retry_does_not_delete_referenced_pdf_or_signature(self):
        self.finalize()
        paths = [self.protocol.dokument_pfad, self.protocol.unterschriften.first().datei]
        for path in paths:
            self.cleanup_model().objects.create(storage_name=path)
        with self.assertRaises(CommandError):
            call_command("retry_handover_archive_cleanup", stdout=StringIO())
        self.assertTrue(all(default_storage.exists(path) for path in paths))
        self.assertEqual(len(self.files()), 3)
        self.assertEqual(self.cleanup_model().objects.count(), 2)

    def test_successful_archive_has_no_cleanup_jobs(self):
        self.finalize()
        self.assertEqual(len(self.files()), 3)
        self.assertEqual(self.protocol.unterschriften.count(), 2)
        self.assertFalse(self.cleanup_model().objects.exists())

    def test_backend_renamed_file_is_also_cleaned_after_database_failure(self):
        data = self.signing_data()
        original_save = default_storage.save

        def renamed_save(name, content, *args, **kwargs):
            return original_save(name + ".renamed", content, *args, **kwargs)

        with (
            patch.object(default_storage, "save", side_effect=renamed_save),
            patch(
                "wohnungsverwaltung.handover_export.ProtokollUnterschrift.objects.create",
                side_effect=ValueError("Synthetic database failure."),
            ),
        ):
            response = self.client.post(self.url("confirm"), data)
        self.assertEqual(response.status_code, 503)
        self.assert_open_without_archive()
        self.assertEqual(self.files(), [])


class HandoverArchiveCleanupPersistenceTests(TransactionTestCase):
    setUp = fixtures.HandoverExportTests.setUp
    url = fixtures.HandoverExportTests.url
    signing_data = fixtures.HandoverExportTests.signing_data

    def test_cleanup_job_survives_rollback_and_a_new_database_connection(self):
        data = self.signing_data()
        original_save = default_storage.save

        def fail_after_signature(name, content, *args, **kwargs):
            original_save(name, content, *args, **kwargs)
            raise OSError("Storage failed after writing.")

        with (
            patch.object(default_storage, "save", side_effect=fail_after_signature),
            patch.object(default_storage, "delete", side_effect=OSError("Storage unavailable.")),
        ):
            response = self.client.post(self.url("confirm"), data)
        self.assertEqual(response.status_code, 503)
        connections.close_all()
        cleanup_model = apps.get_model("immobilien", "HandoverArchiveCleanup")
        job = cleanup_model.objects.get()
        self.assertTrue(default_storage.exists(job.storage_name))
        call_command("retry_handover_archive_cleanup", stdout=StringIO())
        self.assertFalse(default_storage.exists(job.storage_name))
        self.assertFalse(cleanup_model.objects.exists())
