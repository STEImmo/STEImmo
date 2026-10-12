"""Account administration and mail-failure regressions found after issue #63."""

from smtplib import SMTPException
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.messages import get_messages
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.test_auth_revocation import NEW_PASSWORD, PASSWORD, AccountChangesMixin
from core.views import (
    EMPLOYEE_MFA_CHALLENGE_SESSION_KEY,
    EMPLOYEE_MFA_REDIRECT_SESSION_KEY,
    EMPLOYEE_MFA_USER_SESSION_KEY,
)
from wohnungsverwaltung.access import (
    ROLE_EMPLOYEE,
    ROLE_USER_MANAGEMENT,
    USER_MANAGEMENT_PERMISSION,
)
from wohnungsverwaltung.forms import RegistrationForm, UserAccountForm
from wohnungsverwaltung.models import (
    AccountLoginThrottle,
    EmployeeLoginVerification,
    Person,
    RegistrationVerification,
)


class AccountRecoveryTests(AccountChangesMixin, TestCase):
    def registration_data(self, **changes):
        data = {
            "vorname": "Konto",
            "nachname": "Test",
            "email": "account@example.test",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        data.update(changes)
        return data

    def new_account_form(self, *, person=None, actor=None, **changes):
        data = {"is_active": True, **self.registration_data(**changes)}
        if person is not None:
            data.update(person=str(person.pk), vorname="", nachname="", email="")
        return UserAccountForm(data, actor=actor)

    def test_registration_rejects_names_exceeding_user_storage(self):
        for field in ("vorname", "nachname"):
            with self.subTest(field=field):
                form = RegistrationForm(self.registration_data(**{field: "A" * 151}))
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_registration_accepts_names_at_the_user_storage_limit(self):
        form = RegistrationForm(self.registration_data(vorname="A" * 150, nachname="B" * 150))
        self.assertTrue(form.is_valid(), form.errors)
        account = form.save()
        self.assertEqual(account.first_name, "A" * 150)
        self.assertEqual(account.last_name, "B" * 150)
        self.assertEqual(account.person_profile.vorname, account.first_name)

    def test_account_creation_rejects_long_inline_or_selected_names(self):
        for field in ("vorname", "nachname"):
            with self.subTest(field=field, selected=False):
                form = self.new_account_form(**{field: "A" * 151})
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
            with self.subTest(field=field, selected=True):
                person = Person.objects.create(
                    **{
                        "vorname": "Konto",
                        "nachname": "Test",
                        "email": f"{field}@test.de",
                        field: "A" * 151,
                    }
                )
                form = self.new_account_form(person=person)
                self.assertFalse(form.is_valid())
                self.assertIn("person", form.errors)

    def test_account_save_rechecks_names_changed_after_validation(self):
        person = Person.objects.create(vorname="Konto", nachname="Test", email="account@test.de")
        form = self.new_account_form(person=person)
        self.assertTrue(form.is_valid(), form.errors)
        person.nachname = "A" * 151
        person.save(update_fields=["nachname"])
        with self.assertRaisesMessage(ValidationError, "Nachname"):
            form.save()
        self.assertFalse(get_user_model().objects.exists())
        person.refresh_from_db()
        self.assertIsNone(person.user_id)

    def test_revoked_manager_cannot_restore_rights_from_an_inflight_request(self):
        first = self.create_account(ROLE_USER_MANAGEMENT, email="first@example.test")
        second = self.create_account(ROLE_USER_MANAGEMENT, email="second@example.test")
        self.client.force_login(first)
        original_save = UserAccountForm.save
        revocation_observed = []

        def revoke_actor_before_save(form):
            if form.actor.pk == first.pk:
                self.edit_account(
                    first, actor=second, roles=[Group.objects.get(name=ROLE_EMPLOYEE).pk]
                )
                revoked = get_user_model().objects.get(pk=first.pk)
                revocation_observed.append(not revoked.has_perm(USER_MANAGEMENT_PERMISSION))
            return original_save(form)

        with patch.object(UserAccountForm, "save", revoke_actor_before_save):
            response = self.client.post(
                reverse("verwaltung:user_account_edit", args=[first.pk]),
                {
                    "person": str(first.person_profile.pk),
                    "roles": [Group.objects.get(name=ROLE_USER_MANAGEMENT).pk],
                    "is_active": True,
                    "password1": "",
                    "password2": "",
                },
            )
        self.assertEqual(revocation_observed, [True])
        self.assertEqual(response.status_code, 403)
        first.refresh_from_db()
        self.assertFalse(first.has_perm(USER_MANAGEMENT_PERMISSION))

    def test_inactive_manager_cannot_finish_editing_another_account(self):
        actor = self.create_account(ROLE_USER_MANAGEMENT, email="actor@example.test")
        other = self.create_account(ROLE_USER_MANAGEMENT, email="other@example.test")
        target = self.create_account()
        form = self.account_form(
            target, actor=actor, password1=NEW_PASSWORD, password2=NEW_PASSWORD
        )
        self.edit_account(actor, actor=other, is_active=False)
        with self.assertRaises(PermissionDenied):
            form.save()
        target.refresh_from_db()
        self.assertTrue(target.check_password(PASSWORD))

    def test_revoked_manager_cannot_finish_creating_an_account(self):
        actor = self.create_account(ROLE_USER_MANAGEMENT, email="actor@example.test")
        other = self.create_account(ROLE_USER_MANAGEMENT, email="other@example.test")
        form = self.new_account_form(actor=actor)
        self.assertTrue(form.is_valid(), form.errors)
        self.edit_account(actor, actor=other, roles=[Group.objects.get(name=ROLE_EMPLOYEE).pk])
        with self.assertRaises(PermissionDenied):
            form.save()
        self.assertFalse(get_user_model().objects.filter(email="account@example.test").exists())
        self.assertFalse(Person.objects.filter(email="account@example.test").exists())

    def test_password_reset_invalidates_a_running_administrative_request(self):
        actor = self.create_account(ROLE_USER_MANAGEMENT, email="actor@example.test")
        other = self.create_account(ROLE_USER_MANAGEMENT, email="other@example.test")
        target = self.create_account()
        form = self.account_form(target, actor=actor, is_active=False)
        self.edit_account(actor, actor=other, password1=NEW_PASSWORD, password2=NEW_PASSWORD)
        with self.assertRaises(PermissionDenied):
            form.save()
        target.refresh_from_db()
        self.assertTrue(target.is_active)

    def test_registration_mail_failure_allows_confirmation_page_and_resend_after_the_delay(self):
        for index, error in enumerate((SMTPException("mail failed"), TimeoutError("timed out"))):
            with self.subTest(error=type(error).__name__):
                email = f"failure-{index}@example.test"
                client = Client()
                with (
                    self.assertLogs("core.views", level="WARNING"),
                    patch("core.views.send_registration_code", side_effect=error),
                ):
                    response = client.post(reverse("register"), self.registration_data(email=email))
                self.assertRedirects(
                    response, reverse("register_verify"), fetch_redirect_response=False
                )
                page = client.get(reverse("register_verify"))
                self.assertContains(page, "konnte nicht gesendet werden")
                self.assertEqual(page.context["form"].initial["email"], email)
                account = get_user_model().objects.get(email=email)
                self.assertFalse(account.is_active)
                verification = RegistrationVerification.objects.get(user=account)
                self.assertFalse(verification.can_resend())
                mail_count = len(mail.outbox)
                client.post(reverse("resend_registration_code"), {"email": email})
                self.assertEqual(len(mail.outbox), mail_count)
                verification.last_sent_at = timezone.now() - verification.RESEND_DELAY
                verification.save(update_fields=["last_sent_at"])
                client.post(reverse("resend_registration_code"), {"email": email})
                client.post(
                    reverse("register_verify"), {"email": email, "code": self.mailed_code()}
                )
                account.refresh_from_db()
                self.assertTrue(account.is_active)

    def test_zero_mail_deliveries_are_handled_as_a_send_failure(self):
        with (
            self.assertLogs("core.views", level="WARNING"),
            patch("core.views.send_mail", return_value=0),
        ):
            response = self.client.post(reverse("register"), self.registration_data())
        self.assertRedirects(response, reverse("register_verify"))
        self.assertFalse(RegistrationVerification.objects.get().can_resend())

    def test_failed_registration_resend_is_neutral_and_keeps_the_resend_delay(self):
        account = self.register_account()
        old_code = self.mailed_code()
        self.client.get(reverse("register_verify"))
        verification = RegistrationVerification.objects.get(user=account)
        verification.last_sent_at = timezone.now() - verification.RESEND_DELAY
        verification.save(update_fields=["last_sent_at"])
        with (
            self.assertLogs("core.views", level="WARNING"),
            patch("core.views.send_registration_code", side_effect=SMTPException("mail failed")),
        ):
            response = self.client.post(
                reverse("resend_registration_code"), {"email": account.email}
            )
        unknown = Client().post(reverse("resend_registration_code"), {"email": "unknown@test.de"})
        self.assertRedirects(response, reverse("register_verify"))
        self.assertEqual(
            [str(message) for message in get_messages(response.wsgi_request)],
            [str(message) for message in get_messages(unknown.wsgi_request)],
        )
        verification.refresh_from_db()
        self.assertFalse(verification.matches(old_code))
        self.assertFalse(verification.can_resend())
        self.client.post(reverse("resend_registration_code"), {"email": account.email})
        self.assertEqual(len(mail.outbox), 1)
        verification.last_sent_at = timezone.now() - verification.RESEND_DELAY
        verification.save(update_fields=["last_sent_at"])
        self.client.post(reverse("resend_registration_code"), {"email": account.email})
        self.assertEqual(len(mail.outbox), 2)
        self.client.post(
            reverse("register_verify"), {"email": account.email, "code": self.mailed_code()}
        )
        account.refresh_from_db()
        self.assertTrue(account.is_active)

    def test_failed_mfa_mail_clears_only_the_pending_login_and_allows_retry(self):
        account = self.create_account(ROLE_EMPLOYEE)
        with (
            self.assertLogs("core.views", level="WARNING"),
            patch("core.views.send_employee_mfa_code", side_effect=TimeoutError("timed out")),
        ):
            response = self.client.post(
                reverse("login"), {"username": account.username, "password": PASSWORD}
            )
        self.assertContains(response, "konnte nicht gesendet werden")
        self.assertFalse(EmployeeLoginVerification.objects.filter(user=account).exists())
        self.assertFalse(AccountLoginThrottle.objects.filter(user=account).exists())
        for key in (
            EMPLOYEE_MFA_USER_SESSION_KEY,
            EMPLOYEE_MFA_CHALLENGE_SESSION_KEY,
            EMPLOYEE_MFA_REDIRECT_SESSION_KEY,
            "_auth_user_id",
        ):
            self.assertNotIn(key, self.client.session)
        response = self.client.post(
            reverse("login"), {"username": account.username, "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("employee_mfa_verify"))
        self.client.post(reverse("employee_mfa_verify"), {"code": self.mailed_code()})
        self.assertEqual(self.client.session["_auth_user_id"], str(account.pk))

    def test_late_registration_mail_failure_preserves_a_newer_code_and_its_delay(self):
        replacement_hashes = []

        def replace_code_before_failure(email, code):
            verification = RegistrationVerification.objects.get(user__email=email)
            verification.issue_code()
            verification.save()
            replacement_hashes.append(verification.code_hash)
            raise SMTPException("old send failed")

        with (
            self.assertLogs("core.views", level="WARNING"),
            patch("core.views.send_registration_code", replace_code_before_failure),
        ):
            self.client.post(reverse("register"), self.registration_data())
        verification = RegistrationVerification.objects.get()
        self.assertEqual(verification.code_hash, replacement_hashes[0])
        self.assertFalse(verification.can_resend())

    def test_late_registration_mail_failure_does_not_restore_a_revoked_registration(self):
        def revoke_before_failure(email, code):
            account = get_user_model().objects.get(email=email)
            self.edit_account(account, revoke_registration=True)
            raise SMTPException("old send failed")

        with (
            self.assertLogs("core.views", level="WARNING"),
            patch("core.views.send_registration_code", revoke_before_failure),
        ):
            self.client.post(reverse("register"), self.registration_data())
        self.assertFalse(RegistrationVerification.objects.exists())
        self.assertFalse(get_user_model().objects.get().is_active)

    def test_late_mfa_mail_failure_does_not_remove_a_newer_challenge(self):
        account = self.create_account(ROLE_EMPLOYEE)
        replacement_hashes = []

        def replace_code_before_failure(email, code):
            verification = EmployeeLoginVerification.objects.get(user=account)
            verification.issue_code()
            verification.save()
            replacement_hashes.append(verification.code_hash)
            raise SMTPException("old send failed")

        with (
            self.assertLogs("core.views", level="WARNING"),
            patch("core.views.send_employee_mfa_code", replace_code_before_failure),
        ):
            self.client.post(reverse("login"), {"username": account.username, "password": PASSWORD})
        self.assertEqual(
            EmployeeLoginVerification.objects.get(user=account).code_hash, replacement_hashes[0]
        )
        self.assertNotIn(EMPLOYEE_MFA_USER_SESSION_KEY, self.client.session)

    def test_mfa_account_switch_preserves_the_destination_for_a_direct_account_manager(self):
        previous = self.create_account(email="previous@example.test")
        account = self.create_account(ROLE_EMPLOYEE, email="manager@example.test")
        account.groups.clear()
        account.user_permissions.add(Permission.objects.get(codename="manage_user_accounts"))
        self.client.force_login(previous)
        destination = reverse("verwaltung:user_account_list")
        self.client.post(
            reverse("login"),
            {"username": account.username, "password": PASSWORD, "next": destination},
        )
        response = self.client.post(reverse("employee_mfa_verify"), {"code": self.mailed_code()})
        self.assertRedirects(response, destination)
        self.assertEqual(self.client.session["_auth_user_id"], str(account.pk))

    def test_unsafe_mfa_destination_uses_the_current_accounts_default(self):
        account = self.create_account(ROLE_EMPLOYEE)
        account.groups.clear()
        account.user_permissions.add(Permission.objects.get(codename="manage_user_accounts"))
        self.client.post(reverse("login"), {"username": account.username, "password": PASSWORD})
        session = self.client.session
        session[EMPLOYEE_MFA_REDIRECT_SESSION_KEY] = "https://external.example.test/"
        session.save()
        response = self.client.post(reverse("employee_mfa_verify"), {"code": self.mailed_code()})
        self.assertRedirects(response, reverse("verwaltung:user_account_list"))
