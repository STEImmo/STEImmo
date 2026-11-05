"""Ergänzende Zugriffsmatrix für aktuelle und ältere Bewerbungsnachweise (#140)."""

from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.fields.files import FieldFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from .access import ROLE_APPLICANT, ROLE_EMPLOYEE, ROLE_TENANT
from .models import (
    ApplicationProof,
    ApplicationProofCategory,
    Bewerbung,
    BewerbungStatus,
    Person,
    Wohnung,
)


class ApplicationDocumentAccessTests(TestCase):
    document_types = (
        ("income_proof", ApplicationProofCategory.INCOME),
        ("identity_proof", ApplicationProofCategory.IDENTITY),
        ("credit_report_proof", ApplicationProofCategory.CREDIT_REPORT),
    )

    def setUp(self):
        media_root = self.enterContext(TemporaryDirectory())
        self.enterContext(self.settings(MEDIA_ROOT=media_root))
        self.applicant = self.create_user("owner", ROLE_APPLICANT)
        self.foreign_applicant = self.create_user("foreign", ROLE_APPLICANT)
        self.employee = self.create_user("employee", ROLE_EMPLOYEE)
        self.tenant = self.create_user("tenant", ROLE_TENANT)
        self.unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="access-test")
        self.expected_contents = {}
        self.application, self.proofs = self.create_application(self.applicant)
        self.foreign_application, self.foreign_proofs = self.create_application(
            self.foreign_applicant
        )

    @staticmethod
    def create_user(name, role):
        user = get_user_model().objects.create_user(username=f"{name}@example.test")
        user.groups.add(Group.objects.get(name=role))
        Person.objects.create(user=user, vorname="Test", nachname=name, email=user.username)
        return user

    @staticmethod
    def pdf_contents(label: str) -> bytes:
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.add_metadata({"/Title": f"Fiktiver Nachweis: {label}"})
        output = BytesIO()
        writer.write(output)
        return output.getvalue()

    def create_application(self, user):
        application = Bewerbung.objects.create(
            person=user.person_profile,
            wohnung=self.unit,
            personenanzahl=1,
            main_application_unlocked=True,
            submitted_at=timezone.now(),
        )
        proofs = []
        for document_type, category in self.document_types:
            legacy_contents = self.pdf_contents(f"{user.username}: {document_type}: legacy")
            proof_contents = self.pdf_contents(f"{user.username}: {category}: current")
            getattr(application, document_type).save(
                "legacy.pdf", SimpleUploadedFile("legacy.pdf", legacy_contents), save=False
            )
            proof = ApplicationProof.objects.create(
                application=application,
                category=category,
                original_name="fiktiver-nachweis.pdf",
                file=SimpleUploadedFile("proof.pdf", proof_contents),
            )
            proofs.append(proof)
            for area in ("applicant", "employee"):
                legacy_url = reverse(
                    f"wohnungsverwaltung:{area}_application_document",
                    args=[application.pk, document_type],
                )
                proof_url = reverse(
                    f"wohnungsverwaltung:{area}_application_proof_download",
                    args=[application.pk, proof.pk],
                )
                self.expected_contents[legacy_url] = legacy_contents
                self.expected_contents[proof_url] = proof_contents
        application.save()
        return application, proofs

    def download_urls(self, area, application=None, proofs=None):
        application = self.application if application is None else application
        proofs = self.proofs if proofs is None else proofs
        return [
            reverse(
                f"wohnungsverwaltung:{area}_application_document",
                args=[application.pk, document_type],
            )
            for document_type, _category in self.document_types
        ] + [
            reverse(
                f"wohnungsverwaltung:{area}_application_proof_download",
                args=[application.pk, proof.pk],
            )
            for proof in proofs
        ]

    def assert_downloads(self, urls):
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        b"".join(response.streaming_content), self.expected_contents[url]
                    )
                    self.assertEqual(response["Cache-Control"], "private, no-store")
                    self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                    self.assertEqual(response["Content-Type"], "application/octet-stream")
                    self.assertIn("attachment;", response["Content-Disposition"])
                finally:
                    if not response.closed:
                        response.close()

    def assert_denied(self, urls, status):
        # A refusal must happen before any private file is opened.
        with patch.object(FieldFile, "open", side_effect=AssertionError("Private Datei geöffnet")):
            for url in urls:
                with self.subTest(url=url):
                    response = self.client.get(url)
                    try:
                        self.assertEqual(response.status_code, status)
                        self.assertFalse(response.streaming)
                        self.assertNotContains(response, "Fiktiver Nachweis", status_code=status)
                        if status == 302:
                            self.assertRedirects(
                                response,
                                f"{reverse('login')}?next={url}",
                                fetch_redirect_response=False,
                            )
                    finally:
                        if not response.closed:
                            response.close()

    def test_anonymous_and_tenant_only_accounts_cannot_download_any_application_document(self):
        urls = self.download_urls("applicant") + self.download_urls("employee")
        self.assert_denied(urls, 302)
        self.client.force_login(self.tenant)
        self.assert_denied(urls, 403)

    def test_foreign_applicant_cannot_download_any_of_the_owners_documents(self):
        self.client.force_login(self.foreign_applicant)
        self.assert_denied(self.download_urls("applicant"), 404)
        self.assert_denied(self.download_urls("employee"), 403)

    def test_owner_and_employee_can_download_all_three_legacy_and_current_categories(self):
        for user, area in ((self.applicant, "applicant"), (self.employee, "employee")):
            with self.subTest(area=area):
                self.client.force_login(user)
                self.assert_downloads(self.download_urls(area))

    def test_tenant_with_retained_applicant_role_can_download_only_their_own_documents(self):
        self.applicant.groups.add(Group.objects.get(name=ROLE_TENANT))
        self.client.force_login(self.applicant)
        self.assert_downloads(self.download_urls("applicant"))
        self.assert_denied(
            self.download_urls("applicant", self.foreign_application, self.foreign_proofs), 404
        )
        self.assert_denied(self.download_urls("employee"), 403)

    def test_applicant_cannot_combine_own_application_with_foreign_proof_ids(self):
        self.client.force_login(self.applicant)
        urls = self.download_urls("applicant", proofs=self.foreign_proofs)[3:]
        urls += self.download_urls("applicant", self.foreign_application, self.proofs)[3:]
        self.assert_denied(urls, 404)

    def test_unlocked_draft_legacy_documents_are_available_only_to_the_owner(self):
        self.application.submitted_at = None
        self.application.save(update_fields=["submitted_at"])
        self.client.force_login(self.applicant)
        self.assert_downloads(self.download_urls("applicant")[:3])
        self.client.force_login(self.employee)
        self.assert_denied(self.download_urls("employee")[:3], 404)

    def test_owner_cannot_download_legacy_or_current_documents_in_ineligible_states(self):
        self.client.force_login(self.applicant)
        states = (
            {"main_application_unlocked": False},
            {"interest_withdrawn_at": timezone.now()},
            {"status": BewerbungStatus.DECLINED},
            {"status": BewerbungStatus.BLOCKED},
        )
        for state in states:
            with self.subTest(state=state):
                Bewerbung.objects.filter(pk=self.application.pk).update(
                    main_application_unlocked=True,
                    interest_withdrawn_at=None,
                    status=BewerbungStatus.OPEN,
                )
                Bewerbung.objects.filter(pk=self.application.pk).update(**state)
                self.assert_denied(self.download_urls("applicant"), 404)

    def test_employee_retains_legacy_download_access_after_review_or_withdrawal(self):
        self.client.force_login(self.employee)
        for status, withdrawn in (
            (BewerbungStatus.DECLINED, None),
            (BewerbungStatus.BLOCKED, None),
            (BewerbungStatus.OPEN, timezone.now()),
        ):
            with self.subTest(status=status, withdrawn=withdrawn):
                Bewerbung.objects.filter(pk=self.application.pk).update(
                    status=status, interest_withdrawn_at=withdrawn, main_application_unlocked=False
                )
                self.assert_downloads(self.download_urls("employee")[:3])

    def test_deactivation_blocks_all_document_downloads_in_an_existing_session(self):
        for user, area in ((self.applicant, "applicant"), (self.employee, "employee")):
            with self.subTest(area=area):
                self.client.force_login(user)
                self.assert_downloads(self.download_urls(area))
                user.is_active = False
                user.save(update_fields=["is_active"])
                self.assert_denied(self.download_urls(area), 302)

    def test_role_removal_blocks_all_document_downloads_in_an_existing_session(self):
        for user, area in ((self.applicant, "applicant"), (self.employee, "employee")):
            with self.subTest(area=area):
                self.client.force_login(user)
                self.assert_downloads(self.download_urls(area))
                user.groups.clear()
                self.assert_denied(self.download_urls(area), 403)

    def test_direct_permissions_allow_downloads_and_their_removal_takes_effect_immediately(self):
        for user, area, codename in (
            (self.applicant, "applicant", "access_applicant_area"),
            (self.employee, "employee", "access_employee_area"),
        ):
            with self.subTest(area=area):
                permission = Permission.objects.get(
                    content_type__app_label="immobilien", codename=codename
                )
                user.groups.clear()
                user.user_permissions.add(permission)
                self.client.force_login(user)
                self.assert_downloads(self.download_urls(area))
                user.user_permissions.clear()
                self.assert_denied(self.download_urls(area), 403)

    def test_missing_person_link_prevents_applicant_document_access(self):
        person = self.applicant.person_profile
        person.user = None
        person.save(update_fields=["user"])
        self.client.force_login(self.applicant)
        self.assert_denied(self.download_urls("applicant"), 403)

    def test_unknown_application_and_proof_ids_return_not_found(self):
        for user, area in ((self.applicant, "applicant"), (self.employee, "employee")):
            with self.subTest(area=area):
                self.client.force_login(user)
                unknown_application = Bewerbung(pk=uuid4())
                unknown_proof = ApplicationProof(proof_id=uuid4())
                self.assert_denied(self.download_urls(area, unknown_application), 404)
                self.assert_denied(self.download_urls(area, proofs=[unknown_proof])[3:], 404)

    def test_applicant_legacy_document_type_cannot_select_arbitrary_model_fields(self):
        self.client.force_login(self.applicant)
        urls = [
            reverse(
                "wohnungsverwaltung:applicant_application_document",
                args=[self.application.pk, document_type],
            )
            for document_type in ("ueber_mich", "identity_proof_original_name", "__dict__")
        ]
        self.assert_denied(urls, 404)
