from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from wohnungsverwaltung.access import ROLE_EMPLOYEE
from wohnungsverwaltung.models import Person


class Command(BaseCommand):
    help = "Erstellt oder aktualisiert ein lokales Mitarbeiterkonto für die Entwicklung."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--password", required=True)

    def handle(self, *args, **options) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "Das lokale Mitarbeiterkonto darf nur mit DEBUG=True angelegt werden."
            )

        email = options["email"].strip().lower()
        password = options["password"]
        user_model = get_user_model()
        user, _created = user_model.objects.get_or_create(
            username=email,
            defaults={
                "email": email,
                "first_name": "Dev",
                "last_name": "Mitarbeiter",
            },
        )
        linked_person = Person.objects.filter(user=user).first()
        email_person = Person.objects.filter(email__iexact=email).first()
        if linked_person is not None and linked_person.email.lower() != email:
            raise CommandError("Das Mitarbeiterkonto ist bereits einer anderen Person zugeordnet.")
        if email_person is not None and email_person.user_id not in (None, user.pk):
            raise CommandError("Die E-Mail-Adresse ist bereits einem anderen Konto zugeordnet.")

        user.email = email
        user.first_name = "Dev"
        user.last_name = "Mitarbeiter"
        try:
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error

        with transaction.atomic():
            user.is_active = True
            user.set_password(password)
            user.save()
            person = linked_person or email_person
            if person is None:
                person = Person(
                    user=user,
                    vorname="Dev",
                    nachname="Mitarbeiter",
                    email=email,
                    is_employee=True,
                )
            else:
                person.user = user
                person.is_employee = True
            person.save()
            user.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        self.stdout.write(self.style.SUCCESS(f"Lokaler Mitarbeiter {email} ist bereit."))
