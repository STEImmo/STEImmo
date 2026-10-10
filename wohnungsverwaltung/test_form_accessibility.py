from html.parser import HTMLParser
from types import SimpleNamespace
from uuid import uuid4

from django import forms
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .forms import (
    BewerbungForm,
    EmployeeMfaCodeForm,
    HandoverKeyForm,
    HandoverProtocolForm,
    MainApplicationForm,
    MerkmalForm,
    RegistrationVerificationForm,
    ResendRegistrationCodeForm,
    RoomChecklistItemForm,
    RoomProtocolForm,
    UserAccountForm,
)
from .models import Bewerbung, Person, Protokoll, Raumprotokoll, RegistrationVerification, Wohnung


class FormMarkup(HTMLParser):
    void_tags = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "wbr"}

    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.stack = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        element = {"tag": tag, "attrs": dict(attrs), "text": ""}
        self.elements.append(element)
        if tag not in self.void_tags:
            self.stack.append(element)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        for element in self.stack:
            element["text"] += data

    def with_id(self, element_id):
        return [element for element in self.elements if element["attrs"].get("id") == element_id]


class FormAccessibilityAssertions:
    def assert_descriptions_resolve(self, markup):
        for element in markup.elements:
            references = element["attrs"].get("aria-describedby", "").split()
            for reference in references:
                with self.subTest(field=element["attrs"].get("name"), reference=reference):
                    targets = markup.with_id(reference)
                    self.assertEqual(len(targets), 1, f"Description {reference} must exist once")
                    self.assertTrue(targets[0]["text"].strip())

    def assert_field_error_linked(self, markup, field):
        targets = markup.with_id(f"{field.auto_id}_error")
        self.assertEqual(len(targets), 1)
        for error in field.errors:
            self.assertIn(str(error), targets[0]["text"])
        described_elements = [
            element
            for element in markup.elements
            if f"{field.auto_id}_error" in element["attrs"].get("aria-describedby", "").split()
        ]
        self.assertTrue(described_elements)


class RegistrationAccessibilityTests(FormAccessibilityAssertions, TestCase):
    def test_password_mismatch_is_described_by_visible_field_error(self):
        response = self.client.post(
            reverse("register"),
            {
                "vorname": "Lina",
                "nachname": "Lang",
                "email": "a11y@example.test",
                "password1": "FjordTanne!4826",
                "password2": "KometBirke!5927",
            },
        )
        self.assertEqual(response.status_code, 200)
        markup = FormMarkup(response.content.decode())
        self.assert_descriptions_resolve(markup)
        self.assert_field_error_linked(markup, response.context["form"]["password2"])
        self.assertEqual(markup.with_id("id_password2")[0]["attrs"]["aria-invalid"], "true")

    def test_empty_required_fields_keep_labels_and_link_each_visible_error(self):
        response = self.client.post(reverse("register"), {"vorname": ""})
        self.assertEqual(response.status_code, 200)
        markup = FormMarkup(response.content.decode())
        self.assert_descriptions_resolve(markup)
        for field in response.context["form"]:
            with self.subTest(field=field.name):
                self.assertTrue(field.errors)
                self.assert_field_error_linked(markup, field)
                labels = [
                    element
                    for element in markup.elements
                    if element["tag"] == "label"
                    and element["attrs"].get("for") == field.id_for_label
                ]
                self.assertEqual(len(labels), 1)
                self.assertIn(field.label, labels[0]["text"])

    def test_unbound_registration_has_no_error_references(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)
        markup = FormMarkup(response.content.decode())
        self.assert_descriptions_resolve(markup)
        self.assertFalse(any(e["attrs"].get("aria-invalid") for e in markup.elements))


class SharedFormAccessibilityTests(FormAccessibilityAssertions, SimpleTestCase):
    def test_prefixed_field_describes_help_and_multiple_errors(self):
        form = forms.Form(data={}, prefix="rooms-0")
        form.fields["name"] = forms.CharField(label="Name", help_text="Name des Raumes")
        form.is_valid()
        form.add_error("name", "Bitte verwenden Sie einen eindeutigen Namen.")
        markup = FormMarkup(
            render_to_string("wohnungsverwaltung/_form_field.html", {"field": form["name"]})
        )
        self.assert_descriptions_resolve(markup)
        self.assert_field_error_linked(markup, form["name"])
        for error in form["name"].errors:
            self.assertEqual(
                markup.with_id("id_rooms-0-name_error")[0]["text"].count(str(error)), 1
            )
        self.assertEqual(
            markup.with_id("id_rooms-0-name_helptext")[0]["text"].strip(), "Name des Raumes"
        )

    def test_unbound_help_text_has_a_resolvable_description(self):
        form = forms.Form()
        form.fields["name"] = forms.CharField(help_text="Name des Raumes")
        markup = FormMarkup(
            render_to_string("wohnungsverwaltung/_form_field.html", {"field": form["name"]})
        )
        self.assert_descriptions_resolve(markup)
        self.assertFalse(markup.with_id("id_name_error"))


class ManualFormAccessibilityTests(FormAccessibilityAssertions, TestCase):
    def test_main_application_upload_errors_and_help_describe_each_input(self):
        application = Bewerbung(person=Person(), wohnung=Wohnung())
        form = MainApplicationForm(data={"action": "submit"}, instance=application)
        self.assertFalse(form.is_valid())
        markup = FormMarkup(
            render_to_string(
                "wohnungsverwaltung/main_application_status.html",
                {"application": application, "form": form},
            )
        )
        self.assert_descriptions_resolve(markup)
        for field in form.visible_fields():
            self.assert_field_error_linked(markup, field)
            self.assertEqual(
                markup.with_id(f"{field.auto_id}_helptext")[0]["text"].strip(), field.help_text
            )

    def test_registration_revocation_checkbox_describes_its_help_text(self):
        account = get_user_model().objects.create_user(
            username="a11y-manager@example.test", is_active=False
        )
        verification = RegistrationVerification(user=account)
        verification.issue_code()
        verification.save()
        form = UserAccountForm(account=account)
        markup = FormMarkup(
            render_to_string("wohnungsverwaltung/user_account_form.html", {"form": form})
        )
        self.assert_descriptions_resolve(markup)
        self.assertEqual(
            markup.with_id("id_revoke_registration_helptext")[0]["text"].strip(),
            form["revoke_registration"].help_text,
        )

    def test_manual_templates_link_errors_including_checkbox_and_radio_groups(self):
        apartment = Wohnung.objects.create(
            gebaeudenummer="1",
            wohnungsnummer="A11Y",
            etage=0,
            groesse_qm=25,
            zimmeranzahl=1,
            kaltmiete=300,
            warmmiete=400,
            kaution=900,
        )
        protocol = Protokoll(wohnung=apartment)
        room = Raumprotokoll(pk=uuid4(), protokoll=protocol, name="Testzimmer")
        contexts = [
            (
                "registration/verify_registration.html",
                {
                    "form": RegistrationVerificationForm(data={}),
                    "resend_form": ResendRegistrationCodeForm(),
                },
            ),
            ("registration/employee_mfa_verify.html", {"form": EmployeeMfaCodeForm(data={})}),
            ("wohnungsverwaltung/user_account_form.html", {"form": UserAccountForm(data={})}),
            (
                "wohnungsverwaltung/_pre_application_fields.html",
                {
                    "form": BewerbungForm(data={}, applicant=Person()),
                },
            ),
            (
                "wohnungsverwaltung/handover_protocol_key_form.html",
                {
                    "form": HandoverKeyForm(data={}),
                    "protocol": protocol,
                },
            ),
            (
                "wohnungsverwaltung/handover_protocol_room_form.html",
                {
                    "form": RoomProtocolForm(data={}, protocol=protocol),
                    "protocol": protocol,
                },
            ),
            (
                "wohnungsverwaltung/handover_protocol_room_detail.html",
                {
                    "form": RoomChecklistItemForm(data={}),
                    "protocol": protocol,
                    "room": room,
                },
            ),
        ]
        for template, context in contexts:
            with self.subTest(template=template):
                form = context["form"]
                self.assertFalse(form.is_valid())
                if template.endswith("user_account_form.html"):
                    form.add_error("roles", "Bitte prüfen Sie die Rollen.")
                    form.add_error("is_active", "Bitte prüfen Sie den Kontostatus.")
                markup = FormMarkup(render_to_string(template, context))
                self.assert_descriptions_resolve(markup)
                for field in form.visible_fields():
                    if field.errors:
                        self.assert_field_error_linked(markup, field)

    def test_handover_errors_resolve_once_for_meter_readings_and_formset_fields(self):
        form = HandoverProtocolForm(data={})
        form.is_valid()
        form.add_error("zaehlerstand_wasser_kalt", "Bitte prüfen Sie den Zählerstand.")
        room_form = forms.Form(data={}, prefix="rooms-0")
        room_form.fields["raum"] = forms.CharField()
        room_form.is_valid()
        key_form = HandoverKeyForm(data={}, prefix="keys-0")
        key_form.is_valid()
        markup = FormMarkup(
            render_to_string(
                "wohnungsverwaltung/_handover_protocol_fields.html",
                {
                    "form": form,
                    "meter_comparison_rows": [{"field": form["zaehlerstand_wasser_kalt"]}],
                    "room_form_groups": [SimpleNamespace(room_form=room_form, checklist_forms=[])],
                    "key_formset": [key_form],
                },
            )
        )
        self.assert_descriptions_resolve(markup)
        self.assert_field_error_linked(markup, form["zaehlerstand_wasser_kalt"])
        self.assert_field_error_linked(markup, room_form["raum"])
        self.assert_field_error_linked(markup, key_form["anzahl"])

    def test_management_help_text_resolves_in_shared_partial(self):
        form = MerkmalForm()
        markup = FormMarkup(
            render_to_string("wohnungsverwaltung/_form_field.html", {"field": form["datentyp"]})
        )
        self.assert_descriptions_resolve(markup)
