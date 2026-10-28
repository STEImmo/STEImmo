from collections import Counter
from decimal import Decimal
from importlib import import_module
from io import StringIO

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from .access import ROLE_APPLICANT, ROLE_EMPLOYEE
from .models import Person, Wohnung


class ConfirmedInventoryTests(TestCase):
    def test_standard_and_demo_inventory_match_confirmed_distribution(self):
        for command in ("seed_standard_data", "setup_demo"):
            with self.subTest(command=command), override_settings(DEMO_MODE=True):
                call_command(command, stdout=StringIO())
                self.assertEqual(
                    Counter(Wohnung.objects.values_list("zimmeranzahl", flat=True)),
                    {Decimal("1"): 11, Decimal("2"): 12, Decimal("3"): 2},
                )
                self.assertEqual(Wohnung.objects.get(wohnungsnummer="2").zimmeranzahl, 2)
                self.assertEqual(Wohnung.objects.get(wohnungsnummer="401").zimmeranzahl, 3)
                self.assertEqual(
                    Wohnung.objects.get(wohnungsnummer="401").groesse_qm, Decimal("92.90")
                )
                self.assertEqual(
                    Wohnung.objects.get(wohnungsnummer="402").groesse_qm, Decimal("64.90")
                )


class ConfirmedAtticAreaTests(TestCase):
    def test_duplicate_attic_numbers_abort_before_updating_either_area(self):
        for number in ("401", "402", "402"):
            Wohnung.objects.create(
                gebaeudenummer="1", wohnungsnummer=number, etage=4, groesse_qm="111"
            )
        migration = import_module("wohnungsverwaltung.migrations.0034_confirmed_attic_areas")
        with connection.schema_editor() as editor:
            with self.assertRaisesMessage(RuntimeError, "Mehrdeutige Wohnungszuordnung"):
                migration.correct_attic_areas(apps, editor)
        self.assertEqual(Wohnung.objects.filter(groesse_qm=111).count(), 3)

    def test_migration_replaces_incorrect_letter_areas_and_preserves_other_facts(self):
        first = Wohnung.objects.create(
            gebaeudenummer="1",
            wohnungsnummer="401",
            etage=4,
            groesse_qm="111",
            zimmeranzahl="3",
            kaltmiete="850",
        )
        second = Wohnung.objects.create(
            gebaeudenummer="1", wohnungsnummer="402", etage=4, groesse_qm="70"
        )
        other = Wohnung.objects.create(
            gebaeudenummer="1", wohnungsnummer="201", etage=2, groesse_qm="28.01"
        )
        before = {row["wohnung_id"]: row for row in Wohnung.objects.values()}
        migration = import_module("wohnungsverwaltung.migrations.0034_confirmed_attic_areas")
        with connection.schema_editor() as editor:
            migration.correct_attic_areas(apps, editor)
        for row in Wohnung.objects.values():
            expected = before[row["wohnung_id"]].copy()
            if row["wohnung_id"] == first.pk:
                expected["groesse_qm"] = Decimal("92.90")
            elif row["wohnung_id"] == second.pk:
                expected["groesse_qm"] = Decimal("64.90")
            self.assertEqual(row, expected)
        other.refresh_from_db()
        self.assertEqual(other.groesse_qm, Decimal("28.01"))


class InventoryCorrectionTests(TestCase):
    def correct(self):
        migration = import_module(
            "wohnungsverwaltung.migrations.0033_correct_confirmed_room_counts"
        )
        with connection.schema_editor() as editor:
            migration.correct_room_counts(apps, editor)

    def test_correction_changes_only_two_room_counts_and_keeps_relationships(self):
        for floor, number in ((0, "002"), (4, "401"), (4, "402"), (1, "002")):
            Wohnung.objects.create(
                gebaeudenummer="1",
                wohnungsnummer=number,
                etage=floor,
                zimmeranzahl="3.5",
                groesse_qm="39.51",
                kaltmiete="500",
            )
        unit = Wohnung.objects.get(etage=4, wohnungsnummer="401")
        person = Person.objects.create(
            vorname="Test", nachname="Test", email="inventory@example.test", wohnung=unit
        )
        before = {row["wohnung_id"]: row for row in Wohnung.objects.values()}
        self.correct()
        for row in Wohnung.objects.values():
            expected = before[row["wohnung_id"]].copy()
            if row["etage"] == 0:
                expected["zimmeranzahl"] = Decimal("2")
            elif row["wohnungsnummer"] == "401":
                expected["zimmeranzahl"] = Decimal("3")
            self.assertEqual(row, expected)
        person.refresh_from_db()
        self.assertEqual(person.wohnung_id, unit.pk)

    def test_unpadded_ground_floor_number_is_supported(self):
        unit = Wohnung.objects.create(gebaeudenummer="1", etage=0, wohnungsnummer="2")
        self.correct()
        unit.refresh_from_db()
        self.assertEqual(unit.zimmeranzahl, 2)

    def test_ambiguous_assignment_aborts_before_any_changes(self):
        for floor, number in ((0, "2"), (0, "002"), (4, "401")):
            Wohnung.objects.create(
                gebaeudenummer="1", etage=floor, wohnungsnummer=number, zimmeranzahl="9"
            )
        with self.assertRaisesMessage(RuntimeError, "Mehrdeutige Wohnungszuordnung"):
            self.correct()
        self.assertEqual(Wohnung.objects.filter(zimmeranzahl=9).count(), 3)

    def test_empty_inventory_is_not_populated(self):
        self.correct()
        self.assertFalse(Wohnung.objects.exists())


class AreaFormattingTests(SimpleTestCase):
    def test_area_is_truncated_with_one_decimal_place_and_decimal_comma(self):
        from .formatting import format_area

        for value, expected in (
            ("25.27", "25,2"),
            ("59.56", "59,5"),
            ("27.95", "27,9"),
            ("64.90", "64,9"),
            ("45.70", "45,7"),
            ("28.01", "28,0"),
            ("0", "0,0"),
            ("1000.99", "1000,9"),
        ):
            with self.subTest(value=value):
                self.assertEqual(format_area(Decimal(value)), expected)


class InventoryMigrationTests(TransactionTestCase):
    previous = ("immobilien", "0032_merge_viewing_proposals_and_main")
    corrected = ("immobilien", "0033_correct_confirmed_room_counts")

    def setUp(self):
        super().setUp()
        self.addCleanup(self.restore_latest)
        MigrationExecutor(connection).migrate([self.previous])

    def restore_latest(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_migration_corrects_rooms_once_and_rollback_keeps_later_edits(self):
        unit = Wohnung.objects.create(
            gebaeudenummer="1", wohnungsnummer="401", etage=4, zimmeranzahl="3.5"
        )
        MigrationExecutor(connection).migrate([self.corrected])
        unit.refresh_from_db()
        self.assertEqual(unit.zimmeranzahl, 3)
        Wohnung.objects.filter(pk=unit.pk).update(zimmeranzahl="4.25")
        MigrationExecutor(connection).migrate([self.corrected])
        MigrationExecutor(connection).migrate([self.previous])
        unit.refresh_from_db()
        self.assertEqual(unit.zimmeranzahl, Decimal("4.25"))


class AreaPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.unit = Wohnung.objects.create(
            gebaeudenummer="1",
            wohnungsnummer="002",
            etage=0,
            groesse_qm="39.51",
            zimmeranzahl="2",
        )
        cls.employee = get_user_model().objects.create_user(username="area-employee")
        cls.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        cls.applicant = get_user_model().objects.create_user(username="area-applicant")
        cls.applicant.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        Person.objects.create(user=cls.applicant, vorname="Test", nachname="Test")

    def test_public_pages_and_management_share_truncated_area(self):
        for name, args in (
            ("wohnungsverwaltung_public:apartment_search", []),
            ("wohnungsverwaltung_public:floor_view", [0]),
            ("wohnungsverwaltung_public:apartment_detail_placeholder", [self.unit.pk]),
            ("verwaltung:wohnung_list", []),
        ):
            with self.subTest(page=name):
                if name.startswith("verwaltung:"):
                    self.client.force_login(self.employee)
                response = self.client.get(reverse(name, args=args))
                self.assertContains(response, "39,5 m²")
                self.assertNotContains(response, "39,51")
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.groesse_qm, Decimal("39.51"))

    def test_area_filters_still_compare_exact_stored_values(self):
        url = reverse("wohnungsverwaltung_public:apartment_search")
        response = self.client.get(url, {"groesse_max": "39.5"})
        self.assertNotIn(self.unit, response.context["wohnungen"])
        response = self.client.get(url, {"groesse_min": "39.5"})
        self.assertIn(self.unit, response.context["wohnungen"])

    def test_selected_apartment_in_application_uses_truncated_area(self):
        self.client.force_login(self.applicant)
        response = self.client.get(
            reverse("wohnungsverwaltung:pre_application_create_for_unit", args=[self.unit.pk])
        )
        self.assertContains(response, "39,5 m²")
        self.assertNotContains(response, "39,51")
