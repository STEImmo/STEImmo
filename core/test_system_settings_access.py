from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from core.test_auth_revocation import PASSWORD, AccountChangesMixin
from wohnungsverwaltung.access import (
    ROLE_APPLICANT,
    ROLE_EMPLOYEE,
    ROLE_TENANT,
    ROLE_USER_MANAGEMENT,
)


class SystemSettingsAccessTests(AccountChangesMixin, TestCase):
    @property
    def settings_url(self):
        return reverse("verwaltung:system_settings")

    @property
    def action_url(self):
        return reverse("verwaltung:system_settings_access")

    @property
    def permission(self):
        return Permission.objects.get(
            content_type__app_label="immobilien",
            content_type__model="person",
            codename="manage_system_settings",
        )

    def bootstrap(self, account):
        call_command("grant_system_settings_access", account.username, stdout=StringIO())

    def login_with_code(self, account, client=None):
        client = self.client if client is None else client
        response = client.post(
            reverse("login"), {"username": account.username, "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("employee_mfa_verify"))
        self.assertNotIn("_auth_user_id", client.session)
        response = client.post(reverse("employee_mfa_verify"), {"code": self.mailed_code()})
        return response

    def test_direct_access_is_denied_to_all_ordinary_roles(self):
        self.assertEqual(self.client.get(self.settings_url).status_code, 302)
        self.assertEqual(self.client.post(self.action_url).status_code, 302)
        for index, role in enumerate(
            (ROLE_APPLICANT, ROLE_TENANT, ROLE_EMPLOYEE, ROLE_USER_MANAGEMENT)
        ):
            with self.subTest(role=role):
                account = self.create_account(role, f"ordinary-{index}@example.test")
                self.client.force_login(account)
                self.assertEqual(self.client.get(self.settings_url).status_code, 403)
                self.assertEqual(self.client.post(self.action_url).status_code, 403)
                self.assertNotContains(
                    self.client.get(reverse("profile:detail")), self.settings_url
                )
        account.is_superuser = True
        account.save(update_fields=["is_superuser"])
        self.client.force_login(account)
        self.assertEqual(self.client.get(self.settings_url).status_code, 403)
        account.is_superuser = False
        account.save(update_fields=["is_superuser"])
        custom_group = Group.objects.create(name="Weitere Rolle")
        custom_group.permissions.add(self.permission)
        account.groups.add(custom_group)
        self.client.force_login(account)
        self.assertEqual(self.client.get(self.settings_url).status_code, 403)

    def test_settings_only_account_uses_existing_mail_code_login(self):
        account = self.create_account(email="settings@example.test")
        self.bootstrap(account)
        self.client.force_login(account)
        self.assertRedirects(
            self.client.get(self.settings_url),
            f"{reverse('login')}?next={self.settings_url}",
            fetch_redirect_response=False,
        )
        self.client.logout()
        self.assertRedirects(self.login_with_code(account), self.settings_url)
        self.assertContains(self.client.get(self.settings_url), "Systemeinstellungen")
        self.assertContains(self.client.get(reverse("profile:detail")), self.settings_url)
        self.assertEqual(self.client.get(reverse("verwaltung:dashboard")).status_code, 403)

    def test_grant_requires_post_with_csrf_and_retires_preexisting_sessions(self):
        admin = self.create_account(email="admin@example.test")
        target = self.create_account(email="target@example.test")
        self.bootstrap(admin)
        old_session = Client()
        old_session.force_login(target)
        client = Client(enforce_csrf_checks=True)
        self.login_with_code(admin)
        client.cookies.update(self.client.cookies)
        self.assertEqual(client.get(self.action_url).status_code, 405)
        self.assertEqual(client.get(self.settings_url).status_code, 200)
        data = {"action": "grant", "username": target.username}
        self.assertEqual(client.post(self.action_url, data).status_code, 403)
        token = client.cookies["csrftoken"].value
        self.assertRedirects(
            client.post(self.action_url, data, HTTP_X_CSRFTOKEN=token), self.settings_url
        )
        self.assertIn(self.permission, target.user_permissions.all())
        self.assertEqual(old_session.get(reverse("profile:detail")).status_code, 302)
        self.assertRedirects(self.login_with_code(target, old_session), self.settings_url)

    def test_revocation_keeps_last_usable_admin_and_logs_out_a_departing_admin(self):
        first = self.create_account(email="first@example.test")
        backup = self.create_account(email="backup@example.test")
        self.bootstrap(first)
        self.bootstrap(backup)
        backup.set_unusable_password()
        backup.save(update_fields=["password"])
        self.login_with_code(first)
        data = {"action": "revoke", "username": first.username}
        denied = self.client.post(self.action_url, data)
        self.assertContains(denied, "mindestens ein funktionsfähiges", status_code=400)
        self.assertIn(self.permission, first.user_permissions.all())
        backup.set_password(PASSWORD)
        backup.save(update_fields=["password"])
        self.assertRedirects(self.client.post(self.action_url, data), reverse("login"))
        self.assertNotIn(self.permission, first.user_permissions.all())
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertRedirects(self.login_with_code(backup), self.settings_url)

    def test_user_manager_cannot_grant_access_or_change_a_protected_account(self):
        manager = self.create_account(ROLE_USER_MANAGEMENT, "manager@example.test")
        target = self.create_account(email="target@example.test")
        stale_form = self.account_form(target, actor=manager, is_active=False)
        self.bootstrap(target)
        with self.assertRaises(PermissionDenied):
            stale_form.save()
        self.client.force_login(manager)
        url = reverse("verwaltung:user_account_edit", args=[target.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"is_active": False}).status_code, 403)
        target.refresh_from_db()
        self.assertTrue(target.is_active)
        self.assertIn(self.permission, target.user_permissions.all())
        edit_own = reverse("verwaltung:user_account_edit", args=[manager.pk])
        self.assertNotContains(self.client.get(edit_own), self.permission.name)
        self.client.post(
            edit_own,
            {
                "person": manager.person_profile.pk,
                "roles": list(manager.groups.values_list("pk", flat=True)),
                "direct_permissions": [self.permission.pk],
                "is_active": True,
            },
        )
        self.assertNotIn(self.permission, manager.user_permissions.all())

    def test_registration_confirmation_cannot_create_a_settings_session(self):
        account = self.register_account()
        code = self.mailed_code()
        account.user_permissions.add(self.permission)
        response = self.client.post(
            reverse("register_verify"), {"email": account.email, "code": code}
        )
        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_bootstrap_rejects_inactive_or_unusable_accounts(self):
        absent = get_user_model().objects.create_user("inactive", email="test@example.test")
        with self.assertRaises(CommandError):
            self.bootstrap(absent)
        absent.set_password(PASSWORD)
        absent.is_active = False
        absent.save(update_fields=["password", "is_active"])
        with self.assertRaises(CommandError):
            self.bootstrap(absent)
        self.assertNotIn(self.permission, absent.user_permissions.all())

    def test_revocation_invalidates_a_pending_mail_code(self):
        first = self.create_account(email="first@example.test")
        second = self.create_account(email="second@example.test")
        self.bootstrap(first)
        self.bootstrap(second)
        self.login_with_code(first)
        pending = Client()
        self.assertRedirects(
            pending.post(reverse("login"), {"username": second.username, "password": PASSWORD}),
            reverse("employee_mfa_verify"),
        )
        code = self.mailed_code()
        self.assertRedirects(
            self.client.post(self.action_url, {"action": "revoke", "username": second.username}),
            self.settings_url,
        )
        self.assertRedirects(
            pending.post(reverse("employee_mfa_verify"), {"code": code}), reverse("login")
        )
        self.assertNotIn("_auth_user_id", pending.session)


class SystemSettingsConcurrentRevocationTests(AccountChangesMixin, TransactionTestCase):
    def test_simultaneous_self_revocations_leave_one_admin(self):
        admins = [self.create_account(email=f"admin-{index}@example.test") for index in range(2)]
        clients = []
        for admin in admins:
            call_command("grant_system_settings_access", admin.username, stdout=StringIO())
            client = Client()
            self.assertRedirects(
                client.post(reverse("login"), {"username": admin.username, "password": PASSWORD}),
                reverse("employee_mfa_verify"),
            )
            self.assertRedirects(
                client.post(reverse("employee_mfa_verify"), {"code": self.mailed_code()}),
                reverse("verwaltung:system_settings"),
            )
            clients.append(client)

        barrier = Barrier(len(admins), timeout=10)
        url = reverse("verwaltung:system_settings_access")

        def revoke(client, admin):
            close_old_connections()
            try:
                barrier.wait()
                return client.post(
                    url, {"action": "revoke", "username": admin.username}
                ).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(admins)) as pool:
            requests = [
                pool.submit(revoke, client, admin)
                for client, admin in zip(clients, admins, strict=True)
            ]
            self.assertCountEqual([request.result(timeout=15) for request in requests], [302, 400])
        self.assertEqual(
            get_user_model()
            .objects.filter(user_permissions__codename="manage_system_settings")
            .count(),
            1,
        )
