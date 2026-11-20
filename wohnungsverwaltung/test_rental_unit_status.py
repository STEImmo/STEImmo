from unittest.mock import patch

from django.db import transaction
from django.test import TestCase
from django.urls import reverse

from . import test_management as management_fixtures
from . import test_rental_completion as fixtures
from . import views
from .access import ROLE_TENANT
from .forms import WohnungForm
from .models import Bewerbung, Rental, WohnungStatus


class RentalUnitStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.RentalCompletionTests.setUpTestData.__func__(cls)

    completion_url = fixtures.RentalCompletionTests.completion_url
    pdf_bytes = staticmethod(fixtures.RentalCompletionTests.pdf_bytes)
    complete = fixtures.RentalCompletionTests.complete

    def setUp(self):
        self.client.force_login(self.employee)

    def test_acceptance_alone_keeps_unit_available(self):
        Bewerbung.objects.filter(pk=self.application.pk).update(accepted_at=None)
        response = self.client.post(
            reverse("wohnungsverwaltung:employee_application_accept", args=[self.application.pk]),
            follow=True,
        )
        self.assertContains(response, "Bewerbung angenommen")
        self.application.refresh_from_db()
        self.assertIsNotNone(self.application.accepted_at)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, WohnungStatus.FREE)
        self.assertFalse(Rental.objects.exists())

    def test_completion_sets_taken_with_matching_rental_and_tenant_assignment(self):
        for status in WohnungStatus.values:
            with self.subTest(status=status), transaction.atomic():
                self.unit.status = status
                self.unit.save(update_fields=["status"])
                self.assertContains(self.complete(), "Vermietung abgeschlossen")
                self.unit.refresh_from_db()
                self.person.refresh_from_db()
                rental = Rental.objects.get(application=self.application)
                self.assertEqual(self.unit.status, WohnungStatus.TAKEN)
                self.assertEqual(rental.wohnung_id, self.unit.pk)
                self.assertEqual(self.person.wohnung_id, rental.wohnung_id)
                self.assertEqual(rental.tenant_id, self.person.user_id)
                self.assertTrue(self.applicant.groups.filter(name=ROLE_TENANT).exists())
                transaction.set_rollback(True)

    def test_repeated_completion_keeps_status_assignment_and_original_contract(self):
        contract = self.pdf_bytes()
        self.complete(contract=contract)
        rental = Rental.objects.get()
        self.unit.refresh_from_db()
        updated_at = self.unit.updated_at
        self.assertContains(self.complete(contract=b"invalid"), "bereits abgeschlossen")
        self.unit.refresh_from_db()
        self.person.refresh_from_db()
        self.assertEqual(self.unit.status, WohnungStatus.TAKEN)
        self.assertEqual(self.unit.updated_at, updated_at)
        self.assertEqual(self.person.wohnung_id, self.unit.pk)
        self.assertEqual(Rental.objects.count(), 1)
        self.assertEqual(bytes(Rental.objects.get(pk=rental.pk).contract_pdf), contract)

    def test_repeated_completion_preserves_a_later_unit_status(self):
        self.complete()
        self.unit.refresh_from_db()
        self.unit.status = WohnungStatus.BLOCKED
        self.unit.save(update_fields=["status", "updated_at"])
        updated_at = self.unit.updated_at
        self.assertContains(self.complete(contract=b"invalid"), "bereits abgeschlossen")
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, WohnungStatus.BLOCKED)
        self.assertEqual(self.unit.updated_at, updated_at)
        self.assertEqual(Rental.objects.count(), 1)

    def test_invalid_contract_keeps_original_status_and_no_assignment(self):
        for status in WohnungStatus.values:
            with self.subTest(status=status):
                self.unit.status = status
                self.unit.save(update_fields=["status"])
                self.assertEqual(self.complete(contract=b"invalid", follow=False).status_code, 400)
                self.unit.refresh_from_db()
                self.person.refresh_from_db()
                self.assertEqual(self.unit.status, status)
                self.assertIsNone(self.person.wohnung_id)
                self.assertFalse(Rental.objects.exists())

    def test_failure_after_status_save_rolls_back_status_rental_assignment_and_role(self):
        def fail_role_assignment(*args, **kwargs):
            self.unit.refresh_from_db()
            self.assertEqual(self.unit.status, WohnungStatus.TAKEN)
            raise RuntimeError("synthetic role failure")

        with patch.object(type(self.applicant.groups), "add", side_effect=fail_role_assignment):
            with self.assertRaisesMessage(RuntimeError, "synthetic role failure"):
                self.complete()
        self.unit.refresh_from_db()
        self.person.refresh_from_db()
        self.assertEqual(self.unit.status, WohnungStatus.FREE)
        self.assertIsNone(self.person.wohnung_id)
        self.assertFalse(Rental.objects.exists())
        self.assertFalse(self.applicant.groups.filter(name=ROLE_TENANT).exists())

    def test_status_save_failure_rolls_back_rental_and_assignment(self):
        with patch.object(type(self.unit), "save", side_effect=RuntimeError("status save failure")):
            with self.assertRaisesMessage(RuntimeError, "status save failure"):
                self.complete()
        self.unit.refresh_from_db()
        self.person.refresh_from_db()
        self.assertEqual(self.unit.status, WohnungStatus.FREE)
        self.assertIsNone(self.person.wohnung_id)
        self.assertFalse(Rental.objects.exists())
        self.assertFalse(self.applicant.groups.filter(name=ROLE_TENANT).exists())

    def test_completed_unit_is_taken_in_management_and_unavailable_on_public_pages(self):
        detail_url = reverse(
            "wohnungsverwaltung_public:apartment_detail_placeholder", args=[self.unit.pk]
        )
        self.assertEqual(self.client.get(detail_url).status_code, 200)
        self.complete()
        search = self.client.get(reverse("wohnungsverwaltung_public:apartment_search"))
        self.assertFalse(search.context["wohnungen"].filter(pk=self.unit.pk).exists())
        self.assertEqual(self.client.get(detail_url).status_code, 404)
        building = self.client.get(reverse("wohnungsverwaltung_public:building_view"))
        self.assertEqual(building.context["total_available"], 0)
        floor = self.client.get(reverse("wohnungsverwaltung_public:floor_view", args=[0]))
        self.assertNotContains(floor, detail_url)
        listing = self.client.get(reverse("verwaltung:wohnung_list"), {"status": "taken"})
        self.assertContains(listing, "Vermietet")
        self.assertTrue(listing.context["wohnungen"].filter(pk=self.unit.pk).exists())
        available = self.client.get(reverse("verwaltung:wohnung_list"), {"status": "free"})
        self.assertFalse(available.context["wohnungen"].filter(pk=self.unit.pk).exists())

    def management_data(self, page):
        confirmation = page.context["rental_confirmation"]
        self.assertContains(page, f'name="rental_confirmation" value="{confirmation}"')
        return management_fixtures.ManagementViewTests.wohnung_payload(self) | {
            "requirements_version": page.context["requirements_version"],
            "rental_confirmation": confirmation,
        }

    def test_stale_management_form_cannot_reopen_completed_rental(self):
        url = reverse("verwaltung:wohnung_edit", args=[self.unit.pk])
        data = self.management_data(self.client.get(url))
        self.complete()
        self.assertContains(self.client.post(url, data, follow=True), "Vermietung wurde")
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, WohnungStatus.TAKEN)
        self.assertEqual(self.unit.wohnungsnummer, "14")
        self.assertEqual(Rental.objects.count(), 1)

    def test_management_save_rechecks_completion_after_form_validation(self):
        url = reverse("verwaltung:wohnung_edit", args=[self.unit.pk])
        data = self.management_data(self.client.get(url))
        original_clean = WohnungForm.clean

        def complete_during_validation(form):
            cleaned_data = original_clean(form)
            self.complete()
            return cleaned_data

        with patch.object(WohnungForm, "clean", complete_during_validation):
            response = self.client.post(url, data, follow=True)
        self.assertContains(response, "Vermietung wurde")
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, WohnungStatus.TAKEN)
        self.assertEqual(self.unit.wohnungsnummer, "14")

    def test_completion_while_opening_management_form_does_not_confirm_stale_status(self):
        url = reverse("verwaltung:wohnung_edit", args=[self.unit.pk])
        original_get = views.get_object_or_404
        completed = False

        def complete_after_unit_read(*args, **kwargs):
            nonlocal completed
            instance = original_get(*args, **kwargs)
            if isinstance(instance, type(self.unit)) and not completed:
                completed = True
                self.complete()
            return instance

        with patch.object(views, "get_object_or_404", side_effect=complete_after_unit_read):
            page = self.client.get(url)
        data = self.management_data(page)
        response = self.client.post(url, data, follow=True)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, WohnungStatus.TAKEN)
        self.assertContains(response, "Vermietung wurde")

    def test_current_management_form_allows_deliberate_later_status_change(self):
        self.complete()
        url = reverse("verwaltung:wohnung_edit", args=[self.unit.pk])
        data = self.management_data(self.client.get(url)) | {"status": WohnungStatus.BLOCKED}
        self.assertContains(
            self.client.post(url, data, follow=True), "Wohnungsstammdaten wurden gespeichert"
        )
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, WohnungStatus.BLOCKED)

    def test_invalid_stale_management_form_does_not_confirm_new_rental_on_redisplay(self):
        url = reverse("verwaltung:wohnung_edit", args=[self.unit.pk])
        data = self.management_data(self.client.get(url))
        self.complete()
        invalid = self.client.post(url, data | {"wohnungsnummer": ""})
        self.assertEqual(invalid.context["rental_confirmation"], data["rental_confirmation"])
        corrected = data | {"rental_confirmation": invalid.context["rental_confirmation"]}
        self.assertContains(self.client.post(url, corrected, follow=True), "Vermietung wurde")
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, WohnungStatus.TAKEN)
