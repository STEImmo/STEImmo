from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from wohnungsverwaltung.system_settings import change_system_settings_access


class Command(BaseCommand):
    help = "Erteilt einem bestehenden Konto das Einzelrecht für Systemeinstellungen."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Exakter Anmeldename des Kontos")

    def handle(self, *args, **options):
        try:
            change_system_settings_access(options["username"], grant=True)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error
        self.stdout.write(self.style.SUCCESS("Das Recht für Systemeinstellungen ist zugewiesen."))
