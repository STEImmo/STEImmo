from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from core.views import personal_profile_edit
from wohnungsverwaltung.models import (
    AbnahmeStatus,
    Bewerbung,
    Person,
    Protokoll,
    ProtokollStatus,
    ProtokollTyp,
    UebergabeStatus,
    Wohnung,
)


class PersonalProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="profile@example.test",
            email="profile@example.test",
            first_name="Mia",
            last_name="Muster",
        )
        cls.person = Person.objects.create(
            user=cls.user,
            vorname="Mia",
            nachname="Muster",
            email="contact@example.test",
            telefonnummer="+49 931 12345",
        )
        cls.other = Person.objects.create(
            vorname="Fremd", nachname="Geheim", email="other@example.test"
        )

    def setUp(self):
        self.client.force_login(self.user)

    def data(self, **changes):
        return {
            "vorname": " Lea ",
            "nachname": " Beispiel ",
            "telefonnummer": "+49 (0)931 / 54321",
            **changes,
        }

    def test_anonymous_get_and_post_require_login(self):
        self.client.logout()
        for name in ("profile:detail", "profile:edit"):
            for method in (self.client.get, self.client.post):
                response = method(reverse(name), self.data())
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("login")))
        self.person.refresh_from_db()
        self.assertEqual(self.person.vorname, "Mia")

    def test_detail_shows_own_contact_data_and_login_email(self):
        response = self.client.get(reverse("profile:detail"))
        for value in ("Mia", "Muster", "+49 931 12345", self.user.email):
            self.assertContains(response, value)
        self.assertNotContains(response, "contact@example.test")
        self.assertNotContains(response, "Geheim")
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_account_menu_links_to_profile_on_desktop_and_mobile(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("profile:detail")}"', count=2)

    def test_save_changes_only_allowed_fields_and_synchronizes_account_names(self):
        original_user = get_user_model().objects.values().get(pk=self.user.pk)
        original_person = Person.objects.values().get(pk=self.person.pk)
        response = self.client.post(
            reverse("profile:edit"),
            self.data(
                person=self.other.pk,
                person_id=self.other.pk,
                user_id=999,
                email="attacker@example.test",
                is_employee="on",
                is_superuser="on",
                roles=["Mitarbeiter"],
                password="Changed!",
                wohnung="999",
            ),
            follow=True,
        )
        self.assertContains(response, "Ihre Profildaten wurden gespeichert.")
        self.assertRedirects(response, reverse("profile:detail"))
        self.person.refresh_from_db()
        self.user.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual((self.person.vorname, self.person.nachname), ("Lea", "Beispiel"))
        self.assertEqual((self.user.first_name, self.user.last_name), ("Lea", "Beispiel"))
        self.assertEqual(self.person.telefonnummer, "+49 (0)931 / 54321")
        self.assertEqual(self.other.vorname, "Fremd")
        for field, value in original_user.items():
            if field not in ("first_name", "last_name"):
                self.assertEqual(getattr(self.user, field), value, field)
        for field, value in original_person.items():
            if field not in ("vorname", "nachname", "telefonnummer", "updated_at"):
                self.assertEqual(getattr(self.person, field), value, field)
        self.assertFalse(self.user.groups.exists())

    def test_foreign_identifiers_never_select_another_profile(self):
        response = self.client.get(reverse("profile:edit"), {"person": self.other.pk})
        self.assertContains(response, 'value="Mia"')
        self.assertNotContains(response, "Geheim")
        for method in (self.client.get, self.client.post):
            response = method(f"{reverse('profile:detail')}{self.other.pk}/", self.data())
            self.assertEqual(response.status_code, 404)

    def test_invalid_names_have_accessible_errors_and_do_not_save(self):
        for field, value in (
            ("vorname", " "),
            ("nachname", ""),
            ("vorname", "x" * 151),
            ("nachname", "x" * 151),
            ("telefonnummer", "x" * 256),
        ):
            with self.subTest(field=field, length=len(value)):
                response = self.client.post(reverse("profile:edit"), self.data(**{field: value}))
                self.assertContains(response, f'id="id_{field}_error"')
                self.assertContains(response, 'aria-invalid="true"')
                self.assertIn(f"id_{field}_error", response.context["form"][field].aria_describedby)
                self.person.refresh_from_db()
                self.assertEqual(self.person.vorname, "Mia")

    def test_phone_is_optional_and_missing_values_are_explained(self):
        self.client.post(reverse("profile:edit"), self.data(telefonnummer=""))
        response = self.client.get(reverse("profile:detail"))
        self.assertContains(response, "Nicht angegeben")
        Person.objects.filter(pk=self.person.pk).update(vorname="", nachname="")
        response = self.client.get(reverse("profile:detail"))
        self.assertContains(response, "Nicht angegeben", count=5)

    def test_cancel_returns_to_saved_data_and_get_does_not_write(self):
        response = self.client.get(reverse("profile:edit"), self.data())
        self.assertContains(response, f'href="{reverse("profile:detail")}"')
        self.assertContains(response, "Abbrechen")
        self.assertContains(response, 'value="Mia"')
        self.person.refresh_from_db()
        self.assertEqual(self.person.vorname, "Mia")
        self.assertEqual(self.client.post(reverse("profile:detail"), self.data()).status_code, 405)

    def test_unlinked_accounts_get_explanation_without_creation_or_foreign_data(self):
        Person.objects.filter(pk=self.person.pk).update(user=None)
        for method in (self.client.get, self.client.post):
            response = method(reverse("profile:edit"), self.data(person=self.other.pk))
            self.assertContains(response, "Ihrem Konto ist noch kein Personendatensatz zugeordnet.")
            self.assertNotContains(response, 'name="vorname"')
            self.assertNotContains(response, "Geheim")
        self.assertFalse(Person.objects.filter(user=self.user).exists())

    def test_profile_is_available_for_each_role_without_additional_permissions(self):
        for role in Group.objects.all():
            self.user.groups.set([role])
            self.client.force_login(self.user)
            self.assertEqual(self.client.get(reverse("profile:detail")).status_code, 200)

    def test_post_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertContains(client.get(reverse("profile:edit")), 'name="csrfmiddlewaretoken"')
        self.assertEqual(client.post(reverse("profile:edit"), self.data()).status_code, 403)

    def test_inflight_request_cannot_edit_person_after_account_reassignment(self):
        request = RequestFactory().post(reverse("profile:edit"), self.data())
        request.user = get_user_model().objects.get(pk=self.user.pk)
        request.session = {}
        request._messages = FallbackStorage(request)
        Person.objects.filter(pk=self.person.pk).update(user=None)
        Person.objects.filter(pk=self.other.pk).update(user=self.user)
        get_user_model().objects.filter(pk=self.user.pk).update(
            password="changed-by-administration", email=self.other.email, username=self.other.email
        )
        with self.assertRaises(PermissionDenied):
            personal_profile_edit(request)
        self.other.refresh_from_db()
        self.assertEqual(self.other.vorname, "Fremd")

    def test_edit_does_not_modify_submitted_application_or_signed_protocol(self):
        unit = Wohnung.objects.create(wohnungsnummer="1.01", gebaeudenummer="1")
        application = Bewerbung.objects.create(
            person=self.person,
            wohnung=unit,
            ueber_mich="Eingereichter Text",
            submitted_at=timezone.now(),
            income_proof="proofs/original.pdf",
        )
        protocol = Protokoll.objects.create(
            person=self.person,
            wohnung=unit,
            protokoll_typ=ProtokollTyp.MOVE_IN,
            status=ProtokollStatus.SIGNED,
            uebergabe_status=UebergabeStatus.RENOVATED,
            abnahme_status=AbnahmeStatus.ACCEPTED,
            export_snapshot={"tenant": "Mia Muster"},
            dokument_pfad="archive/original.pdf",
            dokument_hash_sha256="a" * 64,
        )
        before_application = Bewerbung.objects.values().get(pk=application.pk)
        before_protocol = Protokoll.objects.values().get(pk=protocol.pk)
        self.assertRedirects(
            self.client.post(reverse("profile:edit"), self.data()), reverse("profile:detail")
        )
        self.assertEqual(Bewerbung.objects.values().get(pk=application.pk), before_application)
        self.assertEqual(Protokoll.objects.values().get(pk=protocol.pk), before_protocol)
