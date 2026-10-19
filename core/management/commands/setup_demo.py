from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from wohnungsverwaltung.access import ROLE_APPLICANT, ROLE_USER_MANAGEMENT
from wohnungsverwaltung.models import Person, Wohnung, WohnungStatus


class Command(BaseCommand):
    help = "Initialisiert ausschließlich im Demo-Modus fiktive Daten und zwei Testkonten."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEMO_MODE:
            raise CommandError("setup_demo benötigt ausdrücklich config.settings_demo.")
        user_model = get_user_model()
        accounts = (("user", ROLE_APPLICANT), ("verwaltung", ROLE_USER_MANAGEMENT))
        for username, _role in accounts:
            existing = user_model.objects.filter(username=username).first()
            if existing is not None and existing.email != f"{username}@example.test":
                raise CommandError(f"Das Konto {username} ist kein bekanntes Demokonto.")
        if not Wohnung.objects.exists():
            call_command("seed_standard_data", stdout=self.stdout)
            Wohnung.objects.filter(wohnungsnummer__in=("301", "302", "303", "401", "402")).update(
                status=WohnungStatus.FREE,
                zimmeranzahl=2,
                kaltmiete="450.00",
                warmmiete="550.00",
                kaution="1350.00",
            )
        for username, role in accounts:
            user, created = user_model.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@example.test", "first_name": "Demo"},
            )
            if not created:
                continue
            # Intentionally simple credentials, restricted to this explicit demo command.
            user.set_password(username)
            user.save(update_fields=["password"])
            Person.objects.create(
                user=user,
                vorname="Demo",
                nachname="Verwaltung" if role == ROLE_USER_MANAGEMENT else "Bewerber",
                email=user.email,
                is_employee=role == ROLE_USER_MANAGEMENT,
            )
            user.groups.add(Group.objects.get(name=role))
        self.stdout.write("Demo bereit; vorhandene Konten und bearbeitete Daten bleiben erhalten.")
