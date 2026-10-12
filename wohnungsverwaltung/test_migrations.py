from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


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
