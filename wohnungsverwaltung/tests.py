from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import (
    AbnahmeStatus,
    Person,
    Protokoll,
    ProtokollStatus,
    ProtokollTyp,
    UebergabeStatus,
    Wohnung,
)


class HandoverProtocolViewsTests(TestCase):
    def setUp(self) -> None:
        self.person = Person.objects.create(
            vorname="Mara",
            nachname="Muster",
            email="mara.muster@example.test",
        )
        self.wohnung = Wohnung.objects.create(
            etage=2,
            wohnungsnummer="2.04",
            gebaeudenummer="1",
        )

    def valid_form_data(self) -> dict[str, str]:
        return {
            "wohnung": str(self.wohnung.pk),
            "person": str(self.person.pk),
            "protokoll_typ": ProtokollTyp.MOVE_IN,
            "uebergabe_status": UebergabeStatus.RENOVATED,
            "abnahme_status": AbnahmeStatus.ACCEPTED,
            "zaehlerstand_wasser_kalt": "12.50",
            "zaehlerstand_wasser_warm": "4.75",
            "zaehlerstand_heizung": "155.00",
            "zaehlerstand_strom": "87.25",
        }

    def test_create_page_shows_required_handover_fields(self) -> None:
        response = self.client.get(reverse("wohnungsverwaltung:handover_protocol_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wohnung")
        self.assertContains(response, "Übergabeart")
        self.assertContains(response, "Zählerstände")

    def test_create_requires_all_mandatory_meter_readings(self) -> None:
        data = self.valid_form_data()
        data.pop("zaehlerstand_strom")

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "zaehlerstand_strom", "Dieses Feld ist zwingend erforderlich."
        )
        self.assertFalse(Protokoll.objects.exists())

    def test_create_assigns_protocol_to_apartment_and_type(self) -> None:
        response = self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )

        protocol = Protokoll.objects.get()
        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            ),
        )
        self.assertEqual(protocol.wohnung, self.wohnung)
        self.assertEqual(protocol.person, self.person)
        self.assertEqual(protocol.protokoll_typ, ProtokollTyp.MOVE_IN)
        self.assertEqual(protocol.status, ProtokollStatus.OPEN)
        self.assertEqual(protocol.zaehlerstand_wasser_kalt, Decimal("12.50"))

    def test_detail_shows_the_complete_protocol_for_its_apartment(self) -> None:
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        protocol = Protokoll.objects.get()

        response = self.client.get(
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gebäude 1, Wohnung 2.04")
        self.assertContains(response, "Einzug")
        self.assertContains(response, "In Bearbeitung")
        self.assertContains(response, "12,50")

    def test_edit_keeps_protocol_data_on_the_same_handover(self) -> None:
        protocol = Protokoll.objects.create(
            wohnung=self.wohnung,
            person=self.person,
            protokoll_typ=ProtokollTyp.MOVE_OUT,
            uebergabe_status=UebergabeStatus.UNRENOVATED,
            abnahme_status=AbnahmeStatus.ACCEPTED_WITH_RESERVATION,
            zaehlerstand_wasser_kalt=Decimal("1.00"),
            zaehlerstand_wasser_warm=Decimal("2.00"),
            zaehlerstand_heizung=Decimal("3.00"),
            zaehlerstand_strom=Decimal("4.00"),
        )
        data = self.valid_form_data()
        data["protokoll_typ"] = ProtokollTyp.MOVE_OUT
        data["zaehlerstand_strom"] = "99.90"

        response = self.client.post(
            reverse(
                "wohnungsverwaltung:handover_protocol_edit",
                kwargs={"protocol_id": protocol.pk},
            ),
            data,
        )

        protocol.refresh_from_db()
        self.assertRedirects(
            response,
            reverse(
                "wohnungsverwaltung:handover_protocol_detail",
                kwargs={"protocol_id": protocol.pk},
            ),
        )
        self.assertEqual(protocol.pk, protocol.protokoll_id)
        self.assertEqual(protocol.zaehlerstand_strom, Decimal("99.90"))
