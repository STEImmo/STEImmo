from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import close_old_connections, connection
from django.test import Client, TransactionTestCase
from django.urls import reverse

from .forms import HandoverProtocolForm
from .models import Person, Protokoll, Wohnung


class AssignmentConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.employee = get_user_model().objects.create_user(
            username="concurrent-employee",
            first_name="Demo",
            last_name="Verwaltung",
        )
        self.employee.groups.add(Group.objects.get(name="Mitarbeiter"))
        self.first = Wohnung.objects.create(
            gebaeudenummer="A",
            wohnungsnummer="101",
            zaehlernummer_wasser_kalt="KW-101",
            zaehlernummer_wasser_warm="WW-101",
            zaehlernummer_heizung="HZ-101",
            zaehlernummer_strom="ST-101",
        )
        self.second = Wohnung.objects.create(gebaeudenummer="A", wohnungsnummer="102")
        self.person = Person.objects.create(
            vorname="Demo",
            nachname="Einzug",
            email="concurrent@example.test",
            wohnung=self.first,
        )
        self.client.force_login(self.employee)
        self.assignment_url = reverse(
            "verwaltung:person_assignment",
            args=[self.second.pk, self.person.pk],
        )
        self.payload = {
            "wohnung": str(self.first.pk),
            "person": str(self.person.pk),
            "protokoll_typ": "move_in",
            "uebergabe_zeitpunkt": "2026-10-29T10:30",
            "uebergabe_status": "renovated",
            "abnahme_status": "accepted",
            "heizungsablesungen": "Keine Zusatzablesung",
            "zaehlerstand_wasser_kalt": "1",
            "zaehlerstand_wasser_warm": "2",
            "zaehlerstand_heizung": "3",
            "zaehlerstand_strom": "4",
            "rooms-TOTAL_FORMS": "0",
            "rooms-INITIAL_FORMS": "0",
            "keys-TOTAL_FORMS": "0",
            "keys-INITIAL_FORMS": "0",
        }

    def post_in_connection(self, url, payload):
        close_old_connections()
        try:
            client = Client()
            client.force_login(self.employee)
            # Return the response before closing this thread's connection.
            return client.post(url, payload)
        finally:
            connection.close()

    def assert_stale_protocol_rejected(self, url, protocol=None):
        validated = Event()
        resume = Event()
        original = HandoverProtocolForm.is_valid

        def pause_after_validation(form):
            valid = original(form)
            if valid:
                validated.set()
                if not resume.wait(10):
                    raise AssertionError("Concurrent assignment did not finish")
            return valid

        before = Protokoll.objects.values().get(pk=protocol.pk) if protocol else None
        with patch.object(HandoverProtocolForm, "is_valid", pause_after_validation):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.post_in_connection, url, self.payload)
                try:
                    self.assertTrue(validated.wait(10), "Protocol form did not validate")
                    assigned = self.client.post(
                        self.assignment_url,
                        {
                            "confirmed": "on",
                            "previous_wohnung": str(self.first.pk),
                        },
                    )
                    self.assertEqual(assigned.status_code, 302)
                finally:
                    resume.set()
                response = future.result(timeout=10)
        self.assertContains(response, "Wohnungszuordnung wurde zwischenzeitlich geändert")
        self.person.refresh_from_db()
        self.assertEqual(self.person.wohnung_id, self.second.pk)
        if protocol:
            self.assertEqual(Protokoll.objects.values().get(pk=protocol.pk), before)
        else:
            self.assertFalse(Protokoll.objects.exists())

    def test_create_rechecks_assignment_after_concurrent_move(self):
        self.assert_stale_protocol_rejected(reverse("wohnungsverwaltung:handover_protocol_create"))

    def test_edit_rechecks_new_participant_after_concurrent_move(self):
        previous = Person.objects.create(
            vorname="Andere",
            nachname="Person",
            email="previous@example.test",
            wohnung=self.first,
        )
        protocol = Protokoll.objects.create(
            person=previous,
            wohnung=self.first,
            protokoll_typ="move_in",
            uebergabe_status="renovated",
            abnahme_status="accepted",
        )
        self.assert_stale_protocol_rejected(
            reverse("wohnungsverwaltung:handover_protocol_edit", args=[protocol.pk]),
            protocol,
        )

    def test_move_waits_for_creation_and_then_rejects_open_protocol(self):
        locked = Event()
        resume = Event()
        assignment_started = Event()
        backend = {}
        original = HandoverProtocolForm.save

        def pause_before_save(form, *args, **kwargs):
            locked.set()
            if not resume.wait(10):
                raise AssertionError("Concurrent assignment did not reach the person lock")
            return original(form, *args, **kwargs)

        def assign_in_connection():
            close_old_connections()
            try:
                client = Client()
                client.force_login(self.employee)
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    backend["pid"] = cursor.fetchone()[0]
                assignment_started.set()
                return client.post(
                    self.assignment_url,
                    {
                        "confirmed": "on",
                        "previous_wohnung": str(self.first.pk),
                    },
                )
            finally:
                connection.close()

        with patch.object(HandoverProtocolForm, "save", pause_before_save):
            with ThreadPoolExecutor(max_workers=2) as executor:
                created = executor.submit(
                    self.post_in_connection,
                    reverse("wohnungsverwaltung:handover_protocol_create"),
                    self.payload,
                )
                try:
                    self.assertTrue(locked.wait(10), "Protocol creation did not reach save")
                    assigned = executor.submit(assign_in_connection)
                    self.assertTrue(assignment_started.wait(10))
                    # Observe an actual PostgreSQL lock wait rather than relying on timing.
                    deadline = monotonic() + 5
                    while monotonic() < deadline:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT pg_blocking_pids(%s)", [backend["pid"]])
                            if cursor.fetchone()[0]:
                                break
                        sleep(0.01)
                    else:
                        self.fail("Assignment did not wait for the protocol's person lock")
                finally:
                    resume.set()
                self.assertEqual(created.result(timeout=10).status_code, 302)
                self.assertContains(assigned.result(timeout=10), "offene oder gesperrte Protokolle")
        self.person.refresh_from_db()
        self.assertEqual(self.person.wohnung_id, self.first.pk)
        self.assertEqual(Protokoll.objects.get(person=self.person).wohnung_id, self.first.pk)
