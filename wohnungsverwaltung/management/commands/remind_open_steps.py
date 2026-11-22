from functools import partial
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from wohnungsverwaltung.decision_notifications import (
    INACTIVE_BACKENDS,
    deliver_decision_notification,
)
from wohnungsverwaltung.models import DecisionNotification
from wohnungsverwaltung.open_step_reminders import (
    REMINDER_TYPES,
    current_task,
    open_applications,
    reminder_allowed,
)
from wohnungsverwaltung.staff_digest import DIGEST_KIND, digest_candidates, queue_digest


class Command(BaseCommand):
    help = "Prüft Erinnerungen an offene Schritte. Ohne --send wird nur eine Vorschau ausgegeben."

    def add_arguments(self, parser):
        parser.add_argument("--send", action="store_true", help="Fällige Erinnerungen versenden.")

    def handle(self, *args, **options):
        send = options["send"]
        if send:
            if settings.DEMO_MODE or settings.EMAIL_BACKEND in INACTIVE_BACKENDS:
                raise CommandError("Versand ist in dieser Umgebung deaktiviert.")
            origin = urlsplit(settings.DECISION_NOTIFICATION_ORIGIN)
            if origin.scheme not in {"http", "https"} or not origin.netloc:
                raise CommandError("Für den Versand fehlt die öffentliche Anwendungsadresse.")

        notices = DecisionNotification.objects.filter(kind__in=REMINDER_TYPES)
        states = DecisionNotification.Status
        due_count = 0
        for application in open_applications().iterator():
            now = timezone.now()
            task = current_task(application, now)
            if task is None:
                continue
            kind, version, due_at = task
            if now < due_at:
                continue

            recipient = application.person.user
            if recipient is None:
                continue
            key = {"kind": kind, "object_id": application.pk, "version": version}
            allowed = reminder_allowed(recipient, kind, due_at)
            if send:
                _, created = notices.get_or_create(
                    **key,
                    defaults={
                        "recipient": recipient,
                        "status": states.PENDING if allowed else states.SUPPRESSED,
                    },
                )
                due_count += int(created and allowed)
            elif allowed and not notices.filter(**key).exists():
                due_count += 1

        for recipient, day, entries in digest_candidates(timezone.now()):
            if send:
                due_count += int(queue_digest(recipient, day, entries))
            else:
                due_count += 1
                self.stdout.write(f"Verwaltungskonto {recipient.pk}, {day}")
                for task in entries:
                    self.stdout.write(
                        f"  {task.reason} seit {timezone.localtime(task.since):%d.%m.%Y %H:%M}"
                    )

        pending = DecisionNotification.objects.filter(
            kind__in=(*REMINDER_TYPES, DIGEST_KIND), status__in=(states.PENDING, states.RETRY)
        ).order_by("pk")
        if send:
            for notice_id in pending.values_list("pk", flat=True).iterator():
                transaction.on_commit(
                    partial(deliver_decision_notification, notice_id), robust=True
                )
            self.stdout.write(f"Neu für den Versand vorgemerkt: {due_count}")
        else:
            self.stdout.write(f"Vorschau: {due_count} neue fällige Erinnerungen.")
