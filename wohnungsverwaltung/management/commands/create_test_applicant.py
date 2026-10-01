from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from wohnungsverwaltung.access import ROLE_APPLICANT
from wohnungsverwaltung.models import Person


class Command(BaseCommand):
    help = "Erstellt oder aktualisiert einen lokalen Testbewerber mit Django-Login."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--email", default="testbewerber@example.test")
        parser.add_argument("--password", required=True)

    def handle(self, *args, **options) -> None:
        email = options["email"].strip().lower()
        password = options["password"]
        user_model = get_user_model()
        user, _created = user_model.objects.get_or_create(
            username=email,
            defaults={"email": email},
        )
        try:
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error

        linked_person = Person.objects.filter(user=user).first()
        person = Person.objects.filter(email=email).first()
        if linked_person is not None and linked_person != person:
            raise CommandError("Das Benutzerkonto ist bereits einer anderen Person zugeordnet.")
        if person is None:
            person = Person(
                vorname="Test",
                nachname="Bewerber",
                email=email,
            )
        elif person.is_employee or person.wohnung_id is not None:
            raise CommandError("Die vorhandene Person eignet sich nicht als Testbewerber.")
        elif person.user_id not in (None, user.pk):
            raise CommandError("Die vorhandene Person ist bereits einem anderen Konto zugeordnet.")

        user.email = email
        user.is_active = True
        user.set_password(password)
        user.save()
        person.user = user
        person.save()
        user.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        self.stdout.write(self.style.SUCCESS(f"Testbewerber {email} ist bereit."))
