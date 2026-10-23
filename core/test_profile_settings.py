import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection, transaction
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from wohnungsverwaltung.models import (
    AccountLoginThrottle,
    EmployeeLoginVerification,
    Person,
    RegistrationVerification,
)

PASSWORD = "FjordProfil!4826"
NEW_PASSWORD = "BirkenKomet!5927"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ProfileSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="settings@example.test", email="settings@example.test", password=PASSWORD
        )
        cls.person = Person.objects.create(
            user=cls.user, vorname="Mia", nachname="Muster", email=cls.user.email
        )
        cls.other = get_user_model().objects.create_user(
            username="other@example.test", email="other@example.test", password=PASSWORD
        )
        cls.other_person = Person.objects.create(
            user=cls.other, vorname="Andere", nachname="Person", email=cls.other.email
        )

    def setUp(self):
        self.client.force_login(self.user)

    def profile_data(self, **changes):
        return {
            "vorname": "Mia",
            "nachname": "Muster",
            "telefonnummer": "",
            "salutation": "ms",
            "geburtsdatum": "1995-04-12",
            **changes,
        }

    def password_data(self, **changes):
        return {
            "old_password": PASSWORD,
            "new_password1": NEW_PASSWORD,
            "new_password2": NEW_PASSWORD,
            **changes,
        }

    def pending(self):
        return apps.get_model("immobilien", "PendingEmailChange").objects.get(user=self.user)

    def start_email_change(self, email="new@example.test"):
        return self.client.post(
            reverse("profile:email"), {"current_password": PASSWORD, "new_email": email}
        )

    def confirmation_data(self, code=None):
        pending = self.pending()
        return {
            "code": code or re.search(r"\b[0-9]{6}\b", mail.outbox[-1].body).group(),
            "challenge": str(pending.challenge),
        }

    def test_extended_profile_round_trips_optional_personal_data(self):
        response = self.client.post(reverse("profile:edit"), self.profile_data())
        self.assertRedirects(response, reverse("profile:detail"))
        self.person.refresh_from_db()
        self.assertEqual(self.person.salutation, "ms")
        self.assertEqual(self.person.geburtsdatum, date(1995, 4, 12))
        response = self.client.get(reverse("profile:detail"))
        for value in (
            "Frau",
            "12. April 1995",
        ):
            self.assertContains(response, value)
        self.assertContains(self.client.get(reverse("profile:edit")), 'type="date"')

    def test_profile_does_not_display_or_collect_address(self):
        self.person.street_address = "Beispielweg 12"
        self.person.save(update_fields=["street_address"])
        for url in ("profile:detail", "profile:edit"):
            with self.subTest(url=url):
                response = self.client.get(reverse(url))
                self.assertNotContains(response, "Anschrift")
                self.assertNotContains(response, "Beispielweg 12")
                for field in ("street_address", "postal_code", "city", "country"):
                    self.assertNotContains(response, f'name="{field}"')

    def test_profile_ignores_posted_address_and_preserves_existing_data(self):
        address = {
            "street_address": "Beispielweg 12",
            "postal_code": "SW1A 1AA",
            "city": "London",
            "country": "Vereinigtes Königreich",
        }
        Person.objects.filter(pk=self.person.pk).update(**address)
        for changes in ({}, {"street_address": "Andere Straße 3", "city": ""}):
            with self.subTest(changes=changes):
                response = self.client.post(
                    reverse("profile:edit"), self.profile_data(vorname="Maja", **changes)
                )
                self.assertRedirects(response, reverse("profile:detail"))
                self.person.refresh_from_db()
                self.assertEqual(self.person.vorname, "Maja")
                for field, value in address.items():
                    self.assertEqual(getattr(self.person, field), value)

    def test_profile_rejects_future_birthdate_and_unknown_salutation(self):
        for changes, field in (
            ({"geburtsdatum": str(timezone.localdate() + timedelta(days=1))}, "geburtsdatum"),
            ({"salutation": "admin"}, "salutation"),
        ):
            with self.subTest(field=field):
                response = self.client.post(reverse("profile:edit"), self.profile_data(**changes))
                self.assertIn(field, response.context["form"].errors)
        self.person.refresh_from_db()
        self.assertEqual(self.person.vorname, "Mia")
        self.assertIsNone(self.person.geburtsdatum)

    def test_optional_data_can_be_cleared(self):
        self.client.post(reverse("profile:edit"), self.profile_data())
        response = self.client.post(
            reverse("profile:edit"),
            self.profile_data(
                salutation="",
                geburtsdatum="",
            ),
        )
        self.assertRedirects(response, reverse("profile:detail"))
        self.person.refresh_from_db()
        self.assertIsNone(self.person.geburtsdatum)

    def test_password_change_rejects_wrong_current_weak_and_mismatched_passwords(self):
        for changes, field in (
            ({"old_password": "wrong"}, "old_password"),
            ({"new_password1": "123", "new_password2": "123"}, "new_password2"),
            ({"new_password2": "Different!4826"}, "new_password2"),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    reverse("profile:password"), self.password_data(**changes)
                )
                self.assertIn(field, response.context["form"].errors)
                self.assertNotContains(response, f'value="{PASSWORD}"')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_password_change_revokes_all_sessions_and_pending_codes_without_changing_roles(self):
        other_session = Client()
        other_session.force_login(self.user)
        self.user.groups.add(Group.objects.get(name="Mitarbeiter"))
        verification = EmployeeLoginVerification(user=self.user)
        verification.issue_code()
        verification.save()
        registration = RegistrationVerification(user=self.user)
        registration.issue_code()
        registration.save()
        response = self.client.post(reverse("profile:password"), self.password_data())
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertFalse(self.user.check_password(PASSWORD))
        self.assertTrue(self.user.groups.filter(name="Mitarbeiter").exists())
        self.assertFalse(EmployeeLoginVerification.objects.filter(user=self.user).exists())
        self.assertFalse(RegistrationVerification.objects.filter(user=self.user).exists())
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(other_session.get(reverse("profile:detail")).status_code, 302)

    def test_password_confirmation_attempts_are_rate_limited(self):
        for _ in range(3):
            self.client.post(reverse("profile:password"), self.password_data(old_password="wrong"))
        self.assertEqual(AccountLoginThrottle.objects.get(user=self.user).failed_attempts, 3)
        response = self.client.post(reverse("profile:password"), self.password_data())
        self.assertContains(response, "Bitte versuchen Sie es später erneut.")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_email_change_keeps_old_login_until_new_address_is_confirmed_then_revokes_sessions(
        self,
    ):
        response = self.start_email_change()
        self.assertRedirects(response, reverse("profile:email_confirm"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "settings@example.test")
        self.assertEqual(mail.outbox[-1].to, ["new@example.test"])
        self.assertNotIn(self.confirmation_data()["code"], self.pending().code_hash)
        second = Client()
        second.force_login(self.user)
        response = self.client.post(reverse("profile:email_confirm"), self.confirmation_data())
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.person.refresh_from_db()
        self.assertEqual(
            (self.user.username, self.user.email, self.person.email), ("new@example.test",) * 3
        )
        self.assertEqual(second.get(reverse("profile:detail")).status_code, 302)
        self.assertFalse(
            apps.get_model("immobilien", "PendingEmailChange")
            .objects.filter(user=self.user)
            .exists()
        )

    def test_email_change_requires_password_and_rejects_duplicates_case_insensitively(self):
        for changes, field in (
            ({"current_password": "wrong"}, "current_password"),
            ({"new_email": "OTHER@example.test"}, "new_email"),
            ({"new_email": "settings@example.test"}, "new_email"),
            ({"new_email": "x" * 145 + "@example.test"}, "new_email"),
        ):
            with self.subTest(field=field):
                data = {"new_email": "new@example.test", "current_password": PASSWORD, **changes}
                response = self.client.post(reverse("profile:email"), data)
                self.assertIn(field, response.context["form"].errors)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "settings@example.test")

    def test_expired_wrong_and_old_challenge_codes_do_not_change_email(self):
        self.start_email_change()
        valid = self.confirmation_data()
        for _ in range(5):
            response = self.client.post(
                reverse("profile:email_confirm"),
                self.confirmation_data(code="999999" if valid["code"] != "999999" else "888888"),
            )
            self.assertContains(response, "Code")
        self.assertEqual(self.pending().attempts, 5)
        self.client.post(reverse("profile:email_confirm"), valid)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "settings@example.test")

    def test_email_expiry_resend_limit_and_cancellation(self):
        self.start_email_change()
        valid = self.confirmation_data()
        response = self.start_email_change("replacement@example.test")
        self.assertContains(response, "Bitte warten Sie")
        pending = self.pending()
        pending.expires_at = timezone.now() - timedelta(seconds=1)
        pending.save()
        self.client.post(reverse("profile:email_confirm"), valid)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "settings@example.test")
        self.assertEqual(self.client.post(reverse("profile:email_cancel")).status_code, 302)
        self.assertFalse(
            apps.get_model("immobilien", "PendingEmailChange")
            .objects.filter(user=self.user)
            .exists()
        )

    def test_mail_failure_preserves_login_and_explains_retry(self):
        with patch("core.views.send_mail", side_effect=OSError):
            response = self.start_email_change()
        self.assertContains(response, "konnte nicht gesendet")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "settings@example.test")

    def test_email_collision_after_code_issue_is_a_form_error(self):
        self.start_email_change()
        valid = self.confirmation_data()
        Person.objects.create(vorname="Neu", nachname="Besetzt", email="NEW@example.test")
        response = self.client.post(reverse("profile:email_confirm"), valid)
        self.assertContains(response, "bereits verwendet")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "settings@example.test")

    def test_anonymous_and_csrf_protection_for_account_changes(self):
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        for route in (
            "profile:password",
            "profile:email",
            "profile:email_confirm",
            "profile:email_cancel",
        ):
            self.assertEqual(csrf.post(reverse(route), {}).status_code, 403)
            anonymous = Client()
            self.assertEqual(anonymous.post(reverse(route), {}).status_code, 302)

    def test_no_person_link_is_explained_for_account_changes(self):
        Person.objects.filter(pk=self.person.pk).update(user=None)
        for route in ("profile:password", "profile:email"):
            response = self.client.post(reverse(route), self.password_data())
            self.assertContains(response, "Personendatensatz")
            self.assertNotContains(response, 'type="password"')

    def test_another_account_cannot_confirm_or_cancel_own_email_change(self):
        self.start_email_change()
        valid = self.confirmation_data()
        self.client.force_login(self.other)
        self.client.post(reverse("profile:email_confirm"), valid)
        self.client.post(reverse("profile:email_cancel"))
        self.assertTrue(self.pending())
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "settings@example.test")

    def test_administrative_password_change_invalidates_pending_email_code(self):
        self.start_email_change()
        valid = self.confirmation_data()
        self.user.set_password(NEW_PASSWORD)
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.post(reverse("profile:email_confirm"), valid)
        self.assertContains(response, "nicht mehr gültig")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "settings@example.test")

    def test_email_change_rejects_address_exceeding_storage_after_normalization(self):
        address = "a" * 60 + "@" + "b" * 50 + ".İ." + "c" * 28 + ".example"
        self.assertEqual(len(address), 150)
        self.assertEqual(len(address.lower()), 151)
        response = self.start_email_change(address)
        self.assertEqual(response.status_code, 200)
        self.assertIn("new_email", response.context["form"].errors)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "settings@example.test")

    def test_resend_replaces_code_and_old_challenge_cannot_confirm_new_address(self):
        self.start_email_change()
        old = self.confirmation_data()
        pending = self.pending()
        pending.last_sent_at = timezone.now() - timedelta(minutes=2)
        pending.save(update_fields=["last_sent_at"])
        self.assertRedirects(
            self.start_email_change("replacement@example.test"), reverse("profile:email_confirm")
        )
        latest = self.confirmation_data()
        self.assertNotEqual(old["challenge"], latest["challenge"])
        self.assertNotEqual(old["code"], latest["code"])
        self.client.post(
            reverse("profile:email_confirm"),
            {"challenge": old["challenge"], "code": latest["code"]},
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "settings@example.test")
        self.client.post(reverse("profile:email_confirm"), latest)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "replacement@example.test")

    def test_security_pages_are_private_and_get_cancel_does_not_change_state(self):
        self.start_email_change()
        for route in ("profile:password", "profile:email", "profile:email_confirm"):
            self.assertIn("no-store", self.client.get(reverse(route)).headers["Cache-Control"])
        self.assertEqual(self.client.get(reverse("profile:email_cancel")).status_code, 405)
        self.assertTrue(self.pending())

    def test_email_change_cannot_be_smuggled_through_personal_data_form(self):
        self.client.post(
            reverse("profile:edit"),
            self.profile_data(
                email="smuggled@example.test", is_employee="on", user_id=self.other.pk
            ),
        )
        self.user.refresh_from_db()
        self.person.refresh_from_db()
        self.assertEqual(self.user.email, "settings@example.test")
        self.assertEqual(self.person.email, "settings@example.test")
        self.assertFalse(self.person.is_employee)

    @override_settings(DEMO_MODE=True)
    def test_email_change_works_with_existing_explicit_demo_code(self):
        self.start_email_change()
        self.assertEqual(self.confirmation_data()["code"], "000000")
        self.client.post(reverse("profile:email_confirm"), self.confirmation_data(code="000000"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.test")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EmailChangeLockTests(TransactionTestCase):
    def test_smtp_runs_without_account_lock_and_administrative_change_invalidates_code(self):
        user = get_user_model().objects.create_user(
            username="locks@example.test", email="locks@example.test", password=PASSWORD
        )
        Person.objects.create(user=user, vorname="Mia", nachname="Muster", email=user.email)
        self.client.force_login(user)
        issued = []

        def edit_account():
            close_old_connections()
            try:
                with transaction.atomic():
                    current = get_user_model().objects.select_for_update().get(pk=user.pk)
                    current.set_password(NEW_PASSWORD)
                    current.save(update_fields=["password"])
            finally:
                close_old_connections()

        def deliver(subject, body, sender, recipients):
            self.assertFalse(connection.in_atomic_block)
            issued.append(re.search(r"\b[0-9]{6}\b", body).group())
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(edit_account).result(timeout=10)
            return 1

        with patch("core.views.send_mail", side_effect=deliver):
            response = self.client.post(
                reverse("profile:email"),
                {"current_password": PASSWORD, "new_email": "fresh@example.test"},
            )
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.client.force_login(user)
        pending = apps.get_model("immobilien", "PendingEmailChange").objects.get(user=user)
        response = self.client.post(
            reverse("profile:email_confirm"), {"challenge": pending.challenge, "code": issued[0]}
        )
        self.assertContains(response, "nicht mehr gültig")
        user.refresh_from_db()
        self.assertEqual(user.email, "locks@example.test")

    def test_parallel_confirmations_for_same_address_have_only_one_winner(self):
        clients = []
        entries = []
        pending_model = apps.get_model("immobilien", "PendingEmailChange")
        for index in range(2):
            email = f"parallel{index}@example.test"
            user = get_user_model().objects.create_user(
                username=email, email=email, password=PASSWORD
            )
            Person.objects.create(user=user, vorname="Test", nachname=str(index), email=email)
            client = Client()
            client.force_login(user)
            self.assertEqual(
                client.post(
                    reverse("profile:email"),
                    {"new_email": "same-target@example.test", "current_password": PASSWORD},
                ).status_code,
                302,
            )
            pending = pending_model.objects.get(user=user)
            entries.append(
                (
                    user.pk,
                    {
                        "challenge": str(pending.challenge),
                        "code": re.search(r"\b[0-9]{6}\b", mail.outbox[-1].body).group(),
                    },
                )
            )
            clients.append(client)

        def confirm(index):
            close_old_connections()
            try:
                return (
                    clients[index]
                    .post(reverse("profile:email_confirm"), entries[index][1])
                    .status_code
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(confirm, range(2)))
        self.assertEqual(sorted(outcomes), [200, 302])
        self.assertEqual(
            get_user_model().objects.filter(email="same-target@example.test").count(), 1
        )
        self.assertEqual(Person.objects.filter(email="same-target@example.test").count(), 1)
        for user_pk, _ in entries:
            user = get_user_model().objects.get(pk=user_pk)
            self.assertEqual(user.email, user.person_profile.email)


class ProfileReadRevocationTests(TestCase):
    def test_inflight_profile_read_rejects_administratively_revoked_session(self):
        from core.views import personal_profile

        user = get_user_model().objects.create_user(username="session-revoked@example.test")
        Person.objects.create(user=user, vorname="Test", nachname="Konto", email=user.username)
        self.client.force_login(user)
        request = RequestFactory().get(reverse("profile:detail"))
        request.user = user
        request.session = self.client.session
        Session.objects.filter(session_key=request.session.session_key).delete()
        with self.assertRaises(PermissionDenied):
            personal_profile(request)

    def test_inflight_profile_read_does_not_disclose_reassigned_person(self):
        from core.views import personal_profile

        user = get_user_model().objects.create_user(username="revoked@example.test")
        request = RequestFactory().get(reverse("profile:detail"))
        request.user = get_user_model().objects.get(pk=user.pk)
        get_user_model().objects.filter(pk=user.pk).update(password="administratively-changed")
        Person.objects.create(
            user=user, vorname="Neue", nachname="Person", email="new-owner@example.test"
        )
        with self.assertRaises(PermissionDenied):
            personal_profile(request)
