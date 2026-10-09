from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from . import test_handover_export as fixtures
from .models import (
    Protokoll,
    ProtokollSchluessel,
    ProtokollTyp,
    RaumMerkmal,
    Raumprotokoll,
    WohnungStatus,
)


class HandoverChronologyTests(TestCase):
    setUp = fixtures.HandoverExportTests.setUp
    url = fixtures.HandoverExportTests.url
    signing_data = fixtures.HandoverExportTests.signing_data
    finalize = fixtures.HandoverExportTests.finalize

    def test_older_move_out_preserves_newer_confirmed_occupancy(self):
        self.protocol.uebergabe_zeitpunkt = timezone.now() - timedelta(days=1)
        self.protocol.save()
        older_move_out = Protokoll.objects.get(pk=self.protocol.pk)
        older_move_out.pk = None
        older_move_out.protokoll_typ = ProtokollTyp.MOVE_OUT
        older_move_out.uebergabe_zeitpunkt = timezone.now() - timedelta(days=2)
        older_move_out.mieter_zukuenftige_anschrift = "Neue Testadresse 4"
        older_move_out.save()
        room = Raumprotokoll.objects.create(
            protokoll=older_move_out, raum=self.master_room, name="Küche"
        )
        RaumMerkmal.objects.create(
            raumprotokoll=room, merkmal=self.feature, wert={"text": "Testfeststellung"}
        )
        ProtokollSchluessel.objects.create(
            protokoll=older_move_out, anzahl=2, raum_bezeichnung="Wohnungstür"
        )

        self.finalize()
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, WohnungStatus.TAKEN)
        self.protocol = older_move_out
        self.finalize()
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, WohnungStatus.TAKEN)
