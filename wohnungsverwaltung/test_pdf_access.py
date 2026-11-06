"""Ergänzende Rollen-/Objektmatrix für PDF-Downloads und Exporterstellung (#140)."""

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.storage import default_storage
from django.test import Client, TestCase
from django.urls import reverse

from . import test_handover_export as fixtures
from .access import ROLE_APPLICANT, ROLE_EMPLOYEE, ROLE_TENANT
from .models import (
    AbnahmeStatus,
    Person,
    Protokoll,
    ProtokollSchluessel,
    ProtokollStatus,
    ProtokollTyp,
    ProtokollUnterschrift,
    Raum,
    UebergabeStatus,
    Wohnung,
)


class PdfAccessTests(TestCase):
    url = fixtures.HandoverExportTests.url

    def setUp(self):
        fixtures.HandoverExportTests.setUp(self)
        self.other_tenant = self.create_user("other-tenant", ROLE_TENANT)
        self.other_person = Person.objects.create(
            user=self.other_tenant,
            vorname="Andere",
            nachname="Testperson",
            email="other-tenant@example.test",
        )
        self.other_protocol = self.create_protocol(self.other_person)
        self.applicants = [
            self.create_user("applicant-a", ROLE_APPLICANT),
            self.create_user("applicant-b", ROLE_APPLICANT),
        ]
        self.staff = self.create_user("staff-only", is_staff=True)

    @staticmethod
    def create_user(name, role=None, **kwargs):
        user = get_user_model().objects.create_user(username=f"{name}@example.test", **kwargs)
        if role:
            user.groups.add(Group.objects.get(name=role))
        return user

    def create_protocol(self, person):
        unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer=f"pdf-{uuid4().hex[:8]}")
        protocol = Protokoll.objects.create(
            wohnung=unit,
            person=person,
            vermieter_name="Eva Verwaltung",
            protokoll_typ=ProtokollTyp.MOVE_IN,
            uebergabe_status=UebergabeStatus.RENOVATED,
            abnahme_status=AbnahmeStatus.ACCEPTED,
            heizungsablesungen="Fiktive Ablesung",
            zaehlernummer_wasser_kalt="TEST-WK",
            zaehlernummer_wasser_warm="TEST-WW",
            zaehlernummer_heizung="TEST-HZ",
            zaehlernummer_strom="TEST-ST",
        )
        master_room = Raum.objects.create(wohnung=unit, name="Küche")
        room = protocol.raeume.create(raum=master_room, name=master_room.name)
        room.raum_merkmale.create(merkmal=self.feature, wert={"text": "Fiktive Feststellung"})
        ProtokollSchluessel.objects.create(
            protokoll=protocol, anzahl=1, raum_bezeichnung="Wohnungstür"
        )
        return protocol

    def preview_token(self, protocol):
        response = self.client.get(self.url("finalize", protocol))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["completion_errors"], [])
        self.assert_private(response)
        return response.context["form"].initial["content_token"]

    @staticmethod
    def signing_data(token):
        return {
            "content_token": token,
            "schluessel_ueberprueft": "on",
            "bestaetigung_erklaert": "on",
            "tenant_mode": "signed",
            "mitarbeiter": fixtures.signature_file(),
            "mieter": fixtures.signature_file(),
        }

    def confirm(self, protocol):
        token = self.preview_token(protocol)
        response = self.client.post(self.url("confirm", protocol), self.signing_data(token))
        self.assertEqual(response.status_code, 200, response.content)
        self.assert_private(response)
        protocol.refresh_from_db()
        self.assertEqual(protocol.status, ProtokollStatus.SIGNED)
        return Path(self.directory.name, protocol.dokument_pfad).read_bytes()

    def assert_private(self, response):
        directives = response.get("Cache-Control", "")
        self.assertIn("private", directives)
        self.assertIn("no-store", directives)

    def assert_pdf(self, protocol, expected):
        response = self.client.get(self.url("pdf", protocol))
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), expected)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertIn("attachment;", response["Content-Disposition"])
            self.assertIn(str(protocol.pk), response["Content-Disposition"])
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assert_private(response)
        finally:
            if not response.closed:
                response.close()

    def archive_state(self):
        return (
            list(Protokoll.objects.order_by("pk").values()),
            list(ProtokollUnterschrift.objects.order_by("pk").values()),
            list(Wohnung.objects.order_by("pk").values_list("pk", "status")),
            sorted(
                (str(path.relative_to(self.directory.name)), path.read_bytes())
                for path in Path(self.directory.name).rglob("*")
                if path.is_file()
            ),
        )

    def assert_refused(self, url, status, method="get", data=None, client=None):
        client = self.client if client is None else client
        before = self.archive_state()
        with (
            patch.object(default_storage, "open", side_effect=AssertionError("Archiv gelesen")),
            patch.object(default_storage, "save", side_effect=AssertionError("Archiv geschrieben")),
        ):
            response = getattr(client, method)(url, data or {})
            self.assertEqual(response.status_code, status)
            self.assertFalse(response.streaming)
            if status == 302:
                self.assertRedirects(
                    response, f"{reverse('login')}?next={url}", fetch_redirect_response=False
                )
        self.assertEqual(self.archive_state(), before)

    def assert_all_refused(self, status, token=""):
        self.assert_refused(reverse("wohnungsverwaltung:handover_protocol_mine"), status)
        self.assert_refused(self.url("pdf"), status)
        self.assert_refused(self.url("pdf_create"), status, "post")
        self.assert_refused(self.url("finalize", self.other_protocol), status)
        self.assert_refused(
            self.url("confirm", self.other_protocol), status, "post", self.signing_data(token)
        )

    def assert_mine(self, protocols):
        response = self.client.get(reverse("wohnungsverwaltung:handover_protocol_mine"))
        self.assertEqual(response.status_code, 200)
        self.assert_private(response)
        self.assertCountEqual(response.context["protocols"], protocols)
        return response

    def test_anonymous_applicants_and_staff_flag_alone_cannot_use_pdf_or_export_endpoints(self):
        token = self.preview_token(self.other_protocol)
        self.confirm(self.protocol)
        self.client.logout()
        self.assert_all_refused(302, token)
        for user in (*self.applicants, self.staff):
            with self.subTest(user=user):
                self.client.force_login(user)
                self.assert_all_refused(403, token)

    def test_tenants_get_only_own_signed_archives_and_cannot_create_or_read_foreign_exports(self):
        first = self.confirm(self.protocol)
        second = self.confirm(self.other_protocol)
        for status in (ProtokollStatus.OPEN, ProtokollStatus.BLOCKED):
            extra = self.create_protocol(self.person)
            Protokoll.objects.filter(pk=extra.pk).update(status=status)
        for user, owned, foreign, contents in (
            (self.tenant, self.protocol, self.other_protocol, first),
            (self.other_tenant, self.other_protocol, self.protocol, second),
        ):
            with self.subTest(user=user):
                self.client.force_login(user)
                self.assert_pdf(owned, contents)
                listing = self.assert_mine([owned])
                self.assertNotContains(listing, str(foreign.pk))
                self.assert_refused(self.url("pdf", foreign), 404)
                self.assert_refused(self.url("pdf_create", foreign), 404, "post")
                self.assert_refused(self.url("finalize", owned), 403)
                self.assert_refused(self.url("confirm", owned), 403, "post")

    def test_other_employee_can_read_existing_archives_and_confirm_another_persons_protocol(self):
        first = self.confirm(self.protocol)
        employee = self.create_user(
            "other-employee", ROLE_EMPLOYEE, first_name="Fiktive", last_name="Vertretung"
        )
        self.assertFalse(employee.is_staff)
        self.client.force_login(employee)
        self.assert_pdf(self.protocol, first)
        second = self.confirm(self.other_protocol)
        self.assert_pdf(self.other_protocol, second)
        self.assertEqual(self.other_protocol.abgeschlossen_von_id, employee.pk)
        self.assertEqual(self.other_protocol.unterschriften.count(), 2)

    def test_tenant_can_create_only_own_legacy_archive_and_cannot_change_it_by_repeating_post(self):
        Protokoll.objects.filter(pk=self.protocol.pk).update(status=ProtokollStatus.SIGNED)
        self.other_person.wohnung = self.unit
        self.other_person.save(update_fields=["wohnung"])
        self.client.force_login(self.other_tenant)
        self.assert_refused(self.url("pdf_create"), 404, "post")
        self.client.force_login(self.tenant)
        self.assert_refused(self.url("pdf"), 404)
        response = self.client.post(self.url("pdf_create"))
        self.assertRedirects(response, self.url("pdf"), fetch_redirect_response=False)
        self.assert_private(response)
        self.protocol.refresh_from_db()
        self.assertTrue(self.protocol.nachtraeglich_gesichert)
        self.assertFalse(self.protocol.unterschriften.exists())
        contents = Path(self.directory.name, self.protocol.dokument_pfad).read_bytes()
        self.assert_pdf(self.protocol, contents)
        before = self.archive_state()
        self.client.post(self.url("pdf_create"))
        self.assertEqual(self.archive_state(), before)

    def test_direct_tenant_permission_allows_own_downloads_and_revocation_is_immediate(self):
        contents = self.confirm(self.protocol)
        self.tenant.groups.clear()
        permission = Permission.objects.get(
            content_type__app_label="immobilien", codename="access_tenant_area"
        )
        self.tenant.user_permissions.add(permission)
        self.client.force_login(self.tenant)
        self.assert_pdf(self.protocol, contents)
        self.assert_mine([self.protocol])
        before = self.archive_state()
        self.assertEqual(self.client.post(self.url("pdf_create")).status_code, 302)
        self.assertEqual(self.archive_state(), before)
        self.tenant.user_permissions.clear()
        self.assert_all_refused(403)

    def test_direct_employee_permission_allows_creation_and_revocation_blocks_every_endpoint(self):
        user = self.create_user("direct-employee", first_name="Direkte", last_name="Vertretung")
        permission = Permission.objects.get(
            content_type__app_label="immobilien", codename="access_employee_area"
        )
        user.user_permissions.add(permission)
        self.client.force_login(user)
        Protokoll.objects.filter(pk=self.protocol.pk).update(status=ProtokollStatus.SIGNED)
        self.assertEqual(self.client.post(self.url("pdf_create")).status_code, 302)
        self.protocol.refresh_from_db()
        self.assertTrue(self.protocol.nachtraeglich_gesichert)
        contents = Path(self.directory.name, self.protocol.dokument_pfad).read_bytes()
        self.assert_pdf(self.protocol, contents)
        second = self.confirm(self.other_protocol)
        self.assert_pdf(self.other_protocol, second)
        user.user_permissions.clear()
        self.assert_all_refused(403)

    def test_deactivation_revokes_pdf_and_export_access_for_existing_employee_and_tenant_sessions(
        self,
    ):
        contents = self.confirm(self.protocol)
        token = self.preview_token(self.other_protocol)
        for user in (self.employee, self.tenant):
            with self.subTest(user=user):
                self.client.force_login(user)
                self.assert_pdf(self.protocol, contents)
                user.is_active = False
                user.save(update_fields=["is_active"])
                self.assert_all_refused(302, token)

    def test_employee_to_tenant_role_change_preserves_only_owned_pdf_access(self):
        contents = self.confirm(self.protocol)
        self.confirm(self.other_protocol)
        self.person.user = self.employee
        self.person.save(update_fields=["user"])
        self.client.force_login(self.employee)
        self.assert_pdf(
            self.other_protocol,
            Path(self.directory.name, self.other_protocol.dokument_pfad).read_bytes(),
        )
        self.employee.groups.set([Group.objects.get(name=ROLE_TENANT)])
        self.assert_pdf(self.protocol, contents)
        self.assert_mine([self.protocol])
        self.assert_refused(self.url("pdf", self.other_protocol), 404)
        self.assert_refused(self.url("pdf_create", self.other_protocol), 404, "post")
        self.assert_refused(self.url("finalize"), 403)
        self.assert_refused(self.url("confirm"), 403, "post")

    def test_removing_tenant_role_blocks_own_pdf_and_legacy_generation_in_existing_session(self):
        contents = self.confirm(self.protocol)
        self.client.force_login(self.tenant)
        self.assert_pdf(self.protocol, contents)
        self.tenant.groups.set([Group.objects.get(name=ROLE_APPLICANT)])
        self.assert_all_refused(403)

    def test_removing_person_link_hides_archived_pdf_without_changing_the_archive(self):
        contents = self.confirm(self.protocol)
        self.client.force_login(self.tenant)
        self.assert_pdf(self.protocol, contents)
        self.person.user = None
        self.person.save(update_fields=["user"])
        self.assert_refused(self.url("pdf"), 404)
        self.assert_refused(self.url("pdf_create"), 404, "post")
        self.assert_mine([])

    def test_open_and_blocked_protocols_stay_hidden_even_if_an_archive_file_exists(self):
        self.confirm(self.protocol)
        for status in (ProtokollStatus.OPEN, ProtokollStatus.BLOCKED):
            Protokoll.objects.filter(pk=self.protocol.pk).update(status=status)
            for user in (self.tenant, self.employee):
                with self.subTest(status=status, user=user):
                    self.client.force_login(user)
                    self.assert_refused(self.url("pdf"), 404)
                    self.assert_refused(self.url("pdf_create"), 404, "post")
            self.client.force_login(self.tenant)
            self.assert_mine([])

    def test_unknown_protocol_ids_cannot_read_preview_or_create_archives(self):
        unknown = Protokoll(pk=uuid4())
        for user in (self.employee, self.tenant):
            self.client.force_login(user)
            self.assert_refused(self.url("pdf", unknown), 404)
            self.assert_refused(self.url("pdf_create", unknown), 404, "post")
        self.client.force_login(self.employee)
        self.assert_refused(self.url("finalize", unknown), 404)
        self.assert_refused(self.url("confirm", unknown), 404, "post", self.signing_data(""))

    def test_confirmation_token_cannot_be_reused_for_a_different_protocol(self):
        token = self.preview_token(self.protocol)
        self.assert_refused(
            self.url("confirm", self.other_protocol), 409, "post", self.signing_data(token)
        )

    def test_missing_and_tampered_confirmation_tokens_cannot_create_archives(self):
        token = self.preview_token(self.protocol)
        for invalid in ("", f"x{token}"):
            with self.subTest(token=invalid):
                self.assert_refused(self.url("confirm"), 409, "post", self.signing_data(invalid))

    def test_valid_pending_confirmation_cannot_run_after_employee_role_removal(self):
        token = self.preview_token(self.other_protocol)
        self.employee.groups.clear()
        self.assert_refused(
            self.url("confirm", self.other_protocol), 403, "post", self.signing_data(token)
        )

    def test_unsupported_http_methods_never_read_or_write_archives(self):
        self.confirm(self.protocol)
        self.employee.groups.add(Group.objects.get(name=ROLE_TENANT))
        for url in (
            self.url("pdf"),
            self.url("finalize", self.other_protocol),
            reverse("wohnungsverwaltung:handover_protocol_mine"),
        ):
            for method in ("head", "post", "put", "patch", "delete", "options"):
                with self.subTest(url=url, method=method):
                    self.assert_refused(url, 405, method)
        for action in ("confirm", "pdf_create"):
            for method in ("get", "head", "put", "patch", "delete", "options"):
                with self.subTest(action=action, method=method):
                    self.assert_refused(self.url(action), 405, method)

    def test_valid_confirmation_and_tenant_legacy_generation_require_csrf(self):
        token = self.preview_token(self.other_protocol)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.employee)
        self.assert_refused(
            self.url("confirm", self.other_protocol),
            403,
            "post",
            self.signing_data(token),
            client=client,
        )
        Protokoll.objects.filter(pk=self.protocol.pk).update(status=ProtokollStatus.SIGNED)
        client.force_login(self.tenant)
        self.assert_refused(self.url("pdf_create"), 403, "post", client=client)

    def test_missing_archive_is_not_regenerated_by_tenant_or_employee(self):
        self.confirm(self.protocol)
        default_storage.delete(self.protocol.dokument_pfad)
        for user in (self.employee, self.tenant):
            with self.subTest(user=user):
                self.client.force_login(user)
                before = self.archive_state()
                response = self.client.get(self.url("pdf"))
                self.assertEqual(response.status_code, 503)
                self.assert_private(response)
                self.assertEqual(self.client.post(self.url("pdf_create")).status_code, 302)
                self.assertEqual(self.archive_state(), before)

    def test_django_never_serves_archived_pdf_or_signatures_through_media_paths(self):
        self.confirm(self.protocol)
        paths = [
            self.protocol.dokument_pfad,
            *self.protocol.unterschriften.values_list("datei", flat=True),
        ]
        for user in (None, self.tenant, self.employee):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for path in paths:
                self.assert_refused(f"{settings.MEDIA_URL}{path}", 404)
