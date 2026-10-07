"""Regression tests for account changes during authentication (issue #63)."""

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import Client, RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from core.views import RoleAwareLoginView
from wohnungsverwaltung.access import (
    ROLE_APPLICANT,
    ROLE_EMPLOYEE,
    ROLE_USER_MANAGEMENT,
    USER_MANAGEMENT_PERMISSION,
)
from wohnungsverwaltung.forms import RegistrationForm, UserAccountForm
from wohnungsverwaltung.models import EmployeeLoginVerification, Person, RegistrationVerification

PASSWORD = "FjordTanne!4826"
NEW_PASSWORD = "BirkenHafen!5927"


class AccountChangesMixin:
    def create_account(self, role=ROLE_APPLICANT, email="account@example.test"):
        user = get_user_model().objects.create_user(username=email, email=email, password=PASSWORD)
        Person.objects.create(user=user, vorname="Konto", nachname="Test", email=user.email)
        user.groups.add(Group.objects.get(name=role))
        return user

    def account_form(self, account, *, actor=None, **changes):
        account = get_user_model().objects.get(pk=account.pk)
        data = {
            "person": str(account.person_profile.pk),
            "roles": list(account.groups.values_list("pk", flat=True)),
            "direct_permissions": list(account.user_permissions.values_list("pk", flat=True)),
            "is_active": account.is_active,
            "password1": "",
            "password2": "",
        }
        data.update(changes)
        form = UserAccountForm(data, account=account, actor=actor)
        self.assertTrue(form.is_valid(), form.errors)
        return form

    def edit_account(self, account, **changes):
        return self.account_form(account, **changes).save()

    def mailed_code(self):
        return re.search(r"\b[0-9]{6}\b", mail.outbox[-1].body).group()

    def register_account(self):
        self.client.post(
            reverse("register"),
            {
                "vorname": "Konto",
                "nachname": "Test",
                "email": "account@example.test",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        return get_user_model().objects.get(username="account@example.test")


class AccountAuthenticationRegressionTests(AccountChangesMixin, TestCase):
    def test_unchanged_pending_registration_keeps_its_code_and_can_be_confirmed(self):
        account = self.register_account()
        code = self.mailed_code()
        before = RegistrationVerification.objects.values().get(user=account)

        self.edit_account(account)

        self.assertEqual(RegistrationVerification.objects.values().get(user=account), before)
        response = self.client.post(
            reverse("register_verify"), {"email": account.email, "code": code}
        )
        self.assertRedirects(response, reverse("wohnungsverwaltung:pre_application_list"))

    def test_unchanged_pending_registration_preserves_attempt_limits_and_resend_delay(self):
        account = self.register_account()
        verification = RegistrationVerification.objects.get(user=account)
        verification.attempts = verification.MAX_ATTEMPTS
        verification.save(update_fields=["attempts"])
        self.edit_account(account)

        self.client.post(reverse("resend_registration_code"), {"email": account.email})
        self.assertEqual(len(mail.outbox), 1)
        response = self.client.post(
            reverse("register_verify"), {"email": account.email, "code": self.mailed_code()}
        )
        self.assertContains(response, "Der Code konnte nicht bestätigt werden.")
        account.refresh_from_db()
        self.assertFalse(account.is_active)

        verification.refresh_from_db()
        verification.last_sent_at = timezone.now() - verification.RESEND_DELAY
        verification.save(update_fields=["last_sent_at"])
        self.client.post(reverse("resend_registration_code"), {"email": account.email})
        self.assertEqual(len(mail.outbox), 2)
        response = self.client.post(
            reverse("register_verify"), {"email": account.email, "code": self.mailed_code()}
        )
        self.assertRedirects(response, reverse("wohnungsverwaltung:pre_application_list"))

    def test_explicit_registration_revocation_blocks_confirmation_and_resending(self):
        account = self.register_account()
        code = self.mailed_code()
        self.edit_account(account, revoke_registration=True)
        self.assertFalse(RegistrationVerification.objects.filter(user=account).exists())
        self.client.post(reverse("resend_registration_code"), {"email": account.email})
        self.assertEqual(len(mail.outbox), 1)
        self.client.post(reverse("register_verify"), {"email": account.email, "code": code})
        account.refresh_from_db()
        self.assertFalse(account.is_active)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_password_validation_does_not_mutate_the_original_account(self):
        account = self.create_account()
        person = account.person_profile
        person.email = "changed@example.test"
        person.save(update_fields=["email"])
        form = UserAccountForm(
            {
                "person": str(person.pk),
                "roles": list(account.groups.values_list("pk", flat=True)),
                "is_active": True,
                "password1": NEW_PASSWORD,
                "password2": NEW_PASSWORD,
            },
            account=account,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(account.email, "account@example.test")
        self.assertEqual(account.username, "account@example.test")

    def assert_changed_credentials_reject_login(self, change):
        account = self.create_account(ROLE_EMPLOYEE)
        original_form_valid = RoleAwareLoginView.form_valid

        def change_after_password_check(view, form):
            change(account)
            return original_form_valid(view, form)

        with patch.object(RoleAwareLoginView, "form_valid", change_after_password_check):
            response = self.client.post(
                reverse("login"), {"username": account.username, "password": PASSWORD}
            )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(EmployeeLoginVerification.objects.filter(user=account).exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_password_change_after_password_check_rejects_the_pending_login(self):
        self.assert_changed_credentials_reject_login(
            lambda account: self.edit_account(
                account, password1=NEW_PASSWORD, password2=NEW_PASSWORD
            )
        )

    def test_email_change_after_password_check_rejects_the_pending_login(self):
        def change_email(account):
            person = Person.objects.get(user=account)
            person.email = "changed@example.test"
            person.save(update_fields=["email"])
            self.edit_account(account)

        self.assert_changed_credentials_reject_login(change_email)

    def test_person_transfer_after_password_check_cannot_issue_a_code_to_the_previous_owner(self):
        target = Person.objects.create(
            vorname="Andere", nachname="Person", email="new-owner@example.test"
        )
        self.assert_changed_credentials_reject_login(
            lambda account: self.edit_account(
                account, person=str(target.pk), password1=NEW_PASSWORD, password2=NEW_PASSWORD
            )
        )

    def test_old_pending_browser_cannot_use_the_code_from_a_new_password_login(self):
        account = self.create_account(ROLE_EMPLOYEE)
        self.client.post(reverse("login"), {"username": account.username, "password": PASSWORD})
        self.edit_account(account, password1=NEW_PASSWORD, password2=NEW_PASSWORD)
        new_client = Client()
        new_client.post(reverse("login"), {"username": account.username, "password": NEW_PASSWORD})
        code = self.mailed_code()

        self.client.post(reverse("employee_mfa_verify"), {"code": code})
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertTrue(EmployeeLoginVerification.objects.filter(user=account).exists())
        response = new_client.post(reverse("employee_mfa_verify"), {"code": code})
        self.assertRedirects(response, reverse("verwaltung:wohnung_list"))

    def test_a_stale_account_form_does_not_restore_the_previous_password(self):
        account = self.create_account()
        unchanged_form = self.account_form(account)
        self.edit_account(account, password1=NEW_PASSWORD, password2=NEW_PASSWORD)

        unchanged_form.save()

        account.refresh_from_db()
        self.assertTrue(account.check_password(NEW_PASSWORD))
        self.assertFalse(account.check_password(PASSWORD))

    def test_person_transfer_rechecks_the_new_password_against_the_locked_account(self):
        account = self.create_account()
        target = Person.objects.create(
            vorname="Andere", nachname="Person", email="new-owner@example.test"
        )
        transfer_form = self.account_form(
            account, person=str(target.pk), password1=NEW_PASSWORD, password2=NEW_PASSWORD
        )
        self.edit_account(account, password1=NEW_PASSWORD, password2=NEW_PASSWORD)

        with self.assertRaisesMessage(ValidationError, "muss ein neues Passwort vergeben werden"):
            transfer_form.save()
        target.refresh_from_db()
        self.assertIsNone(target.user_id)
        self.assertEqual(Person.objects.get(user=account).email, account.email)


class AccountFormEdgeCaseTests(AccountChangesMixin, TestCase):
    LONG_EMAIL = "a" * 64 + "@" + "d" * 63 + "." + "e" * 30 + ".test"

    def registration_data(self, email):
        return {
            "vorname": "Konto",
            "nachname": "Test",
            "email": email,
            "password1": PASSWORD,
            "password2": PASSWORD,
        }

    def new_account_data(self, person=None, email="account@example.test"):
        return {
            "person": str(person.pk) if person is not None else "",
            "vorname": "" if person is not None else "Konto",
            "nachname": "" if person is not None else "Test",
            "email": "" if person is not None else email,
            "roles": [Group.objects.get(name=ROLE_APPLICANT).pk],
            "is_active": True,
            "password1": PASSWORD,
            "password2": PASSWORD,
        }

    def test_registration_rejects_emails_longer_than_the_login_identifier(self):
        form = RegistrationForm(self.registration_data(self.LONG_EMAIL))
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)
        self.assertFalse(get_user_model().objects.exists())

    def test_registration_shows_a_form_error_for_long_email_instead_of_failing(self):
        response = self.client.post(reverse("register"), self.registration_data(self.LONG_EMAIL))
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(Person.objects.exists())

    def test_registration_accepts_an_email_at_the_login_identifier_limit(self):
        email = "a" * 64 + "@" + "d" * 63 + "." + "e" * 16 + ".test"
        self.assertEqual(len(email), 150)
        form = RegistrationForm(self.registration_data(email))
        self.assertTrue(form.is_valid(), form.errors)
        account = form.save()
        self.assertEqual(account.username, email)
        self.assertEqual(account.person_profile.email, email)

    def test_new_account_rejects_an_inline_email_longer_than_the_login_identifier(self):
        form = UserAccountForm(self.new_account_data(email=self.LONG_EMAIL))
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_new_account_rejects_a_selected_person_with_a_long_email(self):
        person = Person.objects.create(vorname="Konto", nachname="Test", email=self.LONG_EMAIL)
        form = UserAccountForm(self.new_account_data(person=person))
        self.assertFalse(form.is_valid())
        self.assertIn("person", form.errors)

    def test_account_edit_rejects_a_person_email_longer_than_the_login_identifier(self):
        account = self.create_account()
        person = account.person_profile
        person.email = self.LONG_EMAIL
        person.save(update_fields=["email"])
        form = UserAccountForm(
            {"person": str(person.pk), "is_active": True, "password1": "", "password2": ""},
            account=account,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("person", form.errors)

    def test_account_save_rechecks_a_person_email_changed_after_validation(self):
        person = Person.objects.create(
            vorname="Konto", nachname="Test", email="account@example.test"
        )
        form = UserAccountForm(self.new_account_data(person=person))
        self.assertTrue(form.is_valid(), form.errors)
        person.email = self.LONG_EMAIL
        person.save(update_fields=["email"])
        with self.assertRaises(ValidationError):
            form.save()
        self.assertFalse(get_user_model().objects.exists())
        person.refresh_from_db()
        self.assertIsNone(person.user_id)

    def test_person_transfer_validation_does_not_upgrade_a_stored_password_hash(self):
        account = self.create_account()
        account.password = PBKDF2PasswordHasher().encode(PASSWORD, "legacy-salt", iterations=1)
        account.save(update_fields=["password"])
        legacy_hash = account.password
        target = Person.objects.create(vorname="Andere", nachname="Person", email="other@test.de")
        form = UserAccountForm(self.new_account_data(person=target), account=account)
        self.assertFalse(form.is_valid())
        self.assertIn("password1", form.errors)
        account.refresh_from_db()
        self.assertEqual(account.password, legacy_hash)

    def test_an_ordinary_login_still_upgrades_a_legacy_password_hash(self):
        account = self.create_account(ROLE_EMPLOYEE)
        account.password = PBKDF2PasswordHasher().encode(PASSWORD, "legacy-salt", iterations=1)
        account.save(update_fields=["password"])
        legacy_hash = account.password
        response = self.client.post(
            reverse("login"), {"username": account.username, "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("employee_mfa_verify"))
        account.refresh_from_db()
        self.assertNotEqual(account.password, legacy_hash)
        self.assertTrue(account.check_password(PASSWORD))
        self.client.post(reverse("employee_mfa_verify"), {"code": self.mailed_code()})
        self.assertEqual(self.client.session["_auth_user_id"], str(account.pk))

    def assert_stale_change_keeps_last_manager(self, *, direct_permission=False, deactivate=False):
        first = self.create_account(ROLE_USER_MANAGEMENT, email="first@example.test")
        second = self.create_account(
            ROLE_EMPLOYEE if direct_permission else ROLE_USER_MANAGEMENT,
            email="second@example.test",
        )
        if direct_permission:
            second.user_permissions.add(Permission.objects.get(codename="manage_user_accounts"))
        first_form = self.account_form(
            first, actor=first, roles=[Group.objects.get(name=ROLE_EMPLOYEE).pk]
        )
        second_form = self.account_form(
            second,
            actor=first if deactivate else second,
            roles=[Group.objects.get(name=ROLE_EMPLOYEE).pk],
            direct_permissions=[],
            is_active=not deactivate,
        )
        changed = first_form.save()
        self.assertFalse(changed.has_perm(USER_MANAGEMENT_PERMISSION))
        with self.assertRaisesMessage(ValidationError, "letzte aktive Benutzerverwalter"):
            second_form.save()
        second.refresh_from_db()
        self.assertTrue(second.has_perm(USER_MANAGEMENT_PERMISSION))

    def test_stale_role_demotions_keep_the_last_active_manager(self):
        self.assert_stale_change_keeps_last_manager()

    def test_stale_direct_permission_removal_keeps_the_last_active_manager(self):
        self.assert_stale_change_keeps_last_manager(direct_permission=True)

    def test_stale_deactivation_keeps_the_last_active_manager(self):
        self.assert_stale_change_keeps_last_manager(deactivate=True)

    def test_a_superuser_can_change_roles_without_losing_management_access(self):
        account = self.create_account(ROLE_USER_MANAGEMENT)
        account.is_superuser = True
        account.save(update_fields=["is_superuser"])
        form = self.account_form(
            account, actor=account, roles=[Group.objects.get(name=ROLE_APPLICANT).pk]
        )
        changed = form.save()
        self.assertTrue(changed.has_perm(USER_MANAGEMENT_PERMISSION))


class ConcurrentAccountAuthenticationTests(AccountChangesMixin, TransactionTestCase):
    def run_revocation_before_login_finishes(
        self, authenticate, login_target, revoke, *, original_operation=None, pause_when=None
    ):
        """Pause at login; resume only after the change commits or is blocked by its row lock."""
        from django.contrib.auth import login as original_login

        original_operation = original_operation or original_login
        login_ready = threading.Event()
        resume_login = threading.Event()
        change_ready = threading.Event()
        change_done = threading.Event()
        change_pid = []

        def paused_login(*args, **kwargs):
            if pause_when is not None and not pause_when(*args, **kwargs):
                return original_operation(*args, **kwargs)
            login_ready.set()
            if not resume_login.wait(10):
                raise AssertionError("Timed out waiting for the controlled account change")
            return original_operation(*args, **kwargs)

        def login_worker():
            close_old_connections()
            try:
                return authenticate()
            finally:
                close_old_connections()

        def change_worker():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    change_pid.append(cursor.fetchone()[0])
                change_ready.set()
                return revoke()
            finally:
                change_done.set()
                close_old_connections()

        patched = (
            patch.object(*login_target, paused_login)
            if isinstance(login_target, tuple)
            else patch(login_target, paused_login)
        )
        was_blocked = False
        with patched, ThreadPoolExecutor(max_workers=2) as executor:
            login_future = executor.submit(login_worker)
            try:
                self.assertTrue(login_ready.wait(10), "Login did not reach the controlled boundary")
                change_future = executor.submit(change_worker)
                self.assertTrue(change_ready.wait(10))
                deadline = time.monotonic() + 10
                while not change_future.done():
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_blocking_pids(%s)", [change_pid[0]])
                        if cursor.fetchone()[0]:
                            was_blocked = True
                            break
                    self.assertLess(
                        time.monotonic(), deadline, "Account change neither ran nor waited"
                    )
                    change_done.wait(0.01)
            finally:
                resume_login.set()
            return (
                login_future.result(timeout=10),
                change_future.result(timeout=10),
                was_blocked,
            )

    def test_password_hash_upgrade_cannot_overwrite_a_concurrent_password_reset(self):
        account = self.create_account(ROLE_EMPLOYEE)
        account.password = PBKDF2PasswordHasher().encode(PASSWORD, "legacy-salt", iterations=1)
        account.save(update_fields=["password"])
        user_model = get_user_model()
        self.run_revocation_before_login_finishes(
            lambda: self.client.post(
                reverse("login"), {"username": account.username, "password": PASSWORD}
            ),
            (user_model, "check_password"),
            lambda: self.edit_account(account, password1=NEW_PASSWORD, password2=NEW_PASSWORD),
            original_operation=user_model.check_password,
        )
        account.refresh_from_db()
        self.assertTrue(account.check_password(NEW_PASSWORD))
        self.assertFalse(account.check_password(PASSWORD))
        self.assertFalse(EmployeeLoginVerification.objects.filter(user=account).exists())
        if mail.outbox:
            self.client.post(reverse("employee_mfa_verify"), {"code": self.mailed_code()})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_slow_mail_delivery_does_not_block_administrative_deactivation(self):
        account = self.create_account(ROLE_EMPLOYEE)
        delivered_codes = []
        _, _, was_blocked = self.run_revocation_before_login_finishes(
            lambda: self.client.post(
                reverse("login"), {"username": account.username, "password": PASSWORD}
            ),
            "core.views.send_employee_mfa_code",
            lambda: self.edit_account(account, is_active=False),
            original_operation=lambda email, code: delivered_codes.append(code),
        )
        self.assertFalse(was_blocked, "SMTP delivery must not hold the account row lock")
        account.refresh_from_db()
        self.assertFalse(account.is_active)
        self.assertFalse(EmployeeLoginVerification.objects.filter(user=account).exists())
        self.client.post(reverse("employee_mfa_verify"), {"code": delivered_codes[0]})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_concurrent_self_demotions_keep_one_active_account_manager(self):
        first = self.create_account(ROLE_USER_MANAGEMENT, email="first@example.test")
        second = self.create_account(ROLE_USER_MANAGEMENT, email="second@example.test")
        employee_role = Group.objects.get(name=ROLE_EMPLOYEE)
        first_form = self.account_form(first, actor=first, roles=[employee_role.pk])
        second_form = self.account_form(second, actor=second, roles=[employee_role.pk])
        groups_manager = type(first.groups)

        def save_second():
            try:
                second_form.save()
            except ValidationError:
                return False
            return True

        _, second_succeeded, _ = self.run_revocation_before_login_finishes(
            first_form.save,
            (groups_manager, "set"),
            save_second,
            original_operation=groups_manager.set,
            pause_when=lambda manager, *args, **kwargs: manager.instance.pk == first.pk,
        )
        self.assertFalse(second_succeeded)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.has_perm(USER_MANAGEMENT_PERMISSION))
        self.assertTrue(second.has_perm(USER_MANAGEMENT_PERMISSION))

    def test_role_or_direct_permission_elevation_cannot_be_overtaken_by_applicant_login(self):
        for direct in (False, True):
            with self.subTest(direct_permission=direct):
                account = self.create_account(email=f"account-{direct}@example.test")
                applicant_client = Client()

                def promote():
                    if direct:
                        self.edit_account(
                            account,
                            direct_permissions=[
                                Permission.objects.get(codename="access_employee_area").pk
                            ],
                        )
                    else:
                        self.edit_account(
                            account,
                            roles=list(account.groups.values_list("pk", flat=True))
                            + [Group.objects.get(name=ROLE_EMPLOYEE).pk],
                        )

                self.run_revocation_before_login_finishes(
                    lambda: applicant_client.post(
                        reverse("login"), {"username": account.username, "password": PASSWORD}
                    ),
                    "django.contrib.auth.views.auth_login",
                    promote,
                )
                response = applicant_client.get(
                    reverse("wohnungsverwaltung:employee_application_list")
                )
                self.assertEqual(response.status_code, 302)
                self.assertNotIn("_auth_user_id", applicant_client.session)
                self.assertFalse(EmployeeLoginVerification.objects.filter(user=account).exists())

    def test_email_change_cannot_be_overtaken_by_mfa_confirmation(self):
        account = self.create_account(ROLE_EMPLOYEE)
        self.client.post(reverse("login"), {"username": account.username, "password": PASSWORD})
        code = self.mailed_code()

        def change_email():
            person = Person.objects.get(user=account)
            person.email = "changed@example.test"
            person.save(update_fields=["email"])
            self.edit_account(account)

        self.run_revocation_before_login_finishes(
            lambda: self.client.post(reverse("employee_mfa_verify"), {"code": code}),
            "core.views.login",
            change_email,
        )
        self.assertEqual(
            self.client.get(reverse("wohnungsverwaltung:employee_application_list")).status_code,
            302,
        )
        self.assertFalse(EmployeeLoginVerification.objects.filter(user=account).exists())

    def test_registration_confirmation_cannot_restore_a_session_after_role_elevation(self):
        account = self.register_account()
        code = self.mailed_code()
        self.run_revocation_before_login_finishes(
            lambda: self.client.post(
                reverse("register_verify"), {"email": account.email, "code": code}
            ),
            "core.views.login",
            lambda: self.edit_account(
                account,
                roles=[Group.objects.get(name=ROLE_EMPLOYEE).pk],
            ),
        )
        self.assertEqual(
            self.client.get(reverse("wohnungsverwaltung:employee_application_list")).status_code,
            302,
        )
        self.assertFalse(RegistrationVerification.objects.filter(user=account).exists())

    def test_late_session_middleware_save_cannot_recreate_a_revoked_session(self):
        account = self.create_account()
        request = RequestFactory().post(
            reverse("login"), {"username": account.username, "password": PASSWORD}
        )
        request.session = SessionStore()
        request.user = AnonymousUser()
        request._dont_enforce_csrf_checks = True
        # Call the view directly to hold back SessionMiddleware's final save.
        response = RoleAwareLoginView.as_view()(request)
        self.assertEqual(response.status_code, 302)
        session_key = request.session.session_key
        self.assertEqual(
            Session.objects.get(session_key=session_key).get_decoded()["_auth_user_id"],
            str(account.pk),
        )
        self.edit_account(account, password1=NEW_PASSWORD, password2=NEW_PASSWORD)
        with self.assertRaises(SessionInterrupted):
            SessionMiddleware(lambda request: response).process_response(request, response)
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())
