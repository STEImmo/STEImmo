from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from wohnungsverwaltung.management.commands.seed_standard_data import APARTMENTS
from wohnungsverwaltung.models import Wohnung


class Command(BaseCommand):
    help = "Convert legacy development apartments once; preserve current database values."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Dieser Abgleich ist nur für die lokale Entwicklung vorgesehen.")
        units = list(Wohnung.objects.select_for_update().filter(gebaeudenummer="1"))
        by_number = {unit.wohnungsnummer: unit for unit in units}
        legacy = {row[0] for row in APARTMENTS}
        current = {row[1] for row in APARTMENTS}
        if len(units) != 25 or set(by_number) not in (legacy, current):
            raise CommandError(
                "Erwartet werden genau die 25 alten oder bereits abgeglichenen Wohnungen."
            )
        old_inventory = set(by_number) == legacy
        if not old_inventory:
            self.stdout.write("25 Wohnungen bereits umgestellt; gepflegte Daten unverändert.")
            return
        for old_number, number, floor, area in APARTMENTS:
            unit = by_number[old_number]
            if options["apply"]:
                unit.wohnungsnummer = number
                unit.etage = floor
                unit.groesse_qm = Decimal(area)
                unit.save(update_fields=["wohnungsnummer", "etage", "groesse_qm", "updated_at"])
        self.stdout.write(
            "25 Wohnungen abgeglichen; IDs und Verknüpfungen erhalten."
            if options["apply"]
            else "25 Wohnungen geprüft. Mit --apply Nummern, Etagen und Flächen übernehmen."
        )
