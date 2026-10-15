from datetime import timedelta
from html.parser import HTMLParser
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from .access import ROLE_APPLICANT, ROLE_EMPLOYEE, ROLE_TENANT, ROLE_USER_MANAGEMENT
from .models import (
    ApplicationProof,
    ApplicationProofCategory,
    ApplicationReviewEvent,
    Bewerbung,
    BewerbungStatus,
    BewerbungStellplatz,
    Person,
    Stellplatz,
    StellplatzTyp,
    ViewingAppointment,
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
        application_data = {
            "personenanzahl": 2,
            "haustiere": True,
            "ueber_mich": "Ich studiere Informatik.",
        }
        application_data.update(kwargs)
        return Bewerbung.objects.create(person=person, wohnung=unit, **application_data)

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
        response = self.client.get(self.list_url, {"wohnung": self.unit.pk, "segment": "all"})
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


class EmployeeApplicationSelectionTests(TestCase):
    def record_completed_viewing(self, application):
        start = timezone.now() - timedelta(days=1)
        ViewingAppointment.objects.create(
            application=application,
            starts_at=start,
            ends_at=start + timedelta(minutes=30),
            status="completed",
        )

    def setUp(self):
        self.employee = get_user_model().objects.create_user(username="selection-employee")
        self.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        self.applicant_user = get_user_model().objects.create_user(
            username="selection-applicant", email="applicant@example.test", password="test"
        )
        self.applicant_user.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        self.unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="selection")
        self.match = EmployeeDashboardTests.create_application(self.unit, haustiere=False)
        self.occupancy_exception = EmployeeDashboardTests.create_application(
            self.unit, personenanzahl=3, haustiere=False
        )
        self.pet_exception = EmployeeDashboardTests.create_application(self.unit, haustiere=True)
        self.client.force_login(self.employee)
        self.list_url = reverse("wohnungsverwaltung:employee_application_list")

    def configure_requirements(self, **overrides):
        self.unit.max_occupants = overrides.get("max_occupants", 2)
        self.unit.occupancy_requirement_reason = overrides.get(
            "occupancy_requirement_reason", "Grundriss und nutzbare Schlafräume"
        )
        self.unit.pet_review_required = overrides.get("pet_review_required", True)
        self.unit.pet_review_reason = overrides.get(
            "pet_review_reason", "Prüfung der konkreten Tierhaltung"
        )
        self.unit.save()

    def test_unconfigured_requirements_do_not_exclude_applications(self):
        response = self.client.get(self.list_url, {"wohnung": self.unit.pk})
        self.assertEqual(
            {item.pk for item in response.context["applications"]},
            {self.match.pk, self.occupancy_exception.pk, self.pet_exception.pk},
        )
        self.assertContains(response, "Anforderungen offen")

    def test_main_invitation_is_shown_for_open_applications_and_explained_for_declined(self):
        open_detail_url = reverse(
            "wohnungsverwaltung:employee_application_detail", args=[self.match.pk]
        )
        response = self.client.get(open_detail_url)
        self.assertContains(response, "Für die Main-Freischaltung fehlt")
        self.assertNotContains(response, "Main-Bewerbung freischalten und einladen")
        self.record_completed_viewing(self.match)
        response = self.client.get(open_detail_url)
        self.assertContains(response, "Main-Bewerbung freischalten und einladen")
        self.assertContains(response, "Ich bestätige die positive Entscheidung")

        declined = EmployeeDashboardTests.create_application(
            self.unit, status=BewerbungStatus.DECLINED
        )
        declined_detail_url = reverse(
            "wohnungsverwaltung:employee_application_detail", args=[declined.pk]
        )
        response = self.client.get(declined_detail_url)
        self.assertContains(response, "Aktueller Status: Abgelehnt")
        self.assertNotContains(response, "Main-Bewerbung freischalten und einladen")

    def test_review_forms_have_unique_reason_ids_and_matching_labels(self):
        self.record_completed_viewing(self.pet_exception)
        self.configure_requirements()
        response = self.client.get(
            reverse("wohnungsverwaltung:employee_application_detail", args=[self.pet_exception.pk])
        )
        reason_ids = [
            response.context[name]["reason"].id_for_label
            for name in ("priority_form", "eligibility_form", "invitation_form")
        ]

        self.assertEqual(len(set(reason_ids)), 3)
        for reason_id in reason_ids:
            with self.subTest(reason_id=reason_id):
                self.assertContains(response, f'id="{reason_id}"', count=1)
                self.assertContains(response, f'for="{reason_id}"', count=1)

    def test_occupancy_excess_is_declined_and_only_pet_applications_need_review(self):
        self.configure_requirements()
        matching = self.client.get(self.list_url, {"wohnung": self.unit.pk})
        review = self.client.get(self.list_url, {"wohnung": self.unit.pk, "segment": "review"})
        all_applications = self.client.get(
            self.list_url, {"wohnung": self.unit.pk, "segment": "all"}
        )

        self.occupancy_exception.refresh_from_db()
        self.assertEqual(self.occupancy_exception.status, BewerbungStatus.DECLINED)
        self.assertEqual(self.occupancy_exception.suitability_review_flags, ())
        rejection_event = ApplicationReviewEvent.objects.get(
            application=self.occupancy_exception,
            kind=ApplicationReviewEvent.Kind.OCCUPANCY_DECLINED,
        )
        self.assertIsNone(rejection_event.actor)
        self.assertIn("Höchstzahl von 2 Personen", rejection_event.reason)
        self.assertEqual([item.pk for item in matching.context["applications"]], [self.match.pk])
        self.assertEqual(
            {item.pk for item in review.context["applications"]},
            {self.pet_exception.pk},
        )
        self.assertEqual(
            {item.pk for item in all_applications.context["applications"]},
            {self.match.pk, self.occupancy_exception.pk, self.pet_exception.pk},
        )
        self.assertContains(review, "Einzelfallprüfung")

    def test_occupancy_excess_is_not_classified_as_individual_review(self):
        self.configure_requirements()
        Bewerbung.objects.filter(pk=self.occupancy_exception.pk).update(status=BewerbungStatus.OPEN)

        matching = self.client.get(self.list_url, {"wohnung": self.unit.pk})
        review = self.client.get(self.list_url, {"wohnung": self.unit.pk, "segment": "review"})
        all_applications = self.client.get(
            self.list_url, {"wohnung": self.unit.pk, "segment": "all"}
        )

        self.assertNotIn(self.occupancy_exception, matching.context["applications"])
        self.assertNotIn(self.occupancy_exception, review.context["applications"])
        self.assertIn(self.occupancy_exception, all_applications.context["applications"])

    def test_requirement_changes_keep_already_unlocked_or_submitted_main_applications(self):
        invited = EmployeeDashboardTests.create_application(
            self.unit, personenanzahl=3, haustiere=False, main_application_unlocked=True
        )
        submitted = EmployeeDashboardTests.create_application(
            self.unit,
            personenanzahl=3,
            haustiere=False,
            main_application_unlocked=True,
            submitted_at=timezone.now(),
        )

        self.configure_requirements()

        invited.refresh_from_db()
        submitted.refresh_from_db()
        self.assertEqual(invited.status, BewerbungStatus.OPEN)
        self.assertTrue(invited.main_application_unlocked)
        self.assertEqual(submitted.status, BewerbungStatus.OPEN)
        self.assertIsNotNone(submitted.submitted_at)

    def test_manual_eligibility_approval_is_reasoned_and_invalidated_by_requirement_changes(self):
        self.configure_requirements()
        approval_url = reverse(
            "wohnungsverwaltung:employee_application_suitability_approve",
            args=[self.pet_exception.pk],
        )
        response = self.client.post(approval_url, {"reason": "Tierhaltung wurde geprüft"})
        self.assertEqual(response.status_code, 302)
        event = ApplicationReviewEvent.objects.get(
            application=self.pet_exception,
            kind=ApplicationReviewEvent.Kind.ELIGIBILITY_APPROVED,
        )
        self.assertEqual(event.actor, self.employee)
        self.assertEqual(event.reason, "Tierhaltung wurde geprüft")
        matching = self.client.get(self.list_url, {"wohnung": self.unit.pk})
        self.assertIn(self.pet_exception, matching.context["applications"])

        self.unit.pet_review_reason = "Ergänzte Prüfung der konkreten Tierhaltung"
        self.unit.save()
        matching = self.client.get(self.list_url, {"wohnung": self.unit.pk})
        review = self.client.get(self.list_url, {"wohnung": self.unit.pk, "segment": "review"})
        self.assertNotIn(self.pet_exception, matching.context["applications"])
        self.assertIn(self.pet_exception, review.context["applications"])

    def test_declined_application_cannot_receive_a_suitability_approval(self):
        self.configure_requirements()
        self.pet_exception.status = BewerbungStatus.DECLINED
        self.pet_exception.save(update_fields=("status",))
        approval_url = reverse(
            "wohnungsverwaltung:employee_application_suitability_approve",
            args=[self.pet_exception.pk],
        )

        response = self.client.post(approval_url, {"reason": "Tierhaltung wurde geprüft"})
        detail = self.client.get(
            reverse("wohnungsverwaltung:employee_application_detail", args=[self.pet_exception.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            ApplicationReviewEvent.objects.filter(
                application=self.pet_exception,
                kind=ApplicationReviewEvent.Kind.ELIGIBILITY_APPROVED,
            ).exists()
        )
        self.assertNotContains(detail, "Einzelfall begründet freigeben")

    def test_stale_requirement_save_does_not_restore_an_invalidated_approval(self):
        self.configure_requirements()
        approved_version = self.unit.requirements_version
        ApplicationReviewEvent.objects.create(
            application=self.pet_exception,
            actor=self.employee,
            kind=ApplicationReviewEvent.Kind.ELIGIBILITY_APPROVED,
            to_value="approved",
            reason="Tierhaltung wurde geprüft",
            requirements_version=approved_version,
        )
        first_edit = Wohnung.objects.get(pk=self.unit.pk)
        second_edit = Wohnung.objects.get(pk=self.unit.pk)
        new_reason = "Ergänzte Prüfung der konkreten Tierhaltung"
        first_edit.pet_review_reason = new_reason
        second_edit.pet_review_reason = new_reason

        first_edit.save()
        second_edit.save()

        self.unit.refresh_from_db()
        matching = self.client.get(self.list_url, {"wohnung": self.unit.pk})
        review = self.client.get(self.list_url, {"wohnung": self.unit.pk, "segment": "review"})
        self.assertEqual(self.unit.requirements_version, approved_version + 1)
        self.assertNotIn(self.pet_exception, matching.context["applications"])
        self.assertIn(self.pet_exception, review.context["applications"])

    def test_open_status_filter_excludes_withdrawn_applications(self):
        withdrawn = EmployeeDashboardTests.create_application(self.unit, haustiere=False)
        withdrawn.interest_withdrawn_at = timezone.now()
        withdrawn.save(update_fields=("interest_withdrawn_at",))

        open_response = self.client.get(
            self.list_url,
            {"wohnung": self.unit.pk, "segment": "all", "status": BewerbungStatus.OPEN},
        )
        withdrawn_response = self.client.get(
            self.list_url,
            {"wohnung": self.unit.pk, "segment": "all", "status": "withdrawn"},
        )

        open_ids = {application.pk for application in open_response.context["applications"]}
        withdrawn_ids = {
            application.pk for application in withdrawn_response.context["applications"]
        }
        self.assertEqual(
            open_ids,
            {self.match.pk, self.occupancy_exception.pk, self.pet_exception.pk},
        )
        self.assertEqual(withdrawn_ids, {withdrawn.pk})

    def test_people_filter_and_priority_sorting(self):
        self.configure_requirements(max_occupants=4, pet_review_required=False)
        self.match.review_priority = Bewerbung.Priority.HIGH
        self.match.personenanzahl = 4
        self.match.save(update_fields=["review_priority", "personenanzahl"])
        other = EmployeeDashboardTests.create_application(
            self.unit, personenanzahl=4, haustiere=False
        )
        response = self.client.get(
            self.list_url,
            {"wohnung": self.unit.pk, "people": "4", "sort": "priority"},
        )
        self.assertEqual(list(response.context["applications"]), [self.match, other])

    def test_pagination_preserves_combined_filters_and_sorting(self):
        class LinkParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links = []

            def handle_starttag(self, tag, attrs):
                if tag == "a":
                    self.links.append(dict(attrs).get("href", ""))

        self.match.personenanzahl = 4
        self.match.save(update_fields=("personenanzahl",))
        applications = [self.match] + [
            EmployeeDashboardTests.create_application(self.unit, personenanzahl=4)
            for _ in range(20)
        ]
        received_at = timezone.now()
        Bewerbung.objects.filter(pk__in=[item.pk for item in applications]).update(
            created_at=received_at, review_priority=Bewerbung.Priority.HIGH
        )
        received_date = timezone.localdate(received_at).isoformat()
        filters = {
            "wohnung": str(self.unit.pk),
            "segment": "all",
            "q": "Berta Bewerber",
            "people": "4",
            "status": BewerbungStatus.OPEN,
            "main_status": "pending",
            "priority": str(Bewerbung.Priority.HIGH),
            "sort": "priority",
            "created_from": received_date,
            "created_to": received_date,
        }
        first_page = self.client.get(self.list_url, filters)
        parser = LinkParser()
        parser.feed(first_page.content.decode())
        next_links = [
            link for link in parser.links if parse_qs(urlsplit(link).query).get("page") == ["2"]
        ]

        self.assertEqual(len(next_links), 1)
        self.assertEqual(
            parse_qs(urlsplit(next_links[0]).query),
            {key: [value] for key, value in (filters | {"page": "2"}).items()},
        )
        second_page = self.client.get(self.list_url + next_links[0])
        self.assertEqual(len(first_page.context["applications"]), 20)
        self.assertEqual(len(second_page.context["applications"]), 1)
        self.assertEqual(
            {item.pk for item in first_page.context["applications"]}
            | {item.pk for item in second_page.context["applications"]},
            {item.pk for item in applications},
        )

    def test_name_filter_matches_full_name_and_email(self):
        person = self.match.person
        person.vorname = "Ada"
        person.nachname = "Muster"
        person.save(update_fields=("vorname", "nachname"))

        for query in ("Ada", "Muster", "ada muster", person.email):
            with self.subTest(query=query):
                response = self.client.get(
                    self.list_url,
                    {"wohnung": self.unit.pk, "q": query},
                )
                self.assertEqual(list(response.context["applications"]), [self.match])

    def test_priority_history_displays_previous_and_new_priority(self):
        url = reverse(
            "wohnungsverwaltung:employee_application_priority_update", args=[self.match.pk]
        )
        self.client.post(url, {"priority": Bewerbung.Priority.HIGH, "reason": "Erste Prüfung"})
        self.client.post(url, {"priority": Bewerbung.Priority.LOW, "reason": "Weitere Prüfung"})

        response = self.client.get(
            reverse("wohnungsverwaltung:employee_application_detail", args=[self.match.pk])
        )
        self.assertContains(response, "Unbewertet → Hoch")
        self.assertContains(response, "Hoch → Niedrig")
        self.assertContains(response, "Erste Prüfung")
        self.assertContains(response, "Weitere Prüfung")

    def test_date_priority_and_main_status_filters_select_the_expected_applications(self):
        received_at = timezone.now() - timedelta(days=2)
        Bewerbung.objects.filter(pk=self.match.pk).update(
            created_at=received_at, review_priority=Bewerbung.Priority.HIGH
        )
        Bewerbung.objects.filter(pk=self.pet_exception.pk).update(main_application_unlocked=True)
        Bewerbung.objects.filter(pk=self.occupancy_exception.pk).update(
            main_application_unlocked=True, submitted_at=timezone.now()
        )
        received_date = timezone.localdate(received_at).isoformat()
        for filters, expected in (
            ({"created_from": received_date, "created_to": received_date}, [self.match]),
            ({"priority": str(Bewerbung.Priority.HIGH)}, [self.match]),
            ({"main_status": "pending"}, [self.match]),
            ({"main_status": "unlocked"}, [self.pet_exception]),
            ({"main_status": "submitted"}, [self.occupancy_exception]),
        ):
            with self.subTest(filters=filters):
                response = self.client.get(self.list_url, {"wohnung": self.unit.pk} | filters)
                self.assertEqual(list(response.context["applications"]), expected)

    def test_review_actions_require_employee_access_post_and_csrf(self):
        actions = (
            ("employee_application_priority_update", {"priority": 3, "reason": "Prüfung"}),
            ("employee_application_suitability_approve", {"reason": "Prüfung"}),
            (
                "employee_application_invite",
                {"confirm_positive_decision": "on", "reason": "Prüfung"},
            ),
            ("employee_application_invitation_resend", {}),
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.employee)
        for action, payload in actions:
            url = reverse(f"wohnungsverwaltung:{action}", args=[self.match.pk])
            with self.subTest(action=action):
                self.client.force_login(self.applicant_user)
                self.assertEqual(self.client.post(url, payload).status_code, 403)
                self.client.force_login(self.employee)
                self.assertEqual(self.client.get(url).status_code, 405)
                self.assertEqual(csrf_client.post(url, payload).status_code, 403)
        self.assertFalse(ApplicationReviewEvent.objects.exists())
        self.match.refresh_from_db()
        self.assertFalse(self.match.main_application_unlocked)
        self.assertEqual(self.match.review_priority, Bewerbung.Priority.UNRATED)

    def test_pet_invitation_requires_current_approval_and_repeated_unlock_is_idempotent(self):
        self.record_completed_viewing(self.pet_exception)
        self.configure_requirements()
        invite_url = reverse(
            "wohnungsverwaltung:employee_application_invite", args=[self.pet_exception.pk]
        )
        approval_url = reverse(
            "wohnungsverwaltung:employee_application_suitability_approve",
            args=[self.pet_exception.pk],
        )
        payload = {"confirm_positive_decision": "on", "reason": "Positive Prüfung"}

        self.client.post(invite_url, payload)
        self.pet_exception.refresh_from_db()
        self.assertFalse(self.pet_exception.main_application_unlocked)
        self.client.post(approval_url, {"reason": "Tierhaltung geprüft"})
        self.unit.pet_review_reason = "Geänderte Tierhaltungsregel"
        self.unit.save(update_fields=("pet_review_reason",))
        self.client.post(invite_url, payload)
        self.pet_exception.refresh_from_db()
        self.assertFalse(self.pet_exception.main_application_unlocked)
        self.assertEqual(len(mail.outbox), 0)

        self.client.post(approval_url, {"reason": "Neue Regel geprüft"})
        self.client.post(invite_url, payload)
        self.client.post(invite_url, payload)
        self.pet_exception.refresh_from_db()
        self.assertTrue(self.pet_exception.main_application_unlocked)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            ApplicationReviewEvent.objects.filter(
                application=self.pet_exception, kind=ApplicationReviewEvent.Kind.MAIN_UNLOCKED
            ).count(),
            1,
        )

    def test_priority_is_private_and_changes_are_audited(self):
        priority_url = reverse(
            "wohnungsverwaltung:employee_application_priority_update", args=[self.match.pk]
        )
        response = self.client.post(
            priority_url,
            {"priority": Bewerbung.Priority.HIGH, "reason": "Passende Raumaufteilung"},
        )
        self.assertEqual(response.status_code, 302)
        self.match.refresh_from_db()
        event = ApplicationReviewEvent.objects.get(
            application=self.match, kind=ApplicationReviewEvent.Kind.PRIORITY_CHANGED
        )
        self.assertEqual(self.match.review_priority, Bewerbung.Priority.HIGH)
        self.assertEqual(event.actor, self.employee)
        self.assertEqual(event.reason, "Passende Raumaufteilung")

        person = self.match.person
        person.user = self.applicant_user
        person.save(update_fields=["user"])
        self.client.force_login(self.applicant_user)
        response = self.client.get(reverse("wohnungsverwaltung:pre_application_list"))
        self.assertNotContains(response, "Passende Raumaufteilung")
        self.assertNotContains(response, "Hoch")

    def test_invitation_unlocks_only_selected_application_and_sends_email(self):
        self.record_completed_viewing(self.match)
        person = self.match.person
        person.user = self.applicant_user
        person.save(update_fields=["user"])
        invite_url = reverse("wohnungsverwaltung:employee_application_invite", args=[self.match.pk])
        response = self.client.post(
            invite_url,
            {
                "confirm_positive_decision": "on",
                "reason": "Besichtigung durchgeführt und positive Eignungsentscheidung",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.match.refresh_from_db()
        self.occupancy_exception.refresh_from_db()
        self.assertTrue(self.match.main_application_unlocked)
        self.assertFalse(self.occupancy_exception.main_application_unlocked)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(
            ApplicationReviewEvent.objects.filter(
                application=self.match,
                kind=ApplicationReviewEvent.Kind.INVITATION_SENT,
                actor=self.employee,
            ).exists()
        )
        self.client.force_login(self.applicant_user)
        self.assertEqual(
            self.client.get(
                reverse("wohnungsverwaltung:main_application_status", args=[self.match.pk])
            ).status_code,
            200,
        )

    def test_failed_invitation_keeps_unlock_and_can_be_resent(self):
        self.record_completed_viewing(self.match)
        self.match.person.user = self.applicant_user
        self.match.person.save(update_fields=["user"])
        invite_url = reverse("wohnungsverwaltung:employee_application_invite", args=[self.match.pk])
        with patch("wohnungsverwaltung.views.send_mail", side_effect=OSError("smtp down")):
            self.client.post(
                invite_url,
                {
                    "confirm_positive_decision": "on",
                    "reason": "Positive Entscheidung nach persönlicher Prüfung",
                },
            )
        self.match.refresh_from_db()
        self.assertTrue(self.match.main_application_unlocked)
        self.assertTrue(
            ApplicationReviewEvent.objects.filter(
                application=self.match,
                kind=ApplicationReviewEvent.Kind.INVITATION_FAILED,
            ).exists()
        )
        dashboard_response = self.client.get(
            self.list_url,
            {"wohnung": self.unit.pk, "segment": "all"},
        )
        self.assertContains(dashboard_response, "Einladung fehlgeschlagen")
        resend_url = reverse(
            "wohnungsverwaltung:employee_application_invitation_resend", args=[self.match.pk]
        )
        with patch("wohnungsverwaltung.views.send_mail", return_value=1) as send_mail_mock:
            response = self.client.post(resend_url)
        self.assertEqual(response.status_code, 302)
        send_mail_mock.assert_called_once()
        self.assertTrue(
            ApplicationReviewEvent.objects.filter(
                application=self.match,
                kind=ApplicationReviewEvent.Kind.INVITATION_SENT,
            ).exists()
        )
        dashboard_response = self.client.get(
            self.list_url,
            {"wohnung": self.unit.pk, "segment": "all"},
        )
        self.assertContains(dashboard_response, "Einladung versendet")
        self.assertNotContains(dashboard_response, "Einladung fehlgeschlagen")

    def test_empty_reasons_and_get_requests_cannot_change_review_state(self):
        self.configure_requirements()
        priority_url = reverse(
            "wohnungsverwaltung:employee_application_priority_update", args=[self.match.pk]
        )
        response = self.client.get(priority_url)
        self.assertEqual(response.status_code, 405)
        response = self.client.post(
            priority_url,
            {"priority": Bewerbung.Priority.HIGH, "reason": "   "},
        )
        self.assertEqual(response.status_code, 302)
        self.match.refresh_from_db()
        self.assertEqual(self.match.review_priority, Bewerbung.Priority.UNRATED)
        self.assertFalse(ApplicationReviewEvent.objects.filter(application=self.match).exists())
