"""Retry deletion of proof files queued for deletion."""

import logging

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from wohnungsverwaltung.models import ApplicationProofCleanup

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Retry deletion of proof files queued after removal or a failed save."

    def handle(self, *args, **options):
        cleaned = 0
        failed = 0
        for cleanup in ApplicationProofCleanup.objects.iterator():
            try:
                default_storage.delete(cleanup.storage_name)
                cleanup.delete()
                cleaned += 1
            except Exception as error:
                failed += 1
                logger.error(
                    "Could not retry application proof cleanup for %s (%s).",
                    cleanup.storage_name,
                    type(error).__name__,
                )

        self.stdout.write(f"Bereinigte Nachweise: {cleaned}; fehlgeschlagen: {failed}.")
        if failed:
            raise CommandError(f"{failed} Nachweisdatei(en) konnten nicht bereinigt werden.")
