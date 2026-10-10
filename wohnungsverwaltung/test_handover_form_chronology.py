from datetime import UTC, datetime
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from . import tests as fixtures
from .models import AbnahmeStatus, Protokoll, ProtokollStatus, ProtokollTyp, UebergabeStatus


class HandoverFormChronologyTests(TestCase):
    setUp = fixtures.HandoverProtocolViewsTests.setUp
    valid_form_data = fixtures.HandoverProtocolViewsTests.valid_form_data

    def create_protocol(self, year, protocol_type=ProtokollTyp.MOVE_IN):
        return Protokoll.objects.create(
            wohnung=self.wohnung,
            person=self.person,
            protokoll_typ=protocol_type,
            status=ProtokollStatus.SIGNED
            if protocol_type == ProtokollTyp.MOVE_IN
            else ProtokollStatus.OPEN,
            uebergabe_zeitpunkt=datetime(year, 6, 1, 10, tzinfo=UTC),
            uebergabe_status=UebergabeStatus.RENOVATED,
            abnahme_status=AbnahmeStatus.ACCEPTED,
            zaehlerstand_strom=year,
        )

    def test_edit_form_uses_same_historical_reference_as_detail(self):
        historical = self.create_protocol(2024)
        future = self.create_protocol(2026)
        move_out = self.create_protocol(2025, ProtokollTyp.MOVE_OUT)

        detail = self.client.get(
            reverse("wohnungsverwaltung:handover_protocol_detail", args=[move_out.pk])
        )
        response = self.client.get(
            reverse("wohnungsverwaltung:handover_protocol_edit", args=[move_out.pk])
        )

        self.assertEqual(detail.context["move_in_reference"].pk, historical.pk)
        self.assertEqual(response.context["move_in_reference"].pk, historical.pk)
        self.assertNotEqual(response.context["move_in_reference"].pk, future.pk)
        self.assertEqual(response.context["meter_comparison_rows"][3]["old_reading"], Decimal(2024))

    def test_invalid_creation_uses_submitted_handover_date_for_comparison(self):
        historical = self.create_protocol(2024)
        self.create_protocol(2026)
        payload = self.valid_form_data() | {
            "protokoll_typ": ProtokollTyp.MOVE_OUT,
            "uebergabe_zeitpunkt": "2025-06-01T12:00",
            "mieter_zukuenftige_anschrift": "",
        }

        response = self.client.post(reverse("wohnungsverwaltung:handover_protocol_create"), payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["move_in_reference"].pk, historical.pk)

    def test_invalid_edit_uses_changed_date_instead_of_the_saved_date(self):
        historical = self.create_protocol(2024)
        self.create_protocol(2026)
        move_out = self.create_protocol(2027, ProtokollTyp.MOVE_OUT)
        payload = self.valid_form_data() | {
            "protokoll_typ": ProtokollTyp.MOVE_OUT,
            "uebergabe_zeitpunkt": "2025-06-01T12:00",
            "mieter_zukuenftige_anschrift": "",
        }

        response = self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_edit", args=[move_out.pk]), payload
        )

        self.assertEqual(response.context["move_in_reference"].pk, historical.pk)
        move_out.refresh_from_db()
        self.assertEqual(move_out.uebergabe_zeitpunkt.year, 2027)

    def test_dynamic_reload_uses_current_handover_time_on_both_forms(self):
        historical = self.create_protocol(2024)
        future = self.create_protocol(2026)
        move_out = self.create_protocol(2027, ProtokollTyp.MOVE_OUT)
        for url in (
            reverse("wohnungsverwaltung:handover_protocol_create"),
            reverse("wohnungsverwaltung:handover_protocol_edit", args=[move_out.pk]),
        ):
            for year, expected in ((2025, historical), (2027, future)):
                with self.subTest(url=url, year=year):
                    response = self.client.get(
                        url,
                        {
                            "wohnung": self.wohnung.pk,
                            "person": self.person.pk,
                            "uebergabe_zeitpunkt": f"{year}-06-01T12:00",
                        },
                    )

                    self.assertEqual(response.context["move_in_reference"].pk, expected.pk)

    def test_missing_predecessor_keeps_documented_same_person_fallback(self):
        future = self.create_protocol(2026)
        move_out = self.create_protocol(2025, ProtokollTyp.MOVE_OUT)

        response = self.client.get(
            reverse("wohnungsverwaltung:handover_protocol_edit", args=[move_out.pk])
        )

        self.assertEqual(response.context["move_in_reference"].pk, future.pk)

    def test_other_tenant_is_not_used_as_historical_reference(self):
        historical = self.create_protocol(2024)
        other_tenant = self.create_protocol(2025)
        other_tenant.person = self.employee
        other_tenant.save(update_fields=["person"])
        move_out = self.create_protocol(2026, ProtokollTyp.MOVE_OUT)

        response = self.client.get(
            reverse("wohnungsverwaltung:handover_protocol_edit", args=[move_out.pk])
        )

        self.assertEqual(response.context["move_in_reference"].pk, historical.pk)

    def test_invalid_date_remains_a_form_error_without_changing_protocol(self):
        self.create_protocol(2024)
        move_out = self.create_protocol(2025, ProtokollTyp.MOVE_OUT)
        payload = self.valid_form_data() | {"uebergabe_zeitpunkt": "invalid"}

        response = self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_edit", args=[move_out.pk]), payload
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("uebergabe_zeitpunkt", response.context["form"].errors)
        move_out.refresh_from_db()
        self.assertEqual(move_out.uebergabe_zeitpunkt.year, 2025)
