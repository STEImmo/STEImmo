from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .access import ROLE_APPLICANT
from .models import ApplicationProof, ApplicationProofCategory, Bewerbung, Person, Wohnung


class ApplicationUITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="ui@example.test")
        cls.user.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        cls.person = Person.objects.create(user=cls.user, email="ui@example.test")
        cls.unit = Wohnung.objects.create(wohnungsnummer="203", gebaeudenummer="1", etage=2)

    def setUp(self):
        self.client.force_login(self.user)

    def application(self):
        return Bewerbung.objects.create(
            person=self.person,
            wohnung=self.unit,
            personenanzahl=1,
            ueber_mich="Synthetischer Test",
            main_application_unlocked=True,
        )

    def test_empty_overview_offers_search_and_explains_the_process(self):
        response = self.client.get(reverse("wohnungsverwaltung:pre_application_list"))
        self.assertContains(response, "application-sidebar")
        self.assertContains(response, "Noch keine Bewerbung")
        self.assertContains(response, reverse("wohnungsverwaltung_public:apartment_search"))

    def test_direct_entry_without_unit_leads_to_apartment_search(self):
        response = self.client.get(reverse("wohnungsverwaltung:pre_application_create"))
        self.assertRedirects(response, reverse("wohnungsverwaltung_public:apartment_search"))

    def test_selected_unit_is_summarized_without_a_second_selection(self):
        self.unit.groesse_qm = "44.04"
        self.unit.save()
        response = self.client.get(
            reverse("wohnungsverwaltung:pre_application_create_for_unit", args=[self.unit.pk])
        )
        self.assertContains(response, "Wohnung 203")
        self.assertContains(response, "2. Obergeschoss")
        self.assertContains(response, "44,0 m²")
        self.assertContains(response, "Andere Wohnung wählen")
        self.assertNotContains(response, 'name="wohnung"')
        self.assertNotContains(response, "application-unit-choices")

    def test_invalid_inquiry_keeps_selected_unit_summary_and_errors(self):
        response = self.client.post(
            reverse("wohnungsverwaltung:pre_application_create_for_unit", args=[self.unit.pk]),
            {"personenanzahl": "0"},
        )
        self.assertContains(response, "Wohnung 203")
        self.assertContains(response, 'id="id_personenanzahl_error"')
        self.assertNotContains(response, 'name="wohnung"')

    def test_unlocked_overview_marks_proof_stage_and_links_to_real_application(self):
        application = self.application()
        response = self.client.get(reverse("wohnungsverwaltung:pre_application_list"))
        self.assertContains(response, 'aria-current="step"><span>03</span>')
        self.assertContains(
            response, reverse("wohnungsverwaltung:main_application_status", args=[application.pk])
        )
        self.assertNotContains(response, "Beispieldaten")

    def test_editable_application_keeps_upload_and_submission_actions(self):
        application = self.application()
        response = self.client.get(
            reverse("wohnungsverwaltung:main_application_status", args=[application.pk])
        )
        self.assertContains(response, "Nachweiskategorien vorhanden")
        self.assertEqual(response.context["proof_count"], 0)
        self.assertContains(response, "data-proof-upload-field", count=3)
        self.assertContains(response, 'name="action" value="submit"')
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_submitted_application_shows_readonly_documents(self):
        application = self.application()
        application.submitted_at = timezone.now()
        application.save()
        response = self.client.get(
            reverse("wohnungsverwaltung:main_application_status", args=[application.pk])
        )
        self.assertContains(response, 'aria-current="step"><span>04</span>')
        self.assertNotContains(response, 'type="file"')
        self.assertNotContains(response, "data-proof-upload-form")

    def test_design_comparison_has_been_removed(self):
        self.assertEqual(self.client.get("/uebergaben/design/bewerbungen/").status_code, 404)

    def test_multiple_files_in_one_category_count_as_one_completed_category(self):
        application = self.application()
        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=directory):
            for index in range(2):
                ApplicationProof.objects.create(
                    application=application,
                    category=ApplicationProofCategory.INCOME,
                    original_name=f"test-{index}.pdf",
                    file=ContentFile(b"synthetic", name=f"test-{index}.pdf"),
                )
            response = self.client.get(
                reverse("wohnungsverwaltung:main_application_status", args=[application.pk])
            )
            self.assertEqual(response.context["proof_count"], 1)
            self.assertContains(response, 'form="remove-proof-1-1"')
            self.assertContains(response, 'id="remove-proof-1-1"')
            self.assertContains(response, "data-proof-existing-name", count=2)
