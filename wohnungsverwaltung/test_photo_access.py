"""Rollen- und Objektgrenzen der Wohnungs- und Übergabefotos (#140)."""

from io import BytesIO
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.fields.files import FieldFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from .access import ROLE_APPLICANT, ROLE_EMPLOYEE, ROLE_TENANT
from .models import (
    AbnahmeStatus,
    ApartmentPhoto,
    Merkmal,
    MerkmalDatentyp,
    Person,
    Protokoll,
    ProtokollStatus,
    ProtokollTyp,
    Raum,
    RaumMerkmalFoto,
    UebergabeStatus,
    Wohnung,
    WohnungStatus,
)


class PhotoAccessTests(TestCase):
    def setUp(self):
        self.media_root = self.enterContext(TemporaryDirectory())
        self.enterContext(self.settings(MEDIA_ROOT=self.media_root))
        self.employee = self.create_user("employee", ROLE_EMPLOYEE)
        self.applicant = self.create_user("applicant-a", ROLE_APPLICANT)
        self.other_applicant = self.create_user("applicant-b", ROLE_APPLICANT)
        self.tenant = self.create_user("tenant", ROLE_TENANT)
        self.staff = self.create_user("staff", is_staff=True)
        self.person = Person.objects.create(
            user=self.tenant, vorname="Test", nachname="Mieter", email="tenant@example.test"
        )
        self.units = {}
        self.apartment_photos = {}
        self.expected_contents = {}
        for status, color in (
            (WohnungStatus.FREE, "red"),
            (WohnungStatus.TAKEN, "green"),
            (WohnungStatus.BLOCKED, "blue"),
        ):
            unit = Wohnung.objects.create(
                gebaeudenummer="1", wohnungsnummer=f"photo-{status}", status=status
            )
            contents = self.image_contents(color, "JPEG")
            photo = ApartmentPhoto.objects.create(
                apartment=unit, image=SimpleUploadedFile("wohnung.jpg", contents)
            )
            self.units[status] = unit
            self.apartment_photos[status] = photo
            self.expected_contents[self.apartment_url(photo)] = contents
        self.feature = Merkmal.objects.create(
            bereich="Zimmer", bezeichnung="Fenster", datentyp=MerkmalDatentyp.OK
        )
        self.chains = [self.create_handover("red"), self.create_handover("blue")]

    @staticmethod
    def create_user(name, role=None, **kwargs):
        user = get_user_model().objects.create_user(username=f"{name}@example.test", **kwargs)
        if role:
            user.groups.add(Group.objects.get(name=role))
        return user

    @staticmethod
    def image_contents(color="white", image_format="PNG"):
        output = BytesIO()
        Image.new("RGB", (8, 8), color).save(output, image_format)
        return output.getvalue()

    def upload(self):
        return SimpleUploadedFile("neu.png", self.image_contents(), content_type="image/png")

    def create_handover(self, color):
        unit = self.units[WohnungStatus.TAKEN]
        protocol = Protokoll.objects.create(
            wohnung=unit,
            person=self.person,
            protokoll_typ=ProtokollTyp.MOVE_IN,
            uebergabe_status=UebergabeStatus.RENOVATED,
            abnahme_status=AbnahmeStatus.ACCEPTED,
        )
        master_room = Raum.objects.create(wohnung=unit, name=f"Zimmer {color}")
        room = protocol.raeume.create(raum=master_room, name=master_room.name)
        item = room.raum_merkmale.create(merkmal=self.feature, wert={"text": "Testfoto"})
        contents = self.image_contents(color)
        photo = item.fotos.create(
            datei=SimpleUploadedFile("uebergabe.png", contents),
            content_type="image/png",
            dateigroesse=len(contents),
        )
        chain = (protocol, room, item, photo)
        self.expected_contents[self.handover_url("view", chain)] = contents
        return chain

    @staticmethod
    def apartment_url(photo):
        return reverse("wohnungsverwaltung_public:apartment_photo", args=[photo.pk])

    def handover_url(self, action, chain=None):
        chain = self.chains[0] if chain is None else chain
        ids = [obj.pk for obj in chain]
        if action == "upload":
            ids = ids[:3]
        return reverse(
            f"wohnungsverwaltung:handover_protocol_checklist_item_photo_{action}", args=ids
        )

    def assert_photo(self, url):
        response = self.client.get(url)
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), self.expected_contents[url])
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertIn(response["Content-Type"], ("image/jpeg", "image/png"))
            self.assertIn("private", response.get("Cache-Control", ""))
            self.assertIn("no-store", response.get("Cache-Control", ""))
        finally:
            if not response.closed:
                response.close()

    def photo_state(self):
        return (
            list(ApartmentPhoto.objects.order_by("pk").values_list("pk", "image")),
            list(RaumMerkmalFoto.objects.order_by("pk").values_list("pk", "datei")),
            sorted(
                (str(path.relative_to(self.media_root)), path.read_bytes())
                for path in Path(self.media_root).rglob("*")
                if path.is_file()
            ),
        )

    def assert_refused(self, url, status, method="get", data=None, client=None):
        client = self.client if client is None else client
        before = self.photo_state()
        with patch.object(FieldFile, "open", side_effect=AssertionError("Private Datei geöffnet")):
            response = getattr(client, method)(url, data or {})
            self.assertEqual(response.status_code, status)
            self.assertFalse(response.streaming)
            if status == 302:
                self.assertRedirects(
                    response, f"{reverse('login')}?next={url}", fetch_redirect_response=False
                )
        self.assertEqual(self.photo_state(), before)

    def assert_employee_endpoints_refused(self, status):
        photo = self.apartment_photos[WohnungStatus.TAKEN]
        management = reverse("verwaltung:apartment_photos", args=[photo.apartment_id])
        deletion = reverse("verwaltung:apartment_photo_delete", args=[photo.apartment_id, photo.pk])
        self.assert_refused(management, status)
        self.assert_refused(management, status, "post", {"image": self.upload()})
        self.assert_refused(deletion, status, "post")
        self.assert_refused(self.handover_url("view"), status)
        self.assert_refused(self.handover_url("upload"), status, "post", {"fotos": self.upload()})
        self.assert_refused(self.handover_url("delete"), status, "post")

    def test_apartment_photo_visibility_follows_status_for_all_public_roles(self):
        for user in (None, self.applicant, self.other_applicant, self.tenant, self.staff):
            with self.subTest(user=user):
                self.client.logout()
                if user:
                    self.client.force_login(user)
                self.assert_photo(self.apartment_url(self.apartment_photos[WohnungStatus.FREE]))
                for status in (WohnungStatus.TAKEN, WohnungStatus.BLOCKED):
                    self.assert_refused(self.apartment_url(self.apartment_photos[status]), 404)

    def test_employee_can_read_each_apartment_photo_including_unavailable_units(self):
        self.client.force_login(self.employee)
        for photo in self.apartment_photos.values():
            with self.subTest(photo=photo.pk):
                self.assert_photo(self.apartment_url(photo))

    def test_all_photo_management_and_handover_endpoints_require_employee_permission(self):
        self.assert_employee_endpoints_refused(302)
        for user in (self.applicant, self.other_applicant, self.tenant, self.staff):
            with self.subTest(user=user):
                self.client.force_login(user)
                self.assert_employee_endpoints_refused(403)

    def test_employee_can_read_handover_photos_in_all_protocol_states_without_caching(self):
        self.client.force_login(self.employee)
        protocol = self.chains[0][0]
        for status in ProtokollStatus.values:
            with self.subTest(status=status):
                Protokoll.objects.filter(pk=protocol.pk).update(status=status)
                for chain in self.chains:
                    self.assert_photo(self.handover_url("view", chain))

    def test_tenant_cannot_read_even_their_own_signed_raw_handover_photos(self):
        Protokoll.objects.update(status=ProtokollStatus.SIGNED)
        self.client.force_login(self.tenant)
        for chain in self.chains:
            self.assert_refused(self.handover_url("view", chain), 403)

    def test_mixed_handover_ids_cannot_read_delete_or_upload_photos(self):
        self.client.force_login(self.employee)
        for choices in product((0, 1), repeat=4):
            if len(set(choices)) == 1:
                continue
            chain = tuple(self.chains[choice][index] for index, choice in enumerate(choices))
            with self.subTest(choices=choices):
                self.assert_refused(self.handover_url("view", chain), 404)
                self.assert_refused(self.handover_url("delete", chain), 404, "post")
        for choices in product((0, 1), repeat=3):
            if len(set(choices)) == 1:
                continue
            chain = tuple(self.chains[choice][index] for index, choice in enumerate(choices))
            with self.subTest(upload_choices=choices):
                self.assert_refused(
                    self.handover_url("upload", chain), 404, "post", {"fotos": self.upload()}
                )

    def test_unknown_photo_and_parent_ids_return_not_found(self):
        self.client.force_login(self.employee)
        unknown_photo = ApartmentPhoto(pk=uuid4())
        self.assert_refused(self.apartment_url(unknown_photo), 404)
        for index in range(4):
            chain = list(self.chains[0])
            chain[index] = type(chain[index])(pk=uuid4())
            with self.subTest(index=index):
                self.assert_refused(self.handover_url("view", chain), 404)
                self.assert_refused(self.handover_url("delete", chain), 404, "post")
                if index < 3:
                    self.assert_refused(
                        self.handover_url("upload", chain), 404, "post", {"fotos": self.upload()}
                    )

    def test_photo_reads_reject_non_get_methods_before_opening_files(self):
        self.client.force_login(self.employee)
        urls = (
            self.apartment_url(self.apartment_photos[WohnungStatus.TAKEN]),
            self.handover_url("view"),
        )
        for url, method in product(urls, ("head", "post", "put", "patch", "delete", "options")):
            with self.subTest(url=url, method=method):
                self.assert_refused(url, 405, method)

    def test_photo_mutation_endpoints_reject_get_without_changing_files(self):
        self.client.force_login(self.employee)
        for action in ("upload", "delete"):
            self.assert_refused(self.handover_url(action), 405)

    def test_blocked_protocol_photos_cannot_be_changed(self):
        protocol = self.chains[0][0]
        Protokoll.objects.filter(pk=protocol.pk).update(status=ProtokollStatus.BLOCKED)
        self.client.force_login(self.employee)
        before = self.photo_state()
        for action, data in (("upload", {"fotos": self.upload()}), ("delete", {})):
            response = self.client.post(self.handover_url(action), data)
            self.assertRedirects(
                response,
                reverse("wohnungsverwaltung:handover_protocol_detail", args=[protocol.pk]),
                fetch_redirect_response=False,
            )
            self.assertEqual(self.photo_state(), before)

    def test_switching_employee_to_tenant_blocks_private_reads_and_all_photo_changes(self):
        self.client.force_login(self.employee)
        self.assert_photo(self.apartment_url(self.apartment_photos[WohnungStatus.TAKEN]))
        self.assert_photo(self.handover_url("view"))
        self.employee.groups.set([Group.objects.get(name=ROLE_TENANT)])
        self.assert_refused(self.apartment_url(self.apartment_photos[WohnungStatus.TAKEN]), 404)
        self.assert_employee_endpoints_refused(403)

    def test_deactivation_immediately_blocks_private_photos_and_changes_in_existing_session(self):
        self.client.force_login(self.employee)
        self.assert_photo(self.apartment_url(self.apartment_photos[WohnungStatus.TAKEN]))
        self.employee.is_active = False
        self.employee.save(update_fields=["is_active"])
        self.assert_refused(self.apartment_url(self.apartment_photos[WohnungStatus.TAKEN]), 404)
        self.assert_employee_endpoints_refused(302)
        self.assert_photo(self.apartment_url(self.apartment_photos[WohnungStatus.FREE]))

    def test_direct_employee_permission_grants_photo_access_and_revocation_is_immediate(self):
        user = self.create_user("direct")
        permission = Permission.objects.get(
            content_type__app_label="immobilien", codename="access_employee_area"
        )
        user.user_permissions.add(permission)
        self.client.force_login(user)
        self.assert_photo(self.apartment_url(self.apartment_photos[WohnungStatus.BLOCKED]))
        self.assert_photo(self.handover_url("view"))
        unit = self.units[WohnungStatus.TAKEN]
        management_url = reverse("verwaltung:apartment_photos", args=[unit.pk])
        self.assertEqual(self.client.get(management_url).status_code, 200)
        self.assertEqual(
            self.client.post(management_url, {"image": self.upload()}).status_code, 302
        )
        uploaded_apartment_photo = unit.photos.exclude(
            pk=self.apartment_photos[WohnungStatus.TAKEN].pk
        ).get()
        response = self.client.post(self.handover_url("upload"), {"fotos": self.upload()})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RaumMerkmalFoto.objects.count(), 3)
        uploaded_handover_photo = self.chains[0][2].fotos.exclude(pk=self.chains[0][3].pk).get()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(
                self.client.post(
                    reverse(
                        "verwaltung:apartment_photo_delete",
                        args=[unit.pk, uploaded_apartment_photo.pk],
                    )
                ).status_code,
                302,
            )
            uploaded_chain = (*self.chains[0][:3], uploaded_handover_photo)
            self.assertEqual(
                self.client.post(self.handover_url("delete", uploaded_chain)).status_code, 302
            )
        self.assertFalse(ApartmentPhoto.objects.filter(pk=uploaded_apartment_photo.pk).exists())
        self.assertFalse(RaumMerkmalFoto.objects.filter(pk=uploaded_handover_photo.pk).exists())
        self.assertFalse(
            uploaded_apartment_photo.image.storage.exists(uploaded_apartment_photo.image.name)
        )
        self.assertFalse(
            uploaded_handover_photo.datei.storage.exists(uploaded_handover_photo.datei.name)
        )
        user.user_permissions.clear()
        self.assert_refused(self.apartment_url(self.apartment_photos[WohnungStatus.BLOCKED]), 404)
        self.assert_employee_endpoints_refused(403)

    def test_apartment_status_change_hides_previously_public_photo(self):
        photo = self.apartment_photos[WohnungStatus.FREE]
        self.assert_photo(self.apartment_url(photo))
        Wohnung.objects.filter(pk=photo.apartment_id).update(status=WohnungStatus.TAKEN)
        self.assert_refused(self.apartment_url(photo), 404)

    def test_handover_upload_and_delete_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.employee)
        self.assert_refused(
            self.handover_url("upload"), 403, "post", {"fotos": self.upload()}, client=client
        )
        self.assert_refused(self.handover_url("delete"), 403, "post", client=client)

    def test_django_does_not_serve_stored_photo_paths_directly(self):
        paths = [photo.image.url for photo in self.apartment_photos.values()]
        paths += [chain[3].datei.url for chain in self.chains]
        for user in (None, self.employee):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for path in paths:
                self.assert_refused(path, 404)
