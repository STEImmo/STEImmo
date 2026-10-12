from django.test import TestCase
from django.urls import reverse

from . import test_handover_export as fixtures
from .models import ProtokollStatus, ProtokollTyp, RaumMerkmalFoto


class HandoverArchivedDisplayTests(TestCase):
    setUp = fixtures.HandoverExportTests.setUp
    url = fixtures.HandoverExportTests.url
    signing_data = fixtures.HandoverExportTests.signing_data
    finalize = fixtures.HandoverExportTests.finalize
    pdf = fixtures.HandoverExportTests.pdf

    def rename_feature(self):
        response = self.client.post(
            reverse("verwaltung:merkmal_edit", args=[self.feature.pk]),
            {
                "bereich": "Neue Gruppe",
                "bezeichnung": "Tür",
                "datentyp": self.feature.datentyp,
                "optionen-TOTAL_FORMS": "0",
                "optionen-INITIAL_FORMS": "0",
                "optionen-MIN_NUM_FORMS": "0",
                "optionen-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.feature.refresh_from_db()
        self.assertEqual(self.feature.bezeichnung, "Tür")

    def test_signed_detail_keeps_archived_labels_and_pdf_after_template_edit(self):
        self.finalize()
        old_snapshot = self.protocol.export_snapshot
        old_pdf, _reader = self.pdf()
        self.rename_feature()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Küche: Fenster")
        self.assertContains(response, "Kratzer am Fenster")
        self.assertNotContains(response, "Neue Gruppe: Tür")
        self.protocol.refresh_from_db()
        self.assertEqual(self.protocol.status, ProtokollStatus.SIGNED)
        self.assertEqual(self.protocol.export_snapshot, old_snapshot)
        self.assertEqual(self.pdf()[0], old_pdf)

    def test_open_detail_uses_current_template_labels(self):
        self.rename_feature()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Neue Gruppe: Tür")
        self.assertNotContains(response, "Küche: Fenster")

    def test_archived_photo_keeps_its_caption_and_can_still_be_enlarged(self):
        upload = fixtures.signature_file()
        photo = RaumMerkmalFoto.objects.create(
            raum_merkmal=self.item, datei=upload, content_type="image/png", dateigroesse=upload.size
        )
        self.finalize()
        self.rename_feature()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, 'data-caption="Küche / Küche: Fenster / Einzug / Foto 1"')
        self.assertContains(response, "data-handover-photo")
        self.assertNotContains(response, "Neue Gruppe: Tür")
        photo_url = reverse(
            "wohnungsverwaltung:handover_protocol_checklist_item_photo_view",
            args=[self.protocol.pk, self.room.pk, self.item.pk, photo.pk],
        )
        self.assertContains(response, photo_url)
        image = self.client.get(photo_url)
        self.assertEqual(image.status_code, 200)
        self.assertTrue(b"".join(image.streaming_content).startswith(b"\x89PNG"))

    def test_move_out_detail_keeps_archived_labels_and_comparison_sides(self):
        self.protocol.protokoll_typ = ProtokollTyp.MOVE_OUT
        self.protocol.mieter_zukuenftige_anschrift = "Neue Straße 4"
        self.protocol.save()
        self.finalize()
        self.rename_feature()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Küche: Fenster")
        self.assertContains(response, "Einzug (Referenz)")
        self.assertContains(response, "Kein Gegenstück erfasst")
        self.assertNotContains(response, "Neue Gruppe: Tür")

    def test_legacy_without_snapshot_is_explicit_and_uses_current_labels(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.save()
        self.rename_feature()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Neue Gruppe: Tür")
        self.assertContains(response, "keine gesicherten Prüfpunktbezeichnungen")

    def test_explicitly_archived_legacy_protocol_keeps_its_secured_labels(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.save()
        response = self.client.post(self.url("pdf_create"))
        self.assertEqual(response.status_code, 302)
        self.protocol.refresh_from_db()
        old_pdf, _reader = self.pdf()
        self.rename_feature()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Küche: Fenster")
        self.assertNotContains(response, "Neue Gruppe: Tür")
        self.assertNotContains(response, "keine gesicherten Prüfpunktbezeichnungen")
        self.assertEqual(self.pdf()[0], old_pdf)
