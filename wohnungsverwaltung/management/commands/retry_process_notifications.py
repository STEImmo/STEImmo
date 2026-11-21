from django.core.management.base import BaseCommand

from wohnungsverwaltung.models import ProcessNotification
from wohnungsverwaltung.notifications import MAX_ATTEMPTS, send_process_notification


class Command(BaseCommand):
    help = "Verarbeitet höchstens 100 offene Prozessmails; maximal drei eindeutige Versandversuche."

    def handle(self, *args, **options):
        ids = list(
            ProcessNotification.objects.filter(
                status__in=("pending", "failed"),
                attempts__lt=MAX_ATTEMPTS,
            )
            .order_by("created_at", "pk")
            .values_list("pk", flat=True)[:100]
        )
        sent = sum(send_process_notification(pk) for pk in ids)
        self.stdout.write(f"Geprüft: {len(ids)}; zum Versand übergeben: {sent}.")
