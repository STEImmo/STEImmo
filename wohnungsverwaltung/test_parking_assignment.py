import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError, close_old_connections
from django.test import Client, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse

from . import test_management as fixtures
from .forms import StellplatzZuordnungForm
from .models import Stellplatz, StellplatzTyp, StellplatzZuordnung, Wohnung


class ParkingAssignmentTests(TestCase):
    setUp = fixtures.ManagementViewTests.setUp

    def payload(self, unit=None, **changes):
        return {
            "name": "TG-01",
            "stellplatz_typ": StellplatzTyp.EV,
            "miete": "45.00",
            "wohnung": str(unit.pk) if unit else "",
        } | changes

    def test_assignment_reassignment_and_unassignment_keep_one_or_zero_relations(self):
        self.client.force_login(self.employee_user)
        units = [Wohnung.objects.create(gebaeudenummer="A", wohnungsnummer=str(i)) for i in (1, 2)]
        response = self.client.post(reverse("verwaltung:stellplatz_create"), self.payload(units[0]))
        parking = Stellplatz.objects.get(name="TG-01")
        self.assertRedirects(response, reverse("verwaltung:stellplatz_edit", args=[parking.pk]))
        url = reverse("verwaltung:stellplatz_edit", args=[parking.pk])
        self.assertEqual(StellplatzZuordnung.objects.get(stellplatz=parking).wohnung, units[0])
        self.assertEqual(self.client.post(url, self.payload(units[1])).status_code, 302)
        self.assertEqual(StellplatzZuordnung.objects.get(stellplatz=parking).wohnung, units[1])
        self.assertEqual(self.client.post(url, self.payload()).status_code, 302)
        self.assertFalse(StellplatzZuordnung.objects.filter(stellplatz=parking).exists())

    def test_conflict_returns_form_error_and_rolls_back_master_data_and_assignment(self):
        self.client.force_login(self.employee_user)
        first = Wohnung.objects.create(gebaeudenummer="A", wohnungsnummer="1")
        second = Wohnung.objects.create(gebaeudenummer="A", wohnungsnummer="2")
        parking = Stellplatz.objects.create(name="TG-01", stellplatz_typ=StellplatzTyp.EV, miete=45)
        relation = StellplatzZuordnung.objects.create(stellplatz=parking, wohnung=first)
        with patch.object(StellplatzZuordnung, "save", side_effect=IntegrityError):
            response = self.client.post(
                reverse("verwaltung:stellplatz_edit", args=[parking.pk]),
                self.payload(second, name="Neuer Name", miete="90.00"),
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["zuordnung_form"].errors.get("wohnung"))
        self.assertContains(response, "Die Stellplatzzuordnung konnte nicht gespeichert werden.")
        parking.refresh_from_db()
        relation.refresh_from_db()
        self.assertEqual(parking.name, "TG-01")
        self.assertEqual(parking.miete, Decimal("45.00"))
        self.assertEqual(relation.wohnung_id, first.pk)

    def test_conflict_when_creating_parking_leaves_no_partial_master_data(self):
        self.client.force_login(self.employee_user)
        unit = Wohnung.objects.create(gebaeudenummer="A", wohnungsnummer="1")
        with patch.object(StellplatzZuordnung, "save", side_effect=IntegrityError):
            response = self.client.post(reverse("verwaltung:stellplatz_create"), self.payload(unit))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["zuordnung_form"].errors.get("wohnung"))
        self.assertContains(response, "Die Stellplatzzuordnung konnte nicht gespeichert werden.")
        self.assertFalse(Stellplatz.objects.filter(name="TG-01").exists())
        self.assertFalse(StellplatzZuordnung.objects.exists())


class ParkingAssignmentConcurrencyTests(TransactionTestCase):
    setUp = fixtures.ManagementViewTests.setUp
    payload = ParkingAssignmentTests.payload

    def post_assignment(self, parking, unit):
        close_old_connections()
        try:
            client = Client(raise_request_exception=False)
            client.force_login(self.employee_user)
            return client.post(
                reverse("verwaltung:stellplatz_edit", args=[parking.pk]), self.payload(unit)
            ).status_code
        finally:
            close_old_connections()

    @skipUnlessDBFeature("has_select_for_update")
    def test_parallel_first_assignments_to_same_or_different_units_succeed(self):
        first = Wohnung.objects.create(gebaeudenummer="A", wohnungsnummer="1")
        second = Wohnung.objects.create(gebaeudenummer="A", wohnungsnummer="2")
        for units in ((first, first), (first, second)):
            with self.subTest(units=[unit.pk for unit in units]):
                parking = Stellplatz.objects.create(name="TG-01", stellplatz_typ=StellplatzTyp.EV)
                barrier = threading.Barrier(2)
                validate = StellplatzZuordnungForm.is_valid

                def synchronize_validation(form):
                    valid = validate(form)
                    if valid:
                        barrier.wait(timeout=10)
                    return valid

                with patch.object(StellplatzZuordnungForm, "is_valid", new=synchronize_validation):
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        requests = [
                            executor.submit(self.post_assignment, parking, unit) for unit in units
                        ]
                        responses = [request.result(timeout=20) for request in requests]
                self.assertEqual(responses, [302, 302])
                relations = StellplatzZuordnung.objects.filter(stellplatz=parking)
                self.assertEqual(relations.count(), 1)
                self.assertIn(relations.get().wohnung_id, [unit.pk for unit in units])
