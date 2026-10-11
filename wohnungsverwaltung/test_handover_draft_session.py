import json
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from . import tests as fixtures
from .access import ROLE_EMPLOYEE
from .models import Protokoll, ProtokollEntwurf


class DraftKeyParser(HTMLParser):
    key = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "form" and attributes.get("id") == "handover-protocol-form":
            self.key = attributes.get("data-draft-storage-key")


class HandoverDraftSessionTests(TestCase):
    setUp = fixtures.HandoverProtocolViewsTests.setUp
    valid_form_data = fixtures.HandoverProtocolViewsTests.valid_form_data
    draft_data = fixtures.HandoverProtocolViewsTests.draft_data

    def storage_key(self, client=None, protocol=None):
        client = client or self.client
        url = (
            reverse("wohnungsverwaltung:handover_protocol_edit", args=[protocol.pk])
            if protocol
            else reverse("wohnungsverwaltung:handover_protocol_create")
        )
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        parser = DraftKeyParser()
        parser.feed(response.content.decode())
        self.assertTrue(parser.key, "The form must provide its session-bound local draft key.")
        self.assertNotContains(response, client.session.session_key)
        self.assertNotEqual(parser.key, "handover-protocol-draft:create")
        return parser.key

    def create_protocol(self):
        response = self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_create"), self.valid_form_data()
        )
        self.assertEqual(response.status_code, 302)
        return Protokoll.objects.get()

    def test_reloading_same_form_in_same_session_keeps_local_key(self):
        self.assertEqual(self.storage_key(), self.storage_key())

    def test_create_and_edit_forms_have_different_local_keys(self):
        protocol = self.create_protocol()
        self.assertNotEqual(self.storage_key(), self.storage_key(protocol=protocol))
        self.assertEqual(self.storage_key(protocol=protocol), self.storage_key(protocol=protocol))

    def test_separate_session_of_same_account_has_different_local_key(self):
        other_session = Client()
        other_session.force_login(self.employee_user)
        self.assertNotEqual(self.storage_key(), self.storage_key(other_session))

    def test_account_switch_changes_local_keys_for_create_and_edit(self):
        protocol = self.create_protocol()
        before = (self.storage_key(), self.storage_key(protocol=protocol))
        other_employee = get_user_model().objects.create_user(username="other-employee")
        other_employee.groups.add(Group.objects.get(name=ROLE_EMPLOYEE))
        self.client.force_login(other_employee)
        after = (self.storage_key(), self.storage_key(protocol=protocol))
        for original, switched in zip(before, after, strict=True):
            self.assertNotEqual(original, switched)

    def test_logout_and_new_login_do_not_reuse_previous_local_key(self):
        before = self.storage_key()
        self.client.post(reverse("logout"))
        self.client.force_login(self.employee_user)
        self.assertNotEqual(before, self.storage_key())

    def test_successful_create_clears_matching_local_and_server_drafts(self):
        key = self.storage_key()
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_draft_save"),
            json.dumps({"scope": "create", "draft": self.draft_data()}),
            content_type="application/json",
        )
        self.assertTrue(ProtokollEntwurf.objects.exists())
        protocol = self.create_protocol()
        self.assertFalse(ProtokollEntwurf.objects.exists())
        detail_url = reverse("wohnungsverwaltung:handover_protocol_detail", args=[protocol.pk])
        response = self.client.get(detail_url)
        self.assertContains(response, f'data-draft-key-to-clear="{key}"')
        self.assertNotContains(self.client.get(detail_url), "data-draft-key-to-clear=")

    def test_successful_edit_clears_matching_local_and_server_drafts(self):
        protocol = self.create_protocol()
        key = self.storage_key(protocol=protocol)
        self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_draft_save"),
            json.dumps({"scope": f"edit:{protocol.pk}", "draft": self.draft_data()}),
            content_type="application/json",
        )
        response = self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_edit", args=[protocol.pk]),
            self.valid_form_data() | {"zaehlerstand_strom": "99.00"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProtokollEntwurf.objects.exists())
        response = self.client.get(response.url)
        self.assertContains(response, f'data-draft-key-to-clear="{key}"')
