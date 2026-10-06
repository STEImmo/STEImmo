from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from .access import ROLE_APPLICANT, ROLE_EMPLOYEE, ROLE_TENANT, ROLE_USER_MANAGEMENT
from .models import (
    ApplicationProof,
    ApplicationProofCategory,
    Bewerbung,
    BewerbungStatus,
    BewerbungStellplatz,
    Person,
    Stellplatz,
    StellplatzTyp,
    Wohnung,
)


class EmployeeDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = get_user_model().objects.create_user(username="dashboard-employee")
        cls.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        cls.applicant = get_user_model().objects.create_user(username="dashboard-applicant")
        cls.applicant.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        cls.unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="01")
        cls.empty_unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="02")
        cls.application = cls.create_application(cls.unit)
        cls.list_url = reverse("wohnungsverwaltung:employee_application_list")
        cls.detail_url = reverse(
            "wohnungsverwaltung:employee_application_detail", args=[cls.application.pk]
        )

    @staticmethod
    def create_application(unit, **kwargs):
        person = Person.objects.create(
            vorname="Berta",
            nachname="Bewerber",
            email=f"{uuid4()}@example.test",
            telefonnummer="0123456789",
            geburtsdatum="2000-01-02",
        )
        return Bewerbung.objects.create(
            person=person,
            wohnung=unit,
            personenanzahl=2,
            haustiere=True,
            ueber_mich="Ich studiere Informatik.",
            **kwargs,
        )

    def setUp(self):
        self.client.force_login(self.employee)

    def test_dashboard_and_details_require_employee_access(self):
        for url in (self.list_url, self.detail_url):
            with self.subTest(url=url):
                self.client.logout()
                self.assertEqual(self.client.get(url).status_code, 302)
                self.client.force_login(self.applicant)
                self.assertEqual(self.client.get(url).status_code, 403)
                self.client.force_login(self.employee)
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_entry_shows_all_units_and_counts_without_applicant_data(self):
        self.create_application(self.unit, status=BewerbungStatus.DECLINED)
        response = self.client.get(self.list_url)
        self.assertContains(response, str(self.empty_unit))
        self.assertNotContains(response, "Berta Bewerber")
        counts = {unit.pk: unit.application_count for unit in response.context["units"]}
        self.assertEqual(counts, {self.unit.pk: 2, self.empty_unit.pk: 0})
        self.assertContains(response, f"?wohnung={self.unit.pk}")

    def test_selected_unit_shows_only_its_applications(self):
        other = self.create_application(self.empty_unit)
        response = self.client.get(self.list_url, {"wohnung": self.unit.pk})
        self.assertEqual(list(response.context["applications"]), [self.application])
        self.assertNotContains(response, str(other.pk))
        self.assertContains(response, "Berta Bewerber")
        self.assertContains(response, "Personenanzahl")
        self.assertContains(response, "Haustiere")
        self.assertContains(response, "Pre-Eingang")
        self.assertNotContains(response, self.application.person.email)

    def test_all_application_statuses_remain_visible(self):
        for kwargs in (
            {"status": BewerbungStatus.DECLINED},
            {"status": BewerbungStatus.BLOCKED},
            {"interest_withdrawn_at": timezone.now()},
            {"main_application_unlocked": True},
            {"submitted_at": timezone.now()},
        ):
            self.create_application(self.unit, **kwargs)
        response = self.client.get(self.list_url, {"wohnung": self.unit.pk})
        self.assertEqual(response.context["page_obj"].paginator.count, 6)
        for status in (
            "In Bearbeitung",
            "Abgelehnt",
            "Gesperrt",
            "Zurückgezogen",
            "Main-Bewerbung freigeschaltet",
            "Main-Bewerbung eingereicht",
        ):
            self.assertContains(response, status)

    def test_invalid_or_unknown_unit_returns_404(self):
        for value in ("", "invalid", str(uuid4())):
            with self.subTest(value=value):
                self.assertEqual(
                    self.client.get(self.list_url, {"wohnung": value}).status_code, 404
                )

    def test_empty_unit_has_clear_empty_state(self):
        response = self.client.get(self.list_url, {"wohnung": self.empty_unit.pk})
        self.assertContains(response, "Für diese Wohnung liegen noch keine Bewerbungen vor.")

    def test_pagination_orders_newest_first_and_preserves_unit(self):
        for _ in range(20):
            self.create_application(self.unit)
        Bewerbung.objects.filter(pk=self.application.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )
        first = self.client.get(self.list_url, {"wohnung": self.unit.pk})
        second = self.client.get(self.list_url, {"wohnung": self.unit.pk, "page": 2})
        self.assertEqual(len(first.context["applications"]), 20)
        self.assertEqual(list(second.context["applications"]), [self.application])
        self.assertContains(first, f"?wohnung={self.unit.pk}&amp;page=2")

    def test_equal_timestamps_have_stable_order(self):
        other = self.create_application(self.unit)
        Bewerbung.objects.all().update(created_at=timezone.now())
        response = self.client.get(self.list_url, {"wohnung": self.unit.pk})
        self.assertEqual(
            [application.pk for application in response.context["applications"]],
            sorted([self.application.pk, other.pk]),
        )

    def test_invalid_page_numbers_remain_usable(self):
        for page in ("invalid", "0", "999"):
            self.assertContains(
                self.client.get(self.list_url, {"wohnung": self.unit.pk, "page": page}),
                "Berta Bewerber",
            )

    def test_detail_shows_pre_data_and_hides_main_draft_files(self):
        proof = ApplicationProof.objects.create(
            application=self.application,
            category=ApplicationProofCategory.IDENTITY,
            file="private/draft",
            original_name="geheimer-entwurf.png",
        )
        response = self.client.get(self.detail_url)
        self.assertContains(response, "Pre-Bewerbung")
        self.assertContains(response, "Main-Bewerbung")
        self.assertContains(response, "Noch nicht eingereicht")
        for value in ("Ich studiere Informatik.", "0123456789", "02.01.2000", "Haustiere"):
            self.assertContains(response, value)
        self.assertNotContains(response, proof.original_name)
        self.assertNotContains(response, "Sicher herunterladen")
        download_url = reverse(
            "wohnungsverwaltung:employee_application_proof_download",
            args=[self.application.pk, proof.pk],
        )
        self.assertEqual(self.client.get(download_url).status_code, 404)
        self.assertContains(response, f"?wohnung={self.unit.pk}")

    def test_submitted_main_shows_proofs_and_submission_date(self):
        self.application.submitted_at = timezone.now()
        self.application.save(update_fields=["submitted_at"])
        ApplicationProof.objects.create(
            application=self.application,
            category=ApplicationProofCategory.IDENTITY,
            file="private/submitted",
            original_name="eingereicht.png",
        )
        response = self.client.get(self.detail_url)
        self.assertContains(response, "eingereicht.png")
        self.assertContains(response, "Sicher herunterladen")
        self.assertNotContains(response, "/media/")
        self.assertContains(response, "Main-Eingang")

    def test_unknown_application_returns_404(self):
        self.assertEqual(
            self.client.get(
                reverse("wohnungsverwaltung:employee_application_detail", args=[uuid4()])
            ).status_code,
            404,
        )

    def test_dashboard_and_detail_reject_post(self):
        for url in (self.list_url, self.detail_url):
            self.assertEqual(self.client.post(url).status_code, 405)

    def test_query_count_does_not_grow_with_units_or_applications(self):
        def query_count(params):
            with CaptureQueriesContext(connection) as queries:
                self.client.get(self.list_url, params)
            return len(queries)

        overview_before = query_count({})
        table_before = query_count({"wohnung": self.unit.pk})
        for number in range(5):
            self.create_application(self.unit)
            Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer=f"extra-{number}")
        self.assertEqual(query_count({}), overview_before)
        self.assertEqual(query_count({"wohnung": self.unit.pk}), table_before)

    def test_dashboard_pages_disallow_caching_of_applicant_data(self):
        for url, params in (
            (self.list_url, {}),
            (self.list_url, {"wohnung": self.unit.pk}),
            (self.detail_url, {}),
        ):
            with self.subTest(url=url, params=params):
                response = self.client.get(url, params)
                directives = response.get("Cache-Control", "").split(", ")
                self.assertIn("no-store", directives)
                self.assertIn("private", directives)

    def test_dashboard_access_uses_permissions_and_denies_other_roles(self):
        manager = get_user_model().objects.create_user(username="dashboard-manager")
        manager.groups.add(Group.objects.get(name=ROLE_USER_MANAGEMENT))
        direct_user = get_user_model().objects.create_user(username="dashboard-direct")
        direct_user.user_permissions.add(Permission.objects.get(codename="access_employee_area"))
        tenant = get_user_model().objects.create_user(username="dashboard-tenant")
        tenant.groups.add(Group.objects.get(name=ROLE_TENANT))
        ordinary_user = get_user_model().objects.create_user(username="dashboard-ordinary")
        for user, expected_status in (
            (manager, 200),
            (direct_user, 200),
            (tenant, 403),
            (ordinary_user, 403),
        ):
            self.client.force_login(user)
            for url, params in (
                (self.list_url, {}),
                (self.list_url, {"wohnung": self.unit.pk}),
                (self.detail_url, {}),
            ):
                with self.subTest(user=user.username, url=url, params=params):
                    self.assertEqual(self.client.get(url, params).status_code, expected_status)
        self.client.logout()
        self.assertEqual(self.client.get(self.detail_url).status_code, 302)

    def test_detail_displays_all_existing_pre_data_and_escapes_user_text(self):
        person = self.application.person
        person.titel = "Dr."
        person.geschlecht = "divers"
        person.save(update_fields=["titel", "geschlecht"])
        self.application.barrierefreiheit_benoetigt = True
        self.application.alternative_wohnung_akzeptiert = True
        self.application.ueber_mich = '<script>alert("x")</script>'
        self.application.save()
        parking = Stellplatz.objects.create(name="Stellplatz A", stellplatz_typ=StellplatzTyp.CAR)
        BewerbungStellplatz.objects.create(bewerbung=self.application, stellplatz=parking)
        response = self.client.get(self.detail_url)
        for value in (
            "Dr.",
            "Divers",
            "02.01.2000",
            "0123456789",
            person.email,
            "Stellplatz A",
            "Barrierefreiheit benötigt",
            "Alternative Wohnung akzeptiert",
        ):
            self.assertContains(response, value)
        self.assertContains(response, "<dd>Ja</dd>", count=3, html=True)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("x")</script>')

    def test_pages_with_equal_timestamps_do_not_skip_or_repeat_applications(self):
        for _ in range(44):
            self.create_application(self.unit)
        Bewerbung.objects.filter(wohnung=self.unit).update(created_at=timezone.now())
        ids = []
        for page, expected_length in ((1, 20), (2, 20), (3, 5)):
            response = self.client.get(self.list_url, {"wohnung": self.unit.pk, "page": page})
            applications = list(response.context["applications"])
            self.assertEqual(len(applications), expected_length)
            ids.extend(application.pk for application in applications)
        self.assertEqual(len(set(ids)), 45)
        self.assertEqual(ids, sorted(ids))

    def test_legacy_main_draft_remains_hidden_until_submission(self):
        self.application.identity_proof = "private/legacy-identity"
        self.application.identity_proof_original_name = "legacy-identitaet.pdf"
        self.application.save(update_fields=["identity_proof", "identity_proof_original_name"])
        response = self.client.get(self.detail_url)
        self.assertNotContains(response, "legacy-identitaet.pdf")
        download_url = reverse(
            "wohnungsverwaltung:employee_application_document",
            args=[self.application.pk, "identity_proof"],
        )
        self.assertEqual(self.client.get(download_url).status_code, 404)
        self.application.submitted_at = timezone.now()
        self.application.save(update_fields=["submitted_at"])
        self.assertContains(self.client.get(self.detail_url), "legacy-identitaet.pdf")


class EmployeeDashboardDisclosureTests(TestCase):
    def setUp(self):
        media_root = self.enterContext(TemporaryDirectory())
        self.enterContext(self.settings(MEDIA_ROOT=media_root))
        self.employee = get_user_model().objects.create_user(username="disclosure-employee")
        self.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        self.unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="audit")
        self.submitted = EmployeeDashboardTests.create_application(
            self.unit, submitted_at=timezone.now()
        )
        self.draft = EmployeeDashboardTests.create_application(
            self.unit, main_application_unlocked=True
        )
        self.submitted_proof = self.create_proof(self.submitted, "eingereichte-datei.pdf")
        self.draft_proof = self.create_proof(self.draft, "privater-main-entwurf.pdf")
        self.draft.identity_proof.save("legacy-entwurf.pdf", self.pdf_upload(), save=True)
        self.draft.identity_proof_original_name = "privater-alt-entwurf.pdf"
        self.draft.save(update_fields=["identity_proof_original_name"])
        self.client.force_login(self.employee)

    @staticmethod
    def pdf_upload():
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_metadata({"/Title": "Nur fiktive Audit-Testdaten"})
        output = BytesIO()
        writer.write(output)
        return SimpleUploadedFile("audit.pdf", output.getvalue(), content_type="application/pdf")

    def create_proof(self, application, name):
        return ApplicationProof.objects.create(
            application=application,
            category=ApplicationProofCategory.IDENTITY,
            original_name=name,
            file=self.pdf_upload(),
        )

    def proof_url(self, application, proof):
        return reverse(
            "wohnungsverwaltung:employee_application_proof_download",
            args=[application.pk, proof.pk],
        )

    def test_employee_cannot_bypass_draft_protection_with_direct_or_mixed_urls(self):
        urls = (
            self.proof_url(self.draft, self.draft_proof),
            self.proof_url(self.submitted, self.draft_proof),
            self.proof_url(self.draft, self.submitted_proof),
            reverse(
                "wohnungsverwaltung:employee_application_document",
                args=[self.draft.pk, "identity_proof"],
            ),
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 404)
                self.assertNotContains(response, "Nur fiktive Audit-Testdaten", status_code=404)

    def test_employee_cannot_mix_two_submitted_application_and_proof_ids(self):
        other_unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="other")
        other = EmployeeDashboardTests.create_application(other_unit, submitted_at=timezone.now())
        other_proof = self.create_proof(other, "andere-bewerbung.pdf")
        self.assertEqual(
            self.client.get(self.proof_url(self.submitted, other_proof)).status_code, 404
        )
        self.assertEqual(
            self.client.get(self.proof_url(other, self.submitted_proof)).status_code, 404
        )
        response = self.client.get(self.proof_url(other, other_proof))
        self.assertEqual(response.status_code, 200)
        b"".join(response.streaming_content)

    def test_employee_downloads_submitted_files_in_all_review_statuses(self):
        for status, withdrawn in (
            (BewerbungStatus.OPEN, None),
            (BewerbungStatus.DECLINED, None),
            (BewerbungStatus.BLOCKED, None),
            (BewerbungStatus.OPEN, timezone.now()),
        ):
            self.submitted.status = status
            self.submitted.interest_withdrawn_at = withdrawn
            self.submitted.save(update_fields=["status", "interest_withdrawn_at"])
            response = self.client.get(self.proof_url(self.submitted, self.submitted_proof))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF-"))
            self.assertIn("attachment", response["Content-Disposition"])
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_all_draft_states_hide_both_legacy_and_current_filenames(self):
        for status, withdrawn in (
            (BewerbungStatus.OPEN, None),
            (BewerbungStatus.DECLINED, None),
            (BewerbungStatus.BLOCKED, None),
            (BewerbungStatus.OPEN, timezone.now()),
        ):
            self.draft.status = status
            self.draft.interest_withdrawn_at = withdrawn
            self.draft.save(update_fields=["status", "interest_withdrawn_at"])
            response = self.client.get(
                reverse("wohnungsverwaltung:employee_application_detail", args=[self.draft.pk])
            )
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "privater-main-entwurf.pdf")
            self.assertNotContains(response, "privater-alt-entwurf.pdf")
            self.assertNotContains(response, str(self.draft_proof.pk))

    def test_uploaded_files_have_no_direct_media_url_even_for_employees(self):
        for file in (self.submitted_proof.file, self.draft_proof.file, self.draft.identity_proof):
            response = self.client.get(file.url)
            self.assertEqual(response.status_code, 404)

    def test_employee_role_does_not_grant_applicant_or_user_management_access(self):
        for url in (
            reverse("wohnungsverwaltung:main_application_status", args=[self.draft.pk]),
            reverse(
                "wohnungsverwaltung:applicant_application_proof_download",
                args=[self.draft.pk, self.draft_proof.pk],
            ),
            reverse(
                "wohnungsverwaltung:applicant_application_document",
                args=[self.draft.pk, "identity_proof"],
            ),
            reverse("verwaltung:user_account_list"),
        ):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_staff_flag_alone_does_not_grant_dashboard_or_download_access(self):
        staff = get_user_model().objects.create_user(username="staff-only", is_staff=True)
        self.client.force_login(staff)
        for url in (
            reverse("wohnungsverwaltung:employee_application_list"),
            reverse("wohnungsverwaltung:employee_application_detail", args=[self.submitted.pk]),
            self.proof_url(self.submitted, self.submitted_proof),
        ):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_revoked_employee_permission_and_disabled_accounts_lose_access(self):
        self.employee.groups.clear()
        url = self.proof_url(self.submitted, self.submitted_proof)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        self.employee.is_active = False
        self.employee.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_legacy_document_type_cannot_select_arbitrary_model_fields(self):
        for document_type in ("ueber_mich", "identity_proof_original_name", "__dict__"):
            url = reverse(
                "wohnungsverwaltung:employee_application_document",
                args=[self.submitted.pk, document_type],
            )
            self.assertEqual(self.client.get(url).status_code, 404)
