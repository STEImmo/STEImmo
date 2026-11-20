from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from . import test_handover_export, test_rental_completion
from .access import ROLE_EMPLOYEE, ROLE_TENANT
from .forms import RentalCompletionForm
from .models import Bewerbung, Person, Rental, Wohnung


class RentalCompletionEdgeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        test_rental_completion.RentalCompletionTests.setUpTestData.__func__(cls)

    completion_url = test_rental_completion.RentalCompletionTests.completion_url
    contract_url = test_rental_completion.RentalCompletionTests.contract_url
    pdf_bytes = staticmethod(test_rental_completion.RentalCompletionTests.pdf_bytes)

    def setUp(self):
        self.client.force_login(self.employee)

    def completion_data(self, *, application=None, client=None):
        application = application or self.application
        client = client or self.client
        page = client.get(
            reverse("wohnungsverwaltung:employee_application_detail", args=[application.pk])
        )
        form = page.context["rental_form"]
        return {
            "account": application.person.user_id or self.applicant.pk,
            "assignment_confirmation": form["assignment_confirmation"].value(),
            "contract": SimpleUploadedFile("contract.pdf", self.pdf_bytes(), "application/pdf"),
        }

    def assert_no_completion(self):
        self.assertFalse(Rental.objects.exists())
        self.person.refresh_from_db()
        self.assertIsNone(self.person.wohnung_id)
        self.assertFalse(self.applicant.groups.filter(name=ROLE_TENANT).exists())

    def test_changed_unit_requires_new_confirmation_before_completion(self):
        data = self.completion_data()
        other_unit = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="15")
        Bewerbung.objects.filter(pk=self.application.pk).update(wohnung=other_unit)
        response = self.client.post(self.completion_url, data)
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, str(other_unit), status_code=409)
        self.assert_no_completion()
        self.application.refresh_from_db()
        self.assertEqual(
            self.client.post(self.completion_url, self.completion_data()).status_code, 302
        )
        self.assertEqual(Rental.objects.get().wohnung, other_unit)

    def test_changed_account_cannot_be_confirmed_by_editing_only_the_hidden_id(self):
        data = self.completion_data()
        Person.objects.filter(pk=self.person.pk).update(user=self.other)
        data["account"] = self.other.pk
        self.assertEqual(self.client.post(self.completion_url, data).status_code, 409)
        self.assert_no_completion()

    def test_missing_or_tampered_confirmation_does_not_write_any_assignment(self):
        for value in (None, "not-a-valid-confirmation"):
            with self.subTest(value=value):
                data = self.completion_data()
                if value is None:
                    data.pop("assignment_confirmation")
                else:
                    data["assignment_confirmation"] = value
                self.assertEqual(self.client.post(self.completion_url, data).status_code, 400)
                self.assert_no_completion()

    def test_inactive_or_missing_tenant_account_cannot_be_assigned(self):
        for missing in (False, True):
            with self.subTest(missing=missing), transaction.atomic():
                if missing:
                    Person.objects.filter(pk=self.person.pk).update(user=None)
                else:
                    get_user_model().objects.filter(pk=self.applicant.pk).update(is_active=False)
                response = self.client.post(
                    self.completion_url, self.completion_data(), follow=True
                )
                self.assertContains(response, "Benutzerkonto")
                self.assert_no_completion()
                transaction.set_rollback(True)

    def test_rights_session_or_credentials_revoked_during_pdf_validation_stop_completion(self):
        original_clean = RentalCompletionForm.clean_contract
        for revoke in ("role", "session", "credentials"):
            with self.subTest(revoke=revoke), transaction.atomic():
                self.client.force_login(self.employee)
                data = self.completion_data()

                def revoke_access(form):
                    upload = original_clean(form)
                    if revoke == "role":
                        self.employee.groups.clear()
                    elif revoke == "session":
                        Session.objects.filter(session_key=self.client.session.session_key).delete()
                    else:
                        get_user_model().objects.filter(pk=self.employee.pk).update(
                            password="!revoked"
                        )
                    return upload

                with patch.object(RentalCompletionForm, "clean_contract", revoke_access):
                    self.assertEqual(self.client.post(self.completion_url, data).status_code, 403)
                self.assert_no_completion()
                transaction.set_rollback(True)

    def test_withdrawal_or_removed_acceptance_during_validation_leaves_no_rental(self):
        original_clean = RentalCompletionForm.clean_contract
        for changes in (
            {"accepted_at": None},
            {"interest_withdrawn_at": self.application.accepted_at},
        ):
            with self.subTest(changes=changes), transaction.atomic():
                data = self.completion_data()

                def change_application(form):
                    upload = original_clean(form)
                    Bewerbung.objects.filter(pk=self.application.pk).update(**changes)
                    return upload

                with patch.object(RentalCompletionForm, "clean_contract", change_application):
                    self.assertEqual(self.client.post(self.completion_url, data).status_code, 302)
                self.assert_no_completion()
                transaction.set_rollback(True)

    def test_existing_different_unit_assignment_is_not_overwritten(self):
        assigned = Wohnung.objects.create(gebaeudenummer="1", wohnungsnummer="16")
        Person.objects.filter(pk=self.person.pk).update(wohnung=assigned)
        response = self.client.post(self.completion_url, self.completion_data(), follow=True)
        self.assertContains(response, "bestehende Wohnungszuordnung")
        self.assertFalse(Rental.objects.exists())
        self.person.refresh_from_db()
        self.assertEqual(self.person.wohnung, assigned)

    def test_role_assignment_failure_rolls_back_both_rental_and_person_assignment(self):
        data = self.completion_data()
        with patch.object(
            type(self.applicant.groups), "add", side_effect=RuntimeError("synthetic role failure")
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(self.completion_url, data)
        self.assert_no_completion()

    def test_removed_tenant_permission_revokes_profile_and_download_access(self):
        self.client.post(self.completion_url, self.completion_data())
        self.applicant.groups.remove(Group.objects.get(name=ROLE_TENANT))
        self.client.force_login(self.applicant)
        profile = self.client.get(reverse("profile:detail"))
        self.assertNotContains(profile, self.contract_url)
        self.assertEqual(self.client.get(self.contract_url).status_code, 403)

    def test_actual_completion_form_has_working_csrf_token_and_download_is_read_only(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.employee)
        data = self.completion_data(client=client)
        self.assertEqual(client.post(self.completion_url, data).status_code, 403)
        data = self.completion_data(client=client)
        data["csrfmiddlewaretoken"] = client.cookies["csrftoken"].value
        self.assertEqual(client.post(self.completion_url, data).status_code, 302)
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.post(self.contract_url).status_code, 405)
        response = self.client.head(self.contract_url)
        self.assertEqual(response.status_code, 200)


class RentalCompletionDocumentTests(TestCase):
    setUp = test_handover_export.HandoverExportTests.setUp
    url = test_handover_export.HandoverExportTests.url
    signing_data = test_handover_export.HandoverExportTests.signing_data
    finalize = test_handover_export.HandoverExportTests.finalize
    pdf = test_handover_export.HandoverExportTests.pdf
    pdf_bytes = staticmethod(test_rental_completion.RentalCompletionTests.pdf_bytes)
    completion_data = RentalCompletionEdgeTests.completion_data

    def application_for_protocol(self):
        self.applicant = self.tenant
        self.application = Bewerbung.objects.create(
            person=self.person,
            wohnung=self.unit,
            submitted_at=timezone.now(),
            accepted_at=timezone.now(),
            main_application_unlocked=True,
        )
        self.tenant.groups.clear()
        return reverse("wohnungsverwaltung:employee_rental_complete", args=[self.application.pk])

    def test_completion_preserves_released_protocol_and_contract_access_after_new_login(self):
        self.finalize()
        archive = self.pdf()[0]
        completion_url = self.application_for_protocol()
        self.assertEqual(self.client.post(completion_url, self.completion_data()).status_code, 302)
        self.client.logout()
        self.client.force_login(self.tenant)
        profile = self.client.get(reverse("profile:detail"))
        self.assertContains(profile, str(self.unit))
        self.assertContains(profile, reverse("wohnungsverwaltung:handover_protocol_mine"))
        self.assertEqual(self.pdf()[0], archive)
        other = get_user_model().objects.create_user("unrelated-tenant")
        other.groups.add(Group.objects.get(name=ROLE_TENANT))
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.url("pdf")).status_code, 404)

    def test_open_protocol_prevents_new_unit_assignment(self):
        completion_url = self.application_for_protocol()
        response = self.client.post(completion_url, self.completion_data(), follow=True)
        self.assertContains(response, "bestehende Wohnungszuordnung")
        self.assertFalse(Rental.objects.exists())
        self.person.refresh_from_db()
        self.assertIsNone(self.person.wohnung_id)


class ConcurrentRentalCompletionTests(TransactionTestCase):
    def setUp(self):
        test_rental_completion.RentalCompletionTests.setUpTestData.__func__(type(self))

    pdf_bytes = staticmethod(test_rental_completion.RentalCompletionTests.pdf_bytes)
    completion_data = RentalCompletionEdgeTests.completion_data

    def test_two_simultaneous_completions_keep_one_rental_and_one_consistent_assignment(self):
        clients = [Client(), Client()]
        second = get_user_model().objects.create_user("second-employee@example.test")
        second.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        for client, account in zip(clients, (self.employee, second), strict=True):
            client.force_login(account)
        data = [self.completion_data(client=client) for client in clients]
        barrier = Barrier(2, timeout=10)
        url = reverse("wohnungsverwaltung:employee_rental_complete", args=[self.application.pk])

        def complete(client, payload):
            close_old_connections()
            try:
                barrier.wait()
                return client.post(url, payload).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(complete, client, payload)
                for client, payload in zip(clients, data, strict=True)
            ]
            self.assertEqual([future.result(timeout=20) for future in futures], [302, 302])
        self.assertEqual(Rental.objects.count(), 1)
        rental = Rental.objects.get()
        self.person.refresh_from_db()
        self.assertEqual(self.person.wohnung_id, rental.wohnung_id)
        self.assertEqual(rental.tenant_id, self.applicant.pk)
        self.assertEqual(bytes(rental.contract_pdf), self.pdf_bytes())
