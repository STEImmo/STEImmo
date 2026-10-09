import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from . import test_handover_export as fixtures
from .access import ROLE_APPLICANT
from .handover_export import render_pdf
from .models import (
    Bewerbung,
    Person,
    Protokoll,
    ProtokollSchluessel,
    ProtokollStatus,
    ProtokollTyp,
    RaumMerkmal,
    Raumprotokoll,
    WohnungQuerySet,
    WohnungStatus,
)


class HandoverChronologyFixtures:
    setUp = fixtures.HandoverExportTests.setUp
    url = fixtures.HandoverExportTests.url
    signing_data = fixtures.HandoverExportTests.signing_data
    finalize = fixtures.HandoverExportTests.finalize

    def create_move_out(self, timestamp):
        move_out = Protokoll.objects.get(pk=self.protocol.pk)
        move_out.pk = None
        move_out.protokoll_typ = ProtokollTyp.MOVE_OUT
        move_out.uebergabe_zeitpunkt = timestamp
        move_out.mieter_zukuenftige_anschrift = "Neue Testadresse 4"
        move_out.save()
        room = Raumprotokoll.objects.create(protokoll=move_out, raum=self.master_room, name="Küche")
        RaumMerkmal.objects.create(
            raumprotokoll=room, merkmal=self.feature, wert={"text": "Testfeststellung"}
        )
        ProtokollSchluessel.objects.create(
            protokoll=move_out, anzahl=2, raum_bezeichnung="Wohnungstür"
        )
        return move_out

    def confirm(self, protocol):
        self.protocol = protocol
        self.finalize()

    def assert_unit_status(self, expected):
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, expected)

    def assert_public_availability(self, available):
        response = self.client.get(reverse("wohnungsverwaltung_public:apartment_search"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["wohnungen"].filter(pk=self.unit.pk).exists(), available)
        response = self.client.get(
            reverse("wohnungsverwaltung_public:apartment_detail_placeholder", args=[self.unit.pk])
        )
        self.assertEqual(response.status_code, 200 if available else 404)
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
        self.assertEqual(response.status_code, 302 if available else 404)
        self.assertEqual(Bewerbung.objects.filter(wohnung=self.unit).exists(), available)


class HandoverChronologyTests(HandoverChronologyFixtures, TestCase):
    def test_older_move_out_preserves_newer_confirmed_occupancy(self):
        self.protocol.uebergabe_zeitpunkt = timezone.now() - timedelta(days=1)
        self.protocol.save()
        older_move_out = self.create_move_out(timezone.now() - timedelta(days=2))

        self.finalize()
        self.assert_unit_status(WohnungStatus.TAKEN)
        self.confirm(older_move_out)
        self.assert_unit_status(WohnungStatus.TAKEN)
        self.assert_public_availability(False)

    def test_older_move_in_preserves_newer_confirmed_vacancy(self):
        move_in = self.protocol
        newer_move_out = self.create_move_out(move_in.uebergabe_zeitpunkt + timedelta(days=1))
        self.confirm(newer_move_out)
        self.confirm(move_in)
        self.assert_unit_status(WohnungStatus.FREE)
        self.assert_public_availability(True)

    def test_newer_move_out_replaces_older_confirmed_occupancy(self):
        newer_move_out = self.create_move_out(self.protocol.uebergabe_zeitpunkt + timedelta(days=1))
        self.finalize()
        self.confirm(newer_move_out)
        self.assert_unit_status(WohnungStatus.FREE)

    def test_newer_move_in_replaces_older_confirmed_vacancy(self):
        move_in = self.protocol
        older_move_out = self.create_move_out(move_in.uebergabe_zeitpunkt - timedelta(days=1))
        self.confirm(older_move_out)
        self.confirm(move_in)
        self.assert_unit_status(WohnungStatus.TAKEN)

    def test_equal_timestamp_move_in_then_move_out_stays_taken(self):
        move_out = self.create_move_out(self.protocol.uebergabe_zeitpunkt)
        self.finalize()
        self.confirm(move_out)
        self.assert_unit_status(WohnungStatus.TAKEN)

    def test_equal_timestamp_move_out_then_move_in_stays_taken(self):
        move_in = self.protocol
        move_out = self.create_move_out(move_in.uebergabe_zeitpunkt)
        self.confirm(move_out)
        self.confirm(move_in)
        self.assert_unit_status(WohnungStatus.TAKEN)

    def test_newer_unconfirmed_protocol_does_not_override_confirmed_move_out(self):
        for status in (ProtokollStatus.OPEN, ProtokollStatus.BLOCKED):
            with self.subTest(status=status):
                self.protocol.status = status
                self.protocol.save()
                self.unit.status = WohnungStatus.TAKEN
                self.unit.save()
                move_out = self.create_move_out(
                    self.protocol.uebergabe_zeitpunkt - timedelta(days=1)
                )
                move_out.status = ProtokollStatus.OPEN
                move_out.save()
                newer = self.protocol
                self.confirm(move_out)
                self.assert_unit_status(WohnungStatus.FREE)
                self.protocol = newer


class HandoverChronologyConcurrencyTests(HandoverChronologyFixtures, TransactionTestCase):
    def post_as_employee(self, url, data):
        close_old_connections()
        try:
            client = Client()
            client.force_login(get_user_model().objects.get(pk=self.employee.pk))
            return client.post(url, data)
        finally:
            close_old_connections()

    def assert_parallel_confirmations(self, first, second, expected):
        self.protocol = first
        first_data = self.signing_data()
        self.protocol = second
        second_data = self.signing_data()
        rendering = threading.Event()
        release = threading.Event()
        second_lock_requested = threading.Event()
        select_for_update = WohnungQuerySet.select_for_update

        def pause_first_render(*args):
            if not rendering.is_set():
                rendering.set()
                if not release.wait(timeout=10):
                    raise RuntimeError("Test synchronization timed out")
            return render_pdf(*args)

        def note_second_lock(queryset, *args, **kwargs):
            if rendering.is_set():
                second_lock_requested.set()
            return select_for_update(queryset, *args, **kwargs)

        with (
            patch("wohnungsverwaltung.handover_export.render_pdf", side_effect=pause_first_render),
            patch.object(WohnungQuerySet, "select_for_update", new=note_second_lock),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            first_result = executor.submit(
                self.post_as_employee, self.url("confirm", first), first_data
            )
            try:
                self.assertTrue(rendering.wait(timeout=10))
                second_result = executor.submit(
                    self.post_as_employee, self.url("confirm", second), second_data
                )
                self.assertTrue(second_lock_requested.wait(timeout=10))
                self.assertFalse(second_result.done())
            finally:
                release.set()
            for result in (first_result, second_result):
                response = result.result(timeout=20)
                self.assertEqual(response.status_code, 200, response.content)
        self.assert_unit_status(expected)
        for protocol in (first, second):
            protocol.refresh_from_db()
            self.assertEqual(protocol.status, ProtokollStatus.SIGNED)
            self.assertTrue(protocol.dokument_pfad)

    @skipUnlessDBFeature("has_select_for_update")
    def test_parallel_newer_move_in_then_older_move_out_stays_taken(self):
        move_out = self.create_move_out(self.protocol.uebergabe_zeitpunkt - timedelta(days=1))
        self.assert_parallel_confirmations(self.protocol, move_out, WohnungStatus.TAKEN)

    @skipUnlessDBFeature("has_select_for_update")
    def test_parallel_older_move_in_then_newer_move_out_becomes_free(self):
        move_out = self.create_move_out(self.protocol.uebergabe_zeitpunkt + timedelta(days=1))
        self.assert_parallel_confirmations(self.protocol, move_out, WohnungStatus.FREE)

    @skipUnlessDBFeature("has_select_for_update")
    def test_parallel_equal_timestamp_move_in_then_move_out_stays_taken(self):
        move_out = self.create_move_out(self.protocol.uebergabe_zeitpunkt)
        self.assert_parallel_confirmations(self.protocol, move_out, WohnungStatus.TAKEN)
