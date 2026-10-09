import json

from django.test import TestCase
from django.urls import reverse

from . import test_handover_export as fixtures
from .models import ProtokollEntwurf


class HandoverDraftValidationTests(TestCase):
    setUp = fixtures.HandoverExportTests.setUp

    def payload(self):
        return {
            "scope": "create",
            "draft": {"version": 1, "fields": {}, "rooms": [], "keys": [], "savedAt": 123},
        }

    def post(self, body):
        return self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_draft_save"),
            body,
            content_type="application/json",
        )

    def existing_draft(self):
        payload = self.payload()
        payload["draft"]["fields"]["note"] = {"value": "Gespeicherte Feststellung"}
        self.assertEqual(self.post(json.dumps(payload)).status_code, 200)
        return ProtokollEntwurf.objects.get()

    def assert_rejected_without_changes(self, body, draft):
        self.client.raise_request_exception = False
        response = self.post(body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Ungültige Entwurfsdaten.")
        current = ProtokollEntwurf.objects.get(pk=draft.pk)
        self.assertEqual(current.daten, draft.daten)
        self.assertEqual(current.updated_at, draft.updated_at)
        self.assertEqual(ProtokollEntwurf.objects.count(), 1)

    def test_invalid_utf8_is_rejected_and_preserves_existing_draft(self):
        self.assert_rejected_without_changes(
            b'{"scope":"create","draft":"\xff"}', self.existing_draft()
        )

    def test_nonfinite_numbers_are_rejected_and_preserve_existing_draft(self):
        draft = self.existing_draft()
        for literal in ["NaN", "Infinity", "-Infinity", "1e999"]:
            with self.subTest(number=literal):
                body = json.dumps(self.payload()).replace('"savedAt": 123', f'"savedAt": {literal}')
                self.assert_rejected_without_changes(body, draft)

    def test_null_characters_in_values_and_keys_are_rejected(self):
        draft = self.existing_draft()
        for field in [{"note": {"value": "null\x00character"}}, {"null\x00key": "value"}]:
            with self.subTest(field=field):
                payload = self.payload()
                payload["draft"]["fields"] = field
                self.assert_rejected_without_changes(json.dumps(payload), draft)

    def test_unpaired_surrogates_in_values_and_keys_are_rejected(self):
        draft = self.existing_draft()
        for field in [{"note": {"value": "\ud800"}}, {"\udfff": "value"}]:
            with self.subTest(field=field):
                payload = self.payload()
                payload["draft"]["fields"] = field
                self.assert_rejected_without_changes(json.dumps(payload), draft)

    def test_excessively_nested_json_is_rejected_and_preserves_existing_draft(self):
        body = '{"scope":"create","draft":' + "[" * 1500 + "0" + "]" * 1500 + "}"
        self.assert_rejected_without_changes(body, self.existing_draft())

    def test_ordinary_json_syntax_error_is_still_rejected(self):
        self.assert_rejected_without_changes(b"{invalid", self.existing_draft())

    def test_valid_unicode_and_literal_escape_text_are_saved(self):
        payload = self.payload()
        payload["draft"]["fields"]["note"] = {
            "value": "Küche, Prüfung 😀 und die Zeichenfolge \\u0000"
        }
        response = self.post(json.dumps(payload))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProtokollEntwurf.objects.get().daten, payload["draft"])
