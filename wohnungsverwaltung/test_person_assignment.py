from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from .access import ROLE_APPLICANT, ROLE_EMPLOYEE, ROLE_USER_MANAGEMENT
from .forms import HandoverProtocolForm
from .models import Person, Protokoll, ProtokollStatus, Wohnung


class PersonAssignmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = get_user_model().objects.create_user(username="employee168")
        cls.employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        cls.applicant = get_user_model().objects.create_user(username="applicant168")
        cls.applicant.groups.add(Group.objects.get(name=ROLE_APPLICANT))
        cls.first = Wohnung.objects.create(gebaeudenummer="A", wohnungsnummer="101")
        cls.second = Wohnung.objects.create(gebaeudenummer="A", wohnungsnummer="102")
        cls.person = Person.objects.create(
            vorname="Demo",
            nachname="Einzug",
            email="einzug168@example.test",
            user=cls.applicant,
        )

    def setUp(self):
        self.client.force_login(self.employee)
        self.url = reverse("verwaltung:person_assignment", args=[self.second.pk, self.person.pk])
        self.overview = reverse("verwaltung:wohnung_personen", args=[self.second.pk])

    def assign(self, previous="", **kwargs):
        return self.client.post(
            self.url,
            {
                "previous_wohnung": previous,
                "confirmed": "on",
                **kwargs,
            },
        )

    def protocol(self, status):
        return Protokoll.objects.create(
            person=self.person,
            wohnung=self.first,
            status=status,
            protokoll_typ="move_in",
            uebergabe_status="renovated",
            abnahme_status="accepted",
        )

    def test_anonymous_and_applicant_cannot_read_or_write(self):
        for user, status in [(None, 302), (self.applicant, 403)]:
            self.client.logout()
            if user:
                self.client.force_login(user)
            for method, url in [("get", self.overview), ("get", self.url), ("post", self.url)]:
                with self.subTest(user=user, method=method, url=url):
                    self.assertEqual(getattr(self.client, method)(url).status_code, status)
        self.person.refresh_from_db()
        self.assertIsNone(self.person.wohnung_id)

    def test_direct_employee_permission_is_sufficient(self):
        self.applicant.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="immobilien",
                codename="access_employee_area",
            )
        )
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_selection_and_get_do_not_assign(self):
        response = self.client.get(self.overview, {"person": self.person.pk})
        self.assertRedirects(response, self.url)
        self.assertContains(self.client.get(self.url), "Bewerber")
        self.person.refresh_from_db()
        self.assertIsNone(self.person.wohnung_id)

    def test_assignment_enables_only_correct_apartment_and_keeps_roles_and_status(self):
        groups = list(self.applicant.groups.values_list("pk", flat=True))
        self.assertRedirects(self.assign(), self.overview)
        self.person.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.person.wohnung_id, self.second.pk)
        self.assertEqual(self.second.status, "free")
        self.assertEqual(list(self.applicant.groups.values_list("pk", flat=True)), groups)
        self.assertEqual(self.person.user_id, self.applicant.pk)
        self.assertTrue(self.applicant.has_perm("immobilien.access_applicant_area"))
        for apartment, expected in [(self.second, True), (self.first, False)]:
            form = HandoverProtocolForm(wohnung_id=str(apartment.pk))
            self.assertEqual(
                form.fields["person"].queryset.filter(pk=self.person.pk).exists(), expected
            )
        foreign = HandoverProtocolForm(
            {"wohnung": self.first.pk, "person": self.person.pk},
            wohnung_id=str(self.first.pk),
        )
        self.assertFalse(foreign.is_valid())
        self.assertIn("person", foreign.errors)

    def test_explicit_confirmation_required(self):
        self.assertContains(self.assign(confirmed=""), "Dieses Feld ist zwingend erforderlich")
        self.person.refresh_from_db()
        self.assertIsNone(self.person.wohnung_id)

    def test_stale_assignment_rejected(self):
        Person.objects.filter(pk=self.person.pk).update(wohnung=self.first)
        self.assertContains(self.assign(), "zwischenzeitlich geändert")
        self.person.refresh_from_db()
        self.assertEqual(self.person.wohnung_id, self.first.pk)

    def test_open_and_blocked_protocols_prevent_move(self):
        Person.objects.filter(pk=self.person.pk).update(wohnung=self.first)
        protocol = self.protocol(ProtokollStatus.OPEN)
        for status in [ProtokollStatus.OPEN, ProtokollStatus.BLOCKED]:
            protocol.status = status
            protocol.save()
            self.assertContains(self.assign(str(self.first.pk)), "offene oder gesperrte Protokolle")
            self.person.refresh_from_db()
            self.assertEqual(self.person.wohnung_id, self.first.pk)

    def test_signed_protocol_unchanged_on_move(self):
        Person.objects.filter(pk=self.person.pk).update(wohnung=self.first)
        protocol = self.protocol(ProtokollStatus.SIGNED)
        before = Protokoll.objects.values().get(pk=protocol.pk)
        self.assertContains(self.client.get(self.url), "Wohnungswechsel")
        self.assertRedirects(self.assign(str(self.first.pk)), self.overview)
        self.assertEqual(Protokoll.objects.values().get(pk=protocol.pk), before)

    def test_unknown_person_or_apartment_and_invalid_selection(self):
        for args in [(self.second.pk, uuid4()), (uuid4(), self.person.pk)]:
            self.assertEqual(
                self.client.post(reverse("verwaltung:person_assignment", args=args)).status_code,
                404,
            )
        response = self.client.get(self.overview, {"person": "invalid"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("person", response.context["form"].errors)

    def test_missing_assignment_links_to_management(self):
        response = self.client.get(
            reverse("wohnungsverwaltung:handover_protocol_create"),
            {
                "wohnung": self.second.pk,
            },
        )
        self.assertContains(response, "Dieser Wohnung ist keine Person zugeordnet")
        self.assertContains(response, self.overview)

    def test_existing_account_link_and_roles_are_visible_only_to_user_managers(self):
        account_url = reverse("verwaltung:user_account_edit", args=[self.applicant.pk])
        self.assertNotContains(self.client.get(self.url), account_url)
        self.employee.groups.add(Group.objects.get(name=ROLE_USER_MANAGEMENT))
        response = self.client.get(self.url)
        self.assertContains(response, account_url)
        self.assertContains(response, "Bewerber")
        self.assertContains(response, "Mieter")

    def test_person_without_account_reuses_account_creation(self):
        self.person.user = None
        self.person.save()
        self.employee.groups.add(Group.objects.get(name=ROLE_USER_MANAGEMENT))
        account_url = reverse("verwaltung:user_account_create")
        self.assertContains(self.client.get(self.url), f"{account_url}?person={self.person.pk}")
        response = self.client.get(account_url, {"person": self.person.pk})
        self.assertEqual(str(response.context["form"]["person"].value()), str(self.person.pk))

    def test_assignment_requires_csrf(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.employee)
        self.assertEqual(client.post(self.url, {"confirmed": "on"}).status_code, 403)

    def test_simulated_move_in_for_101_and_102_through_management(self):
        employee_person = Person.objects.create(
            vorname="Demo",
            nachname="Verwaltung",
            email="verwaltung168@example.test",
            is_employee=True,
            user=self.employee,
        )
        create_url = reverse("wohnungsverwaltung:handover_protocol_create")
        for apartment in [self.first, self.second]:
            with self.subTest(apartment=apartment.wohnungsnummer):
                for field in [
                    "zaehlernummer_wasser_kalt",
                    "zaehlernummer_wasser_warm",
                    "zaehlernummer_heizung",
                    "zaehlernummer_strom",
                ]:
                    setattr(apartment, field, f"{apartment.wohnungsnummer}-{field}")
                apartment.save()
                person = Person.objects.create(
                    vorname="Fiktiv",
                    nachname=apartment.wohnungsnummer,
                    email=f"demo{apartment.wohnungsnummer}@example.test",
                )
                assignment_url = reverse(
                    "verwaltung:person_assignment",
                    args=[apartment.pk, person.pk],
                )
                response = self.client.post(assignment_url, {"confirmed": "on"})
                self.assertRedirects(
                    response,
                    reverse(
                        "verwaltung:wohnung_personen",
                        args=[apartment.pk],
                    ),
                )
                response = self.client.get(
                    create_url,
                    {
                        "wohnung": apartment.pk,
                        "person": person.pk,
                    },
                )
                self.assertEqual(str(response.context["form"]["person"].value()), str(person.pk))
                payload = {
                    "wohnung": str(apartment.pk),
                    "person": str(person.pk),
                    "protokoll_typ": "move_in",
                    "uebergabe_zeitpunkt": "2026-10-29T10:30",
                    "vermieter_name": str(employee_person),
                    "uebergabe_status": "renovated",
                    "abnahme_status": "accepted",
                    "heizungsablesungen": "Keine Zusatzablesung",
                    "zaehlerstand_wasser_kalt": "1",
                    "zaehlerstand_wasser_warm": "2",
                    "zaehlerstand_heizung": "3",
                    "zaehlerstand_strom": "4",
                    "rooms-TOTAL_FORMS": "0",
                    "rooms-INITIAL_FORMS": "0",
                    "keys-TOTAL_FORMS": "0",
                    "keys-INITIAL_FORMS": "0",
                }
                response = self.client.post(create_url, payload)
                self.assertEqual(response.status_code, 302)
                protocol = Protokoll.objects.get(person=person)
                self.assertEqual(protocol.wohnung_id, apartment.pk)
                self.assertEqual(protocol.protokoll_typ, "move_in")
