from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .access import ROLE_EMPLOYEE
from .forms import EmployeeApplicationUnitFilterForm
from .models import Wohnung

# Independent transcription of the confirmed table in issue #158.
EXPECTED_ROOMS = {
    "1": "1",
    "2": "1",
    "3": "1",
    "4": "2",
    "5": "2",
    "101": "1",
    "102": "1",
    "103": "2",
    "104": "1",
    "105": "2",
    "106": "2",
    "201": "1",
    "202": "1",
    "203": "2",
    "204": "1",
    "205": "2",
    "206": "2",
    "301": "1",
    "302": "1",
    "303": "2",
    "304": "1",
    "305": "2",
    "306": "2",
    "401": "3.5",
    "402": "3",
}


class RoomCountSetupTests(TestCase):
    def assert_inventory(self):
        actual = dict(Wohnung.objects.values_list("wohnungsnummer", "zimmeranzahl"))
        self.assertEqual(
            actual,
            {number: Decimal(value) for number, value in EXPECTED_ROOMS.items()}
            | {"2": Decimal("2"), "401": Decimal("3")},
        )
        self.assertEqual(list(actual.values()).count(Decimal("1")), 11)
        self.assertEqual(list(actual.values()).count(Decimal("2")), 12)
        self.assertEqual(list(actual.values()).count(Decimal("3")), 2)

    def test_seed_assigns_confirmed_room_counts_to_all_25_apartments(self):
        call_command("seed_standard_data", stdout=StringIO())
        self.assert_inventory()

    def test_repeated_seed_preserves_manually_edited_room_counts(self):
        call_command("seed_standard_data", stdout=StringIO())
        Wohnung.objects.filter(wohnungsnummer="401").update(zimmeranzahl="4.25")
        call_command("seed_standard_data", stdout=StringIO())
        self.assertEqual(Wohnung.objects.get(wohnungsnummer="401").zimmeranzahl, Decimal("4.25"))

    @override_settings(DEMO_MODE=True)
    def test_demo_keeps_confirmed_room_counts_including_available_attic_apartments(self):
        call_command("setup_demo", stdout=StringIO())
        self.assert_inventory()


class RoomCountMigrationTests(TransactionTestCase):
    migrate_from = ("immobilien", "0028_viewing_appointments")
    migrate_to = ("immobilien", "0029_confirmed_room_counts")

    def setUp(self):
        super().setUp()
        self.addCleanup(self.restore_latest_schema)
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        self.old_apps = executor.loader.project_state([self.migrate_from]).apps
        self.Unit = self.old_apps.get_model("immobilien", "Wohnung")

    def restore_latest_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def migrate(self):
        MigrationExecutor(connection).migrate([self.migrate_to])

    def test_migration_overwrites_only_room_counts_and_preserves_ids_and_relations(self):
        for number in EXPECTED_ROOMS:
            self.Unit.objects.create(
                gebaeudenummer="1",
                wohnungsnummer=number,
                etage=0 if len(number) == 1 else int(number[0]),
                zimmeranzahl="9.75",
                groesse_qm="45.67",
                kaltmiete="543.21",
            )
        unit = self.Unit.objects.get(wohnungsnummer="401")
        Person = self.old_apps.get_model("immobilien", "Person")
        person = Person.objects.create(
            vorname="Test",
            nachname="Bewohner",
            email="room-counts@example.test",
            wohnung=unit,
        )
        before = {row["wohnung_id"]: row for row in self.Unit.objects.values()}
        self.migrate()
        self.assertEqual(self.Unit.objects.count(), 25)
        for row in self.Unit.objects.values():
            expected = before[row["wohnung_id"]] | {
                "zimmeranzahl": Decimal(EXPECTED_ROOMS[row["wohnungsnummer"]])
            }
            self.assertEqual(row, expected)
        person.refresh_from_db()
        self.assertEqual(person.wohnung_id, unit.pk)

    def test_migration_accepts_zero_padded_ground_floor_numbers(self):
        for number in range(1, 6):
            self.Unit.objects.create(gebaeudenummer="1", etage=0, wohnungsnummer=f"{number:03}")
        self.migrate()
        for unit in self.Unit.objects.all():
            self.assertEqual(
                unit.zimmeranzahl, Decimal(EXPECTED_ROOMS[str(int(unit.wohnungsnummer))])
            )
            self.assertEqual(len(unit.wohnungsnummer), 3)

    def test_partial_inventory_updates_only_matching_building_floor_and_number(self):
        matching = self.Unit.objects.create(gebaeudenummer="1", etage=4, wohnungsnummer="401")
        for building, floor, number in (("2", 4, "401"), ("1", 0, "401"), ("1", 4, "999")):
            self.Unit.objects.create(
                gebaeudenummer=building,
                etage=floor,
                wohnungsnummer=number,
                zimmeranzahl="7",
            )
        self.migrate()
        matching.refresh_from_db()
        self.assertEqual(matching.zimmeranzahl, Decimal("3.5"))
        self.assertEqual(
            self.Unit.objects.exclude(pk=matching.pk).filter(zimmeranzahl=7).count(), 3
        )
        self.assertEqual(self.Unit.objects.count(), 4)

    def test_empty_inventory_remains_empty(self):
        self.migrate()
        self.assertFalse(self.Unit.objects.exists())

    def test_ambiguous_aliases_abort_before_any_update(self):
        for number in ("401", "1", "001"):
            self.Unit.objects.create(
                gebaeudenummer="1",
                etage=4 if number == "401" else 0,
                wohnungsnummer=number,
                zimmeranzahl="9",
            )
        duplicate = self.Unit.objects.get(wohnungsnummer="001")
        try:
            with self.assertRaisesMessage(RuntimeError, "Mehrdeutige Wohnungszuordnung"):
                self.migrate()
            self.assertEqual(self.Unit.objects.filter(zimmeranzahl=9).count(), 3)
        finally:
            duplicate.delete()

    def test_duplicate_numbers_abort_before_any_update(self):
        earlier = self.Unit.objects.create(gebaeudenummer="1", etage=0, wohnungsnummer="1")
        first = self.Unit.objects.create(gebaeudenummer="1", etage=4, wohnungsnummer="401")
        duplicate = self.Unit.objects.create(gebaeudenummer="1", etage=4, wohnungsnummer="401")
        try:
            with self.assertRaisesMessage(RuntimeError, "Mehrdeutige Wohnungszuordnung"):
                self.migrate()
            first.refresh_from_db()
            earlier.refresh_from_db()
            self.assertEqual(first.zimmeranzahl, 0)
            self.assertEqual(earlier.zimmeranzahl, 0)
        finally:
            duplicate.delete()

    def test_later_migrate_and_rollback_preserve_subsequent_edits(self):
        unit = self.Unit.objects.create(gebaeudenummer="1", etage=4, wohnungsnummer="401")
        self.migrate()
        self.Unit.objects.filter(pk=unit.pk).update(zimmeranzahl="4.25")
        self.migrate()
        MigrationExecutor(connection).migrate([self.migrate_from])
        unit.refresh_from_db()
        self.assertEqual(unit.zimmeranzahl, Decimal("4.25"))

    def test_merging_from_room_count_branch_applies_new_correction_and_keeps_profile_schema(self):
        unit = self.Unit.objects.create(gebaeudenummer="1", etage=4, wohnungsnummer="401")
        self.migrate()
        self.Unit.objects.filter(pk=unit.pk).update(zimmeranzahl="4.25")

        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        executor.migrate(targets)
        unit.refresh_from_db()
        self.assertEqual(unit.zimmeranzahl, Decimal("3"))
        final_apps = executor.loader.project_state(targets).apps
        Person = final_apps.get_model("immobilien", "Person")
        person = Person.objects.create(
            vorname="Test", nachname="Profil", email="profile-merge@example.test", city="Würzburg"
        )
        self.assertEqual(Person.objects.get(pk=person.pk).city, "Würzburg")

    def test_merging_from_profile_branch_preserves_profile_and_email_throttle(self):
        profile_target = ("immobilien", "0030_account_email_change_throttle")
        executor = MigrationExecutor(connection)
        executor.migrate([profile_target])
        profile_apps = executor.loader.project_state([profile_target]).apps
        User = profile_apps.get_model("auth", "User")
        Person = profile_apps.get_model("immobilien", "Person")
        Throttle = profile_apps.get_model("immobilien", "AccountEmailChangeThrottle")
        user = User.objects.create(username="migration-profile")
        person = Person.objects.create(
            user=user,
            vorname="Test",
            nachname="Profil",
            email="migration-profile@example.test",
            city="Würzburg",
            postal_code="97070",
            country="Deutschland",
            salutation="neutral",
        )
        before = Person.objects.values().get(pk=person.pk)
        sent_at = timezone.now()
        Throttle.objects.create(user=user, last_sent_at=sent_at)
        unit = self.Unit.objects.create(
            gebaeudenummer="1", etage=4, wohnungsnummer="401", zimmeranzahl="9"
        )

        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        unit.refresh_from_db()
        self.assertEqual(unit.zimmeranzahl, Decimal("3"))
        self.assertEqual(Person.objects.values().get(pk=person.pk), before)
        self.assertEqual(Throttle.objects.get(user_id=user.pk).last_sent_at, sent_at)


class RoomCountFormattingTests(SimpleTestCase):
    def test_room_counts_use_decimal_comma_without_trailing_zeroes(self):
        from .formatting import format_room_count

        for value, expected in (
            ("2.00", "2"),
            ("3.50", "3,5"),
            ("3.25", "3,25"),
            ("0.00", "0"),
            ("10.00", "10"),
            ("1E+1", "10"),
        ):
            with self.subTest(value=value):
                self.assertEqual(format_room_count(Decimal(value)), expected)

    def test_filter_labels_are_formatted_but_values_keep_their_decimal_representation(self):
        form = EmployeeApplicationUnitFilterForm(room_counts=[Decimal("2.00"), Decimal("3.50")])
        self.assertEqual(
            form.fields["rooms"].choices, [("2.00", "2 Zimmer"), ("3.50", "3,5 Zimmer")]
        )


class RoomCountPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = get_user_model().objects.create_user(username="room-count-employee")
        cls.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        cls.unit = Wohnung.objects.create(
            gebaeudenummer="1",
            wohnungsnummer="401",
            etage=4,
            zimmeranzahl="3.50",
        )
        cls.whole = Wohnung.objects.create(
            gebaeudenummer="1",
            wohnungsnummer="402",
            etage=4,
            zimmeranzahl="2.00",
        )

    def test_public_and_management_pages_share_room_count_format(self):
        urls = [
            reverse("wohnungsverwaltung_public:apartment_search"),
            reverse("wohnungsverwaltung_public:floor_view", args=[4]),
            reverse("wohnungsverwaltung_public:apartment_detail_placeholder", args=[self.unit.pk]),
            reverse("verwaltung:wohnung_list"),
        ]
        for url in urls:
            with self.subTest(url=url):
                if url == urls[-1]:
                    self.client.force_login(self.employee)
                response = self.client.get(url)
                self.assertContains(response, "3,5</")
                self.assertNotContains(response, "3,50")
                self.assertNotContains(response, "2,00")

    def test_unknown_room_count_retains_missing_value_notice(self):
        Wohnung.objects.filter(pk=self.unit.pk).update(zimmeranzahl=0)
        response = self.client.get(reverse("wohnungsverwaltung_public:apartment_search"))
        self.assertContains(response, "Noch nicht angegeben")

    def test_public_room_range_filters_accept_whole_and_fractional_values(self):
        url = reverse("wohnungsverwaltung_public:apartment_search")
        for value, unit in (("2", self.whole), ("3.5", self.unit)):
            with self.subTest(value=value):
                response = self.client.get(url, {"zimmer_min": value, "zimmer_max": value})
                self.assertEqual(list(response.context["wohnungen"]), [unit])

    def test_internal_room_filter_retains_decimal_values_and_formatted_labels(self):
        self.client.force_login(self.employee)
        url = reverse("wohnungsverwaltung:employee_application_list")
        for value, unit, label in (
            ("2.00", self.whole, "2 Zimmer"),
            ("3.50", self.unit, "3,5 Zimmer"),
        ):
            with self.subTest(value=value):
                response = self.client.get(url, {"rooms": value})
                self.assertContains(response, label)
                self.assertEqual(list(response.context["units"]), [unit])
