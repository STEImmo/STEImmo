from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from .access import ROLE_APPLICANT, ROLE_EMPLOYEE, ROLE_TENANT
from .models import Bewerbung, Person, Wohnung


class RentalCompletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.employee = users.create_user("employee@example.test")
        cls.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        cls.applicant = users.create_user("applicant@example.test")
        cls.applicant.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        cls.other = users.create_user("other@example.test")
        cls.other.groups.add(Group.objects.get(name=ROLE_TENANT))
        cls.person = Person.objects.create(
            user=cls.applicant, vorname="Test", nachname="Person", email="applicant@example.test"
        )
        cls.unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="14")
        cls.application = Bewerbung.objects.create(
            person=cls.person,
            wohnung=cls.unit,
            submitted_at=timezone.now(),
            accepted_at=timezone.now(),
            main_application_unlocked=True,
        )

    @property
    def completion_url(self):
        return reverse("wohnungsverwaltung:employee_rental_complete", args=[self.application.pk])

    @property
    def contract_url(self):
        return reverse("wohnungsverwaltung:tenant_rental_contract", args=[self.application.pk])

    @staticmethod
    def pdf_bytes():
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        data = BytesIO()
        writer.write(data)
        return data.getvalue()

    def complete(self, *, contract=None, account=None, follow=True):
        account = self.applicant.pk if account is None else account
        contract = self.pdf_bytes() if contract is None else contract
        page = self.client.get(
            reverse("wohnungsverwaltung:employee_application_detail", args=[self.application.pk])
        )
        return self.client.post(
            self.completion_url,
            {
                "account": account,
                "assignment_confirmation": page.context["rental_form"][
                    "assignment_confirmation"
                ].value(),
                "contract": SimpleUploadedFile("vertrag.pdf", contract, "application/pdf"),
            },
            follow=follow,
        )

    def test_employee_completes_rental_and_tenant_downloads_contract_after_login(self):
        self.client.force_login(self.employee)
        detail = reverse(
            "wohnungsverwaltung:employee_application_detail", args=[self.application.pk]
        )
        self.assertContains(self.client.get(detail), "Vermietung abschließen")
        data = self.pdf_bytes()
        self.assertContains(self.complete(contract=data), "Vermietung abgeschlossen")
        self.person.refresh_from_db()
        self.assertEqual(self.person.wohnung_id, self.unit.pk)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, self.application.wohnung.status)
        self.assertTrue(self.applicant.groups.filter(name=ROLE_APPLICANT).exists())
        self.assertTrue(self.applicant.groups.filter(name=ROLE_TENANT).exists())
        self.client.logout()
        self.client.force_login(self.applicant)
        profile = self.client.get(reverse("profile:detail"))
        self.assertContains(profile, str(self.unit))
        self.assertContains(profile, self.contract_url)
        download = self.client.get(self.contract_url)
        try:
            self.assertEqual(download.status_code, 200)
            self.assertEqual(download["Content-Type"], "application/pdf")
            self.assertIn("attachment", download["Content-Disposition"])
            self.assertIn("no-store", download["Cache-Control"])
            self.assertEqual(b"".join(download.streaming_content), data)
        finally:
            if not download.closed:
                download.close()

    def test_repeated_completion_keeps_original_contract(self):
        self.client.force_login(self.employee)
        original = self.pdf_bytes()
        self.assertContains(self.complete(contract=original), "Vermietung abgeschlossen")
        self.assertContains(self.complete(contract=b"invalid"), "bereits abgeschlossen")
        self.application.refresh_from_db()
        self.assertEqual(bytes(self.application.rental.contract_pdf), original)

    def test_completed_rental_leaves_open_workflow_but_stays_in_application_history(self):
        self.client.force_login(self.employee)
        listing = reverse("wohnungsverwaltung:employee_application_list")
        detail = reverse(
            "wohnungsverwaltung:employee_application_detail", args=[self.application.pk]
        )
        query = {"wohnung": str(self.unit.pk), "workflow": "open"}
        self.assertContains(self.client.get(listing, query), detail)
        self.complete()
        self.assertNotContains(self.client.get(listing, query), detail)
        self.assertContains(self.client.get(listing, {"wohnung": str(self.unit.pk)}), detail)

    def test_other_tenant_and_staff_cannot_download_private_contract(self):
        self.client.force_login(self.employee)
        self.complete()
        self.assertEqual(self.client.get(self.contract_url).status_code, 403)
        self.client.force_login(self.other)
        profile = self.client.get(reverse("profile:detail"))
        self.assertNotContains(profile, self.contract_url)
        self.assertNotContains(profile, str(self.unit))
        self.assertEqual(self.client.get(self.contract_url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.contract_url).status_code, 302)

    def test_relinking_person_does_not_transfer_the_existing_contract(self):
        self.client.force_login(self.employee)
        self.complete()
        Person.objects.filter(pk=self.person.pk).update(user=self.other)
        for user in (self.applicant, self.other):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.contract_url).status_code, 404)

    def test_invalid_upload_and_stale_account_leave_no_assignment(self):
        self.client.force_login(self.employee)
        self.assertEqual(self.complete(contract=b"invalid", follow=False).status_code, 400)
        self.assertEqual(
            self.complete(contract=b"x" * (6 * 1024 * 1024), follow=False).status_code, 413
        )
        self.assertContains(self.complete(account=self.other.pk), "Benutzerkonto")
        self.person.refresh_from_db()
        self.assertIsNone(self.person.wohnung_id)
        self.assertFalse(self.applicant.groups.filter(name=ROLE_TENANT).exists())
        self.assertFalse(hasattr(self.application, "rental"))

    def test_second_accepted_application_cannot_replace_a_completed_rental(self):
        self.client.force_login(self.employee)
        data = self.pdf_bytes()
        self.assertContains(self.complete(contract=data), "Vermietung abgeschlossen")
        first = self.application
        other_person = Person.objects.create(
            user=self.other, vorname="Test", nachname="Zwei", email="other@example.test"
        )
        self.application = Bewerbung.objects.create(
            person=other_person,
            wohnung=self.unit,
            submitted_at=timezone.now(),
            accepted_at=timezone.now(),
        )
        self.assertContains(self.complete(account=self.other.pk), "bereits eine Vermietung")
        self.assertEqual(bytes(first.rental.contract_pdf), data)
        other_person.refresh_from_db()
        self.assertIsNone(other_person.wohnung_id)

    def test_unaccepted_application_cannot_be_completed(self):
        Bewerbung.objects.filter(pk=self.application.pk).update(accepted_at=None)
        self.client.force_login(self.employee)
        self.assertContains(self.complete(), "angenommene Bewerbung")
        self.person.refresh_from_db()
        self.assertIsNone(self.person.wohnung_id)

    def test_failed_assignment_rolls_back_contract_and_role(self):
        self.client.force_login(self.employee)
        with patch.object(Person, "save", side_effect=RuntimeError("simulierter Fehler")):
            with self.assertRaises(RuntimeError):
                self.complete()
        self.person.refresh_from_db()
        self.assertIsNone(self.person.wohnung_id)
        self.assertFalse(hasattr(self.application, "rental"))
        self.assertFalse(self.applicant.groups.filter(name=ROLE_TENANT).exists())

    def test_completion_requires_employee_and_post_with_csrf(self):
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.post(self.completion_url).status_code, 403)
        employee = Client(enforce_csrf_checks=True)
        employee.force_login(self.employee)
        self.assertEqual(employee.get(self.completion_url).status_code, 405)
        self.assertEqual(employee.post(self.completion_url).status_code, 403)
