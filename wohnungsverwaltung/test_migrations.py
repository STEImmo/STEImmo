from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone


class MigrationGraphTests(SimpleTestCase):
    def test_apartment_migrations_have_one_unambiguous_endpoint(self):
        loader = MigrationLoader(None)
        self.assertNotIn("immobilien", loader.detect_conflicts())


class RaumstammMigrationTests(TransactionTestCase):
    migrate_from = ("immobilien", "0008_merge_stellplatz_und_protokoll")
    migrate_to = ("immobilien", "0009_raumstammdaten")

    def setUp(self) -> None:
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.addCleanup(self.restore_latest_schema)
        self.executor.migrate([self.migrate_from])
        self.old_apps = self.executor.loader.project_state([self.migrate_from]).apps

    def restore_latest_schema(self) -> None:
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.executor.loader.graph.leaf_nodes())

    def test_backfill_creates_one_apartment_room_for_matching_historical_names(self) -> None:
        Wohnung = self.old_apps.get_model("immobilien", "Wohnung")
        Person = self.old_apps.get_model("immobilien", "Person")
        Protokoll = self.old_apps.get_model("immobilien", "Protokoll")
        Raumprotokoll = self.old_apps.get_model("immobilien", "Raumprotokoll")

        wohnung = Wohnung.objects.create(gebaeudenummer="A", wohnungsnummer="1")
        person = Person.objects.create(
            vorname="Mara",
            nachname="Muster",
            email="mara@example.test",
            wohnung=wohnung,
        )
        first_protocol = Protokoll.objects.create(
            wohnung=wohnung,
            person=person,
            protokoll_typ="move_in",
            uebergabe_status="renovated",
            abnahme_status="accepted",
        )
        second_protocol = Protokoll.objects.create(
            wohnung=wohnung,
            person=person,
            protokoll_typ="move_out",
            uebergabe_status="unrenovated",
            abnahme_status="accepted",
        )
        Raumprotokoll.objects.create(protokoll=first_protocol, name="Küche")
        Raumprotokoll.objects.create(protokoll=second_protocol, name="Küche")

        self.executor = MigrationExecutor(connection)
        self.executor.migrate([self.migrate_to])
        new_apps = self.executor.loader.project_state([self.migrate_to]).apps
        Raum = new_apps.get_model("immobilien", "Raum")
        Raumprotokoll = new_apps.get_model("immobilien", "Raumprotokoll")

        self.assertEqual(Raum.objects.filter(wohnung_id=wohnung.pk, name="Küche").count(), 1)
        migrated_rooms = list(Raumprotokoll.objects.order_by("protokoll_id"))
        self.assertEqual([room.name for room in migrated_rooms], ["Küche", "Küche"])
        self.assertEqual(migrated_rooms[0].raum_id, migrated_rooms[1].raum_id)


class RentalAndGlobalSettingsMigrationTests(TransactionTestCase):
    merge_target = ("immobilien", "0038_merge_mail_settings_and_rental_completion")

    def setUp(self):
        super().setUp()
        self.addCleanup(self.restore_latest_schema)
        self.migrate_to(("immobilien", "0034_confirmed_attic_areas"))

    def migrate_to(self, target):
        executor = MigrationExecutor(connection)
        executor.migrate([target])
        return executor.loader.project_state([target]).apps

    def restore_latest_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_upgrade_from_main_preserves_global_settings_and_change_history(self):
        apps = self.migrate_to(
            ("immobilien", "0036_merge_application_acceptance_and_global_settings")
        )
        apps.get_model("immobilien", "GlobalSettings").objects.create(
            optional_user_emails_enabled=False, version=3
        )
        change = apps.get_model("immobilien", "GlobalSettingsChange").objects.create(
            actor_account_id=17, changed_fields=["optional_user_emails_enabled"]
        )

        apps = self.migrate_to(self.merge_target)

        settings = apps.get_model("immobilien", "GlobalSettings").objects.get(pk=1)
        self.assertFalse(settings.optional_user_emails_enabled)
        self.assertEqual(settings.version, 3)
        saved_change = apps.get_model("immobilien", "GlobalSettingsChange").objects.get(
            pk=change.pk
        )
        self.assertEqual(saved_change.actor_account_id, 17)
        self.assertEqual(saved_change.changed_fields, ["optional_user_emails_enabled"])
        self.assertEqual(saved_change.changed_at, change.changed_at)
        self.assertFalse(apps.get_model("immobilien", "Rental").objects.exists())

    def test_upgrade_from_rental_branch_preserves_contract_account_and_assignment(self):
        apps = self.migrate_to(("immobilien", "0036_rental_completion"))
        account = apps.get_model("auth", "User").objects.create(username="migration-tenant")
        unit = apps.get_model("immobilien", "Wohnung").objects.create(
            gebaeudenummer="1", wohnungsnummer="14", status="taken"
        )
        person = apps.get_model("immobilien", "Person").objects.create(
            user_id=account.pk,
            wohnung_id=unit.pk,
            vorname="Test",
            nachname="Migration",
            email="migration@example.test",
        )
        application = apps.get_model("immobilien", "Bewerbung").objects.create(
            person_id=person.pk,
            wohnung_id=unit.pk,
            submitted_at=timezone.now(),
            accepted_at=timezone.now(),
        )
        contract = b"synthetic contract bytes for migration preservation"
        rental = apps.get_model("immobilien", "Rental").objects.create(
            application_id=application.pk,
            wohnung_id=unit.pk,
            tenant_id=account.pk,
            contract_pdf=contract,
        )

        apps = self.migrate_to(self.merge_target)

        saved_rental = apps.get_model("immobilien", "Rental").objects.get(pk=rental.pk)
        self.assertEqual(saved_rental.application_id, application.pk)
        self.assertEqual(saved_rental.wohnung_id, unit.pk)
        self.assertEqual(saved_rental.tenant_id, account.pk)
        self.assertEqual(saved_rental.completed_at, rental.completed_at)
        self.assertEqual(bytes(saved_rental.contract_pdf), contract)
        saved_person = apps.get_model("immobilien", "Person").objects.get(pk=person.pk)
        self.assertEqual(saved_person.user_id, account.pk)
        self.assertEqual(saved_person.wohnung_id, unit.pk)
        self.assertEqual(
            apps.get_model("immobilien", "Wohnung").objects.get(pk=unit.pk).status, "taken"
        )
        saved_application = apps.get_model("immobilien", "Bewerbung").objects.get(pk=application.pk)
        self.assertEqual(saved_application.accepted_at, application.accepted_at)
        self.assertFalse(apps.get_model("immobilien", "GlobalSettings").objects.exists())

    def test_upgrade_from_mail_branch_preserves_addresses_and_test_cooldown(self):
        apps = self.migrate_to(("immobilien", "0037_mail_settings"))
        recipients = ["first@example.test", "second@example.test"]
        apps.get_model("immobilien", "GlobalSettings").objects.create(
            optional_user_emails_enabled=False,
            callback_recipients=recipients,
            reply_to="reply@example.test",
            version=5,
        )
        account = apps.get_model("auth", "User").objects.create(username="migration-mail-admin")
        next_allowed = timezone.now()
        apps.get_model("immobilien", "MailTestAttempt").objects.create(
            account_id=account.pk, next_allowed_at=next_allowed
        )

        apps = self.migrate_to(self.merge_target)

        settings = apps.get_model("immobilien", "GlobalSettings").objects.get(pk=1)
        self.assertEqual(settings.callback_recipients, recipients)
        self.assertEqual(settings.reply_to, "reply@example.test")
        self.assertFalse(settings.optional_user_emails_enabled)
        self.assertEqual(settings.version, 5)
        attempt = apps.get_model("immobilien", "MailTestAttempt").objects.get(pk=account.pk)
        self.assertEqual(attempt.next_allowed_at, next_allowed)
        self.assertFalse(apps.get_model("immobilien", "Rental").objects.exists())
