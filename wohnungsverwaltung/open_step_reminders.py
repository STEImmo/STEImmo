"""Derive reminders from committed application and viewing events."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from .models import (
    ApplicationReviewEvent,
    Bewerbung,
    BewerbungStatus,
    NotificationPreference,
    ViewingAppointment,
    ViewingAppointmentEvent,
)
from .notification_preferences import USER_MAIL_TYPES, mail_allowed

MAIN_REMINDER = "main_application_due"
VIEWING_REMINDER = "viewing_response_due"
REMINDER_TYPES = (MAIN_REMINDER, VIEWING_REMINDER)
MAIN_WAIT = timedelta(hours=48)
VIEWING_MIN_LEAD = timedelta(hours=48)
VIEWING_CUTOFF = timedelta(hours=24)
VIEWING_WINDOW = timedelta(hours=1)


def open_applications():
    return Bewerbung.objects.filter(
        status=BewerbungStatus.OPEN,
        interest_withdrawn_at__isnull=True,
        submitted_at__isnull=True,
        accepted_at__isnull=True,
    ).select_related("person__user")


def current_task(application, now):
    if application.main_application_accessible:
        event = application.review_events.filter(
            kind=ApplicationReviewEvent.Kind.MAIN_UNLOCKED
        ).first()
        if event:
            return MAIN_REMINDER, str(event.pk), event.created_at + MAIN_WAIT
        return None

    appointment = application.viewings.filter(status=ViewingAppointment.Status.PLANNED).first()
    if not appointment or now > appointment.starts_at - VIEWING_CUTOFF:
        return None
    event = appointment.events.filter(
        kind__in=(ViewingAppointmentEvent.Kind.CREATED, ViewingAppointmentEvent.Kind.RESCHEDULED),
        appointment_version=appointment.version,
    ).first()
    if event and appointment.starts_at - event.created_at >= VIEWING_MIN_LEAD:
        return (
            VIEWING_REMINDER,
            str(event.pk),
            appointment.starts_at - VIEWING_CUTOFF - VIEWING_WINDOW,
        )
    return None


def reminder_allowed(account, kind, due_at):
    if not mail_allowed(account, kind):
        return False
    return not NotificationPreference.objects.filter(
        account=account, reminders_changed_at__gt=due_at
    ).exists()


def reminder_message(notice, recipient):
    application = open_applications().filter(pk=notice.object_id, person__user=recipient).first()
    if application is None:
        return None
    now = timezone.now()
    task = current_task(application, now)
    if task is None:
        return None
    kind, version, due_at = task
    if (
        (kind, version) != (notice.kind, notice.version)
        or now < due_at
        or not reminder_allowed(recipient, kind, due_at)
    ):
        return None

    subject = USER_MAIL_TYPES[kind][1]
    if kind == MAIN_REMINDER:
        body = (
            "Bitte vervollständigen Sie Ihre freigeschaltete Hauptbewerbung "
            "und reichen Sie sie ein."
        )
        label = "Eigene Hauptbewerbung öffnen"
        path = reverse("wohnungsverwaltung:main_application_status", args=[application.pk])
    else:
        body = "Bitte antworten Sie auf Ihre Einladung zur Besichtigung."
        label = "Besichtigung in meinen Bewerbungen öffnen"
        path = f"{reverse('wohnungsverwaltung:pre_application_list')}#application-{application.pk}"
    return subject, f"{body} Diese Erinnerung setzt keine neue Frist.", label, path
