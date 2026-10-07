from django.test import TestCase
from django.urls import reverse

from . import test_handover_export as fixtures
from .models import ProtokollStatus


class HandoverArchivedAssignmentTests(TestCase):
    setUp = fixtures.HandoverExportTests.setUp
    url = fixtures.HandoverExportTests.url
    signing_data = fixtures.HandoverExportTests.signing_data
    finalize = fixtures.HandoverExportTests.finalize
    pdf = fixtures.HandoverExportTests.pdf

    def rename_unit(self):
        self.unit.refresh_from_db()
        response = self.client.post(
            reverse("verwaltung:wohnung_edit", args=[self.unit.pk]),
            {
                "gebaeudenummer": "B",
                "wohnungsnummer": "9.99",
                "etage": "2",
                "groesse_qm": "51.25",
                "zimmeranzahl": "2.5",
                "kaltmiete": "650.00",
                "warmmiete": "790.00",
                "kaution": "1300.00",
                "status": self.unit.status,
                "zaehlernummer_wasser_kalt": "WK-1",
                "zaehlernummer_wasser_warm": "WW-1",
                "zaehlernummer_heizung": "HZ-1",
                "zaehlernummer_strom": "ST-1",
                "schluessel-TOTAL_FORMS": "0",
                "schluessel-INITIAL_FORMS": "0",
                "schluessel-MIN_NUM_FORMS": "0",
                "schluessel-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.unit.refresh_from_db()
        self.assertEqual(str(self.unit), "Gebäude B, Wohnung 9.99")

    def test_signed_detail_keeps_archived_assignment_after_regular_unit_edit(self):
        self.finalize()
        snapshot = self.protocol.export_snapshot
        pdf, _reader = self.pdf()
        self.rename_unit()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Gebäude 1, Wohnung 2.04")
        self.assertNotContains(response, "Gebäude B, Wohnung 9.99")
        self.assertNotContains(response, "Historische Wohnungsbezeichnung nicht gesichert")
        self.protocol.refresh_from_db()
        self.assertEqual(self.protocol.status, ProtokollStatus.SIGNED)
        self.assertEqual(self.protocol.wohnung_id, self.unit.pk)
        self.assertEqual(self.protocol.export_snapshot, snapshot)
        self.assertEqual(self.pdf()[0], pdf)

    def test_open_detail_uses_current_assignment(self):
        self.rename_unit()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Gebäude B, Wohnung 9.99")
        self.assertNotContains(response, "Gebäude 1, Wohnung 2.04")
        self.assertNotContains(response, "Historische Wohnungsbezeichnung nicht gesichert")

    def test_legacy_without_snapshot_marks_current_assignment_explicitly(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.save()
        self.rename_unit()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Gebäude B, Wohnung 9.99")
        self.assertContains(response, "Historische Wohnungsbezeichnung nicht gesichert")
        self.assertContains(response, "Aktuelle Bezeichnung")

    def test_legacy_archive_uses_assignment_at_securing_time(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.save()
        self.assertEqual(self.client.post(self.url("pdf_create")).status_code, 302)
        self.protocol.refresh_from_db()
        snapshot = self.protocol.export_snapshot
        pdf, _reader = self.pdf()
        self.rename_unit()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Gebäude 1, Wohnung 2.04")
        self.assertNotContains(response, "Gebäude B, Wohnung 9.99")
        self.protocol.refresh_from_db()
        self.assertTrue(self.protocol.nachtraeglich_gesichert)
        self.assertEqual(self.protocol.export_snapshot, snapshot)
        self.assertEqual(self.pdf()[0], pdf)

    def test_incomplete_legacy_snapshots_fall_back_to_explicit_current_assignment(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.rename_unit()
        for snapshot in [
            [],
            {"rooms": []},
            {"sections": None},
            {"sections": [None, {"title": "Zuordnung", "rows": None}]},
            {"sections": [{"title": "Zuordnung", "rows": [None, ["Wohnung"]]}]},
            {"sections": [{"title": "Zuordnung", "rows": [["Wohnung", ""]]}]},
            {"sections": [{"title": "Zuordnung", "rows": [["Wohnung", {}]]}]},
        ]:
            with self.subTest(snapshot=snapshot):
                self.protocol.export_snapshot = snapshot
                self.protocol.save()
                response = self.client.get(self.url("detail"))
                self.assertContains(response, "Gebäude B, Wohnung 9.99")
                self.assertContains(response, "Historische Wohnungsbezeichnung nicht gesichert")

    def test_archived_assignment_does_not_depend_on_room_snapshot_or_row_position(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.export_snapshot = {
            "sections": [
                {"title": "Zähler", "rows": []},
                {"title": "Zuordnung", "rows": [["Etage", "2"], ["Wohnung", "Gesicherter Name"]]},
            ]
        }
        self.protocol.save()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Gesicherter Name")
        self.assertNotContains(response, "Gebäude 1, Wohnung 2.04")
        self.assertNotContains(response, "Historische Wohnungsbezeichnung nicht gesichert")

    def test_archived_assignment_is_escaped_as_text(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.export_snapshot = {
            "sections": [{"title": "Zuordnung", "rows": [["Wohnung", "Gebäude <b>Alt</b>"]]}]
        }
        self.protocol.save()
        response = self.client.get(self.url("detail"))
        self.assertContains(response, "Gebäude &lt;b&gt;Alt&lt;/b&gt;")
        self.assertNotContains(response, "Gebäude <b>Alt</b>")
