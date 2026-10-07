import copy

from django.test import TestCase

from . import test_handover_export as fixtures
from .models import Person, ProtokollStatus


class HandoverArchivedTenantTests(TestCase):
    setUp = fixtures.HandoverExportTests.setUp
    url = fixtures.HandoverExportTests.url
    signing_data = fixtures.HandoverExportTests.signing_data
    finalize = fixtures.HandoverExportTests.finalize
    pdf = fixtures.HandoverExportTests.pdf

    def rename_person(self):
        Person.objects.filter(pk=self.person.pk).update(nachname="Neuname")

    def test_signed_detail_keeps_tenant_name_and_unchanged_archive(self):
        self.finalize()
        snapshot = copy.deepcopy(self.protocol.export_snapshot)
        pdf, _reader = self.pdf()
        signatures = list(self.protocol.unterschriften.values_list("name", flat=True))
        self.rename_person()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Mia Mieter")
        self.assertNotContains(response, "Mia Neuname")
        self.assertNotContains(response, "Historischer Name nicht gesichert")
        self.protocol.refresh_from_db()
        self.assertEqual(self.protocol.status, ProtokollStatus.SIGNED)
        self.assertEqual(self.protocol.export_snapshot, snapshot)
        self.assertEqual(
            list(self.protocol.unterschriften.values_list("name", flat=True)), signatures
        )
        self.assertEqual(self.pdf()[0], pdf)
        self.client.force_login(self.tenant)
        self.assertEqual(self.pdf()[0], pdf)

    def test_open_detail_uses_current_name_even_with_stale_snapshot(self):
        self.protocol.export_snapshot = {"tenant": "Alter Name"}
        self.protocol.save()
        self.rename_person()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Mia Neuname")
        self.assertNotContains(response, "Alter Name")
        self.assertNotContains(response, "Historischer Name nicht gesichert")

    def test_legacy_without_snapshot_labels_current_name_explicitly(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.save()
        self.rename_person()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Mia Neuname")
        self.assertContains(response, "Historischer Name nicht gesichert")
        self.assertContains(response, "Aktueller Name aus dem Personenstamm")

    def test_legacy_archive_keeps_name_at_securing_time(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.save()
        self.assertEqual(self.client.post(self.url("pdf_create")).status_code, 302)
        self.protocol.refresh_from_db()
        snapshot = copy.deepcopy(self.protocol.export_snapshot)
        pdf, _reader = self.pdf()
        self.rename_person()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Mia Mieter")
        self.assertNotContains(response, "Mia Neuname")
        self.protocol.refresh_from_db()
        self.assertTrue(self.protocol.nachtraeglich_gesichert)
        self.assertEqual(self.protocol.export_snapshot, snapshot)
        self.assertEqual(self.pdf()[0], pdf)

    def test_section_name_is_used_when_top_level_name_is_missing(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.export_snapshot = {
            "sections": [{"title": "Zuordnung", "rows": [["Mieter", "Gesicherter Name"]]}]
        }
        self.protocol.save()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Gesicherter Name")
        self.assertNotContains(response, "Mia Mieter")
        self.assertNotContains(response, "Historischer Name nicht gesichert")

    def test_invalid_names_use_explicit_current_fallback(self):
        self.protocol.status = ProtokollStatus.SIGNED
        for snapshot in [
            [],
            {"tenant": None},
            {"tenant": {}},
            {"tenant": "   "},
            {"sections": [{"title": "Zuordnung", "rows": [["Mieter", None]]}]},
        ]:
            with self.subTest(snapshot=snapshot):
                self.protocol.export_snapshot = snapshot
                self.protocol.save()
                response = self.client.get(self.url("detail"))
                self.assertContains(response, "Mia Mieter")
                self.assertContains(response, "Historischer Name nicht gesichert")

    def test_archived_name_is_escaped_as_text(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.export_snapshot = {"tenant": "Mia <b>Mieter</b>"}
        self.protocol.save()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Mia &lt;b&gt;Mieter&lt;/b&gt;")
        self.assertNotContains(response, "Mia <b>Mieter</b>")
