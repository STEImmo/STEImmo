import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import DatabaseError, close_old_connections
from django.test import Client, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse

from . import test_handover_export as fixtures
from .access import ROLE_APPLICANT
from .handover_export import render_pdf
from .models import Bewerbung, Person, ProtokollStatus, ProtokollTyp, WohnungQuerySet, WohnungStatus


class HandoverAvailabilityTests(TestCase):
    setUp = fixtures.HandoverExportTests.setUp
    url = fixtures.HandoverExportTests.url
    signing_data = fixtures.HandoverExportTests.signing_data
    finalize = fixtures.HandoverExportTests.finalize

    def assert_unit_status(self, expected):
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, expected)

    def prepare_move_out(self):
        self.unit.status = WohnungStatus.TAKEN
        self.unit.save(update_fields=["status"])
        self.protocol.protokoll_typ = ProtokollTyp.MOVE_OUT
        self.protocol.mieter_zukuenftige_anschrift = "Neue Straße 4"
        self.protocol.save()

    def test_confirmed_move_in_is_taken_and_removed_from_public_search(self):
        self.finalize()
        self.assert_unit_status(WohnungStatus.TAKEN)
        response = self.client.get(reverse("wohnungsverwaltung_public:apartment_search"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["wohnungen"].filter(pk=self.unit.pk).exists())
        response = self.client.get(
            reverse("wohnungsverwaltung_public:apartment_detail_placeholder", args=[self.unit.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_confirmed_move_out_is_free_and_returns_to_public_search(self):
        self.prepare_move_out()
        self.finalize()
        self.assert_unit_status(WohnungStatus.FREE)
        response = self.client.get(reverse("wohnungsverwaltung_public:apartment_search"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["wohnungen"].filter(pk=self.unit.pk).exists())

    def test_new_applicant_cannot_apply_after_confirmed_move_in(self):
        self.finalize()
        applicant = get_user_model().objects.create_user(username="new-applicant")
        applicant.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        Person.objects.create(
            user=applicant, vorname="Neue", nachname="Bewerbung", email="neu@example.test"
        )
        client = Client()
        client.force_login(applicant)
        response = client.post(
            reverse("wohnungsverwaltung:pre_application_create_for_unit", args=[self.unit.pk]),
            {
                "wohnung": str(self.unit.pk),
                "personenanzahl": "1",
                "haustiere": "false",
                "ueber_mich": "Synthetische Testbewerbung",
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Bewerbung.objects.filter(wohnung=self.unit).exists())

    def test_open_protocol_and_preview_keep_current_unit_status(self):
        self.prepare_move_out()
        response = self.client.get(self.url("finalize"))
        self.assertEqual(response.status_code, 200)
        self.assert_unit_status(WohnungStatus.TAKEN)

    def test_blocked_protocol_cannot_change_unit_status(self):
        data = self.signing_data()
        self.protocol.status = ProtokollStatus.BLOCKED
        self.protocol.save()
        response = self.client.post(self.url("confirm"), data)
        self.assertEqual(response.status_code, 404)
        self.assert_unit_status(WohnungStatus.FREE)

    def test_invalid_signature_keeps_current_unit_status(self):
        self.prepare_move_out()
        response = self.client.post(
            self.url("confirm"), self.signing_data(mitarbeiter=fixtures.signature_file(blank=True))
        )
        self.assertEqual(response.status_code, 400)
        self.assert_unit_status(WohnungStatus.TAKEN)

    def test_changed_content_keeps_current_unit_status(self):
        data = self.signing_data()
        self.protocol.heizungsablesungen = "Nach der Vorschau verändert"
        self.protocol.save()
        response = self.client.post(self.url("confirm"), data)
        self.assertEqual(response.status_code, 409)
        self.assert_unit_status(WohnungStatus.FREE)

    def test_storage_failure_rolls_back_unit_status_and_protocol(self):
        data = self.signing_data()
        with patch("wohnungsverwaltung.handover_export.render_pdf", side_effect=OSError):
            response = self.client.post(self.url("confirm"), data)
        self.assertEqual(response.status_code, 503)
        self.assert_unit_status(WohnungStatus.FREE)
        self.protocol.refresh_from_db()
        self.assertEqual(self.protocol.status, ProtokollStatus.OPEN)
        self.assertFalse(self.protocol.unterschriften.exists())

    def test_database_failure_rolls_back_unit_status_and_archive(self):
        data = self.signing_data()
        with patch("wohnungsverwaltung.models.Protokoll.save", side_effect=DatabaseError):
            with self.assertRaises(DatabaseError):
                self.client.post(self.url("confirm"), data)
        self.assert_unit_status(WohnungStatus.FREE)
        self.protocol.refresh_from_db()
        self.assertEqual(self.protocol.status, ProtokollStatus.OPEN)
        self.assertFalse(self.protocol.dokument_pfad)
        self.assertFalse(self.protocol.unterschriften.exists())

    def test_repeated_confirmation_preserves_later_unit_status(self):
        self.finalize()
        snapshot = self.protocol.export_snapshot
        self.unit.status = WohnungStatus.BLOCKED
        self.unit.save(update_fields=["status"])
        response = self.client.post(self.url("confirm"), {})
        self.assertEqual(response.status_code, 200)
        self.assert_unit_status(WohnungStatus.BLOCKED)
        self.protocol.refresh_from_db()
        self.assertEqual(self.protocol.export_snapshot, snapshot)
        self.assertEqual(self.protocol.unterschriften.count(), 2)

    def test_archiving_legacy_protocol_preserves_current_unit_status(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.save()
        self.unit.status = WohnungStatus.BLOCKED
        self.unit.save(update_fields=["status"])
        response = self.client.post(self.url("pdf_create"))
        self.assertEqual(response.status_code, 302)
        self.assert_unit_status(WohnungStatus.BLOCKED)
        self.protocol.refresh_from_db()
        self.assertTrue(self.protocol.nachtraeglich_gesichert)


class HandoverAvailabilityConcurrencyTests(TransactionTestCase):
    setUp = fixtures.HandoverExportTests.setUp
    url = fixtures.HandoverExportTests.url
    signing_data = fixtures.HandoverExportTests.signing_data

    def post_as(self, user_id, url, data):
        close_old_connections()
        try:
            client = Client()
            client.force_login(get_user_model().objects.get(pk=user_id))
            return client.post(url, data)
        finally:
            close_old_connections()

    @skipUnlessDBFeature("has_select_for_update")
    def test_application_waiting_for_move_in_cannot_use_stale_availability(self):
        applicant = get_user_model().objects.create_user(username="new-applicant")
        applicant.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        Person.objects.create(
            user=applicant, vorname="Neue", nachname="Bewerbung", email="neu@example.test"
        )
        data = self.signing_data()
        rendering = threading.Event()
        release = threading.Event()
        application_lock_requested = threading.Event()
        select_for_update = WohnungQuerySet.select_for_update

        def pause_render(*args):
            rendering.set()
            if not release.wait(timeout=10):
                raise RuntimeError("Test synchronization timed out")
            return render_pdf(*args)

        def note_application_lock(queryset, *args, **kwargs):
            if rendering.is_set():
                application_lock_requested.set()
            return select_for_update(queryset, *args, **kwargs)

        with (
            patch("wohnungsverwaltung.handover_export.render_pdf", side_effect=pause_render),
            patch.object(WohnungQuerySet, "select_for_update", new=note_application_lock),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            confirmation = executor.submit(
                self.post_as, self.employee.pk, self.url("confirm"), data
            )
            try:
                self.assertTrue(rendering.wait(timeout=10))
                application = executor.submit(
                    self.post_as,
                    applicant.pk,
                    reverse(
                        "wohnungsverwaltung:pre_application_create_for_unit", args=[self.unit.pk]
                    ),
                    {
                        "wohnung": str(self.unit.pk),
                        "personenanzahl": "1",
                        "haustiere": "false",
                        "ueber_mich": "Synthetische Testbewerbung",
                    },
                )
                self.assertTrue(application_lock_requested.wait(timeout=10))
            finally:
                release.set()
            self.assertEqual(confirmation.result(timeout=20).status_code, 200)
            response = application.result(timeout=20)
            self.assertContains(response, "Die Wohnung ist nicht mehr verfügbar.")
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, WohnungStatus.TAKEN)
        self.assertFalse(Bewerbung.objects.filter(wohnung=self.unit).exists())
