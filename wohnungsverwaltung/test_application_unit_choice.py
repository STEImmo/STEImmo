from django.test import TestCase

from .forms import BewerbungForm
from .models import Person, Wohnung, WohnungStatus


class ApplicationUnitChoiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.person = Person.objects.create(email="auswahl@example.test")
        cls.ground = Wohnung.objects.create(
            wohnungsnummer="1", gebaeudenummer="1", etage=0, groesse_qm="25.27"
        )
        cls.upper = Wohnung.objects.create(wohnungsnummer="102", gebaeudenummer="1", etage=1)
        cls.unavailable = Wohnung.objects.create(
            wohnungsnummer="002", gebaeudenummer="1", etage=0, status=WohnungStatus.TAKEN
        )

    def test_unit_label_uses_public_number_without_changing_stored_identifier(self):
        self.assertEqual(str(self.ground), "Gebäude 1, Wohnung 001")
        self.ground.refresh_from_db()
        self.assertEqual(self.ground.wohnungsnummer, "1")

    def test_unavailable_unit_remains_rejected(self):
        form = BewerbungForm({"wohnung": str(self.unavailable.pk)}, applicant=self.person)
        self.assertFalse(form.is_valid())
        self.assertIn("wohnung", form.errors)

    def test_preselected_unit_remains_locked_against_changed_post(self):
        form = BewerbungForm(
            {
                "wohnung": str(self.upper.pk),
                "personenanzahl": "1",
                "haustiere": "false",
                "ueber_mich": "Synthetische Anfrage",
            },
            applicant=self.person,
            unit=self.ground,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["wohnung"], self.ground)
