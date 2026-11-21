from django.core.management.base import BaseCommand

from wohnungsverwaltung.decision_notifications import deliver_decision_notification
from wohnungsverwaltung.models import DecisionNotification


class Command(BaseCommand):
    help = "Verarbeitet vorgemerkte Entscheidungs- und Abschlussbenachrichtigungen."

    def handle(self, *args, **options):
        states = DecisionNotification.Status
        ids = list(
            DecisionNotification.objects.filter(status__in=(states.PENDING, states.RETRY))
            .order_by("created_at", "pk")
            .values_list("pk", flat=True)
        )
        for notice_id in ids:
            deliver_decision_notification(notice_id)
