from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from .forms import StellplatzForm, StellplatzZuordnungForm
from .models import (
    Schluessel,
    Stellplatz,
    StellplatzTyp,
    StellplatzZuordnung,
    Wohnung,
    WohnungStatus,
)


class ManagementViewTests(TestCase):
    def setUp(self) -> None:
        self.staff_user = get_user_model().objects.create_user(
            username="mitarbeiter",
            password="sicheres-passwort",
            is_staff=True,
        )
        self.regular_user = get_user_model().objects.create_user(
            username="besucher",
            password="sicheres-passwort",
        )

    def wohnung(self, **overrides) -> Wohnung:
        defaults = {
            "gebaeudenummer": "A",
            "wohnungsnummer": "1",
            "etage": 1,
            "groesse_qm": Decimal("42.50"),
            "zimmeranzahl": Decimal("2.00"),
            "kaltmiete": Decimal("500.00"),
            "warmmiete": Decimal("650.00"),
            "kaution": Decimal("1000.00"),
        }
        defaults.update(overrides)
        return Wohnung.objects.create(**defaults)

    def wohnung_payload(self, wohnung: Wohnung | None = None) -> dict[str, str]:
        data = {
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
            "schluessel-TOTAL_FORMS": "1",
            "schluessel-INITIAL_FORMS": "0",
            "schluessel-MIN_NUM_FORMS": "0",
            "schluessel-MAX_NUM_FORMS": "1000",
            "schluessel-0-schluessel_id": "",
            "schluessel-0-bezeichnung": "",
            "schluessel-0-anzahl": "0",
            "schluessel-0-aufschrift": "",
            "schluessel-0-status": "",
        }
        if wohnung is not None:
            data["gebaeudenummer"] = wohnung.gebaeudenummer
            data["wohnungsnummer"] = wohnung.wohnungsnummer
            data["etage"] = str(wohnung.etage)
            data["groesse_qm"] = str(wohnung.groesse_qm)
            data["zimmeranzahl"] = str(wohnung.zimmeranzahl)
            data["kaltmiete"] = str(wohnung.kaltmiete)
            data["warmmiete"] = str(wohnung.warmmiete)
            data["kaution"] = str(wohnung.kaution)
        return data

    @staticmethod
    def stellplatz_payload(
        *,
        name: str = "TG-07",
        stellplatz_typ: str = StellplatzTyp.CAR,
        wohnung: Wohnung | None = None,
        miete: str = "0.00",
    ) -> dict[str, str]:
        return {
            "name": name,
            "stellplatz_typ": stellplatz_typ,
            "wohnung": str(wohnung.pk) if wohnung else "",
            "miete": miete,
        }

    def force_staff_login(self) -> None:
        self.client.force_login(self.staff_user)

    def test_management_pages_require_staff_members(self) -> None:
        url = reverse("wohnungsverwaltung:wohnung_list")

        response = self.client.get(url)
        self.assertRedirects(response, f"/admin/login/?next={url}")

        self.client.force_login(self.regular_user)
        response = self.client.get(url)
        self.assertRedirects(response, f"/admin/login/?next={url}")

        self.force_staff_login()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_wohnung_list_is_sorted_by_floor_then_number(self) -> None:
        self.wohnung(etage=2, wohnungsnummer="01")
        self.wohnung(etage=1, wohnungsnummer="99")
        self.wohnung(etage=1, wohnungsnummer="02")
        self.force_staff_login()

        response = self.client.get(reverse("wohnungsverwaltung:wohnung_list"))

        self.assertEqual(
            [wohnung.wohnungsnummer for wohnung in response.context["wohnungen"]],
            ["02", "99", "01"],
        )

    def test_create_wohnung_persists_only_allowed_stammdaten(self) -> None:
        self.force_staff_login()

        response = self.client.post(
            reverse("wohnungsverwaltung:wohnung_create"),
            self.wohnung_payload(),
        )

        wohnung = Wohnung.objects.get(wohnungsnummer="17")
        self.assertRedirects(
            response,
            reverse("wohnungsverwaltung:wohnung_edit", args=[wohnung.pk]),
        )
        self.assertEqual(wohnung.status, WohnungStatus.FREE)
        self.assertTrue(wohnung.barrierefrei)
        self.assertEqual(wohnung.zaehlernummer_strom, "ST-4")

    def test_wohnung_form_does_not_allow_status_changes(self) -> None:
        wohnung = self.wohnung(status=WohnungStatus.TAKEN)
        self.force_staff_login()

        response = self.client.get(reverse("wohnungsverwaltung:wohnung_edit", args=[wohnung.pk]))
        self.assertNotIn("status", response.context["form"].fields)

        payload = self.wohnung_payload(wohnung)
        payload["status"] = WohnungStatus.BLOCKED
        response = self.client.post(
            reverse("wohnungsverwaltung:wohnung_edit", args=[wohnung.pk]),
            payload,
        )
        if response.status_code != 302:
            self.fail(
                f"Schlüsselformset ist ungültig: {response.context['schluessel_formset'].errors}"
            )

        wohnung.refresh_from_db()
        self.assertEqual(wohnung.status, WohnungStatus.TAKEN)

    def test_wohnung_rejects_negative_values(self) -> None:
        self.force_staff_login()
        payload = self.wohnung_payload()
        payload["groesse_qm"] = "-0.01"

        response = self.client.post(reverse("wohnungsverwaltung:wohnung_create"), payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Wohnung.objects.filter(wohnungsnummer="17").exists())
        self.assertTrue(response.context["form"].errors)

    def test_key_formset_can_create_update_and_delete_keys(self) -> None:
        wohnung = self.wohnung()
        existing_key = Schluessel.objects.create(
            wohnung=wohnung,
            bezeichnung="Haustür",
            anzahl=2,
            aufschrift="H1",
            status="in_use",
        )
        self.force_staff_login()
        payload = self.wohnung_payload(wohnung)
        payload.update(
            {
                "schluessel-TOTAL_FORMS": "2",
                "schluessel-INITIAL_FORMS": "1",
                "schluessel-0-schluessel_id": str(existing_key.pk),
                "schluessel-0-bezeichnung": "Haustür",
                "schluessel-0-anzahl": "3",
                "schluessel-0-aufschrift": "H2",
                "schluessel-0-status": "in_use",
                "schluessel-1-schluessel_id": "",
                "schluessel-1-bezeichnung": "Keller",
                "schluessel-1-anzahl": "1",
                "schluessel-1-aufschrift": "K1",
                "schluessel-1-status": "blocked",
            }
        )

        response = self.client.post(
            reverse("wohnungsverwaltung:wohnung_edit", args=[wohnung.pk]),
            payload,
        )
        if response.status_code != 302:
            self.fail(
                f"Schlüsselformset ist ungültig: {response.context['schluessel_formset'].errors}"
            )

        existing_key.refresh_from_db()
        self.assertEqual(existing_key.anzahl, 3)
        self.assertTrue(Schluessel.objects.filter(wohnung=wohnung, bezeichnung="Keller").exists())

        payload = self.wohnung_payload(wohnung)
        payload.update(
            {
                "schluessel-TOTAL_FORMS": "2",
                "schluessel-INITIAL_FORMS": "2",
                "schluessel-0-schluessel_id": str(existing_key.pk),
                "schluessel-0-bezeichnung": "Haustür",
                "schluessel-0-anzahl": "3",
                "schluessel-0-aufschrift": "H2",
                "schluessel-0-status": "in_use",
                "schluessel-0-DELETE": "on",
            }
        )
        cellar_key = Schluessel.objects.get(wohnung=wohnung, bezeichnung="Keller")
        payload.update(
            {
                "schluessel-1-schluessel_id": str(cellar_key.pk),
                "schluessel-1-bezeichnung": "Keller",
                "schluessel-1-anzahl": "1",
                "schluessel-1-aufschrift": "K1",
                "schluessel-1-status": "blocked",
            }
        )

        response = self.client.post(
            reverse("wohnungsverwaltung:wohnung_edit", args=[wohnung.pk]),
            payload,
        )
        if response.status_code != 302:
            self.fail(
                f"Schlüsselformset ist ungültig: {response.context['schluessel_formset'].errors}"
            )

        self.assertFalse(Schluessel.objects.filter(pk=existing_key.pk).exists())
        self.assertTrue(Schluessel.objects.filter(pk=cellar_key.pk).exists())

    def test_stellplatz_dashboard_is_sorted_and_wohnung_form_has_no_stellplatz_fields(self) -> None:
        Stellplatz.objects.create(name="Z 10", stellplatz_typ=StellplatzTyp.CAR)
        Stellplatz.objects.create(name="A 01", stellplatz_typ=StellplatzTyp.EV)
        self.force_staff_login()

        response = self.client.get(reverse("wohnungsverwaltung:stellplatz_list"))

        self.assertEqual(
            [stellplatz.name for stellplatz in response.context["stellplaetze"]], ["A 01", "Z 10"]
        )
        self.assertEqual(set(StellplatzForm().fields), {"name", "stellplatz_typ", "miete"})
        self.assertEqual(set(StellplatzZuordnungForm().fields), {"wohnung"})

        response = self.client.get(reverse("wohnungsverwaltung:wohnung_create"))

        self.assertNotContains(response, "Stellplatz zuordnen")
        self.assertNotIn("zuordnung_formset", response.context)

    def test_stellplatz_create_and_edit_includes_wohnung_zuordnung(self) -> None:
        wohnung = self.wohnung()
        other_wohnung = self.wohnung(wohnungsnummer="2")
        self.force_staff_login()
        create_response = self.client.post(
            reverse("wohnungsverwaltung:stellplatz_create"),
            self.stellplatz_payload(wohnung=wohnung, miete="45.00"),
        )

        stellplatz = Stellplatz.objects.get(name="TG-07")
        self.assertRedirects(
            create_response,
            reverse("wohnungsverwaltung:stellplatz_edit", args=[stellplatz.pk]),
        )
        zuordnung = StellplatzZuordnung.objects.get(stellplatz=stellplatz)
        self.assertEqual(zuordnung.wohnung, wohnung)
        self.assertEqual(stellplatz.miete, Decimal("45.00"))

        response = self.client.post(
            reverse("wohnungsverwaltung:stellplatz_edit", args=[stellplatz.pk]),
            self.stellplatz_payload(
                name="TG-08",
                stellplatz_typ=StellplatzTyp.EV,
                wohnung=other_wohnung,
                miete="55.00",
            ),
        )
        self.assertRedirects(
            response,
            reverse("wohnungsverwaltung:stellplatz_edit", args=[stellplatz.pk]),
        )
        stellplatz.refresh_from_db()
        self.assertEqual(stellplatz.stellplatz_typ, StellplatzTyp.EV)
        self.assertEqual(stellplatz.miete, Decimal("55.00"))
        zuordnung.refresh_from_db()
        self.assertEqual(zuordnung.wohnung, other_wohnung)

    def test_stellplatz_master_data_can_remove_wohnung_zuordnung(self) -> None:
        wohnung = self.wohnung()
        stellplatz = Stellplatz.objects.create(name="TG-01", stellplatz_typ=StellplatzTyp.CAR)
        self.force_staff_login()

        response = self.client.post(
            reverse("wohnungsverwaltung:stellplatz_edit", args=[stellplatz.pk]),
            self.stellplatz_payload(name="TG-01", wohnung=wohnung, miete="45.00"),
        )
        self.assertRedirects(
            response,
            reverse("wohnungsverwaltung:stellplatz_edit", args=[stellplatz.pk]),
        )

        zuordnung = StellplatzZuordnung.objects.get(stellplatz=stellplatz)
        self.assertEqual(zuordnung.wohnung, wohnung)
        stellplatz.refresh_from_db()
        self.assertEqual(stellplatz.miete, Decimal("45.00"))

        response = self.client.post(
            reverse("wohnungsverwaltung:stellplatz_edit", args=[stellplatz.pk]),
            self.stellplatz_payload(name="TG-01"),
        )
        self.assertRedirects(
            response,
            reverse("wohnungsverwaltung:stellplatz_edit", args=[stellplatz.pk]),
        )
        self.assertFalse(StellplatzZuordnung.objects.filter(pk=zuordnung.pk).exists())
        self.assertTrue(Stellplatz.objects.filter(pk=stellplatz.pk).exists())

    def test_stellplatz_can_have_miete_without_wohnung_zuordnung(self) -> None:
        self.force_staff_login()

        response = self.client.post(
            reverse("wohnungsverwaltung:stellplatz_create"),
            self.stellplatz_payload(name="TG-05", miete="30.00"),
        )

        stellplatz = Stellplatz.objects.get(name="TG-05")
        self.assertRedirects(
            response,
            reverse("wohnungsverwaltung:stellplatz_edit", args=[stellplatz.pk]),
        )
        self.assertEqual(stellplatz.miete, Decimal("30.00"))
        self.assertFalse(StellplatzZuordnung.objects.filter(stellplatz=stellplatz).exists())

    def test_stellplatz_master_data_rejects_negative_miete(self) -> None:
        wohnung = self.wohnung(wohnungsnummer="1")
        stellplatz = Stellplatz.objects.create(name="TG-02", stellplatz_typ=StellplatzTyp.CAR)
        self.force_staff_login()

        response = self.client.post(
            reverse("wohnungsverwaltung:stellplatz_edit", args=[stellplatz.pk]),
            self.stellplatz_payload(name="TG-02", wohnung=wohnung, miete="-1.00"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(stellplatz.miete, Decimal("0"))

    def test_database_prevents_two_current_zuordnungen_for_one_stellplatz(self) -> None:
        stellplatz = Stellplatz.objects.create(name="TG-03", stellplatz_typ=StellplatzTyp.CAR)
        StellplatzZuordnung.objects.create(stellplatz=stellplatz, wohnung=self.wohnung())

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StellplatzZuordnung.objects.create(
                    stellplatz=stellplatz,
                    wohnung=self.wohnung(wohnungsnummer="3"),
                )


class StellplatzZuordnungMigrationTests(TransactionTestCase):
    migrate_from = ("immobilien", "0001_initial")
    migrate_to = ("immobilien", "0003_stellplatz_eigenstaendige_miete")

    def setUp(self) -> None:
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        OldWohnung = old_apps.get_model("immobilien", "Wohnung")
        OldStellplatz = old_apps.get_model("immobilien", "Stellplatz")
        wohnung = OldWohnung.objects.create(gebaeudenummer="A", wohnungsnummer="10")
        self.stellplatz_id = OldStellplatz.objects.create(
            wohnung=wohnung,
            name="TG-99",
            stellplatz_typ="car",
            miete=Decimal("35.00"),
        ).pk
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([self.migrate_to])

    def test_existing_stellplatz_becomes_stamm_mit_miete_und_zuordnung(self) -> None:
        apps = MigrationExecutor(connection).loader.project_state([self.migrate_to]).apps
        Stellplatz = apps.get_model("immobilien", "Stellplatz")
        StellplatzZuordnung = apps.get_model("immobilien", "StellplatzZuordnung")

        zuordnung = StellplatzZuordnung.objects.get(stellplatz_id=self.stellplatz_id)
        stellplatz = Stellplatz.objects.get(stellplatz_id=self.stellplatz_id)

        self.assertEqual(zuordnung.stellplatz_id, self.stellplatz_id)
        self.assertEqual(stellplatz.miete, Decimal("35.00"))
        self.assertEqual(stellplatz.name, "TG-99")
