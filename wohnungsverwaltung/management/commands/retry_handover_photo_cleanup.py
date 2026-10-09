"""Retry cleanup of files from failed uploads or removed protocol photos."""

import logging

from django.core.management.base import BaseCommand, CommandError

from wohnungsverwaltung.models import HandoverPhotoCleanup, RaumMerkmalFoto

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Retry deletion of protocol photo files after failed uploads or photo removal."

    def handle(self, *args, **options):
        storage = RaumMerkmalFoto._meta.get_field("datei").storage
        cleaned = 0
        failed = 0
        for cleanup in HandoverPhotoCleanup.objects.iterator():
            try:
                if RaumMerkmalFoto.objects.filter(datei=cleanup.storage_name).exists():
                    raise ValueError("Photo is still referenced.")
                storage.delete(cleanup.storage_name)
                cleanup.delete()
                cleaned += 1
            except Exception as error:
                failed += 1
                logger.error("Could not retry photo cleanup (%s).", type(error).__name__)
        self.stdout.write(f"Bereinigte Fotodateien: {cleaned}; fehlgeschlagen: {failed}.")
        if failed:
            raise CommandError(f"{failed} Fotodatei(en) konnten nicht bereinigt werden.")
