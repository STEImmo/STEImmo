import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageDraw
from pypdf import PdfReader

from .handover_export import clean_signature
from .models import (
    AbnahmeStatus,
    Merkmal,
    MerkmalDatentyp,
    Person,
    Protokoll,
    ProtokollSchluessel,
    ProtokollStatus,
    ProtokollTyp,
    Raum,
    RaumMerkmal,
    RaumMerkmalFoto,
    Raumprotokoll,
    UebergabeStatus,
    Wohnung,
)


def signature_file(*, blank=False, size=(1200, 400), image_format="PNG"):
    image = Image.new("RGB", size, "white")
    if not blank:
        ImageDraw.Draw(image).line(
            [(40, 220), (150, 70), (220, 280), (370, 110), (520, 220)], fill="black", width=5
        )
    data = BytesIO()
    image.save(data, image_format)
    return SimpleUploadedFile("signature.png", data.getvalue(), content_type="image/png")


class HandoverExportTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.directory.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.employee = get_user_model().objects.create_user(
            username="employee", first_name="Eva", last_name="Verwaltung"
        )
        self.employee.groups.add(Group.objects.get(name="Mitarbeiter"))
        self.tenant = get_user_model().objects.create_user(username="tenant")
        self.tenant.groups.add(Group.objects.get(name="Mieter"))
        self.person = Person.objects.create(
            user=self.tenant, vorname="Mia", nachname="Mieter", email="mia@example.test"
        )
        self.unit = Wohnung.objects.create(wohnungsnummer="2.04", gebaeudenummer="1")
        self.protocol = Protokoll.objects.create(
            wohnung=self.unit,
            person=self.person,
            vermieter_name="Eva Verwaltung",
            protokoll_typ=ProtokollTyp.MOVE_IN,
            uebergabe_status=UebergabeStatus.RENOVATED,
            abnahme_status=AbnahmeStatus.ACCEPTED,
            heizungsablesungen="IE 120 / IA 110",
            zaehlernummer_wasser_kalt="WK-1",
            zaehlernummer_wasser_warm="WW-1",
            zaehlernummer_heizung="HZ-1",
            zaehlernummer_strom="ST-1",
        )
        self.master_room = Raum.objects.create(wohnung=self.unit, name="Küche")
        self.room = Raumprotokoll.objects.create(
            protokoll=self.protocol, raum=self.master_room, name="Küche"
        )
        self.feature = Merkmal.objects.create(
            bereich="Küche", bezeichnung="Fenster", datentyp=MerkmalDatentyp.OK
        )
        self.item = RaumMerkmal.objects.create(
            raumprotokoll=self.room,
            merkmal=self.feature,
            wert={"text": "Kratzer am Fenster", "angaben": {"Anzahl": "2"}},
        )
        ProtokollSchluessel.objects.create(
            protokoll=self.protocol, anzahl=2, raum_bezeichnung="Wohnungstür"
        )
        self.client.force_login(self.employee)

    def url(self, action, protocol=None):
        return reverse(
            f"wohnungsverwaltung:handover_protocol_{action}", args=[(protocol or self.protocol).pk]
        )

    def signing_data(self, **updates):
        response = self.client.get(self.url("finalize"))
        self.assertEqual(response.status_code, 200)
        data = {
            "content_token": response.context["form"].initial["content_token"],
            "schluessel_ueberprueft": "on",
            "bestaetigung_erklaert": "on",
            "tenant_mode": "signed",
            "mitarbeiter": signature_file(),
            "mieter": signature_file(),
        }
        data.update(updates)
        return data

    def finalize(self, **updates):
        response = self.client.post(self.url("confirm"), self.signing_data(**updates))
        self.assertEqual(response.status_code, 200, response.content)
        self.protocol.refresh_from_db()
        return response

    def pdf(self):
        response = self.client.get(self.url("pdf"))
        self.assertEqual(response.status_code, 200)
        data = b"".join(response.streaming_content)
        return data, PdfReader(BytesIO(data))

    def test_signatures_and_full_content_are_embedded_in_an_immutable_pdf(self):
        photo = signature_file()
        RaumMerkmalFoto.objects.create(
            raum_merkmal=self.item, datei=photo, content_type="image/png", dateigroesse=photo.size
        )
        self.finalize()
        self.assertEqual(self.protocol.status, ProtokollStatus.SIGNED)
        self.assertEqual(self.protocol.unterschriften.count(), 2)
        self.assertEqual(self.protocol.abgeschlossen_von, self.employee)
        original, reader = self.pdf()
        text = "\n".join(page.extract_text() for page in reader.pages)
        for expected in [
            "Mia Mieter",
            "Eva Verwaltung",
            "Wohnung 2.04",
            "Kratzer am Fenster",
            "Anzahl: 2",
            "Wohnungstür",
            "Bestätigung und Unterschriften",
            "Erfasst beim Abschluss",
            "ST-1",
        ]:
            self.assertIn(expected, text)
        # PDF encoders may reuse one image resource for identical test signatures.
        self.assertGreaterEqual(
            sum(p.get_contents().get_data().count(b" Do") for p in reader.pages), 3
        )
        self.unit.wohnungsnummer = "NEU"
        self.unit.save()
        self.person.nachname = "Geändert"
        self.person.save()
        self.feature.bezeichnung = "Geändert"
        self.feature.save()
        self.assertEqual(original, self.pdf()[0])
        response = self.client.post(self.url("confirm"), {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.protocol.unterschriften.count(), 2)
        self.assertEqual(original, self.pdf()[0])

    def test_missing_tenant_signature_requires_and_exports_reason(self):
        data = self.signing_data(tenant_mode="missing", reason="   ")
        data.pop("mieter")
        response = self.client.post(self.url("confirm"), data)
        self.assertEqual(response.status_code, 400)
        self.finalize(tenant_mode="missing", reason="Mieter lehnt die Unterschrift ab.")
        self.assertEqual(self.protocol.unterschriften.count(), 1)
        text = "\n".join(page.extract_text() for page in self.pdf()[1].pages)
        self.assertIn("Mieter hat nicht unterschrieben", text)
        self.assertIn("Mieter lehnt die Unterschrift ab.", text)

    def test_employee_signature_cannot_be_omitted(self):
        data = self.signing_data(tenant_mode="missing", reason="Abwesend")
        data.pop("mitarbeiter")
        self.assertEqual(self.client.post(self.url("confirm"), data).status_code, 400)
        self.protocol.refresh_from_db()
        self.assertEqual(self.protocol.status, ProtokollStatus.OPEN)

    def test_both_declarations_remain_mandatory(self):
        data = self.signing_data()
        data.pop("bestaetigung_erklaert")
        self.assertEqual(self.client.post(self.url("confirm"), data).status_code, 400)

    def test_changed_content_invalidates_signatures(self):
        data = self.signing_data()
        self.item.wert = {"text": "Neue Feststellung"}
        self.item.save()
        response = self.client.post(self.url("confirm"), data)
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["reload"])
        self.assertFalse(self.protocol.unterschriften.exists())

    def test_token_is_bound_to_the_employee_and_protocol(self):
        data = self.signing_data()
        other = get_user_model().objects.create_user(
            username="other", first_name="Eva", last_name="Verwaltung"
        )
        other.groups.add(Group.objects.get(name="Mitarbeiter"))
        self.client.force_login(other)
        self.assertEqual(self.client.post(self.url("confirm"), data).status_code, 409)

    def test_blank_corrupt_oversize_and_non_png_signatures_are_rejected(self):
        candidates = [
            signature_file(blank=True),
            signature_file(size=(400, 200)),
            signature_file(image_format="JPEG"),
            SimpleUploadedFile("bad.png", b"invalid"),
            SimpleUploadedFile("big.png", b"x" * (512 * 1024 + 1)),
        ]
        for candidate in candidates:
            with self.subTest(size=candidate.size), self.assertRaises(ValidationError):
                clean_signature(candidate)

    def test_reason_length_is_limited(self):
        response = self.client.post(
            self.url("confirm"), self.signing_data(tenant_mode="missing", reason="x" * 1001)
        )
        self.assertEqual(response.status_code, 400)

    def test_storage_failure_rolls_back_and_cleans_partial_files(self):
        data = self.signing_data()
        save = default_storage.save
        count = 0

        def fail_pdf(name, content, **kwargs):
            nonlocal count
            count += 1
            if count == 3:
                raise OSError("test failure")
            return save(name, content, **kwargs)

        with patch("wohnungsverwaltung.handover_export.default_storage.save", side_effect=fail_pdf):
            response = self.client.post(self.url("confirm"), data)
        self.assertEqual(response.status_code, 503)
        self.protocol.refresh_from_db()
        self.assertEqual(self.protocol.status, ProtokollStatus.OPEN)
        self.assertFalse(self.protocol.unterschriften.exists())
        self.assertFalse([p for p in Path(self.directory.name).rglob("*") if p.is_file()])

    def test_missing_photo_does_not_create_partial_pdf(self):
        photo = signature_file()
        saved = RaumMerkmalFoto.objects.create(
            raum_merkmal=self.item, datei=photo, content_type="image/png", dateigroesse=photo.size
        )
        data = self.signing_data()
        default_storage.delete(saved.datei.name)
        self.assertEqual(self.client.post(self.url("confirm"), data).status_code, 503)
        self.protocol.refresh_from_db()
        self.assertEqual(self.protocol.dokument_pfad, "")

    def test_corrupt_archive_is_not_rebuilt(self):
        self.finalize()
        with default_storage.open(self.protocol.dokument_pfad, "wb") as target:
            target.write(b"corrupt")
        self.assertEqual(self.client.get(self.url("pdf")).status_code, 503)
        self.client.post(self.url("pdf_create"))
        self.assertEqual(self.client.get(self.url("pdf")).status_code, 503)

    def test_legacy_protocol_is_explicitly_marked_and_created_once(self):
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.bestaetigt_am = timezone.now()
        self.protocol.save()
        response = self.client.post(self.url("pdf_create"))
        self.assertEqual(response.status_code, 302)
        self.protocol.refresh_from_db()
        self.assertTrue(self.protocol.nachtraeglich_gesichert)
        data, reader = self.pdf()
        text = "\n".join(p.extract_text() for p in reader.pages)
        self.assertIn("Nachträglich gesicherter Stand", text)
        self.assertIn("Keine historische Unterschrift", text)
        self.assertFalse(self.protocol.unterschriften.exists())
        self.client.post(self.url("pdf_create"))
        self.assertEqual(data, self.pdf()[0])

    def test_tenant_only_sees_own_signed_protocols_even_after_moving(self):
        self.finalize()
        self.client.force_login(self.tenant)
        self.assertEqual(self.client.get(self.url("pdf")).status_code, 200)
        self.person.wohnung = None
        self.person.save()
        self.assertEqual(self.client.get(self.url("pdf")).status_code, 200)
        self.assertContains(
            self.client.get(reverse("wohnungsverwaltung:handover_protocol_mine")),
            "PDF herunterladen",
        )
        stranger = get_user_model().objects.create_user(username="stranger")
        stranger.groups.add(Group.objects.get(name="Mieter"))
        Person.objects.create(
            user=stranger,
            vorname="Andere",
            nachname="Person",
            email="other@example.test",
            wohnung=self.unit,
        )
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(self.url("pdf")).status_code, 404)
        self.assertEqual(self.client.post(self.url("pdf_create")).status_code, 404)
        self.assertNotContains(
            self.client.get(reverse("wohnungsverwaltung:handover_protocol_mine")),
            "PDF herunterladen",
        )

    def test_permissions_http_methods_and_private_headers(self):
        self.finalize()
        response = self.client.get(self.url("pdf"))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(self.client.get(self.url("pdf_create")).status_code, 405)
        self.assertEqual(self.client.post(self.url("pdf")).status_code, 405)
        self.client.force_login(self.tenant)
        self.assertEqual(self.client.get(self.url("finalize")).status_code, 403)
        self.assertEqual(self.client.post(self.url("confirm"), {}).status_code, 403)
        self.tenant.groups.clear()
        self.client.force_login(self.tenant)
        self.assertEqual(self.client.get(self.url("pdf")).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url("pdf")).status_code, 302)

    def test_open_and_blocked_protocols_cannot_be_exported(self):
        for status in [ProtokollStatus.OPEN, ProtokollStatus.BLOCKED]:
            self.protocol.status = status
            self.protocol.save()
            self.assertEqual(self.client.get(self.url("pdf")).status_code, 404)
            self.assertEqual(self.client.post(self.url("pdf_create")).status_code, 404)

    def test_csrf_is_required_for_finalization_and_legacy_generation(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.employee)
        self.assertEqual(client.post(self.url("confirm"), {}).status_code, 403)
        self.assertEqual(client.post(self.url("pdf_create"), {}).status_code, 403)

    def test_move_out_contains_reference_photos_and_unmatched_points(self):
        photo = signature_file()
        RaumMerkmalFoto.objects.create(
            raum_merkmal=self.item, datei=photo, content_type="image/png", dateigroesse=photo.size
        )
        self.protocol.status = ProtokollStatus.SIGNED
        self.protocol.save()
        old_protocol = self.protocol
        self.protocol = Protokoll.objects.get(pk=old_protocol.pk)
        self.protocol.pk = None
        self.protocol.status = ProtokollStatus.OPEN
        self.protocol.protokoll_typ = ProtokollTyp.MOVE_OUT
        self.protocol.mieter_zukuenftige_anschrift = "Neue Straße 2"
        self.protocol.save()
        new_room = Raumprotokoll.objects.create(
            protokoll=self.protocol, raum=self.master_room, name="Küche"
        )
        new_feature = Merkmal.objects.create(
            bereich="Küche", bezeichnung="Tür", datentyp=MerkmalDatentyp.OK
        )
        RaumMerkmal.objects.create(
            raumprotokoll=new_room, merkmal=new_feature, wert={"text": "Tür beschädigt"}
        )
        ProtokollSchluessel.objects.create(
            protokoll=self.protocol, anzahl=1, raum_bezeichnung="Tür"
        )
        self.finalize()
        text = "\n".join(p.extract_text() for p in self.pdf()[1].pages)
        for expected in [
            "Einzug (Referenz)",
            "Kratzer am Fenster",
            "Tür beschädigt",
            "Kein Gegenstück erfasst",
            "Differenz Auszug minus Einzug",
        ]:
            self.assertIn(expected, text)

    def test_long_multiline_text_renders_across_pages(self):
        self.item.wert = {"text": "Mängelprüfung mit Umlauten: äöü ß < & >\n" * 250}
        self.item.save()
        self.finalize()
        reader = self.pdf()[1]
        self.assertGreater(len(reader.pages), 5)
        self.assertIn("äöü ß < & >", "\n".join(p.extract_text() for p in reader.pages))


class HandoverExportConcurrencyTests(TransactionTestCase):
    setUp = HandoverExportTests.setUp
    url = HandoverExportTests.url
    signing_data = HandoverExportTests.signing_data

    def worker(self, action, data):
        close_old_connections()
        try:
            client = Client()
            client.force_login(get_user_model().objects.get(pk=self.employee.pk))
            return client.post(self.url(action), data)
        finally:
            close_old_connections()

    def test_parallel_confirmations_create_one_archive_and_two_signatures(self):
        token = self.signing_data()["content_token"]
        barrier = threading.Barrier(2)

        def confirm():
            barrier.wait(timeout=10)
            return self.worker(
                "confirm",
                {
                    "content_token": token,
                    "tenant_mode": "signed",
                    "schluessel_ueberprueft": "on",
                    "bestaetigung_erklaert": "on",
                    "mitarbeiter": signature_file(),
                    "mieter": signature_file(),
                },
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(confirm) for _ in range(2)]
            self.assertEqual([f.result(timeout=20) for f in futures], [200, 200])
        self.protocol.refresh_from_db()
        self.assertEqual(self.protocol.unterschriften.count(), 2)
        self.assertEqual(len(list(Path(self.directory.name).rglob("*.pdf"))), 1)

    def test_edit_waits_for_confirmation_and_cannot_change_signed_content(self):
        from .handover_export import render_pdf

        data = self.signing_data()
        rendering = threading.Event()
        release = threading.Event()

        def pause_render(*args):
            rendering.set()
            if not release.wait(timeout=10):
                raise RuntimeError("Test synchronization timed out")
            return render_pdf(*args)

        with patch("wohnungsverwaltung.handover_export.render_pdf", side_effect=pause_render):
            with ThreadPoolExecutor(max_workers=2) as executor:
                confirmation = executor.submit(self.worker, "confirm", data)
                self.assertTrue(rendering.wait(timeout=10))
                mutation = executor.submit(
                    self.worker,
                    "key_create",
                    {
                        "anzahl": "9",
                        "raum_bezeichnung": "Darf nicht hinzugefügt werden",
                    },
                )
                release.set()
                self.assertEqual(confirmation.result(timeout=20).status_code, 200)
                self.assertEqual(mutation.result(timeout=20).status_code, 302)
        self.assertEqual(self.protocol.protokoll_schluessel.count(), 1)
