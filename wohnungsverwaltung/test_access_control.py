import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .access import (
    APPLICANT_ACCESS_PERMISSION,
    ROLE_APPLICANT,
    ROLE_EMPLOYEE,
    ROLE_TENANT,
    ROLE_USER_MANAGEMENT,
)
from .models import (
    AccountLoginThrottle,
    EmployeeLoginVerification,
    LoginIpThrottle,
    Person,
    RegistrationVerification,
)


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

    def test_registration_verification_does_not_log_in_a_newly_privileged_account(self):
        self.client.post(reverse("register"), self.registration_data())
        code = re.search(r"\b[0-9]{6}\b", mail.outbox[0].body).group()
        account = get_user_model().objects.get(username="lina.lang@example.test")
        account.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        response = self.client.post(
            reverse("register_verify"), {"email": account.email, "code": code}
        )
        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(
            self.client.get(reverse("wohnungsverwaltung:employee_application_list")).status_code,
            302,
        )
        self.assertRedirects(
            self.client.post(
                reverse("login"), {"username": account.email, "password": "FjordTanne!4826"}
            ),
            reverse("employee_mfa_verify"),
        )

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

    def test_employee_cannot_open_the_applicant_application_overview(self) -> None:
        self.client.force_login(self.employee)

        response = self.client.get(reverse("wohnungsverwaltung:pre_application_list"))

        self.assertEqual(response.status_code, 403)

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

    def test_employee_navigation_hides_public_applicant_links(self) -> None:
        direct_user = self.create_user("navigation-direct@example.test")
        direct_user.user_permissions.add(Permission.objects.get(codename="access_employee_area"))
        for user in (self.employee, self.account_manager, direct_user):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("home"))
                self.assertNotContains(response, ">Wohnungen finden<")
                self.assertNotContains(response, ">Bewerbungsvorschau<")
                self.assertContains(response, ">Verwaltung<")

    def test_public_and_applicant_navigation_keeps_apartment_links(self) -> None:
        for user in (None, self.applicant):
            with self.subTest(user=user):
                self.client.logout()
                if user is not None:
                    self.client.force_login(user)
                response = self.client.get(reverse("home"))
                self.assertContains(response, ">Wohnungen finden<")
                self.assertContains(response, ">Bewerbungsvorschau<")

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


class EmployeeMfaLoginTests(TestCase):
    def setUp(self) -> None:
        self.user_model = get_user_model()
        self.employee = self.user_model.objects.create_user(
            username="mitarbeiter.mfa@example.test",
            email="mitarbeiter.mfa@example.test",
            password="FjordTanne!4826",
        )
        Person.objects.create(
            user=self.employee,
            vorname="MFA",
            nachname="Mitarbeiter",
            email="mitarbeiter.mfa@example.test",
            is_employee=True,
        )
        self.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))

    def login_employee(self, **extra_data: str):
        data = {
            "username": "mitarbeiter.mfa@example.test",
            "password": "FjordTanne!4826",
        }
        data.update(extra_data)
        return self.client.post(reverse("login"), data)

    def test_employee_password_login_requires_a_mailed_code_before_session_creation(self) -> None:
        response = self.login_employee()

        self.assertRedirects(response, reverse("employee_mfa_verify"))
        self.assertNotIn("_auth_user_id", self.client.session)
        verification = EmployeeLoginVerification.objects.get(user=self.employee)
        self.assertEqual(len(mail.outbox), 1)
        code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group()
        self.assertTrue(verification.matches(code))
        self.assertNotIn(code, verification.code_hash)

    def test_direct_user_management_permission_requires_a_mailed_code_before_session_creation(
        self,
    ) -> None:
        account_manager = self.user_model.objects.create_user(
            username="direkte-verwaltung@example.test",
            email="direkte-verwaltung@example.test",
            password="FjordTanne!4826",
        )
        Person.objects.create(
            user=account_manager,
            vorname="Direkte",
            nachname="Verwaltung",
            email="direkte-verwaltung@example.test",
        )
        account_manager.user_permissions.add(
            Permission.objects.get(codename="manage_user_accounts")
        )

        response = self.client.post(
            reverse("login"),
            {"username": account_manager.username, "password": "FjordTanne!4826"},
        )

        self.assertRedirects(response, reverse("employee_mfa_verify"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(EmployeeLoginVerification.objects.filter(user=account_manager).exists())
        self.assertEqual(len(mail.outbox), 1)
        code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group()

        response = self.client.post(reverse("employee_mfa_verify"), {"code": code})

        self.assertRedirects(response, reverse("verwaltung:user_account_list"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_valid_mfa_code_logs_an_employee_in_and_preserves_next_url(self) -> None:
        target_url = reverse("verwaltung:wohnung_list")
        self.login_employee(next=target_url)
        code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group()

        response = self.client.post(reverse("employee_mfa_verify"), {"code": code})

        self.assertRedirects(response, target_url)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertFalse(EmployeeLoginVerification.objects.filter(user=self.employee).exists())

    def test_valid_mfa_code_redirects_to_employee_management_by_default(self) -> None:
        self.login_employee()
        code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group()

        response = self.client.post(reverse("employee_mfa_verify"), {"code": code})

        self.assertRedirects(response, reverse("verwaltung:wohnung_list"))

    def test_employee_login_after_logout_issues_a_new_code(self) -> None:
        self.login_employee()
        first_code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group()
        self.client.post(reverse("employee_mfa_verify"), {"code": first_code})
        self.client.post(reverse("logout"))

        response = self.login_employee()

        self.assertRedirects(response, reverse("employee_mfa_verify"))
        self.assertEqual(len(mail.outbox), 2)
        second_code = re.search(r"\b\d{6}\b", mail.outbox[1].body).group()
        self.assertNotEqual(first_code, second_code)

    def test_invalid_mfa_code_does_not_create_a_session(self) -> None:
        self.login_employee()

        response = self.client.post(reverse("employee_mfa_verify"), {"code": "000000"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Der Code konnte nicht bestätigt werden.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_expired_mfa_code_does_not_create_a_session(self) -> None:
        self.login_employee()
        verification = EmployeeLoginVerification.objects.get(user=self.employee)
        verification.expires_at = timezone.now() - timedelta(seconds=1)
        verification.save(update_fields=["expires_at"])
        code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group()

        response = self.client.post(reverse("employee_mfa_verify"), {"code": code})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Der Code konnte nicht bestätigt werden.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_mfa_page_without_a_pending_employee_login_redirects_to_login(self) -> None:
        response = self.client.get(reverse("employee_mfa_verify"))

        self.assertRedirects(response, reverse("login"))


class PasswordLoginThrottleTests(TestCase):
    LOGIN_FAILURE_MESSAGE = (
        "Bitte überprüfen Sie Ihre Zugangsdaten und versuchen Sie es später erneut."
    )

    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="anmeldung@example.test",
            email="anmeldung@example.test",
            password="FjordTanne!4826",
        )
        Person.objects.create(
            user=self.user,
            vorname="Anmeldung",
            nachname="Test",
            email="anmeldung@example.test",
        )

    def login(self, username: str = "anmeldung@example.test", password: str = "falsch"):
        return self.client.post(reverse("login"), {"username": username, "password": password})

    def assert_login_is_rejected(self, response) -> None:
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.LOGIN_FAILURE_MESSAGE)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_three_failed_passwords_lock_an_account_without_starting_mfa(self) -> None:
        self.user.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        unknown_response = self.login(username="unbekannt@example.test")
        first_failure = self.login()
        second_failure = self.login()
        third_failure = self.login()

        for response in (unknown_response, first_failure, second_failure, third_failure):
            self.assert_login_is_rejected(response)
        throttle = AccountLoginThrottle.objects.get(user=self.user)
        self.assertEqual(throttle.failed_attempts, 3)
        self.assertGreater(throttle.locked_until, timezone.now())

        locked_response = self.login(password="FjordTanne!4826")

        self.assert_login_is_rejected(locked_response)
        self.assertFalse(EmployeeLoginVerification.objects.filter(user=self.user).exists())

    def test_expired_account_lock_allows_login_and_removes_the_throttle(self) -> None:
        for _ in range(3):
            self.login()
        throttle = AccountLoginThrottle.objects.get(user=self.user)
        throttle.locked_until = timezone.now() - timedelta(seconds=1)
        throttle.save(update_fields=["locked_until"])

        response = self.login(password="FjordTanne!4826")

        self.assertRedirects(response, reverse("home"))
        self.assertIn("_auth_user_id", self.client.session)
        self.assertFalse(AccountLoginThrottle.objects.filter(user=self.user).exists())

    def test_successful_login_resets_account_failure_count(self) -> None:
        self.login()
        self.login()

        response = self.login(password="FjordTanne!4826")

        self.assertRedirects(response, reverse("home"))
        self.assertFalse(AccountLoginThrottle.objects.filter(user=self.user).exists())

    def test_ten_failed_logins_from_an_ip_limit_other_accounts_without_storing_raw_ip(self) -> None:
        for attempt in range(10):
            response = self.login(username=f"unbekannt-{attempt}@example.test")
            self.assert_login_is_rejected(response)

        throttle = LoginIpThrottle.objects.get()
        self.assertEqual(throttle.failed_attempts, 10)
        self.assertGreater(throttle.locked_until, timezone.now())
        self.assertRegex(throttle.ip_fingerprint, r"^[0-9a-f]{64}$")
        self.assertNotIn("127.0.0.1", throttle.ip_fingerprint)

        response = self.login(password="FjordTanne!4826")

        self.assert_login_is_rejected(response)

    def test_untrusted_forwarded_for_header_does_not_change_the_client_ip(self) -> None:
        response = self.client.post(
            reverse("login"),
            {"username": "unbekannt@example.test", "password": "falsch"},
            REMOTE_ADDR="198.51.100.10",
            HTTP_X_FORWARDED_FOR="203.0.113.10",
        )

        self.assert_login_is_rejected(response)
        throttle = LoginIpThrottle.objects.get()
        self.assertEqual(
            throttle.ip_fingerprint,
            salted_hmac("login-ip-throttle", "198.51.100.10", algorithm="sha256").hexdigest(),
        )

    @override_settings(LOGIN_THROTTLE_TRUSTED_PROXY_IPS=("198.51.100.10",))
    def test_trusted_proxy_uses_the_forwarded_client_ip(self) -> None:
        response = self.client.post(
            reverse("login"),
            {"username": "unbekannt@example.test", "password": "falsch"},
            REMOTE_ADDR="198.51.100.10",
            HTTP_X_FORWARDED_FOR="203.0.113.10",
        )

        self.assert_login_is_rejected(response)
        throttle = LoginIpThrottle.objects.get()
        self.assertEqual(
            throttle.ip_fingerprint,
            salted_hmac("login-ip-throttle", "203.0.113.10", algorithm="sha256").hexdigest(),
        )


class PasswordLoginThrottleConcurrencyTests(TransactionTestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="parallel@example.test",
            email="parallel@example.test",
            password="FjordTanne!4826",
        )
        self.login_url = reverse("login")

    def test_parallel_failed_logins_consistently_lock_an_account(self) -> None:
        barrier = threading.Barrier(3)

        def submit_failed_login() -> int:
            close_old_connections()
            try:
                client = Client()
                barrier.wait()
                response = client.post(
                    self.login_url,
                    {"username": self.user.username, "password": "falsch"},
                )
                return response.status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=3) as executor:
            statuses = list(executor.map(lambda _index: submit_failed_login(), range(3)))

        throttle = AccountLoginThrottle.objects.get(user=self.user)
        self.assertEqual(statuses, [200, 200, 200])
        self.assertEqual(throttle.failed_attempts, 3)
        self.assertGreater(throttle.locked_until, timezone.now())


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

    def test_new_employee_permissions_require_existing_applicant_sessions_to_log_in_again(self):
        for direct_permission in (False, True):
            with self.subTest(direct_permission=direct_permission):
                email = f"upgrade-{direct_permission}@example.test"
                account = self.user_model.objects.create_user(
                    username=email, email=email, password="FjordTanne!4826"
                )
                person = Person.objects.create(
                    user=account, vorname="Rollen", nachname="Test", email=email
                )
                account.groups.add(Group.objects.get(name=ROLE_APPLICANT))
                applicant_client = Client()
                applicant_client.post(
                    reverse("login"), {"username": email, "password": "FjordTanne!4826"}
                )
                self.assertEqual(
                    applicant_client.get(
                        reverse("wohnungsverwaltung:pre_application_list")
                    ).status_code,
                    200,
                )
                employee_group = Group.objects.get(name=ROLE_EMPLOYEE)
                employee_permission = Permission.objects.get(codename="access_employee_area")
                response = self.client.post(
                    reverse("verwaltung:user_account_edit", args=[account.pk]),
                    self.account_payload(
                        person=str(person.pk),
                        vorname="",
                        nachname="",
                        email="",
                        password1="",
                        password2="",
                        roles=[str(Group.objects.get(name=ROLE_APPLICANT).pk)]
                        + ([] if direct_permission else [str(employee_group.pk)]),
                        direct_permissions=[str(employee_permission.pk)]
                        if direct_permission
                        else [],
                    ),
                )
                self.assertEqual(response.status_code, 302)
                dashboard = applicant_client.get(
                    reverse("wohnungsverwaltung:employee_application_list")
                )
                self.assertRedirects(
                    dashboard,
                    reverse("login")
                    + "?next="
                    + reverse("wohnungsverwaltung:employee_application_list"),
                )
                login_response = applicant_client.post(
                    reverse("login"), {"username": email, "password": "FjordTanne!4826"}
                )
                self.assertRedirects(login_response, reverse("employee_mfa_verify"))
                self.assertEqual(
                    applicant_client.get(
                        reverse("wohnungsverwaltung:employee_application_list")
                    ).status_code,
                    302,
                )
                code = re.search(r"\b[0-9]{6}\b", mail.outbox[-1].body).group()
                self.assertEqual(
                    applicant_client.post(
                        reverse("employee_mfa_verify"), {"code": code}
                    ).status_code,
                    302,
                )
                self.assertEqual(
                    applicant_client.get(
                        reverse("wohnungsverwaltung:employee_application_list")
                    ).status_code,
                    200,
                )
                self.assertEqual(
                    self.client.get(reverse("verwaltung:user_account_list")).status_code, 200
                )

    def test_edit_without_privilege_elevation_preserves_existing_session(self):
        account = self.user_model.objects.create_user(
            username="unchanged@example.test",
            email="unchanged@example.test",
            password="FjordTanne!4826",
        )
        person = Person.objects.create(
            user=account, vorname="Unverändert", nachname="Test", email=account.email
        )
        account.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        form_response = self.client.get(reverse("verwaltung:user_account_edit", args=[account.pk]))
        self.assertNotContains(form_response, "Offene Registrierung widerrufen")
        applicant_client = Client()
        applicant_client.force_login(account)
        response = self.client.post(
            reverse("verwaltung:user_account_edit", args=[account.pk]),
            self.account_payload(
                person=str(person.pk), vorname="", nachname="", email="", password1="", password2=""
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            applicant_client.get(reverse("wohnungsverwaltung:pre_application_list")).status_code,
            200,
        )

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

    def test_password_reset_invalidates_a_pending_employee_login_code(self):
        pending_client = Client()
        pending_client.post(
            reverse("login"), {"username": self.manager.username, "password": "FjordTanne!4826"}
        )
        code = re.search(r"\b[0-9]{6}\b", mail.outbox[-1].body).group()
        response = self.client.post(
            reverse("verwaltung:user_account_edit", args=[self.manager.pk]),
            self.account_payload(
                person=str(self.manager.person_profile.pk),
                vorname="",
                nachname="",
                email="",
                roles=[str(Group.objects.get(name=ROLE_USER_MANAGEMENT).pk)],
                password1="BirkenHafen!5927",
                password2="BirkenHafen!5927",
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(EmployeeLoginVerification.objects.filter(user=self.manager).exists())
        pending_client.post(reverse("employee_mfa_verify"), {"code": code})
        self.assertNotIn("_auth_user_id", pending_client.session)
        self.assertEqual(
            pending_client.get(reverse("wohnungsverwaltung:employee_application_list")).status_code,
            302,
        )

    def test_administratively_disabled_registration_cannot_reactivate_with_old_code(self):
        pending_client = Client()
        pending_client.post(reverse("register"), RegistrationViewTests().registration_data())
        account = self.user_model.objects.get(username="lina.lang@example.test")
        code = re.search(r"\b[0-9]{6}\b", mail.outbox[-1].body).group()
        form_response = self.client.get(reverse("verwaltung:user_account_edit", args=[account.pk]))
        self.assertContains(form_response, "Offene Registrierung widerrufen")
        response = self.client.post(
            reverse("verwaltung:user_account_edit", args=[account.pk]),
            self.account_payload(
                person=str(account.person_profile.pk),
                vorname="",
                nachname="",
                email="",
                password1="",
                password2="",
                is_active="",
                revoke_registration="on",
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RegistrationVerification.objects.filter(user=account).exists())
        pending_client.post(reverse("register_verify"), {"email": account.email, "code": code})
        account.refresh_from_db()
        self.assertFalse(account.is_active)
        self.assertNotIn("_auth_user_id", pending_client.session)

    def test_reassigning_an_account_to_another_person_requires_a_new_password(self):
        account = self.user_model.objects.create_user(
            username="previous@example.test",
            email="previous@example.test",
            password="FjordTanne!4826",
        )
        previous = Person.objects.create(
            user=account, vorname="Vorher", nachname="Test", email=account.email
        )
        target = Person.objects.create(
            vorname="Andere", nachname="Person", email="target@example.test"
        )
        response = self.client.post(
            reverse("verwaltung:user_account_edit", args=[account.pk]),
            self.account_payload(
                person=str(target.pk), vorname="", nachname="", email="", password1="", password2=""
            ),
        )
        self.assertEqual(response.status_code, 200)
        account.refresh_from_db()
        self.assertEqual(account.person_profile.pk, previous.pk)
        self.assertContains(
            response, "Bei einem Personenwechsel muss ein neues Passwort vergeben werden."
        )

        response = self.client.post(
            reverse("verwaltung:user_account_edit", args=[account.pk]),
            self.account_payload(
                person=str(target.pk),
                vorname="",
                nachname="",
                email="",
                password1="FjordTanne!4826",
                password2="FjordTanne!4826",
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "Bei einem Personenwechsel muss ein neues Passwort vergeben werden."
        )

        previous_client = Client()
        previous_client.force_login(account)
        response = self.client.post(
            reverse("verwaltung:user_account_edit", args=[account.pk]),
            self.account_payload(
                person=str(target.pk),
                vorname="",
                nachname="",
                email="",
                password1="BirkenHafen!5927",
                password2="BirkenHafen!5927",
            ),
        )
        self.assertEqual(response.status_code, 302)
        account.refresh_from_db()
        previous.refresh_from_db()
        self.assertIsNone(previous.user_id)
        self.assertEqual(account.person_profile.pk, target.pk)
        self.assertEqual(account.email, target.email)
        self.assertFalse(account.check_password("FjordTanne!4826"))
        self.assertTrue(account.check_password("BirkenHafen!5927"))
        self.assertNotIn("_auth_user_id", previous_client.session)

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


class CreateDevelopmentEmployeeCommandTests(TestCase):
    @override_settings(DEBUG=True)
    def test_command_creates_an_active_linked_employee_account(self) -> None:
        call_command(
            "create_development_employee",
            email="mitarbeiter@example.test",
            password="KometFjord!4826",
            stdout=StringIO(),
        )

        account = get_user_model().objects.get(username="mitarbeiter@example.test")

        self.assertTrue(account.is_active)
        self.assertTrue(account.check_password("KometFjord!4826"))
        self.assertTrue(account.person_profile.is_employee)
        self.assertTrue(account.groups.filter(name=ROLE_EMPLOYEE).exists())

        account.is_active = False
        account.set_password("AnderesPasswort!4826")
        account.save()
        call_command(
            "create_development_employee",
            email="mitarbeiter@example.test",
            password="KometFjord!4826",
            stdout=StringIO(),
        )

        account.refresh_from_db()
        self.assertTrue(account.is_active)
        self.assertTrue(account.check_password("KometFjord!4826"))
        self.assertEqual(get_user_model().objects.filter(username=account.username).count(), 1)

    @override_settings(DEBUG=False)
    def test_command_refuses_to_run_outside_development(self) -> None:
        with self.assertRaises(CommandError):
            call_command(
                "create_development_employee",
                email="mitarbeiter@example.test",
                password="KometFjord!4826",
                stdout=StringIO(),
            )
