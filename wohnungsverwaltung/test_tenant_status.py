from unittest.mock import patch

from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import QuerySet
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import test_rental_completion as fixtures
from .access import APPLICANT_ACCESS_PERMISSION, ROLE_APPLICANT, ROLE_TENANT
from .models import Bewerbung, BewerbungStatus, Person, Rental, Wohnung, WohnungStatus


class ApplicantAcceptanceStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.RentalCompletionTests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.applicant)
        self.list_url = reverse("wohnungsverwaltung:pre_application_list")
        self.detail_url = reverse(
            "wohnungsverwaltung:main_application_status", args=[self.application.pk]
        )

    def test_accepted_application_shows_own_acceptance_in_list_and_details(self):
        for url in (self.list_url, self.detail_url):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, "Als Mieter angenommen")
                self.assertIn("no-store", response.headers.get("Cache-Control", ""))
                self.assertContains(response, str(self.unit))
                self.assertNotContains(response, "Bitte warten Sie auf die Rückmeldung")
                self.assertNotContains(response, "Entscheidung zur Bewerbung abwarten")

    def test_application_without_acceptance_does_not_show_a_tenant_confirmation(self):
        Bewerbung.objects.filter(pk=self.application.pk).update(accepted_at=None)
        for url in (self.list_url, self.detail_url):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotContains(response, "Als Mieter angenommen")
                self.assertContains(response, "Hauptbewerbung eingereicht")

    def test_ended_or_incomplete_application_does_not_show_an_old_acceptance(self):
        cases = (
            ({"status": BewerbungStatus.DECLINED}, "Abgelehnt"),
            ({"status": BewerbungStatus.BLOCKED}, "Gesperrt"),
            ({"interest_withdrawn_at": timezone.now()}, "Zurückgezogen"),
            ({"submitted_at": None}, "Hauptbewerbung freigeschaltet"),
        )
        for changes, expected in cases:
            with self.subTest(changes=changes), transaction.atomic():
                Bewerbung.objects.filter(pk=self.application.pk).update(**changes)
                response = self.client.get(self.list_url)
                self.assertNotContains(response, "Als Mieter angenommen")
                self.assertContains(response, expected)
                transaction.set_rollback(True)

    def test_other_account_cannot_see_the_accepted_application_or_its_unit(self):
        self.other.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        Person.objects.create(
            user=self.other, vorname="Andere", nachname="Person", email="other@example.test"
        )
        self.client.force_login(self.other)
        response = self.client.get(self.list_url)
        self.assertNotContains(response, "Als Mieter angenommen")
        self.assertNotContains(response, str(self.unit))
        self.assertEqual(self.client.get(self.detail_url).status_code, 404)

    def test_acceptance_remains_visible_after_logging_in_again(self):
        self.applicant.set_password("Synthetic-status-test-4826")
        self.applicant.save(update_fields=["password"])
        self.client.logout()
        self.assertTrue(
            self.client.login(
                username=self.applicant.username, password="Synthetic-status-test-4826"
            )
        )
        self.assertContains(self.client.get(self.list_url), "Als Mieter angenommen")
        self.assertContains(self.client.get(self.detail_url), "Als Mieter angenommen")


class TenantProfileStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.RentalCompletionTests.setUpTestData.__func__(cls)

    completion_url = fixtures.RentalCompletionTests.completion_url
    contract_url = fixtures.RentalCompletionTests.contract_url
    pdf_bytes = staticmethod(fixtures.RentalCompletionTests.pdf_bytes)
    complete = fixtures.RentalCompletionTests.complete

    def setUp(self):
        self.profile_url = reverse("profile:detail")
        self.client.force_login(self.applicant)

    def complete_as_employee(self):
        self.client.force_login(self.employee)
        self.assertContains(self.complete(), "Vermietung abgeschlossen")
        self.client.force_login(self.applicant)

    def test_profile_shows_own_acceptance_before_rental_is_completed(self):
        response = self.client.get(self.profile_url)
        self.assertContains(response, "Als Mieter angenommen")
        self.assertContains(response, str(self.unit))
        self.assertContains(response, "Der Vermietungsabschluss steht noch aus.")
        self.assertNotContains(response, "Vermietet")
        self.assertNotContains(response, self.contract_url)

    def test_completed_rental_shows_unit_status_and_contract_after_new_login(self):
        self.applicant.set_password("Synthetic-status-test-4826")
        self.applicant.save(update_fields=["password"])
        self.complete_as_employee()
        self.client.logout()
        self.assertTrue(
            self.client.login(
                username=self.applicant.username, password="Synthetic-status-test-4826"
            )
        )
        response = self.client.get(self.profile_url)
        self.assertContains(response, str(self.unit))
        self.assertContains(response, "Wohnungsstatus:")
        self.assertContains(response, "Vermietet")
        self.assertContains(response, "Vermietung abgeschlossen")
        self.assertContains(response, self.contract_url)
        self.assertNotContains(response, "Der Vermietungsabschluss steht noch aus.")
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))

    def test_profile_uses_current_unit_status_instead_of_assuming_taken(self):
        self.complete_as_employee()
        for status, label in (
            (WohnungStatus.TAKEN, "Vermietet"),
            (WohnungStatus.FREE, "Verfügbar"),
            (WohnungStatus.BLOCKED, "Gesperrt"),
        ):
            with self.subTest(status=status):
                Wohnung.objects.filter(pk=self.unit.pk).update(status=status)
                response = self.client.get(self.profile_url)
                self.assertContains(response, label)
                if status != WohnungStatus.TAKEN:
                    self.assertNotContains(response, "Vermietet")

    def test_other_account_cannot_see_acceptance_unit_or_contract(self):
        for completed in (False, True):
            with self.subTest(completed=completed):
                if completed:
                    self.complete_as_employee()
                self.client.force_login(self.other)
                response = self.client.get(self.profile_url)
                self.assertNotContains(response, "Als Mieter angenommen")
                self.assertNotContains(response, str(self.unit))
                self.assertNotContains(response, "Vermietet")
                self.assertNotContains(response, self.contract_url)

    def test_missing_acceptance_or_ended_application_has_no_profile_confirmation(self):
        cases = (
            {"accepted_at": None},
            {"status": BewerbungStatus.DECLINED},
            {"status": BewerbungStatus.BLOCKED},
            {"interest_withdrawn_at": timezone.now()},
            {"submitted_at": None},
        )
        for changes in cases:
            with self.subTest(changes=changes), transaction.atomic():
                Bewerbung.objects.filter(pk=self.application.pk).update(**changes)
                response = self.client.get(self.profile_url)
                self.assertNotContains(response, "Als Mieter angenommen")
                self.assertNotContains(response, str(self.unit))
                self.assertNotContains(response, "Vermietet")
                transaction.set_rollback(True)

    def test_manual_person_assignment_and_tenant_role_do_not_imply_completed_rental(self):
        Bewerbung.objects.filter(pk=self.application.pk).update(accepted_at=None)
        self.applicant.groups.add(Group.objects.get(name=ROLE_TENANT))
        Person.objects.filter(pk=self.person.pk).update(wohnung=self.unit)
        response = self.client.get(self.profile_url)
        self.assertNotContains(response, "Als Mieter angenommen")
        self.assertNotContains(response, "Wohnungsstatus:")
        self.assertNotContains(response, "Vermietet")

    def test_relinked_account_does_not_inherit_completed_rental_status(self):
        self.complete_as_employee()
        Person.objects.filter(pk=self.person.pk).update(user=self.other)
        for account in (self.applicant, self.other):
            with self.subTest(account=account.pk):
                self.client.force_login(account)
                response = self.client.get(self.profile_url)
                self.assertNotContains(response, "Vermietet")
                self.assertNotContains(response, str(self.unit))
                self.assertNotContains(response, self.contract_url)

    def test_removed_tenant_access_hides_rental_status_and_contract(self):
        self.complete_as_employee()
        self.applicant.groups.remove(Group.objects.get(name=ROLE_TENANT))
        response = self.client.get(self.profile_url)
        self.assertNotContains(response, "Wohnungsstatus:")
        self.assertNotContains(response, "Vermietet")
        self.assertNotContains(response, self.contract_url)

    def test_completed_profile_keeps_access_to_personal_notification_preferences(self):
        self.complete_as_employee()
        response = self.client.get(self.profile_url)
        self.assertContains(response, "Vermietet")
        self.assertContains(response, reverse("profile:notifications"))

    def test_completed_application_keeps_its_acceptance_in_both_applicant_views(self):
        self.complete_as_employee()
        urls = (
            reverse("wohnungsverwaltung:pre_application_list"),
            reverse("wohnungsverwaltung:main_application_status", args=[self.application.pk]),
        )
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, "Als Mieter angenommen")
                self.assertNotContains(response, "Bitte warten Sie auf die Rückmeldung")

    def test_person_relinked_during_profile_loading_does_not_expose_pending_acceptance(self):
        original_has_perm = type(self.applicant).has_perm

        def relink_before_query(account, permission, obj=None):
            if account.pk == self.applicant.pk and permission == APPLICANT_ACCESS_PERMISSION:
                Person.objects.filter(pk=self.person.pk).update(user=self.other)
            return original_has_perm(account, permission, obj)

        with patch.object(type(self.applicant), "has_perm", relink_before_query):
            response = self.client.get(self.profile_url)
        self.assertNotContains(response, "Als Mieter angenommen")
        self.assertNotContains(response, str(self.unit))

    def test_completion_after_pending_selection_shows_only_completed_rental(self):
        self.applicant.groups.add(Group.objects.get(name=ROLE_TENANT))
        original_fetch = QuerySet._fetch_all
        completed = False

        def complete_after_pending_selection(queryset):
            nonlocal completed
            original_fetch(queryset)
            if queryset.model is Bewerbung and not completed:
                completed = True
                self.complete_as_employee()

        with patch.object(QuerySet, "_fetch_all", complete_after_pending_selection):
            response = self.client.get(self.profile_url)
        self.assertTrue(completed)
        self.assertNotContains(response, "Der Vermietungsabschluss steht noch aus.")
        self.assertContains(response, "Wohnungsstatus:")
        self.assertContains(response, "Vermietung abgeschlossen.")
        self.assertContains(response, self.contract_url)

    def test_completion_between_profile_queries_keeps_acceptance_or_rental_visible(self):
        self.applicant.groups.add(Group.objects.get(name=ROLE_TENANT))
        original_fetch = QuerySet._fetch_all
        completed = False

        def complete_after_rental_selection(queryset):
            nonlocal completed
            original_fetch(queryset)
            if queryset.model is Rental and not completed:
                completed = True
                self.complete_as_employee()

        with patch.object(QuerySet, "_fetch_all", complete_after_rental_selection):
            response = self.client.get(self.profile_url)

        self.assertTrue(completed)
        self.assertTrue(Rental.objects.filter(application=self.application).exists())
        self.assertContains(response, str(self.unit))
        pending = "Der Vermietungsabschluss steht noch aus." in response.text
        rented = "Wohnungsstatus:" in response.text
        self.assertTrue(pending or rented)
        self.assertFalse(pending and rented)
