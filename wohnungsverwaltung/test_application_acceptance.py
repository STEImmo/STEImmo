from io import BytesIO
from smtplib import SMTPException
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from .access import ROLE_APPLICANT, ROLE_EMPLOYEE
from .models import ApplicationReviewEvent, Bewerbung, BewerbungStatus, Person, Wohnung


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ApplicationAcceptanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = get_user_model().objects.create_user("employee@example.test")
        cls.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        cls.applicant = get_user_model().objects.create_user("login@example.test")
        cls.applicant.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        cls.person = Person.objects.create(
            user=cls.applicant, vorname="Test", nachname="Person", email="recipient@example.test"
        )
        cls.application = Bewerbung.objects.create(
            person=cls.person,
            wohnung=Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="04"),
            main_application_unlocked=True,
            submitted_at=timezone.now(),
        )

    def url(self, action):
        return reverse(
            f"wohnungsverwaltung:employee_application_{action}", args=[self.application.pk]
        )

    @staticmethod
    def pdf():
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        data = BytesIO()
        writer.write(data)
        return SimpleUploadedFile("contract.pdf", data.getvalue(), "application/pdf")

    def accept(self):
        response = self.client.post(self.url("accept"), follow=True)
        self.assertContains(response, "Bewerbung angenommen")
        self.application.refresh_from_db()
        self.assertIsNotNone(self.application.accepted_at)

    def test_employee_can_accept_once_and_see_acceptance_again(self):
        self.client.force_login(self.employee)
        self.assertContains(self.client.get(self.url("detail")), "Bewerbung annehmen")
        self.accept()
        accepted_at = self.application.accepted_at
        self.accept()
        self.assertEqual(self.application.accepted_at, accepted_at)
        self.assertEqual(
            self.application.review_events.filter(
                kind=ApplicationReviewEvent.Kind.ACCEPTED
            ).count(),
            1,
        )
        self.client.logout()
        self.client.force_login(self.employee)
        self.assertContains(self.client.get(self.url("detail")), "Bewerbung angenommen")

    def test_contract_goes_only_to_the_application_recipient(self):
        self.client.force_login(self.employee)
        self.accept()
        contract = self.pdf()
        contents = contract.read()
        contract.seek(0)
        response = self.client.post(
            self.url("send_contract"),
            {"contract": contract, "recipient": "wrong@example.test"},
            follow=True,
        )
        self.assertContains(response, "Mietvertrag wurde zum Versand übergeben")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.person.email])
        self.assertEqual(message.attachments, [("Mietvertrag.pdf", contents, "application/pdf")])
        self.assertTrue(
            self.application.review_events.filter(
                kind=ApplicationReviewEvent.Kind.CONTRACT_SENT
            ).exists()
        )

    def test_failed_delivery_does_not_report_success_and_can_be_retried(self):
        self.client.force_login(self.employee)
        self.accept()
        for failure in ({"side_effect": SMTPException}, {"return_value": 0}):
            with (
                self.subTest(failure=failure),
                patch("django.core.mail.EmailMessage.send", **failure),
            ):
                response = self.client.post(
                    self.url("send_contract"), {"contract": self.pdf()}, follow=True
                )
                self.assertContains(response, "Der Mietvertrag konnte nicht versendet werden")
                self.assertNotContains(response, "Mietvertrag wurde zum Versand übergeben")
        self.assertEqual(
            self.application.review_events.filter(
                kind=ApplicationReviewEvent.Kind.CONTRACT_FAILED
            ).count(),
            2,
        )
        self.assertFalse(
            self.application.review_events.filter(
                kind=ApplicationReviewEvent.Kind.CONTRACT_SENT
            ).exists()
        )
        response = self.client.post(
            self.url("send_contract"), {"contract": self.pdf()}, follow=True
        )
        self.assertContains(response, "Mietvertrag wurde zum Versand übergeben")

    def test_console_file_and_dummy_backends_do_not_receive_contracts(self):
        self.client.force_login(self.employee)
        self.accept()
        for backend in ("console", "filebased", "dummy"):
            with (
                self.subTest(backend=backend),
                self.settings(EMAIL_BACKEND=f"django.core.mail.backends.{backend}.EmailBackend"),
                patch("django.core.mail.EmailMessage.send") as send,
            ):
                response = self.client.post(
                    self.url("send_contract"), {"contract": self.pdf()}, follow=True
                )
                self.assertContains(response, "Der E-Mail-Versand für Mietverträge ist nicht aktiv")
                send.assert_not_called()

    def test_unsubmitted_closed_and_withdrawn_applications_cannot_be_accepted(self):
        self.client.force_login(self.employee)
        for fields in (
            {"submitted_at": None},
            {"status": BewerbungStatus.DECLINED},
            {"interest_withdrawn_at": timezone.now()},
        ):
            with self.subTest(fields=fields):
                Bewerbung.objects.filter(pk=self.application.pk).update(
                    **(
                        {
                            "submitted_at": timezone.now(),
                            "status": BewerbungStatus.OPEN,
                            "interest_withdrawn_at": None,
                        }
                        | fields
                    )
                )
                response = self.client.post(self.url("accept"), follow=True)
                self.assertContains(response, "kann nicht angenommen werden")
                self.application.refresh_from_db()
                self.assertIsNone(self.application.accepted_at)

    def test_contract_requires_an_active_acceptance_and_a_valid_pdf(self):
        self.client.force_login(self.employee)
        response = self.client.post(
            self.url("send_contract"), {"contract": self.pdf()}, follow=True
        )
        self.assertContains(response, "Versand ist nur für eine angenommene Bewerbung möglich")
        self.accept()
        for upload in (
            SimpleUploadedFile("invalid.pdf", b"%PDF-1.7\n%%EOF", "application/pdf"),
            SimpleUploadedFile("large.pdf", b"x" * (5 * 1024 * 1024 + 1), "application/pdf"),
        ):
            with self.subTest(upload=upload.name):
                response = self.client.post(self.url("send_contract"), {"contract": upload})
                self.assertEqual(response.status_code, 400)
        Bewerbung.objects.filter(pk=self.application.pk).update(
            interest_withdrawn_at=timezone.now()
        )
        response = self.client.post(
            self.url("send_contract"), {"contract": self.pdf()}, follow=True
        )
        self.assertContains(response, "Versand ist nur für eine angenommene Bewerbung möglich")
        self.assertEqual(mail.outbox, [])

    def test_actions_require_employee_and_post_with_csrf(self):
        for action in ("accept", "send_contract"):
            with self.subTest(action=action):
                url = self.url(action)
                self.client.logout()
                self.assertEqual(self.client.post(url).status_code, 302)
                self.client.force_login(self.applicant)
                self.assertEqual(self.client.post(url).status_code, 403)
                employee_client = Client(enforce_csrf_checks=True)
                employee_client.force_login(self.employee)
                self.assertEqual(employee_client.get(url).status_code, 405)
                self.assertEqual(employee_client.post(url).status_code, 403)
