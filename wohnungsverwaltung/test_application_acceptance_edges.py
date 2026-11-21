from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from pypdf import PdfWriter

from . import test_application_acceptance
from .access import ROLE_EMPLOYEE, ROLE_TENANT
from .forms import RentalContractForm
from .models import ApplicationReviewEvent, Bewerbung, BewerbungStatus, Person


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ApplicationAcceptanceEdgeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_application_acceptance.ApplicationAcceptanceTests.setUpTestData.__func__(cls)

    url = test_application_acceptance.ApplicationAcceptanceTests.url
    pdf = staticmethod(test_application_acceptance.ApplicationAcceptanceTests.pdf)
    accept = test_application_acceptance.ApplicationAcceptanceTests.accept
    contract_data = test_application_acceptance.ApplicationAcceptanceTests.contract_data

    def setUp(self):
        self.client.force_login(self.employee)
        self.accept()

    def test_encrypted_empty_and_disguised_non_pdf_files_never_reach_mail_backend(self):
        encrypted = PdfWriter()
        encrypted.add_blank_page(width=100, height=100)
        encrypted.encrypt("synthetic-password")
        encrypted_bytes = BytesIO()
        encrypted.write(encrypted_bytes)
        empty = BytesIO()
        PdfWriter().write(empty)
        for contents in (
            b"",
            b"<html>not a PDF</html>",
            b"%PDF-1.7\nnot a real PDF",
            encrypted_bytes.getvalue(),
            empty.getvalue(),
        ):
            with (
                self.subTest(size=len(contents)),
                patch("django.core.mail.EmailMessage.send") as send,
            ):
                response = self.client.post(
                    self.url("send_contract"),
                    self.contract_data(
                        contract=SimpleUploadedFile("fake.pdf", contents, "application/pdf")
                    ),
                )
                self.assertEqual(response.status_code, 400)
                send.assert_not_called()
        self.assertFalse(self.application.review_events.filter(kind="contract_sent").exists())

    @staticmethod
    def sized_pdf(size):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        padding = size
        for _ in range(4):
            writer.add_metadata({"/Padding": "x" * padding})
            output = BytesIO()
            writer.write(output)
            contents = output.getvalue()
            if len(contents) == size:
                return SimpleUploadedFile("boundary.pdf", contents, "application/pdf")
            padding += size - len(contents)
        raise AssertionError("Could not construct exact-size synthetic PDF")

    def test_real_pdf_at_five_mib_is_accepted_and_one_byte_over_is_rejected(self):
        limit = 5 * 1024 * 1024
        with patch("django.core.mail.EmailMessage.send") as send:
            response = self.client.post(
                self.url("send_contract"), self.contract_data(contract=self.sized_pdf(limit + 1))
            )
            self.assertEqual(response.status_code, 400)
            send.assert_not_called()
        response = self.client.post(
            self.url("send_contract"), self.contract_data(contract=self.sized_pdf(limit))
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(mail.outbox[0].attachments[0].content), limit)

    def test_original_filename_and_mime_type_cannot_control_the_attachment(self):
        contents = self.pdf().read()
        response = self.client.post(
            self.url("send_contract"),
            self.contract_data(
                contract=SimpleUploadedFile("../../misleading.html", contents, "text/html")
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            mail.outbox[0].attachments, [("Mietvertrag.pdf", contents, "application/pdf")]
        )

    def test_withdrawal_rejection_or_removed_acceptance_during_validation_stops_delivery(self):
        original_clean = RentalContractForm.clean_contract
        for changes in (
            {"status": BewerbungStatus.DECLINED},
            {"submitted_at": None},
            {"accepted_at": None},
            {"interest_withdrawn_at": self.application.accepted_at},
        ):
            with self.subTest(changes=changes), transaction.atomic():
                data = self.contract_data()

                def change_application(form):
                    upload = original_clean(form)
                    Bewerbung.objects.filter(pk=self.application.pk).update(**changes)
                    return upload

                with patch.object(RentalContractForm, "clean_contract", change_application):
                    response = self.client.post(self.url("send_contract"), data, follow=True)
                self.assertContains(response, "nur für eine angenommene Bewerbung")
                self.assertEqual(mail.outbox, [])
                transaction.set_rollback(True)

    def test_revoked_role_account_session_or_credentials_during_validation_stops_delivery(self):
        original_clean = RentalContractForm.clean_contract
        for revoke in ("role", "account", "session", "credentials"):
            with self.subTest(revoke=revoke), transaction.atomic():
                self.client.force_login(self.employee)
                data = self.contract_data()

                def revoke_access(form):
                    upload = original_clean(form)
                    if revoke == "role":
                        self.employee.groups.clear()
                    elif revoke == "account":
                        get_user_model().objects.filter(pk=self.employee.pk).update(is_active=False)
                    elif revoke == "session":
                        Session.objects.filter(session_key=self.client.session.session_key).delete()
                    else:
                        get_user_model().objects.filter(pk=self.employee.pk).update(
                            password="!revoked"
                        )
                    return upload

                with patch.object(RentalContractForm, "clean_contract", revoke_access):
                    self.assertEqual(
                        self.client.post(self.url("send_contract"), data).status_code, 403
                    )
                self.assertEqual(mail.outbox, [])
                transaction.set_rollback(True)

    def test_invalid_pdf_does_not_silently_replace_a_stale_recipient_confirmation(self):
        data = self.contract_data(
            contract=SimpleUploadedFile("bad.pdf", b"not-pdf", "application/pdf")
        )
        Person.objects.filter(pk=self.person.pk).update(email="new@example.test")
        invalid = self.client.post(self.url("send_contract"), data)
        self.assertEqual(invalid.status_code, 400)
        self.assertContains(invalid, "new@example.test", status_code=400)
        retry = self.contract_data(invalid)
        self.assertEqual(self.client.post(self.url("send_contract"), retry).status_code, 409)
        self.assertEqual(mail.outbox, [])

    def test_invalid_stored_recipient_never_reaches_mail_backend_or_reports_success(self):
        Person.objects.filter(pk=self.person.pk).update(email="invalid\r\nBcc: other@example.test")
        with patch("django.core.mail.EmailMessage.send") as send:
            response = self.client.post(
                self.url("send_contract"), self.contract_data(), follow=True
            )
        self.assertContains(response, "konnte nicht versendet werden")
        self.assertNotContains(response, "Mietvertrag wurde zum Versand übergeben")
        send.assert_not_called()
        self.assertTrue(self.application.review_events.filter(kind="contract_failed").exists())

    def test_smtp_timeout_reports_failure_without_disclosing_exception_details(self):
        with patch(
            "django.core.mail.EmailMessage.send",
            side_effect=TimeoutError("private-smtp-detail-canary"),
        ):
            response = self.client.post(
                self.url("send_contract"), self.contract_data(), follow=True
            )
        self.assertContains(response, "konnte nicht versendet werden")
        self.assertNotContains(response, "private-smtp-detail-canary")
        self.assertNotContains(response, "Mietvertrag wurde zum Versand übergeben")
        self.assertTrue(self.application.review_events.filter(kind="contract_failed").exists())
        self.assertEqual(mail.outbox, [])

    def test_revoked_direct_employee_permission_also_stops_delivery(self):
        from django.contrib.auth.models import Permission

        self.employee.groups.clear()
        self.employee.user_permissions.add(Permission.objects.get(codename="access_employee_area"))
        self.client.force_login(self.employee)
        data = self.contract_data()
        original_clean = RentalContractForm.clean_contract

        def revoke_direct_permission(form):
            upload = original_clean(form)
            self.employee.user_permissions.clear()
            return upload

        with patch.object(RentalContractForm, "clean_contract", revoke_direct_permission):
            self.assertEqual(self.client.post(self.url("send_contract"), data).status_code, 403)
        self.assertEqual(mail.outbox, [])

    def test_csrf_protected_submission_works_with_the_token_from_the_actual_form(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.employee)
        page = csrf_client.get(self.url("detail"))
        data = self.contract_data(page)
        self.assertEqual(csrf_client.post(self.url("send_contract"), data).status_code, 403)
        data = self.contract_data(page)
        data["csrfmiddlewaretoken"] = csrf_client.cookies["csrftoken"].value
        self.assertEqual(csrf_client.post(self.url("send_contract"), data).status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

    def test_unknown_application_ids_have_no_effect(self):
        for action in ("accept", "send_contract"):
            response = self.client.post(
                reverse(f"wohnungsverwaltung:employee_application_{action}", args=[uuid4()])
            )
            self.assertEqual(response.status_code, 404)
        self.assertEqual(mail.outbox, [])

    def test_inactive_employee_and_tenant_cannot_use_a_previously_authorized_form(self):
        data = self.contract_data()
        get_user_model().objects.filter(pk=self.employee.pk).update(is_active=False)
        self.assertEqual(self.client.post(self.url("send_contract"), data).status_code, 302)
        tenant = get_user_model().objects.create_user("tenant@example.test")
        tenant.groups.add(Group.objects.get(name=ROLE_TENANT))
        self.client.force_login(tenant)
        self.assertEqual(
            self.client.post(
                self.url("send_contract"),
                {"contract": self.pdf(), "recipient_confirmation": data["recipient_confirmation"]},
            ).status_code,
            403,
        )
        self.assertEqual(mail.outbox, [])

    def test_explicit_repeated_send_is_a_new_attempt_and_does_not_repeat_acceptance(self):
        for _ in range(2):
            self.assertEqual(
                self.client.post(self.url("send_contract"), self.contract_data()).status_code, 302
            )
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(self.application.review_events.filter(kind="accepted").count(), 1)
        self.assertEqual(self.application.review_events.filter(kind="contract_sent").count(), 2)


class ConcurrentApplicationAcceptanceTests(TransactionTestCase):
    def setUp(self):
        test_application_acceptance.ApplicationAcceptanceTests.setUpTestData.__func__(type(self))

    def test_two_employees_accepting_the_same_application_create_one_acceptance(self):
        clients = [Client(), Client()]
        second = get_user_model().objects.create_user("second-employee@example.test")
        second.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        for client, employee in zip(clients, (self.employee, second), strict=True):
            client.force_login(employee)
        barrier = Barrier(2, timeout=10)
        url = reverse("wohnungsverwaltung:employee_application_accept", args=[self.application.pk])

        def accept(client):
            close_old_connections()
            try:
                barrier.wait()
                return client.post(url).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(accept, client) for client in clients]
            self.assertEqual([future.result(timeout=15) for future in futures], [302, 302])
        self.application.refresh_from_db()
        self.assertIsNotNone(self.application.accepted_at)
        self.assertEqual(
            ApplicationReviewEvent.objects.filter(
                application=self.application, kind="accepted"
            ).count(),
            1,
        )
