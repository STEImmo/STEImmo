import json
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse

from . import test_protocol_edit as fixtures
from . import views
from .models import HandoverPhotoCleanup, ProtokollStatus, Raum, RaumMerkmal, Raumprotokoll


class InlineRoomRemovalTests(TestCase):
    setUp = fixtures.ProtocolEditPreservationTests.setUp
    valid_form_data = fixtures.ProtocolEditPreservationTests.valid_form_data
    checklist_item_for_photo = fixtures.ProtocolEditPreservationTests.checklist_item_for_photo
    checklist_item_for_photo_without_create = (
        fixtures.ProtocolEditPreservationTests.checklist_item_for_photo_without_create
    )
    photo_upload = staticmethod(fixtures.ProtocolEditPreservationTests.photo_upload)
    payload = fixtures.ProtocolEditPreservationTests.payload

    def removal_payload(self):
        data = self.payload()
        data["rooms-0-raumprotokoll"] = str(self.room.pk)
        data["rooms-0-DELETE"] = "on"
        data["removed_rooms"] = [str(self.room.pk)]
        return data

    def assert_original_room_preserved(self):
        self.assertTrue(self.protocol.raeume.filter(pk=self.room.pk).exists())
        self.assertTrue(self.room.raum_merkmale.filter(pk=self.item.pk).exists())
        self.assertTrue(self.item.fotos.filter(pk=self.photo.pk).exists())
        self.assertTrue(self.photo.datei.storage.exists(self.photo.datei.name))

    def test_room_removal_deletes_room_and_photo_but_keeps_master_and_keys(self):
        room_id = self.room.pk
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.edit_url, self.removal_payload())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.protocol.raeume.filter(pk=room_id).exists())
        self.assertTrue(Raum.objects.filter(pk=self.kitchen.pk).exists())
        self.assertTrue(self.protocol.protokoll_schluessel.filter(pk=self.key.pk).exists())
        self.assertFalse(self.photo.datei.storage.exists(self.photo.datei.name))
        self.assertFalse(HandoverPhotoCleanup.objects.exists())
        detail = self.client.get(response.url)
        self.assertFalse(detail.context["protocol"].raeume.exists())
        edit = self.client.get(self.edit_url)
        self.assertEqual(edit.context["room_formset"].initial_form_count(), 0)

    def test_entire_room_is_removed_including_omitted_points_and_other_rooms_survive(self):
        second_item = RaumMerkmal.objects.create(
            raumprotokoll=self.room, merkmal=self.second_room_feature, wert={"text": "Boden"}
        )
        master = Raum.objects.create(wohnung=self.wohnung, name="Wohnzimmer")
        other_room = Raumprotokoll.objects.create(
            protokoll=self.protocol, raum=master, name=master.name
        )
        other_item = RaumMerkmal.objects.create(
            raumprotokoll=other_room, merkmal=self.living_room_feature, wert={"text": "In Ordnung"}
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.edit_url, self.removal_payload())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.protocol.raeume.filter(pk=self.room.pk).exists())
        self.assertFalse(RaumMerkmal.objects.filter(pk=second_item.pk).exists())
        self.assertTrue(RaumMerkmal.objects.filter(pk=other_item.pk).exists())

    def test_empty_saved_room_can_be_removed_without_checkpoint_id(self):
        master = Raum.objects.create(wohnung=self.wohnung, name="Leerer Raum")
        room = Raumprotokoll.objects.create(protokoll=self.protocol, raum=master, name=master.name)
        data = self.payload()
        data.update(
            {
                "rooms-TOTAL_FORMS": "2",
                "rooms-INITIAL_FORMS": "2",
                "rooms-0-raumprotokoll": str(self.room.pk),
                "rooms-1-raumprotokoll": str(room.pk),
                "rooms-1-raum": str(master.pk),
                "rooms-1-DELETE": "on",
                "removed_rooms": [str(room.pk)],
            }
        )
        response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.protocol.raeume.filter(pk=room.pk).exists())
        self.assertTrue(Raum.objects.filter(pk=master.pk).exists())
        self.assert_original_room_preserved()

    def test_single_checkpoint_deletion_keeps_room_and_remaining_checkpoint(self):
        remaining = RaumMerkmal.objects.create(
            raumprotokoll=self.room, merkmal=self.second_room_feature, wert={"text": "Boden"}
        )
        data = self.payload()
        data["rooms-0-DELETE"] = "on"
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.protocol.raeume.filter(pk=self.room.pk).exists())
        self.assertEqual(list(self.room.raum_merkmale.values_list("pk", flat=True)), [remaining.pk])

    def test_foreign_protocol_room_is_rejected_before_any_changes(self):
        other, room, _item = self.checklist_item_for_photo_without_create()
        data = self.removal_payload()
        data["removed_rooms"] = [str(room.pk)]
        response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("removed_rooms", response.context["form"].errors)
        self.assertTrue(other.raeume.filter(pk=room.pk).exists())
        self.assert_original_room_preserved()

    def test_unknown_room_is_rejected_before_any_changes(self):
        data = self.removal_payload()
        data["removed_rooms"] = [str(uuid4())]
        response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("removed_rooms", response.context["form"].errors)
        self.assert_original_room_preserved()

    def test_confirmed_protocol_cannot_be_modified(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.save()
        response = self.client.post(self.edit_url, self.removal_payload())
        self.assertEqual(response.status_code, 302)
        self.assert_original_room_preserved()

    def test_unauthorized_user_cannot_remove_room(self):
        self.client.logout()
        response = self.client.post(self.edit_url, self.removal_payload())
        self.assertEqual(response.status_code, 302)
        self.assert_original_room_preserved()

    def test_user_without_employee_permission_cannot_remove_room(self):
        user = get_user_model().objects.create_user(username="ordinary-user")
        self.client.force_login(user)
        response = self.client.post(self.edit_url, self.removal_payload())
        self.assertEqual(response.status_code, 403)
        self.assert_original_room_preserved()

    def test_pending_room_removal_is_preserved_in_server_draft(self):
        draft = {
            "version": 1,
            "savedAt": 1_790_000_000_000,
            "fields": {},
            "keys": [],
            "rooms": [
                {
                    "raum": str(self.kitchen.pk),
                    "raumprotokoll": str(self.room.pk),
                    "removed": True,
                    "items": [
                        {
                            "raumprotokoll": {"value": str(self.room.pk), "checked": None},
                            "pruefpunkt": {"value": str(self.item.pk), "checked": None},
                            "DELETE": {"value": "on", "checked": True},
                        }
                    ],
                }
            ],
        }
        response = self.client.post(
            reverse("wohnungsverwaltung:handover_protocol_draft_save"),
            data=json.dumps({"scope": f"edit:{self.protocol.pk}", "draft": draft}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        edit = self.client.get(self.edit_url)
        self.assertEqual(edit.context["server_draft"], draft)
        self.assert_original_room_preserved()

    def test_failed_save_rolls_back_room_and_photo_cleanup(self):
        original = views._save_inline_protocol_entries

        def fail_after_save(*args, **kwargs):
            original(*args, **kwargs)
            raise DatabaseError("simulated failure after inline save")

        with (
            patch(
                "wohnungsverwaltung.views._save_inline_protocol_entries",
                side_effect=fail_after_save,
            ),
            self.captureOnCommitCallbacks(execute=True) as callbacks,
        ):
            response = self.client.post(self.edit_url, self.removal_payload())
        self.assertEqual(response.status_code, 200)
        self.assert_original_room_preserved()
        self.assertFalse(HandoverPhotoCleanup.objects.exists())
        self.assertFalse(callbacks)

    def test_cleanup_failure_keeps_durable_job_after_successful_room_removal(self):
        with (
            patch.object(
                self.photo.datei.storage, "delete", side_effect=OSError("storage unavailable")
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(self.edit_url, self.removal_payload())
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.protocol.raeume.filter(pk=self.room.pk).exists())
        self.assertTrue(self.photo.datei.storage.exists(self.photo.datei.name))
        self.assertTrue(
            HandoverPhotoCleanup.objects.filter(storage_name=self.photo.datei.name).exists()
        )

    def test_edit_card_keeps_stable_room_id_and_removal_checkbox(self):
        response = self.client.get(self.edit_url)
        self.assertContains(response, f'name="removed_rooms" value="{self.room.pk}"')
        self.assertContains(response, "data-room-removal")
        self.assertEqual(
            str(response.context["room_formset"].forms[0]["raumprotokoll"].value()),
            str(self.room.pk),
        )

    def test_removed_room_can_be_replaced_without_deduplicating_against_deleted_photos(self):
        data = self.removal_payload()
        data.update(
            {
                "rooms-TOTAL_FORMS": "2",
                "rooms-1-raum": str(self.kitchen.pk),
                "rooms-1-bereich": "Küche",
                "rooms-1-merkmal": str(self.room_feature.pk),
                "rooms-1-wert": "Neue Feststellung",
                "rooms-1-fotos": self.photo_upload("replacement.png"),
            }
        )
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.edit_url, data)
        self.assertEqual(
            response.status_code, 302, response.context and response.context["room_formset"].errors
        )
        replacement = self.protocol.raeume.get()
        self.assertNotEqual(replacement.pk, self.room.pk)
        item = replacement.raum_merkmale.get()
        self.assertEqual(item.wert["text"], "Neue Feststellung")
        self.assertEqual(item.fotos.count(), 1)
        self.assertTrue(item.fotos.get().datei.storage.exists(item.fotos.get().datei.name))
        self.assertFalse(self.photo.datei.storage.exists(self.photo.datei.name))

    def test_invalid_replacement_room_remains_visible_separate_from_removed_room(self):
        data = self.removal_payload()
        data.update(
            {
                "rooms-TOTAL_FORMS": "2",
                "rooms-1-raum": str(self.kitchen.pk),
                "rooms-1-bereich": "Küche",
                "rooms-1-merkmal": str(self.room_feature.pk),
                "rooms-1-wert": "",
            }
        )
        response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 200)
        groups = response.context["room_form_groups"]
        self.assertEqual(len(groups), 2)
        self.assertTrue(groups[0]["remove_room"])
        self.assertEqual(groups[0]["room_protocol_id"], str(self.room.pk))
        self.assertFalse(groups[1]["remove_room"])
        self.assertEqual(groups[1]["room_protocol_id"], "")
        self.assertIn("wert", groups[1]["checklist_forms"][0].errors)
        self.assert_original_room_preserved()

    def test_new_checkpoint_on_existing_room_keeps_group_after_validation_error(self):
        data = self.payload()
        data.update(
            {
                "rooms-TOTAL_FORMS": "2",
                "rooms-0-raumprotokoll": str(self.room.pk),
                "rooms-1-raumprotokoll": str(self.room.pk),
                "rooms-1-raum": str(self.kitchen.pk),
                "rooms-1-bereich": "Küche",
                "rooms-1-merkmal": str(self.second_room_feature.pk),
                "rooms-1-wert": "",
            }
        )
        response = self.client.post(self.edit_url, data)
        self.assertEqual(response.status_code, 200)
        groups = response.context["room_form_groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["checklist_forms"]), 2)
        self.assertFalse(groups[0]["remove_room"])
        self.assertIn("wert", groups[0]["checklist_forms"][1].errors)
        self.assert_original_room_preserved()
