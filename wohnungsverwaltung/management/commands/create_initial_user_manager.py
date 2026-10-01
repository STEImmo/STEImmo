from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from wohnungsverwaltung.access import ROLE_USER_MANAGEMENT
from wohnungsverwaltung.models import Person


class Command(BaseCommand):
    help = "Erstellt den ersten Benutzerverwalter mit zugehöriger Mitarbeiterperson."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--password", required=True)
        parser.add_argument("--first-name", required=True)
        parser.add_argument("--last-name", required=True)

    def handle(self, *args, **options) -> None:
        email = options["email"].strip().lower()
        password = options["password"]
        first_name = options["first_name"].strip()
        last_name = options["last_name"].strip()
        user_model = get_user_model()
        if (
            user_model.objects.filter(username__iexact=email).exists()
            or Person.objects.filter(email__iexact=email).exists()
        ):
            raise CommandError(
                "Für diese E-Mail-Adresse existiert bereits ein Konto oder eine Person."
            )

        user = user_model(username=email, email=email, first_name=first_name, last_name=last_name)
        try:
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error

        with transaction.atomic():
            user.set_password(password)
            user.save()
            Person.objects.create(
                user=user,
                vorname=first_name,
                nachname=last_name,
                email=email,
                is_employee=True,
            )
            user.groups.add(Group.objects.get(name=ROLE_USER_MANAGEMENT))
        self.stdout.write(self.style.SUCCESS(f"Benutzerverwalter {email} ist bereit."))
