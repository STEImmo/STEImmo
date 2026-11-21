from django.contrib.auth.models import Group
from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import test_rental_completion as fixtures
from .access import ROLE_APPLICANT
from .models import Bewerbung, BewerbungStatus, Person


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
