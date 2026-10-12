"""Retry cleanup of PDF and signature files from failed archive transactions."""

from django.core.management.base import BaseCommand, CommandError

from wohnungsverwaltung.handover_archive_files import cleanup_archive_file
from wohnungsverwaltung.models import HandoverArchiveCleanup


class Command(BaseCommand):
    help = "Retry deletion of unreferenced handover PDF and signature files."

    def handle(self, *args, **options):
        cleaned = 0
        failed = 0
        for cleanup in HandoverArchiveCleanup.objects.iterator():
            if cleanup_archive_file(cleanup):
                cleaned += 1
            else:
                failed += 1
        self.stdout.write(f"Bereinigte Archivdateien: {cleaned}; fehlgeschlagen: {failed}.")
        if failed:
            raise CommandError(f"{failed} Archivdatei(en) konnten nicht bereinigt werden.")
