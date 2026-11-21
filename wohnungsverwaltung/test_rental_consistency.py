from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from . import test_rental_completion
from .models import Person, Rental, Wohnung


class RentalConsistencyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_rental_completion.RentalCompletionTests.setUpTestData.__func__(cls)
        cls.rental = Rental.objects.create(
            application=cls.application,
            wohnung=cls.unit,
            tenant=cls.applicant,
            contract_pdf=b"saved-contract",
        )
        Person.objects.filter(pk=cls.person.pk).update(wohnung=cls.unit)

    def test_completed_application_does_not_offer_withdrawal(self):
        self.client.force_login(self.applicant)
        page = self.client.get(
            reverse("wohnungsverwaltung:main_application_status", args=[self.application.pk])
        )
        self.assertNotContains(page, "Interesse zurückziehen")

    def test_completed_application_rejects_direct_withdrawal_without_changing_rental(self):
        self.client.force_login(self.applicant)
        url = reverse("wohnungsverwaltung:application_withdraw", args=[self.application.pk])
        for method in ("get", "post"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(url).status_code, 404)
        self.application.refresh_from_db()
        self.assertIsNone(self.application.interest_withdrawn_at)
        self.assertEqual(Rental.objects.get().wohnung_id, self.unit.pk)
        self.assertEqual(bytes(Rental.objects.get().contract_pdf), b"saved-contract")

    def test_completed_rental_blocks_different_manual_assignment(self):
        self.assert_different_manual_assignment_rejected()

    def assert_different_manual_assignment_rejected(self):
        self.client.force_login(self.employee)
        other_unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="15")
        response = self.client.post(
            reverse("verwaltung:person_assignment", args=[other_unit.pk, self.person.pk]),
            {"previous_wohnung": str(self.unit.pk), "confirmed": "on"},
        )
        self.assertContains(response, "abgeschlossene Vermietung")
        self.person.refresh_from_db()
        self.assertEqual(self.person.wohnung_id, self.unit.pk)
        self.assertEqual(Rental.objects.get().wohnung_id, self.unit.pk)

    def test_same_manual_assignment_remains_allowed(self):
        self.client.force_login(self.employee)
        response = self.client.post(
            reverse("verwaltung:person_assignment", args=[self.unit.pk, self.person.pk]),
            {"previous_wohnung": str(self.unit.pk), "confirmed": "on"},
        )
        self.assertEqual(response.status_code, 302)
        self.person.refresh_from_db()
        self.assertEqual(self.person.wohnung_id, self.unit.pk)

    def test_person_rental_still_blocks_move_after_account_link_is_removed(self):
        Person.objects.filter(pk=self.person.pk).update(user=None)
        self.assert_different_manual_assignment_rejected()


class RentalConsistencyConcurrencyTests(TransactionTestCase):
    def setUp(self):
        test_rental_completion.RentalCompletionTests.setUpTestData.__func__(type(self))

    complete = test_rental_completion.RentalCompletionTests.complete
    completion_url = test_rental_completion.RentalCompletionTests.completion_url
    pdf_bytes = staticmethod(test_rental_completion.RentalCompletionTests.pdf_bytes)

    def assert_action_waits_for_completion(self, *, action):
        saved = Event()
        resume = Event()
        started = Event()
        backend = {}
        original_save = Rental.save
        employee_client = Client()
        employee_client.force_login(self.employee)
        action_client = Client()
        action_client.force_login(self.applicant if action == "withdraw" else self.employee)
        if action == "withdraw":
            url = reverse("wohnungsverwaltung:application_withdraw", args=[self.application.pk])
            payload = {}
        else:
            other_unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="15")
            url = reverse("verwaltung:person_assignment", args=[other_unit.pk, self.person.pk])
            payload = {"previous_wohnung": str(self.unit.pk), "confirmed": "on"}

        def pause_completion(rental, *args, **kwargs):
            original_save(rental, *args, **kwargs)
            saved.set()
            if not resume.wait(10):
                raise AssertionError("Concurrent action did not reach its lock")

        def complete():
            close_old_connections()
            try:
                self.client = employee_client
                return self.complete(follow=False)
            finally:
                connection.close()

        def conflicting_action():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    backend["pid"] = cursor.fetchone()[0]
                started.set()
                return action_client.post(url, payload)
            finally:
                connection.close()

        with patch.object(Rental, "save", pause_completion):
            with ThreadPoolExecutor(max_workers=2) as pool:
                completion = pool.submit(complete)
                try:
                    self.assertTrue(saved.wait(10), "Completion did not save the rental")
                    conflicting = pool.submit(conflicting_action)
                    self.assertTrue(started.wait(10))
                    deadline = monotonic() + 5
                    while monotonic() < deadline:
                        with connection.cursor() as cursor:
                            cursor.execute("SELECT pg_blocking_pids(%s)", [backend["pid"]])
                            if cursor.fetchone()[0]:
                                break
                        sleep(0.01)
                    else:
                        self.fail("Conflicting action did not wait for completion's row lock")
                finally:
                    resume.set()
                self.assertEqual(completion.result(timeout=10).status_code, 302)
                response = conflicting.result(timeout=10)
        if action == "withdraw":
            self.assertEqual(response.status_code, 404)
        else:
            self.assertContains(response, "abgeschlossene Vermietung")
        self.application.refresh_from_db()
        self.person.refresh_from_db()
        self.assertIsNone(self.application.interest_withdrawn_at)
        self.assertEqual(self.person.wohnung_id, self.unit.pk)
        self.assertEqual(Rental.objects.get().wohnung_id, self.unit.pk)

    def test_withdrawal_waits_for_completion_and_rejects_newly_completed_rental(self):
        self.assert_action_waits_for_completion(action="withdraw")

    def test_manual_assignment_waits_for_completion_and_preserves_rental_unit(self):
        self.assert_action_waits_for_completion(action="assign")
