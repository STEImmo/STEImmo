from html.parser import HTMLParser

from django.test import TestCase
from django.urls import reverse

from . import test_management as fixtures
from .models import Raum, Schluessel, Wohnung


class FormStructureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.stack = []
        self.nested_forms = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            if self.stack:
                self.nested_forms.append(attrs)
            form = {"attrs": attrs, "controls": []}
            self.forms.append(form)
            self.stack.append(form)
        elif tag in {"input", "select", "textarea", "button"} and self.stack:
            self.stack[-1]["controls"].append({"tag": tag, **attrs})

    def handle_endtag(self, tag):
        if tag == "form" and self.stack:
            self.stack.pop()


class ApartmentRoomFormTests(TestCase):
    setUp = fixtures.ManagementViewTests.setUp
    wohnung_payload = fixtures.ManagementViewTests.wohnung_payload

    def create_unit(self):
        return Wohnung.objects.create(
            **{
                name: value
                for name, value in self.wohnung_payload().items()
                if not name.startswith("schluessel-")
            }
        )

    def rendered_forms(self, unit):
        self.client.force_login(self.employee_user)
        response = self.client.get(reverse("verwaltung:wohnung_edit", args=[unit.pk]))
        self.assertEqual(response.status_code, 200)
        parser = FormStructureParser()
        parser.feed(response.content.decode())
        self.assertEqual(parser.nested_forms, [], "The rendered page must not nest forms.")
        return parser.forms

    def test_master_data_and_keys_share_one_form_with_zero_one_or_many_rooms(self):
        for count in (0, 1, 3):
            with self.subTest(room_count=count):
                unit = self.create_unit()
                for index in range(count):
                    Raum.objects.create(wohnung=unit, name=f"Raum {index + 1}")
                Schluessel.objects.create(wohnung=unit, bezeichnung="Haustür", status="in_use")
                forms = self.rendered_forms(unit)
                master_forms = [
                    form
                    for form in forms
                    if any(control.get("name") == "wohnungsnummer" for control in form["controls"])
                ]
                self.assertEqual(len(master_forms), 1)
                names = {control.get("name") for control in master_forms[0]["controls"]}
                self.assertTrue(
                    {
                        "kaltmiete",
                        "warmmiete",
                        "kaution",
                        "zaehlernummer_strom",
                        "schluessel-TOTAL_FORMS",
                        "schluessel-0-schluessel_id",
                        "schluessel-0-anzahl",
                        "csrfmiddlewaretoken",
                    }.issubset(names)
                )
                self.assertTrue(
                    any(
                        control["tag"] == "button" and control.get("type") == "submit"
                        for control in master_forms[0]["controls"]
                    )
                )

    def test_first_and_following_room_buttons_delete_only_the_selected_room(self):
        unit = self.create_unit()
        rooms = [Raum.objects.create(wohnung=unit, name=name) for name in ("Bad", "Küche")]
        before = Wohnung.objects.filter(pk=unit.pk).values().get()
        forms = self.rendered_forms(unit)
        for room in rooms:
            with self.subTest(room=room.name):
                url = reverse("verwaltung:raum_delete", args=[unit.pk, room.pk])
                delete_form = next(form for form in forms if form["attrs"].get("action") == url)
                self.assertEqual(delete_form["attrs"].get("method"), "post")
                names = {
                    control.get("name")
                    for control in delete_form["controls"]
                    if control.get("name")
                }
                self.assertEqual(names, {"csrfmiddlewaretoken"})
                self.assertTrue(
                    any(
                        control["tag"] == "button" and control.get("type") == "submit"
                        for control in delete_form["controls"]
                    )
                )
                response = self.client.post(url)
                self.assertEqual(response.status_code, 302)
                self.assertFalse(Raum.objects.filter(pk=room.pk).exists())
                self.assertEqual(Wohnung.objects.filter(pk=unit.pk).values().get(), before)

    def test_master_data_and_keys_can_still_be_saved_with_existing_rooms(self):
        unit = self.create_unit()
        room = Raum.objects.create(wohnung=unit, name="Küche")
        self.rendered_forms(unit)
        payload = self.wohnung_payload() | {
            "warmmiete": "850.00",
            "zaehlernummer_strom": "NEU-4",
            "schluessel-TOTAL_FORMS": "1",
            "schluessel-0-schluessel_id": "",
            "schluessel-0-bezeichnung": "Haustür",
            "schluessel-0-anzahl": "2",
            "schluessel-0-aufschrift": "H1",
            "schluessel-0-status": "in_use",
        }
        response = self.client.post(reverse("verwaltung:wohnung_edit", args=[unit.pk]), payload)
        self.assertEqual(response.status_code, 302)
        unit.refresh_from_db()
        self.assertEqual(str(unit.warmmiete), "850.00")
        self.assertEqual(unit.zaehlernummer_strom, "NEU-4")
        self.assertEqual(unit.schluessel.get().anzahl, 2)
        self.assertTrue(Raum.objects.filter(pk=room.pk).exists())
