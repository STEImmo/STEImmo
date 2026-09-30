from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .access import ROLE_EMPLOYEE
from .models import Person, Schluessel, Stellplatz, StellplatzTyp, StellplatzZuordnung, Wohnung


class ManagementViewTests(TestCase):
    def setUp(self) -> None:
        self.employee_user = get_user_model().objects.create_user(
            username="mitarbeiter",
            password="sicheres-passwort",
        )
        Person.objects.create(
            user=self.employee_user,
            vorname="Mitarbeiter",
            nachname="Test",
            email="mitarbeiter@example.test",
            is_employee=True,
        )
        self.employee_user.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))

    def wohnung_payload(self) -> dict[str, str]:
        return {
            "gebaeudenummer": "B",
            "wohnungsnummer": "17",
            "etage": "2",
            "groesse_qm": "51.25",
            "zimmeranzahl": "2.5",
            "kaltmiete": "650.00",
            "warmmiete": "790.00",
            "kaution": "1300.00",
            "barrierefrei": "on",
            "zaehlernummer_wasser_kalt": "KW-1",
            "zaehlernummer_wasser_warm": "WW-2",
            "zaehlernummer_heizung": "HZ-3",
            "zaehlernummer_strom": "ST-4",
            "schluessel-TOTAL_FORMS": "0",
            "schluessel-INITIAL_FORMS": "0",
            "schluessel-MIN_NUM_FORMS": "0",
            "schluessel-MAX_NUM_FORMS": "1000",
        }

    def test_management_requires_employee_permission(self) -> None:
        url = reverse("verwaltung:wohnung_list")

        response = self.client.get(url)

        self.assertRedirects(response, f"{reverse('login')}?next={url}")

    def test_apartment_can_be_created_with_all_master_data(self) -> None:
        self.client.force_login(self.employee_user)

        response = self.client.post(reverse("verwaltung:wohnung_create"), self.wohnung_payload())

        wohnung = Wohnung.objects.get(wohnungsnummer="17")
        self.assertRedirects(response, reverse("verwaltung:wohnung_edit", args=[wohnung.pk]))
        self.assertTrue(wohnung.barrierefrei)
        self.assertEqual(wohnung.zaehlernummer_strom, "ST-4")

    def test_key_is_managed_with_apartment(self) -> None:
        self.client.force_login(self.employee_user)
        payload = self.wohnung_payload()
        payload.update(
            {
                "schluessel-TOTAL_FORMS": "1",
                "schluessel-0-schluessel_id": "",
                "schluessel-0-bezeichnung": "Haustür",
                "schluessel-0-anzahl": "2",
                "schluessel-0-aufschrift": "H1",
                "schluessel-0-status": "in_use",
            }
        )

        response = self.client.post(reverse("verwaltung:wohnung_create"), payload)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Schluessel.objects.filter(bezeichnung="Haustür", anzahl=2).exists())

    def test_stellplatz_miete_is_independent_from_wohnung_zuordnung(self) -> None:
        wohnung = Wohnung.objects.create(gebaeudenummer="A", wohnungsnummer="1")
        self.client.force_login(self.employee_user)

        response = self.client.post(
            reverse("verwaltung:stellplatz_create"),
            {
                "name": "TG-07",
                "stellplatz_typ": StellplatzTyp.EV,
                "miete": "45.00",
                "wohnung": str(wohnung.pk),
            },
        )

        stellplatz = Stellplatz.objects.get(name="TG-07")
        self.assertRedirects(response, reverse("verwaltung:stellplatz_edit", args=[stellplatz.pk]))
        self.assertEqual(stellplatz.miete, Decimal("45.00"))
        self.assertEqual(StellplatzZuordnung.objects.get(stellplatz=stellplatz).wohnung, wohnung)
