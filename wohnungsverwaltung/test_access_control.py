import re
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .access import (
    APPLICANT_ACCESS_PERMISSION,
    ROLE_APPLICANT,
    ROLE_EMPLOYEE,
    ROLE_TENANT,
    ROLE_USER_MANAGEMENT,
)
from .models import Person, RegistrationVerification


class RegistrationViewTests(TestCase):
    def registration_data(self) -> dict[str, str]:
        return {
            "vorname": "Lina",
            "nachname": "Lang",
            "email": "lina.lang@example.test",
            "password1": "FjordTanne!4826",
            "password2": "FjordTanne!4826",
        }

    def test_registration_creates_linked_applicant_account(self) -> None:
        response = self.client.post(reverse("register"), self.registration_data())

        self.assertRedirects(response, reverse("register_verify"))
        user = get_user_model().objects.get(username="lina.lang@example.test")
        self.assertEqual(user.email, "lina.lang@example.test")
        self.assertEqual(user.person_profile.vorname, "Lina")
        self.assertFalse(user.is_active)
        self.assertTrue(user.groups.filter(name=ROLE_APPLICANT).exists())
        verification = RegistrationVerification.objects.get(user=user)
        self.assertEqual(len(mail.outbox), 1)
        code_match = re.search(r"\b\d{6}\b", mail.outbox[0].body)
        self.assertIsNotNone(code_match)
        self.assertTrue(verification.matches(code_match.group()))
        self.assertNotIn(code_match.group(), verification.code_hash)

    def test_valid_verification_code_activates_and_logs_in_the_new_account(self) -> None:
        self.client.post(reverse("register"), self.registration_data())
        code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group()

        response = self.client.post(
            reverse("register_verify"),
            {"email": "lina.lang@example.test", "code": code},
        )

        self.assertRedirects(response, reverse("wohnungsverwaltung:pre_application_list"))
        user = get_user_model().objects.get(username="lina.lang@example.test")
        self.assertTrue(user.is_active)
        self.assertFalse(RegistrationVerification.objects.filter(user=user).exists())

    def test_expired_verification_code_does_not_activate_the_account(self) -> None:
        self.client.post(reverse("register"), self.registration_data())
        verification = RegistrationVerification.objects.get()
        verification.expires_at = timezone.now() - timedelta(seconds=1)
        verification.save(update_fields=["expires_at"])
        code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group()

        response = self.client.post(
            reverse("register_verify"),
            {"email": "lina.lang@example.test", "code": code},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Der Code konnte nicht bestätigt werden.")
        self.assertFalse(get_user_model().objects.get().is_active)

    def test_resending_a_code_invalidates_the_previous_code(self) -> None:
        self.client.post(reverse("register"), self.registration_data())
        first_code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group()
        verification = RegistrationVerification.objects.get()
        verification.last_sent_at = timezone.now() - RegistrationVerification.RESEND_DELAY
        verification.save(update_fields=["last_sent_at"])

        response = self.client.post(
            reverse("resend_registration_code"),
            {"email": "lina.lang@example.test"},
        )

        self.assertRedirects(response, reverse("register_verify"))
        self.assertEqual(len(mail.outbox), 2)
        second_code = re.search(r"\b\d{6}\b", mail.outbox[1].body).group()
        verification.refresh_from_db()
        self.assertNotEqual(first_code, second_code)
        self.assertFalse(verification.matches(first_code))
        self.assertTrue(verification.matches(second_code))

    def test_registration_marks_account_email_as_username_for_password_managers(self) -> None:
        response = self.client.get(reverse("register"))

        self.assertContains(
            response,
            '<input type="email" name="email" class="uk-input" autocomplete="username"',
        )
        self.assertContains(
            response,
            '<input type="password" name="password1" class="uk-input" autocomplete="new-password"',
        )

    def test_verification_code_field_uses_one_time_code_autofill(self) -> None:
        response = self.client.get(reverse("register_verify"))

        self.assertContains(response, 'name="code" class="uk-input" autocomplete="one-time-code"')

    def test_registration_does_not_link_an_existing_person(self) -> None:
        Person.objects.create(
            vorname="Lina",
            nachname="Bestand",
            email="lina.lang@example.test",
        )

        response = self.client.post(reverse("register"), self.registration_data())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mit diesen Angaben kann kein Konto erstellt werden.")
        self.assertFalse(
            get_user_model().objects.filter(username="lina.lang@example.test").exists()
        )
        self.assertEqual(Person.objects.filter(email="lina.lang@example.test").count(), 1)


class AccessControlTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        self.applicant = self.create_user("bewerber@example.test", ROLE_APPLICANT)
        self.employee = self.create_user("mitarbeiter@example.test", ROLE_EMPLOYEE)
        self.account_manager = self.create_user("verwaltung@example.test", ROLE_USER_MANAGEMENT)

    def create_user(self, email: str, *roles: str):
        user = self.user_model.objects.create_user(
            username=email,
            email=email,
            password="FjordTanne!4826",
        )
        Person.objects.create(user=user, vorname="Test", nachname=email, email=email)
        user.groups.add(*(Group.objects.get(name=role) for role in roles))
        return user

    def test_anonymous_user_is_redirected_from_employee_pages(self) -> None:
        url = reverse("verwaltung:wohnung_list")

        response = self.client.get(url)

        self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_applicant_cannot_open_employee_pages(self) -> None:
        self.client.force_login(self.applicant)

        management_response = self.client.get(reverse("verwaltung:wohnung_list"))
        handover_response = self.client.get(reverse("wohnungsverwaltung:handover_protocol_list"))

        self.assertEqual(management_response.status_code, 403)
        self.assertEqual(handover_response.status_code, 403)

    def test_employee_can_open_management_and_handover_pages_without_staff_flag(self) -> None:
        self.client.force_login(self.employee)

        management_response = self.client.get(reverse("verwaltung:wohnung_list"))
        handover_response = self.client.get(reverse("wohnungsverwaltung:handover_protocol_list"))

        self.assertEqual(management_response.status_code, 200)
        self.assertEqual(handover_response.status_code, 200)

    def test_individual_permission_grants_employee_page_access(self) -> None:
        direct_user = self.create_user("direkt@example.test")
        permission = Permission.objects.get(codename="access_employee_area")
        direct_user.user_permissions.add(permission)
        self.client.force_login(direct_user)

        response = self.client.get(reverse("verwaltung:wohnung_list"))

        self.assertEqual(response.status_code, 200)

    def test_user_management_is_separate_from_employee_access(self) -> None:
        self.client.force_login(self.employee)
        employee_response = self.client.get(reverse("verwaltung:user_account_list"))

        self.client.force_login(self.account_manager)
        manager_response = self.client.get(reverse("verwaltung:user_account_list"))

        self.assertEqual(employee_response.status_code, 403)
        self.assertEqual(manager_response.status_code, 200)

    def test_tenant_role_can_be_assigned_without_removing_applicant_access(self) -> None:
        self.applicant.groups.add(Group.objects.get(name=ROLE_TENANT))

        self.assertTrue(self.applicant.has_perm(APPLICANT_ACCESS_PERMISSION))
        self.assertTrue(self.applicant.groups.filter(name=ROLE_APPLICANT).exists())
        self.assertTrue(self.applicant.groups.filter(name=ROLE_TENANT).exists())

    def test_navigation_only_shows_authorized_sections(self) -> None:
        self.client.force_login(self.applicant)
        applicant_response = self.client.get(reverse("home"))

        self.client.force_login(self.account_manager)
        manager_response = self.client.get(reverse("home"))

        self.assertContains(applicant_response, "Meine Bewerbungen")
        self.assertNotContains(applicant_response, ">Verwaltung<")
        self.assertContains(manager_response, ">Verwaltung<")
        self.assertContains(manager_response, ">Übergaben<")
        self.assertContains(manager_response, ">Benutzer<")


class UserAccountManagementTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        self.manager = self.user_model.objects.create_user(
            username="verwaltung@example.test",
            email="verwaltung@example.test",
            password="FjordTanne!4826",
        )
        Person.objects.create(
            user=self.manager,
            vorname="Verwaltung",
            nachname="Test",
            email="verwaltung@example.test",
        )
        self.manager.groups.add(Group.objects.get(name=ROLE_USER_MANAGEMENT))
        self.client.force_login(self.manager)

    def account_payload(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "person": "",
            "vorname": "Mona",
            "nachname": "Mieterin",
            "email": "mona.mieterin@example.test",
            "roles": [str(Group.objects.get(name=ROLE_APPLICANT).pk)],
            "direct_permissions": [],
            "is_active": "on",
            "password1": "FjordTanne!4826",
            "password2": "FjordTanne!4826",
        }
        payload.update(overrides)
        return payload

    def test_account_manager_can_create_a_linked_account_and_assign_tenant_role(self) -> None:
        roles = [
            str(Group.objects.get(name=ROLE_APPLICANT).pk),
            str(Group.objects.get(name=ROLE_TENANT).pk),
        ]

        response = self.client.post(
            reverse("verwaltung:user_account_create"), self.account_payload(roles=roles)
        )

        account = self.user_model.objects.get(username="mona.mieterin@example.test")
        self.assertRedirects(response, reverse("verwaltung:user_account_edit", args=[account.pk]))
        self.assertEqual(account.person_profile.email, "mona.mieterin@example.test")
        self.assertTrue(account.groups.filter(name=ROLE_APPLICANT).exists())
        self.assertTrue(account.groups.filter(name=ROLE_TENANT).exists())

    def test_account_manager_can_link_an_existing_person(self) -> None:
        person = Person.objects.create(
            vorname="Bestehende",
            nachname="Person",
            email="bestehend@example.test",
        )

        response = self.client.post(
            reverse("verwaltung:user_account_create"),
            self.account_payload(
                person=str(person.pk),
                vorname="",
                nachname="",
                email="",
            ),
        )

        account = self.user_model.objects.get(username="bestehend@example.test")
        self.assertRedirects(response, reverse("verwaltung:user_account_edit", args=[account.pk]))
        self.assertEqual(account.person_profile, person)

    def test_account_manager_deactivates_without_deleting_person(self) -> None:
        account = self.user_model.objects.create_user(
            username="deaktiviert@example.test",
            email="deaktiviert@example.test",
            password="FjordTanne!4826",
        )
        person = Person.objects.create(
            user=account,
            vorname="Deaktiviert",
            nachname="Test",
            email="deaktiviert@example.test",
        )
        account.groups.add(Group.objects.get(name=ROLE_APPLICANT))

        response = self.client.post(
            reverse("verwaltung:user_account_edit", args=[account.pk]),
            self.account_payload(
                person=str(person.pk),
                vorname="",
                nachname="",
                email="",
                password1="",
                password2="",
                is_active="",
            ),
        )

        self.assertRedirects(response, reverse("verwaltung:user_account_edit", args=[account.pk]))
        account.refresh_from_db()
        self.assertFalse(account.is_active)
        self.assertEqual(Person.objects.get(pk=person.pk).user, account)

    def test_last_account_manager_cannot_remove_their_own_management_role(self) -> None:
        person = self.manager.person_profile

        response = self.client.post(
            reverse("verwaltung:user_account_edit", args=[self.manager.pk]),
            self.account_payload(
                person=str(person.pk),
                vorname="",
                nachname="",
                email="",
                roles=[str(Group.objects.get(name=ROLE_EMPLOYEE).pk)],
                password1="",
                password2="",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Der letzte aktive Benutzerverwalter")
        self.assertTrue(self.manager.groups.filter(name=ROLE_USER_MANAGEMENT).exists())


class InitialUserManagerCommandTests(TestCase):
    def test_command_creates_a_linked_user_manager(self) -> None:
        call_command(
            "create_initial_user_manager",
            email="erste.verwaltung@example.test",
            password="FjordTanne!4826",
            first_name="Erste",
            last_name="Verwaltung",
            stdout=StringIO(),
        )

        account = get_user_model().objects.get(username="erste.verwaltung@example.test")

        self.assertTrue(account.check_password("FjordTanne!4826"))
        self.assertEqual(account.person_profile.email, "erste.verwaltung@example.test")
        self.assertTrue(account.person_profile.is_employee)
        self.assertTrue(account.groups.filter(name=ROLE_USER_MANAGEMENT).exists())
